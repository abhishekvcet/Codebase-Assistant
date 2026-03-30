"""
Google Gemini LLM client — cloud inference for deep reasoning.
Used for complex architectural analysis and documentation generation.

Features:
  • Retry with exponential backoff (3 attempts)
  • API key validation before call
  • Response validation (non-empty text)
  • Safety block handling
"""

import logging
from typing import Optional

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from .base import LLMClient, LLMResponse
from shared.config import settings

logger = logging.getLogger(__name__)


class GeminiClient(LLMClient):
    """Client for Google's Gemini generative AI API."""

    provider_name = "gemini"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = settings.GEMINI_MODEL
        self.timeout = settings.GEMINI_TIMEOUT
        self._model = None

    def _get_model(self):
        if self._model is None:
            if not self.api_key or self.api_key == "your_gemini_api_key_here":
                raise ValueError(
                    "Gemini API key not configured. Set GEMINI_API_KEY in .env"
                )
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(self.model_name)
        return self._model

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
        import google.generativeai as genai

        model_name = kwargs.get("model", self.model_name)

        # Rebuild model if a different model name is requested or with system prompt
        if model_name != self.model_name or self._model is None or system_prompt:
            if not self.api_key or self.api_key == "your_gemini_api_key_here":
                raise ValueError(
                    "Gemini API key not configured. Set GEMINI_API_KEY in .env"
                )
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                model_name,
                system_instruction=system_prompt,
            )
        else:
            model = self._get_model()

        logger.info("Gemini request → model=%s, prompt_len=%d", model_name, len(prompt))

        try:
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )

            response = await model.generate_content_async(
                prompt,
                generation_config=generation_config,
            )
        except ValueError:
            # API key validation error — don't retry
            raise
        except Exception as exc:
            logger.error("Gemini API error: %s", exc)
            raise

        # Extract text with comprehensive fallback
        text = ""
        try:
            text = response.text.strip()
        except (ValueError, AttributeError):
            # Safety block or other issue — try candidates
            if hasattr(response, "candidates") and response.candidates:
                try:
                    parts = response.candidates[0].content.parts
                    text = "".join(p.text for p in parts).strip()
                except (AttributeError, IndexError):
                    pass

        if not text:
            # Check for safety blocks
            safety_info = getattr(response, "prompt_feedback", None)
            if safety_info:
                logger.warning("Gemini safety block: %s", safety_info)
                raise RuntimeError(
                    f"Gemini blocked the response due to safety settings: {safety_info}"
                )
            raise RuntimeError("Gemini returned empty response")

        return LLMResponse(
            text=text,
            model_used=model_name,
            provider=self.provider_name,
            metadata={
                "safety_ratings": str(getattr(response, "safety_ratings", [])),
            },
        )

    async def is_available(self) -> bool:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return False
        try:
            self._get_model()
            return True
        except Exception:
            return False
