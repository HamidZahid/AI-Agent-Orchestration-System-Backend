"""Configuration management using Pydantic Settings with python-dotenv."""

import json
from typing import List

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database Configuration
    DATABASE_URL: str = Field(
        ...,
        description="PostgreSQL database connection URL",
    )

    # OpenAI Configuration
    OPENAI_API_KEY: str = Field(
        ...,
        description="OpenAI API key for agent operations",
    )

    # Logging Configuration
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # Webhook Configuration
    WEBHOOK_TIMEOUT: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Webhook request timeout in seconds",
    )
    WEBHOOK_MAX_RETRIES: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of webhook retry attempts",
    )
    WEBHOOK_RETRY_DELAYS: List[int] = Field(
        default=[1, 5, 15],
        description="Exponential backoff delays in seconds for webhook retries",
    )

    @field_validator("WEBHOOK_RETRY_DELAYS", mode="before")
    @classmethod
    def parse_retry_delays(cls, v):
        """Parse retry delays from JSON string if needed."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # If not JSON, treat as comma-separated string
                return [int(d.strip()) for d in v.split(",")]
        return v

    # Processing Configuration
    MAX_TEXT_LENGTH: int = Field(
        default=10000,
        ge=100,
        le=100000,
        description="Maximum allowed text length for processing",
    )

    # CORS Configuration
    CORS_ORIGINS: List[str] = Field(
        default=["*"],
        description="Allowed CORS origins",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from JSON string if needed."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # If not JSON, treat as comma-separated string
                return [origin.strip() for origin in v.split(",")]
        return v

    # API Configuration
    API_PREFIX: str = Field(
        default="/api/v1",
        description="API route prefix",
    )

    # Application Configuration
    APP_NAME: str = Field(
        default="AI Agent Orchestration System",
        description="Application name",
    )
    APP_VERSION: str = Field(
        default="1.0.0",
        description="Application version",
    )
    DEBUG: bool = Field(
        default=False,
        description="Debug mode",
    )


# Global settings instance
settings = Settings()

