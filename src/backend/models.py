"""SQLAlchemy ORM models for the AI Agent Orchestration System."""

import enum
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.backend.database import Base


class OrchestrationMode(str, enum.Enum):
    """Orchestration mode enumeration."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class RequestStatus(str, enum.Enum):
    """Processing request status enumeration."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class WebhookStatus(str, enum.Enum):
    """Webhook delivery status enumeration."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class AgentStatus(str, enum.Enum):
    """Agent execution status enumeration."""

    SUCCESS = "success"
    ERROR = "error"


class ProcessingRequest(Base):
    """Model for processing requests."""

    __tablename__ = "processing_requests"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    orchestration_mode: Mapped[OrchestrationMode] = mapped_column(
        Enum(
            OrchestrationMode,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            name="orchestrationmode",
        ),
        nullable=False,
        default=OrchestrationMode.SEQUENTIAL,
        index=True,
    )
    status: Mapped[RequestStatus] = mapped_column(
        Enum(
            RequestStatus,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            name="requeststatus",
        ),
        nullable=False,
        default=RequestStatus.PENDING,
        index=True,
    )
    webhook_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    webhook_secret: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    webhook_status: Mapped[Optional[WebhookStatus]] = mapped_column(
        Enum(
            WebhookStatus,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            name="webhookstatus",
        ),
        nullable=True,
        index=True,
    )
    webhook_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    webhook_last_attempt: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    webhook_response: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    agent_results: Mapped[list["AgentResult"]] = relationship(
        "AgentResult",
        back_populates="request",
        cascade="all, delete-orphan",
    )
    aggregated_result: Mapped[Optional["AggregatedResult"]] = relationship(
        "AggregatedResult",
        back_populates="request",
        uselist=False,
        cascade="all, delete-orphan",
    )
    webhook_logs: Mapped[list["WebhookLog"]] = relationship(
        "WebhookLog",
        back_populates="request",
        cascade="all, delete-orphan",
    )


class AgentResult(Base):
    """Model for individual agent execution results."""

    __tablename__ = "agent_results"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )
    request_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    result_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    execution_time: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    status: Mapped[AgentStatus] = mapped_column(
        Enum(
            AgentStatus,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            name="agentstatus",
        ),
        nullable=False,
        index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    request: Mapped["ProcessingRequest"] = relationship(
        "ProcessingRequest",
        back_populates="agent_results",
    )


class AggregatedResult(Base):
    """Model for aggregated processing results."""

    __tablename__ = "aggregated_results"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )
    request_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_requests.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    sentiment: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    entities: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    total_execution_time: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    request: Mapped["ProcessingRequest"] = relationship(
        "ProcessingRequest",
        back_populates="aggregated_result",
    )

    __table_args__ = (
        UniqueConstraint("request_id", name="uq_aggregated_results_request_id"),
    )


class WebhookLog(Base):
    """Model for webhook delivery logs."""

    __tablename__ = "webhook_logs"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )
    request_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    webhook_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    status_code: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    response_body: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    request: Mapped["ProcessingRequest"] = relationship(
        "ProcessingRequest",
        back_populates="webhook_logs",
    )

