"""Sentiment analyzer agent using OpenAI API."""

import json
from typing import Any

from openai import AsyncOpenAI

from src.backend.agents.base_agent import BaseAgent
from src.backend.config import settings
from src.backend.utils.logger import get_logger

logger = get_logger(__name__)


class SentimentAgent(BaseAgent):
    """Agent that analyzes sentiment using OpenAI."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize sentiment agent.

        Args:
            api_key: OpenAI API key (uses config if not provided)
        """
        super().__init__(name="sentiment", api_key=api_key)
        self.client = AsyncOpenAI(
            api_key=api_key or settings.OPENAI_API_KEY,
        )

    async def execute(self, text: str) -> dict[str, Any]:
        """
        Analyze sentiment of the text.

        Args:
            text: Input text to analyze

        Returns:
            Dictionary with sentiment and confidence score

        Raises:
            AgentExecutionError: If sentiment analysis fails
        """
        system_prompt = """You are a sentiment analysis expert.
        Analyze the sentiment of the given text and classify it as:
        - "positive" for positive sentiment
        - "negative" for negative sentiment  
        - "neutral" for neutral sentiment
        
        Also provide a confidence score between 0.0 and 1.0.
        
        Return your response as a JSON object with:
        - "sentiment": one of "positive", "negative", or "neutral"
        - "confidence": a float between 0.0 and 1.0"""

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Analyze the sentiment of this text:\n\n{text}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=100,
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from OpenAI")

            result = json.loads(content)
            sentiment = result.get("sentiment", "").lower()
            confidence = float(result.get("confidence", 0.0))

            # Validate sentiment
            if sentiment not in ["positive", "negative", "neutral"]:
                raise ValueError(f"Invalid sentiment value: {sentiment}")

            # Validate confidence
            if not 0.0 <= confidence <= 1.0:
                raise ValueError(f"Confidence must be between 0.0 and 1.0, got {confidence}")

            return {
                "sentiment": sentiment,
                "confidence": round(confidence, 3),
            }

        except (ValueError, KeyError) as e:
            logger.error(
                f"Invalid response format from OpenAI: {str(e)}",
                extra={"agent_name": self.name},
            )
            raise ValueError(f"Invalid response format: {str(e)}") from e
        except Exception as e:
            logger.error(
                f"OpenAI API error in sentiment analyzer: {str(e)}",
                extra={"agent_name": self.name},
            )
            raise

