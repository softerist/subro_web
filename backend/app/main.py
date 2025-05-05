# backend/app/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status, Depends # Added Depends
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware # Added CORS
from fastapi.responses import JSONResponse
from celery import Celery # Kept Celery
from app.api.routers.admin import admin_router # Add this line

# --- Project Specific Imports ---
from app.core.config import settings # Import settings
from app.api.routers.auth import auth_router, users_router # This should now work

# from app.db.session import engine # Uncomment if used in lifespan/health
# from app.db.models import Base # Uncomment if used in lifespan

# Configure basic logging
logging.basicConfig(level=logging.INFO) # Or use settings.LOG_LEVEL later
logger = logging.getLogger(__name__)

# --- Celery App (Keep configuration here or move to dedicated module later) ---
# TODO: Consider moving Celery app setup to app/tasks/celery_app.py later
celery_app = Celery('tasks', broker='redis://redis:6379/0') # Use settings.CELERY_BROKER_URL later
celery_app.conf.update(
    result_backend='redis://redis:6379/0', # Use settings.CELERY_RESULT_BACKEND later
)

# --- Lifespan Management (for startup/shutdown events) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic: connect to DB, initialize resources, etc.
    logger.info(f"Starting up {settings.APP_NAME} v{settings.APP_VERSION}...")
    # Example: Create DB tables if they don't exist (handled by Alembic now)
    # You might add checks here to ensure DB/Redis are reachable at startup
    yield
    # Shutdown logic: close connections, cleanup resources
    logger.info("Application shutdown.")
    # Example: Dispose DB engine if needed
    # try:
    #     if engine:
    #         await engine.dispose()
    #         logger.info("Database connection pool disposed.")
    # except Exception as e:
    #     logger.error(f"Error during database connection disposal: {e}")

# --- FastAPI App Initialization ---
# IMPORTANT: Define the 'app' instance *before* using @app decorators
app = FastAPI(
    title=settings.APP_NAME, # Use settings
    version=settings.APP_VERSION, # Use settings
    description="API for managing subtitle download jobs and user authentication.", # Updated description
    lifespan=lifespan,
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# --- Middleware ---
# CORS (Cross-Origin Resource Sharing) - Integrated from Step 2.9
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).strip() for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(f"CORS enabled for origins: {settings.BACKEND_CORS_ORIGINS}")
else:
    logger.warning("CORS disabled (no BACKEND_CORS_ORIGINS configured)")


# --- Exception Handlers (Keep existing handlers) ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error for {request.method} {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation Error", "errors": exc.errors()},
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.info(f"HTTPException for {request.method} {request.url.path}: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception for request {request.method} {request.url.path}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected internal server error occurred."},
    )

# --- API Routers ---
# Include authentication and user management routers - Integrated from Step 2.9
app.include_router(auth_router, prefix="/api") # Mounts under /api/auth/*
app.include_router(users_router, prefix="/api") # Mounts under /api/users/*
app.include_router(admin_router, prefix="/api") # Mounts under /api/admin/*

# Add job router later: app.include_router(jobs_router, prefix="/api")

# --- Basic API Routes (Keep existing) ---

# Root endpoint for /api
@app.get("/api", tags=["Root"])
async def api_root():
    return {"message": f"Welcome to {settings.APP_NAME} API"}

# Detailed health check at /api/healthz
@app.get(
    "/api/healthz",
    tags=["Health"],
    summary="Detailed application health check",
    status_code=status.HTTP_200_OK
)
async def health_check_detailed():
    # TODO: Add actual checks for DB, Redis using dependencies
    db_ok = True
    redis_ok = True
    if db_ok and redis_ok:
        return {"status": "ok", "database": "connected", "redis": "connected"} # Placeholder
    else:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Dependency check failed") # Placeholder

# Minimal health check at /health (for Docker - keep hidden from schema)
@app.get(
    "/health",
    tags=["Health"],
    status_code=status.HTTP_200_OK,
    include_in_schema=False
)
async def health_check_docker():
    return {"status": "healthy"}


# --- Main execution block (Keep existing for local debugging) ---
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn directly for debugging...")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True, # Be careful with reload and lifespan functions
        log_level=logging.INFO
    )
