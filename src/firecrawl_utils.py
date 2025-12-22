"""Utilities for Firecrawl operations and document processing."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from firecrawl import FirecrawlApp


class FirecrawlManager:
    """Manages Firecrawl operations with logging and error handling."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize Firecrawl manager.

        Args:
            api_key: Firecrawl API key. If None, will use FIRECRAWL_API_KEY env var.
        """
        self.app = FirecrawlApp(api_key=api_key) if api_key else FirecrawlApp()
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def scrape_url(
        self,
        url: str,
        output_dir: Path,
        formats: list[str] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Scrape a single URL with Firecrawl.

        Args:
            url: URL to scrape
            output_dir: Directory to save results
            formats: Output formats (e.g., ["markdown", "html"])
            **kwargs: Additional Firecrawl parameters

        Returns:
            dict: Scraping results including metadata
        """
        if formats is None:
            formats = ["markdown"]

        try:
            print(f"🔥 Scraping: {url}")
            result = self.app.scrape_url(url, params={"formats": formats, **kwargs})

            # Save results
            self._save_scrape_result(result, output_dir, url)

            print(f"✅ Successfully scraped: {url}")
            return result

        except Exception as e:
            print(f"❌ Error scraping {url}: {e}")
            self._log_error(url, str(e), output_dir)
            raise

    def crawl_website(
        self,
        url: str,
        output_dir: Path,
        max_pages: int = 100,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Crawl an entire website with Firecrawl.

        Args:
            url: Base URL to crawl
            output_dir: Directory to save results
            max_pages: Maximum number of pages to crawl
            **kwargs: Additional Firecrawl parameters

        Returns:
            dict: Crawling results including all pages
        """
        try:
            print(f"🔥 Crawling website: {url} (max {max_pages} pages)")

            crawl_params = {
                "limit": max_pages,
                "scrapeOptions": {"formats": ["markdown", "html"]},
                **kwargs,
            }

            result = self.app.crawl_url(url, params=crawl_params, wait_until_done=True)

            # Save results
            self._save_crawl_result(result, output_dir, url)

            page_count = len(result.get("data", []))
            print(f"✅ Successfully crawled {page_count} pages from: {url}")

            return result

        except Exception as e:
            print(f"❌ Error crawling {url}: {e}")
            self._log_error(url, str(e), output_dir)
            raise

    def _save_scrape_result(
        self, result: dict[str, Any], output_dir: Path, url: str
    ) -> None:
        """Save scrape result to disk."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate safe filename from URL
        filename = self._url_to_filename(url)

        # Save markdown if available
        if "markdown" in result:
            md_path = output_dir / f"{filename}.md"
            md_path.write_text(result["markdown"], encoding="utf-8")

        # Save HTML if available
        if "html" in result:
            html_path = output_dir / f"{filename}.html"
            html_path.write_text(result["html"], encoding="utf-8")

        # Save complete JSON result with metadata
        json_path = output_dir / f"{filename}_metadata.json"
        json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    def _save_crawl_result(
        self, result: dict[str, Any], output_dir: Path, base_url: str
    ) -> None:
        """Save crawl result to disk."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save individual pages
        for idx, page_data in enumerate(result.get("data", [])):
            page_url = page_data.get("url", f"page_{idx}")
            filename = self._url_to_filename(page_url)

            if "markdown" in page_data:
                md_path = output_dir / f"{filename}.md"
                md_path.write_text(page_data["markdown"], encoding="utf-8")

            if "html" in page_data:
                html_path = output_dir / f"{filename}.html"
                html_path.write_text(page_data["html"], encoding="utf-8")

        # Save complete crawl metadata
        metadata_path = output_dir / f"crawl_metadata_{self.session_id}.json"
        metadata_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Create index file
        self._create_index(result, output_dir)

    def _create_index(self, result: dict[str, Any], output_dir: Path) -> None:
        """Create an index file listing all crawled pages."""
        index_path = output_dir / f"index_{self.session_id}.md"

        with index_path.open("w", encoding="utf-8") as f:
            f.write(f"# Crawl Index - {self.session_id}\n\n")
            f.write(f"Total pages: {len(result.get('data', []))}\n\n")

            for idx, page_data in enumerate(result.get("data", []), 1):
                url = page_data.get("url", "Unknown")
                title = page_data.get("title", "Untitled")
                f.write(f"{idx}. [{title}]({url})\n")

    def _url_to_filename(self, url: str) -> str:
        """Convert URL to safe filename."""
        # Remove protocol and replace special chars
        filename = url.replace("https://", "").replace("http://", "")
        filename = filename.replace("/", "_").replace("?", "_").replace("&", "_")
        filename = filename.replace("=", "_").replace(":", "_")

        # Limit length
        if len(filename) > 200:
            filename = filename[:200]

        return filename or "page"

    def _log_error(self, url: str, error: str, output_dir: Path) -> None:
        """Log error to file."""
        error_log = output_dir / "errors.log"
        timestamp = datetime.now().isoformat()

        with error_log.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {url}\n")
            f.write(f"Error: {error}\n")
            f.write("-" * 80 + "\n")


def extract_documents_from_page(page_markdown: str) -> list[dict[str, str]]:
    """
    Extract document links and metadata from scraped page content.

    This is a placeholder for custom extraction logic based on the
    specific structure of the Audierne municipal website.

    Args:
        page_markdown: Markdown content from scraped page

    Returns:
        list: Document metadata dicts with 'url', 'title', 'date', etc.
    """
    # TODO: Implement specific extraction logic for Audierne website
    # This will depend on the actual HTML/markdown structure
    documents = []

    # Example structure (to be customized):
    # - Parse markdown for document links
    # - Extract titles, dates, document types
    # - Return structured data

    return documents
