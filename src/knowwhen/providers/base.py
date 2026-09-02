"""Provider interface and the shared value types.

One adapter shape covers every backend we support. Provider selection is a URL and an
environment variable, never a code change.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

Message = dict[str, str]


@dataclass(frozen=True, slots=True)
class Params:
    """Sampling parameters, recorded verbatim into the run manifest."""

    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 512
    seed: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "seed": self.seed,
        }


@dataclass(frozen=True, slots=True)
class Completion:
    """One model response."""

    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    """CXS ``ModelDescriptor`` — what was asked, precisely enough to re-run."""

    provider: str
    model: str
    base_url: str | None
    params: Params
    observed_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "params": self.params.as_dict(),
            "observed_at": self.observed_at,
        }


@runtime_checkable
class Provider(Protocol):
    """Anything that can turn messages into text."""

    name: str
    model: str
    base_url: str | None
    params: Params

    def complete(self, messages: list[Message]) -> Completion:
        """Return one completion. Must not raise for model-side errors: put the message
        in ``Completion.error`` so the trial is recorded rather than lost."""
        ...


def prompt_sha256(messages: list[Message]) -> str:
    """Stable hash of a message list. Used for CXS ``Trial.prompt_sha256``."""
    payload = json.dumps(messages, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_key(provider: str, model: str, params: Params, messages: list[Message]) -> str:
    """Content-addressed cache key, per SHARED-FOUNDATION D5."""
    payload = json.dumps(
        {
            "provider": provider,
            "model": model,
            "params": params.as_dict(),
            "messages": messages,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    """Very rough token estimate for ``--dry-run``.

    Four characters per token. This is a budgeting aid, not a measurement, and the CLI
    labels it as an estimate wherever it prints one.
    """
    return max(1, len(text) // 4)
