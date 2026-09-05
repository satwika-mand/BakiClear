"""Single entry point for getting a ContextProvider. Everything else in `ai/`
should call `get_context_provider()` — never construct MockContextProvider
directly — so switching CONTEXT_SOURCE in .env is the entire Phase 5 migration."""

from functools import lru_cache

from ai.config import settings
from ai.orchestration.context_provider import ContextProvider
from ai.orchestration.mock_provider import MockContextProvider


@lru_cache
def get_context_provider() -> ContextProvider:
    if settings.context_source == "mock":
        return MockContextProvider()
    raise NotImplementedError(
        "CONTEXT_SOURCE=api is wired up in Phase 5, once Person 1's endpoints are live."
    )


__all__ = ["ContextProvider", "get_context_provider"]
