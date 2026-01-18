"""Main script for orchestrating Firecrawl operations on municipal documents."""

import argparse
import sys
from pathlib import Path

from config import DATA_SOURCES, FIRECRAWL_CONFIG, CRAWL_FULL_CONFIG, DataSource
from firecrawl_utils import FirecrawlManager


def crawl_data_source(
    source: DataSource,
    manager: FirecrawlManager,
    mode: str = "scrape",
    formats: list[str] = ["markdown", "html"],
    max_pages: int = 100,
) -> bool:
    """
    Crawl a single data source.

    Args:
        source: DataSource configuration
        manager: FirecrawlManager instance
        mode: "scrape" for single page, "crawl" for full site
        max_pages: Maximum pages to crawl (only for crawl mode)

    Returns:
        bool: True if successful, False otherwise
    """
    print(f"\n{'='*80}")
    print(f"📂 Processing: {source.name}")
    print(f"   URL: {source.url}")
    print(f"   Method: {source.method}")
    print(f"   Output: {source.output_dir}")
    if source.expected_count:
        print(f"   Expected count: {source.expected_count}")
    print(f"{'='*80}\n")

    try:
        if mode == "scrape":
            # Scrape single page (useful for getting structure first)
            manager.scrape_url(
                url=source.url,
                output_dir=source.output_dir,
                formats=formats,
                **FIRECRAWL_CONFIG,
            )
        else:  # crawl
            # Crawl entire website section with crawl-specific config
            manager.crawl_website(
                url=source.url,
                output_dir=source.output_dir,
                max_pages=max_pages,
                **CRAWL_FULL_CONFIG,
            )

        print(f"✅ Completed: {source.name}\n")
        return True

    except Exception as e:
        print(f"❌ Failed: {source.name}")
        print(f"   Error: {e}\n")
        return False


def main():
    """Main entry point for municipal document crawling."""
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

    # Filter sources based on argument
    if args.source == "all":
        sources_to_process = DATA_SOURCES
    else:
        sources_to_process = [s for s in DATA_SOURCES if s.name == args.source]

    if not sources_to_process:
        print(f"❌ Error: No data source found with name '{args.source}'")
        sys.exit(1)

    # Dry run mode
    if args.dry_run:
        print("🔍 DRY RUN MODE - No actual crawling will be performed\n")
        for source in sources_to_process:
            print(f"Would process: {source.name}")
            print(f"  URL: {source.url}")
            print(f"  Mode: {args.mode}")
            print(f"  Output: {source.output_dir}\n")
        sys.exit(0)

    # Initialize Firecrawl manager
    try:
        manager = FirecrawlManager(api_key=args.api_key)
    except Exception as e:
        print(f"❌ Failed to initialize Firecrawl: {e}")
        print("\n💡 Tip: Set FIRECRAWL_API_KEY environment variable or use --api-key")
        sys.exit(1)

    # Process each source
    print(f"\n🚀 Starting crawl operation")
    print(f"   Mode: {args.mode}")
    print(f"   Sources: {len(sources_to_process)}")
    if args.mode == "crawl":
        print(f"   Max pages per source: {args.max_pages}")

    results = []
    for source in sources_to_process:
        success = crawl_data_source(
            source=source,
            manager=manager,
            mode=args.mode,
            max_pages=args.max_pages,
        )
        results.append((source.name, success))

    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)

    successful = sum(1 for _, success in results if success)
    failed = len(results) - successful

    for name, success in results:
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"  {status}: {name}")

    print(f"\n  Total: {len(results)} | Success: {successful} | Failed: {failed}")
    print("=" * 80 + "\n")

    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
