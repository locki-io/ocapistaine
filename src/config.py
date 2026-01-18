"""Configuration for Firecrawl data sources."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class DataSource:
    """Configuration for a data source to be scraped."""

    name: str
    url: str
    method: Literal["firecrawl", "firecrawl+ocr", "ocr"]
    output_dir: Path
    description: str = ""
    expected_count: int | None = None

    def __post_init__(self):
        """Ensure output directory exists."""
        self.output_dir.mkdir(parents=True, exist_ok=True)


# Base directory for external data
EXT_DATA_DIR = Path(__file__).parent.parent / "ext_data"

# Define all data sources from README.md
DATA_SOURCES = [
    DataSource(
        name="mairie_arretes",
        url="https://www.audierne.bzh/publications-arretes/",
        method="firecrawl+ocr",
        output_dir=EXT_DATA_DIR / "mairie_arretes",
        description="Arrêtés - publications (actes + annexes)",
        expected_count=4010,
    ),
    DataSource(
        name="mairie_deliberations",
        url="https://www.audierne.bzh/deliberations-conseil-municipal/",
        method="firecrawl+ocr",
        output_dir=EXT_DATA_DIR / "mairie_deliberations",
        description="Délibérations du conseil municipal",
    ),
    DataSource(
        name="commission_controle",
        url="https://www.audierne.bzh/systeme/documentheque/?documents_category=49",
        method="firecrawl+ocr",
        output_dir=EXT_DATA_DIR / "commission_controle",
        description="Campagne commission de contrôle",
    ),
]

# Firecrawl scrape configuration (for both scrape and crawl operations)
FIRECRAWL_CONFIG = {
    "only_main_content": True,
    "include_tags": ["article", "main", "div.content"],
    "exclude_tags": ["nav", "footer", "header", "aside"],
    "wait_for": 2000,  # Wait 2 seconds for dynamic content
}

# Crawl-specific configuration (only used for crawl operations)
CRAWL_CONFIG = {
    "crawl_entire_domain": True,  # Allow crawling entire audierne.bzh domain
    "include_paths": [  # URL pathname regex patterns to include
        ".*publications-arretes.*",  # Arrêtés and related pages
        ".*deliberations.*",  # Délibérations and related pages
        ".*documentheque.*",  # Document library pages (all categories)
    ],
    "max_discovery_depth": 3,  # Max depth from base URL (number of slashes in pathname)
}

# Combined config for crawl operations (merges FIRECRAWL_CONFIG + CRAWL_CONFIG)
CRAWL_FULL_CONFIG = {**FIRECRAWL_CONFIG, **CRAWL_CONFIG}

# OCR configuration (placeholder for future implementation)
OCR_CONFIG = {
    "language": "fra",  # French
    "dpi": 300,
    "output_format": "text",
}
