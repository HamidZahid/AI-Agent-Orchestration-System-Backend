"""Webhook delivery service with HMAC signing and retry logic."""

import hmac
import hashlib
import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.config import settings
from src.backend.models import ProcessingRequest, WebhookLog, WebhookStatus
from src.backend.schemas import WebhookPayload
from src.backend.utils.exceptions import (
    InvalidWebhookSignatureError,
    WebhookDeliveryError,
)
from src.backend.utils.logger import get_logger

logger = get_logger(__name__)


class WebhookService:
    """Service for webhook delivery with security and retry logic."""

    def __init__(self, db: AsyncSession):
        """
        Initialize webhook service.

        Args:
            db: Database session
        """
        self.db = db

    async def send_webhook(
        self,
        request_id: UUID,
        result_data: dict[str, Any],
    ) -> bool:
        """
        Send webhook with HMAC signature and retry logic.

        Args:
            request_id: Processing request ID
            result_data: Result data to send in webhook

        Returns:
            True if webhook was sent successfully, False otherwise
        """
        # Get processing request
        request = await self.db.get(ProcessingRequest, request_id)
        if not request:
            logger.error(f"Processing request {request_id} not found")
            return False

        if not request.webhook_url:
            logger.warning(f"No webhook URL configured for request {request_id}")
            return False

        webhook_url = str(request.webhook_url)
        webhook_secret = request.webhook_secret

        # Construct payload
        # Get timestamp
        timestamp = result_data.get("timestamp")
        if not timestamp:
            timestamp = datetime.utcnow()

        payload = WebhookPayload(
            request_id=str(request_id),
            status=request.status.value,
            summary=result_data.get("summary", ""),
            sentiment=result_data.get("sentiment", {}),
            entities=result_data.get("entities", {}),
            agent_results=result_data.get("agent_results", []),
            total_execution_time=result_data.get("total_execution_time", 0.0),
            timestamp=timestamp,
        )

        payload_dict = payload.model_dump(mode="json")
        payload_json = payload.model_dump_json(exclude_none=True)

        # Generate HMAC signature
        signature = None
        if webhook_secret:
            signature = self._generate_signature(payload_json.encode("utf-8"), webhook_secret)

        # Attempt webhook delivery with retries
        max_attempts = settings.WEBHOOK_MAX_RETRIES
        retry_delays = settings.WEBHOOK_RETRY_DELAYS

        for attempt in range(1, max_attempts + 1):
            try:
                success = await self._send_webhook_request(
                    webhook_url=webhook_url,
                    payload=payload_dict,
                    signature=signature,
                    request_id=request_id,
                    attempt=attempt,
                )

                if success:
                    # Update request status
                    request.webhook_status = WebhookStatus.SENT
                    request.webhook_attempts = attempt
                    request.webhook_last_attempt = datetime.utcnow()
                    await self.db.commit()
                    logger.info(
                        f"Webhook delivered successfully for request {request_id}",
                        extra={"request_id": request_id, "attempt": attempt},
                    )
                    return True

            except Exception as e:
                error_msg = str(e)
                logger.warning(
                    f"Webhook attempt {attempt} failed for request {request_id}: {error_msg}",
                    extra={"request_id": request_id, "attempt": attempt},
                )

                # Log the failed attempt
                await self._log_webhook_attempt(
                    request_id=request_id,
                    webhook_url=webhook_url,
                    payload=payload_dict,
                    attempt=attempt,
                    error_message=error_msg,
                )

                # Update request tracking
                request.webhook_attempts = attempt
                request.webhook_last_attempt = datetime.utcnow()
                await self.db.commit()

                # Retry with exponential backoff (except on last attempt)
                if attempt < max_attempts:
                    delay = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
                    logger.info(
                        f"Retrying webhook for request {request_id} after {delay}s",
                        extra={"request_id": request_id, "delay": delay},
                    )
                    await asyncio.sleep(delay)

        # All attempts failed
        request.webhook_status = WebhookStatus.FAILED
        await self.db.commit()
        logger.error(
            f"All webhook attempts failed for request {request_id}",
            extra={"request_id": request_id, "attempts": max_attempts},
        )
        return False

    async def _send_webhook_request(
        self,
        webhook_url: str,
        payload: dict[str, Any],
        signature: str | None,
        request_id: UUID,
        attempt: int,
    ) -> bool:
        """
        Send a single webhook request.

        Args:
            webhook_url: Webhook URL
            payload: Payload to send
            signature: HMAC signature if available
            request_id: Request ID for logging
            attempt: Attempt number

        Returns:
            True if request was successful, False otherwise

        Raises:
            WebhookDeliveryError: If delivery fails
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "AI-Agent-Orchestrator/1.0",
        }

        if signature:
            headers["X-Webhook-Signature"] = signature

        timeout = httpx.Timeout(settings.WEBHOOK_TIMEOUT)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                )

                status_code = response.status_code
                response_body = response.text[:1000]  # Limit response body length

                # Log the attempt
                await self._log_webhook_attempt(
                    request_id=request_id,
                    webhook_url=webhook_url,
                    payload=payload,
                    attempt=attempt,
                    status_code=status_code,
                    response_body=response_body,
                )

                # Check if successful (2xx status codes)
                if 200 <= status_code < 300:
                    return True

                # Don't retry on 4xx errors (except 429 rate limit)
                if 400 <= status_code < 500 and status_code != 429:
                    raise WebhookDeliveryError(
                        webhook_url=webhook_url,
                        message=f"Client error: {status_code}",
                        status_code=status_code,
                    )

                # Retry on 5xx errors and 429
                raise WebhookDeliveryError(
                    webhook_url=webhook_url,
                    message=f"Server error: {status_code}",
                    status_code=status_code,
                )

        except httpx.TimeoutException as e:
            raise WebhookDeliveryError(
                webhook_url=webhook_url,
                message=f"Request timeout after {settings.WEBHOOK_TIMEOUT}s",
                original_error=e,
            ) from e
        except httpx.ConnectError as e:
            raise WebhookDeliveryError(
                webhook_url=webhook_url,
                message="Connection error",
                original_error=e,
            ) from e
        except WebhookDeliveryError:
            raise
        except Exception as e:
            raise WebhookDeliveryError(
                webhook_url=webhook_url,
                message=f"Unexpected error: {str(e)}",
                original_error=e,
            ) from e

    async def _log_webhook_attempt(
        self,
        request_id: UUID,
        webhook_url: str,
        payload: dict[str, Any],
        attempt: int,
        status_code: int | None = None,
        response_body: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """
        Log a webhook delivery attempt.

        Args:
            request_id: Processing request ID
            webhook_url: Webhook URL
            payload: Payload sent
            attempt: Attempt number
            status_code: HTTP status code if available
            response_body: Response body if available
            error_message: Error message if any
        """
        # Sanitize payload (remove secrets if present)
        sanitized_payload = payload.copy()
        if "webhook_secret" in sanitized_payload:
            sanitized_payload["webhook_secret"] = "***REDACTED***"

        log_entry = WebhookLog(
            request_id=request_id,
            webhook_url=webhook_url,
            payload=sanitized_payload,
            status_code=status_code,
            response_body=response_body,
            error_message=error_message,
            attempt_number=attempt,
        )

        self.db.add(log_entry)
        await self.db.commit()

    def _generate_signature(self, payload: bytes, secret: str) -> str:
        """
        Generate HMAC-SHA256 signature for webhook payload.

        Args:
            payload: Payload bytes
            secret: Secret key for HMAC

        Returns:
            Hexadecimal signature string
        """
        return hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

    async def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """
        Verify HMAC-SHA256 signature of incoming webhook.

        Uses constant-time comparison to prevent timing attacks.

        Args:
            payload: Payload bytes
            signature: Signature to verify (hexadecimal string)
            secret: Secret key for HMAC

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            expected_signature = self._generate_signature(payload, secret)
            # Use constant-time comparison
            return hmac.compare_digest(expected_signature, signature)
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False

