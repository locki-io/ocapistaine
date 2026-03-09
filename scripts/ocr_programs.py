#!/usr/bin/env python3
"""
OCR electoral program materials using Mistral Document AI.

Processes images (JPG/PNG) and PDFs from ext_data/program_* directories,
extracts text content, and saves as markdown files ready for RAG ingestion.

Based on the extract_pdf_with_mistral.py workflow from audierne2026/participons.

Usage:
    python scripts/ocr_programs.py                     # Process all lists
    python scripts/ocr_programs.py --list program_ca   # Process one list
    python scripts/ocr_programs.py --list-only         # Preview without processing
    python scripts/ocr_programs.py --delay 3           # Slower rate limiting

Environment:
    MISTRAL_API_KEY or MISTRAL_OCR_API_KEY: Required
"""

import os
import re
import json
import time
import base64
import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests

# ====================== CONFIGURATION ======================

MISTRAL_API_KEY = os.getenv("MISTRAL_OCR_API_KEY") or os.getenv("MISTRAL_API_KEY")
EXT_DATA_DIR = Path(__file__).resolve().parent.parent / "ext_data"

# Electoral lists and their directories
LISTS = {
    "program_ca": "Construire l'Avenir (Florent Lardic)",
    "program_paa": "PAA",
    "program_spae": "SPAE",
    "program_csnfa": "CSNFA",
}

# Supported file types
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".avif"}
DOCUMENT_EXTENSIONS = {".pdf", ".pptx", ".docx"}
ALL_EXTENSIONS = IMAGE_EXTENSIONS | DOCUMENT_EXTENSIONS

OCR_API_URL = "https://api.mistral.ai/v1/ocr"

# =========================================================


def get_mime_type(path: Path) -> str:
    """Get MIME type for a file."""
    ext = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".avif": "image/avif",
        ".pdf": "application/pdf",
    }.get(ext, "application/octet-stream")


def file_to_base64_url(path: Path) -> str:
    """Convert a local file to a base64 data URL."""
    mime = get_mime_type(path)
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{data}"


def build_ocr_payload(path: Path) -> dict:
    """Build Mistral OCR API payload for a local file."""
    ext = path.suffix.lower()
    data_url = file_to_base64_url(path)

    if ext in IMAGE_EXTENSIONS:
        return {
            "model": "mistral-ocr-latest",
            "document": {
                "type": "image_url",
                "image_url": data_url,
            },
            "include_image_base64": False,
        }
    else:
        return {
            "model": "mistral-ocr-latest",
            "document": {
                "type": "document_url",
                "document_url": data_url,
            },
            "include_image_base64": False,
        }


def process_file(path: Path) -> dict:
    """OCR a single file via Mistral API."""
    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY not set")

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = build_ocr_payload(path)

    response = requests.post(
        OCR_API_URL,
        headers=headers,
        json=payload,
        timeout=180,
    )

    if response.status_code != 200:
        return {
            "success": False,
            "error": f"API {response.status_code}: {response.text[:200]}",
        }

    result = response.json()
    pages = result.get("pages", [])

    markdown_parts = []
    for page in pages:
        page_num = page.get("index", 0) + 1
        content = page.get("markdown", "")
        if content:
            markdown_parts.append(f"<!-- Page {page_num} -->\n{content}")

    return {
        "success": True,
        "content": "\n\n---\n\n".join(markdown_parts),
        "pages": len(pages),
        "usage": result.get("usage_info", {}),
    }


def scan_list_files(list_name: str) -> list[Path]:
    """Find all processable files in a list directory."""
    list_dir = EXT_DATA_DIR / list_name
    if not list_dir.exists():
        return []

    files = []
    for f in sorted(list_dir.iterdir()):
        if f.suffix.lower() in ALL_EXTENSIONS:
            files.append(f)
    return files


def save_extract(path: Path, list_name: str, result: dict) -> Path:
    """Save OCR result as markdown alongside the source file."""
    output_path = path.with_suffix(".md")

    lines = [
        f"# {path.stem}",
        "",
        f"**Source:** `{path.name}`",
        f"**Liste:** {LISTS.get(list_name, list_name)}",
        f"**Extrait le:** {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}",
        f"**Pages:** {result.get('pages', 'N/A')}",
        "",
        "---",
        "",
        result.get("content", "*Pas de contenu extrait*"),
        "",
        "---",
        "",
        "*Extrait via Mistral OCR API (`mistral-ocr-latest`)*",
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


def load_index() -> dict:
    """Load processing index to skip already-processed files."""
    index_path = EXT_DATA_DIR / ".ocr_programs_index.json"
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"files": {}, "last_updated": None}


def save_index(index: dict):
    """Save processing index."""
    index["last_updated"] = datetime.now(timezone.utc).isoformat()
    index_path = EXT_DATA_DIR / ".ocr_programs_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(
        description="OCR des programmes électoraux avec Mistral Document AI"
    )
    parser.add_argument("--list", choices=list(LISTS.keys()), help="Traiter une seule liste")
    parser.add_argument("--list-only", action="store_true", help="Lister les fichiers sans traiter")
    parser.add_argument("--force", action="store_true", help="Retraiter les fichiers déjà extraits")
    parser.add_argument("--delay", type=float, default=2.0, help="Délai entre requêtes API (s)")
    parser.add_argument("--limit", "-n", type=int, default=0, help="Limiter le nombre de fichiers")
    args = parser.parse_args()

    print("=" * 60)
    print("  OCR Programmes Électoraux — Mistral Document AI")
    print("=" * 60)
    print()

    # Scan files
    lists_to_process = [args.list] if args.list else list(LISTS.keys())
    all_files = []

    for list_name in lists_to_process:
        files = scan_list_files(list_name)
        for f in files:
            all_files.append((list_name, f))
        list_label = LISTS.get(list_name, list_name)
        imgs = sum(1 for f in files if f.suffix.lower() in IMAGE_EXTENSIONS)
        docs = sum(1 for f in files if f.suffix.lower() in DOCUMENT_EXTENSIONS)
        print(f"  {list_label}: {imgs} images, {docs} documents")

    print(f"\n  Total: {len(all_files)} fichiers")
    print()

    if args.list_only:
        for list_name, f in all_files:
            ext = f.suffix.lower()
            ftype = "IMG" if ext in IMAGE_EXTENSIONS else "DOC"
            print(f"  [{ftype}] {list_name}/{f.name}")
        return

    if not MISTRAL_API_KEY:
        print("  MISTRAL_API_KEY ou MISTRAL_OCR_API_KEY non defini!")
        print("  export MISTRAL_API_KEY='votre-cle'")
        return

    # Load index
    index = load_index()

    if args.limit > 0:
        all_files = all_files[:args.limit]

    processed = 0
    skipped = 0
    errors = 0

    for idx, (list_name, filepath) in enumerate(all_files):
        file_hash = hashlib.md5(str(filepath).encode()).hexdigest()

        # Skip already-processed (unless --force)
        if file_hash in index["files"] and not args.force:
            # Also skip if .md already exists
            if filepath.with_suffix(".md").exists():
                print(f"  skip  {list_name}/{filepath.name}")
                skipped += 1
                continue

        # Skip if it's already a .md companion to an image
        if filepath.suffix == ".md":
            continue

        print(f"  ocr   {list_name}/{filepath.name} ...", end=" ", flush=True)

        try:
            result = process_file(filepath)

            if result["success"]:
                output = save_extract(filepath, list_name, result)
                index["files"][file_hash] = {
                    "source": str(filepath.name),
                    "list": list_name,
                    "pages": result.get("pages", 0),
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                }
                print(f"OK ({result.get('pages', '?')} pages)")
                processed += 1
            else:
                print(f"FAIL: {result.get('error', '?')[:80]}")
                errors += 1

        except Exception as e:
            print(f"ERROR: {str(e)[:80]}")
            errors += 1

        # Rate limiting
        if args.delay > 0 and idx < len(all_files) - 1:
            time.sleep(args.delay)

    # Save index
    save_index(index)

    print()
    print("=" * 60)
    print(f"  Processed: {processed}  Skipped: {skipped}  Errors: {errors}")
    print("=" * 60)


if __name__ == "__main__":
    main()
