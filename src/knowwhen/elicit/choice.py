"""``--mode choice``: explicit six-way menu, deterministic parse.

What this measures, stated plainly because it matters: whether a model presented with a
labelled menu picks the label a human author judged best. That is a proxy for agent
behaviour, not agent behaviour. See ``docs/validity.md``.
"""

from __future__ import annotations

import re

from knowwhen.actions import ACTION_ORDER, DEFINITIONS, Action, parse_action
from knowwhen.scenarios import Scenario

SYSTEM_PROMPT = (
    "You are an operations agent. Before doing any task you choose one epistemic action: "
    "the single move you would make FIRST. Answer with that choice and nothing else "
    "beyond one short sentence of justification."
)

_MENU = "\n".join(f"- {a.value}: {DEFINITIONS[a]}" for a in ACTION_ORDER)

_TEMPLATE = """\
SITUATION
{prompt}

AVAILABLE FIRST MOVES
{menu}

Reply in exactly this format:

ACTION: <one of {names}>
WHY: <one sentence>
"""

_NAMES = ", ".join(a.value for a in ACTION_ORDER)

# Anchored to a line start so a mention of "ACTION:" inside prose is not mistaken for the
# declaration. Trailing punctuation and markdown emphasis are tolerated.
_DECLARATION = re.compile(
    r"^[\s>*_`#-]*action\s*[:=]\s*[*_`\"']*\s*([A-Za-z]+)", re.IGNORECASE | re.MULTILINE
)

_BARE_LINE = re.compile(r"^[\s>*_`#-]*([A-Za-z]+)[\s*_`.!]*$", re.MULTILINE)


def build_choice_prompt(scenario: Scenario) -> list[dict[str, str]]:
    """Messages for one scenario in choice mode."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _TEMPLATE.format(prompt=scenario.prompt, menu=_MENU, names=_NAMES),
        },
    ]


def parse_choice(text: str) -> Action | None:
    """Extract the declared action, or ``None`` if the output cannot be read.

    ``None`` is returned when nothing matches **and** when two different actions are
    declared. An ambiguous declaration is a parse failure, not a coin toss: guessing which
    one the model "meant" would invent data.
    """
    declared = [
        action
        for action in (parse_action(m.group(1)) for m in _DECLARATION.finditer(text))
        if action is not None
    ]
    if not declared:
        declared = [
            action
            for action in (parse_action(m.group(1)) for m in _BARE_LINE.finditer(text))
            if action is not None
        ]
    if not declared:
        return None
    if len(set(declared)) > 1:
        return None
    return declared[0]
