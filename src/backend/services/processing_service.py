"""Background processing service for orchestrating agents and storing results."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.agents.orchestrator import AgentOrchestrator
from src.backend.models import (
    AggregatedResult,
    AgentResult,
    AgentStatus,
    ProcessingRequest,
    RequestStatus,
)
from src.backend.services.webhook_service import WebhookService
from src.backend.utils.exceptions import OrchestrationError
from src.backend.utils.logger import get_logger

logger = get_logger(__name__)


class ProcessingService:
    """Service for processing text requests with agent orchestration."""

    def __init__(self, db: AsyncSession):
        """
        Initialize processing service.

        Args:
            db: Database session
        """
        self.db = db

    async def process_request_background(self, request_id: UUID) -> None:
        """
        Process a text request in the background.

        This method:
        1. Updates request status to "processing"
        2. Executes agents via orchestrator
        3. Stores agent results in database
        4. Creates aggregated result
        5. Updates status to "completed" or "failed"
        6. Triggers webhook if configured

        Args:
            request_id: Processing request ID
        """
        logger.info(
            f"Starting background processing for request {request_id}",
            extra={"request_id": request_id},
        )

        # Get processing request
        request = await self.db.get(ProcessingRequest, request_id)
        if not request:
            logger.error(f"Processing request {request_id} not found")
            return

        try:
            # Update status to processing
            request.status = RequestStatus.PROCESSING
            await self.db.commit()
            logger.info(
                f"Updated request {request_id} status to processing",
                extra={"request_id": request_id},
            )

            # Initialize orchestrator
            orchestrator = AgentOrchestrator(
                text=request.input_text,
                mode=request.orchestration_mode.value,
            )

            # Execute agents
            logger.info(
                f"Executing agents in {request.orchestration_mode.value} mode",
                extra={
                    "request_id": request_id,
                    "mode": request.orchestration_mode.value,
                },
            )
            aggregated_data = await orchestrator.execute()

            # Store agent results
            for agent_result_data in aggregated_data["agent_results"]:
                agent_result = AgentResult(
                    request_id=request_id,
                    agent_name=agent_result_data["agent_name"],
                    result_data=agent_result_data["result_data"],
                    execution_time=agent_result_data["execution_time"],
                    status=AgentStatus.SUCCESS
                    if agent_result_data["status"] == "success"
                    else AgentStatus.ERROR,
                    error_message=agent_result_data.get("error_message"),
                )
                self.db.add(agent_result)

            # Check if any agent failed
            has_failures = any(
                result["status"] == "error"
                for result in aggregated_data["agent_results"]
            )

            if has_failures:
                logger.warning(
                    f"Some agents failed for request {request_id}",
                    extra={"request_id": request_id},
                )

            # Create aggregated result
            aggregated_result = AggregatedResult(
                request_id=request_id,
                summary=aggregated_data["summary"],
                sentiment=aggregated_data["sentiment"],
                entities=aggregated_data["entities"],
                total_execution_time=aggregated_data["total_execution_time"],
            )
            self.db.add(aggregated_result)

            # Update request status
            request.status = (
                RequestStatus.COMPLETED if not has_failures else RequestStatus.FAILED
            )
            await self.db.commit()

            logger.info(
                f"Processing completed for request {request_id}",
                extra={
                    "request_id": request_id,
                    "status": request.status.value,
                    "execution_time": aggregated_data["total_execution_time"],
                },
            )

            # Send webhook if configured
            if request.webhook_url:
                logger.info(
                    f"Triggering webhook for request {request_id}",
                    extra={"request_id": request_id},
                )

                webhook_service = WebhookService(self.db)

                # Prepare result data with timestamp
                result_data = {
                    **aggregated_data,
                    "timestamp": datetime.utcnow(),
                }

                try:
                    await webhook_service.send_webhook(request_id, result_data)
                except Exception as e:
                    logger.error(
                        f"Webhook delivery failed for request {request_id}: {str(e)}",
                        extra={"request_id": request_id},
                    )
                    # Don't fail the entire request if webhook fails

        except OrchestrationError as e:
            logger.error(
                f"Orchestration failed for request {request_id}: {str(e)}",
                exc_info=True,
                extra={"request_id": request_id},
            )
            request.status = RequestStatus.FAILED
            await self.db.commit()
        except Exception as e:
            logger.error(
                f"Processing failed for request {request_id}: {str(e)}",
                exc_info=True,
                extra={"request_id": request_id},
            )
            request.status = RequestStatus.FAILED
            await self.db.commit()
            raise

