"""The ONLY module in this project that touches the Gemini SDK.

Every agent calls `generate_structured(...)` and gets back a validated Pydantic
object. Keeping the SDK surface in one file means an upstream API change is a
5-line edit here, not a hunt through every agent.

Verified against google-genai 2.22.0 on 2026-09-05:
  client.models.generate_content(model=..., contents=..., config=...)
  types.GenerateContentConfig(response_mime_type=..., response_schema=...)
  response.parsed -> instance of the schema
"""

from __future__ import annotations

import logging
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from ai.config import settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


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

    try:
        response = get_client().models.generate_content(
            model=model or settings.gemini_model,
            contents=prompt,
            config=config,
        )
    except Exception as exc:  # SDK raises a family of errors; treat all as one failure
        raise LLMError(f"Gemini call failed: {exc}") from exc

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
    try:
        response = get_client().models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature, system_instruction=system_instruction
            ),
        )
    except Exception as exc:
        raise LLMError(f"Gemini call failed: {exc}") from exc
    return (response.text or "").strip()
