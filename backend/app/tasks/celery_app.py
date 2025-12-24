# backend/app/tasks/celery_app.py
import logging

import nest_asyncio
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

from app.core.config import settings

# Import the worker-specific db resource management functions
from app.db.session import dispose_worker_db_resources_sync, initialize_worker_db_resources

# It's good practice to use Celery's logger or a specific module logger
logger = logging.getLogger("app.tasks.celery_app")  # Or use celery.utils.log.get_task_logger

# Initialize Celery
# The first argument "worker" can be any name, often the project name or "tasks".
# It's used for naming purposes and sometimes for auto-discovery.
celery_app = Celery(
    "worker",  # Using "worker" as a descriptive name for the task execution process
    broker=str(settings.CELERY_BROKER_URL),
    backend=str(settings.CELERY_RESULT_BACKEND),
    # Explicitly list modules to import when the worker starts.
    # This ensures tasks defined in these modules are registered.
    # Add any other task modules you create here.
    include=[
        "app.tasks.subtitle_jobs"
    ],  # "app.tasks.test_tasks"], # Assuming test_tasks might exist or for future use
)

# Celery Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],  # Only accept json serialized tasks
    result_serializer="json",
    timezone=settings.TIMEZONE,  # Use TIMEZONE from your settings if defined, else "UTC"
    enable_utc=True,  # Ensure Celery uses UTC internally if timezone is set
    broker_connection_retry_on_startup=True,  # Good for Celery 5+ ensuring worker retries connection on startup
    task_track_started=True,  # To report 'STARTED' state for tasks
    # worker_concurrency=1, # You can set this, but often better to configure via CLI for flexibility
    # Or leave it to Celery's default (number of CPU cores)
    task_acks_late=settings.CELERY_ACKS_LATE,  # If you have this in settings
    result_expires=settings.CELERY_RESULT_EXPIRES,  # If you have this in settings
)

# Add these to your app.core.config.py if they don't exist, e.g.:
# TIMEZONE: str = "UTC"
# CELERY_ACKS_LATE: bool = True # Example
# CELERY_RESULT_EXPIRES: int = 3600 # 1 hour in seconds, example

# --- Worker Process Lifecycle Signal Handlers ---


@worker_process_init.connect(weak=False)
def init_worker_process_signal(**_kwargs):
    """Signal handler for when a Celery worker process starts."""
    logger.info("CELERY_WORKER_PROCESS_INIT: Applying nest_asyncio for event loop compatibility.")
    nest_asyncio.apply()  # <--- APPLIED NEST_ASYNCIO
    logger.info("CELERY_WORKER_PROCESS_INIT: nest_asyncio applied. Initializing DB resources.")
    initialize_worker_db_resources()
    logger.info("CELERY_WORKER_PROCESS_INIT: DB resources initialization complete.")


@worker_process_shutdown.connect(weak=False)
def shutdown_worker_process_signal(**_kwargs):
    """Signal handler for when a Celery worker process shuts down."""
    logger.info("CELERY_WORKER_PROCESS_SHUTDOWN: Signal received. Disposing DB resources.")
    dispose_worker_db_resources_sync()  # Call the synchronous wrapper
    logger.info("CELERY_WORKER_PROCESS_SHUTDOWN: DB resources disposal complete.")


# --- Tasks ---


# A simple health check task (can be moved to app.tasks.test_tasks if you prefer)
@celery_app.task(
    name="app.tasks.health_check_celery"
)  # Renamed to avoid conflict if defined elsewhere
def health_check_celery_task() -> str:  # Task names usually end with _task
    logger.info("Celery health check task executed.")
    return "Celery worker is healthy, DB signals should be active, and nest_asyncio is applied!"


# This section is typically for running the worker directly, not usually needed when using Docker.
# Docker will use `celery -A app.tasks.celery_app worker ...`
# if __name__ == "__main__":
#     # This allows running the worker directly using: python -m app.tasks.celery_app worker -l info
#     # However, it's better to use the Celery CLI command for starting workers.
#     celery_app.worker_main()

# Autodiscovery:
# If you prefer autodiscover_tasks over explicit `include`:
# Ensure your tasks are in modules like `app/your_feature/tasks.py`
# Then you can use:
# celery_app.autodiscover_tasks(lambda: settings.INSTALLED_APPS) # Django style
# Or for FastAPI, list the base packages where tasks might be:
# celery_app.autodiscover_tasks(['app.tasks', 'app.another_module_with_tasks'])
# For your current structure with `app/tasks/subtitle_jobs.py`, the `include` list is clear and effective.
