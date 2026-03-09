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
EXT_DATA = Path("ext_data")

# GitHub base URL for source links
GITHUB_BASE = "https://github.com/audierne2026/participons/blob/main/programmes"

# Map directory name -> (list_name slug, official name)
# Keys match directory names in participons/programmes/
PROGRAM_DIRS = {
    "construire-avenir": ("construire-avenir", "Construire l'Avenir"),
    "cap-sur-notre-futur": ("csnfa", "Cap sur Notre Futur"),
    "passons-a-laction": ("paa", "Passons à l'Action !"),
    "sunir-pour-audierne": ("spae", "S'unir pour Audierne-Esquibien"),
}

# Legacy mapping (ext_data/program_* -> list slug) for fallback
LEGACY_DIRS = {
    "program_ca": ("construire-avenir", "Construire l'Avenir"),
    "program_csnfa": ("csnfa", "Cap sur Notre Futur"),
    "program_paa": ("paa", "Passons à l'Action !"),
    "program_spae": ("spae", "S'unir pour Audierne-Esquibien"),
}


def load_existing_non_program(path: Path) -> list[dict]:
    """Load JSONL entries that are NOT from program_* directories."""
    kept = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            source_type = doc.get("source_type", "")
            # Keep everything except OCR program docs
            if source_type not in ("ocr", "program"):
                kept.append(doc)
    return kept


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

    # Check URLs
    with_url = sum(1 for d in program_docs if d.get("url"))
    print(f"  Docs with GitHub URL: {with_url}/{len(program_docs)}")

    all_docs = non_program + program_docs
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
