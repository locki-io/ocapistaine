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
    ),
    DataSource(
        name="mairie_deliberations",
        url="https://www.audierne.bzh/deliberations-conseil-municipal/",
        method="firecrawl+ocr",
        output_dir=EXT_DATA_DIR / "mairie_deliberations",
        description="Délibérations du conseil municipal",
        expected_count=4014,  # Requires infinite scroll actions to capture all documents
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
        # ".*deliberations.*",  # Délibérations and related pages
        ".*documentheque(?!.*documents_category=49).*",  # Document library (exclude category=49)
    ],
    "exclude_paths": [  # URL patterns to exclude
        ".*documents_category=49$",  # Exclude commission_controle (separate data source)
    ],
    "max_discovery_depth": 3,  # Max depth from base URL (number of slashes in pathname)
}

# Combined config for crawl operations (merges FIRECRAWL_CONFIG + CRAWL_CONFIG)
CRAWL_FULL_CONFIG = {**FIRECRAWL_CONFIG, **CRAWL_CONFIG}

# Actions for handling dynamic content (JavaScript interactions)
# These handle pagination buttons and infinite scroll

# Actions for mairie_deliberations (infinite scroll)
# Firecrawl limits: max 50 actions, max 60s total wait time
# Strategy: Scroll 24 times with minimal waits to load as much content as possible
DELIBERATIONS_ACTIONS = [
    {"type": "wait", "milliseconds": 2000},  # Initial load (2s)
]
# Add 24 scroll sequences (48 actions) = 24 scrolls + 24 waits
# Total wait time: 2s + (24 * 1s) = 26s (well under 60s limit)
for _ in range(24):  # Scroll down 24 times
    DELIBERATIONS_ACTIONS.extend([
        {"type": "press", "key": "End"},  # Scroll to bottom
        {"type": "wait", "milliseconds": 1000},  # Wait 1s for content to load
    ])

# Actions for mairie_arretes (pagination with "Afficher plus" / "Show more" buttons)
# Each category page loads 10 documents initially, then requires clicks to load more
# Button selector: #load-older-posts
# Strategy: Click the button multiple times with waits to load all paginated content
# Firecrawl limits: max 50 actions, max 60s wait time
ARRETES_ACTIONS = [
    {"type": "wait", "milliseconds": 2000},  # Initial load (2s)
]
# Click "Show more" up to 10 times to load paginated documents
# Total: 1 wait + (10 clicks + 10 waits) = 21 actions, ~22s total wait time
for _ in range(10):
    ARRETES_ACTIONS.extend([
        {"type": "click", "selector": "#load-older-posts"},  # Click "Show more"
        {"type": "wait", "milliseconds": 2000},  # Wait for content to load
    ])

# Source-specific configurations (can override FIRECRAWL_CONFIG)
SOURCE_CONFIGS = {
    "mairie_deliberations": {
        **FIRECRAWL_CONFIG,
        "actions": DELIBERATIONS_ACTIONS,
    },
    "mairie_arretes": {
        **FIRECRAWL_CONFIG,
        "actions": ARRETES_ACTIONS,
    },
    "commission_controle": FIRECRAWL_CONFIG,  # No special actions needed
}

# OCR configuration (placeholder for future implementation)
OCR_CONFIG = {
    "language": "fra",  # French
    "dpi": 300,
    "output_format": "text",
}
