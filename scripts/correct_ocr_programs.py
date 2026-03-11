"""
OCR Correction Script — Fix OCR errors in program markdown files.

Uses the Forseti wording correction feature with an OCR-specific prompt
that knows candidate names, Audierne-specific terms, and common OCR errors.

The RAG context (LISTS.md + candidate names) helps the LLM identify
misspelled proper nouns like "PIDER" → "Didier".

Usage:
    poetry run python scripts/correct_ocr_programs.py                    # preview all
    poetry run python scripts/correct_ocr_programs.py --apply            # apply corrections
    poetry run python scripts/correct_ocr_programs.py --dir program_paa  # single directory
    poetry run python scripts/correct_ocr_programs.py --file ext_data/program_paa/paa_edito2.md
"""

import sys
import json
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.logging import get_logger

logger = get_logger("processors")

EXT_DATA = Path("ext_data")
GAZETTEER_PATH = EXT_DATA / "gazetteer_audierne.txt"
PROGRAM_DIRS = ["program_ca", "program_csnfa", "program_paa", "program_spae"]

# =============================================================================
# GAZETTEER — loaded from ext_data/gazetteer_audierne.txt
# =============================================================================


def load_gazetteer(path: Path = GAZETTEER_PATH) -> list[str]:
    """Load place names from gazetteer file (one per line, # comments)."""
    if not path.exists():
        logger.warning(f"Gazetteer not found: {path}")
        return []
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names


# Load once at import time
GAZETTEER = load_gazetteer()

# =============================================================================
# KNOWN NAMES & TERMS (RAG context for the LLM)
# =============================================================================

# Têtes de liste and known colistiers
KNOWN_NAMES = [
    "Didier Guillon",        # PAA
    "Michel Van Praët",      # SPAE
    "Florent Lardic",        # Construire l'Avenir
    "Eric Bosser",           # CSNFA
    "Gurvan Kerloc'h",       # Current mayor
]

# Municipal & electoral terms (not places — places are in GAZETTEER)
CIVIC_TERMS = [
    "délibération", "arrêté", "conseil municipal", "commune",
    "intercommunalité", "PLU", "CCCS", "Gwaien",
    "Passons à l'Action", "Construire l'Avenir",
    "S'unir pour Audierne-Esquibien", "Cap sur Notre Futur",
    "Audierne-Esquibien 2026",
]

# Common OCR error patterns (before → after)
KNOWN_OCR_FIXES = {
    "PIDER": "Didier",
    "Audierne Esquibien": "Audierne-Esquibien",
}


# =============================================================================
# OCR CORRECTION PROMPT (specialized version of wording correction)
# =============================================================================

OCR_CORRECTION_PROMPT = """Tu es un correcteur spécialisé dans la correction d'erreurs OCR (reconnaissance optique de caractères) dans des documents de campagne électorale.

## Contexte
Ces documents sont des programmes électoraux des élections municipales d'Audierne-Esquibien 2026, extraits par OCR depuis des photos et PDFs. L'OCR produit souvent des erreurs sur :
- Les accents et caractères spéciaux français
- La ponctuation et la mise en forme
- Les mots coupés en fin de ligne
- L'orthographe des mots courants

## NOMS PROTÉGÉS — NE JAMAIS MODIFIER
Les noms suivants sont des lieux-dits, quartiers et villages réels d'Audierne-Esquibien.
Ils peuvent sembler inhabituels mais sont CORRECTS. Ne les "corrige" JAMAIS :

{protected_places}

## Personnes connues (référence)
{known_names}

## Termes civiques (référence)
{civic_terms}

## Corrections connues
{known_fixes}

## Règles STRICTES
1. Corriger UNIQUEMENT les erreurs OCR évidentes (orthographe, accents manquants)
2. NE JAMAIS modifier un mot qui figure dans la liste des noms protégés
3. NE JAMAIS remplacer un mot inconnu par un nom de lieu connu (ex: ne PAS corriger "Stiri" en "Stum")
4. En cas de doute sur un nom propre breton, NE PAS corriger — le laisser tel quel
5. NE PAS modifier le sens, le style, ou la structure du texte
6. Préserver la mise en forme markdown (titres, listes, gras, etc.)
7. Les erreurs de césure (mots coupés) doivent être recollés

## Texte à corriger

{text}

Réponds en JSON avec ce format exact :
{{
  "corrected": "Le texte corrigé",
  "changes": ["Description de chaque correction effectuée"],
  "reasoning": "Explication des corrections"
}}

Si aucune correction n'est nécessaire, retourne le texte original dans "corrected" et une liste "changes" vide.

Réponds UNIQUEMENT avec le JSON, sans markdown ni explication."""


# =============================================================================
# CORRECTION ENGINE
# =============================================================================


def apply_known_fixes(text: str) -> tuple[str, list[str]]:
    """Apply deterministic known OCR fixes (no LLM needed)."""
    changes = []
    corrected = text
    for wrong, right in KNOWN_OCR_FIXES.items():
        if wrong in corrected:
            count = corrected.count(wrong)
            corrected = corrected.replace(wrong, right)
            changes.append(f"'{wrong}' → '{right}' ({count}x)")
    return corrected, changes


async def correct_with_llm(
    text: str,
    provider_name: str = "mistral",
    model_override: str | None = None,
) -> dict:
    """
    Use LLM to correct OCR errors with Audierne context.

    Returns:
        dict with keys: corrected, changes, reasoning
    """
    from app.providers import Message
    from app.providers.failover import ProviderWithFailover

    provider = ProviderWithFailover(
        primary=provider_name,
        model_overrides={provider_name: model_override} if model_override else {},
    )

    # Build the prompt with context
    prompt = OCR_CORRECTION_PROMPT.format(
        protected_places="\n".join(f"- {name}" for name in GAZETTEER),
        known_names="\n".join(f"- {name}" for name in KNOWN_NAMES),
        civic_terms=", ".join(CIVIC_TERMS),
        known_fixes="\n".join(f"- {k} → {v}" for k, v in KNOWN_OCR_FIXES.items()),
        text=text,
    )

    messages = [
        Message(role="system", content="Tu es un correcteur OCR précis et conservateur."),
        Message(role="user", content=prompt),
    ]

    try:
        response = await provider.complete(
            messages=messages,
            max_tokens=4000,
            temperature=0.1,  # Low temperature for precise corrections
        )
        content = response.content
        model = response.model

        # Parse JSON response
        # Strip markdown fences if present
        clean = content.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
            if clean.endswith("```"):
                clean = clean.rsplit("```", 1)[0]
            clean = clean.strip()

        data = json.loads(clean)
        return {
            "corrected": data.get("corrected", text),
            "changes": data.get("changes", []),
            "reasoning": data.get("reasoning", ""),
            "model": model,
        }
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error: {e}")
        return {"corrected": text, "changes": [], "reasoning": f"Parse error: {e}", "model": ""}
    except Exception as e:
        logger.error(f"LLM correction failed: {e}")
        return {"corrected": text, "changes": [], "reasoning": f"Error: {e}", "model": ""}


async def correct_file(
    md_path: Path,
    provider_name: str = "mistral",
    model_override: str | None = None,
    apply: bool = False,
) -> dict:
    """
    Correct a single markdown file.

    Steps:
        1. Apply known deterministic fixes
        2. Send to LLM for contextual OCR correction
        3. Report changes (and optionally write)
    """
    text = md_path.read_text(encoding="utf-8")

    # Step 1: Deterministic fixes
    text_after_known, known_changes = apply_known_fixes(text)

    # Step 2: LLM correction (on the already-fixed text)
    llm_result = await correct_with_llm(
        text_after_known,
        provider_name=provider_name,
        model_override=model_override,
    )

    all_changes = known_changes + llm_result.get("changes", [])
    corrected = llm_result.get("corrected", text_after_known)

    result = {
        "file": str(md_path),
        "original_length": len(text),
        "corrected_length": len(corrected),
        "known_fixes": known_changes,
        "llm_changes": llm_result.get("changes", []),
        "total_changes": len(all_changes),
        "reasoning": llm_result.get("reasoning", ""),
        "model": llm_result.get("model", ""),
        "modified": corrected != text,
    }

    if apply and corrected != text:
        md_path.write_text(corrected, encoding="utf-8")
        result["written"] = True
        logger.info(f"  WRITTEN: {md_path.name} ({len(all_changes)} corrections)")
    else:
        result["written"] = False

    return result


# =============================================================================
# MAIN
# =============================================================================


async def run(
    dirs: list[str],
    single_file: str | None,
    provider_name: str,
    model_override: str | None,
    apply: bool,
):
    results = []

    if single_file:
        files = [Path(single_file)]
    else:
        files = []
        for dir_name in dirs:
            dir_path = EXT_DATA / dir_name
            if dir_path.exists():
                files.extend(sorted(dir_path.glob("*.md")))
            else:
                print(f"  WARN: {dir_path} not found")

    print(f"\n  OCR Correction — {len(files)} files")
    print(f"  Provider: {provider_name}")
    print(f"  Mode: {'APPLY' if apply else 'DRY RUN'}\n")

    for md_path in files:
        print(f"  [{md_path.parent.name}/{md_path.name}]", end=" ", flush=True)
        result = await correct_file(
            md_path,
            provider_name=provider_name,
            model_override=model_override,
            apply=apply,
        )
        results.append(result)

        if result["total_changes"] > 0:
            print(f"{result['total_changes']} corrections")
            for c in result["known_fixes"]:
                print(f"    [known] {c}")
            for c in result["llm_changes"]:
                print(f"    [llm]   {c}")
        else:
            print("OK (no changes)")

    # Summary
    modified = sum(1 for r in results if r["modified"])
    total_changes = sum(r["total_changes"] for r in results)
    print(f"\n  Summary: {modified}/{len(results)} files with corrections, {total_changes} total changes")

    if modified and not apply:
        print("\n  Dry run. Use --apply to write corrections.")
        print("  Then run: poetry run python scripts/rebuild_programs_jsonl.py --apply")
        print("  Then run: poetry run python -m app.rag.ingest --reset")


def main():
    parser = argparse.ArgumentParser(description="Correct OCR errors in program markdown files")
    parser.add_argument("--apply", action="store_true", help="Write corrections to files")
    parser.add_argument("--dir", type=str, help="Single directory to process (e.g. program_paa)")
    parser.add_argument("--file", type=str, help="Single file to process")
    parser.add_argument("--provider", type=str, default="mistral", help="LLM provider (default: mistral)")
    parser.add_argument("--model", type=str, default=None, help="Model override")
    args = parser.parse_args()

    dirs = [args.dir] if args.dir else PROGRAM_DIRS

    asyncio.run(run(
        dirs=dirs,
        single_file=args.file,
        provider_name=args.provider,
        model_override=args.model,
        apply=args.apply,
    ))


if __name__ == "__main__":
    main()
