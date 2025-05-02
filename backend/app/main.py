# backend/app/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse # Removed PlainTextResponse as it wasn't used
from celery import Celery # Uncomment if using Celery for background tasks
# Example imports - uncomment and implement later as needed
# from app.api.routers import auth, jobs, users
# from app.core.config import settings
# from app.db.session import engine
# from app.db.models import Base

# Configure basic logging
logging.basicConfig(level=logging.INFO) # Or use settings.LOG_LEVEL later
logger = logging.getLogger(__name__)
celery_app = Celery('tasks', broker='redis://redis:6379/0')

celery_app.conf.update(
    result_backend='redis://redis:6379/0',
)



# --- Lifespan Management (for startup/shutdown events) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic: connect to DB, initialize resources, etc.
    logger.info("Application startup...")
    # Example: Create DB tables if they don't exist (useful for initial setup)
    # try:
    #     async with engine.begin() as conn:
    #         await conn.run_sync(Base.metadata.create_all)
    #     logger.info("Database tables checked/created.")
    # except Exception as e:
    #     logger.error(f"Database connection/setup failed during startup: {e}")
    #     # Depending on severity, you might want to raise the exception
    #     # to prevent the app from starting fully in a broken state.
    yield
    # Shutdown logic: close connections, cleanup resources
    logger.info("Application shutdown.")
    # try:
    #     if engine: # Check if engine was initialized
    #         await engine.dispose()
    #         logger.info("Database connection pool disposed.")
    # except Exception as e:
    #     logger.error(f"Error during database connection disposal: {e}")


# --- FastAPI App Initialization ---
# IMPORTANT: Define the 'app' instance *before* using @app decorators
app = FastAPI(
    title="Subtitle Downloader API",
    description="API for managing subtitle download jobs.",
    version="0.1.0", # Consider reading from pyproject.toml or config
    lifespan=lifespan,
    # Define API docs URLs relative to root or under /api/ prefix
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)


# --- Health Check Endpoint (for Docker) ---
# This path MUST match the one used in the docker-compose.yml healthcheck
@app.get(
    "/health",
    tags=["Health"],
    summary="Docker health check endpoint",
    status_code=status.HTTP_200_OK,
    include_in_schema=False # Usually hide this simple check from public API docs
)
async def health_check_docker():
    """
    Minimal health check endpoint used by Docker to verify the service is running.
    Returns a static response.
    """
    return {"status": "healthy"}


# --- Exception Handlers ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Custom handler for Pydantic validation errors
    # Log the error details for debugging
    logger.warning(f"Validation error for {request.method} {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        # Provide a user-friendly structure
        content={"detail": "Validation Error", "errors": exc.errors()},
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Custom handler for FastAPI's HTTPExceptions
    # Log the exception details
    logger.info(f"HTTPException for {request.method} {request.url.path}: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    # Generic handler for unexpected server errors
    # Log the full traceback for unexpected errors
    logger.exception(f"Unhandled exception for request {request.method} {request.url.path}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected internal server error occurred."},
    )


# --- Middleware ---
# Example: Add CORS middleware if needed (Caddy can also handle this)
# Make sure to install 'python-multipart' if allowing file uploads in forms
# from fastapi.middleware.cors import CORSMiddleware
# origins = [
#     "http://localhost:5173", # Allow Vite dev server
#     "https://localhost",    # Allow access via Caddy proxy
#     # Add your production frontend URL here later
# ]
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=origins,
#     allow_credentials=True,
#     allow_methods=["*"], # Or restrict to specific methods (GET, POST, etc.)
#     allow_headers=["*"], # Or restrict to specific headers
# )


# --- Basic API Routes ---
@app.get(
    "/api/healthz",
    tags=["Health"],
    summary="Detailed application health check",
    status_code=status.HTTP_200_OK
)
async def health_check_detailed():
    """
    Provides a more detailed health status, potentially checking connections
    to the database, Redis, or other downstream services.
    """
    # Example checks (implement robustly later)
    db_ok = True
    redis_ok = True
    # try:
    #     # Check DB connection (e.g., execute a simple query)
    #     async with engine.connect() as conn:
    #         await conn.execute(text("SELECT 1"))
    # except Exception as e:
    #     logger.error(f"Detailed health check: DB connection failed: {e}")
    #     db_ok = False
    #
    # try:
    #     # Check Redis connection (e.g., PING)
    #     # Assuming you have a redis client instance 'redis_client'
    #     await redis_client.ping()
    # except Exception as e:
    #     logger.error(f"Detailed health check: Redis connection failed: {e}")
    #     redis_ok = False

    if db_ok and redis_ok:
        return {"status": "ok", "database": "connected", "redis": "connected"}
    else:
        # Return 503 Service Unavailable if dependencies are down
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "error",
                "database": "connected" if db_ok else "disconnected",
                "redis": "connected" if redis_ok else "disconnected",
            }
        )


@app.get("/api", include_in_schema=False)
async def api_root():
    # Simple root endpoint for the /api path
    return {"message": "Welcome to the Subtitle Downloader API!"}


# --- Include Routers (Uncomment and implement as needed) ---
# Make sure the router files exist and define 'router = APIRouter(...)'
# from app.api.v1.endpoints import auth, users, jobs # Example structure
# app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
# app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
# app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["Jobs"])


# --- Main execution block (for direct running, e.g., python -m app.main) ---
if __name__ == "__main__":
    # This block is useful for simple local testing without docker/uvicorn CLI
    # For Docker/production, uvicorn is typically started via the command line (like in docker-compose)
    import uvicorn
    logger.info("Starting Uvicorn directly for debugging...")
    uvicorn.run(
        "app.main:app", # Point to the app instance
        host="0.0.0.0", # Listen on all interfaces
        port=8000,      # Standard port
        reload=True,    # Enable auto-reload for code changes (dev only)
        log_level=logging.INFO # Match logger config or use 'debug'
    )
