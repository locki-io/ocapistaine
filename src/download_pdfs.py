"""Download PDFs from extracted metadata."""

import json
import re
import time
from pathlib import Path
import requests
from config import EXT_DATA_DIR


def sanitize_filename(text: str, max_length: int = 100) -> str:
    """
    Convert text to a safe filename.

    Args:
        text: Text to sanitize
        max_length: Maximum filename length (excluding extension)

    Returns:
        Safe filename string
    """
    # Remove or replace invalid characters
    safe = re.sub(r'[<>:"/\\|?*]', '', text)  # Remove Windows-invalid chars
    safe = re.sub(r'\s+', '_', safe)  # Replace whitespace with underscores
    safe = safe.strip('._')  # Remove leading/trailing dots and underscores

    # Limit length
    if len(safe) > max_length:
        safe = safe[:max_length]

    return safe or "unnamed"


def download_pdf(url: str, output_path: Path, timeout: int = 30) -> bool:
    """
    Download a PDF file.

    Args:
        url: URL of the PDF
        output_path: Path to save the PDF
        timeout: Request timeout in seconds

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()

        # Save the PDF
        with output_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return True

    except Exception as e:
        print(f"    ❌ Error: {e}")
        return False


def main():
    """Main download process."""

    for source in ["commission_controle", "mairie_arretes", "mairie_deliberations"]:

        print(f"\n{'='*60}")
        print(f"Processing: {source}")
        print(f"{'='*60}\n")

        # Load extracted metadata
        metadata_file = EXT_DATA_DIR / f"{source}/extracted_pdf_metadata.json"
        if not metadata_file.exists():
            print(f"❌ Metadata file not found: {metadata_file}")
            print("   Run extract_pdf_urls.py first!")
            continue  # Skip to next source

        with metadata_file.open("r", encoding="utf-8") as f:
            documents = json.load(f)

        print(f"📥 Found {len(documents)} documents to process\n")

        # Create output directory
        pdf_dir = EXT_DATA_DIR / f"{source}/pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)

        # Track progress across all downloads for this source
        success_count = 0
        skip_count = 0
        error_count = 0
        errors = []

        for doc_idx, doc in enumerate(documents, 1):
            # Get main document details
            main_url = doc.get("url")
            if not main_url:
                print(f"  ⚠️  [{doc_idx}/{len(documents)}] Skipping - no URL found")
                continue

            if doc.get("filename"):
                main_filename = doc.get('filename')
            elif doc.get("objet"):
                title = sanitize_filename(doc.get("objet"))
                main_filename = f"{title}.pdf"
            elif doc.get("title"):
                title = sanitize_filename(doc.get("title"))
                main_filename = f"{title}.pdf"
            else:
                main_filename = f"{doc.get('hash')}.pdf"

            main_output_path = pdf_dir / main_filename

            # Download main document
            if main_output_path.exists():
                skip_count += 1
                if doc_idx % 50 == 0:
                    print(f"  ⏭️  [{doc_idx}/{len(documents)}] Skipping (exists): {main_filename}")
            else:
                print(f"  📥 [{doc_idx}/{len(documents)}] Downloading: {main_filename}")
                success = download_pdf(main_url, main_output_path)

                if success:
                    success_count += 1
                    time.sleep(0.1)  # Be respectful to the server
                else:
                    error_count += 1
                    errors.append({"filename": main_filename, "url": main_url})

            # Download annexes if they exist (only for mairie_deliberations)
            annexes = doc.get("annexes", [])
            if annexes:
                for annex_idx, annex in enumerate(annexes, 1):
                    annex_url = annex.get("url")
                    if not annex_url:
                        continue

                    # Create unique filename for annex
                    base_name = main_filename.rsplit('.', 1)[0]  # Remove .pdf extension
                    annex_filename = f"{base_name}_annex_{annex_idx}.pdf"
                    annex_output_path = pdf_dir / annex_filename

                    if annex_output_path.exists():
                        skip_count += 1
                    else:
                        print(f"      📎 Downloading annex {annex_idx}/{len(annexes)}: {annex_filename}")
                        success = download_pdf(annex_url, annex_output_path)

                        if success:
                            success_count += 1
                            time.sleep(0.1)
                        else:
                            error_count += 1
                            errors.append({"filename": annex_filename, "url": annex_url})

            # Progress update every 25 documents
            if doc_idx % 25 == 0:
                print(f"    📊 Progress: {success_count} downloaded, {skip_count} skipped, {error_count} errors")

        # Summary for this source
        print(f"\n{'='*60}")
        print(f"📊 Download Summary - {source}")
        print(f"{'='*60}")
        print(f"  ✅ Successfully downloaded: {success_count}")
        print(f"  ⏭️  Skipped (already exist): {skip_count}")
        print(f"  ❌ Errors: {error_count}")
        print(f"  📁 PDFs saved to: {pdf_dir}")

        # Save error log if any
        if errors:
            error_file = EXT_DATA_DIR / f"{source}/download_errors.json"
            with error_file.open("w", encoding="utf-8") as f:
                json.dump(errors, f, indent=2, ensure_ascii=False)
            print(f"  ⚠️  Error log saved to: {error_file}")


if __name__ == "__main__":
    main()
