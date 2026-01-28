"""Main script for orchestrating Firecrawl operations on municipal documents."""

import asyncio
import argparse
import sys
import os
from pathlib import Path

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.config import DATA_SOURCES
from app.processors.crawl_processor import CrawlProcessor, CrawlWorkflowConfig

async def main_async():
    """Async main entry point."""
    parser = argparse.ArgumentParser(
        description="Crawl and process municipal documents from Audierne website"
    )

    parser.add_argument(
        "--source",
        type=str,
        choices=[s.name for s in DATA_SOURCES] + ["all"],
        default="all",
        help="Which data source to process (default: all)",
    )

    parser.add_argument(
        "--mode",
        type=str,
        choices=["scrape", "crawl"],
        default="scrape",
        help="scrape = single page, crawl = full site (default: scrape)",
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="Maximum pages to crawl in crawl mode (default: 100)",
    )

    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Firecrawl API key (or set FIRECRAWL_API_KEY env var)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without actually crawling",
    )

    args = parser.parse_args()

    # Filter sources
    if args.source == "all":
        sources_to_process = DATA_SOURCES
    else:
        sources_to_process = [s for s in DATA_SOURCES if s.name == args.source]

    if not sources_to_process:
        print(f"❌ Error: No data source found with name '{args.source}'")
        sys.exit(1)

    # Initialize Processor
    processor = CrawlProcessor()
    
    # Check dependencies
    # We suppress output here as the processor handles logging
    await processor.check_dependencies()

    # Create config
    config = CrawlWorkflowConfig(
        mode=args.mode,
        max_pages=args.max_pages,
        dry_run=args.dry_run,
        api_key=args.api_key
    )

    print(f"\n🚀 Starting crawl operation via CrawlProcessor")
    print(f"   Mode: {args.mode}")
    print(f"   Sources: {len(sources_to_process)}")

    # Run Workflow
    result = await processor.run_workflow(sources_to_process, config)

    # Summary Output
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    
    for source in result.successful_sources:
        print(f"  ✅ SUCCESS: {source}")
    for source in result.failed_sources:
        print(f"  ❌ FAILED: {source}")

    failed_count = len(result.failed_sources)
    print(f"\n  Total: {result.sources_processed} | Success: {len(result.successful_sources)} | Failed: {failed_count}")
    print("=" * 80 + "\n")

    sys.exit(0 if failed_count == 0 else 1)


def main():
    """Sync wrapper for async main."""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled by user")
        sys.exit(130)

if __name__ == "__main__":
    main()
