"""
RAG Service — Retrieval-Augmented Generation for codebase understanding.

Pipeline:
  1. Chunk source code files
  2. Store in ChromaDB (persistent) with metadata
  3. Retrieve top-k context chunks
  4. Inject context into strict prompt template
  5. Send to LLM — context-only answers enforced
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions

from shared.config import settings

logger = logging.getLogger(__name__)

# ── ChromaDB Client ────────────────────────────────────────────────

_chroma_client: Optional[chromadb.PersistentClient] = None
_collection = None


def _get_collection():
    """Get or create the ChromaDB collection with persistent storage."""
    global _chroma_client, _collection
    if _collection is None:
        persist_dir = os.path.abspath(settings.CHROMA_PERSIST_DIR)
        os.makedirs(persist_dir, exist_ok=True)

        logger.info("Initializing ChromaDB at: %s", persist_dir)
        _chroma_client = chromadb.PersistentClient(path=persist_dir)

        # Use built-in sentence-transformer embedding function
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.EMBEDDING_MODEL
        )

        _collection = _chroma_client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB collection '%s' ready (%d documents)",
            settings.CHROMA_COLLECTION_NAME,
            _collection.count(),
        )
    return _collection


# ── Code Chunking ──────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
    ".kt", ".scala", ".sh", ".bash", ".yaml", ".yml", ".json",
    ".toml", ".md", ".txt", ".html", ".css", ".sql",
}

EXTENSION_TO_LANGUAGE = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "jsx", ".tsx": "tsx", ".java": "java", ".go": "go",
    ".rs": "rust", ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
    ".cs": "csharp", ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".kt": "kotlin", ".scala": "scala", ".sh": "bash", ".bash": "bash",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml",
    ".md": "markdown", ".txt": "text", ".html": "html", ".css": "css",
    ".sql": "sql",
}


def _detect_scope(text: str, language: str) -> str:
    """Try to detect the function/class name from a chunk of code."""
    if language == "python":
        # Find the last class or function definition
        matches = re.findall(r'^(?:class|def)\s+(\w+)', text, re.MULTILINE)
        if matches:
            return matches[-1]
    elif language in ("javascript", "typescript", "jsx", "tsx"):
        matches = re.findall(
            r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(|class\s+(\w+))',
            text, re.MULTILINE,
        )
        if matches:
            flat = [name for group in matches for name in group if name]
            if flat:
                return flat[-1]
    elif language == "java":
        matches = re.findall(r'(?:class|interface)\s+(\w+)', text, re.MULTILINE)
        if matches:
            return matches[-1]
    return ""


def chunk_file(
    file_path: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> list[dict]:
    """Split a source file into overlapping text chunks with metadata."""
    ext = Path(file_path).suffix.lower()
    language = EXTENSION_TO_LANGUAGE.get(ext, "unknown")

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
            text = "".join(current_chunk_lines)
            scope = _detect_scope(text, language)
            chunks.append({
                "text": text,
                "file": file_path,
                "start_line": start_line,
                "end_line": i,
                "language": language,
                "scope": scope,
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
        text = "".join(current_chunk_lines)
        scope = _detect_scope(text, language)
        chunks.append({
            "text": text,
            "file": file_path,
            "start_line": start_line,
            "end_line": len(lines),
            "language": language,
            "scope": scope,
        })

    return chunks


def chunk_directory(directory: str) -> list[dict]:
    """Recursively chunk all supported files in a directory."""
    all_chunks = []
    directory_path = Path(directory)

    skip_dirs = {
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        ".env", "dist", "build", ".idea", ".vscode", "chroma_db",
    }

    for root, dirs, files in os.walk(directory_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for file in files:
            ext = Path(file).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS:
                fpath = os.path.join(root, file)
                all_chunks.extend(chunk_file(fpath))

    logger.info("Chunked %d chunks from %s", len(all_chunks), directory)
    return all_chunks


# ── ChromaDB Index ─────────────────────────────────────────────────

def build_index(chunks: list[dict], directory: str = "") -> None:
    """Build/update ChromaDB index from code chunks."""
    collection = _get_collection()

    # Save last indexed directory if provided
    if directory:
        persist_dir = os.path.abspath(settings.CHROMA_PERSIST_DIR)
        meta_path = os.path.join(persist_dir, "metadata.json")
        try:
            with open(meta_path, "w") as f:
                json.dump({"last_indexed_directory": os.path.abspath(directory)}, f)
        except Exception as exc:
            logger.warning("Failed to save index metadata: %s", exc)

    # Prepare data for upserting
    ids = []
    documents = []
    metadatas = []

    for i, chunk in enumerate(chunks):
        # Create a deterministic ID based on file + line range
        chunk_id = f"{chunk['file']}:{chunk['start_line']}-{chunk['end_line']}"
        ids.append(chunk_id)
        documents.append(chunk["text"])
        metadatas.append({
            "file_path": chunk["file"],
            "start_line": chunk["start_line"],
            "end_line": chunk["end_line"],
            "language": chunk["language"],
            "scope": chunk.get("scope", ""),
        })

    # Upsert in batches of 500 (ChromaDB limit)
    batch_size = 500
    for start in range(0, len(ids), batch_size):
        end = min(start + batch_size, len(ids))
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
        logger.info(
            "Upserted batch %d-%d of %d chunks",
            start, end, len(ids),
        )

    logger.info(
        "ChromaDB index updated: %d documents in collection '%s'",
        collection.count(),
        settings.CHROMA_COLLECTION_NAME,
    )


def search(query: str, top_k: int = 5) -> list[dict]:
    """Search ChromaDB for chunks most relevant to the query."""
    collection = _get_collection()

    if collection.count() == 0:
        logger.warning("ChromaDB collection is empty. Index a codebase first.")
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    if results and results["documents"] and results["documents"][0]:
        for doc, meta, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity score: 1 - (distance / 2)
            score = 1.0 - (distance / 2.0)
            chunks.append({
                "text": doc,
                "file": meta.get("file_path", "unknown"),
                "start_line": meta.get("start_line", 0),
                "end_line": meta.get("end_line", 0),
                "language": meta.get("language", "unknown"),
                "scope": meta.get("scope", ""),
                "score": round(score, 4),
            })

    logger.info("RAG search returned %d results for query: %.80s...", len(chunks), query)
    return chunks


# ── RAG Pipeline ───────────────────────────────────────────────────

async def rag_query(
    query: str,
    orchestrator,
    model_preference: str = "auto",
    top_k: int = 5,
) -> dict:
    """
    Full RAG pipeline: retrieve relevant chunks → compose context → generate answer.
    Enforces context-only answers via strict prompt template.
    """
    # Retrieve
    results = search(query, top_k=top_k)
    context_used = []

    if not results:
        context = "⚠ WARNING: No relevant code context was found in the index. The codebase may not be indexed yet."
        logger.warning("RAG returned no results for query: %s", query)
    else:
        context_parts = []
        for r in results:
            scope_label = f" → {r['scope']}" if r['scope'] else ""
            context_parts.append(
                f"--- {r['file']} (lines {r['start_line']}-{r['end_line']}, "
                f"lang={r['language']}{scope_label}, "
                f"score={r['score']:.3f}) ---\n{r['text']}"
            )
            context_used.append({
                "file": r["file"],
                "lines": f"{r['start_line']}-{r['end_line']}",
                "scope": r["scope"],
                "score": r["score"],
            })
        context = "\n\n".join(context_parts)

    # Strict augmented prompt — enforce context-only answers
    augmented_prompt = (
        "Use ONLY the following code context to answer the question.\n"
        "If the context does not contain enough information, say so explicitly.\n"
        "Do NOT make up code or information not present in the context.\n\n"
        f"## Code Context\n\n{context}\n\n"
        f"## Question\n\n{query}\n\n"
        "Provide a clear, detailed answer referencing the specific code where relevant."
    )

    response = await orchestrator.generate_response(
        augmented_prompt,
        model_preference=model_preference,
    )
    response["context_chunks"] = len(results)
    response["context_used"] = context_used
    return response


def index_status() -> dict:
    """Return the current state of the ChromaDB index."""
    try:
        collection = _get_collection()
        count = collection.count()
        return {
            "indexed": count > 0,
            "total_chunks": count,
            "total_vectors": count,
            "persist_directory": settings.CHROMA_PERSIST_DIR,
            "collection_name": settings.CHROMA_COLLECTION_NAME,
        }
    except Exception as exc:
        logger.error("Failed to get index status: %s", exc)
        return {
            "indexed": False,
            "total_chunks": 0,
            "total_vectors": 0,
            "error": str(exc),
        }

def get_last_indexed_directory() -> Optional[str]:
    """Retrieve the path of the last indexed codebase."""
    persist_dir = os.path.abspath(settings.CHROMA_PERSIST_DIR)
    meta_path = os.path.join(persist_dir, "metadata.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r") as f:
                data = json.load(f)
                return data.get("last_indexed_directory")
        except Exception:
            pass
    return None
