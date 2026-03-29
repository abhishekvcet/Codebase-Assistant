"""
Abstract base class for all LLM clients.
Every provider (Ollama, Groq, Gemini) implements this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    text: str
    model_used: str
    provider: str  # "ollama" | "groq" | "gemini"
    latency_ms: float = 0.0
    tokens_used: Optional[int] = None
    metadata: dict = field(default_factory=dict)


class LLMClient(ABC):
    """Abstract LLM client interface."""

    provider_name: str = "unknown"

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        """Generate a response from the LLM."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if this LLM provider is currently reachable."""
        ...

    async def timed_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        """Generate with automatic latency tracking."""
        start = time.perf_counter()
        try:
            response = await self.generate(
                prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            response.latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "LLM [%s/%s] responded in %.0fms",
                response.provider,
                response.model_used,
                response.latency_ms,
            )
            return response
        except Exception as exc:
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "LLM [%s] failed after %.0fms: %s",
                self.provider_name,
                elapsed,
                exc,
            )
            raise
