"""Webhook endpoints for receiving and handling webhook requests."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from src.backend.api.dependencies import DatabaseDep, RequestIdDep, rate_limit_webhook
from src.backend.models import OrchestrationMode, ProcessingRequest, RequestStatus
from src.backend.schemas import ProcessingResponse, TextProcessRequest
from src.backend.services.processing_service import ProcessingService
from src.backend.services.webhook_service import WebhookService
from src.backend.utils.background_tasks import process_text_async
from src.backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Webhooks"])


class WebhookTestPayload(BaseModel):
    """Test payload for webhook callback test."""

    message: str = "Webhook test successful"
    timestamp: str = ""


@router.post("/receive", response_model=ProcessingResponse, dependencies=[Depends(rate_limit_webhook)])
async def receive_webhook(
    request_data: TextProcessRequest,
    background_tasks: BackgroundTasks,
    db: DatabaseDep,
    request_id: RequestIdDep,
) -> ProcessingResponse:
    """
    Main webhook endpoint for receiving text processing requests.

    Validates request, creates ProcessingRequest, and triggers background processing.
    Returns immediately with request_id.

    Args:
        request_data: Text processing request data
        background_tasks: FastAPI background tasks
        db: Database session
        request_id: Request ID for correlation

    Returns:
        Processing response with request_id and status
    """
    logger.info(
        "Received webhook request",
        extra={"request_id": request_id, "mode": request_data.orchestration_mode},
    )

    # Validate text length
    from src.backend.config import settings

    if len(request_data.text) > settings.MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Text length exceeds maximum of {settings.MAX_TEXT_LENGTH} characters",
        )

    # Create processing request
    processing_request = ProcessingRequest(
        input_text=request_data.text,
        orchestration_mode=OrchestrationMode(request_data.orchestration_mode),
        status=RequestStatus.PENDING,
        webhook_url=str(request_data.webhook_url) if request_data.webhook_url else None,
        webhook_secret=request_data.webhook_secret,
        webhook_status=None,
    )

    db.add(processing_request)
    await db.commit()
    await db.refresh(processing_request)

    logger.info(
        f"Created processing request {processing_request.id} from webhook",
        extra={
            "request_id": request_id,
            "processing_request_id": str(processing_request.id),
        },
    )

    # Add background task for processing
    background_tasks.add_task(process_text_async, processing_request.id)

    return ProcessingResponse(
        request_id=processing_request.id,
        status="pending",
        message="Processing started",
        webhook_registered=request_data.webhook_url is not None,
    )


@router.post("/callback/test", dependencies=[Depends(rate_limit_webhook)])
async def test_webhook_callback(
    payload: dict,
    request: Request,
) -> dict:
    """
    Test endpoint for webhook callback validation.

    Echoes back received data with timestamp.
    Useful for testing webhook delivery and signature verification.

    Args:
        payload: Webhook payload data
        request: FastAPI request object

    Returns:
        Echo response with payload and metadata
    """
    from datetime import datetime

    logger.info("Received test webhook callback", extra={"payload_keys": list(payload.keys())})

    # Check for signature header
    signature = request.headers.get("X-Webhook-Signature")
    signature_info = {"signature_present": signature is not None}

    if signature:
        signature_info["signature_value"] = signature[:20] + "..."  # Truncate for logging

    response_data = {
        "message": "Webhook callback test successful",
        "received_payload": payload,
        "timestamp": datetime.utcnow().isoformat(),
        "signature_info": signature_info,
        "headers": dict(request.headers),
    }

    logger.info("Sent test webhook callback response")
    return response_data

