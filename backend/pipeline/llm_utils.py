"""
Utility functions for LLM providers.
"""

import logging
import os
import random
import threading
import time
from typing import Any, Dict, List, Optional
from .models import ModelProvider, OllamaProvider, GeminiProvider
from .prompt import MODEL_PROVIDER_MAPPING, GEMINI_API_KEY

logger = logging.getLogger(__name__)

# Free-tier Gemini keys allow ~10 requests/minute, and one resume costs ~8
# calls, so rate limiting is a normal condition here, not an error: gate
# concurrency process-wide and retry 429s with backoff.
LLM_MAX_CONCURRENCY = int(os.getenv("LLM_MAX_CONCURRENCY", "2"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "5"))
_llm_gate = threading.Semaphore(LLM_MAX_CONCURRENCY)

_RATE_LIMIT_MARKERS = (
    "429",
    "rate limit",
    "ratelimit",
    "resource_exhausted",
    "resource has been exhausted",
    "quota",
    "too many requests",
)


def _is_rate_limit_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


class ThrottledProvider:
    """
    Wraps any LLMProvider with a process-wide concurrency gate and
    exponential-backoff retries on rate-limit errors, so every call site
    (extraction, enrichment, evaluation) is protected without changes.
    """

    def __init__(self, provider: Any, max_retries: int = LLM_MAX_RETRIES):
        self._provider = provider
        self._max_retries = max_retries

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        options: Dict[str, Any] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        delay = 5.0
        for attempt in range(self._max_retries + 1):
            with _llm_gate:
                try:
                    return self._provider.chat(
                        model=model, messages=messages, options=options, **kwargs
                    )
                except Exception as exc:
                    if not _is_rate_limit_error(exc) or attempt == self._max_retries:
                        raise
            sleep_for = delay + random.uniform(0, delay / 2)
            logger.warning(
                f"⏳ LLM rate-limited (attempt {attempt + 1}/{self._max_retries}); "
                f"retrying in {sleep_for:.0f}s"
            )
            time.sleep(sleep_for)
            delay = min(delay * 2, 60.0)


def extract_json_from_response(response_text: str) -> str:
    """
    Extract JSON content from markdown code blocks.

    Args:
        response_text: Text that may contain JSON wrapped in markdown code blocks

    Returns:
        Text with markdown code block syntax removed
    """

    response_text = response_text.strip()
    if "<think>" in response_text:
        think_start = response_text.find("<think>")
        think_end = response_text.find("</think>")
        if think_start != -1 and think_end != -1:
            response_text = response_text[:think_start] + response_text[think_end + 8 :]

    # Remove leading ```json if present
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    # Remove trailing ``` if present
    if response_text.endswith("```"):
        response_text = response_text[:-3]
    return response_text


def initialize_llm_provider(model_name: str) -> Any:
    """
    Initialize the appropriate LLM provider based on the model name.

    Args:
        model_name: The name of the model to use

    Returns:
        An initialized LLM provider (either OllamaProvider or GeminiProvider)
    """
    # Default to Ollama provider
    provider = OllamaProvider()
    # If using Gemini and API key is available, use Gemini provider
    model_provider = MODEL_PROVIDER_MAPPING.get(model_name, ModelProvider.OLLAMA)
    if model_provider == ModelProvider.GEMINI:
        if not GEMINI_API_KEY:
            logger.warning("⚠️ Gemini API key not found. Falling back to Ollama.")
        else:
            logger.info(f"🔄 Using Google Gemini API provider with model {model_name}")
            provider = GeminiProvider(api_key=GEMINI_API_KEY)
    else:
        logger.info(f"🔄 Using Ollama provider with model {model_name}")
    return ThrottledProvider(provider)
