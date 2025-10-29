"""Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator


class TextProcessRequest(BaseModel):
    """Schema for text processing request."""

    text: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="Text to process",
    )
    orchestration_mode: Literal["sequential", "parallel"] = Field(
        default="sequential",
        description="Execution mode for agents",
    )
    webhook_url: Optional[HttpUrl] = Field(
        default=None,
        description="URL to receive processing results",
    )
    webhook_secret: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Secret for HMAC webhook signature",
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Validate text is not just whitespace."""
        if not v.strip():
            raise ValueError("Text cannot be empty or only whitespace")
        return v


class AgentResultSchema(BaseModel):
    """Schema for agent execution result."""

    agent_name: str = Field(..., description="Name of the agent")
    result_data: dict = Field(..., description="Agent result data")
    execution_time: float = Field(..., ge=0, description="Execution time in seconds")
    status: Literal["success", "error"] = Field(..., description="Execution status")

    class Config:
        """Pydantic config."""

        from_attributes = True


class WebhookPayload(BaseModel):
    """Schema for webhook payload sent to external systems."""

    request_id: str = Field(..., description="Processing request ID")
    status: str = Field(..., description="Processing status")
    summary: str = Field(..., description="Text summary")
    sentiment: dict = Field(..., description="Sentiment analysis result")
    entities: dict = Field(..., description="Extracted entities")
    agent_results: List[AgentResultSchema] = Field(
        ...,
        description="Individual agent results",
    )
    total_execution_time: float = Field(
        ...,
        ge=0,
        description="Total execution time in seconds",
    )
    timestamp: datetime = Field(..., description="Processing completion timestamp")


class ProcessingResponse(BaseModel):
    """Schema for processing request response."""

    request_id: UUID = Field(..., description="Processing request ID")
    status: str = Field(..., description="Current processing status")
    message: str = Field(..., description="Response message")
    webhook_registered: bool = Field(..., description="Whether webhook is registered")


class AggregatedResultResponse(BaseModel):
    """Schema for aggregated result response."""

    request_id: UUID = Field(..., description="Processing request ID")
    summary: str = Field(..., description="Text summary")
    sentiment: dict = Field(..., description="Sentiment analysis result")
    entities: dict = Field(..., description="Extracted entities")
    agent_results: List[AgentResultSchema] = Field(
        ...,
        description="Individual agent results",
    )
    total_execution_time: float = Field(
        ...,
        ge=0,
        description="Total execution time in seconds",
    )
    created_at: datetime = Field(..., description="Result creation timestamp")
    webhook_status: Optional[str] = Field(
        None,
        description="Webhook delivery status",
    )
    webhook_attempts: int = Field(
        ...,
        ge=0,
        description="Number of webhook delivery attempts",
    )

    class Config:
        """Pydantic config."""

        from_attributes = True


class WebhookLogResponse(BaseModel):
    """Schema for webhook log response."""

    id: UUID = Field(..., description="Log entry ID")
    request_id: UUID = Field(..., description="Processing request ID")
    webhook_url: str = Field(..., description="Webhook URL")
    status_code: Optional[int] = Field(None, description="HTTP status code")
    response_body: Optional[str] = Field(None, description="Response body")
    error_message: Optional[str] = Field(None, description="Error message if any")
    attempt_number: int = Field(..., ge=1, description="Attempt number")
    created_at: datetime = Field(..., description="Log creation timestamp")

    class Config:
        """Pydantic config."""

        from_attributes = True


class HealthCheckResponse(BaseModel):
    """Schema for health check response."""

    status: str = Field(..., description="Overall health status")
    database: str = Field(..., description="Database connection status")
    openai: str = Field(..., description="OpenAI API status")
    timestamp: datetime = Field(..., description="Check timestamp")


class ErrorResponse(BaseModel):
    """Schema for error responses."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    request_id: Optional[UUID] = Field(None, description="Request ID if available")


class PaginatedResponse(BaseModel):
    """Schema for paginated responses."""

    items: List[AggregatedResultResponse] = Field(..., description="Result items")
    total: int = Field(..., ge=0, description="Total number of items")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Page size")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_previous: bool = Field(..., description="Whether there is a previous page")

