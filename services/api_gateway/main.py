"""
API Gateway — FastAPI application serving as the central entry point.

Pipeline: User (CLI/Web) → API Gateway → RAG (ChromaDB) → LLM → Response

Endpoints:
  POST /chat              → Main chat (RAG-first, then LLM)
  POST /index             → Index a codebase directory
  POST /debug             → Analyze error logs
  POST /deps              → Dependency analysis
  GET  /rag/status        → RAG index status
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
    logger.info("   ChromaDB   : %s", settings.CHROMA_PERSIST_DIR)

    # Check Ollama availability
    available = await orchestrator.ollama.is_available()
    logger.info("   Ollama     : %s", "✅ reachable" if available else "❌ unreachable")

    # Log RAG index status
    rag_status = rag_service.index_status()
    logger.info("   RAG Index  : %d chunks indexed", rag_status.get("total_chunks", 0))

    yield
    logger.info("Shutting down...")


# ── App ────────────────────────────────────────────────────────────

app = FastAPI(
    title="Intelligent Codebase Assistant",
    description="AI-powered code understanding, debugging, and documentation",
    version="2.0.0",
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
    mode: str = Field("chat", description="Mode: chat | debug | deps")
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
    context_used: list = Field(default_factory=list)
    context_chunks: int = 0


class IndexRequest(BaseModel):
    directory: str = Field(..., description="Path to the codebase directory to index")


class DebugRequest(BaseModel):
    log_content: str = Field(..., description="Error log content to analyze")
    model: str = Field("groq", description="Model preference for analysis")
    additional_context: str = Field("", description="Extra context for analysis")


class DepsRequest(BaseModel):
    file_path: str = Field("", description="File path to analyze dependencies for")
    query: str = Field("", description="Dependency impact query")
    model: str = Field("auto", description="Model preference")


class GraphParseRequest(BaseModel):
    directory: str = Field(..., description="Path to the codebase directory to parse")


# ── Endpoints ──────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint — ALWAYS queries RAG first, then sends context to LLM.

    Pipeline: Query → RAG (ChromaDB) → Context Injection → LLM → Response
    """
    start_time = time.perf_counter()
    logger.info(
        "Chat request: model=%s, mode=%s, query_len=%d, query=%.100s",
        request.model, request.mode, len(request.query), request.query,
    )

    try:
        # ALWAYS use RAG pipeline — this is the enforced flow
        result = await rag_service.rag_query(
            query=request.query,
            orchestrator=orchestrator,
            model_preference=request.model,
            top_k=settings.TOP_K_RESULTS,
        )

        total_ms = round((time.perf_counter() - start_time) * 1000, 2)

        logger.info(
            "Chat response: model=%s, provider=%s, fallback=%s, "
            "context_chunks=%d, latency=%.0fms",
            result.get("model_used"), result.get("provider"),
            result.get("fallback_used"), result.get("context_chunks", 0),
            total_ms,
        )

        return ChatResponse(
            answer=result["answer"],
            model_used=result["model_used"],
            provider=result["provider"],
            mode=request.mode,
            fallback_used=result.get("fallback_used", False),
            latency_ms=result.get("latency_ms", total_ms),
            tokens_used=result.get("tokens_used"),
            context_used=result.get("context_used", []),
            context_chunks=result.get("context_chunks", 0),
        )

    except RuntimeError as exc:
        logger.error("All LLM providers failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="All LLM providers failed. Check your configuration and API keys.",
        )
    except Exception as exc:
        logger.error("Chat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Index Endpoint ─────────────────────────────────────────────────

@app.post("/index")
async def index_codebase(request: IndexRequest):
    """Index a codebase directory for RAG queries."""
    directory = request.directory
    if not os.path.isdir(directory):
        raise HTTPException(status_code=400, detail=f"Directory not found: {directory}")

    logger.info("Indexing directory: %s", directory)

    try:
        chunks = rag_service.chunk_directory(directory)
        if not chunks:
            raise HTTPException(status_code=400, detail="No supported files found in directory")

        rag_service.build_index(chunks)
        status = rag_service.index_status()
        logger.info("Indexing complete: %d chunks", status.get("total_chunks", 0))
        return {"status": "indexed", **status}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Indexing failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# Alias: /rag/index → /index
@app.post("/rag/index")
async def rag_index(request: IndexRequest):
    """Alias for /index."""
    return await index_codebase(request)


@app.get("/rag/status")
async def rag_status():
    """Return current RAG index status."""
    return rag_service.index_status()


# ── Debug Endpoint ─────────────────────────────────────────────────

@app.post("/debug")
async def debug_analyze_short(request: DebugRequest):
    """Analyze error logs for root cause."""
    return await _debug_analyze(request)


@app.post("/debug/analyze")
async def debug_analyze(request: DebugRequest):
    """Analyze error logs for root cause (legacy endpoint)."""
    return await _debug_analyze(request)


async def _debug_analyze(request: DebugRequest):
    """Shared debug analysis logic."""
    logger.info("Debug analysis request: model=%s, log_len=%d", request.model, len(request.log_content))

    try:
        result = await debug_service.analyze_errors(
            log_content=request.log_content,
            orchestrator=orchestrator,
            model_preference=request.model,
            additional_context=request.additional_context,
        )

        logger.info(
            "Debug analysis complete: model=%s, errors_found=%d",
            result.get("model_used"), result.get("parsed_errors", 0),
        )

        return result
    except Exception as exc:
        logger.error("Debug analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Dependency Endpoint ───────────────────────────────────────────

@app.post("/deps")
async def deps_query(request: DepsRequest):
    """Dependency analysis — parse file or answer impact queries."""
    if request.file_path:
        if not os.path.isfile(request.file_path):
            raise HTTPException(status_code=400, detail=f"File not found: {request.file_path}")

        try:
            info = graph_service.parse_python_file(str(Path(request.file_path).resolve()))
            return info
        except Exception as exc:
            logger.error("Dependency parsing failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc))

    elif request.query:
        # Use RAG to answer dependency impact questions
        try:
            result = await rag_service.rag_query(
                query=f"Dependency analysis: {request.query}",
                orchestrator=orchestrator,
                model_preference=request.model,
            )
            return result
        except Exception as exc:
            logger.error("Dependency query failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc))

    raise HTTPException(status_code=400, detail="Provide either file_path or query")


# ── Graph Endpoints (legacy) ──────────────────────────────────────

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
    """Query dependencies for a specific module."""
    return {"message": "Use POST /graph/parse first, then query the returned graph data"}


# ── Shutdown ───────────────────────────────────────────────────────

@app.post("/shutdown")
async def shutdown():
    """Shutdown the server."""
    logger.info("Shutdown requested via API...")
    # Delay shutdown slightly to allow response to be sent
    import threading
    import signal
    
    def kill_process():
        time.sleep(1)
        os.kill(os.getpid(), signal.SIGTERM)
        
    threading.Thread(target=kill_process, daemon=True).start()
    return {"message": "Shutting down Intelligent Codebase Assistant..."}


# ── Health Check ───────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check endpoint."""
    ollama_ok = await orchestrator.ollama.is_available()
    rag_stat = rag_service.index_status()

    return {
        "status": "healthy",
        "providers": {
            "ollama": "available" if ollama_ok else "unavailable",
            "groq": "configured" if settings.GROQ_API_KEY and settings.GROQ_API_KEY != "your_groq_api_key_here" else "not_configured",
            "gemini": "configured" if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_gemini_api_key_here" else "not_configured",
        },
        "rag": {
            "indexed": rag_stat.get("indexed", False),
            "total_chunks": rag_stat.get("total_chunks", 0),
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
