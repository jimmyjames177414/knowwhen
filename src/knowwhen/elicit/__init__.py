"""Two ways of asking the model what it would do first.

``choice`` shows an explicit six-way menu and parses the declared action. It is cheap,
deterministic and comparable, and it measures a **proxy**: behaviour under a menu, not
behaviour in an agent loop.

``freeform`` hands the model tools and a situation, asks for its first move in its own
words, and classifies that move with :mod:`knowwhen.mapper`. Higher validity, noisier,
and the mapper is a source of error the ``choice`` mode does not have.

Both are reported. Agreement between them is itself a result — see ``docs/validity.md``.
"""

from __future__ import annotations

from typing import Literal

from knowwhen.elicit.choice import build_choice_prompt, parse_choice
from knowwhen.elicit.freeform import build_freeform_prompt, parse_freeform

Mode = Literal["choice", "freeform"]

MODES: tuple[Mode, ...] = ("choice", "freeform")

__all__ = [
    "MODES",
    "Mode",
    "build_choice_prompt",
    "build_freeform_prompt",
    "parse_choice",
    "parse_freeform",
]
