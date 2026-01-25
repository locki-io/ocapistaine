"""Utilities for Firecrawl operations and document processing."""

import json
import re
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
from firecrawl import Firecrawl

load_dotenv()
FIRECRAWL_API_KEY_ENV = os.getenv("FIRECRAWL_API_KEY")


class FirecrawlManager:
    """Manages Firecrawl operations with logging and error handling."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize Firecrawl manager.

        Args:
            api_key: Firecrawl API key. If None, will use FIRECRAWL_API_KEY env var.
        """

        self.app = Firecrawl(api_key=api_key) if api_key else Firecrawl()
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def scrape_url(
        self,
        url: str,
        output_dir: Path,
        formats: list[str] | None = None,
        **kwargs,
    ) -> Any:
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
            result = self.app.scrape(url, formats=formats, **kwargs)

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
    ) -> Any:
        """
        Crawl an entire website with Firecrawl.

        Args:
            url: Base URL to crawl
            output_dir: Directory to save results
            max_pages: Maximum number of pages to crawl
            **kwargs: Additional Firecrawl parameters (both crawl and scrape options)

        Returns:
            CrawlJob: Crawling results including all pages
        """
        # Separate crawl-specific params from scrape options
        crawl_params = {
            "limit": max_pages,
        }

        # Crawl-specific parameters (passed directly to crawl())
        # Python SDK uses snake_case parameter names
        crawl_param_keys = {
            "include_paths",
            "exclude_paths",
            "max_discovery_depth",
            "ignore_sitemap",
            "allow_external_links",
            "crawl_entire_domain",
            "allow_subdomains",
            "delay",
            "max_concurrency",
            "webhook",
            "zero_data_retention",
            "poll_interval",
            "timeout",
            "request_timeout",
            "prompt",  # Natural language crawl prompt
        }

        # Extract crawl params from kwargs
        for key in crawl_param_keys:
            if key in kwargs:
                crawl_params[key] = kwargs[key]

        # Remaining kwargs are scrape options
        scrape_opts = {k: v for k, v in kwargs.items() if k not in crawl_param_keys}
        scrape_opts["formats"] = ["markdown", "html"]

        crawl_params["scrape_options"] = scrape_opts

        try:
            print(f"🔥 Crawling website: {url} (max {max_pages} pages)")

            result = self.app.crawl(url, **crawl_params)

            # Save results
            self._save_crawl_result(result, output_dir, url)

            page_count = len(result.data) if hasattr(result, "data") else 0
            print(f"✅ Successfully crawled {page_count} pages from: {url}")

            return result

        except Exception as e:
            print(f"❌ Error crawling {url}: {e}")
            self._log_error(url, str(e), output_dir)
            raise

    def _save_scrape_result(
        self, result: Any, output_dir: Path, url: str
    ) -> None:
        """Save scrape result to disk."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate safe filename from URL
        filename = self._url_to_filename(url)

        # Save markdown if available
        if hasattr(result, "markdown") and result.markdown:
            md_path = output_dir / f"{filename}.md"
            md_path.write_text(result.markdown, encoding="utf-8")

        # Save HTML if available
        if hasattr(result, "html") and result.html:
            html_path = output_dir / f"{filename}.html"
            html_path.write_text(result.html, encoding="utf-8")

        # Save complete JSON result with metadata
        # Convert Document object to dict for JSON serialization
        json_path = output_dir / f"{filename}_metadata.json"
        metadata_dict = {
            "url": url,
            "markdown": result.markdown if hasattr(result, "markdown") else None,
            "html": result.html if hasattr(result, "html") else None,
            "metadata": result.metadata.__dict__ if hasattr(result, "metadata") else None,
            "links": result.links if hasattr(result, "links") else None,
        }
        json_path.write_text(json.dumps(metadata_dict, indent=2, ensure_ascii=False))

    def _save_crawl_result(
        self, result: Any, output_dir: Path, base_url: str
    ) -> None:
        """Save crawl result to disk."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Get data from CrawlJob object
        pages = result.data if hasattr(result, "data") else []

        # Save individual pages (each is a Document object)
        for idx, page_doc in enumerate(pages):
            # Get URL from metadata or use fallback
            page_url = (
                page_doc.metadata.source_url
                if hasattr(page_doc, "metadata") and hasattr(page_doc.metadata, "source_url")
                else f"page_{idx}"
            )
            filename = self._url_to_filename(page_url)

            # Save markdown if available
            if hasattr(page_doc, "markdown") and page_doc.markdown:
                md_path = output_dir / f"{filename}.md"
                md_path.write_text(page_doc.markdown, encoding="utf-8")

            # Save HTML if available
            if hasattr(page_doc, "html") and page_doc.html:
                html_path = output_dir / f"{filename}.html"
                html_path.write_text(page_doc.html, encoding="utf-8")

        # Save complete crawl metadata
        # Convert CrawlJob to dict for JSON serialization
        metadata_path = output_dir / f"crawl_metadata_{self.session_id}.json"
        crawl_summary = {
            "base_url": base_url,
            "session_id": self.session_id,
            "total_pages": len(pages),
            "status": result.status if hasattr(result, "status") else "unknown",
            "pages": [
                {
                    "url": (
                        page.metadata.source_url
                        if hasattr(page, "metadata") and hasattr(page.metadata, "source_url")
                        else None
                    ),
                    "title": (
                        page.metadata.title
                        if hasattr(page, "metadata") and hasattr(page.metadata, "title")
                        else None
                    ),
                }
                for page in pages
            ],
        }
        metadata_path.write_text(
            json.dumps(crawl_summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Create index file
        self._create_index(result, output_dir)

    def _create_index(self, result: Any, output_dir: Path) -> None:
        """Create an index file listing all crawled pages."""
        index_path = output_dir / f"index_{self.session_id}.md"

        pages = result.data if hasattr(result, "data") else []

        with index_path.open("w", encoding="utf-8") as f:
            f.write(f"# Crawl Index - {self.session_id}\n\n")
            f.write(f"Total pages: {len(pages)}\n\n")

            for idx, page_doc in enumerate(pages, 1):
                url = (
                    page_doc.metadata.source_url
                    if hasattr(page_doc, "metadata") and hasattr(page_doc.metadata, "source_url")
                    else "Unknown"
                )
                title = (
                    page_doc.metadata.title
                    if hasattr(page_doc, "metadata") and hasattr(page_doc.metadata, "title")
                    else "Untitled"
                )
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

    documents = []

    # Find all PDF URLs in the markdown
    pdf_pattern = r'\[(?:View|Download|Consulter|Télécharger)[^\]]*\]\((https://www\.audierne\.bzh/wp-content/uploads/[^)]+\.pdf)[^\)]*\)'
    pdf_urls = set(re.findall(pdf_pattern, page_markdown))

    # For each unique PDF URL, extract metadata
    for pdf_url in pdf_urls:
        # Find the section of text before this PDF URL (up to 500 chars back)
        url_pos = page_markdown.find(pdf_url)
        if url_pos == -1:
            continue

        # Get context before the URL
        start_pos = max(0, url_pos - 500)
        context = page_markdown[start_pos:url_pos]

        # Extract title (typically the last heading or first substantial line before metadata)
        title_match = re.search(r'(?:^|\n)([^\n-]+)\n\n-\s', context)
        title = title_match.group(1).strip() if title_match else "Untitled"

        # Remove "arrests" or other category labels from title
        title = re.sub(r'^arrests\s*', '', title, flags=re.IGNORECASE)

        # Extract date
        date_patterns = [
            r'-\s*(\w+\s+\d{1,2},?\s+\d{4})',  # "January 16, 2026" or "December 2024"
            r'-\s*(\d{1,2}\s+\w+\s+\d{4})',    # "20 décembre 2023"
            r'-\s*(\w+\s+\d{4})',              # "December 2024"
        ]
        date_str = None
        for pattern in date_patterns:
            date_match = re.search(pattern, context)
            if date_match:
                date_str = date_match.group(1).strip()
                break

        # Extract file size
        size_match = re.search(r'-\s*(\d+\s*[KM]B)', context, re.IGNORECASE)
        file_size = size_match.group(1).strip() if size_match else None

        # Extract language
        lang_match = re.search(r'-\s*(French|Français)', context, re.IGNORECASE)
        language = lang_match.group(1).strip() if lang_match else "French"

        # Extract filename from URL
        filename = pdf_url.split('/')[-1]

        documents.append({
            "url": pdf_url,
            "title": title,
            "date": date_str,
            "file_size": file_size,
            "language": language,
            "filename": filename,
            "file_type": "pdf",
        })

    return documents
