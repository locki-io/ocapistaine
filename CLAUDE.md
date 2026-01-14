# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**OCapistaine** is a Python-based RAG (Retrieval Augmented Generation) system and AI agent for civic transparency in Audierne, France. It supports the audierne2026.fr participatory democracy platform by:

- Crawling 6 years of municipal documents (arrêtés, délibérations, commission reports)
- Processing citizen contributions from GitHub issues, Facebook, and local press
- Integrating with **Opik** (Comet ML) for LLM tracing, evaluation, and observability

### Related Repositories

- **Vaettir** (github.com/locki-io/vaettir) - N8N workflows for decision-making, integrating FB/email/chatbot interactions
- **audierne2026/participons** - Public participation platform (jekyll page)
- **docs.locki.io** Workflows should be documented via Docusaurus in the docs directory (sub git versionned).

## Commands

```bash
# Install dependencies
poetry install

# Run municipal document crawler
python src/crawl_municipal_docs.py --source all --mode scrape      # Single page test
python src/crawl_municipal_docs.py --source mairie_arretes --mode crawl --max-pages 100
python src/crawl_municipal_docs.py --dry-run                        # Preview only

# Dev tools
poetry run black .          # Format
poetry run ruff check .     # Lint
poetry run pytest           # Test
```

## Architecture

### Core Components

- **`src/config.py`** - `DataSource` definitions with URLs, extraction methods (`firecrawl`, `firecrawl+ocr`, `ocr`), and output directories. Contains `FIRECRAWL_CONFIG` and `OCR_CONFIG`.

- **`src/firecrawl_utils.py`** - `FirecrawlManager` class for web scraping via Firecrawl API. Methods: `scrape_url()` (single page), `crawl_website()` (full site). Saves results as markdown/HTML/JSON.

- **`src/crawl_municipal_docs.py`** - CLI orchestrating crawl operations across configured data sources.

### Data Flow

```
Data Sources (config.py) → FirecrawlManager → ext_data/<source>/
                                                  ├── *.md (content)
                                                  ├── *.html
                                                  ├── *_metadata.json
                                                  └── index_*.md
```

### Directory Structure

```
docs/                          # Git submodule → github.com/locki-io/docs.locki.io
├── docs/
│   ├── methods/               # TRIZ, SoC, ToC methodologies
│   └── workflows/             # Consolidation, Charter, Firecrawl
├── docusaurus.config.js       # Docusaurus configuration
└── package.json               # npm build scripts

docs.legacy/                   # Original docs (pre-Docusaurus)
├── FIRECRAWL_GUIDE.md
├── QUICKSTART.md
└── ideas/

ext_data/                      # Scraped municipal documents
├── mairie_arretes/            # ~4010 arrêtés & publications
├── mairie_deliberations/      # Council deliberations
├── commission_controle/       # Commission documents
└── gwaien/                    # Local bulletin (OCR source)

sources/                       # Additional data sources
concept/, persona/             # Project concept documentation
```

### Documentation (Submodule)

The `docs/` directory is a git submodule pointing to `locki-io/docs.locki.io`:

```bash
# Clone with submodules
git clone --recurse-submodules <repo>

# Update submodule
git submodule update --remote docs

# Work on docs
cd docs && npm install && npm start
```

### Methodologies

The project uses structured problem-solving approaches documented in `docs/docs/methods/`:

- **TRIZ** - Inventive problem solving
- **Separation of Concerns** - For workflows and code organization
- **Theory of Constraints** - For budget and localization constraints
- **Contribution Charter** - Governance rules for citizen participation

## Environment

Requires `FIRECRAWL_API_KEY` in `.env` (see `.env.example`).

## Data Sources

| Source                 | URL                                                       | Method        | Expected Count |
| ---------------------- | --------------------------------------------------------- | ------------- | -------------- |
| `mairie_arretes`       | audierne.bzh/publications-arretes/                        | firecrawl+ocr | ~4010          |
| `mairie_deliberations` | audierne.bzh/deliberations-conseil-municipal/             | firecrawl+ocr | -              |
| `commission_controle`  | audierne.bzh/systeme/documentheque/?documents_category=49 | firecrawl+ocr | -              |
