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

## Running the Application

### Local Development

```bash
# Install dependencies
poetry install

# Start Streamlit locally
./scripts/run_streamlit.sh

# Access at http://localhost:8502
```

### Public Access (via ngrok + vaettir proxy)

To make the app publicly accessible at `https://ocapistaine.vaettir.locki.io`:

```bash
# Terminal 1: Start Streamlit
./scripts/run_streamlit.sh

# Terminal 2: Start ngrok tunnel
poetry run python scripts/start_ngrok.py

# Access points:
# - Local:  http://localhost:8502
# - ngrok:  https://ocapistaine.ngrok-free.app
# - Public: https://ocapistaine.vaettir.locki.io
```

### VS Code Integration

**Tasks** (Cmd+Shift+P → "Tasks: Run Task"):

| Task | Description |
|------|-------------|
| 🚀 Start OCapistaine (Streamlit + ngrok) | One-click full startup (default build task) |
| 🛑 Stop OCapistaine (All) | Stop both Streamlit and ngrok |
| 📊 Check Status | View running services status |
| 🔗 Open in Browser (Local) | Open http://localhost:8502 |
| 🌐 Open in Browser (Public) | Open https://ocapistaine.vaettir.locki.io |

**Debug Configurations** (F5 or Run & Debug panel):

| Configuration | Description |
|---------------|-------------|
| Run Uvicorn (Poetry) | Start FastAPI server on port 8050 with debugger |
| Run Streamlit (Debug) | Start Streamlit UI on port 8502 with debugger |
| Full Stack (Uvicorn + Streamlit) | Both services with debugging |
| 🚀 OCapistaine Public | Streamlit + ngrok for public access |

**Quick Start:**
- Press `Cmd+Shift+B` to run the default build task (starts everything)
- Or use the Run & Debug panel to select a configuration

## version control on main, dev and feature branch

```
main requires approval
dev no approval but linear history

To keep our history clean (no noisy merge commits on feature branches):

1. Run once:
   git config --local pull.rebase true
   # (or git config --local pull.rebase merges)

   Optional safety layer:
   git config --local pull.ff only

   → git pull will now rebase by default (clean linear history)
   → if it can't fast-forward, it fails instead of auto-merging

This way:
- Your local git pull stays clean
- Main/dev stays perfectly linear
- No more "Merge branch 'feature/ocr-…' into dev" spam

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

## Authentication

The public instance is password-protected. Configure in `.streamlit/secrets.toml`:

```toml
[auth]
password = "your-secret-password"
```

**Setup:**
```bash
# Copy template
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# Edit with your password
nano .streamlit/secrets.toml
```

**For hashed passwords** (more secure):
```bash
poetry run python -c "from app.auth import hash_password; print(hash_password('your-password'))"
# Then use: password = "sha256:..."
```

**Disable authentication** (local development): Remove or leave empty the `password` field.

## Environment Variables

| Variable            | Description                        | Example |
| ------------------- | ---------------------------------- | ------- |
| `FIRECRAWL_API_KEY` | Firecrawl API key for web scraping | |
| `OPIK_API_KEY`      | Opik API key for LLM observability | |
| `OPIK_WORKSPACE`    | Opik workspace name                | |
| `NGROK_DOMAIN`      | Fixed ngrok domain (paid plan)     | `ocapistaine.ngrok-free.app` |
| `STREAMLIT_PORT`    | Local Streamlit port               | `8502` |
| `DISCORD_INVITE_URL`| Discord invite link for auth page  | `https://discord.gg/yourserver` |

See `.env.example` for a complete template.

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
