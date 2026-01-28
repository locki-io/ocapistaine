# app/mockup/generator.py
"""
Contribution Generator

Generate mock contributions for batch testing Forseti validation.
Creates variations using:
- Levenshtein distance for controlled character-level mutations (orthographic errors)
- LLM (Ollama/Mistral) for semantic mutations (paraphrasing, subtle violations)
"""

import json
import hashlib
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Literal
from dataclasses import dataclass, asdict

from app.mockup.levenshtein import (
    levenshtein_distance,
    levenshtein_ratio,
    apply_distance,
    inject_violation,
    inject_constructive,
    generate_distance_series,
    VIOLATION_PATTERNS,
)

# LLM mutations (lazy import to avoid requiring Ollama when not used)
_llm_mutator = None

# Default path for contributions JSON
CONTRIBUTIONS_DIR = Path(__file__).parent / "data"
CONTRIBUTIONS_FILE = CONTRIBUTIONS_DIR / "contributions.json"


@dataclass
class MockContribution:
    """
    A mock contribution for testing.

    Matches Framaforms submission format:
    - category: The contribution category
    - constat_factuel: Factual observation about current situation
    - idees_ameliorations: Proposed improvement ideas
    """

    id: str
    category: Optional[str] = None
    constat_factuel: str = ""  # "Constat factuel" - factual observation
    idees_ameliorations: str = ""  # "Vos idées d'améliorations" - improvement ideas
    source: str = "mock"  # "mock", "derived", "real", "framaforms"
    parent_id: Optional[str] = None  # For derived contributions
    distance_from_parent: Optional[int] = None
    similarity_to_parent: Optional[float] = None
    expected_valid: Optional[bool] = None
    violations_injected: Optional[List[str]] = None
    metadata: Optional[dict] = None

    @property
    def title(self) -> str:
        """Generate title from constat_factuel (first 80 chars)."""
        text = self.constat_factuel or self.idees_ameliorations
        if len(text) > 80:
            return text[:77] + "..."
        return text

    @property
    def body(self) -> str:
        """Combine constat and ideas into body text."""
        parts = []
        if self.constat_factuel:
            parts.append(f"**Constat factuel:**\n{self.constat_factuel}")
        if self.idees_ameliorations:
            parts.append(f"**Vos idées d'améliorations:**\n{self.idees_ameliorations}")
        return "\n\n".join(parts)

    @property
    def full_text(self) -> str:
        """Get full text for distance calculations."""
        return f"{self.constat_factuel} {self.idees_ameliorations}"

    def to_dict(self) -> dict:
        data = asdict(self)
        # Add computed properties for compatibility
        data["title"] = self.title
        data["body"] = self.body
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "MockContribution":
        # Handle legacy format with title/body
        if "title" in data and "constat_factuel" not in data:
            data["constat_factuel"] = data.get("body", data.get("title", ""))
            data["idees_ameliorations"] = ""
        # Remove computed properties if present
        data.pop("title", None)
        data.pop("body", None)
        data.pop("full_text", None)
        return cls(**data)

    def generate_id(self) -> str:
        """Generate a unique ID based on content hash."""
        content = f"{self.constat_factuel}:{self.idees_ameliorations}:{self.category}"
        return hashlib.md5(content.encode()).hexdigest()[:12]


class ContributionGenerator:
    """
    Generate mock contributions with controlled variations.

    Supports:
    - Creating base contributions
    - Generating variations at specific Levenshtein distances
    - Injecting violations to test charter compliance
    - Batch generation for comprehensive testing
    """

    def __init__(self, contributions: Optional[List[MockContribution]] = None):
        self.contributions: List[MockContribution] = contributions or []
        self._id_counter = 0

    def add_contribution(
        self,
        constat_factuel: str,
        idees_ameliorations: str = "",
        category: Optional[str] = None,
        expected_valid: Optional[bool] = None,
        source: str = "mock",
    ) -> MockContribution:
        """
        Add a new base contribution.

        Args:
            constat_factuel: Factual observation about current situation
            idees_ameliorations: Proposed improvement ideas
            category: Contribution category
            expected_valid: Expected validation result
            source: Source type (mock, real, framaforms)

        Returns:
            New MockContribution
        """
        contrib = MockContribution(
            id="",
            constat_factuel=constat_factuel,
            idees_ameliorations=idees_ameliorations,
            category=category,
            source=source,
            expected_valid=expected_valid,
        )
        contrib.id = contrib.generate_id()
        self.contributions.append(contrib)
        return contrib

    def derive_contribution(
        self,
        parent: MockContribution,
        target_distance: int,
        mutation_type: str = "mixed",
        inject_violation_type: Optional[str] = None,
        violation_intensity: float = 0.5,
    ) -> MockContribution:
        """
        Create a derived contribution at a specific distance from parent.

        Args:
            parent: Parent contribution to derive from
            target_distance: Target Levenshtein distance
            mutation_type: Type of mutations to apply
            inject_violation_type: Optional violation to inject
            violation_intensity: Intensity of violation injection

        Returns:
            New derived MockContribution
        """
        # Apply distance mutations to constat_factuel
        mutated_constat, _ = apply_distance(
            parent.constat_factuel,
            target_distance // 2,
            mutation_type=mutation_type,
        )

        # Apply distance mutations to idees_ameliorations
        mutated_idees, _ = apply_distance(
            parent.idees_ameliorations,
            target_distance // 2,
            mutation_type=mutation_type,
        )

        violations_injected = []

        # Inject violation if requested (prefer injecting into idees)
        if inject_violation_type:
            if mutated_idees:
                mutated_idees, v_type = inject_violation(
                    mutated_idees,
                    inject_violation_type,
                    intensity=violation_intensity,
                )
            else:
                mutated_constat, v_type = inject_violation(
                    mutated_constat,
                    inject_violation_type,
                    intensity=violation_intensity,
                )
            violations_injected.append(v_type)

        # Calculate actual distance and similarity from full text
        parent_text = parent.full_text
        derived_text = f"{mutated_constat} {mutated_idees}"
        text_distance = levenshtein_distance(parent_text, derived_text)
        similarity = levenshtein_ratio(parent_text, derived_text)

        # Determine expected validity
        expected_valid = parent.expected_valid
        if violations_injected:
            expected_valid = False

        contrib = MockContribution(
            id="",
            constat_factuel=mutated_constat,
            idees_ameliorations=mutated_idees,
            category=parent.category,
            source="derived",
            parent_id=parent.id,
            distance_from_parent=text_distance,
            similarity_to_parent=round(similarity, 3),
            expected_valid=expected_valid,
            violations_injected=violations_injected if violations_injected else None,
        )
        contrib.id = contrib.generate_id()
        self.contributions.append(contrib)
        return contrib

    def generate_variation_series(
        self,
        parent: MockContribution,
        num_variations: int = 5,
        max_distance_ratio: float = 0.3,
        progressive_violations: bool = True,
    ) -> List[MockContribution]:
        """
        Generate a series of variations at increasing distances.

        Args:
            parent: Parent contribution
            num_variations: Number of variations to generate
            max_distance_ratio: Max distance as ratio of text length
            progressive_violations: Inject violations progressively

        Returns:
            List of derived contributions
        """
        derived = []
        max_distance = int(len(parent.body) * max_distance_ratio)
        violation_types = list(VIOLATION_PATTERNS.keys())

        for i in range(num_variations):
            progress = (i + 1) / num_variations
            target_distance = int(max_distance * progress)

            # Determine violation to inject
            inject_violation_type = None
            if progressive_violations and progress > 0.4:
                v_idx = int((progress - 0.4) / 0.6 * len(violation_types))
                v_idx = min(v_idx, len(violation_types) - 1)
                inject_violation_type = violation_types[v_idx]

            contrib = self.derive_contribution(
                parent=parent,
                target_distance=target_distance,
                inject_violation_type=inject_violation_type,
                violation_intensity=progress,
            )
            derived.append(contrib)

        return derived

    def generate_llm_variation_series(
        self,
        parent: MockContribution,
        num_variations: int = 5,
        include_violations: bool = True,
        model: str = "mistral:latest",
    ) -> List[MockContribution]:
        """
        Generate variations using LLM (Ollama/Mistral) for semantic mutations.

        Args:
            parent: Parent contribution
            num_variations: Number of variations to generate
            include_violations: Include violation mutations
            model: Ollama model to use

        Returns:
            List of derived contributions with LLM-generated mutations
        """
        from app.mockup.llm_mutations import (
            LLMMutator,
            MutationType,
            _run_async,
        )

        mutator = LLMMutator(model=model)
        derived = []

        # Define mutation sequence
        if include_violations:
            mutation_sequence = [
                MutationType.PARAPHRASE,       # Valid - same meaning, different words
                MutationType.ORTHOGRAPHIC,     # Valid - realistic typos
                MutationType.SEMANTIC_SHIFT,   # Borderline - slightly different meaning
                MutationType.SUBTLE_VIOLATION, # Invalid - subtle charter violation
                MutationType.AGGRESSIVE,       # Invalid - obvious violation
                MutationType.OFF_TOPIC,        # Invalid - off topic
            ]
        else:
            mutation_sequence = [
                MutationType.PARAPHRASE,
                MutationType.ORTHOGRAPHIC,
                MutationType.PARAPHRASE,
                MutationType.ORTHOGRAPHIC,
                MutationType.SEMANTIC_SHIFT,
            ]

        async def generate_all():
            results = []
            for i in range(num_variations):
                idx = i % len(mutation_sequence)
                mutation_type = mutation_sequence[idx]

                # Mutate constat_factuel
                constat_result = await mutator.mutate(
                    parent.constat_factuel,
                    mutation_type,
                    temperature=0.7,
                )

                # Mutate idees_ameliorations if present
                if parent.idees_ameliorations:
                    idees_result = await mutator.mutate(
                        parent.idees_ameliorations,
                        mutation_type,
                        temperature=0.7,
                    )
                    mutated_idees = idees_result.mutated if idees_result.success else parent.idees_ameliorations
                else:
                    mutated_idees = ""

                mutated_constat = constat_result.mutated if constat_result.success else parent.constat_factuel

                # Determine expected validity
                if mutation_type in [MutationType.PARAPHRASE, MutationType.ORTHOGRAPHIC]:
                    expected_valid = True
                elif mutation_type == MutationType.SEMANTIC_SHIFT:
                    expected_valid = None  # Borderline
                else:
                    expected_valid = False

                # Calculate distance and similarity
                parent_text = parent.full_text
                derived_text = f"{mutated_constat} {mutated_idees}"
                text_distance = levenshtein_distance(parent_text, derived_text)
                similarity = levenshtein_ratio(parent_text, derived_text)

                results.append({
                    "constat": mutated_constat,
                    "idees": mutated_idees,
                    "mutation_type": mutation_type.value,
                    "expected_valid": expected_valid,
                    "distance": text_distance,
                    "similarity": similarity,
                    "success": constat_result.success,
                })

            return results

        # Run async mutations
        mutation_results = _run_async(generate_all())

        # Create MockContribution objects
        for i, result in enumerate(mutation_results):
            violations_injected = None
            if result["mutation_type"] in ["subtle_violation", "aggressive", "off_topic"]:
                violations_injected = [result["mutation_type"]]

            contrib = MockContribution(
                id="",
                constat_factuel=result["constat"],
                idees_ameliorations=result["idees"],
                category=parent.category,
                source="derived",
                parent_id=parent.id,
                distance_from_parent=result["distance"],
                similarity_to_parent=round(result["similarity"], 3),
                expected_valid=result["expected_valid"],
                violations_injected=violations_injected,
                metadata={
                    "mutation_type": result["mutation_type"],
                    "llm_generated": True,
                },
            )
            contrib.id = contrib.generate_id()
            self.contributions.append(contrib)
            derived.append(contrib)

        return derived

    def generate_batch(
        self,
        base_contributions: List[MockContribution],
        variations_per_base: int = 5,
        include_valid_series: bool = True,
        include_violation_series: bool = True,
    ) -> List[MockContribution]:
        """
        Generate a comprehensive batch of test contributions.

        Args:
            base_contributions: List of base contributions
            variations_per_base: Variations to generate per base
            include_valid_series: Include progressively mutated (but valid) series
            include_violation_series: Include series with injected violations

        Returns:
            List of all generated contributions
        """
        all_contributions = list(base_contributions)

        for base in base_contributions:
            if include_valid_series:
                # Generate variations without violations
                valid_series = []
                max_distance = int(len(base.body) * 0.2)
                for i in range(variations_per_base):
                    target = int(max_distance * (i + 1) / variations_per_base)
                    contrib = self.derive_contribution(
                        parent=base,
                        target_distance=target,
                        inject_violation_type=None,
                    )
                    valid_series.append(contrib)
                all_contributions.extend(valid_series)

            if include_violation_series:
                # Generate variations with progressive violations
                violation_series = self.generate_variation_series(
                    parent=base,
                    num_variations=variations_per_base,
                    progressive_violations=True,
                )
                all_contributions.extend(violation_series)

        return all_contributions

    def to_json(self) -> str:
        """Export contributions to JSON string."""
        data = {
            "generated_at": datetime.now().isoformat(),
            "count": len(self.contributions),
            "contributions": [c.to_dict() for c in self.contributions],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "ContributionGenerator":
        """Load contributions from JSON string."""
        data = json.loads(json_str)
        contributions = [
            MockContribution.from_dict(c) for c in data.get("contributions", [])
        ]
        return cls(contributions=contributions)


def load_contributions(path: Optional[Path] = None) -> ContributionGenerator:
    """Load contributions from JSON file."""
    path = path or CONTRIBUTIONS_FILE
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return ContributionGenerator.from_json(f.read())
    return ContributionGenerator()


def save_contributions(
    generator: ContributionGenerator,
    path: Optional[Path] = None,
) -> Path:
    """Save contributions to JSON file."""
    path = path or CONTRIBUTIONS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(generator.to_json())
    return path


def generate_variations(
    constat_factuel: str,
    idees_ameliorations: str = "",
    category: Optional[str] = None,
    num_variations: int = 5,
    include_violations: bool = True,
    use_llm: bool = False,
    llm_model: str = "mistral:latest",
) -> List[dict]:
    """
    Quick function to generate variations of a single contribution.

    Args:
        constat_factuel: Factual observation
        idees_ameliorations: Improvement ideas
        category: Optional category
        num_variations: Number of variations
        include_violations: Whether to inject violations
        use_llm: Use LLM (Ollama/Mistral) for semantic mutations
        llm_model: Ollama model to use (default: mistral:latest)

    Returns:
        List of variation dictionaries
    """
    generator = ContributionGenerator()
    base = generator.add_contribution(
        constat_factuel=constat_factuel,
        idees_ameliorations=idees_ameliorations,
        category=category,
        expected_valid=True,
        source="input",
    )

    if use_llm:
        # Use LLM-based mutations
        variations = generator.generate_llm_variation_series(
            parent=base,
            num_variations=num_variations,
            include_violations=include_violations,
            model=llm_model,
        )
    else:
        # Use text-based mutations (Levenshtein)
        variations = generator.generate_variation_series(
            parent=base,
            num_variations=num_variations,
            progressive_violations=include_violations,
        )

    return [v.to_dict() for v in [base] + variations]


def generate_variations_async(
    constat_factuel: str,
    idees_ameliorations: str = "",
    category: Optional[str] = None,
    num_variations: int = 5,
    include_violations: bool = True,
    llm_model: str = "mistral:latest",
) -> List[dict]:
    """
    Async function to generate LLM-based variations.

    Args:
        constat_factuel: Factual observation
        idees_ameliorations: Improvement ideas
        category: Optional category
        num_variations: Number of variations
        include_violations: Whether to inject violations
        llm_model: Ollama model to use

    Returns:
        List of variation dictionaries
    """
    return generate_variations(
        constat_factuel=constat_factuel,
        idees_ameliorations=idees_ameliorations,
        category=category,
        num_variations=num_variations,
        include_violations=include_violations,
        use_llm=True,
        llm_model=llm_model,
    )
