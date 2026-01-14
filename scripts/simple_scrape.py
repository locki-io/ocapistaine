"""
Simple example script for testing Firecrawl setup.

This is a minimal example to verify your Firecrawl API key works
and to understand the basic scraping workflow.
"""

# import sys
from pathlib import Path

# # Add src to path
# sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.firecrawl_utils import FirecrawlManager


def test_scrape():
    """Test basic Firecrawl functionality."""

    # Initialize manager (uses FIRECRAWL_API_KEY env var)
    try:
        manager = FirecrawlManager()
        print("✅ Firecrawl initialized successfully\n")
    except Exception as e:
        print(f"❌ Failed to initialize Firecrawl: {e}")
        print("\n💡 Make sure FIRECRAWL_API_KEY is set in your environment:")
        print("   export FIRECRAWL_API_KEY='your_key_here'")
        return

    # Test URL - Audierne homepage
    test_url = "https://www.audierne.bzh/"
    output_dir = Path(__file__).parent.parent / "ext_data" / "test_output"

    print(f"🔥 Testing scrape of: {test_url}")
    print(f"📂 Output directory: {output_dir}\n")

    try:
        result = manager.scrape_url(
            url=test_url,
            output_dir=output_dir,
            formats=["markdown", "html"],
            onlyMainContent=True,
        )

        print("\n📊 Results:")
        print(f"  - Title: {result.get('title', 'N/A')}")
        print(f"  - URL: {result.get('url', 'N/A')}")
        print(f"  - Markdown length: {len(result.get('markdown', ''))} chars")
        print(f"  - HTML length: {len(result.get('html', ''))} chars")

        print(f"\n✅ Success! Check output in: {output_dir}")

    except Exception as e:
        print(f"\n❌ Error during scraping: {e}")


if __name__ == "__main__":
    test_scrape()
