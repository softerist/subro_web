import logging

import nest_asyncio
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

from app.core.config import settings

# Import all models to ensure they are registered in the registry
from app.db import base  # noqa: F401

# Import the worker-specific db resource management functions
from app.db.session import dispose_worker_db_resources_sync, initialize_worker_db_resources

logger = logging.getLogger("app.tasks.celery_app")  # Or use celery.utils.log.get_task_logger

celery_app = Celery(
    "worker",
    broker=str(settings.CELERY_BROKER_URL),
    backend=str(settings.CELERY_RESULT_BACKEND),
    include=["app.tasks.subtitle_jobs", "app.tasks.audit_export", "app.tasks.audit_worker"],
)

# Robust configuration using pydantic settings object directly.
# Using namespace="CELERY" means it looks for attributes starting with CELERY_
celery_app.config_from_object(settings, namespace="CELERY")

# Optional: keep timezone as it might be named differently in settings (TIMEZONE vs CELERY_TIMEZONE)
celery_app.conf.timezone = settings.TIMEZONE

# Periodic tasks (Celery beat)
celery_app.conf.beat_schedule = {
    "audit_outbox_drain": {
        "task": "app.tasks.audit_worker_batch",
        "schedule": 15.0,
        "args": (100,),
    },
}

# Store celerybeat-schedule.db in /tmp to avoid polluting the mounted volume
celery_app.conf.beat_schedule_filename = "/tmp/celerybeat-schedule.db"


# --- Worker Process Lifecycle Signal Handlers ---


@worker_process_init.connect(weak=False)
def init_worker_process_signal(**_kwargs):
    """Signal handler for when a Celery worker process starts."""
    # Ensure all models are imported and registered

    logger.info("CELERY_WORKER_PROCESS_INIT: Applying nest_asyncio for event loop compatibility.")
    nest_asyncio.apply()
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

# For your current structure with `app/tasks/subtitle_jobs.py`, the `include` list is clear and effective.
