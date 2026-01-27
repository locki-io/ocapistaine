# app/mockup/llm_mutations.py
"""
LLM-Based Mutation Generation

Uses Ollama (Mistral) to generate semantic mutations of contributions
for more realistic charter validation testing.

Mutation types:
- Paraphrase: Reword while preserving meaning (should remain valid)
- Subtle violation: Add borderline charter violations
- Orthographic: Generate realistic typos and errors
- Semantic shift: Change meaning slightly
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from app.providers.ollama import OllamaProvider
from app.providers.base import Message
from app.services import AgentLogger

_logger = AgentLogger("llm_mutations")


class MutationType(Enum):
    """Types of LLM-generated mutations."""
    PARAPHRASE = "paraphrase"
    SUBTLE_VIOLATION = "subtle_violation"
    ORTHOGRAPHIC = "orthographic"
    SEMANTIC_SHIFT = "semantic_shift"
    AGGRESSIVE = "aggressive"
    OFF_TOPIC = "off_topic"


# Prompts for different mutation types
MUTATION_PROMPTS = {
    MutationType.PARAPHRASE: """Tu es un assistant qui reformule des textes en français.

Reformule le texte suivant en gardant EXACTEMENT le même sens, mais avec des mots différents.
Le texte doit rester constructif, respectueux et pertinent pour Audierne.

Texte original:
{text}

Réponds UNIQUEMENT avec le texte reformulé, sans explication.""",

    MutationType.SUBTLE_VIOLATION: """Tu es un assistant qui modifie des textes pour les tests.

Modifie le texte suivant pour y ajouter une LÉGÈRE critique personnelle ou un ton légèrement négatif,
tout en gardant une apparence constructive. Le texte doit sembler acceptable mais contenir
une violation subtile de charte (critique implicite, ton condescendant, ou généralisation négative).

Texte original:
{text}

Réponds UNIQUEMENT avec le texte modifié, sans explication.""",

    MutationType.ORTHOGRAPHIC: """Tu es un assistant qui simule des erreurs de frappe.

Ajoute des erreurs orthographiques RÉALISTES au texte suivant:
- Lettres inversées (teh -> the)
- Lettres manquantes ou doublées
- Accents manquants ou incorrects
- Erreurs de conjugaison courantes

Le texte doit rester lisible mais contenir 3-5 erreurs naturelles.

Texte original:
{text}

Réponds UNIQUEMENT avec le texte avec erreurs, sans explication.""",

    MutationType.SEMANTIC_SHIFT: """Tu es un assistant qui modifie des textes pour les tests.

Modifie le texte suivant pour changer LÉGÈREMENT le sens:
- Garde le même sujet général
- Change une ou deux propositions clés
- Le résultat doit être différent mais plausible

Texte original:
{text}

Réponds UNIQUEMENT avec le texte modifié, sans explication.""",

    MutationType.AGGRESSIVE: """Tu es un assistant qui modifie des textes pour les tests.

Transforme le texte suivant pour le rendre agressif et non-constructif:
- Ajoute des critiques directes
- Utilise un ton accusateur
- Inclus des généralisations négatives
- Ajoute de l'emphase excessive (majuscules, ponctuation)

Le texte doit clairement violer une charte de contribution citoyenne.

Texte original:
{text}

Réponds UNIQUEMENT avec le texte modifié, sans explication.""",

    MutationType.OFF_TOPIC: """Tu es un assistant qui modifie des textes pour les tests.

Modifie le texte suivant pour le rendre hors-sujet par rapport à Audierne:
- Garde le début du texte original
- Dévie vers un sujet national ou sans rapport (politique nationale, autre ville, sujet personnel)
- Le texte doit commencer de manière pertinente puis dériver

Texte original:
{text}

Réponds UNIQUEMENT avec le texte modifié, sans explication.""",
}


@dataclass
class MutationResult:
    """Result of an LLM mutation."""
    original: str
    mutated: str
    mutation_type: MutationType
    success: bool
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original": self.original,
            "mutated": self.mutated,
            "mutation_type": self.mutation_type.value,
            "success": self.success,
            "error": self.error,
        }


class LLMMutator:
    """
    LLM-based text mutator using Ollama (Mistral).

    Generates semantic mutations for contribution testing.
    """

    def __init__(
        self,
        model: str = "mistral:latest",
        host: str | None = None,
        timeout: float = 60.0,
    ):
        """
        Initialize the LLM mutator.

        Args:
            model: Ollama model name (default: mistral:latest)
            host: Ollama host URL (default: from config)
            timeout: Request timeout in seconds
        """
        self._provider = OllamaProvider(
            model=model,
            host=host,
            timeout=timeout,
        )
        self._logger = AgentLogger("llm_mutator")

    async def health_check(self) -> bool:
        """Check if Ollama is available."""
        return await self._provider.health_check()

    async def mutate(
        self,
        text: str,
        mutation_type: MutationType,
        temperature: float = 0.7,
    ) -> MutationResult:
        """
        Generate a mutation of the text.

        Args:
            text: Original text to mutate
            mutation_type: Type of mutation to apply
            temperature: LLM temperature (higher = more creative)

        Returns:
            MutationResult with original and mutated text
        """
        prompt_template = MUTATION_PROMPTS.get(mutation_type)
        if not prompt_template:
            return MutationResult(
                original=text,
                mutated=text,
                mutation_type=mutation_type,
                success=False,
                error=f"Unknown mutation type: {mutation_type}",
            )

        prompt = prompt_template.format(text=text)

        try:
            messages = [
                Message(role="user", content=prompt),
            ]

            response = await self._provider.complete(
                messages=messages,
                temperature=temperature,
                max_tokens=len(text) * 2,  # Allow some expansion
            )

            mutated = response.content.strip()

            # Clean up common LLM artifacts
            mutated = self._clean_response(mutated)

            self._logger.debug(
                "MUTATION",
                type=mutation_type.value,
                original_len=len(text),
                mutated_len=len(mutated),
            )

            return MutationResult(
                original=text,
                mutated=mutated,
                mutation_type=mutation_type,
                success=True,
            )

        except Exception as e:
            self._logger.error("MUTATION_ERROR", type=mutation_type.value, error=str(e))
            return MutationResult(
                original=text,
                mutated=text,
                mutation_type=mutation_type,
                success=False,
                error=str(e),
            )

    def _clean_response(self, text: str) -> str:
        """Clean common LLM response artifacts."""
        # Remove common prefixes
        prefixes_to_remove = [
            "Voici le texte reformulé:",
            "Voici le texte modifié:",
            "Texte reformulé:",
            "Texte modifié:",
            "Réponse:",
        ]
        for prefix in prefixes_to_remove:
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].strip()

        # Remove quotes if the entire response is quoted
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        if text.startswith("«") and text.endswith("»"):
            text = text[1:-1].strip()

        return text.strip()

    async def mutate_batch(
        self,
        text: str,
        mutation_types: List[MutationType],
        temperature: float = 0.7,
    ) -> List[MutationResult]:
        """
        Generate multiple mutations of the same text.

        Args:
            text: Original text
            mutation_types: List of mutation types to apply
            temperature: LLM temperature

        Returns:
            List of MutationResults
        """
        tasks = [
            self.mutate(text, mt, temperature)
            for mt in mutation_types
        ]
        return await asyncio.gather(*tasks)

    async def generate_variation_series(
        self,
        text: str,
        num_variations: int = 5,
        include_violations: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Generate a series of variations with progressive mutations.

        Args:
            text: Original text
            num_variations: Number of variations to generate
            include_violations: Whether to include violation mutations

        Returns:
            List of variation dictionaries
        """
        variations = []

        # Define mutation sequence based on num_variations
        if include_violations:
            # Mix of valid and invalid mutations
            mutation_sequence = [
                MutationType.PARAPHRASE,      # Valid
                MutationType.ORTHOGRAPHIC,    # Valid (typos)
                MutationType.SEMANTIC_SHIFT,  # Borderline
                MutationType.SUBTLE_VIOLATION,  # Invalid (subtle)
                MutationType.AGGRESSIVE,      # Invalid (obvious)
                MutationType.OFF_TOPIC,       # Invalid
            ]
        else:
            # Only valid mutations
            mutation_sequence = [
                MutationType.PARAPHRASE,
                MutationType.ORTHOGRAPHIC,
                MutationType.SEMANTIC_SHIFT,
                MutationType.PARAPHRASE,
                MutationType.ORTHOGRAPHIC,
            ]

        # Select mutations based on num_variations
        selected_mutations = []
        for i in range(num_variations):
            idx = i % len(mutation_sequence)
            selected_mutations.append(mutation_sequence[idx])

        # Generate mutations
        results = await self.mutate_batch(text, selected_mutations)

        for i, result in enumerate(results):
            # Determine expected validity based on mutation type
            expected_valid = result.mutation_type in [
                MutationType.PARAPHRASE,
                MutationType.ORTHOGRAPHIC,
            ]
            if result.mutation_type == MutationType.SEMANTIC_SHIFT:
                expected_valid = None  # Borderline, unknown

            variations.append({
                "index": i,
                "text": result.mutated if result.success else text,
                "mutation_type": result.mutation_type.value,
                "expected_valid": expected_valid,
                "success": result.success,
                "error": result.error,
            })

        return variations


# Convenience functions for synchronous usage
def _run_async(coro):
    """Run async function in sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're in an async context, create a new task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def mutate_with_llm(
    text: str,
    mutation_type: str | MutationType = MutationType.PARAPHRASE,
    model: str = "mistral:latest",
) -> MutationResult:
    """
    Synchronous wrapper for LLM mutation.

    Args:
        text: Text to mutate
        mutation_type: Type of mutation (string or MutationType)
        model: Ollama model to use

    Returns:
        MutationResult
    """
    if isinstance(mutation_type, str):
        mutation_type = MutationType(mutation_type)

    mutator = LLMMutator(model=model)
    return _run_async(mutator.mutate(text, mutation_type))


def generate_llm_variations(
    text: str,
    num_variations: int = 5,
    include_violations: bool = True,
    model: str = "mistral:latest",
) -> List[Dict[str, Any]]:
    """
    Synchronous wrapper for generating variation series.

    Args:
        text: Original text
        num_variations: Number of variations
        include_violations: Include violation mutations
        model: Ollama model to use

    Returns:
        List of variation dictionaries
    """
    mutator = LLMMutator(model=model)
    return _run_async(
        mutator.generate_variation_series(text, num_variations, include_violations)
    )


async def check_ollama_available(model: str = "mistral:latest") -> bool:
    """Check if Ollama is available with the specified model."""
    mutator = LLMMutator(model=model)
    return await mutator.health_check()
