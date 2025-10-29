"""Summarizer agent using OpenAI API."""

import json
from typing import Any

from openai import AsyncOpenAI

from src.backend.agents.base_agent import BaseAgent
from src.backend.config import settings
from src.backend.utils.logger import get_logger

logger = get_logger(__name__)


class SummarizerAgent(BaseAgent):
    """Agent that summarizes text using OpenAI."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize summarizer agent.

        Args:
            api_key: OpenAI API key (uses config if not provided)
        """
        super().__init__(name="summarizer", api_key=api_key)
        self.client = AsyncOpenAI(
            api_key=api_key or settings.OPENAI_API_KEY,
        )

    async def execute(self, text: str) -> dict[str, Any]:
        """
        Generate a concise summary of the text.

        Args:
            text: Input text to summarize

        Returns:
            Dictionary with summary text

        Raises:
            AgentExecutionError: If summarization fails
        """
        system_prompt = """You are a professional text summarizer. 
        Create concise, informative summaries that capture the key points of the text.
        Maximum length: 200 words.
        Return your response as a JSON object with a "summary" field containing the summary text."""

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Please summarize the following text:\n\n{text}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=300,
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from OpenAI")

            result = json.loads(content)
            summary = result.get("summary", "").strip()

            if not summary:
                raise ValueError("Summary field is empty in response")

            # Ensure summary is within 200 words
            words = summary.split()
            if len(words) > 200:
                summary = " ".join(words[:200])
                logger.warning(
                    "Summary exceeded 200 words, truncated",
                    extra={"agent_name": self.name},
                )

            return {"summary": summary}

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from OpenAI: {str(e)}") from e
        except Exception as e:
            logger.error(
                f"OpenAI API error in summarizer: {str(e)}",
                extra={"agent_name": self.name},
            )
            raise

