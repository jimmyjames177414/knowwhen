"""Replay provider: reads responses from a JSON file, makes no network calls.

A cassette is keyed by ``(scenario_id, mode)`` rather than by prompt hash. That is a
deliberate trade: a hash-keyed cassette breaks the moment anyone edits a prompt template,
and it cannot be written or reviewed by hand. This one can.

Every cassette carries a ``_meta`` block declaring whether its responses were **recorded**
from a real model or **synthetic**, and a provider that finds neither refuses to load.
That rule exists so a synthetic fixture can never be mistaken for a measurement.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowwhen.providers.base import Completion, Message, ModelDescriptor, Params

_VALID_SOURCES = frozenset({"recorded", "synthetic"})


class CassetteError(ValueError):
    """The cassette is missing, malformed, or does not declare its provenance."""


class CassetteProvider:
    """Serves pre-written responses for one elicitation mode."""

    name = "cassette"

    def __init__(self, path: Path | str, *, mode: str, params: Params | None = None) -> None:
        self.path = Path(path)
        self.mode = mode
        self.params = params or Params()
        self.base_url: str | None = None

        if not self.path.exists():
            raise CassetteError(f"cassette not found: {self.path}")
        with self.path.open("r", encoding="utf-8") as fh:
            blob: Any = json.load(fh)
        if not isinstance(blob, dict):
            raise CassetteError(f"{self.path}: expected a JSON object")

        meta = blob.get("_meta")
        if not isinstance(meta, dict):
            raise CassetteError(f"{self.path}: missing '_meta' block")
        source = meta.get("source")
        if source not in _VALID_SOURCES:
            raise CassetteError(
                f"{self.path}: _meta.source must be one of {sorted(_VALID_SOURCES)}, "
                f"got {source!r}. A cassette that will not say where its responses came "
                "from cannot be replayed."
            )
        responses = blob.get("responses")
        if not isinstance(responses, dict):
            raise CassetteError(f"{self.path}: missing 'responses' object")

        self.meta: dict[str, Any] = meta
        self.source: str = str(source)
        self.model: str = str(meta.get("model", "cassette"))
        self._responses: dict[str, dict[str, str]] = {
            str(k): {str(mk): str(mv) for mk, mv in v.items()} for k, v in responses.items()
        }
        self._current: str | None = None

    @property
    def is_synthetic(self) -> bool:
        return self.source == "synthetic"

    def descriptor(self) -> ModelDescriptor:
        return ModelDescriptor(
            provider=self.name,
            model=self.model,
            base_url=None,
            params=self.params,
            observed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    def covers(self, scenario_id: str) -> bool:
        return self.mode in self._responses.get(scenario_id, {})

    def set_scenario(self, scenario_id: str) -> None:
        """Point the provider at the next scenario. The runner calls this before
        ``complete``, because a cassette cannot recover the scenario from the prompt."""
        self._current = scenario_id

    def complete(self, messages: list[Message]) -> Completion:
        if self._current is None:
            raise CassetteError("set_scenario() must be called before complete()")
        entry = self._responses.get(self._current)
        if entry is None or self.mode not in entry:
            return Completion(
                text="",
                error=f"cassette has no {self.mode} response for scenario {self._current!r}",
            )
        return Completion(text=entry[self.mode], prompt_tokens=0, completion_tokens=0, latency_ms=0)
