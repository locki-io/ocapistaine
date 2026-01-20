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

# TODO: Import routes when implemented
# from app.api.routes import chat, documents, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Startup: Initialize connections, warm caches
    Shutdown: Clean up resources
    """
    # Startup
    print("🚀 OCapistaine API starting...")

    # Check Redis connection
    if redis_health_check():
        print("✅ Redis connected")
    else:
        print("⚠️  Redis not available - some features may be limited")

    # TODO: Initialize vector store connection
    # TODO: Warm embedding model cache

    yield

    # Shutdown
    print("👋 OCapistaine API shutting down...")


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
        "http://localhost:8501",      # Streamlit dev
        "https://audierne2026.fr",    # Production
        "https://docs.locki.io",      # Documentation
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Health & Status Routes
# =============================================================================

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
    return {
        "service": "ocapistaine",
        "version": "0.1.0",
        "components": {
            "redis": "connected" if redis_health_check() else "disconnected",
            "firecrawl": "not_configured",  # TODO: Check Firecrawl
            "rag": "not_implemented",        # TODO: Check RAG
            "opik": "not_configured",        # TODO: Check Opik
        },
    }


# =============================================================================
# Chat Routes (Placeholder)
# =============================================================================

@app.post("/api/v1/chat")
async def chat_endpoint(request: Request):
    """
    Citizen Q&A endpoint.

    TODO: Implement RAG-based response generation.

    Request body:
        {
            "user_id": "uuid",
            "message": "Question about municipal decisions",
            "thread_id": "optional-thread-id"
        }

    Response:
        {
            "response": "Answer with sources",
            "sources": ["doc1.pdf", "doc2.pdf"],
            "confidence": 0.85
        }
    """
    body = await request.json()
    user_id = body.get("user_id", "anonymous")
    message = body.get("message", "")
    thread_id = body.get("thread_id", "default")

    # TODO: Replace with actual RAG call
    # from app.services.rag_service import RAGService
    # response = await RAGService.query(message, user_id, thread_id)

    return {
        "response": f"🚧 RAG system en développement. Votre question: '{message}'",
        "sources": [],
        "confidence": 0.0,
        "thread_id": thread_id,
    }


# =============================================================================
# Document Routes (Placeholder)
# =============================================================================

@app.get("/api/v1/documents")
async def list_documents():
    """
    List available document sources.

    TODO: Implement document listing from vector store.
    """
    return {
        "sources": [
            {
                "name": "mairie_arretes",
                "description": "Arrêtés municipaux",
                "count": 0,
                "status": "not_crawled",
            },
            {
                "name": "mairie_deliberations",
                "description": "Délibérations du conseil",
                "count": 0,
                "status": "not_crawled",
            },
            {
                "name": "gwaien",
                "description": "Bulletins municipaux",
                "count": 42,
                "status": "partial",
            },
        ],
        "total_indexed": 42,
    }


@app.get("/api/v1/documents/{doc_id}")
async def get_document(doc_id: str):
    """
    Get a specific document.

    TODO: Implement document retrieval.
    """
    return {
        "error": "not_implemented",
        "message": f"Document {doc_id} retrieval not yet implemented",
    }


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
        reload=True,
    )
