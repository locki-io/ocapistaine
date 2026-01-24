"""Download PDFs from extracted metadata."""

import json
import time
from pathlib import Path
import requests
from config import EXT_DATA_DIR


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

    for source in ["commission_controle", "mairie_arretes"]:

        # Load extracted metadata
        metadata_file = EXT_DATA_DIR / f"{source}/extracted_pdf_metadata.json"
        if not metadata_file.exists():
            print(f"❌ Metadata file not found: {metadata_file}")
            print("   Run extract_pdf_urls.py first!")

        with metadata_file.open("r", encoding="utf-8") as f:
            documents = json.load(f)

        print(f"📥 Found {len(documents)} PDFs to download\n")

        # Create output directory
        pdf_dir = EXT_DATA_DIR / f"{source}/pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)

        # Track progress
        success_count = 0
        skip_count = 0
        error_count = 0
        errors = []

        for idx, doc in enumerate(documents, 1):
            url = doc["url"]
            filename = doc["filename"]
            output_path = pdf_dir / filename

            # Skip if already downloaded
            if output_path.exists():
                skip_count += 1
                if idx % 50 == 0:
                    print(f"  [{idx}/{len(documents)}] Skipping (already exists): {filename}")
                continue

            print(f"  [{idx}/{len(documents)}] Downloading: {filename}")

            success = download_pdf(url, output_path)

            if success:
                success_count += 1
                # Small delay to be respectful of the server
                time.sleep(0.1)
            else:
                error_count += 1
                errors.append({"filename": filename, "url": url})

            # Progress update every 25 files
            if idx % 25 == 0:
                print(f"    Progress: {success_count} downloaded, {skip_count} skipped, {error_count} errors")

            # Summary
            print(f"\n📊 Download Summary:")
            print(f"  ✅ Successfully downloaded: {success_count}")
            print(f"  ⏭️  Skipped (already exist): {skip_count}")
            print(f"  ❌ Errors: {error_count}")
            print(f"  📁 PDFs saved to: {pdf_dir}")

            # Save error log if any
            if errors:
                error_file = EXT_DATA_DIR / "download_errors.json"
                with error_file.open("w", encoding="utf-8") as f:
                    json.dump(errors, f, indent=2, ensure_ascii=False)
                print(f"  ⚠️  Error log saved to: {error_file}")


if __name__ == "__main__":
    main()
