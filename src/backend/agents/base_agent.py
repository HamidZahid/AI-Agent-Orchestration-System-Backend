"""Base agent class with error handling."""

from abc import ABC, abstractmethod
from typing import Any

from src.backend.utils.exceptions import AgentExecutionError
from src.backend.utils.logger import get_logger

logger = get_logger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all AI agents."""

    def __init__(self, name: str, api_key: str | None = None):
        """
        Initialize base agent.

        Args:
            name: Agent name
            api_key: OpenAI API key (optional, uses config if not provided)
        """
        self.name = name
        self.api_key = api_key
        logger.info(f"Initialized agent: {name}")

    @abstractmethod
    async def execute(self, text: str) -> dict[str, Any]:
        """
        Execute agent on input text.

        Args:
            text: Input text to process

        Returns:
            Dictionary with agent result data

        Raises:
            AgentExecutionError: If execution fails
        """
        pass

    async def run(self, text: str) -> dict[str, Any]:
        """
        Run agent with error handling and logging.

        Args:
            text: Input text to process

        Returns:
            Dictionary with agent result data

        Raises:
            AgentExecutionError: If execution fails
        """
        logger.info(
            f"Agent {self.name} starting execution",
            extra={"agent_name": self.name},
        )
        try:
            result = await self.execute(text)
            logger.info(
                f"Agent {self.name} completed successfully",
                extra={"agent_name": self.name},
            )
            return result
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"Agent {self.name} failed: {error_msg}",
                exc_info=True,
                extra={"agent_name": self.name},
            )
            raise AgentExecutionError(
                agent_name=self.name,
                message=error_msg,
                original_error=e,
            ) from e

    def __repr__(self) -> str:
        """String representation of agent."""
        return f"{self.__class__.__name__}(name={self.name})"

