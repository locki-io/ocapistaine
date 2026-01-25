# OCapistaine Architecture

## Overview

OCapistaine is an AI-powered civic transparency system for local democracy. This document describes the layered architecture following **Separation of Concerns** principles.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PRESENTATION LAYER                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │   Streamlit UI  │  │   FastAPI REST  │  │   N8N Webhooks (external)   │  │
│  │   (view.py)     │  │   (api/main.py) │  │   FB / Email / Chatbot      │  │
│  └────────┬────────┘  └────────┬────────┘  └──────────────┬──────────────┘  │
└───────────┼────────────────────┼─────────────────────────┼──────────────────┘
            │                    │                         │
            ▼                    ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           APPLICATION LAYER                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         Service Orchestrator                         │   │
│  │                      (services/orchestrator.py)                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│         ┌──────────────────────────┼──────────────────────────┐             │
│         ▼                          ▼                          ▼             │
│  ┌─────────────┐          ┌─────────────┐          ┌─────────────────┐      │
│  │  RAG Service│          │ Chat Service│          │ Document Service│      │
│  │             │          │             │          │                 │      │
│  └─────────────┘          └─────────────┘          └─────────────────┘      │
└─────────────────────────────────────────────────────────────────────────────┘
            │                    │                         │
            ▼                    ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BUSINESS LOGIC LAYER                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                              AGENTS                                  │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐  │   │
│  │  │ RAG Agent      │  │ Crawler Agent  │  │ Evaluation Agent       │  │   │
│  │  │ (retrieval +   │  │ (Firecrawl +   │  │ (Opik LLM-as-judge)    │  │   │
│  │  │  generation)   │  │  OCR pipeline) │  │                        │  │   │
│  │  └────────────────┘  └────────────────┘  └────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                           PROCESSORS                                 │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐  │   │
│  │  │ Embeddings     │  │ Document       │  │ Response               │  │   │
│  │  │ Processor      │  │ Parser         │  │ Formatter              │  │   │
│  │  └────────────────┘  └────────────────┘  └────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
            │                    │                         │
            ▼                    ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA ACCESS LAYER                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  Redis Cache    │  │  Vector Store   │  │   File Storage              │  │
│  │  (sessions,     │  │  (embeddings,   │  │   (ext_data/, crawled docs) │  │
│  │   hot data)     │  │   retrieval)    │  │                             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
            │                    │                         │
            ▼                    ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL SERVICES                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Firecrawl  │  │   OpenAI    │  │    Opik     │  │   N8N (Vaettir)     │ │
│  │  API        │  │   / LLM     │  │   Tracing   │  │   Workflows         │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Layer Responsibilities

### 1. Presentation Layer

| Component        | Purpose                                  | Technology              |
| ---------------- | ---------------------------------------- | ----------------------- |
| **Streamlit UI** | Citizen-facing Q&A interface             | Streamlit               |
| **FastAPI REST** | API for external integrations            | FastAPI + Uvicorn       |
| **N8N Webhooks** | Multi-channel input (FB, email, chatbot) | External (Vaettir repo) |

### 2. Application Layer

| Component                | Purpose                                         |
| ------------------------ | ----------------------------------------------- |
| **Service Orchestrator** | Coordinates services, manages request lifecycle |
| **RAG Service**          | Handles document retrieval + answer generation  |
| **Chat Service**         | Manages conversation history, context           |
| **Document Service**     | CRUD operations on document corpus              |

### 3. Business Logic Layer

#### Agents (ELv2 Licensed - locki.io IP)

| Agent                | Purpose                                        | Status             |
| -------------------- | ---------------------------------------------- | ------------------ |
| **RAG Agent**        | Retrieval-Augmented Generation for citizen Q&A | 🔴 Pending         |
| **Crawler Agent**    | Firecrawl + OCR document acquisition           | 🔴 Not operational |
| **Evaluation Agent** | Opik LLM-as-judge for hallucination detection  | 🟡 Planned         |

#### Processors (Apache 2.0 Licensed - Open Source)

| Processor                | Purpose                      | Status     |
| ------------------------ | ---------------------------- | ---------- |
| **Embeddings Processor** | Generate vector embeddings   | 🔴 Pending |
| **Document Parser**      | Extract text from PDFs, HTML | 🟡 Partial |
| **Response Formatter**   | Format answers with sources  | 🔴 Pending |

### 4. Data Access Layer

| Component        | Purpose                                | Technology                     |
| ---------------- | -------------------------------------- | ------------------------------ |
| **Redis Cache**  | Session state, hot data, rate limiting | Redis                          |
| **Vector Store** | Document embeddings for retrieval      | TBD (Chroma/Pinecone/Qdrant)   |
| **File Storage** | Raw crawled documents                  | Local filesystem (`ext_data/`) |

---

## Directory Structure

```
app/
├── __init__.py
├── main.py                 # FastAPI app entry point (uvicorn)
├── view.py                 # Streamlit UI (simplified)
├── sidebar.py              # Streamlit sidebar (simplified)
│
├── api/                    # Presentation Layer - REST API
│   ├── __init__.py
│   ├── routes/
│   │   ├── chat.py         # POST /chat - citizen Q&A
│   │   ├── documents.py    # GET /documents - corpus info
│   │   └── health.py       # GET /health - status
│   └── middleware/
│       └── auth.py         # User identification
│
├── services/               # Application Layer
│   ├── __init__.py
│   ├── orchestrator.py     # Service coordinator
│   ├── rag_service.py      # RAG operations
│   ├── chat_service.py     # Conversation management
│   └── document_service.py # Document CRUD
│
├── agents/                 # Business Logic - Agents (ELv2)
│   ├── __init__.py
│   ├── rag_agent.py        # RAG retrieval + generation
│   ├── crawler_agent.py    # Firecrawl + OCR pipeline
│   └── eval_agent.py       # Opik evaluation agent
│
├── processors/             # Business Logic - Processors (Apache 2.0)
│   ├── __init__.py
│   ├── embeddings.py       # Vector embedding generation
│   ├── document_parser.py  # PDF/HTML text extraction
│   └── response_formatter.py
│
├── data/                   # Data Access Layer
│   ├── __init__.py
│   ├── redis_client.py     # Redis connection + operations
│   ├── vector_store.py     # Vector DB operations
│   └── file_storage.py     # File system operations
│
├── models/                 # Shared data models (Pydantic)
│   ├── __init__.py
│   ├── user.py             # User session model
│   ├── document.py         # Document model
│   ├── chat.py             # Chat message models
│   └── response.py         # API response models
│
└── config/                 # Configuration
    ├── __init__.py
    ├── settings.py         # Environment-based settings
    └── logging.py          # Logging configuration
```

---

## Key Design Decisions

### 1. Redis-Only Caching Strategy

```python
# All hot data in Redis for fast Streamlit response
REDIS_KEYS = {
    "session:{user_id}": "User session state (TTL: 24h)",
    "chat:{user_id}:{thread_id}": "Conversation history (TTL: 7d)",
    "document:{doc_id}": "Cached document content (TTL: 1h)",
    "rate_limit:{user_id}": "Rate limiting counter (TTL: 1min)",
}
```

### 2. User Identification (Simplified)

```python
# Single unique identifier per user
class UserSession:
    user_id: str          # UUID from cookie or generated
    created_at: datetime
    last_active: datetime

# No complex session state - just user_id flows through all layers
```

### 3. Uvicorn Production Setup

```python
# main.py - FastAPI entry point
from fastapi import FastAPI
from app.api.routes import chat, documents, health

app = FastAPI(title="Ò Capistaine API", version="0.1.0")

app.include_router(chat.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(health.router)

# Run with: uvicorn app.main:app --host 0.0.0.0 --port 8050
```

### 4. Streamlit + FastAPI Coexistence

```
┌─────────────────────────────────────────────────────────┐
│                    Production Setup                      │
├─────────────────────────────────────────────────────────┤
│  Port 8502: Streamlit UI (citizen-facing)               │
│  Port 8050: FastAPI (API + N8N webhooks)                │
│  Port 6379: Redis (shared cache)                        │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Roadmap

Based on [Checkpoint 1 Blog Post](../docs/blog/2026-01-15-let-the-journey-begin.mdx):

### Phase 1: Foundation (Current)

- [x] audierne2026.fr live
- [x] Documentation site (docs.locki.io)
- [x] Simplified front.py + sidebar.py
- [ ] **TODO: Redis client setup**

### Phase 2: Document Pipeline

- [ ] Fix Firecrawl pipeline (crawler_agent.py)
- [ ] Document parser for municipal PDFs
- [ ] File storage organization

### Phase 3: RAG System

- [ ] Embeddings processor
- [ ] Vector store integration
- [ ] RAG agent implementation

### Phase 4: Quality & Observability

- [ ] Opik tracing integration
- [ ] Evaluation agent (LLM-as-judge)
- [ ] Hallucination detection

### Phase 5: Multi-Channel

- [ ] FastAPI webhooks for N8N
- [ ] Facebook integration (via Vaettir)
- [ ] Email response pipeline

---

## Environment Variables

```bash
# .env
REDIS_DB=5
REDIS_POST=6379
FIRECRAWL_API_KEY=your_key
OPENAI_API_KEY=your_key
OPIK_API_KEY=your_key
OPIK_WORKSPACE=ocapistaine-dev

# Optional
VECTOR_STORE_TYPE=chroma  # or pinecone, qdrant
APP_ENV=development       # or production
```

---

## Running the Application

### Development

```bash
# Terminal 1: Streamlit UI
poetry run streamlit run app/view.py --server.port 8502

# Terminal 2: FastAPI
poetry run uvicorn app.main:app --reload --port 8050

# Terminal 3: Redis (if not running)
redis-server
```

### Production

```bash
# Using docker-compose (recommended)
docker-compose up -d

# Or manually with uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
streamlit run app/front.py --server.port 8501 --server.address 0.0.0.0
```

---

## License Split

| Layer                            | License    |
| -------------------------------- | ---------- |
| Presentation (app/front.py, API) | Apache 2.0 |
| Application (services/)          | Apache 2.0 |
| Processors (processors/)         | Apache 2.0 |
| **Agents (agents/)**             | **ELv2**   |
| Data Access (data/)              | **ELv2**   |
| Models (models/)                 | Apache 2.0 |

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for details.
