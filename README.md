# Ò Capistaine

AI-powered RAG system for civic transparency in Audierne, France.

## Overview

Ò Capistaine crawls, processes, and makes accessible 6 years of municipal documents (arrêtés, délibérations, commission reports) through a conversational AI interface. It supports the [audierne2026.fr](https://audierne2026.fr) participatory democracy platform.

## Tech Stack

| Component             | Technology    | Purpose                                        |
| --------------------- | ------------- | ---------------------------------------------- |
| **Data Validation**   | Pydantic      | Schema validation for documents and API models |
| **Web Scraping**      | Firecrawl     | Municipal document acquisition with OCR        |
| **Scheduling**        | APScheduler   | Periodic crawl jobs and data refresh           |
| **LLM Observability** | Opik (cloud)  | Tracing, evaluation, and LLM-as-judge          |
| **API**               | FastAPI       | REST endpoints for N8N integration             |
| **Orchestration**     | N8N (Vaettir) | Multi-channel workflows (FB, email, chatbot)   |

## Quick Start

```bash
# Clone with submodules
git clone --recurse-submodules https://github.com/locki-io/ocapistaine.git
cd ocapistaine

# Install dependencies
poetry install

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run crawler
python src/crawl_municipal_docs.py --source all --mode scrape
```

## git merge proposal on feature branch

```
git config pull.rebase merges
```

## Project Structure

```
ocapistaine/
├── src/                       # Python source code
│   ├── config.py              # Data source configuration
│   ├── firecrawl_utils.py     # Web scraping utilities
│   └── crawl_municipal_docs.py # CLI entry point
├── docs/                      # Git submodule → locki-io/docs.locki.io
├── docs.legacy/               # Original documentation
├── ext_data/                  # Scraped municipal documents
└── pyproject.toml             # Poetry dependencies
```

## Working with Submodules

The `docs/` directory is a git submodule pointing to [locki-io/docs.locki.io](https://github.com/locki-io/docs.locki.io).

### Clone with submodules

```bash
git clone --recurse-submodules https://github.com/locki-io/ocapistaine.git
```

### If already cloned without submodules

```bash
git submodule update --init --recursive
```

### Update docs to latest

```bash
git submodule update --remote docs
git add docs
git commit -m "Update docs submodule"
```

### Work on documentation

```bash
cd docs
npm install
npm start    # Dev server at localhost:3000
npm run build
```

### Commit changes to docs

```bash
# Inside docs/
git add .
git commit -m "Your changes"
git push

# Back in parent repo
cd ..
git add docs
git commit -m "Update docs submodule"
git push
```

## Related Repositories

- **[Vaettir](https://github.com/locki-io/vaettir)** - N8N workflows for decision-making
- **[audierne2026/participons](https://github.com/audierne2026/participons)** - Public participation platform (Jekyll)
- **[docs.locki.io](https://github.com/locki-io/docs.locki.io)** - Docusaurus documentation

## Environment Variables

| Variable            | Description                        |
| ------------------- | ---------------------------------- |
| `FIRECRAWL_API_KEY` | Firecrawl API key for web scraping |
| `OPIK_API_KEY`      | Opik API key for LLM observability |
| `OPIK_WORKSPACE`    | Opik workspace name                |

## Project Board

Track progress: [github.com/orgs/locki-io/projects/2](https://github.com/orgs/locki-io/projects/2)

## Contributing

> **Important for Hackathon Participants**: Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting code.

This project uses a dual-license structure. By contributing, you agree to the license terms for the component you're working on. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

This project uses a **dual-license structure**:

| Component                 | License             | Files                      |
| ------------------------- | ------------------- | -------------------------- |
| Core infrastructure       | Apache 2.0          | `src/`, `docs/`, utilities |
| Agent workflows & prompts | Elastic License 2.0 | `agents/`, `workflows/`    |

### Summary

- **Open source components**: Crawlers, utilities, documentation - free to use, modify, distribute
- **Source-available components**: Agent orchestration, prompts, N8N workflows - visible but commercial use requires license from [locki.io](https://locki.io)

See [LICENSE](LICENSE) and [LICENSE-ELv2](LICENSE-ELv2) for full terms.

### Hackathon Note

This structure complies with hackathon open-source requirements while protecting locki.io engineering IP for future commercialization.
