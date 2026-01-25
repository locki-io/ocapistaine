"""Extract text from PDFs using PyPDF."""

import json
from pathlib import Path
from typing import Any
from pypdf import PdfReader
from config import EXT_DATA_DIR


def extract_text_from_pdf(pdf_path: Path) -> dict[str, Any]:
    """
    Extract text from a PDF file.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Dictionary with extracted text and metadata
    """
    try:
        reader = PdfReader(pdf_path)

        # Extract text from all pages
        pages_text = []
        total_chars = 0

        for page_num, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            pages_text.append(text)
            total_chars += len(text)

        # Combine all pages
        full_text = "\n\n".join(pages_text)

        # Determine if extraction was successful
        # Heuristic: if we got less than 50 chars, it's probably a scanned PDF
        needs_ocr = total_chars < 50

        return {
            "success": True,
            "text": full_text,
            "page_count": len(reader.pages),
            "char_count": total_chars,
            "needs_ocr": needs_ocr,
            "error": None,
        }

    except Exception as e:
        return {
            "success": False,
            "text": "",
            "page_count": 0,
            "char_count": 0,
            "needs_ocr": True,
            "error": str(e),
        }


def main():
    """Main extraction process."""

    for source in ["commission_controle", "mairie_arretes", "mairie_deliberations"]:

        print(f"\n{'='*60}")
        print(f"Processing: {source}")
        print(f"{'='*60}\n")

        # Find all PDFs in the source directory
        pdf_dir = EXT_DATA_DIR / f"{source}/pdfs"
        if not pdf_dir.exists():
            print(f"❌ PDF directory not found: {pdf_dir}")
            print("   Run download_pdfs.py first!")
            continue

        pdf_files = list(pdf_dir.glob("*.pdf"))
        print(f"📄 Found {len(pdf_files)} PDFs to process\n")

        if not pdf_files:
            print("   No PDFs found, skipping...\n")
            continue

        # Create output directory for extracted text
        text_dir = EXT_DATA_DIR / f"{source}/text"
        text_dir.mkdir(parents=True, exist_ok=True)

        # Track progress
        success_count = 0
        needs_ocr_count = 0
        error_count = 0
        skip_count = 0
        results = []

        for idx, pdf_path in enumerate(pdf_files, 1):
            # Check if text file already exists
            text_filename = pdf_path.stem + ".txt"
            text_path = text_dir / text_filename

            if text_path.exists():
                skip_count += 1
                if idx % 50 == 0:
                    print(f"  ⏭️  [{idx}/{len(pdf_files)}] Skipping (exists): {pdf_path.name}")
                continue

            print(f"  📖 [{idx}/{len(pdf_files)}] Extracting: {pdf_path.name}")

            # Extract text
            result = extract_text_from_pdf(pdf_path)

            # Save extracted text if we got any
            if result["success"] and result["char_count"] > 0:
                text_path.write_text(result["text"], encoding="utf-8")
                success_count += 1

            # Track which PDFs need OCR
            if result["needs_ocr"]:
                needs_ocr_count += 1

            if not result["success"]:
                error_count += 1
                print(f"      ⚠️  Error: {result['error']}")

            # Store results for summary
            results.append({
                "filename": pdf_path.name,
                "page_count": result["page_count"],
                "char_count": result["char_count"],
                "needs_ocr": result["needs_ocr"],
                "success": result["success"],
                "error": result["error"],
            })

            # Progress update every 25 files
            if idx % 25 == 0:
                print(f"    📊 Progress: {success_count} extracted, {skip_count} skipped, {needs_ocr_count} need OCR, {error_count} errors")

        # Save extraction metadata
        metadata_file = text_dir / "extraction_metadata.json"
        with metadata_file.open("w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        # Summary for this source
        print(f"\n{'='*60}")
        print(f"📊 Extraction Summary - {source}")
        print(f"{'='*60}")
        print(f"  ✅ Successfully extracted: {success_count}")
        print(f"  ⏭️  Skipped (already exist): {skip_count}")
        print(f"  🔍 Need OCR (scanned/empty): {needs_ocr_count}")
        print(f"  ❌ Errors: {error_count}")
        print(f"  📁 Text files saved to: {text_dir}")
        print(f"  📋 Metadata saved to: {metadata_file}")

        # Show sample of PDFs that need OCR
        if needs_ocr_count > 0:
            print(f"\n  📋 Sample of PDFs needing OCR:")
            ocr_needed = [r for r in results if r["needs_ocr"]][:5]
            for r in ocr_needed:
                print(f"    - {r['filename']} ({r['char_count']} chars)")


if __name__ == "__main__":
    main()
