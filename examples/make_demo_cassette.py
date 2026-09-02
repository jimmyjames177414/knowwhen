#!/usr/bin/env python3
"""Generate the synthetic demo cassette from ``demo-policy.yaml``.

    python examples/make_demo_cassette.py

Why a generator instead of 240 hand-written fake model responses: hand-writing prose that
looks like a model wrote it, and then replaying it, produces a fixture whose provenance is
a matter of trust. A policy file plus a mechanical renderer is auditable — you can read
which action each item expresses and check the renderer in fifty lines.

Everything this produces is labelled ``source: synthetic`` in the cassette's ``_meta``
block, and ``CassetteProvider`` refuses to load a cassette that does not declare its
provenance. ``knowwhen submit`` refuses to submit a run that used one.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from knowwhen.actions import Action, parse_action
from knowwhen.scenarios import Scenario, load_scenarios

HERE = Path(__file__).resolve().parent
POLICY_PATH = HERE / "demo-policy.yaml"
OUT_PATH = HERE / "cassettes" / "demo-synthetic-v1.json"

_WHY: dict[Action, str] = {
    Action.ACT: "the request is clear enough to carry out as asked",
    Action.ASK: "a value only the requester knows is missing",
    Action.VERIFY: "a fact I am relying on is checkable before anything changes",
    Action.SIMULATE: "a rehearsal shows the effect without causing it",
    Action.ESCALATE: "this needs authority I do not have",
    Action.ABSTAIN: "this should not proceed at all",
}

UNPARSEABLE_CHOICE = "Tricky one. It depends what they meant, really."
UNPARSEABLE_FREEFORM = "Hmm."


def _first_tool(scenario: Scenario, kinds: tuple[str, ...]) -> str | None:
    for tool in scenario.tools:
        if tool.kind in kinds:
            return tool.name
    return None


def render_choice(action: Action | None) -> str:
    if action is None:
        return UNPARSEABLE_CHOICE
    return f"ACTION: {action.value}\nWHY: {_WHY[action]}."


def render_freeform(scenario: Scenario, action: Action | None) -> str:
    """Write a first move that expresses ``action``, using this scenario's real tools.

    Using the actual tool names matters: it means the demo exercises the mapper's tool
    detection rather than only its prose patterns.
    """
    if action is None:
        return UNPARSEABLE_FREEFORM

    if action is Action.ACT:
        name = scenario.task_tool or _first_tool(scenario, ("write",))
        if name:
            return f"tool: {name}\nDoing it now, the request is specific enough."
        return "I'll go ahead and do it now."

    if action is Action.VERIFY:
        name = _first_tool(scenario, ("read",))
        if name and name != scenario.task_tool:
            return f"tool: {name}\nChecking the current state before I touch anything."
        return "Let me check the current state before I touch anything."

    if action is Action.SIMULATE:
        name = _first_tool(scenario, ("simulate",))
        if name:
            return f"tool: {name}\nRehearsing it first so I can see the effect."
        return "I'll do a dry-run first to preview the effect before anything real happens."

    if action is Action.ASK:
        return "Before I proceed, could you clarify which one you mean?"

    if action is Action.ESCALATE:
        return "I'm going to escalate this: it needs sign-off from whoever owns the decision."

    return "I won't do this."


def main() -> int:
    with POLICY_PATH.open("r", encoding="utf-8") as fh:
        policy_file = yaml.safe_load(fh)
    policy: dict[str, dict[str, str]] = policy_file["policy"]
    model = str(policy_file.get("model", "demo-synthetic-v1"))

    scenario_set = load_scenarios()
    known = {s.id for s in scenario_set.scenarios}
    missing = sorted(known - set(policy))
    extra = sorted(set(policy) - known)
    if missing:
        raise SystemExit(
            f"policy is missing {len(missing)} scenarios: {', '.join(missing[:5])} ..."
        )
    if extra:
        raise SystemExit(f"policy names unknown scenarios: {', '.join(extra)}")

    responses: dict[str, dict[str, str]] = {}
    divergent = 0
    for scenario in scenario_set.scenarios:
        entry = policy[scenario.id]
        choice_name = str(entry["choice"])
        freeform_name = str(entry.get("freeform", choice_name))
        if freeform_name != choice_name:
            divergent += 1
        choice_action = None if choice_name == "UNPARSEABLE" else parse_action(choice_name)
        freeform_action = None if freeform_name == "UNPARSEABLE" else parse_action(freeform_name)
        if choice_name != "UNPARSEABLE" and choice_action is None:
            raise SystemExit(f"{scenario.id}: unknown action {choice_name!r}")
        if freeform_name != "UNPARSEABLE" and freeform_action is None:
            raise SystemExit(f"{scenario.id}: unknown action {freeform_name!r}")
        responses[scenario.id] = {
            "choice": render_choice(choice_action),
            "freeform": render_freeform(scenario, freeform_action),
        }

    cassette = {
        "_meta": {
            "source": "synthetic",
            "model": model,
            "generated_by": "examples/make_demo_cassette.py",
            "generated_from": "examples/demo-policy.yaml",
            "dataset_sha256": scenario_set.sha256,
            "n_scenarios": len(scenario_set),
            "deliberate_mode_divergences": divergent,
            "warning": (
                "SYNTHETIC. No model produced these responses. They were rendered from a "
                "hand-written policy to exercise the pipeline offline. This cassette "
                "measures nothing about any model and cannot be submitted."
            ),
        },
        "responses": responses,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(cassette, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    print(f"wrote {OUT_PATH} ({len(responses)} scenarios, {divergent} deliberate divergences)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
