"""Structure extracted text with metadata for RAG indexing."""

import json
from pathlib import Path
from typing import Any
from datetime import datetime
import hashlib
from config import EXT_DATA_DIR


def generate_doc_id(filename: str, source_category: str) -> str:
    """
    Generate a unique document ID from filename and source.

    Args:
        filename: The PDF filename
        source_category: The source category (e.g., mairie_arretes)

    Returns:
        A unique hash-based ID
    """
    unique_str = f"{source_category}_{filename}"
    return hashlib.sha256(unique_str.encode()).hexdigest()[:16]


def parse_date(date_str: str | None) -> str | None:
    """
    Parse date strings into ISO format if possible.

    Args:
        date_str: Date string in various formats (e.g., "July 9, 2025", "December 2023")

    Returns:
        ISO format date string or None
    """
    if not date_str:
        return None

    # Common French month names
    french_months = {
        "janvier": "January", "février": "February", "mars": "March",
        "avril": "April", "mai": "May", "juin": "June",
        "juillet": "July", "août": "August", "septembre": "September",
        "octobre": "October", "novembre": "November", "décembre": "December"
    }

    # Try to normalize French to English
    date_normalized = date_str.lower()
    for fr, en in french_months.items():
        date_normalized = date_normalized.replace(fr, en)

    # Handle ISO format with timezone (from API)
    if "T" in date_str and "Z" in date_str:
        try:
            parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Try various date formats
    formats = [
        "%B %d, %Y",      # July 9, 2025
        "%d %B %Y",       # 9 July 2025
        "%B %Y",          # December 2023
        "%Y-%m-%d",       # 2025-07-09
        "%d/%m/%Y",       # 09/07/2025
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(date_normalized.strip(), fmt.lower())
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # If parsing fails, return original
    return date_str


def structure_documents_for_source(source: str) -> list[dict[str, Any]]:
    """
    Structure documents from a single source.

    Args:
        source: Source category (e.g., "mairie_arretes")

    Returns:
        List of structured documents
    """
    print(f"\n{'='*60}")
    print(f"Structuring documents: {source}")
    print(f"{'='*60}\n")

    # Load PDF metadata
    pdf_metadata_file = EXT_DATA_DIR / f"{source}/extracted_pdf_metadata.json"
    if not pdf_metadata_file.exists():
        print(f"❌ No PDF metadata found: {pdf_metadata_file}")
        return []

    with pdf_metadata_file.open("r", encoding="utf-8") as f:
        pdf_metadata_list = json.load(f)

    # Create lookup by filename
    # Handle two formats: scraped (has "filename") and API (has "hash")
    pdf_metadata_map = {}
    for item in pdf_metadata_list:
        if "filename" in item:
            # Scraped format (mairie_arretes, commission_controle)
            pdf_metadata_map[item["filename"]] = item
        elif "hash" in item:
            # API format (mairie_deliberations) - use hash as filename
            hash_filename = f"{item['hash']}.pdf"
            pdf_metadata_map[hash_filename] = item

    # Load extraction metadata
    text_dir = EXT_DATA_DIR / f"{source}/text"
    extraction_metadata_file = text_dir / "extraction_metadata.json"

    extraction_metadata_map = {}
    if extraction_metadata_file.exists():
        with extraction_metadata_file.open("r", encoding="utf-8") as f:
            extraction_metadata_list = json.load(f)
        extraction_metadata_map = {item["filename"]: item for item in extraction_metadata_list}

    # Process each text file
    structured_docs = []
    text_files = list(text_dir.glob("*.txt"))

    print(f"📄 Found {len(text_files)} text files\n")

    for idx, text_file in enumerate(text_files, 1):
        # Derive PDF filename from text filename
        pdf_filename = text_file.stem + ".pdf"

        # Load text content
        try:
            content = text_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  ⚠️  [{idx}/{len(text_files)}] Error reading {text_file.name}: {e}")
            continue

        # Skip empty or very short documents
        if len(content.strip()) < 50:
            if idx % 100 == 0:
                print(f"  ⏭️  [{idx}/{len(text_files)}] Skipping (too short): {text_file.name}")
            continue

        # Get PDF metadata
        pdf_meta = pdf_metadata_map.get(pdf_filename, {})

        # Get extraction metadata
        extraction_meta = extraction_metadata_map.get(pdf_filename, {})

        # Determine extraction method
        if extraction_meta.get("needs_ocr"):
            extraction_method = "ocr_needed"  # Will be updated when OCR runs
        else:
            extraction_method = "pypdf"

        # Extract metadata fields - handle both scraped and API formats
        if "objet" in pdf_meta:
            # API format (mairie_deliberations)
            title = pdf_meta.get("objet", "Untitled")
            date_field = pdf_meta.get("date_acte", pdf_meta.get("date_publication"))
            source_file = None
            classification = pdf_meta.get("classification_libelle", "")
        else:
            # Scraped format (mairie_arretes, commission_controle)
            title = pdf_meta.get("title", "Untitled")
            date_field = pdf_meta.get("date")
            source_file = pdf_meta.get("source_file")
            classification = None

        # Structure the document
        doc = {
            "id": generate_doc_id(pdf_filename, source),
            "content": content,
            "metadata": {
                "title": title,
                "date": parse_date(date_field) if date_field else None,
                "date_raw": date_field,
                "category": source,
                "classification": classification,
                "source_url": pdf_meta.get("url"),
                "filename": pdf_filename,
                "file_size": pdf_meta.get("file_size"),
                "language": pdf_meta.get("language", "French"),
                "page_count": extraction_meta.get("page_count", 0),
                "char_count": len(content),
                "extraction_method": extraction_method,
                "needs_ocr": extraction_meta.get("needs_ocr", False),
                "source_file": source_file,
            }
        }

        structured_docs.append(doc)

        if idx % 100 == 0:
            print(f"  ✅ [{idx}/{len(text_files)}] Processed: {text_file.name}")

    print(f"\n✅ Structured {len(structured_docs)} documents from {source}\n")
    return structured_docs


def main():
    """Main structuring process."""

    all_documents = []
    sources = ["commission_controle", "mairie_arretes", "mairie_deliberations"]

    for source in sources:
        docs = structure_documents_for_source(source)
        all_documents.extend(docs)

    # Save combined structured documents
    output_dir = EXT_DATA_DIR / "structured"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "all_documents.json"
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(all_documents, f, indent=2, ensure_ascii=False)

    # Also save per-source files
    for source in sources:
        source_docs = [doc for doc in all_documents if doc["metadata"]["category"] == source]
        if source_docs:
            source_file = output_dir / f"{source}_documents.json"
            with source_file.open("w", encoding="utf-8") as f:
                json.dump(source_docs, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n{'='*60}")
    print(f"📊 Structuring Summary")
    print(f"{'='*60}")
    print(f"  ✅ Total documents structured: {len(all_documents)}")
    for source in sources:
        count = len([d for d in all_documents if d["metadata"]["category"] == source])
        print(f"     - {source}: {count} documents")
    print(f"  📁 Output directory: {output_dir}")
    print(f"  📋 Combined file: {output_file}")
    print(f"  📋 Per-source files: {source}_documents.json")

    # Sample document
    if all_documents:
        print(f"\n📄 Sample structured document:")
        sample = all_documents[0]
        print(f"   ID: {sample['id']}")
        print(f"   Title: {sample['metadata']['title']}")
        print(f"   Date: {sample['metadata']['date']}")
        print(f"   Category: {sample['metadata']['category']}")
        print(f"   Content length: {len(sample['content'])} chars")
        print(f"   Pages: {sample['metadata']['page_count']}")


if __name__ == "__main__":
    main()
