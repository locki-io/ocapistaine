"""
Base Feature Class

Provides common functionality for all Forseti features.
"""

import json
from abc import ABC, abstractmethod
from typing import Any

from app.providers import LLMProvider, Message


class FeatureBase(ABC):
    """
    Abstract base class for Forseti features.

    Provides common functionality:
    - JSON response handling
    - Message construction
    - Error handling
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique feature identifier."""
        ...

    @property
    @abstractmethod
    def prompt(self) -> str:
        """Feature prompt template."""
        ...

    @abstractmethod
    async def execute(
        self,
        provider: LLMProvider,
        system_prompt: str,
        **kwargs,
    ) -> Any:
        """Execute the feature."""
        ...

    def format_prompt(self, **kwargs) -> str:
        """
        Format the prompt template with provided values.

        Args:
            **kwargs: Values to substitute in the template.

        Returns:
            Formatted prompt string.
        """
        return self.prompt.format(**kwargs)

    async def _get_json_response(
        self,
        provider: LLMProvider,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
    ) -> dict:
        """
        Get a JSON response from the provider.

        Args:
            provider: LLM provider to use.
            system_prompt: System prompt (persona).
            user_prompt: User prompt (formatted feature prompt).
            temperature: Sampling temperature (lower for more deterministic).

        Returns:
            Parsed JSON dict.

        Raises:
            json.JSONDecodeError: If response is not valid JSON.
        """
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ]

        response = await provider.complete(
            messages=messages,
            temperature=temperature,
            json_mode=True,
        )

        return json.loads(response.content)

    def _safe_parse(
        self,
        data: dict,
        defaults: dict,
    ) -> dict:
        """
        Safely extract values from response with defaults.

        Args:
            data: Parsed JSON response.
            defaults: Default values for missing keys.

        Returns:
            Dict with all expected keys.
        """
        result = defaults.copy()
        for key in defaults:
            if key in data:
                result[key] = data[key]
        return result
