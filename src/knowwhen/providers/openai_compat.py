"""The primary adapter: any OpenAI-compatible ``/v1/chat/completions`` endpoint.

One adapter covers Ollama, vLLM, LM Studio, llama.cpp server, OpenRouter, Together, Groq,
DeepSeek and OpenAI itself. A contributor with Ollama and no credit card can run
everything in this repo.

The API key is read from an environment variable name, never taken as a command-line
argument, so it cannot end up in a shell history or a CI log.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from knowwhen.providers.base import Completion, Message, ModelDescriptor, Params

DEFAULT_TIMEOUT = 120.0


class OpenAICompatProvider:
    """POSTs to ``{base_url}/chat/completions``."""

    name = "openai-compatible"

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key_env: str = "KNOWWHEN_API_KEY",
        params: Params | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.params = params or Params()
        self.timeout = timeout
        # Many local servers need no key at all, so a missing variable is not an error.
        self._api_key = os.environ.get(api_key_env, "")
        self._client = client or httpx.Client(timeout=timeout)

    def descriptor(self) -> ModelDescriptor:
        return ModelDescriptor(
            provider=self.name,
            model=self.model,
            base_url=self.base_url,
            params=self.params,
            observed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    def complete(self, messages: list[Message]) -> Completion:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.params.temperature,
            "top_p": self.params.top_p,
            "max_tokens": self.params.max_tokens,
        }
        if self.params.seed is not None:
            payload["seed"] = self.params.seed

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        started = time.monotonic()
        try:
            response = self._client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
            response.raise_for_status()
            body: Any = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # A transport or decode failure is a recorded trial with an error, not a
            # crashed run: a resumable run must be able to continue past one bad call.
            return Completion(
                text="",
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=int((time.monotonic() - started) * 1000),
            )

        latency_ms = int((time.monotonic() - started) * 1000)
        try:
            text = str(body["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            return Completion(
                text="",
                error=f"unexpected response shape: {type(exc).__name__}: {exc}",
                latency_ms=latency_ms,
            )

        usage = body.get("usage") or {}
        return Completion(
            text=text,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=latency_ms,
        )

    def close(self) -> None:
        self._client.close()
