"""knowwhen — a benchmark for whether an agent should have started.

Public surface is deliberately small. Everything else is an implementation detail and may
change without a major version bump.
"""

from __future__ import annotations

from knowwhen.actions import ACTION_ORDER, DEFINITIONS, Action, parse_action
from knowwhen.scenarios import Scenario, ScenarioSet, Tool, load_scenarios
from knowwhen.score import EASReport, Judgement, score_run

__version__ = "0.1.0"

#: The CXS interchange format version this tool reads and writes.
CXS_VERSION = "0.1"

#: The scorer identifier written into every ``Outcome`` record.
SCORER_ID = "eas:v1"

__all__ = [
    "ACTION_ORDER",
    "CXS_VERSION",
    "DEFINITIONS",
    "SCORER_ID",
    "Action",
    "EASReport",
    "Judgement",
    "Scenario",
    "ScenarioSet",
    "Tool",
    "__version__",
    "load_scenarios",
    "parse_action",
    "score_run",
]
