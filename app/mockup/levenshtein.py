# app/mockup/levenshtein.py
"""
Levenshtein Distance Utilities

Tools for calculating edit distance and generating text variations
at controlled distances from the original.
"""

import random
import re
from typing import List, Tuple


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate the Levenshtein distance between two strings.

    The Levenshtein distance is the minimum number of single-character edits
    (insertions, deletions, substitutions) required to change one string into another.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Integer edit distance
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # j+1 instead of j since previous_row and current_row are one character longer
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def levenshtein_ratio(s1: str, s2: str) -> float:
    """
    Calculate similarity ratio between two strings (0.0 to 1.0).

    Args:
        s1: First string
        s2: Second string

    Returns:
        Float between 0.0 (completely different) and 1.0 (identical)
    """
    distance = levenshtein_distance(s1, s2)
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    return 1.0 - (distance / max_len)


def apply_distance(
    text: str,
    target_distance: int,
    mutation_type: str = "mixed",
    seed: int | None = None,
) -> Tuple[str, int]:
    """
    Apply mutations to text to achieve approximately the target Levenshtein distance.

    Args:
        text: Original text
        target_distance: Desired edit distance from original
        mutation_type: Type of mutations - "insert", "delete", "substitute", "mixed"
        seed: Random seed for reproducibility

    Returns:
        Tuple of (mutated_text, actual_distance)
    """
    if seed is not None:
        random.seed(seed)

    if target_distance <= 0:
        return text, 0

    chars = list(text)
    mutations_applied = 0

    # Character sets for mutations
    vowels = "aeiouàâäéèêëïîôùûü"
    consonants = "bcdfghjklmnpqrstvwxyz"
    punctuation = ".,;:!?-'\"()"

    while mutations_applied < target_distance and len(chars) > 0:
        mutation = mutation_type
        if mutation == "mixed":
            mutation = random.choice(["insert", "delete", "substitute", "swap"])

        pos = random.randint(0, max(0, len(chars) - 1))

        if mutation == "delete" and len(chars) > 10:
            # Delete a character
            chars.pop(pos)
            mutations_applied += 1

        elif mutation == "insert":
            # Insert a random character
            if random.random() < 0.7:
                # Insert a letter
                char = random.choice(vowels + consonants)
            else:
                # Insert punctuation or space
                char = random.choice(punctuation + "   ")
            chars.insert(pos, char)
            mutations_applied += 1

        elif mutation == "substitute":
            # Replace a character
            original = chars[pos]
            if original.lower() in vowels:
                new_char = random.choice(vowels.replace(original.lower(), ""))
            elif original.lower() in consonants:
                new_char = random.choice(consonants.replace(original.lower(), ""))
            else:
                new_char = random.choice(vowels + consonants)

            # Preserve case
            if original.isupper():
                new_char = new_char.upper()
            chars[pos] = new_char
            mutations_applied += 1

        elif mutation == "swap" and len(chars) > 1 and pos < len(chars) - 1:
            # Swap adjacent characters
            chars[pos], chars[pos + 1] = chars[pos + 1], chars[pos]
            mutations_applied += 1

    result = "".join(chars)
    actual_distance = levenshtein_distance(text, result)

    return result, actual_distance


# Violation patterns to inject for testing
VIOLATION_PATTERNS = {
    "personal_attack": [
        "cet incompétent de maire",
        "ces idiots du conseil",
        "le maire est un menteur",
        "ils sont tous corrompus",
        "bande d'incapables",
    ],
    "off_topic": [
        "d'ailleurs, parlons de la politique nationale",
        "comme le président Macron",
        "les immigrés sont responsables",
        "le gouvernement devrait",
    ],
    "non_constructive": [
        "c'est nul",
        "ça ne marchera jamais",
        "personne ne fait rien",
        "tout est pourri",
        "ça sert à rien",
    ],
    "aggressive": [
        "!!!",
        "RÉVEILLEZ-VOUS",
        "C'EST SCANDALEUX",
        "HONTE À VOUS",
        "INADMISSIBLE",
    ],
}

# Constructive patterns to inject for making text more valid
CONSTRUCTIVE_PATTERNS = {
    "proposal": [
        "Je propose que",
        "Il serait intéressant de",
        "Une solution pourrait être",
        "Nous pourrions envisager",
    ],
    "collaboration": [
        "ensemble, nous pourrions",
        "en collaboration avec les habitants",
        "avec le soutien de la communauté",
        "en impliquant les citoyens",
    ],
    "positive": [
        "pour améliorer",
        "pour le bien de tous",
        "dans l'intérêt général",
        "pour notre commune",
    ],
}


def inject_violation(
    text: str,
    violation_type: str,
    intensity: float = 0.5,
    seed: int | None = None,
) -> Tuple[str, str]:
    """
    Inject a violation pattern into text.

    Args:
        text: Original text
        violation_type: Type of violation to inject
        intensity: How much to inject (0.0 to 1.0)
        seed: Random seed

    Returns:
        Tuple of (modified_text, violation_description)
    """
    if seed is not None:
        random.seed(seed)

    if violation_type not in VIOLATION_PATTERNS:
        return text, "unknown_violation"

    patterns = VIOLATION_PATTERNS[violation_type]
    pattern = random.choice(patterns)

    # Determine insertion point based on intensity
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if not sentences:
        return f"{pattern}. {text}", violation_type

    if intensity < 0.3:
        # Low intensity: add at end
        modified = f"{text} {pattern}."
    elif intensity < 0.7:
        # Medium intensity: insert in middle
        mid = len(sentences) // 2
        sentences.insert(mid, pattern)
        modified = " ".join(sentences)
    else:
        # High intensity: replace beginning
        sentences[0] = f"{pattern}. {sentences[0]}"
        modified = " ".join(sentences)

    return modified, violation_type


def inject_constructive(
    text: str,
    pattern_type: str = "proposal",
    seed: int | None = None,
) -> str:
    """
    Inject constructive patterns to make text more valid.

    Args:
        text: Original text
        pattern_type: Type of constructive pattern
        seed: Random seed

    Returns:
        Modified text with constructive elements
    """
    if seed is not None:
        random.seed(seed)

    if pattern_type not in CONSTRUCTIVE_PATTERNS:
        pattern_type = "proposal"

    pattern = random.choice(CONSTRUCTIVE_PATTERNS[pattern_type])

    # Add at beginning for proposals, end for positive
    if pattern_type == "proposal":
        return f"{pattern} {text[0].lower()}{text[1:]}"
    else:
        return f"{text} {pattern}."


def generate_distance_series(
    text: str,
    num_variations: int = 5,
    max_distance_ratio: float = 0.3,
    include_violations: bool = True,
) -> List[dict]:
    """
    Generate a series of text variations at increasing distances.

    Args:
        text: Original text
        num_variations: Number of variations to generate
        max_distance_ratio: Maximum distance as ratio of text length
        include_violations: Whether to inject violation patterns

    Returns:
        List of dicts with variation info
    """
    variations = []
    max_distance = int(len(text) * max_distance_ratio)

    for i in range(num_variations):
        # Calculate target distance for this step
        progress = (i + 1) / num_variations
        target_distance = int(max_distance * progress)

        # Apply character-level mutations
        mutated, actual_distance = apply_distance(
            text,
            target_distance,
            mutation_type="mixed",
            seed=i * 42,
        )

        # Optionally inject violations at higher distances
        violation_type = None
        if include_violations and progress > 0.5:
            violation_types = list(VIOLATION_PATTERNS.keys())
            violation_idx = int((progress - 0.5) * 2 * len(violation_types))
            violation_idx = min(violation_idx, len(violation_types) - 1)
            violation_type = violation_types[violation_idx]
            mutated, _ = inject_violation(
                mutated,
                violation_type,
                intensity=progress,
                seed=i * 42,
            )

        similarity = levenshtein_ratio(text, mutated)

        variations.append({
            "index": i,
            "text": mutated,
            "distance": levenshtein_distance(text, mutated),
            "similarity": round(similarity, 3),
            "target_distance": target_distance,
            "violation_injected": violation_type,
        })

    return variations
