# main.py
"""
OCapistaine - FastAPI Application

Production entry point for uvicorn.
Handles REST API and N8N webhook integrations.

Run with:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.data.redis_client import health_check as redis_health_check
from app.services.logging import get_logger

logger = get_logger("presentation")

# Route imports
from app.api.routes.validate import router as validate_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Startup: Initialize connections, warm caches, start scheduler
    Shutdown: Stop scheduler, clean up resources
    """
    # Startup
    logger.info("OCapistaine API starting...")

    # Check Redis connection
    if redis_health_check():
        logger.info("Redis connected")
    else:
        logger.warning("Redis not available - some features may be limited")

    # Check provider availability
    from app.providers.health import check_providers

    await check_providers()

    # Start scheduler
    from app.services.scheduler import start_scheduler

    await start_scheduler()

    # Initialize RAG vector store
    try:
        from app.rag.store import get_collection

        col = get_collection()
        logger.info(f"RAG vector store ready: {col.count()} chunks indexed")
    except Exception as e:
        logger.warning(f"RAG initialization failed (non-blocking): {e}")

    yield

    # Shutdown
    from app.services.scheduler import stop_scheduler

    await stop_scheduler()
    logger.info("OCapistaine API shutting down...")


# Create FastAPI application
app = FastAPI(
    title="OCapistaine API",
    description="AI-powered civic transparency for local democracy",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8501",  # Streamlit dev
        "https://audierne2026.fr",  # Production
        "https://docs.locki.io",  # Documentation
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(validate_router, prefix="/api/v1")


def _rag_status() -> dict | str:
    """Check RAG system status."""
    try:
        from app.rag.store import collection_stats

        stats = collection_stats()
        if stats["total_chunks"] > 0:
            return {"status": "ready", **stats}
        return "empty"
    except Exception:
        return "not_available"


# =============================================================================
# Health & Status Routes
# =============================================================================


@app.get("/")
async def root():
    """Root endpoint - API info."""
    return {
        "service": "OCapistaine API",
        "version": "0.1.0",
        "description": "AI-powered civic transparency for local democracy",
        "docs": "/docs",
        "health": "/health",
        "ui": "https://ocapistaine.onrender.com:8502",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "ocapistaine",
        "version": "0.1.0",
    }


@app.get("/status")
async def status():
    """Detailed status endpoint."""
    # Check Opik availability
    from app.agents.tracing import get_tracer

    tracer = get_tracer()
    opik_status = "connected" if tracer.enabled else "not_configured"

    # Check provider availability
    from app.providers.health import get_provider_status

    provider_report = get_provider_status()
    providers_component = {}
    if provider_report:
        providers_component = {
            "ollama": provider_report["ollama"],
            "cloud": provider_report["cloud"],
            "checked_at": provider_report["checked_at"],
        }

    return {
        "service": "ocapistaine",
        "version": "0.1.0",
        "components": {
            "redis": "connected" if redis_health_check() else "disconnected",
            "firecrawl": "not_configured",
            "rag": _rag_status(),
            "opik": opik_status,
            "forseti": "available",
            "providers": providers_component,
        },
    }


# =============================================================================
# Chat Routes (Placeholder)
# =============================================================================


@app.post("/api/v1/chat")
async def chat_endpoint(request: Request):
    """
    Citizen Q&A endpoint — RAG-powered answers with sources.

    Request body:
        {
            "message": "Question about municipal decisions",
            "filters": {"category": "economie"},  // optional
            "n_results": 5  // optional
        }
    """
    from app.rag import RAGService

    body = await request.json()
    message = body.get("message", "")
    filters = body.get("filters")
    n_results = body.get("n_results", 5)
    thread_id = body.get("thread_id")

    if not message:
        return {"error": "message is required"}

    service = RAGService()
    result = await service.query(
        message, n_results=n_results, filters=filters, thread_id=thread_id
    )
    return result


@app.post("/api/v1/chat/compare")
async def chat_compare_endpoint(request: Request):
    """
    Compare electoral programs across lists.

    Request body:
        {
            "question": "Que proposent les listes sur l'économie locale ?",
            "list_names": ["audierne2026", "liste-opposition-1", ...]
        }
    """
    from app.rag import RAGService

    body = await request.json()
    question = body.get("question", "")
    list_names = body.get("list_names", [])
    thread_id = body.get("thread_id")

    if not question or not list_names:
        return {"error": "question and list_names are required"}

    service = RAGService()
    result = await service.compare(question, list_names, thread_id=thread_id)
    return result


# =============================================================================
# Document Routes (Placeholder)
# =============================================================================


@app.get("/api/v1/documents")
async def list_documents():
    """List indexed document sources from the RAG vector store."""
    from app.rag import RAGService

    stats = RAGService.stats()
    return stats


@app.get("/api/v1/documents/ingest")
async def trigger_ingest(reset: bool = False):
    """Trigger document ingestion (admin). Use ?reset=true to rebuild."""
    from app.rag.ingest import ingest_from_jsonl

    result = ingest_from_jsonl(reset=reset)
    return result


# =============================================================================
# Webhook Routes (for N8N / Vaettir integration)
# =============================================================================


@app.post("/api/v1/webhooks/message")
async def webhook_message(request: Request):
    """
    Incoming message webhook for N8N.

    Handles messages from Facebook, email, chatbot via Vaettir workflows.

    Request body:
        {
            "source": "facebook|email|chatbot",
            "user_id": "external_user_id",
            "message": "User question",
            "metadata": {...}
        }
    """
    body = await request.json()

    # TODO: Process and route to appropriate handler
    # from app.services.orchestrator import Orchestrator
    # response = await Orchestrator.handle_external_message(body)

    return {
        "status": "received",
        "message": "Webhook received, processing not yet implemented",
        "body": body,
    }


# =============================================================================
# Admin Routes (protected in production)
# =============================================================================


@app.post("/api/v1/admin/crawl")
async def trigger_crawl(request: Request):
    """
    Trigger document crawl (admin only).

    TODO: Implement crawl triggering with authentication.
    """
    return {
        "status": "not_implemented",
        "message": "Crawl triggering not yet implemented",
    }


# Entry point for development
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
