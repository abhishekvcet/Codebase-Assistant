"""
Central configuration management.
Loads all environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


class Settings:
    """Application-wide settings sourced from environment variables."""

    # ── Ollama (Local LLM) ──────────────────────────────────────────
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL_FAST: str = os.getenv("OLLAMA_MODEL_FAST", "phi3")
    OLLAMA_MODEL_COMPLEX: str = os.getenv("OLLAMA_MODEL_COMPLEX", "llama3:8b")
    OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "120"))

    # ── Groq (Cloud LLM) ───────────────────────────────────────────
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    GROQ_TIMEOUT: int = int(os.getenv("GROQ_TIMEOUT", "60"))

    # ── Gemini (Cloud LLM) ─────────────────────────────────────────
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_TIMEOUT: int = int(os.getenv("GEMINI_TIMEOUT", "60"))

    # ── Database ───────────────────────────────────────────────────
    POSTGRES_URL: str = os.getenv(
        "POSTGRES_URL", "postgresql://codeassist:codeassist@localhost:5432/codeassist"
    )
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "codeassist")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # ── RAG / ChromaDB ─────────────────────────────────────────────
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL", "all-MiniLM-L6-v2"
    )
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "512"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "64"))
    TOP_K_RESULTS: int = int(os.getenv("TOP_K_RESULTS", "5"))
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    CHROMA_COLLECTION_NAME: str = os.getenv("CHROMA_COLLECTION_NAME", "codebase")

    # ── Server ─────────────────────────────────────────────────────
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
