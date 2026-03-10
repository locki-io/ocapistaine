"""
Unified RAG dataset builder for audierne2026 content.

Reads all source documents from the audierne2026 submodule (ext_data/audierne2026/docs/)
and builds a single JSONL file for ChromaDB ingestion.

Source types:
  - readme:         Category synthesis documents (docs/{category}/README.md)
  - contribution:   Citizen contributions (docs/{category}/contributions/*.md)
  - pdf_extract:    OCR-extracted PDFs (docs/{category}/pdf_extracts/*.md)
  - programme:      Electoral programme transcripts (docs/programmes/{list}/*.md)
  - context:        Municipal context documents (docs/*.md — council reports, voeux)

All source URLs point to audierne2026.fr (Jekyll-served) to avoid GitHub rate limits.

Usage:
    python scripts/build_rag_dataset.py              # dry run (preview)
    python scripts/build_rag_dataset.py --apply       # write JSONL
    python scripts/build_rag_dataset.py --apply --reset-ingest  # write + re-ingest
"""

import json
import re
import sys
from pathlib import Path

# ====================== PATHS ======================

SUBMODULE_DOCS = Path(__file__).resolve().parents[1] / "ext_data" / "audierne2026" / "docs"
JSONL_PATH = Path(__file__).resolve().parents[1] / "data" / "audierne2026" / "rag" / "documents.jsonl"

# ====================== CONFIG ======================

SITE_BASE = "https://audierne2026.fr/docs"

CATEGORIES = {
    "economie": "Économie locale",
    "logement": "Logement & Urbanisme",
    "culture": "Culture & Patrimoine",
    "environnement": "Environnement",
    "associations": "Associations & Vie locale",
    "jeunesse": "École & Jeunesse",
    "alimentation-bien-etre-soins": "Alimentation, bien-être et soins",
}

PROGRAMME_DIRS = {
    "construire-avenir": ("ca", "Construire l'Avenir"),
    "cap-sur-notre-futur": ("csnf", "Cap sur Notre Futur"),
    "passons-a-laction": ("paa", "Passons à l'Action !"),
    "sunir-pour-audierne": ("spae", "S'unir pour Audierne-Esquibien"),
}

# Top-level docs/*.md files to ingest as context (council reports, voeux, etc.)
CONTEXT_PATTERNS = [
    "reunion_municipale_*.md",
    "voeux_*.md",
]

# ====================== HELPERS ======================


def doc_id(source_type: str, *parts: str) -> str:
    """Generate a deterministic document ID."""
    base = f"{source_type}-{'-'.join(parts)}"
    return re.sub(r"[^a-z0-9-]", "-", base.lower())[:64]


def extract_title(content: str, fallback: str) -> str:
    """Extract first markdown heading or use fallback."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return match.group(1) if match else fallback


def read_md(path: Path) -> str:
    """Read a markdown file, return empty string if missing."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


# ====================== EXTRACTORS ======================


def build_readmes() -> list[dict]:
    """Category README synthesis documents."""
    docs = []
    for cat_key, cat_title in CATEGORIES.items():
        content = read_md(SUBMODULE_DOCS / cat_key / "README.md")
        if not content.strip():
            continue
        docs.append({
            "id": doc_id("readme", cat_key, "main"),
            "category": cat_key,
            "category_title": cat_title,
            "source_type": "readme",
            "title": extract_title(content, f"README {cat_key}"),
            "url": f"{SITE_BASE}/{cat_key}/README.md",
            "content": content,
            "list_name": "",
        })
    return docs


def build_contributions() -> list[dict]:
    """Citizen contribution documents (issues + discussions exported to markdown)."""
    docs = []
    for cat_key, cat_title in CATEGORIES.items():
        contrib_dir = SUBMODULE_DOCS / cat_key / "contributions"
        if not contrib_dir.exists():
            continue
        for filepath in sorted(contrib_dir.glob("*.md")):
            if filepath.name == "INDEX.md":
                continue
            content = read_md(filepath)
            if not content.strip():
                continue

            filename = filepath.stem
            num_match = re.search(r"(issue|discussion)-(\d+)", filename)
            contrib_type = num_match.group(1) if num_match else "contribution"
            contrib_num = num_match.group(2) if num_match else filename

            # Prefer GitHub issue/discussion URL if embedded in the file
            gh_match = re.search(
                r"\[.+?\]\((https://github\.com/audierne2026/participons/(?:issues|discussions)/\d+)\)",
                content,
            )
            url = gh_match.group(1) if gh_match else f"{SITE_BASE}/{cat_key}/contributions/{filepath.name}"

            docs.append({
                "id": doc_id("contribution", cat_key, filename),
                "category": cat_key,
                "category_title": cat_title,
                "source_type": "contribution",
                "contribution_type": contrib_type,
                "contribution_number": contrib_num,
                "title": extract_title(content, f"Contribution {contrib_num}"),
                "url": url,
                "content": content,
                "list_name": "",
            })
    return docs


def build_pdf_extracts() -> list[dict]:
    """OCR-extracted PDF documents. URL points to the original external PDF source."""
    docs = []
    for cat_key, cat_title in CATEGORIES.items():
        pdf_dir = SUBMODULE_DOCS / cat_key / "pdf_extracts"
        if not pdf_dir.exists():
            continue
        for filepath in sorted(pdf_dir.glob("*.md")):
            if filepath.name == "INDEX.md":
                continue
            content = read_md(filepath)
            if not content.strip():
                continue

            filename = filepath.stem

            # Extract original PDF source URL (keep external URL, not audierne2026.fr)
            url_match = re.search(r"\*\*Source URL:\*\*\s*(.+?)$", content, re.MULTILINE)
            source_url = url_match.group(1).strip() if url_match else ""

            pages_match = re.search(r"\*\*Pages:\*\*\s*(\d+)", content)
            pages = int(pages_match.group(1)) if pages_match else 0

            # Extract content body (after metadata header)
            content_match = re.search(r"## Contenu extrait\n\n(.+?)(?=\n---\n|\Z)", content, re.DOTALL)
            body = content_match.group(1).strip() if content_match else content

            docs.append({
                "id": doc_id("pdf", cat_key, filename),
                "category": cat_key,
                "category_title": cat_title,
                "source_type": "pdf_extract",
                "title": extract_title(content, filename),
                "url": source_url,
                "content": body,
                "list_name": "",
            })
    return docs


def build_programmes() -> list[dict]:
    """Electoral programme transcripts (OCR from campaign documents)."""
    docs = []
    prog_dir = SUBMODULE_DOCS / "programmes"
    if not prog_dir.exists():
        print(f"  WARN: {prog_dir} not found")
        return docs

    for dir_name, (list_name, official_name) in sorted(PROGRAMME_DIRS.items()):
        list_dir = prog_dir / dir_name
        if not list_dir.exists():
            print(f"  WARN: {list_dir} not found")
            continue
        for filepath in sorted(list_dir.glob("*.md")):
            content = read_md(filepath)
            if not content.strip():
                continue

            # Strip OCR metadata header (everything before first ---)
            match = re.search(r"\n---\n\n(.*)", content, re.DOTALL)
            body = match.group(1).strip() if match else content.strip()
            if not body:
                continue

            docs.append({
                "id": doc_id("programme", list_name, filepath.stem),
                "category": "",
                "category_title": "",
                "source_type": "programme",
                "title": f"{filepath.stem} ({official_name})",
                "url": f"{SITE_BASE}/programmes/{dir_name}/{filepath.name}",
                "content": body,
                "list_name": list_name,
            })
    return docs


def build_context() -> list[dict]:
    """Municipal context documents (council reports, voeux du maire, etc.)."""
    docs = []
    for pattern in CONTEXT_PATTERNS:
        for filepath in sorted(SUBMODULE_DOCS.glob(pattern)):
            content = read_md(filepath)
            if not content.strip():
                continue
            docs.append({
                "id": doc_id("context", filepath.stem),
                "category": "",
                "category_title": "",
                "source_type": "context",
                "title": extract_title(content, filepath.stem.replace("_", " ").title()),
                "url": f"{SITE_BASE}/{filepath.name}",
                "content": content,
                "list_name": "",
            })
    return docs


# ====================== MAIN ======================


def main():
    apply = "--apply" in sys.argv
    reset_ingest = "--reset-ingest" in sys.argv

    if not SUBMODULE_DOCS.exists():
        print(f"ERROR: submodule docs not found at {SUBMODULE_DOCS}")
        print("Run: git submodule update --remote ext_data/audierne2026")
        sys.exit(1)

    print(f"Source: {SUBMODULE_DOCS}")
    print(f"Output: {JSONL_PATH}")
    print()

    # Build all document types
    builders = [
        ("READMEs", build_readmes),
        ("Contributions", build_contributions),
        ("PDF extracts", build_pdf_extracts),
        ("Programmes", build_programmes),
        ("Context docs", build_context),
    ]

    all_docs = []
    for label, builder in builders:
        docs = builder()
        all_docs.extend(docs)
        print(f"  {label}: {len(docs)} docs")

    # Programme breakdown by list
    list_counts = {}
    for d in all_docs:
        ln = d.get("list_name", "")
        if ln:
            list_counts[ln] = list_counts.get(ln, 0) + 1
    if list_counts:
        for ln, count in sorted(list_counts.items()):
            print(f"    {ln}: {count}")

    # URL check
    with_url = sum(1 for d in all_docs if d.get("url"))
    without_url = len(all_docs) - with_url
    print(f"\n  Total: {len(all_docs)} documents ({with_url} with URL, {without_url} without)")

    if not apply:
        print("\nDry run. Use --apply to write changes.")
        return

    # Write JSONL
    JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(JSONL_PATH, "w", encoding="utf-8") as f:
        for doc in all_docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    print(f"\nWritten to {JSONL_PATH}")

    if reset_ingest:
        print("\nRe-ingesting into ChromaDB...")
        import subprocess
        result = subprocess.run(
            ["poetry", "run", "python", "-m", "app.rag.ingest", "--reset"],
            cwd=Path(__file__).resolve().parents[1],
        )
        if result.returncode != 0:
            sys.exit(result.returncode)
    else:
        print("\nRun: poetry run python -m app.rag.ingest --reset")


if __name__ == "__main__":
    main()
