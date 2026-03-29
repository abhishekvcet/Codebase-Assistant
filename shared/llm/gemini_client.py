"""
Google Gemini LLM client — cloud inference for deep reasoning.
Used for complex architectural analysis and documentation generation.
"""

import logging
from typing import Optional

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
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(self.model_name)
        return self._model

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

        # Rebuild model if a different model name is requested
        if model_name != self.model_name or self._model is None:
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                model_name,
                system_instruction=system_prompt,
            )
        else:
            model = self._get_model()

        logger.info("Gemini request → model=%s, prompt_len=%d", model_name, len(prompt))

        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        response = await model.generate_content_async(
            prompt,
            generation_config=generation_config,
        )

        text = ""
        try:
            text = response.text.strip()
        except (ValueError, AttributeError):
            if response.candidates:
                parts = response.candidates[0].content.parts
                text = "".join(p.text for p in parts).strip()

        return LLMResponse(
            text=text,
            model_used=model_name,
            provider=self.provider_name,
            metadata={
                "safety_ratings": str(getattr(response, "safety_ratings", [])),
            },
        )

    async def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            self._get_model()
            return True
        except Exception:
            return False
