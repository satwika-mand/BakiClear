"""The ONLY module in this project that touches the Gemini SDK.

Every agent calls `generate_structured(...)` and gets back a validated Pydantic
object. Keeping the SDK surface in one file means an upstream API change is a
5-line edit here, not a hunt through every agent.

Verified against google-genai 2.22.0 on 2026-09-05:
  client.models.generate_content(model=..., contents=..., config=...)
  types.GenerateContentConfig(response_mime_type=..., response_schema=...)
  response.parsed -> instance of the schema

Resilience: gemini-3.5-flash had a live multi-minute 503 outage window during
development while gemini-3.5-flash-lite stayed up. _generate_content_resilient
retries the primary model once, then falls back to GEMINI_FALLBACK_MODEL — a
transient outage on stage should degrade quality, not kill the demo.
"""

from __future__ import annotations

import logging
import time
from typing import TypeVar

from google import genai
from google.genai import types
from google.genai.errors import ServerError
from pydantic import BaseModel

from ai.config import settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_RETRY_BACKOFF_SECONDS = 2.0


class LLMError(RuntimeError):
    """Raised when Gemini fails or returns something we cannot validate."""


_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not set. Add it to .env")
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _generate_content_resilient(
    *, model: str, contents: str, config: types.GenerateContentConfig
) -> types.GenerateContentResponse:
    """Try the requested model, retry once on transient server overload, then
    fall back to the configured fallback model. Client errors (bad request,
    auth, invalid schema) are not retried — those are our bugs, not Gemini's."""
    client = get_client()
    attempts = [model, model, settings.gemini_fallback_model]

    last_exc: Exception | None = None
    for i, attempt_model in enumerate(attempts):
        try:
            return client.models.generate_content(
                model=attempt_model, contents=contents, config=config
            )
        except ServerError as exc:
            last_exc = exc
            is_last = i == len(attempts) - 1
            log.warning(
                "Gemini %s returned a server error (attempt %d/%d): %s",
                attempt_model,
                i + 1,
                len(attempts),
                exc,
            )
            if not is_last:
                time.sleep(_RETRY_BACKOFF_SECONDS)
        except Exception as exc:  # non-transient: don't retry
            raise LLMError(f"Gemini call failed: {exc}") from exc

    raise LLMError(f"Gemini call failed after retries and fallback: {last_exc}") from last_exc


def generate_structured(
    prompt: str,
    schema: type[T],
    *,
    system_instruction: str | None = None,
    temperature: float = 0.2,
    model: str | None = None,
) -> T:
    """Ask Gemini for JSON conforming to `schema` and return a validated instance.

    Low temperature by default: these are financial decisions, not creative writing.
    """
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=temperature,
        system_instruction=system_instruction,
    )
    response = _generate_content_resilient(
        model=model or settings.gemini_model, contents=prompt, config=config
    )

    parsed = response.parsed
    if not isinstance(parsed, schema):
        # Happens on refusal / truncation / safety block.
        raise LLMError(
            f"Gemini did not return valid {schema.__name__}. Raw: {response.text!r:.300}"
        )
    return parsed


def generate_text(
    prompt: str, *, system_instruction: str | None = None, temperature: float = 0.4
) -> str:
    """Free-text generation. Used for customer-facing message drafting only."""
    config = types.GenerateContentConfig(
        temperature=temperature, system_instruction=system_instruction
    )
    response = _generate_content_resilient(
        model=settings.gemini_model, contents=prompt, config=config
    )
    return (response.text or "").strip()
