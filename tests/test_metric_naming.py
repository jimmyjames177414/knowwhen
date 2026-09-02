"""EAS must never be described as calibration, anywhere in this repository.

This is not pedantry about a word. "Decision calibration" is a formally defined property
from Zhao et al., NeurIPS 2021 (arXiv:2107.05719): a predictor is decision-calibrated when
its predicted and true distributions are indistinguishable to a set of downstream
decision-makers. EAS is nothing of the kind — it is a cost-sensitive multi-class scoring
rule over a substitutability structure, and picking the right action class is
classification, not confidence-vs-accuracy agreement.

Calling it calibration would overclaim (borrowing a theory we do not use) and
under-describe (hiding the one genuinely new thing here). So the word may appear only
where the repository is explaining that EAS is *not* calibration, which is what the
allow-list below encodes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

SEARCH_DIRS = ("src", "tests", "docs", "schemas", "examples", ".github")
SEARCH_SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt"}

SKIP_FILES = {
    # The prior-art gate discusses the calibration literature at length, by design.
    "NOVELTY.md",
    # This file names every phrase it forbids, so scanning it would always fail.
    "test_metric_naming.py",
}

#: How far either side of a hit to look for the disclaimer. Prose wraps, and a sentence
#: that says "EAS is not calibration" often puts those two words on different lines.
CONTEXT_LINES = 2

#: A line may mention calibration only if it also carries one of these, i.e. only in the
#: course of denying that EAS is a calibration metric or citing the literature.
DISCLAIMER_MARKERS = (
    "not calibration",
    "is not a calibration",
    "not a calibration",
    "never call it",
    "never be described as calibration",
    "rather than calibration",
    "arXiv:2107.05719",
    "2107.05719",
    "ece",
    "brier",
    "aurc",
    "calibration theory",
    "calibration literature",
    "confidence-vs-accuracy",
    "different quantity",
    "would overclaim",
    "calling it calibration",
    "calling it one",
    "naming it a calibration",
    "decision calibration",
)

_WORD = re.compile(r"calibrat", re.IGNORECASE)


def _files() -> list[Path]:
    found: list[Path] = []
    for name in SEARCH_DIRS:
        directory = REPO_ROOT / name
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix in SEARCH_SUFFIXES:
                found.append(path)
    found.extend(REPO_ROOT.glob("*.md"))
    return [p for p in found if p.name not in SKIP_FILES]


def test_the_search_actually_covers_the_repository() -> None:
    """A silent zero-file scan would make the guard below vacuously pass."""
    files = _files()
    assert len(files) > 30
    names = {p.name for p in files}
    assert "score.py" in names
    assert "README.md" in names


def _window(lines: list[str], index: int) -> str:
    """Lowercased context around a hit, with markdown emphasis stripped.

    Stripping matters: "It is **not** a calibration metric" does not contain the literal
    substring "not a calibration" until the asterisks come out.
    """
    low = max(0, index - CONTEXT_LINES)
    high = min(len(lines), index + CONTEXT_LINES + 1)
    joined = " ".join(lines[low:high]).lower()
    return re.sub(r"[*_`]+", "", joined)


def test_calibration_never_describes_the_metric() -> None:
    offenders: list[str] = []
    for path in _files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if not _WORD.search(line):
                continue
            context = _window(lines, index)
            if any(marker.lower() in context for marker in DISCLAIMER_MARKERS):
                continue
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{index + 1}: {line.strip()}")
    assert not offenders, "'calibration' used without disclaiming it:\n" + "\n".join(offenders)


#: A line may carry a banned phrase only while saying it is banned.
_BAN_MARKERS = ("banned", "turned down", "must not", "never claim", "forbidden")

BANNED_PHRASES = (
    "first ever",
    "the first tool to",
    "revolutionary",
    "solves hallucination",
    "solves agent safety",
    "the definitive benchmark",
)


@pytest.mark.parametrize("banned", BANNED_PHRASES)
def test_banned_marketing_phrases_do_not_appear(banned: str) -> None:
    offenders: list[str] = []
    for path in _files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if banned not in line.lower():
                continue
            context = _window(lines, index)
            if any(marker in context for marker in _BAN_MARKERS):
                continue
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{index + 1}")
    assert not offenders, f"banned phrase {banned!r} in {offenders}"


def test_state_of_the_art_needs_a_citation() -> None:
    """Banned unless a cited measurement supports it, so the check is for a nearby link."""
    offenders: list[str] = []
    for path in _files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if "state of the art" not in line.lower():
                continue
            context = _window(lines, index)
            if any(marker in context for marker in _BAN_MARKERS) or "arxiv" in context:
                continue
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{index + 1}")
    assert not offenders, f"'state of the art' without a citation in {offenders}"


def test_the_metric_is_named_consistently() -> None:
    """EAS is spelled out at least once in each of the places a reader arrives."""
    for name in ("README.md", "docs/scoring.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "Epistemic Action Score" in text, name
        assert "EAS" in text, name
