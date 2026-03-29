"""
LLM Orchestrator — the brain of the model selection system.

Implements:
  • User-controlled routing  (local / groq / gemini / auto)
  • Auto-classification      (simple → phi3, rag → llama3, debug → groq, complex → gemini)
  • Cascading fallback        (local → groq → gemini)
"""

import logging
import re
from enum import Enum
from typing import Optional

from .base import LLMResponse
from .ollama_client import OllamaClient
from .groq_client import GroqClient
from .gemini_client import GeminiClient

logger = logging.getLogger(__name__)


class QueryCategory(str, Enum):
    SIMPLE = "simple"
    RAG = "rag"
    DEBUG = "debug"
    COMPLEX = "complex"


class LLMOrchestrator:
    """Centralized model selection with fallback chain."""

    def __init__(self):
        self.ollama = OllamaClient()
        self.groq = GroqClient()
        self.gemini = GeminiClient()

        # Fallback order
        self._fallback_chain = [
            ("local", self._call_local),
            ("groq", self._call_groq),
            ("gemini", self._call_gemini),
        ]

    # ── Public API ──────────────────────────────────────────────────

    async def generate_response(
        self,
        query: str,
        model_preference: str = "auto",
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> dict:
        """
        Primary entry point.
        Returns dict with: answer, model_used, mode, fallback_used, latency_ms
        """
        fallback_used = False

        if model_preference == "auto":
            category = self._classify_query(query)
            model_preference = self._category_to_provider(category)
            logger.info("Auto-classified as '%s' → provider '%s'", category, model_preference)

        try:
            response = await self._route(
                model_preference, query, system_prompt, temperature, max_tokens
            )
        except Exception as exc:
            logger.warning(
                "Primary provider '%s' failed (%s), starting fallback chain",
                model_preference,
                exc,
            )
            response = await self._fallback(
                query, system_prompt, temperature, max_tokens, skip=model_preference
            )
            fallback_used = True

        return {
            "answer": response.text,
            "model_used": response.model_used,
            "provider": response.provider,
            "mode": model_preference,
            "fallback_used": fallback_used,
            "latency_ms": response.latency_ms,
            "tokens_used": response.tokens_used,
        }

    # ── Query Classification ───────────────────────────────────────

    @staticmethod
    def _classify_query(query: str) -> QueryCategory:
        q = query.lower()

        # Debug patterns
        debug_words = [
            "error", "bug", "exception", "traceback", "fail", "crash", "stack trace",
            "debug", "broken", "not working", "fix", "issue", "stderr", "panic",
        ]
        if any(w in q for w in debug_words):
            return QueryCategory.DEBUG

        # Complex / architecture patterns
        complex_words = [
            "architecture", "design pattern", "refactor", "trade-off", "compare",
            "best practice", "optimize", "performance", "scale", "security",
            "migration", "complex", "comprehensive", "in-depth",
        ]
        if any(w in q for w in complex_words):
            return QueryCategory.COMPLEX

        # RAG patterns — code-specific retrieval
        rag_words = [
            "explain", "how does", "what does", "find", "search", "where is",
            "function", "class", "module", "import", "dependency", "flow",
            "codebase", "source code", "implementation",
        ]
        if any(w in q for w in rag_words):
            return QueryCategory.RAG

        return QueryCategory.SIMPLE

    @staticmethod
    def _category_to_provider(category: QueryCategory) -> str:
        return {
            QueryCategory.SIMPLE: "local",
            QueryCategory.RAG: "local",
            QueryCategory.DEBUG: "groq",
            QueryCategory.COMPLEX: "gemini",
        }[category]

    # ── Routing ────────────────────────────────────────────────────

    async def _route(
        self,
        provider: str,
        query: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        dispatch = {
            "local": self._call_local,
            "groq": self._call_groq,
            "gemini": self._call_gemini,
        }
        handler = dispatch.get(provider)
        if not handler:
            raise ValueError(f"Unknown provider: {provider}")
        return await handler(query, system_prompt, temperature, max_tokens)

    async def _call_local(
        self, query: str, system_prompt, temperature, max_tokens
    ) -> LLMResponse:
        return await self.ollama.timed_generate(
            query,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def _call_groq(
        self, query: str, system_prompt, temperature, max_tokens
    ) -> LLMResponse:
        return await self.groq.timed_generate(
            query,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def _call_gemini(
        self, query: str, system_prompt, temperature, max_tokens
    ) -> LLMResponse:
        return await self.gemini.timed_generate(
            query,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # ── Fallback ───────────────────────────────────────────────────

    async def _fallback(
        self,
        query: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
        skip: str = "",
    ) -> LLMResponse:
        """Try all providers in fallback order, skipping the one that already failed."""
        for name, handler in self._fallback_chain:
            if name == skip:
                continue
            try:
                logger.info("Fallback → trying '%s'", name)
                return await handler(query, system_prompt, temperature, max_tokens)
            except Exception as exc:
                logger.warning("Fallback '%s' also failed: %s", name, exc)
                continue

        raise RuntimeError("All LLM providers failed. Check your configuration and API keys.")
