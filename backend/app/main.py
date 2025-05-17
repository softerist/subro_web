# backend/app/main.py
import logging
from contextlib import asynccontextmanager

# --- Project Specific Imports ---
from app.core.config import settings

# Celery import
try:
    from app.tasks.celery_app import celery_app  # type: ignore
except ImportError:
    from celery import Celery

    logger_celery_fallback = logging.getLogger(__name__ + ".celery_fallback")
    logger_celery_fallback.warning(
        "Celery app not found at app.tasks.celery_app. Using a basic placeholder. "
        "Ensure CELERY_BROKER_URL and CELERY_RESULT_BACKEND are set in .env if this fallback is used."
    )
    celery_app = Celery(
        "tasks_placeholder",
        broker=settings.CELERY_BROKER_URL,
        result_backend=settings.CELERY_RESULT_BACKEND,
    )
    celery_app.conf.update(
        task_track_started=True,
    )

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_users.exceptions import UserNotExists
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Import Routers - these are the actual router objects from your files
from app.api.routers.admin import admin_router
from app.api.routers.auth import auth_router as custom_auth_router
from app.api.routers.jobs import router as jobs_router
from app.api.routers.users import router as users_router

# --- Add these imports for initial superuser creation ---
from app.core.users import UserManager
from app.db.models.user import User as UserModel
from app.db.session import (  # get_async_session is used later
    AsyncSessionLocal,
    async_engine,
    get_async_session,
)
from app.schemas.user import UserCreate

# Configure basic logging
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

    if settings.FIRST_SUPERUSER_EMAIL and settings.FIRST_SUPERUSER_PASSWORD:
        logger.info(
            f"Attempting to create/ensure initial superuser: {settings.FIRST_SUPERUSER_EMAIL}"
        )
        async with AsyncSessionLocal() as session:
            try:
                user_db_adapter = SQLAlchemyUserDatabase(session, UserModel)
                user_manager = UserManager(user_db_adapter)
                try:
                    existing_user = await user_manager.get_by_email(settings.FIRST_SUPERUSER_EMAIL)
                    if existing_user:
                        logger.info(
                            f"Initial superuser {settings.FIRST_SUPERUSER_EMAIL} (ID: {existing_user.id}) already exists."
                        )
                except UserNotExists:
                    logger.info(
                        f"Initial superuser {settings.FIRST_SUPERUSER_EMAIL} not found, creating..."
                    )
                    user_create_data = UserCreate(
                        email=settings.FIRST_SUPERUSER_EMAIL,
                        password=settings.FIRST_SUPERUSER_PASSWORD,
                        is_superuser=True,
                        is_active=True,
                        is_verified=True,
                        role="admin",
                    )
                    created_user = await user_manager.create(user_create_data, safe=True)
                    await session.commit()
                    logger.info(
                        f"Initial superuser {settings.FIRST_SUPERUSER_EMAIL} (ID: {created_user.id}) created successfully."
                    )
            except Exception as e:
                await session.rollback()
                logger.error(
                    f"Error during initial superuser creation in lifespan: {e}", exc_info=True
                )
    else:
        logger.warning(
            "FIRST_SUPERUSER_EMAIL or FIRST_SUPERUSER_PASSWORD not set. Skipping superuser creation in lifespan."
        )

    yield

    logger.info(f"Shutting down {settings.APP_NAME}...")
    if async_engine:
        logger.info("Disposing database engine connection pool...")
        await async_engine.dispose()


# --- FastAPI App Initialization ---
advertised_host = "localhost" if settings.SERVER_HOST == "0.0.0.0" else settings.SERVER_HOST
server_protocol = "https" if settings.USE_HTTPS else "http"
advertised_server_url_base = f"{server_protocol}://{advertised_host}:{settings.SERVER_PORT}"

if hasattr(settings, "ROOT_PATH") and settings.ROOT_PATH and settings.ROOT_PATH != "/":
    effective_root_path = "/" + settings.ROOT_PATH.strip("/")
    openapi_server_url = f"{advertised_server_url_base}{effective_root_path}"
else:
    openapi_server_url = advertised_server_url_base

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    lifespan=lifespan,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    servers=[{"url": openapi_server_url, "description": "Current environment server"}],
    # --- ADD THIS SECTION TO CUSTOMIZE OPENAPI SECURITY SCHEMES ---
    openapi_components={
        "securitySchemes": {
            # This name MUST match the name fastapi-users (or your manual setup)
            # is using for the OAuth2 Password flow in the generated openapi.json.
            # Common default is "OAuth2PasswordBearer".
            "OAuth2PasswordBearer": {
                "type": "oauth2",
                "flows": {
                    "password": {
                        # Point to YOUR custom login endpoint
                        "tokenUrl": f"{settings.API_V1_STR}/auth/login",
                        "scopes": {},  # Add scopes here if your app uses them, e.g., {"read:items": "Read items."}
                    }
                },
            }
            # If you have other schemes (e.g., for a cookie-based auth also shown in Swagger),
            # you might need to define or adjust them here too.
            # For example, if fastapi-users also defines a scheme for its cookie auth that
            # you want to keep, you'd copy its existing definition from openapi.json here
            # and just modify the OAuth2PasswordBearer one.
        }
    },
    # --- END OF ADDED SECTION ---
)

# --- Middleware ---
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
        logger.info(
            f"CORS enabled for origins: {origins} (Note: If this list contains '*', it means all origins are allowed)"
        )
    else:
        logger.warning(
            "BACKEND_CORS_ORIGINS was configured but resulted in an empty list after processing. CORS might not work as expected."
        )
else:
    logger.info("CORS disabled (BACKEND_CORS_ORIGINS not configured or empty).")


# --- Exception Handlers ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_details = exc.errors()
    log_body = (
        await request.body()
        if settings.DEBUG and request.method in ["POST", "PUT", "PATCH"]
        else None
    )
    logger.warning(
        f"Request validation error: {request.method} {request.url.path} - Errors: {error_details}",
        extra={"errors": error_details, "request_body": log_body.decode() if log_body else None},
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": error_details},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler_custom(request: Request, exc: HTTPException):
    log_message = (
        f"HTTPException: Status={exc.status_code}, Detail='{exc.detail}' "
        f"for {request.method} {request.url.path}"
    )
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
async def generic_exception_handler_custom(request: Request, _exc: Exception):
    logger.error(
        f"Unhandled exception during request: {request.method} {request.url.path}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected internal server error occurred. Please try again later."},
    )


# --- API v1 Router Definition and Inclusions ---
api_v1_router = APIRouter()

# Include all specific routers into the api_v1_router
api_v1_router.include_router(
    custom_auth_router,  # This is the 'auth_router as custom_auth_router' from app.api.routers.auth
    prefix="/auth",
    tags=["Auth - Authentication & Authorization"],
)
api_v1_router.include_router(
    users_router,  # This is the 'router as users_router' from app.api.routers.users
    prefix="/users",
    tags=["Users - User Management"],
)
api_v1_router.include_router(
    admin_router,  # This is 'admin_router' from app.api.routers.admin
    prefix="/admin",
    tags=["Admins - Admin Management"],
)
api_v1_router.include_router(
    jobs_router,  # This is the 'router as jobs_router' from app.api.routers.jobs
    prefix="/jobs",
    tags=["Jobs - Subtitle Download Management"],
)


# Add root and healthz for the /api/v1 path itself
@api_v1_router.get("/", tags=["API Root"], summary="API v1 Root Endpoint")
async def api_v1_root_endpoint():
    return {
        "message": f"Welcome to {settings.APP_NAME} - API Version 1",
        "version": settings.APP_VERSION,
        "documentation_url": app.docs_url,  # This will be /api/v1/docs
    }


@api_v1_router.get("/test-db-users", tags=["Debug"])  # This will be /api/v1/test-db-users
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
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"DB Test Error: {e!s}") from e


@api_v1_router.get(
    "/healthz",  # This will be /api/v1/healthz
    tags=["Health Checks"],
    summary="Detailed API and Dependencies Health Check",
    status_code=status.HTTP_200_OK,
    description="Performs a detailed health check of the API and its critical dependencies (e.g., database).",
)
async def health_check_api_v1_detailed(db: AsyncSession = Depends(get_async_session)):
    db_status = "unavailable"
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
        logger.debug("Health check (detailed): Database connection successful.")
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


# Mount the consolidated api_v1_router to the main app
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


# --- Health Check Endpoint (at app root) ---
@app.get(
    "/health",  # This will be /health
    tags=["System Health"],
    summary="Basic System Liveness Check",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,  # Typically not part of the versioned API docs
)
async def health_check_basic_system():
    return {"status": "healthy"}


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
