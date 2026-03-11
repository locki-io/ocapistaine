"""
Neutrality Audit Feature — detect ordering bias and coverage imbalance
in OCapistaine comparison outputs.

Born from a real incident: a citizen noticed Construire l'Avenir always
appeared first. The cause was Python dict insertion order. The fix was
random.shuffle(). This feature ensures it never happens again undetected.
"""

import re
from collections import Counter
from typing import Any

from app.providers import LLMProvider

from .base import FeatureBase


# Display names used in comparison outputs (must match compare.py headers)
KNOWN_LISTS = {
    "Construire l'Avenir",
    "Passons à l'Action !",
    "Passons à l'Action",
    "S'unir pour Audierne-Esquibien",
    "Cap sur Notre Futur",
    "Audierne-Esquibien 2026",
}

# Regex to find list headers in markdown comparison output
# Matches "### List Name" or "**List Name**" at start of line
_HEADER_RE = re.compile(
    r"(?:^###\s+|^\*\*)"
    + r"("
    + "|".join(re.escape(name) for name in KNOWN_LISTS)
    + r")"
    + r"(?:\*\*)?",
    re.MULTILINE,
)


def extract_list_order(text: str) -> list[str]:
    """Extract the order in which lists appear in a comparison response."""
    seen = []
    for match in _HEADER_RE.finditer(text):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def extract_list_word_counts(text: str) -> dict[str, int]:
    """Extract word count per list section from a comparison response."""
    counts: dict[str, int] = {}
    # Split by list headers
    parts = _HEADER_RE.split(text)
    # parts alternates: [before_first_header, header1, content1, header2, content2, ...]
    i = 1
    while i < len(parts) - 1:
        name = parts[i]
        content = parts[i + 1] if i + 1 < len(parts) else ""
        counts[name] = len(content.split())
        i += 2
    return counts


class NeutralityAuditResult:
    """Result of a neutrality audit across multiple comparison responses."""

    def __init__(
        self,
        n_responses: int,
        first_position_counts: dict[str, int],
        mean_word_counts: dict[str, float],
        ordering_bias_detected: bool,
        coverage_bias_detected: bool,
        warnings: list[str],
    ):
        self.n_responses = n_responses
        self.first_position_counts = first_position_counts
        self.mean_word_counts = mean_word_counts
        self.ordering_bias_detected = ordering_bias_detected
        self.coverage_bias_detected = coverage_bias_detected
        self.warnings = warnings

    @property
    def is_neutral(self) -> bool:
        return not self.ordering_bias_detected and not self.coverage_bias_detected

    def to_dict(self) -> dict:
        return {
            "n_responses": self.n_responses,
            "first_position_counts": self.first_position_counts,
            "mean_word_counts": {k: round(v, 1) for k, v in self.mean_word_counts.items()},
            "ordering_bias_detected": self.ordering_bias_detected,
            "coverage_bias_detected": self.coverage_bias_detected,
            "is_neutral": self.is_neutral,
            "warnings": self.warnings,
        }

    def summary(self) -> str:
        """Human-readable summary for reports."""
        lines = [f"Neutrality Audit — {self.n_responses} responses analyzed"]
        lines.append("")

        if self.first_position_counts:
            lines.append("First-position frequency:")
            total = sum(self.first_position_counts.values())
            for name, count in sorted(
                self.first_position_counts.items(), key=lambda x: -x[1]
            ):
                pct = count / total * 100 if total else 0
                flag = " ⚠" if pct > 40 else ""
                lines.append(f"  {name}: {count}/{total} ({pct:.0f}%){flag}")

        if self.mean_word_counts:
            lines.append("")
            lines.append("Mean word count per list:")
            for name, wc in sorted(
                self.mean_word_counts.items(), key=lambda x: -x[1]
            ):
                lines.append(f"  {name}: {wc:.0f} words")

        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")

        verdict = "✅ NEUTRAL" if self.is_neutral else "⚠ BIAS DETECTED"
        lines.append("")
        lines.append(f"Verdict: {verdict}")
        return "\n".join(lines)


class NeutralityAuditFeature(FeatureBase):
    """
    Audit OCapistaine comparison outputs for neutrality.

    Checks:
    1. Ordering bias — is one list systematically first?
    2. Coverage balance — does word count vary dramatically?

    These checks are pure code (no LLM call needed).
    """

    # Alert if any list appears first more than this fraction of the time
    ORDERING_THRESHOLD = 0.40  # 40% (expected ~25% for 4 lists)

    # Alert if coefficient of variation of word counts exceeds this
    COVERAGE_CV_THRESHOLD = 0.50

    @property
    def name(self) -> str:
        return "neutrality_audit"

    @property
    def prompt(self) -> str:
        return ""  # No LLM prompt — this is a code-based audit

    async def execute(
        self,
        provider: LLMProvider,
        system_prompt: str,
        responses: list[str] | None = None,
        **kwargs,
    ) -> Any:
        """
        Audit a batch of comparison responses for neutrality.

        Args:
            provider: Not used (pure code audit), kept for interface compatibility.
            system_prompt: Not used.
            responses: List of comparison response texts to audit.

        Returns:
            NeutralityAuditResult with bias detection results.
        """
        if not responses:
            return NeutralityAuditResult(
                n_responses=0,
                first_position_counts={},
                mean_word_counts={},
                ordering_bias_detected=False,
                coverage_bias_detected=False,
                warnings=["No responses provided for audit."],
            )

        # 1. Ordering bias analysis
        first_position = Counter()
        for resp in responses:
            order = extract_list_order(resp)
            if order:
                first_position[order[0]] += 1

        n = len(responses)
        ordering_bias = False
        warnings = []

        if first_position:
            for name, count in first_position.items():
                ratio = count / n
                if ratio > self.ORDERING_THRESHOLD:
                    ordering_bias = True
                    warnings.append(
                        f"Ordering bias: '{name}' appears first in "
                        f"{count}/{n} responses ({ratio:.0%}). "
                        f"Expected ~{1/len(first_position):.0%}."
                    )

        # 2. Coverage balance analysis
        all_word_counts: dict[str, list[int]] = {}
        for resp in responses:
            wc = extract_list_word_counts(resp)
            for name, count in wc.items():
                all_word_counts.setdefault(name, []).append(count)

        mean_word_counts = {
            name: sum(counts) / len(counts)
            for name, counts in all_word_counts.items()
        }

        coverage_bias = False
        if len(mean_word_counts) > 1:
            values = list(mean_word_counts.values())
            mean_val = sum(values) / len(values)
            if mean_val > 0:
                variance = sum((v - mean_val) ** 2 for v in values) / len(values)
                cv = (variance ** 0.5) / mean_val
                if cv > self.COVERAGE_CV_THRESHOLD:
                    # Check if it's a data gap (genuinely sparse list) vs. bias
                    min_list = min(mean_word_counts, key=mean_word_counts.get)
                    max_list = max(mean_word_counts, key=mean_word_counts.get)
                    coverage_bias = True
                    warnings.append(
                        f"Coverage imbalance: '{max_list}' averages "
                        f"{mean_word_counts[max_list]:.0f} words vs. "
                        f"'{min_list}' at {mean_word_counts[min_list]:.0f} words "
                        f"(CV={cv:.2f}). May reflect data gap rather than bias."
                    )

        return NeutralityAuditResult(
            n_responses=n,
            first_position_counts=dict(first_position),
            mean_word_counts=mean_word_counts,
            ordering_bias_detected=ordering_bias,
            coverage_bias_detected=coverage_bias,
            warnings=warnings,
        )
