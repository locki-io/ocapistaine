"""
Translation Feature

Translates French citizen contributions to English for evaluation purposes.
"""

from pydantic import BaseModel

from app.providers import LLMProvider
from app.services.logging import MockupLogger

from .base import FeatureBase

_logger = MockupLogger("translation_feature")


TRANSLATION_PROMPT = """Translate the following French citizen contribution to English.
Keep the same structure, tone, and meaning.

Return a JSON object with this exact structure:
{{
    "observation": "translated factual observation",
    "ideas": "translated improvement ideas",
    "success": true
}}

French contribution:

CONSTAT FACTUEL:
{constat}

IDÉES D'AMÉLIORATION:
{idees}

Return ONLY the JSON object, no additional text."""


class TranslationResult(BaseModel):
    """Result of translation feature."""

    original_constat: str
    original_idees: str
    translated_constat: str
    translated_idees: str
    success: bool = True


class TranslationFeature(FeatureBase):
    """
    Feature for translating French contributions to English.

    Used for:
    - Evaluation by English-speaking judges
    - Cross-language comparison
    - Documentation purposes
    """

    @property
    def name(self) -> str:
        return "translation"

    @property
    def prompt(self) -> str:
        return TRANSLATION_PROMPT

    async def execute(
        self,
        provider: LLMProvider,
        system_prompt: str,
        constat: str,
        idees: str,
        **kwargs,
    ) -> TranslationResult:
        """
        Translate a French contribution to English.

        Args:
            provider: LLM provider.
            system_prompt: Agent persona prompt (can be empty).
            constat: French factual observation.
            idees: French improvement ideas.

        Returns:
            TranslationResult with translated texts.
        """
        user_prompt = self.format_prompt(constat=constat, idees=idees)

        _logger.debug(
            "TRANSLATION_REQUEST",
            constat_length=len(constat),
            idees_length=len(idees),
            provider=provider.__class__.__name__,
        )

        try:
            data = await self._get_json_response(
                provider=provider,
                system_prompt=system_prompt or "",
                user_prompt=user_prompt,
                temperature=0.3,
            )

            translated_constat = data.get("observation", "")
            translated_idees = data.get("ideas", "")
            success = data.get("success", True) and bool(translated_constat)

            _logger.info(
                "TRANSLATION_SUCCESS",
                constat_translated=bool(translated_constat),
                idees_translated=bool(translated_idees),
            )

            return TranslationResult(
                original_constat=constat,
                original_idees=idees,
                translated_constat=translated_constat,
                translated_idees=translated_idees,
                success=success,
            )

        except Exception as e:
            _logger.error("TRANSLATION_FEATURE_ERROR", error=str(e))
            # Return originals on error
            return TranslationResult(
                original_constat=constat,
                original_idees=idees,
                translated_constat=constat,
                translated_idees=idees,
                success=False,
            )
