"""
Anonymization Feature

LLM-based anonymization of PII (names, emails, phones) in documents.
Extracts non-PII keywords (organizations, places) for theme analysis.
"""

from app.providers import LLMProvider
from app.services.logging import MockupLogger

from ..models import AnonymizationResult, DetectedEntity, EntityType
from .base import FeatureBase

# Import prompt from central location
from app.prompts.local.forseti import ANONYMIZATION_PROMPT

_logger = MockupLogger("anonymization_feature")


class AnonymizationFeature(FeatureBase):
    """
    Feature for LLM-based document anonymization.

    Anonymizes:
    - Personal names → [PERSONNE_N]
    - Email addresses → [EMAIL_N]
    - Phone numbers → [TELEPHONE_N]
    - Postal addresses → [ADRESSE_N]

    Extracts as keywords (not anonymized):
    - Organization names
    - Place names
    - Public institutions
    """

    @property
    def name(self) -> str:
        return "anonymization"

    @property
    def prompt(self) -> str:
        return ANONYMIZATION_PROMPT

    async def execute(
        self,
        provider: LLMProvider,
        system_prompt: str,
        text: str,
        **kwargs,
    ) -> AnonymizationResult:
        """
        Anonymize PII in a document.

        Args:
            provider: LLM provider.
            system_prompt: Agent persona prompt (can be empty).
            text: Document text to anonymize.

        Returns:
            AnonymizationResult with anonymized text and entity mappings.
        """
        user_prompt = self.format_prompt(text=text)

        _logger.debug(
            "ANONYMIZATION_REQUEST",
            text_length=len(text),
            provider=provider.__class__.__name__,
        )

        try:
            data = await self._get_json_response(
                provider=provider,
                system_prompt=system_prompt or "",
                user_prompt=user_prompt,
                temperature=0.2,  # Low temperature for consistent anonymization
            )

            # Parse entities
            entities = []
            for entity_data in data.get("entities", []):
                entity_type_str = entity_data.get("entity_type", "person")
                try:
                    entity_type = EntityType(entity_type_str)
                except ValueError:
                    entity_type = EntityType.PERSON

                entities.append(
                    DetectedEntity(
                        original=entity_data.get("original", ""),
                        anonymized=entity_data.get("anonymized", ""),
                        entity_type=entity_type,
                        start_pos=entity_data.get("start_pos"),
                        end_pos=entity_data.get("end_pos"),
                    )
                )

            result = AnonymizationResult(
                original_text=text,
                anonymized_text=data.get("anonymized_text", text),
                entities=entities,
                entity_mapping=data.get("entity_mapping", {}),
                keywords_extracted=data.get("keywords_extracted", []),
                reasoning=data.get("reasoning", ""),
            )

            _logger.info(
                "ANONYMIZATION_COMPLETE",
                entities_found=len(entities),
                keywords_extracted=len(result.keywords_extracted),
            )

            return result

        except Exception as e:
            _logger.error(
                "ANONYMIZATION_ERROR",
                error=str(e),
                text_preview=text[:100] if text else "",
            )
            # Return original text on error (fail open)
            return AnonymizationResult(
                original_text=text,
                anonymized_text=text,
                entities=[],
                entity_mapping={},
                keywords_extracted=[],
                reasoning=f"Anonymization error: {e}",
            )
