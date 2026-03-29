"""
Ollama LLM client — talks to a locally running Ollama instance.
Supports automatic model selection between phi3 (fast) and llama3:8b (complex).
"""

import httpx
import logging
from typing import Optional

from .base import LLMClient, LLMResponse
from shared.config import settings

logger = logging.getLogger(__name__)


class OllamaClient(LLMClient):
    """Client for the local Ollama inference server."""

    provider_name = "ollama"

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model_fast = settings.OLLAMA_MODEL_FAST
        self.model_complex = settings.OLLAMA_MODEL_COMPLEX
        self.timeout = settings.OLLAMA_TIMEOUT

    def _select_model(self, prompt: str, **kwargs) -> str:
        """Pick phi3 for short/simple queries, llama3:8b for longer/complex ones."""
        explicit = kwargs.get("model")
        if explicit:
            return explicit

        word_count = len(prompt.split())
        complex_indicators = [
            "explain", "analyze", "architecture", "refactor",
            "debug", "root cause", "dependency", "design pattern",
            "trade-off", "compare", "why", "how does",
        ]
        is_complex = word_count > 40 or any(
            kw in prompt.lower() for kw in complex_indicators
        )
        return self.model_complex if is_complex else self.model_fast

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        model = self._select_model(prompt, **kwargs)

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        logger.info("Ollama request → model=%s, prompt_len=%d", model, len(prompt))

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        return LLMResponse(
            text=data.get("response", "").strip(),
            model_used=model,
            provider=self.provider_name,
            metadata={
                "total_duration": data.get("total_duration"),
                "eval_count": data.get("eval_count"),
            },
        )

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """Return names of models currently pulled in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                return [m["name"] for m in resp.json().get("models", [])]
        except Exception as exc:
            logger.warning("Cannot list Ollama models: %s", exc)
            return []
