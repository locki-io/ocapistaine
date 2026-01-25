"""
Base Agent Framework

Provides the foundational agent class with feature composition support.
"""

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from app.providers import LLMProvider, Message, get_provider


@runtime_checkable
class AgentFeature(Protocol):
    """
    Protocol defining the interface for agent features.

    Features are composable units of functionality that can be
    registered with an agent. Each feature has:
    - name: Unique identifier
    - prompt: The prompt template for this feature
    - execute: Method to run the feature
    """

    @property
    def name(self) -> str:
        """Unique feature identifier."""
        ...

    @property
    def prompt(self) -> str:
        """Feature prompt template."""
        ...

    async def execute(
        self,
        provider: LLMProvider,
        system_prompt: str,
        **kwargs,
    ) -> Any:
        """
        Execute the feature.

        Args:
            provider: LLM provider to use.
            system_prompt: Agent's system/persona prompt.
            **kwargs: Feature-specific arguments.

        Returns:
            Feature-specific result.
        """
        ...


class BaseAgent(ABC):
    """
    Base class for all agents with feature composition.

    Agents combine:
    - A persona (system prompt defining identity)
    - An LLM provider (for generating completions)
    - Features (composable functionality units)

    Subclasses must implement:
    - persona_prompt: The agent's identity/role description

    Example:
        class MyAgent(BaseAgent):
            @property
            def persona_prompt(self) -> str:
                return "You are a helpful assistant..."

            def __init__(self):
                super().__init__()
                self.register_feature(MyFeature())
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        provider_name: str | None = None,
    ):
        """
        Initialize the agent.

        Args:
            provider: Optional LLM provider instance.
            provider_name: Optional provider name (uses default if not specified).
        """
        self._provider = provider or get_provider(provider_name)
        self._features: dict[str, AgentFeature] = {}

    @property
    @abstractmethod
    def persona_prompt(self) -> str:
        """
        Agent's persona/identity system prompt.

        This defines WHO the agent is, not WHAT it does.
        Feature prompts define specific functionality.
        """
        ...

    @property
    def provider(self) -> LLMProvider:
        """Get the agent's LLM provider."""
        return self._provider

    @property
    def features(self) -> dict[str, AgentFeature]:
        """Get all registered features."""
        return self._features.copy()

    def register_feature(self, feature: AgentFeature) -> None:
        """
        Register a feature with the agent.

        Args:
            feature: Feature instance to register.

        Raises:
            ValueError: If feature with same name already exists.
        """
        if feature.name in self._features:
            raise ValueError(f"Feature '{feature.name}' already registered")
        self._features[feature.name] = feature

    def unregister_feature(self, name: str) -> None:
        """
        Remove a feature from the agent.

        Args:
            name: Feature name to remove.
        """
        self._features.pop(name, None)

    def has_feature(self, name: str) -> bool:
        """Check if a feature is registered."""
        return name in self._features

    async def execute_feature(
        self,
        feature_name: str,
        **kwargs,
    ) -> Any:
        """
        Execute a specific feature.

        Args:
            feature_name: Name of the feature to execute.
            **kwargs: Arguments passed to the feature.

        Returns:
            Feature execution result.

        Raises:
            KeyError: If feature is not registered.
        """
        if feature_name not in self._features:
            raise KeyError(f"Feature '{feature_name}' not registered")

        feature = self._features[feature_name]
        return await feature.execute(
            provider=self._provider,
            system_prompt=self.persona_prompt,
            **kwargs,
        )

    async def execute_all(
        self,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Execute all registered features.

        Args:
            **kwargs: Arguments passed to all features.

        Returns:
            Dict mapping feature names to their results.
        """
        results = {}
        for name, feature in self._features.items():
            try:
                results[name] = await feature.execute(
                    provider=self._provider,
                    system_prompt=self.persona_prompt,
                    **kwargs,
                )
            except Exception as e:
                results[name] = {"error": str(e)}
        return results

    async def complete(
        self,
        user_message: str,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> str:
        """
        Simple completion using the agent's persona.

        Args:
            user_message: User's message.
            temperature: Sampling temperature.
            json_mode: If True, request JSON output.

        Returns:
            Agent's response as string.
        """
        messages = [
            Message(role="system", content=self.persona_prompt),
            Message(role="user", content=user_message),
        ]
        response = await self._provider.complete(
            messages=messages,
            temperature=temperature,
            json_mode=json_mode,
        )
        return response.content
