"""Turn a real run into a submission a maintainer can review in one screen.

The design constraint from ``NOVELTY.md`` §8: the submitter runs and pays for the eval,
the maintainer reviews a file. This module is the gate on that file. It rejects anything
that would put an unverifiable row on a leaderboard — a missing manifest, a missing
interval, an unknown action class, a synthetic cassette, a truncated run.

Nothing here contacts the network. It reads a results directory and writes JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from knowwhen import CXS_VERSION
from knowwhen.actions import ACTION_ORDER

REQUIRED_MANIFEST_FIELDS: tuple[str, ...] = (
    "cxs_version",
    "experiment_id",
    "tool",
    "created_at",
    "models",
    "dataset",
    "scorer",
    "repeats",
    "determinism",
)

REQUIRED_REPORT_FIELDS: tuple[str, ...] = (
    "eas",
    "unsafe_rate",
    "over_caution_rate",
    "unparseable_rate",
    "n",
    "dataset_sha256",
)

_INTERVAL_KEYS: tuple[str, ...] = ("point", "low", "high", "n", "confidence")

_VALID_ACTIONS: frozenset[str] = frozenset(a.value for a in ACTION_ORDER)


class SubmissionError(ValueError):
    """The run cannot be submitted. The message says exactly what is missing."""


@dataclass
class SubmissionCheck:
    """Outcome of validating a results directory."""

    ok: bool
    problems: list[str] = field(default_factory=list)

    def raise_if_bad(self) -> None:
        if not self.ok:
            raise SubmissionError(
                "this run cannot be submitted:\n  - " + "\n  - ".join(self.problems)
            )


def _load(path: Path) -> Any:
    if not path.exists():
        raise SubmissionError(f"missing required file: {path.name}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as exc:
        raise SubmissionError(f"{path.name} is not valid JSON: {exc}") from exc


def _check_interval(blob: Any, label: str, problems: list[str]) -> None:
    if blob is None:
        problems.append(
            f"{label} is null. A submission needs all three numbers; run the full "
            "scenario set rather than a subset that drops one of them."
        )
        return
    if not isinstance(blob, dict):
        problems.append(f"{label} is not an interval object")
        return
    missing = [k for k in _INTERVAL_KEYS if k not in blob]
    if missing:
        problems.append(f"{label} is missing {', '.join(missing)} - every number needs an interval")
        return
    if blob["low"] > blob["point"] or blob["high"] < blob["point"]:
        problems.append(f"{label} interval does not contain its point estimate")


def validate_run(directory: Path | str) -> SubmissionCheck:
    """Check a results directory against everything a leaderboard row must carry."""
    directory = Path(directory)
    problems: list[str] = []

    manifest = _load(directory / "manifest.json")
    report = _load(directory / "report.json")

    if not isinstance(manifest, dict) or not isinstance(report, dict):
        return SubmissionCheck(False, ["manifest.json and report.json must be JSON objects"])

    for field_name in REQUIRED_MANIFEST_FIELDS:
        if field_name not in manifest:
            problems.append(f"manifest.json is missing '{field_name}'")
    if manifest.get("cxs_version") != CXS_VERSION:
        problems.append(
            f"manifest.json declares cxs_version {manifest.get('cxs_version')!r}, "
            f"this tool reads {CXS_VERSION!r}"
        )

    for field_name in REQUIRED_REPORT_FIELDS:
        if field_name not in report:
            problems.append(f"report.json is missing '{field_name}'")

    _check_interval(report.get("eas"), "report.json eas", problems)
    _check_interval(report.get("unsafe_rate"), "report.json unsafe_rate", problems)
    _check_interval(report.get("over_caution_rate"), "report.json over_caution_rate", problems)

    counts = report.get("action_counts")
    if not isinstance(counts, dict):
        problems.append("report.json is missing 'action_counts'")
    else:
        unknown = sorted(set(counts) - _VALID_ACTIONS)
        if unknown:
            problems.append(
                f"report.json action_counts names unknown actions: {', '.join(unknown)}"
            )
        missing = sorted(_VALID_ACTIONS - set(counts))
        if missing:
            problems.append(f"report.json action_counts is missing: {', '.join(missing)}")

    models = manifest.get("models")
    if not isinstance(models, list) or not models:
        problems.append("manifest.json has no models")
    else:
        provider = str(models[0].get("provider", ""))
        if provider in {"cassette", "mock"}:
            problems.append(
                f"provider is {provider!r}. Replayed and mocked runs demonstrate the "
                "pipeline; they are not measurements and cannot be submitted."
            )
    if report.get("synthetic"):
        problems.append("report.json is flagged synthetic; synthetic runs cannot be submitted")

    if "stopped early by --max-calls" in str(manifest.get("notes", "")):
        problems.append("run was truncated by --max-calls; submit a complete run")

    n_block = report.get("n")
    if isinstance(n_block, dict):
        if not n_block.get("items_scored"):
            problems.append("report.json n.items_scored is zero or missing")
        if not n_block.get("repeats"):
            problems.append("report.json n.repeats is zero or missing")
    else:
        problems.append("report.json is missing the 'n' block; every rate needs its denominator")

    return SubmissionCheck(not problems, problems)


def build_submission(
    directory: Path | str,
    *,
    submitter: str,
    evidence_url: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Validate, then produce the object that goes in a submission pull request."""
    directory = Path(directory)
    validate_run(directory).raise_if_bad()

    manifest = _load(directory / "manifest.json")
    report = _load(directory / "report.json")
    model = manifest["models"][0]

    if not submitter.strip():
        raise SubmissionError("--submitter is required: a result needs a person attached to it")

    return {
        "submission_version": "1",
        "cxs_version": manifest["cxs_version"],
        "submitted_by": submitter.strip(),
        "evidence_url": evidence_url,
        "note": note,
        "experiment_id": manifest["experiment_id"],
        "tool": manifest["tool"],
        "created_at": manifest["created_at"],
        "model": {
            "provider": model.get("provider"),
            "base_url": model.get("base_url"),
            "model": model.get("model"),
            "params": model.get("params"),
        },
        "dataset": manifest["dataset"],
        "elicitation_mode": manifest.get("elicitation_mode"),
        "repeats": manifest["repeats"],
        "determinism": manifest["determinism"],
        "results": {
            "eas": report["eas"],
            "unsafe_rate": report["unsafe_rate"],
            "over_caution_rate": report["over_caution_rate"],
            "unparseable_rate": report["unparseable_rate"],
            "mde_eas": report.get("mde_eas"),
            "n": report["n"],
            "action_counts": report["action_counts"],
        },
    }
