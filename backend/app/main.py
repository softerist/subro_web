import logging
from contextlib import asynccontextmanager

# --- Project Specific Imports ---
# Import settings early for Celery fallback
from app.core.config import settings  # MOVED UP

# Celery import - keep try/except if Celery setup is still evolving
try:
    from app.tasks.celery_app import celery_app
except ImportError:
    from celery import Celery  # Fallback import

    logger_celery_fallback = logging.getLogger(__name__ + ".celery_fallback")
    logger_celery_fallback.warning(
        "Celery app not found at app.tasks.celery_app. Using a basic placeholder. "
        "Ensure CELERY_BROKER_URL and CELERY_RESULT_BACKEND are set in .env if this fallback is used."
    )
    celery_app = Celery(
        "tasks_placeholder",
        broker=settings.CELERY_BROKER_URL,  # settings is now available
        result_backend=settings.CELERY_RESULT_BACKEND,  # settings is now available
    )
    celery_app.conf.update(task_track_started=True)


from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status  # Added APIRouter
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Import Routers
from app.api.routers.admin import admin_router
from app.api.routers.auth import auth_router
from app.api.routers.jobs import router as jobs_router
from app.api.routers.users import router as users_router
from app.db.session import async_engine, get_async_session

# Configure basic logging
logging.basicConfig(
    level=settings.LOG_LEVEL.upper(), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# --- Lifespan Management ---
@asynccontextmanager
async def lifespan(_app_instance: FastAPI):  # Prefixed app_instance with underscore
    logger.info(f"Starting up {settings.APP_NAME} v{settings.APP_VERSION}...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    yield
    logger.info(f"Shutting down {settings.APP_NAME}...")
    if async_engine:
        logger.info("Disposing database engine connection pool...")
        await async_engine.dispose()


# --- FastAPI App Initialization ---
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    lifespan=lifespan,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

# --- Middleware ---
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).strip("/") for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(f"CORS enabled for origins: {settings.BACKEND_CORS_ORIGINS}")
else:
    logger.info("CORS disabled (BACKEND_CORS_ORIGINS not configured or empty).")


# --- Exception Handlers ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        f"Request validation error: {request.method} {request.url.path} - Errors: {exc.errors()}",
        extra={"errors": exc.errors()},
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation Error", "errors": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler_custom(
    request: Request,
    exc: HTTPException,
):
    """Custom handler for HTTP exceptions.

    Args:
        request: The incoming request
        exc: The HTTP exception that was raised
    """
    # Force use of exc parameter
    status_code, detail, headers = exc.status_code, exc.detail, getattr(exc, "headers", None)

    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error(
            f"HTTPException (Server Error): {status_code} for {request.method} {request.url.path} - Detail: {detail}",
            exc_info=True,
        )
    elif status_code in [
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    ]:
        logger.warning(
            f"HTTPException (Client Error): {status_code} for {request.method} {request.url.path} - Detail: {detail}"
        )

    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers=headers,
    )


@app.exception_handler(Exception)
async def generic_exception_handler_custom(request: Request, _exc: Exception):
    logger.exception(f"Unhandled exception during request: {request.method} {request.url.path}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected internal server error occurred. Please try again later."},
    )


# --- API Routers ---
api_v1_router = APIRouter()

# Include your specific feature routers into this v1 group
# These routers (auth_router, etc.) should have their own prefixes (e.g., "/auth")
api_v1_router.include_router(auth_router)  # Assuming auth_router has prefix like "/auth"
api_v1_router.include_router(users_router)  # Assuming users_router has prefix like "/users"
api_v1_router.include_router(admin_router)  # Assuming admin_router has prefix like "/admin"
api_v1_router.include_router(jobs_router)  # Assuming jobs_router has prefix like "/jobs"


@api_v1_router.get("/", tags=["API Root"], summary="API v1 Root")
async def api_v1_root_endpoint():  # Renamed for clarity
    return {
        "message": f"Welcome to {settings.APP_NAME} - API Version 1",
        "version": settings.APP_VERSION,
    }


@api_v1_router.get(
    "/healthz",
    tags=["Health"],
    summary="Detailed API health check",  # Removed "(via APIRouter)" for cleaner summary
    status_code=status.HTTP_200_OK,
    description="Performs a detailed health check of the API and its critical dependencies (e.g., database).",
    # response_model=dict, # Consider defining a Pydantic model for this response
    include_in_schema=True,
)
async def health_check_api_v1_endpoint(db: AsyncSession = Depends(get_async_session)):  # Renamed
    db_ok = False
    redis_ok = True  # Placeholder, implement actual check if needed

    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
        logger.debug("Health check: Database connection successful.")
    except Exception as e:
        logger.error(f"Health check: Database connection failed. Error: {e}", exc_info=True)

    if db_ok and redis_ok:
        return {
            "status": "ok",
            "dependencies": {
                "database": "connected",
                "redis": "connected" if redis_ok else "check_failed_or_not_applicable",
            },
        }
    else:
        failed_deps = []
        if not db_ok:
            failed_deps.append("database")
        # Example for adding redis check to failed_deps if it was implemented and failed
        # if not redis_ok:
        #     failed_deps.append("redis")
        logger.error(f"API health check failed for dependencies: {', '.join(failed_deps)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unavailable. Failed dependencies: {', '.join(failed_deps)}.",
        ) from None  # B904: Explicitly chain or break chain


# Use include_router to add the v1 router group to the main app with the prefix
app.include_router(api_v1_router, prefix=settings.API_V1_STR)  # This is the correct way


# --- Basic Non-API Routes (e.g., Docker health check) ---
@app.get(
    "/health",
    tags=["System Health"],
    summary="Basic system health check",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def health_check_basic():
    return {"status": "healthy"}


# --- Main execution block (for local debugging with Uvicorn) ---
if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Uvicorn server directly for local debugging...")
    uvicorn.run(
        "app.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
