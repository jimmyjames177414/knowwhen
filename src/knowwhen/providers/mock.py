"""Deterministic, offline provider. No network, no key, no surprises.

Used by the test suite and by anyone who wants to exercise the pipeline before spending
money. Its outputs are **synthetic** and must never be presented as a measurement of any
model: it is a stand-in that emits well-formed text, not a thing with judgement.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from knowwhen.actions import ACTION_ORDER, Action
from knowwhen.providers.base import Completion, Message, ModelDescriptor, Params

_CHOICE_TEMPLATE = "ACTION: {action}\nWHY: synthetic mock response, no judgement involved."

_FREEFORM_TEMPLATE: dict[Action, str] = {
    Action.ACT: "I'll run the change now.",
    Action.ASK: "Before I proceed, could you clarify which one you mean?",
    Action.VERIFY: "Let me check the current state first.",
    Action.SIMULATE: "I'll do a dry-run first to preview the effect.",
    Action.ESCALATE: "I'll escalate this to the owner for sign-off.",
    Action.ABSTAIN: "I won't do this.",
}


class MockProvider:
    """Picks an action from a hash of the prompt, or from a fixed policy.

    ``policy`` pins every response to one action, which is what most tests want.
    ``unparseable_every`` makes every *n*th call emit text no parser can read, so the
    unparseable path is exercised rather than assumed.
    """

    name = "mock"

    def __init__(
        self,
        *,
        model: str = "mock-synthetic-v1",
        params: Params | None = None,
        policy: Action | None = None,
        unparseable_every: int | None = None,
        freeform: bool = False,
    ) -> None:
        self.model = model
        self.base_url: str | None = None
        self.params = params or Params()
        self.policy = policy
        self.unparseable_every = unparseable_every
        self.freeform = freeform
        self._calls = 0

    def descriptor(self) -> ModelDescriptor:
        return ModelDescriptor(
            provider=self.name,
            model=self.model,
            base_url=None,
            params=self.params,
            observed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    def complete(self, messages: list[Message]) -> Completion:
        self._calls += 1
        if self.unparseable_every and self._calls % self.unparseable_every == 0:
            return Completion(text="Hmm. Tricky one.", prompt_tokens=0, completion_tokens=0)

        if self.policy is not None:
            action = self.policy
        else:
            blob = "".join(m.get("content", "") for m in messages).encode("utf-8")
            digest = hashlib.sha256(blob).digest()
            action = ACTION_ORDER[digest[0] % len(ACTION_ORDER)]

        text = (
            _FREEFORM_TEMPLATE[action]
            if self.freeform
            else _CHOICE_TEMPLATE.format(action=action.value)
        )
        return Completion(text=text, prompt_tokens=0, completion_tokens=0, latency_ms=0)
