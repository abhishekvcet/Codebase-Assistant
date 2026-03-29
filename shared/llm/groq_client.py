"""
Groq LLM client — cloud inference via the Groq API.
Used for fast debugging and quick reasoning tasks.
"""

import logging
from typing import Optional

from .base import LLMClient, LLMResponse
from shared.config import settings

logger = logging.getLogger(__name__)


class GroqClient(LLMClient):
    """Client for the Groq cloud inference API."""

    provider_name = "groq"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GROQ_API_KEY
        self.model = settings.GROQ_MODEL
        self.timeout = settings.GROQ_TIMEOUT
        self._client = None

    def _get_client(self):
        if self._client is None:
            from groq import AsyncGroq
            self._client = AsyncGroq(
                api_key=self.api_key,
                timeout=self.timeout,
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        model = kwargs.get("model", self.model)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.info("Groq request → model=%s, prompt_len=%d", model, len(prompt))

        client = self._get_client()
        completion = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        choice = completion.choices[0]
        usage = completion.usage

        return LLMResponse(
            text=choice.message.content.strip(),
            model_used=model,
            provider=self.provider_name,
            tokens_used=usage.total_tokens if usage else None,
            metadata={
                "prompt_tokens": usage.prompt_tokens if usage else None,
                "completion_tokens": usage.completion_tokens if usage else None,
                "finish_reason": choice.finish_reason,
            },
        )

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            client = self._get_client()
            # Light-weight check: list models
            await client.models.list()
            return True
        except Exception:
            return False
