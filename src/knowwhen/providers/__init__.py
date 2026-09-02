"""Provider adapters. OpenAI-compatible HTTP is the base case; mock and cassette are
offline."""

from __future__ import annotations

from knowwhen.providers.base import (
    Completion,
    Message,
    ModelDescriptor,
    Params,
    Provider,
    cache_key,
    estimate_tokens,
    prompt_sha256,
)
from knowwhen.providers.cassette import CassetteError, CassetteProvider
from knowwhen.providers.mock import MockProvider
from knowwhen.providers.openai_compat import OpenAICompatProvider

PROVIDER_NAMES: tuple[str, ...] = ("openai-compatible", "mock", "cassette")

__all__ = [
    "PROVIDER_NAMES",
    "CassetteError",
    "CassetteProvider",
    "Completion",
    "Message",
    "MockProvider",
    "ModelDescriptor",
    "OpenAICompatProvider",
    "Params",
    "Provider",
    "cache_key",
    "estimate_tokens",
    "prompt_sha256",
]
