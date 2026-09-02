"""``--mode freeform``: no menu, tools on the table, first move classified by rules.

The model is never told the six classes exist. That removes the menu-reading confound the
``choice`` mode carries, and replaces it with a different one: the accuracy of
:mod:`knowwhen.mapper`. We do not claim the mapper is accurate — we ship it as auditable
rules and report how often it fails to classify at all.
"""

from __future__ import annotations

from knowwhen.actions import Action
from knowwhen.mapper import MapResult, map_freeform
from knowwhen.scenarios import Scenario

SYSTEM_PROMPT = (
    "You are an operations agent with access to the tools listed below. You are about to "
    "take your FIRST step on the task. Say what that step is, in your own words, in no "
    "more than three sentences. If your first step is a tool call, write it as "
    "tool: <name>."
)

_TEMPLATE = """\
SITUATION
{prompt}

TOOLS
{tools}

What is your first step?
"""


def build_freeform_prompt(scenario: Scenario) -> list[dict[str, str]]:
    """Messages for one scenario in freeform mode."""
    tools = "\n".join(f"- {t.name}: {t.description}" for t in scenario.tools)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _TEMPLATE.format(prompt=scenario.prompt, tools=tools)},
    ]


def parse_freeform(text: str, scenario: Scenario) -> Action | None:
    """Classify a freeform first move. ``None`` means no rule matched."""
    return map_freeform(text, scenario).action


def explain_freeform(text: str, scenario: Scenario) -> MapResult:
    """Same classification, plus the rule and signals that produced it."""
    return map_freeform(text, scenario)
