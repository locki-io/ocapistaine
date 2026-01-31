"""Apply OCR to scanned PDFs using EasyOCR."""

import json
from pathlib import Path
from typing import Any
import easyocr
from pdf2image import convert_from_path
from config import EXT_DATA_DIR


def ocr_pdf(pdf_path: Path, ocr_reader: easyocr.Reader) -> dict[str, Any]:
    """
    Apply OCR to a PDF file using EasyOCR.

    Args:
        pdf_path: Path to the PDF file
        ocr_reader: Initialized EasyOCR Reader instance

    Returns:
        Dictionary with OCR results and metadata
    """
    try:
        # Convert PDF pages to images
        images = convert_from_path(pdf_path)
        page_count = len(images)

        # Process each page with OCR
        pages_text = []
        for img in images:
            # EasyOCR can work directly with PIL images
            import numpy as np
            img_array = np.array(img)

            # Run OCR on the image
            # EasyOCR returns: [(bbox, text, confidence), ...]
            result = ocr_reader.readtext(img_array)

            # Extract text from OCR results
            page_text = []
            for detection in result:
                if len(detection) >= 2:
                    text = detection[1]  # Text is the second element
                    page_text.append(text)

            pages_text.append(" ".join(page_text))

        # Combine all pages
        full_text = "\n\n".join(pages_text)
        char_count = len(full_text)

        return {
            "success": True,
            "text": full_text,
            "page_count": page_count,
            "char_count": char_count,
            "method": "easyocr",
            "error": None,
        }

    except Exception as e:
        return {
            "success": False,
            "text": "",
            "page_count": 0,
            "char_count": 0,
            "method": "easyocr",
            "error": str(e),
        }


def main():
    """Main OCR process."""

    # Initialize EasyOCR once (for efficiency)
    # ['fr', 'en'] supports both French and English text
    # gpu=False uses CPU (set to True if you have CUDA GPU)
    print("Initializing EasyOCR engine...")
    ocr_reader = easyocr.Reader(['fr', 'en'], gpu=False)
    print("✅ EasyOCR engine ready\n")

    for source in ["commission_controle", "mairie_arretes", "mairie_deliberations"]:

        print(f"\n{'='*60}")
        print(f"Processing OCR: {source}")
        print(f"{'='*60}\n")

        # Load extraction metadata to find PDFs needing OCR
        text_dir = EXT_DATA_DIR / f"{source}/text"
        metadata_file = text_dir / "extraction_metadata.json"

        if not metadata_file.exists():
            print(f"❌ No extraction metadata found: {metadata_file}")
            print("   Run extract_text_from_pdfs.py first!")
            continue

        with metadata_file.open("r", encoding="utf-8") as f:
            extraction_results = json.load(f)

        # Find PDFs that need OCR
        pdfs_needing_ocr = [r for r in extraction_results if r.get("needs_ocr", False)]

        if not pdfs_needing_ocr:
            print(f"✅ No PDFs need OCR in {source}\n")
            continue

        print(f"📄 Found {len(pdfs_needing_ocr)} PDFs needing OCR\n")

        # Get PDF directory
        pdf_dir = EXT_DATA_DIR / f"{source}/pdfs"

        # Track progress
        success_count = 0
        skip_count = 0
        error_count = 0
        ocr_results = []

        for idx, pdf_info in enumerate(pdfs_needing_ocr, 1):
            pdf_filename = pdf_info["filename"]
            pdf_path = pdf_dir / pdf_filename

            if not pdf_path.exists():
                print(f"  ⚠️  [{idx}/{len(pdfs_needing_ocr)}] PDF not found: {pdf_filename}")
                continue

            # Check if OCR already done
            text_filename = pdf_path.stem + ".txt"
            text_path = text_dir / text_filename

            # Check if file exists AND has content
            if text_path.exists():
                existing_text = text_path.read_text(encoding="utf-8")
                if len(existing_text.strip()) > 50:  # Has meaningful content
                    skip_count += 1
                    if idx % 50 == 0:
                        print(f"  ⏭️  [{idx}/{len(pdfs_needing_ocr)}] Skipping (exists): {pdf_filename}")
                    continue

            print(f"  🔍 [{idx}/{len(pdfs_needing_ocr)}] OCR processing: {pdf_filename}")

            # Perform OCR
            result = ocr_pdf(pdf_path, ocr_reader)

            # Save OCR text
            if result["success"] and result["char_count"] > 0:
                text_path.write_text(result["text"], encoding="utf-8")
                success_count += 1
                print(f"      ✅ Extracted {result['char_count']} chars from {result['page_count']} pages")
            else:
                error_count += 1
                print(f"      ❌ Error: {result['error']}")

            # Store results for metadata update
            ocr_results.append({
                "filename": pdf_filename,
                "page_count": result["page_count"],
                "char_count": result["char_count"],
                "method": result["method"],
                "success": result["success"],
                "error": result["error"],
            })

            # Progress update every 10 files (OCR is slower)
            if idx % 10 == 0:
                print(f"    📊 Progress: {success_count} processed, {skip_count} skipped, {error_count} errors")

        # Save OCR metadata
        ocr_metadata_file = text_dir / "ocr_metadata.json"
        with ocr_metadata_file.open("w", encoding="utf-8") as f:
            json.dump(ocr_results, f, indent=2, ensure_ascii=False)

        # Summary
        print(f"\n{'='*60}")
        print(f"📊 OCR Summary - {source}")
        print(f"{'='*60}")
        print(f"  ✅ Successfully processed: {success_count}")
        print(f"  ⏭️  Skipped (already exist): {skip_count}")
        print(f"  ❌ Errors: {error_count}")
        print(f"  📁 Text files saved to: {text_dir}")
        print(f"  📋 OCR metadata saved to: {ocr_metadata_file}")


if __name__ == "__main__":
    main()
