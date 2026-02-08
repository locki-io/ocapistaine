# app/mockup/anonymizer.py
"""
Document Anonymization Module

Provides transcript anonymization (regex-based) and orchestration for
LLM-based anonymization via Forseti.

Features:
- Transcript detection and speaker name replacement (Speaker_1, Speaker_2...)
- Fuzzy name matching for spelling variations
- Inline mention replacement
- Document type auto-detection
- Opik PII guardrail integration for validation
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from app.mockup.levenshtein import levenshtein_ratio
from app.services.logging import MockupLogger

_logger = MockupLogger("anonymizer")


class DocumentType(Enum):
    """Type of document for anonymization routing."""

    TRANSCRIPT_NAMED = "transcript_named"  # Timestamp + real names
    TRANSCRIPT_ANONYMOUS = "transcript_anonymous"  # Already anonymized (Speaker 1, etc.)
    GENERAL = "general"  # General document, needs LLM-based anonymization


@dataclass
class SpeakerMapping:
    """Mapping between original speaker name and anonymized identifier."""

    original: str  # "Florent Lardic"
    normalized: str  # "florent_lardic"
    anonymized: str  # "Speaker_1"
    variations: List[str] = field(default_factory=list)  # ["Florent Lardic", "Florent"]
    occurrence_count: int = 0


@dataclass
class TranscriptAnonymizationResult:
    """Result of transcript anonymization."""

    original_text: str
    anonymized_text: str
    document_type: DocumentType
    speaker_mappings: Dict[str, SpeakerMapping] = field(default_factory=dict)
    header_replacements: int = 0
    inline_replacements: int = 0

    @property
    def total_replacements(self) -> int:
        return self.header_replacements + self.inline_replacements

    @property
    def speaker_count(self) -> int:
        return len(self.speaker_mappings)

    def to_dict(self) -> dict:
        return {
            "document_type": self.document_type.value,
            "speaker_count": self.speaker_count,
            "header_replacements": self.header_replacements,
            "inline_replacements": self.inline_replacements,
            "total_replacements": self.total_replacements,
            "speaker_mappings": {
                k: {
                    "original": v.original,
                    "anonymized": v.anonymized,
                    "variations": v.variations,
                    "occurrence_count": v.occurrence_count,
                }
                for k, v in self.speaker_mappings.items()
            },
        }


class TranscriptAnonymizer:
    """
    Anonymizes transcripts with timestamped speaker names.

    Detects patterns like:
        00:00:00 Florent Lardic
        00:05:23 Malika Redaouia

    And replaces with:
        00:00:00 Speaker_1
        00:05:23 Speaker_2

    Also handles inline mentions ("comme Florent le disait" -> "comme Speaker_1 le disait").
    """

    # Timestamp pattern: HH:MM:SS at start of line followed by speaker name
    TIMESTAMP_PATTERN = re.compile(
        r"^(\d{2}:\d{2}:\d{2})\s+(.+?)$", re.MULTILINE
    )

    # Already anonymized patterns (don't need processing)
    ANONYMOUS_SPEAKER_PATTERNS = [
        re.compile(r"^Speaker\s*\d+", re.IGNORECASE),
        re.compile(r"^Intervenant\s*\d+", re.IGNORECASE),
        re.compile(r"^Élu\s+(principal|secondaire|\d+)", re.IGNORECASE),
        re.compile(r"^Elu\s+(principal|secondaire|\d+)", re.IGNORECASE),
        re.compile(r"^Participant\s*\d+", re.IGNORECASE),
    ]

    # Minimum timestamp occurrences to classify as transcript
    MIN_TIMESTAMP_COUNT = 3

    def __init__(self, similarity_threshold: float = 0.85):
        """
        Initialize anonymizer.

        Args:
            similarity_threshold: Threshold for fuzzy name matching (0.0-1.0).
                                  Higher = stricter matching.
        """
        self.similarity_threshold = similarity_threshold
        self._speaker_index = 0
        self._speaker_map: Dict[str, SpeakerMapping] = {}

    def detect_document_type(self, text: str) -> DocumentType:
        """
        Detect the type of document for anonymization routing.

        Args:
            text: Document text to analyze.

        Returns:
            DocumentType indicating how to process the document.
        """
        matches = list(self.TIMESTAMP_PATTERN.finditer(text))

        if len(matches) < self.MIN_TIMESTAMP_COUNT:
            return DocumentType.GENERAL

        # Check if speakers are already anonymized
        sample_speakers = [m.group(2).strip() for m in matches[:10]]
        anonymous_count = 0

        for speaker in sample_speakers:
            for pattern in self.ANONYMOUS_SPEAKER_PATTERNS:
                if pattern.match(speaker):
                    anonymous_count += 1
                    break

        # If majority are already anonymous, no need to process
        if anonymous_count > len(sample_speakers) * 0.7:
            return DocumentType.TRANSCRIPT_ANONYMOUS

        return DocumentType.TRANSCRIPT_NAMED

    def _normalize_name(self, name: str) -> str:
        """Normalize a name for comparison (lowercase, single spaces, no accents)."""
        import unicodedata

        # Remove accents
        normalized = unicodedata.normalize("NFKD", name)
        normalized = "".join(c for c in normalized if not unicodedata.combining(c))

        # Lowercase and normalize whitespace
        normalized = " ".join(normalized.lower().split())

        return normalized

    def _find_matching_speaker(self, name: str) -> Optional[str]:
        """
        Find if a name matches an existing speaker (exact or fuzzy).

        Args:
            name: Speaker name to look up.

        Returns:
            Normalized key of matching speaker, or None if no match.
        """
        normalized = self._normalize_name(name)

        # Exact match on normalized name
        if normalized in self._speaker_map:
            return normalized

        # Fuzzy match against existing speakers
        for key, mapping in self._speaker_map.items():
            # Check against original and variations
            names_to_check = [mapping.normalized] + [
                self._normalize_name(v) for v in mapping.variations
            ]

            for existing_name in names_to_check:
                similarity = levenshtein_ratio(normalized, existing_name)
                if similarity >= self.similarity_threshold:
                    return key

            # Also check first name only for single-word matches
            if " " not in normalized:
                # Check if this could be a first name match
                first_name = mapping.normalized.split()[0] if mapping.normalized else ""
                if first_name and levenshtein_ratio(normalized, first_name) >= 0.9:
                    return key

        return None

    def _get_or_create_speaker(self, name: str) -> SpeakerMapping:
        """
        Get existing speaker mapping or create a new one.

        Args:
            name: Speaker name.

        Returns:
            SpeakerMapping for this speaker.
        """
        existing_key = self._find_matching_speaker(name)

        if existing_key:
            mapping = self._speaker_map[existing_key]
            # Add variation if not already tracked
            if name not in mapping.variations and name != mapping.original:
                mapping.variations.append(name)
            mapping.occurrence_count += 1
            return mapping

        # Create new speaker
        self._speaker_index += 1
        normalized = self._normalize_name(name)
        mapping = SpeakerMapping(
            original=name,
            normalized=normalized,
            anonymized=f"Speaker_{self._speaker_index}",
            variations=[],
            occurrence_count=1,
        )
        self._speaker_map[normalized] = mapping
        return mapping

    def _extract_speakers(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Extract all speaker occurrences from timestamp headers.

        Returns:
            List of (speaker_name, start_pos, end_pos) tuples.
        """
        speakers = []
        for match in self.TIMESTAMP_PATTERN.finditer(text):
            speaker_name = match.group(2).strip()
            # Calculate position of speaker name within the match
            full_match = match.group(0)
            timestamp = match.group(1)
            speaker_start = match.start() + len(timestamp) + 1  # +1 for space
            speaker_end = match.end()
            speakers.append((speaker_name, speaker_start, speaker_end))
        return speakers

    def _replace_inline_mentions(
        self, text: str, speaker_map: Dict[str, SpeakerMapping]
    ) -> Tuple[str, int]:
        """
        Replace inline mentions of speaker names.

        Handles patterns like:
        - "comme Florent le disait" -> "comme Speaker_1 le disait"
        - "Florent et Karine" -> "Speaker_1 et Speaker_2"

        Args:
            text: Text with anonymized headers but original inline mentions.
            speaker_map: Map of normalized names to speaker mappings.

        Returns:
            Tuple of (processed_text, replacement_count).
        """
        replacement_count = 0

        # Build list of all name variations to replace
        replacements: List[Tuple[str, str]] = []

        for mapping in speaker_map.values():
            # Add original name
            replacements.append((mapping.original, mapping.anonymized))

            # Add variations
            for variation in mapping.variations:
                replacements.append((variation, mapping.anonymized))

            # Add first name only (for common references like "comme Florent disait")
            first_name = mapping.original.split()[0] if mapping.original else ""
            if first_name and len(first_name) > 2:
                replacements.append((first_name, mapping.anonymized))

        # Sort by length (longest first) to avoid partial replacements
        replacements.sort(key=lambda x: len(x[0]), reverse=True)

        # Perform replacements (case-insensitive, word boundaries)
        for original, anonymized in replacements:
            # Use word boundaries to avoid replacing parts of words
            pattern = re.compile(
                rf"\b{re.escape(original)}\b",
                re.IGNORECASE,
            )
            new_text, count = pattern.subn(anonymized, text)
            if count > 0:
                text = new_text
                replacement_count += count

        return text, replacement_count

    def anonymize(self, text: str) -> TranscriptAnonymizationResult:
        """
        Anonymize a transcript document.

        Args:
            text: Full transcript text.

        Returns:
            TranscriptAnonymizationResult with anonymized text and metadata.
        """
        # Reset state for new document
        self._speaker_index = 0
        self._speaker_map = {}

        document_type = self.detect_document_type(text)

        _logger.info(
            "ANONYMIZATION_START",
            document_type=document_type.value,
            text_length=len(text),
        )

        # If already anonymous or not a transcript, return as-is
        if document_type in (DocumentType.TRANSCRIPT_ANONYMOUS, DocumentType.GENERAL):
            return TranscriptAnonymizationResult(
                original_text=text,
                anonymized_text=text,
                document_type=document_type,
                speaker_mappings={},
                header_replacements=0,
                inline_replacements=0,
            )

        # Extract speakers from headers first (builds speaker map)
        header_speakers = self._extract_speakers(text)

        # Pre-populate speaker map by processing headers in order
        for speaker_name, _, _ in header_speakers:
            self._get_or_create_speaker(speaker_name)

        # Now replace headers with anonymized versions
        result_text = text
        header_replacements = 0

        # Process in reverse order to maintain positions
        for speaker_name, start, end in reversed(header_speakers):
            mapping = self._get_or_create_speaker(speaker_name)
            result_text = (
                result_text[:start]
                + mapping.anonymized
                + result_text[end:]
            )
            header_replacements += 1

        # Replace inline mentions
        result_text, inline_replacements = self._replace_inline_mentions(
            result_text, self._speaker_map
        )

        # Adjust inline count to exclude header replacements (already counted)
        # The inline replacement will also match headers, so we subtract
        inline_replacements = max(0, inline_replacements - header_replacements)

        _logger.info(
            "ANONYMIZATION_COMPLETE",
            speakers=len(self._speaker_map),
            header_replacements=header_replacements,
            inline_replacements=inline_replacements,
        )

        return TranscriptAnonymizationResult(
            original_text=text,
            anonymized_text=result_text,
            document_type=document_type,
            speaker_mappings=self._speaker_map.copy(),
            header_replacements=header_replacements,
            inline_replacements=inline_replacements,
        )


def detect_and_anonymize(
    text: str,
    similarity_threshold: float = 0.85,
) -> TranscriptAnonymizationResult:
    """
    Convenience function to detect document type and anonymize if transcript.

    Args:
        text: Document text.
        similarity_threshold: Fuzzy matching threshold.

    Returns:
        TranscriptAnonymizationResult.
    """
    anonymizer = TranscriptAnonymizer(similarity_threshold=similarity_threshold)
    return anonymizer.anonymize(text)


# =============================================================================
# Opik PII Guardrail Integration
# =============================================================================


@dataclass
class PIIValidationResult:
    """Result of PII validation check."""

    is_clean: bool
    blocked_entities: List[str] = field(default_factory=list)
    error: Optional[str] = None


def validate_no_pii(
    text: str,
    blocked_entities: Optional[List[str]] = None,
    language: str = "fr",
) -> PIIValidationResult:
    """
    Validate that text contains no PII using Opik's NLP-based guardrail.

    This is faster than LLM-based detection and useful for:
    - Pre-validation before sending to LLM
    - Post-validation of generated content
    - Audit logging of potential PII leaks

    Args:
        text: Text to validate.
        blocked_entities: List of entity types to block.
            Default: ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]
            Available types: PERSON, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD,
                            IBAN_CODE, IP_ADDRESS, etc.
        language: Language code for NER model (default: "fr" for French).

    Returns:
        PIIValidationResult indicating whether text is clean.
    """
    try:
        from opik.guardrails import Guardrail, PII
        from opik import exceptions
    except ImportError:
        _logger.warning("OPIK_GUARDRAILS_UNAVAILABLE")
        return PIIValidationResult(
            is_clean=True,
            error="Opik guardrails not available",
        )

    if blocked_entities is None:
        blocked_entities = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]

    try:
        guardrail = Guardrail(
            guards=[PII(blocked_entities=blocked_entities, language=language)]
        )
        guardrail.validate(text)
        return PIIValidationResult(is_clean=True)

    except exceptions.GuardrailValidationFailed as e:
        _logger.warning("PII_DETECTED", error=str(e))
        return PIIValidationResult(
            is_clean=False,
            blocked_entities=blocked_entities,
            error=str(e),
        )
    except json.JSONDecodeError as e:
        # Opik API may return invalid JSON in some cases
        _logger.warning("PII_VALIDATION_JSON_ERROR", error=str(e))
        return PIIValidationResult(
            is_clean=True,  # Fail open on JSON errors
            error=f"JSON parse error: {e}",
        )
    except Exception as e:
        _logger.error("PII_VALIDATION_ERROR", error=str(e))
        return PIIValidationResult(
            is_clean=True,  # Fail open
            error=str(e),
        )
