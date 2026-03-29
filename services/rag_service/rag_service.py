"""
RAG Service — Retrieval-Augmented Generation for codebase understanding.

Pipeline:
  1. Chunk source code files
  2. Generate embeddings via sentence-transformers
  3. Store/search with FAISS
  4. Retrieve top-k context chunks
  5. Send context + query to LLM
"""

import os
import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Lazy-loaded heavy dependencies ─────────────────────────────────
_faiss_index = None
_embedding_model = None
_chunk_store: list[dict] = []  # [{text, file, start_line, end_line}, ...]


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        from shared.config import settings
        logger.info("Loading embedding model: %s", settings.EMBEDDING_MODEL)
        _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _embedding_model


# ── Code Chunking ──────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
    ".kt", ".scala", ".sh", ".bash", ".yaml", ".yml", ".json",
    ".toml", ".md", ".txt", ".html", ".css", ".sql",
}


def chunk_file(
    file_path: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[dict]:
    """Split a source file into overlapping text chunks."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception as exc:
        logger.warning("Cannot read %s: %s", file_path, exc)
        return []

    chunks = []
    current_chunk_lines = []
    current_len = 0
    start_line = 1

    for i, line in enumerate(lines, 1):
        current_chunk_lines.append(line)
        current_len += len(line)

        if current_len >= chunk_size:
            chunks.append({
                "text": "".join(current_chunk_lines),
                "file": file_path,
                "start_line": start_line,
                "end_line": i,
            })
            # Overlap: keep last N characters worth of lines
            overlap_lines = []
            overlap_len = 0
            for ol in reversed(current_chunk_lines):
                if overlap_len + len(ol) > chunk_overlap:
                    break
                overlap_lines.insert(0, ol)
                overlap_len += len(ol)

            current_chunk_lines = overlap_lines
            current_len = overlap_len
            start_line = i - len(overlap_lines) + 1

    if current_chunk_lines:
        chunks.append({
            "text": "".join(current_chunk_lines),
            "file": file_path,
            "start_line": start_line,
            "end_line": len(lines),
        })

    return chunks


def chunk_directory(directory: str) -> list[dict]:
    """Recursively chunk all supported files in a directory."""
    all_chunks = []
    directory_path = Path(directory)

    skip_dirs = {
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        ".env", "dist", "build", ".idea", ".vscode",
    }

    for root, dirs, files in os.walk(directory_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for file in files:
            ext = Path(file).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                fpath = os.path.join(root, file)
                all_chunks.extend(chunk_file(fpath))

    logger.info("Chunked %d files → %d chunks from %s", len(all_chunks), len(all_chunks), directory)
    return all_chunks


# ── FAISS Index ────────────────────────────────────────────────────

def build_index(chunks: list[dict]) -> None:
    """Build a FAISS index from code chunks."""
    global _faiss_index, _chunk_store
    import faiss

    model = _get_embedding_model()
    texts = [c["text"] for c in chunks]

    logger.info("Generating embeddings for %d chunks...", len(texts))
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    embeddings = embeddings.astype("float32")

    # Normalize for cosine similarity
    faiss.normalize_L2(embeddings)

    dim = embeddings.shape[1]
    _faiss_index = faiss.IndexFlatIP(dim)  # Inner product = cosine after normalization
    _faiss_index.add(embeddings)
    _chunk_store = chunks

    logger.info("FAISS index built: %d vectors, dim=%d", _faiss_index.ntotal, dim)


def search(query: str, top_k: int = 5) -> list[dict]:
    """Search the FAISS index for chunks most relevant to the query."""
    global _faiss_index, _chunk_store
    import faiss

    if _faiss_index is None or not _chunk_store:
        logger.warning("FAISS index not built yet. Call build_index() first.")
        return []

    model = _get_embedding_model()
    query_embedding = model.encode([query], convert_to_numpy=True).astype("float32")
    faiss.normalize_L2(query_embedding)

    scores, indices = _faiss_index.search(query_embedding, top_k)

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        chunk = _chunk_store[idx].copy()
        chunk["score"] = float(score)
        results.append(chunk)

    return results


# ── RAG Pipeline ───────────────────────────────────────────────────

async def rag_query(
    query: str,
    orchestrator,
    model_preference: str = "auto",
    top_k: int = 5,
) -> dict:
    """
    Full RAG pipeline: retrieve relevant chunks → compose context → generate answer.
    """
    # Retrieve
    results = search(query, top_k=top_k)

    if not results:
        context = "No relevant code context was found in the index."
    else:
        context_parts = []
        for r in results:
            context_parts.append(
                f"--- {r['file']} (lines {r['start_line']}-{r['end_line']}, "
                f"score={r['score']:.3f}) ---\n{r['text']}"
            )
        context = "\n\n".join(context_parts)

    # Augmented prompt
    augmented_prompt = (
        f"You are an expert code assistant. Use the following code context to answer the question.\n\n"
        f"## Relevant Code Context\n\n{context}\n\n"
        f"## Question\n\n{query}\n\n"
        f"Provide a clear, detailed answer referencing the specific code where relevant."
    )

    response = await orchestrator.generate_response(
        augmented_prompt,
        model_preference=model_preference,
    )
    response["context_chunks"] = len(results)
    return response


def index_status() -> dict:
    """Return the current state of the FAISS index."""
    return {
        "indexed": _faiss_index is not None,
        "total_chunks": len(_chunk_store),
        "total_vectors": _faiss_index.ntotal if _faiss_index else 0,
    }
