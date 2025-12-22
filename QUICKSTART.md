# Firecrawl Quick Reference

## 🚀 One-Time Setup

```bash
# 1. Set API key
export FIRECRAWL_API_KEY="your_key_here"

# 2. Install dependencies (if not done)
poetry install
```

## 📝 Common Commands

### Test Connection
```bash
poetry run python examples/simple_scrape.py
```

### Dry Run (see what would happen)
```bash
poetry run python src/crawl_municipal_docs.py --dry-run
```

### Scrape Single Page (Testing)
```bash
# Test one source
poetry run python src/crawl_municipal_docs.py --source mairie_arretes --mode scrape

# Test all sources
poetry run python src/crawl_municipal_docs.py --source all --mode scrape
```

### Crawl Full Site (Production)
```bash
# One source, limited pages
poetry run python src/crawl_municipal_docs.py --source mairie_arretes --mode crawl --max-pages 50

# All sources, up to 100 pages each
poetry run python src/crawl_municipal_docs.py --source all --mode crawl --max-pages 100

# Large crawl (for arrêtés with 4010 documents)
poetry run python src/crawl_municipal_docs.py --source mairie_arretes --mode crawl --max-pages 500
```

## 📊 Available Sources

| Source Name              | URL                                          | Expected Count |
|-------------------------|----------------------------------------------|----------------|
| `mairie_arretes`        | publications-arretes/                        | ~4010          |
| `mairie_deliberations`  | deliberations-conseil-municipal/             | Unknown        |
| `commission_controle`   | documentheque/?documents_category=49         | Unknown        |

## 📂 Output Locations

```
ext_data/
├── mairie_arretes/          # Arrêtés & publications
├── mairie_deliberations/    # Délibérations
└── commission_controle/     # Commission documents
```

Each directory contains:
- `*.md` - Markdown content
- `*.html` - HTML content
- `*_metadata.json` - Full page metadata
- `index_*.md` - Index of all pages
- `errors.log` - Error log (if any)

## 🔍 Checking Results

```bash
# Count scraped files
ls ext_data/mairie_arretes/*.md | wc -l

# View index
cat ext_data/mairie_arretes/index_*.md

# Check for errors
cat ext_data/mairie_arretes/errors.log
```

## 💡 Recommended Workflow

1. **Test API**: `poetry run python examples/simple_scrape.py`
2. **Explore Structure**: `--mode scrape` on each source
3. **Limited Crawl**: `--mode crawl --max-pages 10` to validate
4. **Full Crawl**: Increase `--max-pages` based on needs
5. **Review Outputs**: Check files in `ext_data/`

## 🛠️ Troubleshooting

### "Failed to initialize Firecrawl"
- Check API key: `echo $FIRECRAWL_API_KEY`
- Get key from: https://firecrawl.dev

### "Rate limit exceeded"
- Wait a few minutes
- Reduce `--max-pages`
- Process sources one at a time

### Empty or Missing Files
- Check `errors.log` in output directory
- Try `--mode scrape` first to test structure
- Verify URL is accessible in browser

## 📚 Full Documentation

- Complete Guide: [FIRECRAWL_GUIDE.md](FIRECRAWL_GUIDE.md)
- Examples: [examples/README.md](examples/README.md)
- Configuration: [src/config.py](src/config.py)
