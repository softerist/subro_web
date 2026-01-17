import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from app.core.config import settings

# Import all models to ensure they are registered in the registry
from app.db import base  # noqa: F401

try:
    from app.tasks.celery_app import celery_app  # type: ignore
except ImportError:
    from celery import Celery

    logger_celery_fallback = logging.getLogger(__name__ + ".celery_fallback")
    logger_celery_fallback.warning(
        "Celery app not found at app.tasks.celery_app. Using a basic placeholder. "
        "Ensure CELERY_BROKER_URL and CELERY_RESULT_BACKEND are set in .env if this fallback is used."
    )
    # Make sure CELERY_BROKER_URL and CELERY_RESULT_BACKEND are properties in your settings
    celery_broker_url_val = getattr(settings, "CELERY_BROKER_URL", None)
    celery_result_backend_val = getattr(settings, "CELERY_RESULT_BACKEND", None)

    if not celery_broker_url_val or not celery_result_backend_val:
        logger_celery_fallback.error(
            "CELERY_BROKER_URL or CELERY_RESULT_BACKEND is missing in settings for Celery fallback. "
            "Celery placeholder will not function correctly."
        )
        # Assign some default dummy values if you want the app to start even if celery is misconfigured
        # Otherwise, this could be a place to raise an error or exit.
        celery_broker_url_val = celery_broker_url_val or "redis://localhost:6379/0"
        celery_result_backend_val = celery_result_backend_val or "redis://localhost:6379/0"

    celery_app = Celery(
        "tasks_placeholder",
        broker=str(celery_broker_url_val),
        backend=str(celery_result_backend_val),
    )
    celery_app.conf.update(task_track_started=True)
    logger_celery_fallback.info(
        f"Celery placeholder configured with broker: {celery_broker_url_val} and backend: {celery_result_backend_val}"
    )


from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_users.exceptions import UserNotExists
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.admin import admin_router
from app.api.routers.audit import audit_router
from app.api.routers.auth import auth_router as custom_auth_router
from app.api.routers.dashboard import router as dashboard_router
from app.api.routers.files import router as files_router
from app.api.routers.jobs import router as jobs_router
from app.api.routers.mfa import router as mfa_router
from app.api.routers.onboarding import router as onboarding_router
from app.api.routers.settings import router as settings_router
from app.api.routers.storage_paths import router as storage_paths_router
from app.api.routers.translation_stats import router as translation_stats_router
from app.api.routers.users import router as users_router
from app.api.routers.webhook_keys import router as webhook_keys_router
from app.api.websockets.job_logs import router as job_logs_websocket_router
from app.core.rate_limit import limiter  # Import the limiter instance
from app.core.request_context import RequestContextMiddleware
from app.core.users import UserManager
from app.db import session as db_session_module
from app.db.models.user import User as UserModel
from app.db.session import (
    get_async_session,  # Dependency for path operations
    lifespan_db_manager,  # Manages DB init/dispose for FastAPI
)
from app.schemas.user import UserCreate

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# --- Lifespan Management ---
@asynccontextmanager
async def lifespan(_app_instance: FastAPI) -> AsyncGenerator[None, None]:  # noqa: C901
    logger.info(f"Starting up {settings.APP_NAME} v{settings.APP_VERSION}...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # 1. Initialize FastAPI's database resources via lifespan_db_manager
    # This call is expected to populate `db_session_module.fastapi_async_engine`
    # and `db_session_module.FastAPISessionLocal`.
    try:
        await lifespan_db_manager(_app_instance, "startup")
        logger.info("LIFESPAN_HOOK: Database resources initialized via lifespan_db_manager.")
    except Exception as e:
        logger.critical(
            f"LIFESPAN_HOOK: CRITICAL - Failed to initialize database resources: {e}", exc_info=True
        )
        raise  # Re-raise to stop app startup if DB init fails

    # 2. Superuser creation:
    # Now, check `db_session_module.FastAPISessionLocal` which should have been set by lifespan_db_manager.
    if (
        db_session_module.FastAPISessionLocal
        and settings.FIRST_SUPERUSER_EMAIL
        and settings.FIRST_SUPERUSER_PASSWORD
    ):
        logger.info(
            f"LIFESPAN_HOOK: Checking for existing superusers before creating: {settings.FIRST_SUPERUSER_EMAIL}"
        )
        # Use the FastAPISessionLocal from the db_session_module
        async with db_session_module.FastAPISessionLocal() as session:
            try:
                # First, check if ANY active superuser already exists
                existing_superuser_stmt = (
                    select(UserModel)
                    .where(
                        UserModel.is_superuser == True,  # noqa: E712
                        UserModel.is_active == True,  # noqa: E712
                    )
                    .limit(1)
                )
                existing_superuser_result = await session.execute(existing_superuser_stmt)
                existing_superuser = existing_superuser_result.scalar_one_or_none()

                if existing_superuser:
                    logger.info(
                        f"LIFESPAN_HOOK: Active superuser already exists: {existing_superuser.email} (ID: {existing_superuser.id}). "
                        f"Skipping creation of {settings.FIRST_SUPERUSER_EMAIL}."
                    )
                else:
                    # No active superuser exists, create one
                    user_db_adapter: SQLAlchemyUserDatabase = SQLAlchemyUserDatabase(
                        session, UserModel
                    )
                    user_manager = UserManager(user_db_adapter)

                    try:
                        existing_user = await user_manager.get_by_email(
                            settings.FIRST_SUPERUSER_EMAIL
                        )
                        if existing_user:
                            logger.info(
                                f"LIFESPAN_HOOK: Initial superuser {settings.FIRST_SUPERUSER_EMAIL} (ID: {existing_user.id}) already exists."
                            )
                    except UserNotExists:
                        logger.info(
                            f"LIFESPAN_HOOK: No superusers found. Creating initial superuser: {settings.FIRST_SUPERUSER_EMAIL}"
                        )
                        user_create_data = UserCreate(
                            email=settings.FIRST_SUPERUSER_EMAIL,
                            password=settings.FIRST_SUPERUSER_PASSWORD,
                            is_superuser=True,
                            is_active=True,
                            is_verified=True,
                            role="admin",
                        )
                        created_user_orm_instance = await user_manager.create(
                            user_create_data, safe=False
                        )
                        await session.commit()
                        await session.refresh(created_user_orm_instance)
                        logger.info(
                            f"LIFESPAN_HOOK: Initial superuser {settings.FIRST_SUPERUSER_EMAIL} (ID: {created_user_orm_instance.id}) created."
                        )
            except Exception as e:
                await session.rollback()
                logger.error(
                    f"LIFESPAN_HOOK: Error during initial superuser creation: {e}", exc_info=True
                )
    elif not db_session_module.FastAPISessionLocal:
        logger.error(
            "LIFESPAN_HOOK: db_session_module.FastAPISessionLocal is None after DB initialization attempt. Skipping superuser creation."
        )
    else:
        logger.warning(
            "LIFESPAN_HOOK: FIRST_SUPERUSER_EMAIL or FIRST_SUPERUSER_PASSWORD not set. Skipping superuser creation."
        )

    # 3. Ensure Webhook Key (Auto-generation)
    if db_session_module.FastAPISessionLocal:
        async with db_session_module.FastAPISessionLocal() as session:
            try:
                from app.api.routers.webhook_keys import ensure_default_webhook_key

                await ensure_default_webhook_key(session)
            except Exception as e:
                logger.error(
                    f"LIFESPAN_HOOK: Error ensuring default webhook key: {e}", exc_info=True
                )

    yield  # Application runs here

    # --- Shutdown logic ---
    logger.info(f"Shutting down {settings.APP_NAME}...")
    try:
        await lifespan_db_manager(_app_instance, "shutdown")
        logger.info("LIFESPAN_HOOK: Database resources disposed via lifespan_db_manager.")
    except Exception as e:
        logger.error(f"LIFESPAN_HOOK: Error during database resource disposal: {e}", exc_info=True)


advertised_host = "localhost" if settings.SERVER_HOST == "0.0.0.0" else settings.SERVER_HOST  # nosec B104
server_protocol = "https" if settings.USE_HTTPS else "http"
advertised_server_url_base = f"{server_protocol}://{advertised_host}:{settings.SERVER_PORT}"

if hasattr(settings, "ROOT_PATH") and settings.ROOT_PATH and settings.ROOT_PATH.strip("/"):
    effective_root_path = "/" + settings.ROOT_PATH.strip("/")
    openapi_server_url = (
        f"{advertised_server_url_base}{effective_root_path if effective_root_path != '/' else ''}"
    )
else:
    effective_root_path = ""
    openapi_server_url = advertised_server_url_base

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    lifespan=lifespan,
    root_path=effective_root_path,
    openapi_url=settings.OPENAPI_URL,
    docs_url=settings.DOCS_URL,
    redoc_url=settings.REDOC_URL,
    servers=[{"url": openapi_server_url, "description": "Current environment server"}],
    openapi_components={
        "securitySchemes": {
            "OAuth2PasswordBearer": {
                "type": "oauth2",
                "flows": {
                    "password": {
                        "tokenUrl": f"{effective_root_path}{settings.API_V1_STR}/auth/login",
                        "scopes": {},
                    }
                },
            }
        }
    },
)

# --- Request Context Middleware (added early) ---
app.add_middleware(RequestContextMiddleware)

# --- Rate Limiting Setup ---
app.state.limiter = limiter

# --- Root Redirect ---
if settings.ENVIRONMENT == "development":
    from fastapi.responses import RedirectResponse

    @app.get("/", include_in_schema=False, response_model=None)
    async def root_redirect() -> RedirectResponse | dict[str, str]:
        """Redirect root to API documentation in development."""
        if settings.DOCS_URL:
            return RedirectResponse(url=settings.DOCS_URL)
        return {"status": "running", "environment": "development"}


# --- Custom Rate Limit Exception Handler for Security Logging ---
async def security_rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom rate limit handler that logs to security log for fail2ban.
    """
    from app.core.rate_limit import get_real_client_ip
    from app.core.security_logger import security_log

    client_ip = get_real_client_ip(request)
    endpoint = request.url.path

    # Log rate limit violation for fail2ban
    security_log.rate_limited(client_ip, endpoint)

    # Return standard 429 response
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )


app.add_exception_handler(RateLimitExceeded, security_rate_limit_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)

if settings.BACKEND_CORS_ORIGINS:
    origins = [
        str(origin).strip("/") for origin in settings.BACKEND_CORS_ORIGINS if str(origin).strip("/")
    ]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[
                "Content-Type",
                "Authorization",
                "X-API-Key",
                "X-Onboarding-Token",
                "Accept",
                "Origin",
                "X-Requested-With",
            ],
        )
        logger.info(f"CORS enabled for origins: {origins}")
    else:
        logger.warning("BACKEND_CORS_ORIGINS configured but resulted in an empty list.")
else:
    logger.info("CORS disabled (BACKEND_CORS_ORIGINS not configured).")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    error_details = exc.errors()
    log_body = None
    if settings.DEBUG and request.method in ["POST", "PUT", "PATCH"]:
        try:
            body_bytes = await request.body()
            log_body = body_bytes.decode()
        except Exception:
            log_body = "<Could not read or decode body>"
    logger.warning(
        "Request validation error: %s %s - Errors: %s",
        request.method,
        request.url.path,
        error_details,
        extra={"errors": error_details, "request_body": log_body},
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": error_details}
    )


@app.exception_handler(HTTPException)
async def http_exception_handler_custom(request: Request, exc: HTTPException) -> JSONResponse:
    # Audit 403 Forbidden
    if exc.status_code == status.HTTP_403_FORBIDDEN:
        from app.core.rate_limit import get_real_client_ip
        from app.db.session import FastAPISessionLocal
        from app.services import audit_service

        if FastAPISessionLocal:
            client_ip = get_real_client_ip(request)
            async with FastAPISessionLocal() as db:
                await audit_service.log_event(
                    db,
                    category="security",
                    action="security.permission_denied",
                    severity="warning",
                    success=False,
                    details={
                        "endpoint": request.url.path,
                        "method": request.method,
                        "reason": str(exc.detail),
                        "client_ip": client_ip,
                    },
                    http_status=403,
                )
                await db.commit()

    log_message = "HTTPException: Status=%s, Detail='%s' for %s %s"
    log_args = (exc.status_code, exc.detail, request.method, request.url.path)
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error(log_message, *log_args, exc_info=True)
    else:
        logger.warning(log_message, *log_args)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def generic_exception_handler_custom(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception during request: %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected internal server error occurred."},
    )


# --- API v1 Router Definition and Inclusions ---
api_v1_router = APIRouter()
api_v1_router.include_router(
    custom_auth_router, prefix="/auth", tags=["Auth - Authentication & Authorization"]
)
api_v1_router.include_router(audit_router)  # prefix is already "/admin/audit" in router
api_v1_router.include_router(users_router, prefix="/users", tags=["Users - User Management"])
api_v1_router.include_router(admin_router, prefix="/admin", tags=["Admins - Admin Management"])
api_v1_router.include_router(
    jobs_router, prefix="/jobs", tags=["Jobs - Subtitle Download Management"]
)

api_v1_router.include_router(
    dashboard_router, prefix="/dashboard", tags=["Dashboard - External Services"]
)
api_v1_router.include_router(storage_paths_router, prefix="/storage-paths", tags=["Storage Paths"])

# *** ONBOARDING AND SETTINGS ROUTERS ***
# Onboarding is PUBLIC (no auth required) - used for initial configuration wizard
api_v1_router.include_router(onboarding_router)  # prefix is already "/onboarding" in router
# Settings requires admin auth - used for updating configuration after setup
api_v1_router.include_router(settings_router)  # prefix is already "/settings" in router
# MFA - Multi-Factor Authentication endpoints
api_v1_router.include_router(mfa_router)  # prefix is already "/auth/mfa" in router
# Translation statistics - requires admin auth
api_v1_router.include_router(
    translation_stats_router
)  # prefix is already "/translation-stats" in router
# File download - requires admin auth
api_v1_router.include_router(files_router)  # prefix is already "/files" in router
# Webhook key management - requires admin auth
api_v1_router.include_router(
    webhook_keys_router
)  # prefix is already "/settings/webhook-key" in router

ws_api_v1_router = APIRouter()
ws_api_v1_router.include_router(
    job_logs_websocket_router,
    # No prefix here, as the full path is defined in job_logs.py,
    # and this sub-router is just for grouping.
    # The prefix is already set in job_logs.py's own APIRouter if needed, or handled by its @router.websocket
    tags=["WebSockets - Job Logs"],
)
api_v1_router.include_router(ws_api_v1_router, prefix="/ws")  # This adds the /ws segment

# Option 2: Attach directly to `app` (would be /ws/jobs/... if job_logs_websocket_router had prefix="/ws")
# app.include_router(job_logs_websocket_router, prefix="/ws", tags=["WebSockets - Job Logs"])


@api_v1_router.get("/", tags=["API Root"], summary="API v1 Root Endpoint")
async def api_v1_root_endpoint() -> dict[str, str | None]:
    return {
        "message": f"Welcome to {settings.APP_NAME} - API Version 1",
        "version": settings.APP_VERSION,
        "documentation_url": app.docs_url,
    }


if settings.ENVIRONMENT != "production":

    @api_v1_router.get("/test-db-users", tags=["Debug"])
    async def test_db_users(
        db: AsyncSession = Depends(get_async_session),
    ) -> dict[str, str]:
        try:
            stmt = select(UserModel).limit(1)
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            if user:
                return {"status": "User table accessible", "first_user_email": user.email}
            return {"status": "User table accessible, but no users found."}
        except Exception as e:
            logger.error(f"Error in /test-db-users: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"DB Test Error: {e!s}") from e


# --- Health Check Endpoints ---
# Move health_check_api_v1_detailed to be registered conditionally on app
if settings.HEALTHZ_URL:

    @app.get(
        settings.HEALTHZ_URL,
        tags=["Health Checks"],
        summary="Detailed API and Dependencies Health Check",
        status_code=status.HTTP_200_OK,
    )
    async def health_check_api_v1_detailed(
        db: AsyncSession = Depends(get_async_session),
    ) -> dict[str, Any]:
        db_status = "unavailable"
        try:
            await db.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception as e:
            logger.error(
                f"Health check (detailed): Database connection failed. Error: {e}",
                exc_info=settings.DEBUG,
            )
        dependencies_status = {"database": db_status}
        overall_status = (
            "ok"
            if all(status == "connected" for status in dependencies_status.values())
            else "degraded"
        )
        if overall_status == "ok":
            return {"status": overall_status, "dependencies": dependencies_status}
        logger.error(
            f"API health check (detailed) failed. Status: {overall_status}, Dependencies: {dependencies_status}"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": overall_status, "dependencies": dependencies_status},
        )


app.include_router(api_v1_router, prefix=settings.API_V1_STR)


# --- Health Check Endpoint (at app root) ---
@app.get(
    "/health",
    tags=["System Health"],
    summary="Basic System Liveness Check",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def health_check_basic_system() -> dict[str, str]:
    return {"status": "healthy"}


# --- Main entry point for Uvicorn direct run ---
if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Uvicorn server directly for {settings.APP_NAME} (local debugging)...")
    uvicorn.run(
        "app.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
