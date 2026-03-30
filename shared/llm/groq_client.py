"""
Groq LLM client — cloud inference via the Groq API.
Used for fast debugging and quick reasoning tasks.

Features:
  • Retry with exponential backoff (3 attempts)
  • API key validation before call
  • Timeout / auth / empty-response handling
"""

import logging
from typing import Optional

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

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
            if not self.api_key or self.api_key == "your_groq_api_key_here":
                raise ValueError(
                    "Groq API key not configured. Set GROQ_API_KEY in .env"
                )
            from groq import AsyncGroq
            self._client = AsyncGroq(
                api_key=self.api_key,
                timeout=self.timeout,
            )
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
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

        try:
            client = self._get_client()
            completion = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except ValueError:
            # API key validation error — don't retry
            raise
        except Exception as exc:
            logger.error("Groq API error: %s", exc)
            raise

        # Validate response
        if not completion.choices:
            raise RuntimeError("Groq returned empty response (no choices)")

        choice = completion.choices[0]
        text = choice.message.content

        if not text or not text.strip():
            raise RuntimeError("Groq returned empty response text")

        usage = completion.usage

        return LLMResponse(
            text=text.strip(),
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
        if not self.api_key or self.api_key == "your_groq_api_key_here":
            return False
        try:
            client = self._get_client()
            await client.models.list()
            return True
        except Exception:
            return False
