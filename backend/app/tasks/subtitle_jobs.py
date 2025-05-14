import logging
import time

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


# CHANGE THE NAME HERE to the full path
@celery_app.task(name="app.tasks.subtitle_jobs.run_subtitle_downloader_mock")
def run_subtitle_downloader_mock(
    job_id: str, folder_path: str, language: str | None = None
) -> dict:
    task_log_prefix = f"[CeleryTask:{run_subtitle_downloader_mock.name} ID:{job_id} CeleryID:{run_subtitle_downloader_mock.request.id}]"
    logger.info(
        f"{task_log_prefix} Starting mock subtitle download for '{folder_path}' (Lang: {language})"
    )
    time.sleep(10)  # Simulate work
    result_message = f"Mock download complete for '{folder_path}'"
    logger.info(f"{task_log_prefix} {result_message}")
    return {
        "job_id": job_id,
        "folder_path": folder_path,
        "language": language,
        "status": "SUCCEEDED_MOCK",  # Maybe change to avoid confusion with real "SUCCEEDED"
        "message": result_message,
        "celery_task_id": run_subtitle_downloader_mock.request.id,
    }
