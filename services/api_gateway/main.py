"""
API Gateway — FastAPI application serving as the central entry point.

Endpoints:
  POST /chat              → Main chat endpoint with model selection
  POST /rag/index         → Index a codebase directory for RAG
  GET  /rag/status        → RAG index status
  POST /debug/analyze     → Analyze error logs
  POST /graph/parse       → Parse and build dependency graph
  GET  /graph/deps        → Query dependencies for a module
  GET  /health            → Health check
  GET  /                  → Serve frontend
"""

import sys
import os
import time
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.config import settings
from shared.llm.orchestrator import LLMOrchestrator
from services.rag_service import rag_service
from services.debug_service import debug_service
from services.graph_service import graph_service

# ── Logging ────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("api_gateway")


# ── Lifespan ───────────────────────────────────────────────────────

orchestrator = LLMOrchestrator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Intelligent Codebase Assistant starting...")
    logger.info("   Ollama URL : %s", settings.OLLAMA_BASE_URL)
    logger.info("   Groq key   : %s", "configured" if settings.GROQ_API_KEY else "NOT SET")
    logger.info("   Gemini key : %s", "configured" if settings.GEMINI_API_KEY else "NOT SET")

    # Check Ollama availability
    available = await orchestrator.ollama.is_available()
    logger.info("   Ollama     : %s", "✅ reachable" if available else "❌ unreachable")

    yield
    logger.info("Shutting down...")


# ── App ────────────────────────────────────────────────────────────

app = FastAPI(
    title="Intelligent Codebase Assistant",
    description="AI-powered code understanding, debugging, and documentation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ──────────────────────────────────────

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User's question or prompt")
    model: str = Field("auto", description="Model preference: auto | local | groq | gemini")
    system_prompt: Optional[str] = Field(None, description="Optional system prompt")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1, le=8192)


class ChatResponse(BaseModel):
    answer: str
    model_used: str
    provider: str
    mode: str
    fallback_used: bool
    latency_ms: float
    tokens_used: Optional[int] = None


class IndexRequest(BaseModel):
    directory: str = Field(..., description="Path to the codebase directory to index")


class DebugRequest(BaseModel):
    log_content: str = Field(..., description="Error log content to analyze")
    model: str = Field("groq", description="Model preference for analysis")
    additional_context: str = Field("", description="Extra context for analysis")


class GraphParseRequest(BaseModel):
    directory: str = Field(..., description="Path to the codebase directory to parse")


class GraphQueryRequest(BaseModel):
    module_id: str = Field(..., description="Module file path to query dependencies for")


# ── Endpoints ──────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Main chat endpoint — routes to the appropriate LLM."""
    logger.info("Chat request: model=%s, query_len=%d", request.model, len(request.query))

    try:
        result = await orchestrator.generate_response(
            query=request.query,
            model_preference=request.model,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return ChatResponse(**result)
    except Exception as exc:
        logger.error("Chat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/rag/index")
async def rag_index(request: IndexRequest):
    """Index a codebase directory for RAG queries."""
    directory = request.directory
    if not os.path.isdir(directory):
        raise HTTPException(status_code=400, detail=f"Directory not found: {directory}")

    try:
        chunks = rag_service.chunk_directory(directory)
        if not chunks:
            raise HTTPException(status_code=400, detail="No supported files found in directory")

        rag_service.build_index(chunks)
        status = rag_service.index_status()
        return {"status": "indexed", **status}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("RAG indexing failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/rag/status")
async def rag_status():
    """Return current RAG index status."""
    return rag_service.index_status()


@app.post("/rag/query")
async def rag_query(request: ChatRequest):
    """Query the indexed codebase using RAG."""
    try:
        result = await rag_service.rag_query(
            query=request.query,
            orchestrator=orchestrator,
            model_preference=request.model,
        )
        return result
    except Exception as exc:
        logger.error("RAG query failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/debug/analyze")
async def debug_analyze(request: DebugRequest):
    """Analyze error logs for root cause."""
    try:
        result = await debug_service.analyze_errors(
            log_content=request.log_content,
            orchestrator=orchestrator,
            model_preference=request.model,
            additional_context=request.additional_context,
        )
        return result
    except Exception as exc:
        logger.error("Debug analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/graph/parse")
async def graph_parse(request: GraphParseRequest):
    """Parse a codebase and build a dependency graph."""
    if not os.path.isdir(request.directory):
        raise HTTPException(status_code=400, detail=f"Directory not found: {request.directory}")

    try:
        parsed = graph_service.parse_directory(request.directory)
        graph = graph_service.build_dependency_graph(parsed)
        return graph
    except Exception as exc:
        logger.error("Graph parsing failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/graph/deps")
async def graph_deps(module_id: str):
    """Query dependencies for a specific module (in-memory graph)."""
    # This uses in-memory data; for Neo4j, use the Neo4jGraphStore
    return {"message": "Use POST /graph/parse first, then query the returned graph data"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    ollama_ok = await orchestrator.ollama.is_available()
    return {
        "status": "healthy",
        "providers": {
            "ollama": "available" if ollama_ok else "unavailable",
            "groq": "configured" if settings.GROQ_API_KEY else "not_configured",
            "gemini": "configured" if settings.GEMINI_API_KEY else "not_configured",
        },
    }


# ── Frontend Static Files ─────────────────────────────────────────

FRONTEND_DIR = PROJECT_ROOT / "frontend"


@app.get("/")
async def serve_frontend():
    """Serve the frontend index.html."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return JSONResponse(
        {"message": "Frontend not found. Place files in /frontend/ directory."},
        status_code=404,
    )


# Mount static files (CSS, JS) AFTER specific routes
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ── Entry Point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "services.api_gateway.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
