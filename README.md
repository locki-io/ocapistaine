# Ò Capistaine

**Making local democracy accessible through AI — because understanding your town council shouldn't require a law degree.**

> *"This year, I will finally understand my local elections and get involved as a citizen."* — Our 2026 resolution

[![Demo Video](https://img.shields.io/badge/Demo-YouTube-red?logo=youtube)](https://youtu.be/EAZiVUMtfp8)
[![Documentation](https://img.shields.io/badge/Docs-docs.locki.io-blue)](https://docs.locki.io)
[![Encode Hackathon](https://img.shields.io/badge/Encode-Hackathon%202026-purple)](https://www.encode.club/)

## 🎬 Demo

**[Watch the 3-minute demo →](https://youtu.be/EAZiVUMtfp8)**

## Overview

Ò Capistaine is an AI-powered civic transparency platform that crawls, processes, and makes accessible 6 years of municipal documents (arrêtés, délibérations, commission reports) for Audierne, France. It serves as a training ground for civic AI agents that help citizens engage with local democracy.

**Key Features:**
- 🔍 **Document Intelligence**: 4,000+ municipal documents indexed and searchable
- 🤖 **Forseti 461**: AI agent for charter validation, category classification, and PII anonymization
- 📊 **LLM Observability**: Full tracing via Opik with cost tracking and evaluation
- 🔗 **Multi-channel Integration**: Facebook, email, chatbot via [Vaettir N8N workflows](https://github.com/locki-io/vaettir)
- 🌐 **Bilingual**: French/English interface

The platform supports [audierne2026.fr](https://audierne2026.fr), a real participatory democracy initiative.

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

### 1. Start the Streamlit UI

The primary way to start the OCapistaine interface is via the unified startup script. It handles environment configuration, port management, and optional public access.

```bash
# Start the interactive UI
./scripts/run_streamlit.sh
```

**Access Point:**
- **Local**: [http://localhost:8502](http://localhost:8502)

### 2. Start the API Backend (Optional)

If you need the REST API or N8N/Vaettir webhook integrations, start the FastAPI server in a separate terminal:

```bash
# Start FastAPI backend
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8050 --reload
```

Access API documentation at [http://localhost:8050/docs](http://localhost:8050/docs).

### VS Code Integration

**Tasks** (Cmd+Shift+P → "Tasks: Run Task"):

| Task | Description |
|------|-------------|
| 🚀 Start OCapistaine (Local) | One-click local startup |
| 🛑 Stop OCapistaine | Stop the Streamlit process |
| 📊 Check Status | View running services status |
| 🔗 Open in Browser | Open http://localhost:8502 |

**Debug Configurations** (F5 or Run & Debug panel):

| Configuration | Description |
|---------------|-------------|
| Run Uvicorn (Poetry) | Start FastAPI server on port 8050 with debugger |
| Run Streamlit (Debug) | Start Streamlit UI on port 8502 with debugger |
| Full Stack (Uvicorn + Streamlit) | Both services with debugging |

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
├── app/                       # Streamlit UI + Forseti agent + services
├── src/                       # Document crawlers (Firecrawl, OCR)
├── docs/                      # Git submodule → docs.locki.io
└── ext_data/                  # 4,000+ scraped municipal documents
```

For detailed architecture, see **[docs.locki.io](https://docs.locki.io)**:
- [Application](https://docs.locki.io/docs/app) — Streamlit UI, Forseti agent, scheduler
- [Architecture](https://docs.locki.io/docs/ARCHITECTURE) — System design and data flow
- [Orchestration](https://docs.locki.io/docs/orchestration) — Docker, N8N, observability

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

| Repository | Status | Description |
|------------|--------|-------------|
| **[Vaettir](https://github.com/locki-io/vaettir)** | ✅ Operational | N8N workflows connecting OCapistaine to audierne2026, Facebook, email |
| **[docs.locki.io](https://docs.locki.io)** | ✅ Live | Technical documentation + [hackathon journey blog](https://docs.locki.io/blog) |
| **[audierne2026/participons](https://github.com/audierne2026/participons)** | ✅ Live | Public participation platform (Jekyll) |

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

---

## 🏆 Encode Hackathon 2026

**Ò Capistaine** was built for the [Encode AI Hackathon 2026](https://www.encode.club/).

| Resource | Link |
|----------|------|
| 🎬 Demo Video | [youtu.be/EAZiVUMtfp8](https://youtu.be/EAZiVUMtfp8) |
| 📚 Documentation | [docs.locki.io](https://docs.locki.io) |
| 📝 Hackathon Journey | [Blog posts](https://docs.locki.io/blog) |
| 📊 Project Board | [GitHub Project](https://github.com/orgs/locki-io/projects/2) |

*Built with ❤️ for local democracy in Audierne, Brittany, France.*
