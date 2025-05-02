from celery import Celery

# Create the Celery app instance
celery_app = Celery('app')

# Configure Celery
celery_app.conf.update(
    broker_url='redis://redis:6379/0',  # Adjust this to match your redis service name
    result_backend='redis://redis:6379/0',
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    worker_concurrency=1,
)

# Auto-discover tasks in other modules
celery_app.autodiscover_tasks(['app.tasks'])

# Optional: Add a simple test task
@celery_app.task(name='test_task')
def test_task():
    return "Celery is working!"

if __name__ == '__main__':
    celery_app.start()