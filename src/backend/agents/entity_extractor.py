"""Entity extraction agent using OpenAI API."""

import json
from typing import Any

from openai import AsyncOpenAI

from src.backend.agents.base_agent import BaseAgent
from src.backend.config import settings
from src.backend.utils.logger import get_logger

logger = get_logger(__name__)


class EntityExtractorAgent(BaseAgent):
    """Agent that extracts entities from text using OpenAI."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize entity extractor agent.

        Args:
            api_key: OpenAI API key (uses config if not provided)
        """
        super().__init__(name="entity_extractor", api_key=api_key)
        self.client = AsyncOpenAI(
            api_key=api_key or settings.OPENAI_API_KEY,
        )

    async def execute(self, text: str) -> dict[str, Any]:
        """
        Extract entities from the text.

        Args:
            text: Input text to extract entities from

        Returns:
            Dictionary with categorized entities

        Raises:
            AgentExecutionError: If entity extraction fails
        """
        system_prompt = """You are an expert in named entity recognition.
        Extract entities from the given text and categorize them into:
        - "persons": List of person names
        - "organizations": List of organization/company names
        - "locations": List of location/place names
        - "dates": List of dates mentioned (in ISO format YYYY-MM-DD if possible)
        
        Return your response as a JSON object with these four fields as arrays.
        If a category has no entities, return an empty array for that field."""

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract entities from this text:\n\n{text}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=500,
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from OpenAI")

            result = json.loads(content)

            # Validate and structure response
            entities = {
                "persons": self._validate_list(result.get("persons", []), "persons"),
                "organizations": self._validate_list(
                    result.get("organizations", []),
                    "organizations",
                ),
                "locations": self._validate_list(result.get("locations", []), "locations"),
                "dates": self._validate_list(result.get("dates", []), "dates"),
            }

            return entities

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from OpenAI: {str(e)}") from e
        except Exception as e:
            logger.error(
                f"OpenAI API error in entity extractor: {str(e)}",
                extra={"agent_name": self.name},
            )
            raise

    def _validate_list(self, value: Any, field_name: str) -> list[str]:
        """
        Validate that a value is a list of strings.

        Args:
            value: Value to validate
            field_name: Name of the field for error messages

        Returns:
            List of strings

        Raises:
            ValueError: If value is not a list of strings
        """
        if not isinstance(value, list):
            raise ValueError(f"{field_name} must be a list, got {type(value).__name__}")
        return [str(item) for item in value if item]

