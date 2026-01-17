#!/usr/bin/env python3
"""
Celery healthcheck script with comprehensive broker and worker validation.

This script verifies:
1. Broker connectivity with timeout and retries
2. Worker availability and responsiveness
3. Proper connection cleanup

Exit codes:
    0: Healthcheck passed
    1: Healthcheck failed
    2: Healthcheck timed out
"""

import logging
import os
import signal
import sys

from app.tasks.celery_app import celery_app

# Configuration from environment variables
MAX_RETRIES = int(os.getenv("CELERY_HEALTHCHECK_RETRIES", "3"))
RETRY_INTERVAL_START = float(os.getenv("CELERY_HEALTHCHECK_INTERVAL_START", "0.5"))
RETRY_INTERVAL_STEP = float(os.getenv("CELERY_HEALTHCHECK_INTERVAL_STEP", "0.5"))
HEALTHCHECK_TIMEOUT = int(os.getenv("CELERY_HEALTHCHECK_TIMEOUT", "10"))
CHECK_WORKERS = os.getenv("CELERY_HEALTHCHECK_CHECK_WORKERS", "true").lower() == "true"
WORKER_TIMEOUT = int(os.getenv("CELERY_HEALTHCHECK_WORKER_TIMEOUT", "3"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


class HealthcheckTimeout(Exception):
    """Raised when healthcheck exceeds timeout."""

    pass


def timeout_handler(_signum, _frame):
    """Handle timeout signal."""
    raise HealthcheckTimeout(f"Healthcheck exceeded {HEALTHCHECK_TIMEOUT} second timeout")


def check_broker_connection() -> None:
    """
    Verify broker connectivity with retries and heartbeat.

    Raises:
        Exception: If broker connection fails or is unhealthy.
    """
    try:
        logger.info("Testing broker connection...")
        with celery_app.connection_or_acquire() as conn:
            # Attempt connection with retries
            conn.ensure_connection(
                max_retries=MAX_RETRIES,
                interval_start=RETRY_INTERVAL_START,
                interval_step=RETRY_INTERVAL_STEP,
            )

            # Verify connection is actually alive
            conn.heartbeat_check()

        logger.info("✓ Broker connection successful")

    except Exception as e:
        logger.error(f"✗ Broker connection failed: {type(e).__name__}: {e}")
        raise
    finally:
        # Alarm cancellation is handled in the caller
        pass


def check_workers() -> None:
    """
    Verify that Celery workers are available and responding.

    Raises:
        RuntimeError: If no workers are found or workers don't respond.
    """
    try:
        logger.info("Checking for active workers...")
        inspector = celery_app.control.inspect(timeout=WORKER_TIMEOUT)

        # Get worker stats
        stats = inspector.stats()

        if not stats:
            raise RuntimeError("No active Celery workers found")

        worker_count = len(stats)
        worker_names = ", ".join(stats.keys())
        logger.info(f"✓ Found {worker_count} active worker(s): {worker_names}")

    except Exception as e:
        logger.error(f"✗ Worker check failed: {type(e).__name__}: {e}")
        raise


def healthcheck() -> int:
    """
    Perform comprehensive Celery healthcheck.

    Returns:
        int: Exit code (0 for success, 1 for failure, 2 for timeout)
    """
    # Set up timeout handler
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(HEALTHCHECK_TIMEOUT)

    try:
        logger.info("=" * 60)
        logger.info("Starting Celery healthcheck")
        logger.info("=" * 60)

        # Check broker connection
        check_broker_connection()

        # Optionally check workers
        if CHECK_WORKERS:
            check_workers()
        else:
            logger.info("Worker check disabled (CELERY_HEALTHCHECK_CHECK_WORKERS=false)")

        # Success
        logger.info("=" * 60)
        logger.info("✓ Healthcheck PASSED")
        logger.info("=" * 60)
        print("OK", file=sys.stdout)  # Simple output for scripts/monitoring
        return 0

    except HealthcheckTimeout as e:
        logger.error("=" * 60)
        logger.error(f"✗ Healthcheck TIMEOUT: {e}")
        logger.error("=" * 60)
        print("TIMEOUT", file=sys.stdout)
        return 2

    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"✗ Healthcheck FAILED: {type(e).__name__}: {e}")
        logger.error("=" * 60)
        print("FAILED", file=sys.stdout)
        return 1

    finally:
        # Cancel alarm
        signal.alarm(0)


if __name__ == "__main__":
    exit_code = healthcheck()
    sys.exit(exit_code)
