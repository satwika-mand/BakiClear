"""The ONLY module in this project that touches the Gemini SDK.

Every agent calls `generate_structured(...)` and gets back a validated Pydantic
object. Keeping the SDK surface in one file means an upstream API change is a
5-line edit here, not a hunt through every agent.

Verified against google-genai 2.22.0 on 2026-09-05:
  client.models.generate_content(model=..., contents=..., config=...)
  types.GenerateContentConfig(response_mime_type=..., response_schema=...)
  response.parsed -> instance of the schema

Resilience: two distinct failure modes observed live during development.
  - gemini-3.5-flash had a multi-minute 503 (ServerError) outage window while
    gemini-3.5-flash-lite stayed up -> worth one same-model retry, then fall
    back, since a 503 is transient.
  - The free tier caps gemini-3.5-flash at 20 requests/day; once exhausted,
    Gemini returns 429 RESOURCE_EXHAUSTED (a ClientError). Retrying the SAME
    model does nothing — the quota won't reset in seconds — so this goes
    straight to the fallback model, which has its own separate quota bucket.
Any other ClientError (bad request, invalid schema, auth) is a real bug on
our side and is raised immediately — retrying or falling back would just
burn the fallback model's quota on a request that will never succeed.
"""

from __future__ import annotations

import logging
import time
from typing import TypeVar

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError
from pydantic import BaseModel

from ai.config import settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_RETRY_BACKOFF_SECONDS = 2.0
_QUOTA_EXCEEDED_CODE = 429


def _is_quota_exceeded(exc: Exception) -> bool:
    return isinstance(exc, ClientError) and getattr(exc, "code", None) == _QUOTA_EXCEEDED_CODE


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
    client = get_client()
    fallback = settings.gemini_fallback_model

    def _call(attempt_model: str) -> types.GenerateContentResponse:
        return client.models.generate_content(model=attempt_model, contents=contents, config=config)

    # 1. Primary model, with one same-model retry on transient 503 overload.
    for attempt in range(2):
        try:
            return _call(model)
        except ServerError as exc:
            log.warning("Gemini %s server error (attempt %d/2): %s", model, attempt + 1, exc)
            if attempt == 0:
                time.sleep(_RETRY_BACKOFF_SECONDS)
        except ClientError as exc:
            if not _is_quota_exceeded(exc):
                raise LLMError(f"Gemini call failed: {exc}") from exc
            log.warning("Gemini %s quota exceeded, falling back to %s: %s", model, fallback, exc)
            break  # no point retrying the same model on quota exhaustion
        except Exception as exc:
            raise LLMError(f"Gemini call failed: {exc}") from exc

    # 2. Fallback model, once — either the primary kept 503ing or hit its quota.
    try:
        return _call(fallback)
    except (ServerError, ClientError) as exc:
        raise LLMError(f"Gemini call failed on both {model} and fallback {fallback}: {exc}") from exc
    except Exception as exc:
        raise LLMError(f"Gemini call failed: {exc}") from exc


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
