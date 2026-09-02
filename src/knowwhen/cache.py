"""Content-addressed response cache.

Keyed by ``sha256(provider|model|params|messages)`` per SHARED-FOUNDATION D5, so a re-run
with the same inputs costs nothing and a changed prompt template correctly misses.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from knowwhen.providers.base import Completion


def default_cache_dir() -> Path:
    """``$XDG_CACHE_HOME/knowwhen`` if set, else ``~/.cache/knowwhen``."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "knowwhen"


@dataclass
class ResponseCache:
    """On-disk cache. ``enabled=False`` turns every method into a no-op."""

    directory: Path
    enabled: bool = True
    hits: int = 0
    misses: int = 0

    @classmethod
    def create(cls, directory: Path | str | None = None, *, enabled: bool = True) -> ResponseCache:
        return cls(directory=Path(directory) if directory else default_cache_dir(), enabled=enabled)

    def _path(self, key: str) -> Path:
        # Two-character shard so a 120-scenario run does not put thousands of files in
        # one directory.
        return self.directory / key[:2] / f"{key}.json"

    def get(self, key: str) -> Completion | None:
        if not self.enabled:
            return None
        path = self._path(key)
        if not path.exists():
            self.misses += 1
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                blob = json.load(fh)
        except (OSError, ValueError):
            # A corrupt cache entry is a miss, not a crash. It gets overwritten on write.
            self.misses += 1
            return None
        self.hits += 1
        return Completion(
            text=str(blob.get("text", "")),
            prompt_tokens=blob.get("prompt_tokens"),
            completion_tokens=blob.get("completion_tokens"),
            latency_ms=blob.get("latency_ms"),
            error=blob.get("error"),
        )

    def put(self, key: str, completion: Completion) -> None:
        if not self.enabled or completion.error:
            # Errors are never cached: a transient 503 must not become permanent.
            return
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(
                {
                    "text": completion.text,
                    "prompt_tokens": completion.prompt_tokens,
                    "completion_tokens": completion.completion_tokens,
                    "latency_ms": completion.latency_ms,
                },
                fh,
            )
        tmp.replace(path)

    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses}
