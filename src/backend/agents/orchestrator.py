"""Agent orchestration logic with sequential and parallel execution modes."""

import asyncio
import time
from typing import Any

from src.backend.agents.entity_extractor import EntityExtractorAgent
from src.backend.agents.sentiment import SentimentAgent
from src.backend.agents.summarizer import SummarizerAgent
from src.backend.config import settings
from src.backend.utils.exceptions import OrchestrationError
from src.backend.utils.logger import get_logger

logger = get_logger(__name__)


class AgentOrchestrator:
    """Orchestrates multiple agents with sequential or parallel execution."""

    def __init__(self, text: str, mode: str = "sequential"):
        """
        Initialize orchestrator.

        Args:
            text: Text to process
            mode: Execution mode ("sequential" or "parallel")
        """
        self.text = text
        self.mode = mode
        self.agents = {
            "summarizer": SummarizerAgent(),
            "sentiment": SentimentAgent(),
            "entity_extractor": EntityExtractorAgent(),
        }

    async def execute(self) -> dict[str, Any]:
        """
        Execute all agents according to the specified mode.

        Returns:
            Dictionary with aggregated results and execution times

        Raises:
            OrchestrationError: If orchestration fails
        """
        start_time = time.time()
        logger.info(
            f"Starting agent orchestration in {self.mode} mode",
            extra={"orchestration_mode": self.mode},
        )

        try:
            if self.mode == "parallel":
                results = await self._execute_parallel()
            else:
                results = await self._execute_sequential()

            total_time = time.time() - start_time

            # Aggregate results
            aggregated = {
                "summary": results["summarizer"]["result_data"].get("summary", ""),
                "sentiment": results["sentiment"]["result_data"],
                "entities": results["entity_extractor"]["result_data"],
                "agent_results": [
                    {
                        "agent_name": "summarizer",
                        "result_data": results["summarizer"]["result_data"],
                        "execution_time": results["summarizer"]["execution_time"],
                        "status": results["summarizer"]["status"],
                    },
                    {
                        "agent_name": "sentiment",
                        "result_data": results["sentiment"]["result_data"],
                        "execution_time": results["sentiment"]["execution_time"],
                        "status": results["sentiment"]["status"],
                    },
                    {
                        "agent_name": "entity_extractor",
                        "result_data": results["entity_extractor"]["result_data"],
                        "execution_time": results["entity_extractor"]["execution_time"],
                        "status": results["entity_extractor"]["status"],
                    },
                ],
                "total_execution_time": total_time,
            }

            logger.info(
                f"Agent orchestration completed in {total_time:.2f}s",
                extra={
                    "orchestration_mode": self.mode,
                    "total_execution_time": total_time,
                },
            )

            return aggregated

        except Exception as e:
            error_msg = f"Orchestration failed: {str(e)}"
            logger.error(
                error_msg,
                exc_info=True,
                extra={"orchestration_mode": self.mode},
            )
            raise OrchestrationError(message=str(e), original_error=e) from e

    async def _execute_sequential(self) -> dict[str, dict[str, Any]]:
        """
        Execute agents sequentially.

        Returns:
            Dictionary with results from each agent
        """
        results: dict[str, dict[str, Any]] = {}

        for agent_name, agent in self.agents.items():
            agent_start = time.time()
            try:
                result_data = await agent.run(self.text)
                execution_time = time.time() - agent_start
                results[agent_name] = {
                    "result_data": result_data,
                    "execution_time": execution_time,
                    "status": "success",
                }
                logger.info(
                    f"Agent {agent_name} completed in {execution_time:.2f}s",
                    extra={"agent_name": agent_name},
                )
            except Exception as e:
                execution_time = time.time() - agent_start
                results[agent_name] = {
                    "result_data": {},
                    "execution_time": execution_time,
                    "status": "error",
                    "error_message": str(e),
                }
                logger.error(
                    f"Agent {agent_name} failed: {str(e)}",
                    extra={"agent_name": agent_name},
                )

        return results

    async def _execute_parallel(self) -> dict[str, dict[str, Any]]:
        """
        Execute agents in parallel using asyncio.

        Returns:
            Dictionary with results from each agent
        """
        async def run_agent(agent_name: str, agent: Any) -> tuple[str, dict[str, Any]]:
            """Run a single agent and return its result."""
            agent_start = time.time()
            try:
                result_data = await agent.run(self.text)
                execution_time = time.time() - agent_start
                logger.info(
                    f"Agent {agent_name} completed in {execution_time:.2f}s",
                    extra={"agent_name": agent_name},
                )
                return (
                    agent_name,
                    {
                        "result_data": result_data,
                        "execution_time": execution_time,
                        "status": "success",
                    },
                )
            except Exception as e:
                execution_time = time.time() - agent_start
                logger.error(
                    f"Agent {agent_name} failed: {str(e)}",
                    extra={"agent_name": agent_name},
                )
                return (
                    agent_name,
                    {
                        "result_data": {},
                        "execution_time": execution_time,
                        "status": "error",
                        "error_message": str(e),
                    },
                )

        # Execute all agents in parallel
        tasks = [
            run_agent(agent_name, agent)
            for agent_name, agent in self.agents.items()
        ]
        results_list = await asyncio.gather(*tasks)

        # Convert to dictionary
        results = {agent_name: result for agent_name, result in results_list}
        return results

