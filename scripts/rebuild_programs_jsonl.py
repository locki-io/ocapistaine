"""
Rebuild the program documents in the RAG JSONL from participons submodule.

Reads electoral programme markdown files from participons/programmes/,
generates GitHub-linkable URLs, and merges with non-program documents.

Usage:
    python scripts/rebuild_programs_jsonl.py          # preview
    python scripts/rebuild_programs_jsonl.py --apply   # write changes
"""

import json
import re
import sys
from pathlib import Path

JSONL_PATH = Path("data/audierne2026/rag/documents.jsonl")

# Submodule path (primary) and legacy fallback
PARTICIPONS_DIR = Path("ext_data/audierne2026/programmes")
PARTICIPONS_DOCS = Path("ext_data/audierne2026/docs")
EXT_DATA = Path("ext_data")

# GitHub base URL for source links
GITHUB_BASE = "https://github.com/audierne2026/participons/blob/main/programmes"
GITHUB_DOCS_BASE = "https://github.com/audierne2026/participons/blob/main/docs"

# Context documents to ingest from participons/docs/ (general municipal context)
CONTEXT_DOCS = [
    "reunion_municipale_feb2026.md",
    "reunion_municipale_jan2026.md",
    "voeux_maire_jan2026.md",
]

# Map directory name -> (list_name slug, official name)
# Keys match directory names in participons/programmes/
PROGRAM_DIRS = {
    "construire-avenir": ("ca", "Construire l'Avenir"),
    "cap-sur-notre-futur": ("csnf", "Cap sur Notre Futur"),
    "passons-a-laction": ("paa", "Passons à l'Action !"),
    "sunir-pour-audierne": ("spae", "S'unir pour Audierne-Esquibien"),
}

# Legacy mapping (ext_data/program_* -> list slug) for fallback
LEGACY_DIRS = {
    "program_ca": ("ca", "Construire l'Avenir"),
    "program_csnfa": ("csnf", "Cap sur Notre Futur"),
    "program_paa": ("paa", "Passons à l'Action !"),
    "program_spae": ("spae", "S'unir pour Audierne-Esquibien"),
}


def load_existing_non_program(path: Path) -> list[dict]:
    """Load JSONL entries that are NOT rebuilt from the submodule."""
    kept = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            source_type = doc.get("source_type", "")
            # Keep everything except OCR programs and council-reports (both rebuilt from submodule)
            if source_type not in ("ocr", "program", "council-report"):
                kept.append(doc)
    return kept


def build_context_docs() -> list[dict]:
    """Build JSONL entries from participons/docs/ context files."""
    docs = []
    if not PARTICIPONS_DOCS.exists():
        return docs

    for filename in CONTEXT_DOCS:
        filepath = PARTICIPONS_DOCS / filename
        if not filepath.exists():
            print(f"  WARN: context doc {filepath} not found")
            continue

        content = filepath.read_text(encoding="utf-8")
        if not content.strip():
            continue

        doc_id = filepath.stem
        title = filepath.stem.replace("_", " ").title()
        url = f"{GITHUB_DOCS_BASE}/{filename}"

        docs.append({
            "id": doc_id,
            "category": "",
            "category_title": "",
            "source_type": "council-report",
            "title": title,
            "url": url,
            "content": content.strip(),
            "list_name": "",
        })

    return docs


def _build_docs_from_dir(
    base_dir: Path,
    dir_name: str,
    list_name: str,
    official_name: str,
    github_url_prefix: str | None,
) -> list[dict]:
    """Build JSONL entries from a directory of markdown files."""
    docs = []
    dir_path = base_dir / dir_name
    if not dir_path.exists():
        return docs

    md_files = sorted(dir_path.glob("*.md"))
    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        if not content.strip():
            continue

        # Strip the metadata header (everything before first ---)
        # but keep the actual content
        match = re.search(r"\n---\n\n(.*)", content, re.DOTALL)
        body = match.group(1).strip() if match else content.strip()

        if not body:
            continue

        doc_id = f"{md_file.stem} ({list_name})"
        title = f"{md_file.stem} ({official_name})"

        # Generate GitHub URL if using submodule
        url = ""
        if github_url_prefix:
            url = f"{github_url_prefix}/{dir_name}/{md_file.name}"

        docs.append({
            "id": doc_id,
            "category": "",
            "category_title": "",
            "source_type": "ocr",
            "title": title,
            "url": url,
            "content": body,
            "list_name": list_name,
        })

    return docs


def build_program_docs() -> list[dict]:
    """Build JSONL entries from participons submodule or ext_data fallback."""
    docs = []

    if PARTICIPONS_DIR.exists():
        print(f"  Source: {PARTICIPONS_DIR} (submodule)")
        for dir_name, (list_name, official_name) in sorted(PROGRAM_DIRS.items()):
            dir_docs = _build_docs_from_dir(
                PARTICIPONS_DIR, dir_name, list_name, official_name, GITHUB_BASE,
            )
            if not dir_docs:
                print(f"  WARN: {PARTICIPONS_DIR / dir_name} not found or empty")
            docs.extend(dir_docs)
    else:
        print(f"  WARN: submodule not found at {PARTICIPONS_DIR}, using ext_data/ fallback")
        for dir_name, (list_name, official_name) in sorted(LEGACY_DIRS.items()):
            dir_docs = _build_docs_from_dir(
                EXT_DATA, dir_name, list_name, official_name, None,
            )
            if not dir_docs:
                print(f"  WARN: {EXT_DATA / dir_name} not found or empty")
            docs.extend(dir_docs)

    return docs


def main():
    apply = "--apply" in sys.argv

    print(f"Loading existing JSONL: {JSONL_PATH}")
    non_program = load_existing_non_program(JSONL_PATH)
    print(f"  Non-program docs kept: {len(non_program)}")

    print("Building program docs...")
    program_docs = build_program_docs()
    print(f"  Program docs built: {len(program_docs)}")

    # Count per list
    list_counts = {}
    for d in program_docs:
        ln = d["list_name"]
        list_counts[ln] = list_counts.get(ln, 0) + 1
    for ln, count in sorted(list_counts.items()):
        print(f"    {ln}: {count} docs")

    print("Building context docs...")
    context_docs = build_context_docs()
    print(f"  Context docs built: {len(context_docs)}")

    submodule_docs = program_docs + context_docs

    # Check URLs
    with_url = sum(1 for d in submodule_docs if d.get("url"))
    print(f"  Docs with GitHub URL: {with_url}/{len(submodule_docs)}")

    all_docs = non_program + submodule_docs
    print(f"\nTotal: {len(all_docs)} docs")

    if apply:
        with open(JSONL_PATH, "w") as f:
            for doc in all_docs:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        print(f"Written to {JSONL_PATH}")
        print("\nRun: poetry run python -m app.rag.ingest --reset")
    else:
        print("\nDry run. Use --apply to write changes.")


if __name__ == "__main__":
    main()
