"""Shared fixtures.

Nothing here touches the network. The whole suite runs with no API key, which is the
point of SHARED-FOUNDATION D3.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from knowwhen.actions import ACTION_ORDER, Action
from knowwhen.scenarios import Scenario, ScenarioSet, Tool, _hash_scenarios, load_scenarios

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_CASSETTE = REPO_ROOT / "examples" / "cassettes" / "demo-synthetic-v1.json"
DEMO_POLICY = REPO_ROOT / "examples" / "demo-policy.yaml"
SCHEMA_DIR = REPO_ROOT / "schemas"

READ_TOOL = Tool(name="list_databases", kind="read", description="List databases.")
WRITE_TOOL = Tool(name="drop_database", kind="write", description="Delete a database.")
SIM_TOOL = Tool(name="dry_run_sql", kind="simulate", description="Report affected rows.")
ASK_TOOL = Tool(name="ask_requester", kind="ask", description="Ask the requester.")
ESCALATE_TOOL = Tool(name="escalate_to_human", kind="escalate", description="Hand it over.")

ALL_TOOLS = (READ_TOOL, WRITE_TOOL, SIM_TOOL, ASK_TOOL, ESCALATE_TOOL)


def make_scenario(
    scenario_id: str,
    *,
    scenario_type: str = "ambiguous_target",
    credit: dict[Action, float] | None = None,
    unsafe: tuple[Action, ...] = (),
    tools: tuple[Tool, ...] = ALL_TOOLS,
    task_tool: str | None = None,
) -> Scenario:
    """Build a Scenario directly, bypassing YAML. For scoring tests only."""
    if credit is None:
        credit = dict.fromkeys(ACTION_ORDER, 0.0)
        credit[Action.VERIFY] = 1.0
    return Scenario(
        id=scenario_id,
        type=scenario_type,
        title=scenario_id,
        prompt=f"A situation requiring a decision about {scenario_id}, described at length.",
        credit=credit,
        unsafe=frozenset(unsafe),
        rationale="Constructed for a test; the credit vector is chosen, not argued.",
        tools=tools,
        task_tool=task_tool,
    )


def make_set(*scenarios: Scenario) -> ScenarioSet:
    ordered = tuple(sorted(scenarios, key=lambda s: s.id))
    return ScenarioSet(version="test", scenarios=ordered, sha256=_hash_scenarios(ordered))


@pytest.fixture(scope="session")
def shipped() -> ScenarioSet:
    """The real bundled v1 scenario set."""
    return load_scenarios()
