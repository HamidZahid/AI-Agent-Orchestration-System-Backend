"""Background task utilities and scheduled cleanup tasks."""

import asyncio
from datetime import datetime, timedelta
from typing import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.database import AsyncSessionLocal
from src.backend.models import ProcessingRequest, WebhookLog
from src.backend.models import RequestStatus, WebhookStatus
from src.backend.services.processing_service import ProcessingService
from src.backend.services.webhook_service import WebhookService
from src.backend.utils.logger import get_logger

logger = get_logger(__name__)


async def process_text_async(request_id: UUID) -> None:
    """
    Background task to process text asynchronously.

    Args:
        request_id: Processing request ID
    """
    logger.info(
        f"Starting background processing for request {request_id}",
        extra={"request_id": request_id},
    )
    from src.backend.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            service = ProcessingService(db)
            await service.process_request_background(request_id)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(
                f"Background processing failed for request {request_id}: {str(e)}",
                exc_info=True,
                extra={"request_id": request_id},
            )
            raise


async def send_webhook_async(request_id: UUID) -> None:
    """
    Background task to send webhook asynchronously.

    Args:
        request_id: Processing request ID
    """
    logger.info(
        f"Starting background webhook delivery for request {request_id}",
        extra={"request_id": request_id},
    )
    from src.backend.database import AsyncSessionLocal
    from src.backend.models import AggregatedResult

    async with AsyncSessionLocal() as db:
        try:
            service = WebhookService(db)
            # Get the aggregated result to send
            result = await db.scalar(
                select(AggregatedResult).where(
                    AggregatedResult.request_id == request_id
                )
            )
            if result:
                result_data = {
                    "request_id": str(result.request_id),
                    "summary": result.summary,
                    "sentiment": result.sentiment,
                    "entities": result.entities,
                    "total_execution_time": result.total_execution_time,
                }
                await service.send_webhook(request_id, result_data)
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(
                f"Background webhook delivery failed for request {request_id}: {str(e)}",
                exc_info=True,
                extra={"request_id": request_id},
            )
            raise


async def cleanup_old_logs(days_to_keep: int = 30) -> None:
    """
    Clean up webhook logs older than specified days.

    This task should run daily to maintain database size.

    Args:
        days_to_keep: Number of days to keep logs (default: 30)
    """
    logger.info(f"Starting cleanup of logs older than {days_to_keep} days")
    cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(WebhookLog).where(WebhookLog.created_at < cutoff_date)
            )
            old_logs = result.scalars().all()
            count = 0
            for log in old_logs:
                await db.delete(log)
                count += 1
            await db.commit()
            logger.info(f"Cleaned up {count} old webhook logs")
        except Exception as e:
            await db.rollback()
            logger.error(
                f"Log cleanup failed: {str(e)}",
                exc_info=True,
            )
            raise


async def retry_failed_webhooks() -> None:
    """
    Background task to retry failed webhooks.

    Finds webhooks with attempts < 3 and retries sending them.
    Should run every 5 minutes.
    """
    logger.info("Starting retry of failed webhooks")
    async with AsyncSessionLocal() as db:
        try:
            # Find requests with failed webhooks that have less than max retries
            from src.backend.config import settings

            result = await db.execute(
                select(ProcessingRequest).where(
                    ProcessingRequest.webhook_url.isnot(None),
                    ProcessingRequest.webhook_status == WebhookStatus.FAILED,
                    ProcessingRequest.webhook_attempts < settings.WEBHOOK_MAX_RETRIES,
                    ProcessingRequest.status == RequestStatus.COMPLETED,
                )
            )
            failed_requests = result.scalars().all()

            service = WebhookService(db)
            retried_count = 0

            for request in failed_requests:
                try:
                    # Get aggregated result
                    from src.backend.models import AggregatedResult

                    agg_result = await db.scalar(
                        select(AggregatedResult).where(
                            AggregatedResult.request_id == request.id
                        )
                    )
                    if agg_result:
                        result_data = {
                            "request_id": str(agg_result.request_id),
                            "summary": agg_result.summary,
                            "sentiment": agg_result.sentiment,
                            "entities": agg_result.entities,
                            "total_execution_time": agg_result.total_execution_time,
                        }
                        await service.send_webhook(request.id, result_data)
                        retried_count += 1
                except Exception as e:
                    logger.error(
                        f"Failed to retry webhook for request {request.id}: {str(e)}",
                        extra={"request_id": request.id},
                    )

            logger.info(f"Retried {retried_count} failed webhooks")
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(
                f"Failed webhook retry task failed: {str(e)}",
                exc_info=True,
            )
            raise


def schedule_periodic_task(
    task: Callable,
    interval_seconds: int,
    task_name: str,
) -> None:
    """
    Schedule a periodic background task.

    Args:
        task: Async function to run periodically
        interval_seconds: Interval between task executions
        task_name: Name of the task for logging
    """
    async def run_periodic():
        while True:
            try:
                await task()
            except Exception as e:
                logger.error(
                    f"Periodic task '{task_name}' failed: {str(e)}",
                    exc_info=True,
                )
            await asyncio.sleep(interval_seconds)

    # Start task in background
    asyncio.create_task(run_periodic())
    logger.info(f"Scheduled periodic task '{task_name}' with interval {interval_seconds}s")

