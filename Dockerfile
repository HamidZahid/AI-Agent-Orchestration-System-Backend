# Multi-stage Dockerfile for production optimization with security hardening

# Stage 1: Builder
FROM python:3.12-slim as builder

# Set build arguments for security
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION

# Add labels for metadata
LABEL maintainer="AI Agent Orchestration System" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.authors="FISTA Solutions" \
      org.opencontainers.image.url="https://github.com/yourorg/backend" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.vendor="FISTA Solutions" \
      org.opencontainers.image.title="AI Agent Orchestration System" \
      org.opencontainers.image.description="Production-ready AI Agent Orchestration System backend"

WORKDIR /app

# Install build dependencies with security updates
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* \
    && rm -rf /var/tmp/*

# Install uv for dependency management
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies using uv
RUN uv pip install --system --no-cache . && \
    rm -rf /root/.cache/pip && \
    rm -rf /root/.cache/uv

# Stage 2: Runtime (minimal, secure production image)
FROM python:3.12-slim

# Security: Create non-root user first to ensure proper permissions
RUN groupadd -r appuser && \
    useradd -r -g appuser -u 1000 -m -d /home/appuser -s /bin/bash appuser && \
    mkdir -p /app && \
    chown -R appuser:appuser /app

WORKDIR /app

# Install only runtime dependencies (minimal attack surface)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /tmp/* \
    && rm -rf /var/tmp/* \
    && update-ca-certificates

# Security: Copy installed packages from builder (without build tools)
COPY --from=builder --chown=appuser:appuser /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder --chown=appuser:appuser /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy application code with proper ownership
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser alembic/ ./alembic/

# Security: Switch to non-root user
USER appuser

# Security: Set read-only where possible
# Note: /app needs to be writable for logs and temp files
# Consider mounting /app/logs as volume if needed

# Health check using curl (already installed)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Expose port
EXPOSE 8000

# Use exec form for proper signal handling
CMD ["uvicorn", "src.backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
