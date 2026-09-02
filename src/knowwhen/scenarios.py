"""Loading, validating and hash-pinning the scenario set.

A scenario is a situation plus a **credit vector**: how much each of the six epistemic
actions is worth on that situation. There is no single gold label, because for most of
these situations more than one move is defensible and the interesting question is which
ones, and by how much. ``docs/scoring.md`` argues for the vectors; this module only
enforces that they are internally consistent.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal, cast

import yaml

from knowwhen.actions import ACTION_ORDER, Action, parse_action

ToolKind = Literal["read", "write", "simulate", "ask", "escalate"]

_TOOL_KINDS: frozenset[str] = frozenset({"read", "write", "simulate", "ask", "escalate"})

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

#: Fixed vocabulary of scenario types. Adding one is a deliberate change to the benchmark
#: and must come with scenarios, not just a string.
SCENARIO_TYPES: tuple[str, ...] = (
    "ambiguous_target",
    "missing_parameter",
    "irreversible_action",
    "stale_evidence",
    "conflicting_instructions",
    "conflicting_evidence",
    "insufficient_permission",
    "unverified_precondition",
    "blast_radius",
    "false_premise",
    "benign_readonly",
    "benign_reversible",
    "benign_specified",
    "benign_low_stakes",
)

#: Types whose scenarios are benign controls. Over-caution is measured over exactly these.
BENIGN_TYPES: frozenset[str] = frozenset(t for t in SCENARIO_TYPES if t.startswith("benign_"))

#: Tools every scenario gets for free in freeform mode, so that ASK and ESCALATE are
#: always available moves and their absence can never be mistaken for a model choosing
#: not to use them.
UNIVERSAL_TOOLS: tuple[tuple[str, ToolKind, str], ...] = (
    ("ask_requester", "ask", "Send a clarifying question back to whoever asked for this."),
    ("escalate_to_human", "escalate", "Hand the decision to an authorised human and wait."),
)


class ScenarioError(ValueError):
    """A scenario file is malformed or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class Tool:
    """A tool offered to the model in ``--mode freeform``."""

    name: str
    kind: ToolKind
    description: str


@dataclass(frozen=True, slots=True)
class Scenario:
    """One benchmark item."""

    id: str
    type: str
    title: str
    prompt: str
    credit: dict[Action, float]
    unsafe: frozenset[Action]
    rationale: str
    tools: tuple[Tool, ...]
    #: The tool that *is* the task, where performing the task does not mutate anything.
    #: On "list the buckets", calling ``list_buckets`` is ACT, not VERIFY, and without
    #: this field freeform mode could never record an ACT on a read-only control — which
    #: would silently zero the over-caution measurement in that mode.
    task_tool: str | None = None

    @property
    def benign(self) -> bool:
        """True when this is a benign control used to measure over-caution."""
        return self.type in BENIGN_TYPES

    @property
    def has_unsafe(self) -> bool:
        """True when at least one action on this item is actively harmful.

        Items where nothing is harmful are excluded from the unsafe-rate denominator;
        including them would make the rate depend on the benign/risky mix of the set
        rather than on the model.
        """
        return bool(self.unsafe)

    @property
    def best_actions(self) -> tuple[Action, ...]:
        """Every action awarded full credit."""
        return tuple(a for a in ACTION_ORDER if self.credit[a] == 1.0)

    def canonical(self) -> dict[str, Any]:
        """Serialisation used for the dataset hash. Order is fixed, floats are rounded."""
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "prompt": self.prompt,
            "credit": {a.value: round(self.credit[a], 6) for a in ACTION_ORDER},
            "unsafe": [a.value for a in ACTION_ORDER if a in self.unsafe],
            "rationale": self.rationale,
            "task_tool": self.task_tool,
            "tools": [
                {"name": t.name, "kind": t.kind, "description": t.description} for t in self.tools
            ],
        }


@dataclass(frozen=True, slots=True)
class ScenarioSet:
    """An immutable, hash-pinned collection of scenarios."""

    version: str
    scenarios: tuple[Scenario, ...]
    sha256: str

    def __len__(self) -> int:
        return len(self.scenarios)

    def __iter__(self) -> Any:
        return iter(self.scenarios)

    def by_id(self, scenario_id: str) -> Scenario:
        for s in self.scenarios:
            if s.id == scenario_id:
                return s
        raise KeyError(scenario_id)

    @property
    def benign(self) -> tuple[Scenario, ...]:
        return tuple(s for s in self.scenarios if s.benign)

    @property
    def risky(self) -> tuple[Scenario, ...]:
        return tuple(s for s in self.scenarios if not s.benign)

    def filtered(
        self,
        *,
        types: tuple[str, ...] | None = None,
        ids: tuple[str, ...] | None = None,
        limit: int | None = None,
    ) -> ScenarioSet:
        """Return a subset. The sha256 is recomputed, so a subset never claims the full pin."""
        chosen = self.scenarios
        if types is not None:
            wanted = set(types)
            chosen = tuple(s for s in chosen if s.type in wanted)
        if ids is not None:
            order = {sid: i for i, sid in enumerate(ids)}
            missing = sorted(set(ids) - {s.id for s in chosen})
            if missing:
                raise KeyError(f"unknown scenario ids: {', '.join(missing)}")
            chosen = tuple(sorted((s for s in chosen if s.id in order), key=lambda s: order[s.id]))
        if limit is not None:
            chosen = chosen[:limit]
        return ScenarioSet(version=self.version, scenarios=chosen, sha256=_hash_scenarios(chosen))


def _hash_scenarios(scenarios: tuple[Scenario, ...]) -> str:
    payload = json.dumps(
        [s.canonical() for s in scenarios], sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _load_tool_catalogue(root: Path) -> dict[str, Tool]:
    path = root / "_tools.yaml"
    if not path.exists():
        raise ScenarioError(f"missing tool catalogue: {path}")
    raw = _read_yaml(path)
    if not isinstance(raw, dict) or "tools" not in raw:
        raise ScenarioError(f"{path}: expected a mapping with a 'tools' key")
    catalogue: dict[str, Tool] = {}
    for entry in raw["tools"]:
        name = str(entry["name"])
        kind = str(entry["kind"])
        if kind not in _TOOL_KINDS:
            raise ScenarioError(f"{path}: tool {name!r} has unknown kind {kind!r}")
        if name in catalogue:
            raise ScenarioError(f"{path}: duplicate tool {name!r}")
        catalogue[name] = Tool(
            name=name, kind=cast(ToolKind, kind), description=str(entry["description"]).strip()
        )
    for name, kind, description in UNIVERSAL_TOOLS:
        catalogue.setdefault(name, Tool(name=name, kind=kind, description=description))
    return catalogue


def _parse_credit(raw: Any, where: str) -> dict[Action, float]:
    if not isinstance(raw, dict):
        raise ScenarioError(f"{where}: 'credit' must be a mapping of action -> number")
    credit: dict[Action, float] = {}
    for key, value in raw.items():
        action = parse_action(str(key))
        if action is None:
            raise ScenarioError(f"{where}: 'credit' names unknown action {key!r}")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ScenarioError(f"{where}: credit for {action} must be a number, got {value!r}")
        number = float(value)
        if not 0.0 <= number <= 1.0:
            raise ScenarioError(f"{where}: credit for {action} is {number}, must be in [0, 1]")
        credit[action] = number
    missing = [a.value for a in ACTION_ORDER if a not in credit]
    if missing:
        raise ScenarioError(f"{where}: 'credit' is missing {', '.join(missing)}")
    if not any(v == 1.0 for v in credit.values()):
        raise ScenarioError(f"{where}: no action scores 1.0, so the item has no best move")
    return credit


def _parse_scenario(raw: Any, where: str, catalogue: dict[str, Tool]) -> Scenario:
    if not isinstance(raw, dict):
        raise ScenarioError(f"{where}: scenario must be a mapping")
    try:
        scenario_id = str(raw["id"]).strip()
        scenario_type = str(raw["type"]).strip()
        title = str(raw["title"]).strip()
        prompt = str(raw["prompt"]).strip()
        rationale = str(raw["rationale"]).strip()
    except KeyError as exc:
        raise ScenarioError(f"{where}: missing required field {exc}") from exc

    if not _ID_RE.match(scenario_id):
        raise ScenarioError(f"{where}: id {scenario_id!r} must be lowercase-kebab-case")
    if scenario_type not in SCENARIO_TYPES:
        raise ScenarioError(f"{where}: unknown type {scenario_type!r}")
    if len(prompt) < 40:
        raise ScenarioError(f"{where}: prompt is too short to describe a situation")
    if len(rationale) < 20:
        raise ScenarioError(f"{where}: rationale is too short; explain the credit vector")

    credit = _parse_credit(raw.get("credit"), where)

    unsafe: set[Action] = set()
    for name in raw.get("unsafe", []) or []:
        action = parse_action(str(name))
        if action is None:
            raise ScenarioError(f"{where}: 'unsafe' names unknown action {name!r}")
        unsafe.add(action)

    # An action that is actively harmful cannot also earn credit. Without this invariant
    # a scenario author could quietly make the unsafe rate and the EAS disagree.
    for action in sorted(unsafe, key=lambda a: a.value):
        if credit[action] != 0.0:
            raise ScenarioError(
                f"{where}: {action} is marked unsafe but scores {credit[action]}; "
                "unsafe actions must score 0.0"
            )

    benign = scenario_type in BENIGN_TYPES
    if benign:
        if unsafe:
            raise ScenarioError(
                f"{where}: benign controls must have no unsafe action; "
                "if an action here is genuinely harmful the item is not a control"
            )
        if credit[Action.ACT] != 1.0:
            raise ScenarioError(
                f"{where}: on a benign control ACT must score 1.0, otherwise "
                "over-caution is not measurable"
            )
    elif credit[Action.ACT] == 1.0:
        raise ScenarioError(
            f"{where}: a risky item that awards ACT full credit is not a risky item; "
            "retag it as a benign control"
        )

    tool_names = [str(n) for n in (raw.get("tools", []) or [])]
    unknown = [n for n in tool_names if n not in catalogue]
    if unknown:
        raise ScenarioError(f"{where}: unknown tools {', '.join(sorted(unknown))}")
    tools = [catalogue[n] for n in tool_names]
    tools.extend(catalogue[name] for name, _, _ in UNIVERSAL_TOOLS if name not in tool_names)
    if not any(t.kind in {"read", "write", "simulate"} for t in tools):
        raise ScenarioError(f"{where}: needs at least one read/write/simulate tool")

    task_tool = raw.get("task_tool")
    task_tool = str(task_tool) if task_tool else None
    if task_tool is not None and task_tool not in tool_names:
        raise ScenarioError(f"{where}: task_tool {task_tool!r} is not in this scenario's tools")
    if task_tool is None and not any(t.kind in {"write", "simulate"} for t in tools):
        raise ScenarioError(
            f"{where}: every tool here is read-only, so performing the task IS a read. "
            "Set task_tool to the tool that does the job, or freeform mode can never "
            "record an ACT on this item."
        )

    return Scenario(
        id=scenario_id,
        type=scenario_type,
        title=title,
        prompt=prompt,
        credit=credit,
        unsafe=frozenset(unsafe),
        rationale=rationale,
        tools=tuple(tools),
        task_tool=task_tool,
    )


def default_scenario_root() -> Path:
    """Filesystem path of the bundled ``v1`` scenario set."""
    return Path(str(resources.files("knowwhen") / "data" / "scenarios" / "v1"))


def load_scenarios(root: Path | str | None = None, *, version: str = "v1") -> ScenarioSet:
    """Load, validate and hash-pin every scenario under ``root``.

    Raises :class:`ScenarioError` on the first problem found, with the file it came from.
    Scenarios are sorted by id so the hash does not depend on directory iteration order.
    """
    base = Path(root) if root is not None else default_scenario_root()
    if not base.is_dir():
        raise ScenarioError(f"scenario directory not found: {base}")

    catalogue = _load_tool_catalogue(base)
    scenarios: list[Scenario] = []
    seen: dict[str, str] = {}

    for path in sorted(base.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        raw = _read_yaml(path)
        if not isinstance(raw, dict) or "scenarios" not in raw:
            raise ScenarioError(f"{path}: expected a mapping with a 'scenarios' key")
        for index, entry in enumerate(raw["scenarios"]):
            where = f"{path.name}[{index}]"
            scenario = _parse_scenario(entry, where, catalogue)
            if scenario.id in seen:
                raise ScenarioError(
                    f"{where}: duplicate id {scenario.id!r}, already defined in {seen[scenario.id]}"
                )
            seen[scenario.id] = where
            scenarios.append(scenario)

    if not scenarios:
        raise ScenarioError(f"no scenarios found under {base}")

    ordered = tuple(sorted(scenarios, key=lambda s: s.id))
    return ScenarioSet(version=version, scenarios=ordered, sha256=_hash_scenarios(ordered))
