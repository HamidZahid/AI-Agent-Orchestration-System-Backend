"""Custom exception classes for the AI Agent Orchestration System."""


class AgentExecutionError(Exception):
    """Raised when an agent execution fails."""

    def __init__(self, agent_name: str, message: str, original_error: Exception | None = None):
        """
        Initialize agent execution error.

        Args:
            agent_name: Name of the agent that failed
            message: Error message
            original_error: Original exception if any
        """
        self.agent_name = agent_name
        self.original_error = original_error
        super().__init__(f"Agent '{agent_name}' execution failed: {message}")


class OrchestrationError(Exception):
    """Raised when agent orchestration fails."""

    def __init__(self, message: str, original_error: Exception | None = None):
        """
        Initialize orchestration error.

        Args:
            message: Error message
            original_error: Original exception if any
        """
        self.original_error = original_error
        super().__init__(f"Orchestration failed: {message}")


class WebhookDeliveryError(Exception):
    """Raised when webhook delivery fails."""

    def __init__(
        self,
        webhook_url: str,
        message: str,
        status_code: int | None = None,
        original_error: Exception | None = None,
    ):
        """
        Initialize webhook delivery error.

        Args:
            webhook_url: URL where webhook delivery failed
            message: Error message
            status_code: HTTP status code if available
            original_error: Original exception if any
        """
        self.webhook_url = webhook_url
        self.status_code = status_code
        self.original_error = original_error
        status_info = f" (HTTP {status_code})" if status_code else ""
        super().__init__(f"Webhook delivery to {webhook_url} failed{status_info}: {message}")


class InvalidWebhookSignatureError(Exception):
    """Raised when webhook signature verification fails."""

    def __init__(self, message: str = "Invalid webhook signature"):
        """
        Initialize invalid webhook signature error.

        Args:
            message: Error message
        """
        super().__init__(message)

