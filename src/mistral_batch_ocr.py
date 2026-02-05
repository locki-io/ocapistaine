"""Process PDFs using Mistral OCR Batch API.

This script processes PDFs from ext_data using Mistral's batch OCR API.
- Handles both text and image-based PDFs
- Respects 50MB file size limit
- Logs success/failure for each document
- Stores returned IDs for agent training
"""

import os
import json
import time
import base64
from pathlib import Path
from typing import Any
from datetime import datetime
from dotenv import load_dotenv
from mistralai import Mistral

from config import EXT_DATA_DIR

# Load environment variables
load_dotenv()

# Constants
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
BATCH_LOG_DIR = EXT_DATA_DIR / "mistral_ocr_logs"
RESULTS_DIR = EXT_DATA_DIR / "mistral_ocr_results"


def encode_pdf_to_base64(pdf_path: Path) -> str | None:
    """
    Encode PDF file to base64.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Base64 encoded string or None if error
    """
    try:
        with pdf_path.open("rb") as f:
            pdf_bytes = f.read()
            return base64.b64encode(pdf_bytes).decode('utf-8')
    except Exception as e:
        print(f"    ❌ Error encoding {pdf_path.name}: {e}")
        return None


def get_file_size_mb(file_path: Path) -> float:
    """Get file size in MB."""
    return file_path.stat().st_size / (1024 * 1024)


def collect_pdfs(max_files: int | None = None) -> list[dict[str, Any]]:
    """
    Collect all PDFs from ext_data directory.

    Args:
        max_files: Maximum number of files to process (None for all)

    Returns:
        List of PDF file info dicts
    """
    print(f"\n{'='*60}")
    print("Collecting PDFs from ext_data")
    print(f"{'='*60}\n")

    pdfs = []
    sources = ["commission_controle", "mairie_arretes", "mairie_deliberations"]

    for source in sources:
        pdf_dir = EXT_DATA_DIR / source / "pdfs"
        if not pdf_dir.exists():
            print(f"  ⚠️  Skipping {source}: directory not found")
            continue

        source_pdfs = list(pdf_dir.glob("*.pdf"))
        print(f"  📁 {source}: {len(source_pdfs)} PDFs found")

        for pdf_path in source_pdfs:
            size_mb = get_file_size_mb(pdf_path)

            pdfs.append({
                "path": pdf_path,
                "source": source,
                "filename": pdf_path.name,
                "size_mb": size_mb,
                "within_limit": size_mb <= MAX_FILE_SIZE_MB,
            })

    # Sort by size (smallest first for pilot)
    pdfs.sort(key=lambda x: x["size_mb"])

    # Limit if specified
    if max_files:
        pdfs = pdfs[:max_files]

    # Stats
    total = len(pdfs)
    within_limit = sum(1 for p in pdfs if p["within_limit"])
    over_limit = total - within_limit

    print(f"\n📊 Collection Summary:")
    print(f"  Total PDFs: {total}")
    print(f"  Within {MAX_FILE_SIZE_MB}MB limit: {within_limit}")
    print(f"  Over limit (will skip): {over_limit}")

    if over_limit > 0:
        avg_over = sum(p["size_mb"] for p in pdfs if not p["within_limit"]) / over_limit
        print(f"  Average size of oversized files: {avg_over:.1f}MB")

    return pdfs


def create_batch_file(pdfs: list[dict[str, Any]], batch_file_path: Path) -> dict[str, Any]:
    """
    Create JSONL batch file for Mistral API.

    Args:
        pdfs: List of PDF info dicts
        batch_file_path: Path to save batch file

    Returns:
        Dict with file stats and metadata
    """
    print(f"\n{'='*60}")
    print("Creating Batch File")
    print(f"{'='*60}\n")

    batch_file_path.parent.mkdir(parents=True, exist_ok=True)

    processed = 0
    skipped_size = 0
    skipped_encoding = 0
    file_id_map = {}  # custom_id -> pdf info

    with batch_file_path.open('w', encoding='utf-8') as f:
        for idx, pdf_info in enumerate(pdfs):
            custom_id = f"{pdf_info['source']}_{idx}_{pdf_info['filename']}"

            # Skip oversized files
            if not pdf_info["within_limit"]:
                print(f"  ⏭️  [{idx+1}/{len(pdfs)}] Skipping (>{MAX_FILE_SIZE_MB}MB): {pdf_info['filename']} ({pdf_info['size_mb']:.1f}MB)")
                skipped_size += 1
                continue

            # Encode PDF
            print(f"  📄 [{idx+1}/{len(pdfs)}] Encoding: {pdf_info['filename']} ({pdf_info['size_mb']:.1f}MB)")
            base64_pdf = encode_pdf_to_base64(pdf_info["path"])

            if not base64_pdf:
                skipped_encoding += 1
                continue

            # Create batch entry
            entry = {
                "custom_id": custom_id,
                "body": {
                    "model": "mistral-ocr-latest",
                    "document": {
                        "type": "document_url",
                        "document_url": f"data:application/pdf;base64,{base64_pdf}"
                    },
                    "table_format": "html",
                    "extract_header": True,
                    "extract_footer": True,
                    "include_image_base64": False,
                }
            }

            f.write(json.dumps(entry) + '\n')
            file_id_map[custom_id] = pdf_info
            processed += 1

    print(f"\n📊 Batch File Summary:")
    print(f"  ✅ Processed: {processed}")
    print(f"  ⏭️  Skipped (size): {skipped_size}")
    print(f"  ❌ Skipped (encoding error): {skipped_encoding}")
    print(f"  📁 Batch file: {batch_file_path}")

    return {
        "processed": processed,
        "skipped_size": skipped_size,
        "skipped_encoding": skipped_encoding,
        "file_id_map": file_id_map,
    }


def submit_batch_job(
    client: Mistral,
    batch_file_path: Path,
    metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Submit batch job to Mistral API.

    Args:
        client: Mistral client
        batch_file_path: Path to batch JSONL file
        metadata: Optional metadata for the job

    Returns:
        Job info dict
    """
    print(f"\n{'='*60}")
    print("Submitting Batch Job")
    print(f"{'='*60}\n")

    # Upload batch file
    print(f"📤 Uploading batch file...")
    batch_data = client.files.upload(
        file={
            "file_name": batch_file_path.name,
            "content": batch_file_path.open("rb")
        },
        purpose="batch"
    )
    print(f"✅ File uploaded: {batch_data.id}")

    # Create batch job
    print(f"\n🚀 Creating batch job...")
    created_job = client.batch.jobs.create(
        input_files=[batch_data.id],
        model="mistral-ocr-latest",
        endpoint="/v1/ocr",
        metadata=metadata or {}
    )

    print(f"✅ Batch job created!")
    print(f"  Job ID: {created_job.id}")
    print(f"  Status: {created_job.status}")
    print(f"  Created: {created_job.created_at}")

    return {
        "job_id": created_job.id,
        "file_id": batch_data.id,
        "status": created_job.status,
        "created_at": created_job.created_at,
    }


def monitor_batch_job(client: Mistral, job_id: str, poll_interval: int = 30) -> dict[str, Any]:
    """
    Monitor batch job until completion.

    Args:
        client: Mistral client
        job_id: Batch job ID
        poll_interval: Seconds between status checks

    Returns:
        Final job status dict
    """
    print(f"\n{'='*60}")
    print("Monitoring Batch Job")
    print(f"{'='*60}\n")
    print(f"  Job ID: {job_id}")
    print(f"  Checking status every {poll_interval}s...\n")

    start_time = time.time()
    while True:
        job = client.batch.jobs.get(job_id=job_id)
        elapsed = int(time.time() - start_time)

        status_emoji = {
            "QUEUED": "⏳",
            "RUNNING": "🔄",
            "SUCCESS": "✅",
            "FAILED": "❌",
            "TIMEOUT_EXCEEDED": "⏱️",
            "CANCELLATION_REQUESTED": "🛑",
            "CANCELLED": "🛑",
        }.get(job.status, "❓")

        print(f"  {status_emoji} Status: {job.status} (elapsed: {elapsed}s)")

        if job.status in ["SUCCESS", "FAILED", "TIMEOUT_EXCEEDED", "CANCELLED"]:
            break

        time.sleep(poll_interval)

    print(f"\n🏁 Job completed with status: {job.status}")

    return {
        "job_id": job.id,
        "status": job.status,
        "total_requests": job.total_requests,
        "succeeded": getattr(job, "succeeded_requests", 0),
        "failed": getattr(job, "failed_requests", 0),
        "output_file": getattr(job, "output_file", None),
        "error_file": getattr(job, "error_file", None),
    }


def download_results(
    client: Mistral,
    job_result: dict[str, Any],
    output_dir: Path
) -> tuple[Path | None, Path | None]:
    """
    Download batch job results.

    Args:
        client: Mistral client
        job_result: Job result dict from monitor_batch_job
        output_dir: Directory to save results

    Returns:
        Tuple of (success_file_path, error_file_path)
    """
    print(f"\n{'='*60}")
    print("Downloading Results")
    print(f"{'='*60}\n")

    output_dir.mkdir(parents=True, exist_ok=True)

    success_file = None
    error_file = None

    # Download success results
    if job_result.get("output_file"):
        print(f"📥 Downloading success results...")
        success_content = client.files.download(file_id=job_result["output_file"])
        success_file = output_dir / f"results_{job_result['job_id']}.jsonl"

        with success_file.open('wb') as f:
            f.write(success_content.read())

        print(f"✅ Saved to: {success_file}")

    # Download error results
    if job_result.get("error_file"):
        print(f"\n📥 Downloading error results...")
        error_content = client.files.download(file_id=job_result["error_file"])
        error_file = output_dir / f"errors_{job_result['job_id']}.jsonl"

        with error_file.open('wb') as f:
            f.write(error_content.read())

        print(f"✅ Saved to: {error_file}")

    return success_file, error_file


def process_results(
    success_file: Path | None,
    error_file: Path | None,
    file_id_map: dict[str, Any],
    log_dir: Path
) -> dict[str, Any]:
    """
    Process results and generate detailed logs.

    Args:
        success_file: Path to success JSONL file
        error_file: Path to error JSONL file
        file_id_map: Mapping of custom_id to PDF info
        log_dir: Directory for detailed logs

    Returns:
        Summary statistics dict
    """
    print(f"\n{'='*60}")
    print("Processing Results")
    print(f"{'='*60}\n")

    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    success_log = []
    error_log = []
    training_ids = []

    # Process successes
    if success_file and success_file.exists():
        print(f"📄 Processing {success_file.name}...")
        with success_file.open('r', encoding='utf-8') as f:
            for line in f:
                result = json.loads(line)
                custom_id = result.get("custom_id")
                pdf_info = file_id_map.get(custom_id, {})

                success_entry = {
                    "custom_id": custom_id,
                    "filename": pdf_info.get("filename"),
                    "source": pdf_info.get("source"),
                    "size_mb": pdf_info.get("size_mb"),
                    "pages_processed": len(result.get("response", {}).get("body", {}).get("pages", [])),
                    "model": result.get("response", {}).get("body", {}).get("model"),
                    "timestamp": timestamp,
                }

                success_log.append(success_entry)
                training_ids.append({
                    "custom_id": custom_id,
                    "filename": pdf_info.get("filename"),
                    "result_id": result.get("id"),
                })

        print(f"  ✅ {len(success_log)} successful results")

    # Process errors
    if error_file and error_file.exists():
        print(f"\n📄 Processing {error_file.name}...")
        with error_file.open('r', encoding='utf-8') as f:
            for line in f:
                error = json.loads(line)
                custom_id = error.get("custom_id")
                pdf_info = file_id_map.get(custom_id, {})

                error_entry = {
                    "custom_id": custom_id,
                    "filename": pdf_info.get("filename"),
                    "source": pdf_info.get("source"),
                    "size_mb": pdf_info.get("size_mb"),
                    "error": error.get("error", {}),
                    "timestamp": timestamp,
                }

                error_log.append(error_entry)

        print(f"  ❌ {len(error_log)} failed results")

    # Save logs
    success_log_path = log_dir / f"success_log_{timestamp}.json"
    error_log_path = log_dir / f"error_log_{timestamp}.json"
    training_ids_path = log_dir / f"training_ids_{timestamp}.json"

    with success_log_path.open('w', encoding='utf-8') as f:
        json.dump(success_log, f, indent=2, ensure_ascii=False)

    with error_log_path.open('w', encoding='utf-8') as f:
        json.dump(error_log, f, indent=2, ensure_ascii=False)

    with training_ids_path.open('w', encoding='utf-8') as f:
        json.dump(training_ids, f, indent=2, ensure_ascii=False)

    print(f"\n📊 Logs saved:")
    print(f"  ✅ Success log: {success_log_path}")
    print(f"  ❌ Error log: {error_log_path}")
    print(f"  🎯 Training IDs: {training_ids_path}")

    return {
        "total_success": len(success_log),
        "total_errors": len(error_log),
        "success_log_path": str(success_log_path),
        "error_log_path": str(error_log_path),
        "training_ids_path": str(training_ids_path),
    }


def main(max_files: int = 100, poll_interval: int = 30):
    """
    Main batch OCR processing pipeline.

    Args:
        max_files: Maximum number of files to process (pilot mode)
        poll_interval: Seconds between job status checks
    """
    print(f"\n{'='*60}")
    print("Mistral Batch OCR Processing")
    print(f"{'='*60}")
    print(f"  Max files: {max_files}")
    print(f"  File size limit: {MAX_FILE_SIZE_MB}MB")
    print(f"{'='*60}\n")

    # Check API key
    api_key = os.getenv("MISTRAL_AI_KEY")
    if not api_key:
        raise ValueError(
            "MISTRAL_AI_KEY not found in environment.\n"
            "Please add it to your .env file:\n"
            "  MISTRAL_AI_KEY=your-key-here"
        )

    # Initialize client
    client = Mistral(api_key=api_key)

    # Step 1: Collect PDFs
    pdfs = collect_pdfs(max_files=max_files)

    if not pdfs:
        print("\n❌ No PDFs found to process")
        return

    # Step 2: Create batch file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_file_path = BATCH_LOG_DIR / f"batch_{timestamp}.jsonl"
    batch_stats = create_batch_file(pdfs, batch_file_path)

    if batch_stats["processed"] == 0:
        print("\n❌ No files were successfully processed into batch file")
        return

    # Step 3: Submit batch job
    job_info = submit_batch_job(
        client,
        batch_file_path,
        metadata={
            "pilot": True,
            "max_files": max_files,
            "timestamp": timestamp,
        }
    )

    # Save job info
    job_info_path = BATCH_LOG_DIR / f"job_info_{timestamp}.json"
    with job_info_path.open('w', encoding='utf-8') as f:
        json.dump(job_info, f, indent=2)
    print(f"\n📝 Job info saved to: {job_info_path}")

    # Step 4: Monitor job
    job_result = monitor_batch_job(client, job_info["job_id"], poll_interval)

    # Step 5: Download results
    success_file, error_file = download_results(client, job_result, RESULTS_DIR)

    # Step 6: Process results and generate logs
    summary = process_results(
        success_file,
        error_file,
        batch_stats["file_id_map"],
        BATCH_LOG_DIR
    )

    # Final summary
    print(f"\n{'='*60}")
    print("🎉 Batch Processing Complete!")
    print(f"{'='*60}")
    print(f"  Total files submitted: {batch_stats['processed']}")
    print(f"  Successful: {summary['total_success']}")
    print(f"  Failed: {summary['total_errors']}")
    print(f"  Success rate: {summary['total_success'] / batch_stats['processed'] * 100:.1f}%")
    print(f"\n📁 Results saved to: {RESULTS_DIR}")
    print(f"📁 Logs saved to: {BATCH_LOG_DIR}")
    print(f"\n🎯 Training IDs saved for agent training:")
    print(f"   {summary['training_ids_path']}")


if __name__ == "__main__":
    # Pilot mode: Process 100 files
    main(max_files=100, poll_interval=30)

    # To process all files, use:
    # main(max_files=None, poll_interval=60)
