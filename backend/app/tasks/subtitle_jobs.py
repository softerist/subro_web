import logging
import time

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="run_subtitle_downloader_mock")
def run_subtitle_downloader_mock(
    job_id: str, folder_path: str, language: str | None = None
) -> dict:
    logger.info(
        f"Job {job_id}: Starting mock subtitle download for '{folder_path}' (Lang: {language})"
    )
    time.sleep(10)  # Simulate work
    result_message = f"Job {job_id}: Mock download complete for '{folder_path}'"
    logger.info(result_message)
    return {
        "job_id": job_id,
        "folder_path": folder_path,
        "language": language,
        "status": "SUCCEEDED",
        "message": result_message,
    }
