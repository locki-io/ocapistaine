# Examples

This directory contains example scripts to help you get started with the Firecrawl methodology.

## Quick Start Test

### 1. Set up your API key

```bash
# Copy the example env file
cp .env.example .env

# Edit .env and add your Firecrawl API key
# Get one from: https://firecrawl.dev

# Load environment variables
export $(cat .env | xargs)
```

### 2. Run the simple test

```bash
poetry run python examples/simple_scrape.py
```

This will:
- Test your Firecrawl API connection
- Scrape the Audierne homepage
- Save results to `ext_data/test_output/`

### 3. Try the full workflow

Once the simple test works, move to the main script:

```bash
# Dry run to see what would happen
poetry run python src/crawl_municipal_docs.py --dry-run

# Scrape a single source
poetry run python src/crawl_municipal_docs.py --source mairie_arretes --mode scrape

# Full crawl (limited pages for testing)
poetry run python src/crawl_municipal_docs.py --source mairie_arretes --mode crawl --max-pages 10
```

## Example Outputs

After running `simple_scrape.py`, you'll find:

```
ext_data/test_output/
├── www.audierne.bzh.md              # Markdown version
├── www.audierne.bzh.html            # HTML version
└── www.audierne.bzh_metadata.json   # Full metadata
```

## Next Steps

See the main [FIRECRAWL_GUIDE.md](../FIRECRAWL_GUIDE.md) for:
- Complete usage documentation
- Customization options
- Recommended workflow
- Troubleshooting tips
