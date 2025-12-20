# backend/app/api/websockets/job_logs.py
import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketState

from app.core.config import settings
from app.core.users import UserManager, get_user_manager
from app.db.models.job import Job  # Assuming Job model exists
from app.db.models.user import User  # Assuming User model has .role and .is_superuser
from app.db.session import get_async_session

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Custom Exceptions for WebSocket Flow Control ---
class WebSocketFlowException(Exception):
    """Base exception for controlled error handling in WebSocket flows."""

    def __init__(self, code: int, reason: str | None = None, error_payload: dict | None = None):
        self.code = code
        self.reason = reason
        self.error_payload = error_payload
        super().__init__(reason or "WebSocket flow exception")


class JobNotFoundForStreamError(WebSocketFlowException):
    def __init__(self, job_id: UUID):
        super().__init__(
            code=status.WS_1003_UNSUPPORTED_DATA,
            reason=f"Job {job_id} not found",
            error_payload={"type": "error", "payload": {"message": f"Job {job_id} not found"}},
        )


class JobAccessForbiddenForStreamError(WebSocketFlowException):
    def __init__(self, job_id: UUID):
        super().__init__(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=f"Forbidden to access logs for job {job_id}",
            error_payload={
                "type": "error",
                "payload": {"message": "Forbidden to access this job's logs"},
            },
        )
        self.job_id = job_id


class RedisConfigurationError(WebSocketFlowException):
    def __init__(self):
        super().__init__(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Server configuration error for log streaming.",
            error_payload={
                "type": "error",
                "payload": {"message": "Server configuration error for log streaming."},
            },
        )


class RedisConnectionError(WebSocketFlowException):
    def __init__(self):
        super().__init__(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Log streaming service temporarily unavailable.",
            error_payload={
                "type": "error",
                "payload": {"message": "Log streaming service temporarily unavailable."},
            },
        )


# --- Dependency for WebSocket Authentication ---
async def get_current_user_ws(
    token: str = Query(...), user_manager: UserManager = Depends(get_user_manager)
) -> User:
    credentials_exception = WebSocketDisconnect(
        code=status.WS_1008_POLICY_VIOLATION, reason="Invalid authentication credentials"
    )

    if not token:
        logger.warning("WebSocket connection attempt without token.")
        raise credentials_exception

    try:
        logger.debug(f"Attempting to decode token for WebSocket: {token[:20]}...")
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience="fastapi-users:auth",
        )
        user_id_str: str | None = payload.get("sub")

        if user_id_str is None:
            token_type_for_log: str | None = payload.get("type")
            logger.warning(
                "Invalid token payload for WebSocket: user_id_str is None. "
                f"(token_type was: {token_type_for_log})"
            )
            raise credentials_exception

        user_id = UUID(user_id_str)

    except JWTError as e:
        logger.warning(f"JWTError during WebSocket token decoding: {e}", exc_info=settings.DEBUG)
        raise credentials_exception from e
    except ValueError as e:
        logger.warning(
            "ValueError during WebSocket token decoding (user_id not UUID): "
            f"{user_id_str if 'user_id_str' in locals() else 'UNKNOWN'}",
            exc_info=settings.DEBUG,
        )
        raise credentials_exception from e
    except Exception as e:
        logger.error(f"Unexpected error during WebSocket token decoding: {e}", exc_info=True)
        raise credentials_exception from e

    user = await user_manager.get(user_id)
    if user is None:
        logger.warning(f"User not found for ID from WebSocket token: {user_id}")
        raise credentials_exception
    if not user.is_active:
        logger.warning(f"Inactive user attempted WebSocket connection: {user.id}")
        raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION, reason="Inactive user")

    logger.info(f"WebSocket authenticated user: {user.email} (ID: {user.id})")
    return user


# --- Helper Functions for websocket_job_log_stream ---
async def _validate_job_access_for_stream(
    job_id: UUID, current_user: User, db: AsyncSession
) -> Job:
    """Validates if the user can access the job's logs. Raises WebSocketFlowException on failure."""
    logger.debug(f"Validating access for user {current_user.email} to job {job_id}")
    job = await db.get(Job, job_id)
    if not job:
        raise JobNotFoundForStreamError(job_id)

    is_authorized = (
        (job.user_id == current_user.id)
        or (current_user.role == "admin")
        or current_user.is_superuser
    )

    if not is_authorized:
        raise JobAccessForbiddenForStreamError(job_id)

    logger.info(f"User {current_user.email} authorized for job {job_id} logs.")
    return job


@asynccontextmanager
async def redis_pubsub_listener(redis_url: str, channel_name: str, job_id: UUID):
    """Manages Redis connection and Pub/Sub subscription."""
    if not redis_url:
        logger.error(f"REDIS_PUBSUB_URL not configured for job {job_id}.")
        raise RedisConfigurationError()

    redis_client: AsyncRedis | None = None
    pubsub = None
    try:
        redis_client = AsyncRedis.from_url(str(redis_url), encoding="utf-8", decode_responses=False)
        await redis_client.ping()
        logger.info(f"Successfully connected to Redis for Pub/Sub for job {job_id}.")

        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel_name)
        logger.info(f"Subscribed to Redis channel '{channel_name}' for job {job_id}.")
        yield pubsub
    except Exception as e:
        logger.error(
            f"Failed to setup or connect to Redis Pub/Sub for job {job_id}: {e}", exc_info=True
        )
        raise RedisConnectionError() from e
    finally:
        if pubsub and pubsub.connection:
            try:
                await pubsub.unsubscribe(channel_name)
                logger.info(f"Unsubscribed from Redis channel '{channel_name}' for job {job_id}.")
            except Exception as unsub_err:
                logger.error(
                    f"Error unsubscribing pubsub for job {job_id}: {unsub_err}", exc_info=True
                )
        if redis_client:
            try:
                await redis_client.aclose()
                logger.info(f"Closed Redis client connection for job {job_id}.")
            except Exception as redis_close_err:
                logger.error(
                    f"Error closing Redis client for job {job_id}: {redis_close_err}", exc_info=True
                )


async def _websocket_monitor_task(websocket: WebSocket, job_id: UUID):
    """Monitors the WebSocket for client-side disconnections."""
    try:
        while True:
            await websocket.receive_text()
            logger.debug(
                f"WebSocket monitor for job {job_id} received keepalive/data, connection active."
            )
    except WebSocketDisconnect:
        logger.info(f"WebSocket client for job {job_id} disconnected (detected by monitor_task).")
        raise


async def _redis_to_websocket_forwarder_task(websocket: WebSocket, listener, job_id: UUID):
    """Listens to Redis Pub/Sub and forwards messages to the WebSocket."""
    try:
        async for message in listener.listen():  # listener is the pubsub object
            if websocket.client_state == WebSocketState.DISCONNECTED:
                logger.info(
                    f"WebSocket disconnected (checked in forwarder for job {job_id}). Aborting forwarder."
                )
                break

            if message and message["type"] == "message":
                message_data_bytes: bytes = message["data"]
                message_data_str = message_data_bytes.decode("utf-8")
                logger.debug(
                    f"Forwarding message from Redis for job {job_id}: {message_data_str[:200]}"
                )
                await websocket.send_text(message_data_str)
            elif message and message["type"] == "subscribe":
                logger.debug(
                    f"PubSub subscribe confirmation received by forwarder for job {job_id}."
                )
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected during send_text for job {job_id}.")
    except Exception as e:
        logger.error(f"Error in Redis-to-WebSocket forwarder for job {job_id}: {e}", exc_info=True)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.send_json(
                    {
                        "type": "error",
                        "payload": {"message": "Log streaming interrupted due to server error."},
                    }
                )
            except Exception:
                logger.warning(
                    f"Could not send error to client for job {job_id} during forwarder exception."
                )
        raise


async def _handle_websocket_flow_exception(
    websocket: WebSocket, exc: WebSocketFlowException, job_id: UUID, user_email: str
):
    """Handles custom WebSocketFlowException by logging and sending appropriate response to client."""
    logger.warning(
        f"WebSocketFlowException for job {job_id} (user {user_email}): {exc.reason} (Code: {exc.code})"
    )
    if exc.error_payload and websocket.client_state != WebSocketState.DISCONNECTED:
        try:
            await websocket.send_json(exc.error_payload)
        except Exception:
            pass  # Suppress errors during error reporting
    if websocket.client_state != WebSocketState.DISCONNECTED:
        await websocket.close(code=exc.code, reason=exc.reason)


async def _run_streaming_session(  # noqa: C901
    websocket: WebSocket, job_id: UUID, current_user: User, db: AsyncSession
):
    """Manages the core log streaming session including tasks and Redis listener."""
    await _validate_job_access_for_stream(job_id, current_user, db)

    redis_channel_name = f"job:{job_id}:logs"
    monitor_task = None  # Initialize to None
    forwarder_task = None  # Initialize to None

    try:
        async with redis_pubsub_listener(
            str(settings.REDIS_PUBSUB_URL), redis_channel_name, job_id
        ) as listener:
            await websocket.send_json(
                {
                    "type": "system",
                    "payload": {"message": "Log streaming started.", "job_id": str(job_id)},
                }
            )

            # Fetch and send history from Redis list for late subscribers
            try:
                history_redis = AsyncRedis.from_url(
                    str(settings.REDIS_PUBSUB_URL), encoding="utf-8", decode_responses=False
                )
                try:
                    history_key = f"job:{job_id}:history"
                    history_items = await history_redis.lrange(history_key, 0, -1)
                    if history_items:
                        logger.debug(
                            f"Sending {len(history_items)} historical log items for job {job_id}"
                        )
                        for item in history_items:
                            # Direct send_text as items are already JSON strings
                            await websocket.send_text(item.decode("utf-8"))
                finally:
                    await history_redis.aclose()
            except Exception as e_hist:
                logger.error(f"Failed to fetch log history for job {job_id}: {e_hist}")

            monitor_task = asyncio.create_task(
                _websocket_monitor_task(websocket, job_id), name=f"monitor-{job_id}"
            )
            forwarder_task = asyncio.create_task(
                _redis_to_websocket_forwarder_task(websocket, listener, job_id),
                name=f"forwarder-{job_id}",
            )

            done, pending = await asyncio.wait(
                [monitor_task, forwarder_task], return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()
            for task in done:
                if task.exception():
                    raise task.exception()
        logger.info(f"Log streaming session ended normally for job {job_id}.")
    finally:
        # Ensure tasks are cancelled if an exception occurred that prevented normal completion of asyncio.wait
        # or if they were in 'pending' list from asyncio.wait.
        for task in [monitor_task, forwarder_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task  # Give task a chance to handle cancellation
                except asyncio.CancelledError:
                    logger.debug(
                        f"Task {task.get_name()} for job {job_id} confirmed cancelled during session cleanup."
                    )
                except Exception as task_cleanup_err:
                    logger.error(
                        f"Error during task {task.get_name()} cleanup for job {job_id}: {task_cleanup_err}",
                        exc_info=False,  # Keep log concise for cleanup errors
                    )


# --- Main WebSocket Endpoint ---
@router.websocket("/jobs/{job_id}/logs")
async def websocket_job_log_stream(
    websocket: WebSocket,
    job_id: UUID,
    current_user: User = Depends(get_current_user_ws),
    db: AsyncSession = Depends(get_async_session),
):
    logger.info(
        f"User {current_user.email} attempting WebSocket connection for job_id: {job_id} from {websocket.client}"
    )
    await websocket.accept()

    try:
        await _run_streaming_session(websocket, job_id, current_user, db)

    except WebSocketFlowException as wf_exc:
        await _handle_websocket_flow_exception(websocket, wf_exc, job_id, current_user.email)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for job_id: {job_id} by user {current_user.email}.")
    except (
        asyncio.CancelledError
    ):  # This would typically be caught if websocket_job_log_stream itself is cancelled
        logger.info(f"Main streaming handler for job {job_id} was cancelled.")
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close(
                code=status.WS_1001_GOING_AWAY, reason="Stream cancelled by server"
            )
    except Exception as e:
        logger.error(
            f"Unexpected error in WebSocket handler for job_id {job_id} (user {current_user.email}): {e}",
            exc_info=True,
        )
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    finally:
        if websocket.client_state != WebSocketState.DISCONNECTED:
            logger.warning(
                f"WebSocket for job {job_id} still open in final 'finally' block of main handler; closing."
            )
            try:
                await websocket.close(code=status.WS_1001_GOING_AWAY)
            except Exception:
                pass

        logger.info(
            f"Finished all cleanup for WebSocket connection for job_id: {job_id} (user {current_user.email})"
        )
