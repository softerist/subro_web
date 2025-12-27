# backend/app/main.py
import logging
from contextlib import asynccontextmanager

# --- Project Specific Imports ---
from app.core.config import settings

# Import all models to ensure they are registered in the registry
from app.db import base  # noqa: F401

# Celery import (your existing fallback logic is good)
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
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Import Routers
from app.api.routers.admin import admin_router
from app.api.routers.auth import auth_router as custom_auth_router
from app.api.routers.dashboard import router as dashboard_router
from app.api.routers.files import router as files_router
from app.api.routers.jobs import router as jobs_router
from app.api.routers.settings import router as settings_router

# *** NEW IMPORTS FOR SETUP AND SETTINGS ROUTERS ***
from app.api.routers.setup import router as setup_router
from app.api.routers.storage_paths import router as storage_paths_router
from app.api.routers.translation_stats import router as translation_stats_router
from app.api.routers.users import router as users_router

# *** NEW IMPORT FOR WEBSOCKET ROUTER ***
from app.api.websockets.job_logs import router as job_logs_websocket_router
from app.core.rate_limit import limiter  # Import the limiter instance

# --- Imports for initial superuser creation & DB management ---
from app.core.users import UserManager

# Import the session module itself to access its members after initialization
from app.db import session as db_session_module
from app.db.models.user import User as UserModel
from app.db.session import (
    get_async_session,  # Dependency for path operations
    lifespan_db_manager,  # Manages DB init/dispose for FastAPI
)
from app.schemas.user import UserCreate

# Configure basic logging (ensure this is done early)
logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# --- Lifespan Management ---
@asynccontextmanager
async def lifespan(_app_instance: FastAPI):
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
            f"LIFESPAN_HOOK: Attempting to create/ensure initial superuser: {settings.FIRST_SUPERUSER_EMAIL}"
        )
        # Use the FastAPISessionLocal from the db_session_module
        async with db_session_module.FastAPISessionLocal() as session:
            try:
                user_db_adapter = SQLAlchemyUserDatabase(session, UserModel)
                user_manager = UserManager(user_db_adapter)

                try:
                    existing_user = await user_manager.get_by_email(settings.FIRST_SUPERUSER_EMAIL)
                    if existing_user:
                        logger.info(
                            f"LIFESPAN_HOOK: Initial superuser {settings.FIRST_SUPERUSER_EMAIL} (ID: {existing_user.id}) already exists."
                        )
                except UserNotExists:
                    logger.info(
                        f"LIFESPAN_HOOK: Initial superuser {settings.FIRST_SUPERUSER_EMAIL} not found, creating..."
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

    yield  # Application runs here

    # --- Shutdown logic ---
    logger.info(f"Shutting down {settings.APP_NAME}...")
    try:
        await lifespan_db_manager(_app_instance, "shutdown")
        logger.info("LIFESPAN_HOOK: Database resources disposed via lifespan_db_manager.")
    except Exception as e:
        logger.error(f"LIFESPAN_HOOK: Error during database resource disposal: {e}", exc_info=True)


# --- FastAPI App Initialization ---
# (Your existing app init logic for advertised_host, server_protocol, etc., looks fine)
advertised_host = "localhost" if settings.SERVER_HOST == "0.0.0.0" else settings.SERVER_HOST
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
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
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

# --- Rate Limiting Setup ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# --- Middleware ---
# (Your existing CORS middleware logic looks fine)
if settings.BACKEND_CORS_ORIGINS:
    origins = [
        str(origin).strip("/") for origin in settings.BACKEND_CORS_ORIGINS if str(origin).strip("/")
    ]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        logger.info(f"CORS enabled for origins: {origins}")
    else:
        logger.warning("BACKEND_CORS_ORIGINS configured but resulted in an empty list.")
else:
    logger.info("CORS disabled (BACKEND_CORS_ORIGINS not configured).")


# --- Exception Handlers ---
# (Your existing exception handlers look fine)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_details = exc.errors()
    log_body = None
    if settings.DEBUG and request.method in ["POST", "PUT", "PATCH"]:
        try:
            body_bytes = await request.body()
            log_body = body_bytes.decode()
        except Exception:
            log_body = "<Could not read or decode body>"
    logger.warning(
        f"Request validation error: {request.method} {request.url.path} - Errors: {error_details}",
        extra={"errors": error_details, "request_body": log_body},
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": error_details}
    )


@app.exception_handler(HTTPException)
async def http_exception_handler_custom(request: Request, exc: HTTPException):
    log_message = f"HTTPException: Status={exc.status_code}, Detail='{exc.detail}' for {request.method} {request.url.path}"
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error(log_message, exc_info=True)
    else:
        logger.warning(log_message)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def generic_exception_handler_custom(request: Request, exc: Exception):
    logger.error(
        f"Unhandled exception during request: {request.method} {request.url.path}", exc_info=exc
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
api_v1_router.include_router(users_router, prefix="/users", tags=["Users - User Management"])
api_v1_router.include_router(admin_router, prefix="/admin", tags=["Admins - Admin Management"])
api_v1_router.include_router(
    jobs_router, prefix="/jobs", tags=["Jobs - Subtitle Download Management"]
)

api_v1_router.include_router(
    dashboard_router, prefix="/dashboard", tags=["Dashboard - External Services"]
)
api_v1_router.include_router(storage_paths_router, prefix="/storage-paths", tags=["Storage Paths"])

# *** SETUP AND SETTINGS ROUTERS ***
# Setup is PUBLIC (no auth required) - used for initial configuration wizard
api_v1_router.include_router(setup_router)  # prefix is already "/setup" in router
# Settings requires admin auth - used for updating configuration after setup
api_v1_router.include_router(settings_router)  # prefix is already "/settings" in router
# Translation statistics - requires admin auth
api_v1_router.include_router(
    translation_stats_router
)  # prefix is already "/translation-stats" in router
# File download - requires admin auth
api_v1_router.include_router(files_router)  # prefix is already "/files" in router

# *** INCLUDE THE WEBSOCKET ROUTER HERE ***
# Note: WebSocket routers are typically included directly on the `app` instance
# or under a specific WebSocket prefix if you have many.
# For consistency with your /api/v1 pattern for HTTP, you could also create a
# separate WebSocket root router if you plan many different WebSocket types.
# For a single job log streamer, attaching it to api_v1_router is fine,
# or directly to `app` if you prefer a cleaner /ws root.

# Option 1: Attach to the existing api_v1_router (will be /api/v1/ws/jobs/... )
# This seems most consistent with your current structure.
# We define the WebSocket path *within* job_logs.py as "/jobs/{job_id}/logs"
# So if we prefix api_v1_router with /ws, the full path will be /api/v1/ws/jobs/{job_id}/logs
# Let's create a sub-router for WebSockets under api_v1_router for clarity
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
async def api_v1_root_endpoint():
    return {
        "message": f"Welcome to {settings.APP_NAME} - API Version 1",
        "version": settings.APP_VERSION,
        "documentation_url": app.docs_url,
    }


@api_v1_router.get("/test-db-users", tags=["Debug"])
async def test_db_users(db: AsyncSession = Depends(get_async_session)):
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


@api_v1_router.get(
    "/healthz",
    tags=["Health Checks"],
    summary="Detailed API and Dependencies Health Check",
    status_code=status.HTTP_200_OK,
)
async def health_check_api_v1_detailed(db: AsyncSession = Depends(get_async_session)):
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
async def health_check_basic_system():
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
