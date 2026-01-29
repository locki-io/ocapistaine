# app/prompts/registry.py
"""
Prompt Registry - Central Access Point for All Prompts

Provides unified access to prompts with fallback chain:
1. Vaettir MCP (future) - Remote, versioned
2. Opik Prompt Library - Versioned, experiment-linked
3. Local Python files - Development fallback

Usage:
    from app.prompts import get_registry

    registry = get_registry()
    prompt = registry.get_prompt("forseti.charter_validation")
    formatted = registry.format_prompt("forseti.charter_validation", title="...", body="...")
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import re

from app.prompts.local import LOCAL_PROMPTS
from app.services import AgentLogger

_logger = AgentLogger("prompt_registry")


@dataclass
class PromptInfo:
    """Metadata about a prompt."""

    name: str
    template: str
    type: str  # "system" or "user"
    variables: List[str]
    description: str
    source: str  # "local", "opik", "mcp"
    version: Optional[str] = None
    language: Optional[str] = None
    format: str = "text"  # "text" or "chat"
    messages: List[Dict[str, str]] = field(default_factory=list)
    opik_name: Optional[str] = None

    def get_messages(self, **variables) -> List[Dict[str, str]]:
        """
        Get formatted messages for chat format.

        Args:
            **variables: Variables to substitute (title, body, etc.)

        Returns:
            List of message dicts with 'role' and 'content'
        """
        if not self.messages:
            # Convert text template to single user message
            return [{"role": self.type, "content": self.format_template(**variables)}]

        formatted = []
        for msg in self.messages:
            content = msg.get("content", "")
            # Replace Mustache variables {{input.var}} and {{var}}
            for key, value in variables.items():
                content = content.replace(f"{{{{input.{key}}}}}", str(value))
                content = content.replace(f"{{{{{key}}}}}", str(value))
            formatted.append({
                "role": msg.get("role", "user"),
                "content": content,
            })
        return formatted

    def format_template(self, **variables) -> str:
        """
        Format the template with variables.

        Supports both Mustache ({{var}}) and Python ({var}) formats.
        """
        content = self.template

        # Replace Mustache variables first
        for key, value in variables.items():
            content = content.replace(f"{{{{input.{key}}}}}", str(value))
            content = content.replace(f"{{{{{key}}}}}", str(value))

        # Then try Python format for any remaining
        try:
            content = content.format(**variables)
        except KeyError:
            pass  # Some variables not provided, that's OK

        return content


class PromptRegistry:
    """
    Central registry for all prompts with versioning support.

    Supports multiple backends:
    - Local Python files (always available)
    - Opik Prompt Library (when configured)
    - Vaettir MCP (future)
    """

    def __init__(self, opik_enabled: bool = True):
        """
        Initialize the prompt registry.

        Args:
            opik_enabled: Whether to try Opik for prompt retrieval
        """
        self._opik_enabled = opik_enabled
        self._opik_client = None
        self._cache: Dict[str, PromptInfo] = {}
        self._init_opik()

    def _init_opik(self):
        """Initialize Opik client if available."""
        if not self._opik_enabled:
            return

        try:
            import opik

            self._opik_client = opik.Opik()
            _logger.info("OPIK_INIT_SUCCESS")
        except ImportError:
            _logger.warning("OPIK_NOT_INSTALLED", message="pip install opik")
            self._opik_client = None
        except Exception as e:
            _logger.warning("OPIK_INIT_FAILED", error=str(e))
            self._opik_client = None

    @property
    def opik_available(self) -> bool:
        """Check if Opik is available."""
        return self._opik_client is not None

    def get_prompt(
        self,
        name: str,
        version: Optional[str] = None,
    ) -> PromptInfo:
        """
        Get a prompt by name, optionally specific version.

        Args:
            name: Prompt name (e.g., "forseti.charter_validation")
            version: Optional Opik commit ID or "latest"

        Returns:
            PromptInfo with template and metadata
        """
        cache_key = f"{name}:{version or 'latest'}"

        # Check cache first
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try Opik first (if enabled and available)
        if self._opik_client and version != "local":
            prompt_info = self._get_from_opik(name, version)
            if prompt_info:
                self._cache[cache_key] = prompt_info
                return prompt_info

        # Fallback to local
        prompt_info = self._get_from_local(name)
        if prompt_info:
            self._cache[cache_key] = prompt_info
            return prompt_info

        # Not found
        _logger.error("PROMPT_NOT_FOUND", name=name)
        raise KeyError(f"Prompt not found: {name}")

    def _get_from_opik(
        self,
        name: str,
        version: Optional[str] = None,
    ) -> Optional[PromptInfo]:
        """Retrieve prompt from Opik library."""
        try:
            if version:
                opik_prompt = self._opik_client.get_prompt(name=name, commit=version)
            else:
                opik_prompt = self._opik_client.get_prompt(name=name)

            # Extract metadata
            metadata = getattr(opik_prompt, "metadata", {}) or {}

            return PromptInfo(
                name=name,
                template=opik_prompt.prompt,
                type=metadata.get("type", "user"),
                variables=metadata.get("variables", []),
                description=metadata.get("description", ""),
                source="opik",
                version=getattr(opik_prompt, "commit", None),
                language=metadata.get("language"),
            )

        except Exception as e:
            _logger.debug("OPIK_FETCH_FAILED", name=name, error=str(e))
            return None

    def _get_from_local(self, name: str) -> Optional[PromptInfo]:
        """Retrieve prompt from local Python/JSON files."""
        if name not in LOCAL_PROMPTS:
            return None

        prompt_data = LOCAL_PROMPTS[name]

        return PromptInfo(
            name=name,
            template=prompt_data.get("template", ""),
            type=prompt_data.get("type", "user"),
            variables=prompt_data.get("variables", []),
            description=prompt_data.get("description", ""),
            source="local",
            version=prompt_data.get("opik_commit"),
            language=prompt_data.get("language"),
            format=prompt_data.get("format", "text"),
            messages=prompt_data.get("messages", []),
            opik_name=prompt_data.get("opik_name"),
        )

    def format_prompt(
        self,
        name: str,
        version: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Get and format a prompt with variables.

        Args:
            name: Prompt name
            version: Optional version
            **kwargs: Variables to substitute

        Returns:
            Formatted prompt string
        """
        prompt_info = self.get_prompt(name, version)
        return prompt_info.format_template(**kwargs)

    def get_messages(
        self,
        name: str,
        version: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, str]]:
        """
        Get formatted messages for chat-based prompts.

        Args:
            name: Prompt name
            version: Optional version
            **kwargs: Variables to substitute

        Returns:
            List of message dicts with 'role' and 'content'
        """
        prompt_info = self.get_prompt(name, version)
        return prompt_info.get_messages(**kwargs)

    def list_prompts(self, prefix: Optional[str] = None) -> List[str]:
        """
        List available prompt names.

        Args:
            prefix: Optional prefix filter (e.g., "forseti.")

        Returns:
            List of prompt names
        """
        names = list(LOCAL_PROMPTS.keys())

        if prefix:
            names = [n for n in names if n.startswith(prefix)]

        return sorted(names)

    def get_prompt_template(
        self,
        name: str,
        version: Optional[str] = None,
    ) -> str:
        """
        Get just the prompt template string.

        Args:
            name: Prompt name
            version: Optional version

        Returns:
            Template string
        """
        return self.get_prompt(name, version).template

    def clear_cache(self):
        """Clear the prompt cache."""
        self._cache.clear()
        _logger.info("CACHE_CLEARED")


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_registry: Optional[PromptRegistry] = None


def get_registry(opik_enabled: bool = True) -> PromptRegistry:
    """
    Get or create the global prompt registry.

    Args:
        opik_enabled: Whether to enable Opik integration

    Returns:
        PromptRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = PromptRegistry(opik_enabled=opik_enabled)
    return _registry


def get_prompt(name: str, version: Optional[str] = None) -> str:
    """
    Convenience function to get a prompt template.

    Args:
        name: Prompt name
        version: Optional version

    Returns:
        Prompt template string
    """
    return get_registry().get_prompt_template(name, version)


def format_prompt(name: str, version: Optional[str] = None, **kwargs) -> str:
    """
    Convenience function to format a prompt.

    Args:
        name: Prompt name
        version: Optional version
        **kwargs: Variables

    Returns:
        Formatted prompt string
    """
    return get_registry().format_prompt(name, version, **kwargs)
