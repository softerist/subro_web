from celery import Celery

from app.core.config import settings

# Initialize Celery
# The first argument "worker" can be any name, often the project name or "tasks".
# It's used for naming purposes and sometimes for auto-discovery.
celery_app = Celery(
    "worker",  # Using "worker" as a descriptive name for the task execution process
    broker=str(settings.CELERY_BROKER_URL),
    backend=str(settings.CELERY_RESULT_BACKEND),
    # Explicitly list modules to import when the worker starts.
    # This ensures tasks defined in these modules are registered.
    include=["app.tasks.subtitle_jobs"],
)

# Celery Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],  # Only accept json serialized tasks
    result_serializer="json",
    timezone="UTC",  # Standardize on UTC
    enable_utc=True,
    # broker_connection_retry_on_startup=True, # Good for Celery 5+ ensuring worker retries connection on startup
    task_track_started=True,  # To report 'STARTED' state for tasks
    # worker_concurrency=1, # You can set this, but often better to configure via CLI for flexibility
    # Or leave it to Celery's default (number of CPU cores)
)


# A simple health check task for initial testing
@celery_app.task(name="health_check_celery")
def health_check_celery() -> str:
    return "Celery is healthy!"


if __name__ == "__main__":
    # This allows running the worker directly using: python -m app.tasks.celery_app worker -l info
    celery_app.worker_main()

# If you prefer autodiscover_tasks over explicit `include`:
# Ensure your tasks are in modules like `app/tasks/sometasks_module/tasks.py`
# or `app/tasks/tasks.py` if you want to use:
# celery_app.autodiscover_tasks(["app.tasks"])
# For `app/tasks/subtitle_jobs.py`, `include` is often more straightforward.
