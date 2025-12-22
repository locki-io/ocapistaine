# Firecrawl Methodology Guide

This guide explains how to use the Firecrawl infrastructure to collect and organize municipal documents from the Audierne website.

## 🏗️ Architecture

```
src/
├── __init__.py                  # Package initialization
├── config.py                    # Data source configuration
├── firecrawl_utils.py          # Firecrawl manager and utilities
└── crawl_municipal_docs.py     # Main orchestration script

ext_data/
├── README.md                    # Data sources documentation
├── mairie_arretes/             # Output: arrêtés & publications
├── mairie_deliberations/       # Output: délibérations
└── commission_controle/        # Output: commission documents
```

## 📋 Data Sources

As defined in `ext_data/README.md`, we have three main sources:

1. **Mairie: Arrêtés** (4010 documents)
   - URL: https://www.audierne.bzh/publications-arretes/
   - Method: Firecrawl + OCR

2. **Mairie: Délibérations**
   - URL: https://www.audierne.bzh/deliberations-conseil-municipal/
   - Method: Firecrawl + OCR

3. **Commission de Contrôle**
   - URL: https://www.audierne.bzh/systeme/documentheque/?documents_category=49
   - Method: Firecrawl + OCR

## 🚀 Getting Started

### Prerequisites

1. **API Key**: Get a Firecrawl API key from https://firecrawl.dev
2. **Environment Setup**:
   ```bash
   export FIRECRAWL_API_KEY="your_api_key_here"
   ```

### Installation

Dependencies are already configured in `pyproject.toml`:

```bash
poetry install
```

## 📖 Usage

### Basic Usage

```bash
# Scrape a single page (exploratory mode)
poetry run python src/crawl_municipal_docs.py --source mairie_arretes --mode scrape

# Crawl full website section (up to 100 pages)
poetry run python src/crawl_municipal_docs.py --source mairie_arretes --mode crawl --max-pages 100

# Process all sources
poetry run python src/crawl_municipal_docs.py --source all --mode scrape
```

### Command-Line Options

```
--source <name>      Which source to process: mairie_arretes, mairie_deliberations,
                     commission_controle, or all (default: all)

--mode <mode>        scrape = single page only (for testing structure)
                     crawl = full website crawl (default: scrape)

--max-pages <n>      Maximum pages to crawl (default: 100, only for crawl mode)

--api-key <key>      Firecrawl API key (alternative to env var)

--dry-run            Show what would be done without actually crawling
```

### Examples

#### 1. Dry Run (No Actual Crawling)

```bash
poetry run python src/crawl_municipal_docs.py --source all --dry-run
```

#### 2. Test Single Source

```bash
# First, scrape just the main page to understand structure
poetry run python src/crawl_municipal_docs.py --source mairie_arretes --mode scrape

# Then crawl the full section
poetry run python src/crawl_municipal_docs.py --source mairie_arretes --mode crawl --max-pages 50
```

#### 3. Full Crawl of All Sources

```bash
poetry run python src/crawl_municipal_docs.py --source all --mode crawl --max-pages 200
```

## 📂 Output Structure

For each data source, the script creates:

```
ext_data/<source_name>/
├── <page1>.md                    # Markdown content
├── <page1>.html                  # HTML content
├── <page1>_metadata.json         # Full metadata
├── <page2>.md
├── <page2>.html
├── ...
├── index_<timestamp>.md          # Index of all crawled pages
├── crawl_metadata_<timestamp>.json  # Complete crawl metadata
└── errors.log                    # Error log (if any)
```

## 🔧 Customization

### Adding New Data Sources

Edit `src/config.py`:

```python
DATA_SOURCES.append(
    DataSource(
        name="new_source",
        url="https://example.com/page",
        method="firecrawl+ocr",
        output_dir=EXT_DATA_DIR / "new_source",
        description="Description of the source",
        expected_count=100,  # Optional
    )
)
```

### Adjusting Firecrawl Settings

Edit `src/config.py` to modify `FIRECRAWL_CONFIG`:

```python
FIRECRAWL_CONFIG = {
    "formats": ["markdown", "html"],
    "onlyMainContent": True,
    "includeTags": ["article", "main", "div.content"],
    "excludeTags": ["nav", "footer", "header"],
    "waitFor": 2000,  # Milliseconds to wait for dynamic content
}
```

### Document Extraction Logic

The function `extract_documents_from_page()` in `src/firecrawl_utils.py` is a placeholder for custom extraction logic specific to the Audierne website structure.

After scraping initial pages, you can:
1. Examine the markdown/HTML output
2. Identify patterns for document links, titles, dates
3. Implement extraction logic in this function

## 📊 Monitoring Progress

The script provides real-time feedback:

```
🔥 Scraping: https://...
✅ Successfully scraped: https://...

📊 SUMMARY
  ✅ SUCCESS: mairie_arretes
  ✅ SUCCESS: mairie_deliberations
  Total: 2 | Success: 2 | Failed: 0
```

Check output directories for:
- `index_*.md` files for page lists
- `errors.log` for any failures
- Individual `.md` files for content

## 🔄 Recommended Workflow

### Phase 1: Exploration (Scrape Mode)

```bash
# Test each source individually
poetry run python src/crawl_municipal_docs.py --source mairie_arretes --mode scrape
poetry run python src/crawl_municipal_docs.py --source mairie_deliberations --mode scrape
poetry run python src/crawl_municipal_docs.py --source commission_controle --mode scrape
```

**Review outputs to understand:**
- Page structure
- Document link patterns
- Pagination approach

### Phase 2: Limited Crawl (Testing)

```bash
# Crawl a small number of pages to validate
poetry run python src/crawl_municipal_docs.py --source mairie_arretes --mode crawl --max-pages 10
```

**Verify:**
- All pages are captured
- Content quality is good
- No errors in logs

### Phase 3: Full Crawl

```bash
# Crawl complete sections (adjust max-pages based on expected count)
poetry run python src/crawl_municipal_docs.py --source mairie_arretes --mode crawl --max-pages 500
```

### Phase 4: OCR Processing

After Firecrawl completes, process downloaded PDFs with OCR:
- Identify PDF files in scraped content
- Apply OCR (configuration in `src/config.py` → `OCR_CONFIG`)
- Extract text from images/scanned documents

## 🛡️ Error Handling

The script includes:
- **Try-catch blocks** for each source
- **Error logging** to `errors.log`
- **Graceful failure** (continues with next source if one fails)
- **Summary report** showing success/failure status

## 💡 Tips

1. **Start Small**: Always test with `--mode scrape` first
2. **Rate Limiting**: Be respectful of the municipal website
3. **API Costs**: Firecrawl has usage limits; monitor your quota
4. **Incremental**: Process sources one at a time before running `--source all`
5. **Backup**: The script preserves original HTML + metadata for reference

## 🔮 Next Steps

1. **Implement OCR**: Add OCR processing for PDF documents
2. **Custom Extraction**: Implement `extract_documents_from_page()` logic
3. **Database Storage**: Store structured data in a database
4. **Scheduling**: Set up automated periodic crawls
5. **Analysis**: Build tools to analyze collected documents

## 📞 Support

- Firecrawl Documentation: https://docs.firecrawl.dev
- Project Issues: See main README.md
