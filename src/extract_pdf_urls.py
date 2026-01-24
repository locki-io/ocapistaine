"""Extract PDF URLs and metadata from scraped markdown files."""

import json
from pathlib import Path
from firecrawl_utils import extract_documents_from_page
from config import EXT_DATA_DIR


def process_markdown_files(source_dir: Path) -> list[dict]:
    """
    Process all markdown files in a directory and extract PDF metadata.

    Args:
        source_dir: Directory containing markdown files

    Returns:
        list: All extracted document metadata
    """
    all_documents = []

    # Find all markdown files (excluding index files)
    md_files = [
        f for f in source_dir.glob("*.md")
        if not f.name.startswith("index_")
    ]

    print(f"Found {len(md_files)} markdown files in {source_dir.name}")

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
            documents = extract_documents_from_page(content)

            # Add source file info to each document
            for doc in documents:
                doc["source_file"] = md_file.name
                doc["source_category"] = source_dir.name

            all_documents.extend(documents)

            if documents:
                print(f"  {md_file.name}: {len(documents)} PDFs")

        except Exception as e:
            print(f"  ❌ Error processing {md_file.name}: {e}")

    return all_documents


def main():
    """Main extraction process."""

    # Process mairie_arretes
    print("\n📄 Processing mairie_arretes...")
    arretes_docs = process_markdown_files(EXT_DATA_DIR / "mairie_arretes")

    # Process commission_controle
    print("\n📄 Processing commission_controle...")
    commission_docs = process_markdown_files(EXT_DATA_DIR / "commission_controle")

    # Combine all documents
    all_documents = arretes_docs + commission_docs

    # Remove duplicates based on URL
    unique_docs = {doc["url"]: doc for doc in all_documents}.values()
    unique_docs = list(unique_docs)

    print(f"\n📊 Summary:")
    print(f"  Total PDFs found: {len(all_documents)}")
    print(f"  Unique PDFs: {len(unique_docs)}")
    print(f"  mairie_arretes: {len(arretes_docs)}")
    print(f"  commission_controle: {len(commission_docs)}")

    # Save to JSON
    output_file = EXT_DATA_DIR / "extracted_pdf_metadata.json"
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(unique_docs, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved metadata to: {output_file}")

    # Show sample
    if unique_docs:
        print(f"\n📋 Sample document:")
        sample = unique_docs[0]
        for key, value in sample.items():
            print(f"  {key}: {value}")

    return unique_docs


if __name__ == "__main__":
    main()
