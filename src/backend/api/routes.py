"""REST API endpoints for the AI Agent Orchestration System."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.api.dependencies import DatabaseDep, RequestIdDep
from src.backend.models import (
    AggregatedResult,
    AgentResult,
    ProcessingRequest,
    RequestStatus,
    WebhookLog,
)
from src.backend.schemas import (
    AggregatedResultResponse,
    ErrorResponse,
    HealthCheckResponse,
    PaginatedResponse,
    ProcessingResponse,
    TextProcessRequest,
    WebhookLogResponse,
)
from src.backend.services.processing_service import ProcessingService
from src.backend.services.webhook_service import WebhookService
from src.backend.utils.background_tasks import process_text_async, send_webhook_async
from src.backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["API"])


@router.post("/process", response_model=ProcessingResponse)
async def process_text(
    request: TextProcessRequest,
    background_tasks: BackgroundTasks,
    db: DatabaseDep,
    request_id: RequestIdDep,
) -> ProcessingResponse:
    """
    Submit a text processing request.

    Creates a processing request and starts background processing.
    Returns immediately with request_id for polling.

    Args:
        request: Text processing request
        background_tasks: FastAPI background tasks
        db: Database session
        request_id: Request ID for correlation

    Returns:
        Processing response with request_id and status
    """
    try:
        logger.info(
            "Received text processing request",
            extra={"request_id": request_id, "mode": request.orchestration_mode},
        )

        # Validate text length
        from src.backend.config import settings

        if len(request.text) > settings.MAX_TEXT_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Text length exceeds maximum of {settings.MAX_TEXT_LENGTH} characters",
            )

        # Create processing request
        from src.backend.models import OrchestrationMode

        processing_request = ProcessingRequest(
            input_text=request.text,
            orchestration_mode=OrchestrationMode(request.orchestration_mode),
            status=RequestStatus.PENDING,
            webhook_url=str(request.webhook_url) if request.webhook_url else None,
            webhook_secret=request.webhook_secret,
            webhook_status=None,
        )

        db.add(processing_request)
        await db.commit()
        await db.refresh(processing_request)

        logger.info(
            f"Created processing request {processing_request.id}",
            extra={
                "request_id": request_id,
                "processing_request_id": str(processing_request.id),
            },
        )

        # Add background task
        background_tasks.add_task(process_text_async, processing_request.id)

        return ProcessingResponse(
            request_id=processing_request.id,
            status="pending",
            message="Processing started",
            webhook_registered=request.webhook_url is not None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error processing request: {str(e)}",
            exc_info=True,
            extra={"request_id": request_id},
        )
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/results/{request_id}", response_model=AggregatedResultResponse)
async def get_result(
    request_id: UUID,
    db: DatabaseDep,
    request_id_header: RequestIdDep,
) -> AggregatedResultResponse:
    """
    Get processing result for a specific request.

    Args:
        request_id: Processing request ID
        db: Database session
        request_id_header: Request ID for correlation

    Returns:
        Aggregated result response

    Raises:
        HTTPException: If request not found
    """
    result = await db.scalar(
        select(AggregatedResult).where(AggregatedResult.request_id == request_id)
    )

    if not result:
        # Check if request exists
        request = await db.get(ProcessingRequest, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Processing request not found")

        # Request exists but no result yet
        raise HTTPException(
            status_code=404,
            detail="Processing result not yet available",
        )

    # Get processing request for webhook status
    request = await db.get(ProcessingRequest, request_id)

    # Get agent results
    agent_results_query = await db.execute(
        select(AgentResult).where(AgentResult.request_id == request_id)
    )
    agent_results = agent_results_query.scalars().all()

    # Convert to response format
    agent_results_data = [
        {
            "agent_name": ar.agent_name,
            "result_data": ar.result_data,
            "execution_time": ar.execution_time,
            "status": ar.status.value,
        }
        for ar in agent_results
    ]

    return AggregatedResultResponse(
        request_id=result.request_id,
        summary=result.summary,
        sentiment=result.sentiment,
        entities=result.entities,
        agent_results=agent_results_data,
        total_execution_time=result.total_execution_time,
        created_at=result.created_at,
        webhook_status=request.webhook_status.value if request.webhook_status else None,
        webhook_attempts=request.webhook_attempts,
    )


@router.get("/results", response_model=PaginatedResponse)
async def list_results(
    db: DatabaseDep,
    request_id: RequestIdDep,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    status: RequestStatus | None = Query(None, description="Filter by status"),
    webhook_status: str | None = Query(None, description="Filter by webhook status"),
    start_date: datetime | None = Query(None, description="Start date filter"),
    end_date: datetime | None = Query(None, description="End date filter"),
) -> PaginatedResponse:
    """
    List all processing results with pagination and filtering.

    Args:
        db: Database session
        request_id: Request ID for correlation
        page: Page number (1-indexed)
        page_size: Number of items per page
        status: Filter by processing status
        webhook_status: Filter by webhook status
        start_date: Filter results created after this date
        end_date: Filter results created before this date

    Returns:
        Paginated response with results
    """
    query = select(AggregatedResult)

    # Apply filters
    if status:
        query = query.join(ProcessingRequest).where(
            ProcessingRequest.status == status
        )
    if webhook_status:
        query = query.join(ProcessingRequest).where(
            ProcessingRequest.webhook_status == webhook_status
        )
    if start_date:
        query = query.where(AggregatedResult.created_at >= start_date)
    if end_date:
        query = query.where(AggregatedResult.created_at <= end_date)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(AggregatedResult.created_at.desc())
    query = query.offset(offset).limit(page_size)

    result_query = await db.execute(query)
    results = result_query.scalars().all()

    # Get agent results for each aggregated result
    items = []
    for result in results:
        # Get agent results
        agent_results_query = await db.execute(
            select(AgentResult).where(AgentResult.request_id == result.request_id)
        )
        agent_results = agent_results_query.scalars().all()

        # Get processing request
        request = await db.get(ProcessingRequest, result.request_id)

        items.append(
            AggregatedResultResponse(
                request_id=result.request_id,
                summary=result.summary,
                sentiment=result.sentiment,
                entities=result.entities,
                agent_results=[
                    {
                        "agent_name": ar.agent_name,
                        "result_data": ar.result_data,
                        "execution_time": ar.execution_time,
                        "status": ar.status.value,
                    }
                    for ar in agent_results
                ],
                total_execution_time=result.total_execution_time,
                created_at=result.created_at,
                webhook_status=request.webhook_status.value
                if request.webhook_status
                else None,
                webhook_attempts=request.webhook_attempts,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total or 0,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < (total or 0),
        has_previous=page > 1,
    )


@router.get("/webhook-logs/{request_id}", response_model=list[WebhookLogResponse])
async def get_webhook_logs(
    request_id: UUID,
    db: DatabaseDep,
    request_id_header: RequestIdDep,
) -> list[WebhookLogResponse]:
    """
    Get webhook delivery logs for a specific request.

    Args:
        request_id: Processing request ID
        db: Database session
        request_id_header: Request ID for correlation

    Returns:
        List of webhook log entries

    Raises:
        HTTPException: If request not found
    """
    # Verify request exists
    request = await db.get(ProcessingRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Processing request not found")

    # Get webhook logs
    logs_query = await db.execute(
        select(WebhookLog)
        .where(WebhookLog.request_id == request_id)
        .order_by(WebhookLog.created_at.desc())
    )
    logs = logs_query.scalars().all()

    return [
        WebhookLogResponse(
            id=log.id,
            request_id=log.request_id,
            webhook_url=log.webhook_url,
            status_code=log.status_code,
            response_body=log.response_body,
            error_message=log.error_message,
            attempt_number=log.attempt_number,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.post("/webhook/retry/{request_id}")
async def retry_webhook(
    request_id: UUID,
    background_tasks: BackgroundTasks,
    db: DatabaseDep,
    request_id_header: RequestIdDep,
) -> dict[str, str]:
    """
    Manually retry webhook delivery for a failed webhook.

    Args:
        request_id: Processing request ID
        background_tasks: FastAPI background tasks
        db: Database session
        request_id_header: Request ID for correlation

    Returns:
        Success message

    Raises:
        HTTPException: If request not found or webhook not configured
    """
    request = await db.get(ProcessingRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Processing request not found")

    if not request.webhook_url:
        raise HTTPException(
            status_code=400,
            detail="No webhook URL configured for this request",
        )

    if request.status != RequestStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="Request must be completed before webhook can be retried",
        )

    # Add background task to retry webhook
    background_tasks.add_task(send_webhook_async, request_id)

    return {"message": "Webhook retry initiated"}


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(
    db: DatabaseDep,
    request_id: RequestIdDep,
) -> HealthCheckResponse:
    """
    Health check endpoint.

    Checks database connectivity and OpenAI API connectivity.

    Args:
        db: Database session
        request_id: Request ID for correlation

    Returns:
        Health check response
    """
    # Check database
    db_status = "healthy"
    try:
        await db.execute(select(1))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
        logger.error(f"Database health check failed: {str(e)}")

    # Check OpenAI API
    openai_status = "healthy"
    try:
        from openai import AsyncOpenAI
        from src.backend.config import settings

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        # Simple API key validation
        # Note: This is a lightweight check, full validation would require an API call
        if not settings.OPENAI_API_KEY:
            openai_status = "unhealthy: API key not configured"
        else:
            # Try to list models (lightweight operation)
            await client.models.list()
    except Exception as e:
        openai_status = f"unhealthy: {str(e)}"
        logger.error(f"OpenAI API health check failed: {str(e)}")

    overall_status = (
        "healthy" if db_status == "healthy" and openai_status == "healthy" else "degraded"
    )

    return HealthCheckResponse(
        status=overall_status,
        database=db_status,
        openai=openai_status,
        timestamp=datetime.utcnow(),
    )

