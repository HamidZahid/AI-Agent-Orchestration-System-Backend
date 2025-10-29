"""FastAPI dependencies for request processing."""

import time
from collections import defaultdict
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.database import get_db
from src.backend.utils.logger import get_logger

logger = get_logger(__name__)

# Rate limiting storage (in-memory, use Redis for production)
rate_limit_storage: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 60  # 1 minute


async def get_db_session() -> AsyncSession:
    """
    Get database session dependency.

    Yields:
        AsyncSession: Database session
    """
    async for session in get_db():
        yield session


# Dependency for database session
DatabaseDep = Annotated[AsyncSession, Depends(get_db_session)]


async def get_request_id(
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
) -> str:
    """
    Get or generate request ID for correlation tracking.

    Args:
        x_request_id: Request ID from header

    Returns:
        Request ID string
    """
    if x_request_id:
        return x_request_id
    return str(uuid4())


RequestIdDep = Annotated[str, Depends(get_request_id)]


async def rate_limit_webhook(
    request: Request,
) -> None:
    """
    Rate limiting dependency for webhook endpoints.

    Allows 100 requests per minute per IP address.

    Args:
        request: FastAPI request object

    Raises:
        HTTPException: If rate limit is exceeded
    """
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()

    # Clean old entries
    rate_limit_storage[client_ip] = [
        timestamp
        for timestamp in rate_limit_storage[client_ip]
        if current_time - timestamp < RATE_LIMIT_WINDOW
    ]

    # Check rate limit
    if len(rate_limit_storage[client_ip]) >= RATE_LIMIT_REQUESTS:
        logger.warning(
            f"Rate limit exceeded for IP {client_ip}",
            extra={"client_ip": client_ip},
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 100 requests per minute.",
        )

    # Add current request
    rate_limit_storage[client_ip].append(current_time)

