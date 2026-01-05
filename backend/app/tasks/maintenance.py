# backend/app/tasks/maintenance.py
"""
Maintenance tasks for database hygiene and performance.
"""

import logging
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.schema import DDL

from app.db.session import WorkerSessionLocal, initialize_worker_db_resources
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.maintenance.manage_audit_partitions")
def manage_audit_partitions_task():
    """
    Periodic task to ensure audit log partitions exist for the next 4 months.
    Run this as an async wrapper for the actual logic.
    """
    import asyncio

    return asyncio.run(manage_audit_partitions())


async def manage_audit_partitions():
    """
    Logic to check and create monthly partitions for 'audit_logs'.
    Ensures partitions exist for the current month and the next 3 months.
    """
    logger.info("Maintenance: Running audit log partition management.")

    # We want to ensure partitions for now, now+1, now+2, now+3 months
    today = date.today()
    target_months = [today + relativedelta(months=i) for i in range(4)]

    # Ensure worker resources are initialized
    initialize_worker_db_resources()
    if WorkerSessionLocal is None:
        raise RuntimeError("WorkerSessionLocal not initialized")

    async with WorkerSessionLocal() as db:
        for m_start in target_months:
            m_end = m_start + relativedelta(months=1)

            # Canonical name: audit_logs_YYYY_MM
            table_name = f"audit_logs_{m_start.strftime('%Y_%m')}"
            start_str = m_start.strftime("%Y-%m-01")
            end_str = m_end.strftime("%Y-%m-01")

            # Check if partition exists
            check_query = select(func.to_regclass(f"public.{table_name}"))
            result = await db.execute(check_query)
            if result.scalar() is None:
                logger.warning(f"Partition {table_name} missing. Creating...")
                create_query = DDL(
                    f"CREATE TABLE IF NOT EXISTS {table_name} "
                    f"PARTITION OF audit_logs "
                    f"FOR VALUES FROM ('{start_str}') TO ('{end_str}')"
                )
                try:
                    await db.execute(create_query)
                    await db.commit()
                    logger.info(f"Successfully created partition: {table_name}")
                except Exception as e:
                    logger.error(f"Failed to create partition {table_name}: {e}")
                    await db.rollback()
            else:
                logger.debug(f"Partition {table_name} already exists.")

    return "Audit partition management complete."
