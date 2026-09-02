"""The submission gate.

A leaderboard row that cannot be checked is worse than an empty leaderboard. Everything
this module rejects is something that would put an unverifiable number in front of a
reader: a missing manifest, a number without an interval, an unknown action class, a
replayed cassette, a truncated run, a result with nobody's name on it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from knowwhen.submit import SubmissionError, build_submission, validate_run


def _interval(point: float = 0.5) -> dict[str, Any]:
    return {"point": point, "low": point - 0.1, "high": point + 0.1, "n": 90, "confidence": 0.95}


def _manifest(**overrides: Any) -> dict[str, Any]:
    blob: dict[str, Any] = {
        "cxs_version": "0.1",
        "experiment_id": "01ABC",
        "tool": {"name": "knowwhen", "version": "0.1.0"},
        "created_at": "2026-09-02T00:00:00Z",
        "models": [
            {
                "provider": "openai-compatible",
                "base_url": "http://localhost:11434/v1",
                "model": "qwen3:8b",
                "params": {"temperature": 0.0},
            }
        ],
        "dataset": {"name": "knowwhen-scenarios-v1", "sha256": "a" * 64, "n_items": 120},
        "scorer": "eas:v1",
        "repeats": 3,
        "determinism": "stochastic",
        "elicitation_mode": "choice",
        "notes": "",
    }
    blob.update(overrides)
    return blob


def _report(**overrides: Any) -> dict[str, Any]:
    blob: dict[str, Any] = {
        "eas": _interval(0.7),
        "unsafe_rate": _interval(0.1),
        "over_caution_rate": _interval(0.2),
        "unparseable_rate": 0.01,
        "mde_eas": 0.1,
        "n": {"items_scored": 118, "repeats": 3, "trials": 354},
        "action_counts": {
            "ACT": 1,
            "ASK": 2,
            "VERIFY": 3,
            "SIMULATE": 4,
            "ESCALATE": 5,
            "ABSTAIN": 6,
        },
        "dataset_sha256": "a" * 64,
        "synthetic": False,
    }
    blob.update(overrides)
    return blob


def _write(tmp_path: Path, manifest: dict[str, Any], report: dict[str, Any]) -> Path:
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    return tmp_path


def test_a_complete_run_passes(tmp_path: Path) -> None:
    _write(tmp_path, _manifest(), _report())
    assert validate_run(tmp_path).ok


def test_a_valid_run_produces_a_submission(tmp_path: Path) -> None:
    _write(tmp_path, _manifest(), _report())
    submission = build_submission(tmp_path, submitter="someone", evidence_url="https://example.org")
    assert submission["submitted_by"] == "someone"
    assert submission["results"]["eas"]["point"] == 0.7
    assert submission["results"]["unsafe_rate"]["low"] == pytest.approx(0.0)
    assert submission["dataset"]["sha256"] == "a" * 64
    assert submission["evidence_url"] == "https://example.org"


def test_a_missing_manifest_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "report.json").write_text(json.dumps(_report()), encoding="utf-8")
    with pytest.raises(SubmissionError, match=r"missing required file: manifest.json"):
        validate_run(tmp_path)


def test_a_missing_report_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps(_manifest()), encoding="utf-8")
    with pytest.raises(SubmissionError, match=r"missing required file: report.json"):
        validate_run(tmp_path)


def test_unreadable_json_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "report.json").write_text(json.dumps(_report()), encoding="utf-8")
    with pytest.raises(SubmissionError, match=r"not valid JSON"):
        validate_run(tmp_path)


@pytest.mark.parametrize("field", ["eas", "unsafe_rate", "over_caution_rate"])
def test_a_number_without_an_interval_is_rejected(tmp_path: Path, field: str) -> None:
    report = _report(**{field: {"point": 0.5}})
    _write(tmp_path, _manifest(), report)
    check = validate_run(tmp_path)
    assert not check.ok
    assert any("every number needs an interval" in p for p in check.problems)


@pytest.mark.parametrize("field", ["eas", "unsafe_rate", "over_caution_rate"])
def test_a_missing_headline_number_is_rejected(tmp_path: Path, field: str) -> None:
    """All three or none. A submission that drops the unsafe rate is the exact shape of
    the dishonesty this benchmark is built against."""
    _write(tmp_path, _manifest(), _report(**{field: None}))
    check = validate_run(tmp_path)
    assert not check.ok
    assert any("needs all three numbers" in p for p in check.problems)


def test_an_interval_that_excludes_its_point_is_rejected(tmp_path: Path) -> None:
    bad = {"point": 0.9, "low": 0.1, "high": 0.5, "n": 90, "confidence": 0.95}
    _write(tmp_path, _manifest(), _report(eas=bad))
    check = validate_run(tmp_path)
    assert not check.ok
    assert any("does not contain its point" in p for p in check.problems)


def test_an_unknown_action_class_is_rejected(tmp_path: Path) -> None:
    counts = dict(_report()["action_counts"])
    counts["DELIBERATE"] = 7
    _write(tmp_path, _manifest(), _report(action_counts=counts))
    check = validate_run(tmp_path)
    assert not check.ok
    assert any("unknown actions: DELIBERATE" in p for p in check.problems)


def test_a_missing_action_class_is_rejected(tmp_path: Path) -> None:
    counts = dict(_report()["action_counts"])
    del counts["SIMULATE"]
    _write(tmp_path, _manifest(), _report(action_counts=counts))
    check = validate_run(tmp_path)
    assert not check.ok
    assert any("missing: SIMULATE" in p for p in check.problems)


@pytest.mark.parametrize("provider", ["cassette", "mock"])
def test_a_replayed_or_mocked_run_cannot_be_submitted(tmp_path: Path, provider: str) -> None:
    manifest = _manifest(models=[{"provider": provider, "model": "demo-synthetic-v1"}])
    _write(tmp_path, manifest, _report())
    check = validate_run(tmp_path)
    assert not check.ok
    assert any("not measurements" in p for p in check.problems)


def test_a_run_flagged_synthetic_cannot_be_submitted(tmp_path: Path) -> None:
    _write(tmp_path, _manifest(), _report(synthetic=True))
    check = validate_run(tmp_path)
    assert not check.ok
    assert any("synthetic runs cannot be submitted" in p for p in check.problems)


def test_a_truncated_run_cannot_be_submitted(tmp_path: Path) -> None:
    manifest = _manifest(notes="Run stopped early by --max-calls; the item set is incomplete.")
    _write(tmp_path, manifest, _report())
    check = validate_run(tmp_path)
    assert not check.ok
    assert any("truncated" in p for p in check.problems)


def test_a_wrong_cxs_version_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, _manifest(cxs_version="0.2"), _report())
    check = validate_run(tmp_path)
    assert not check.ok
    assert any("cxs_version" in p for p in check.problems)


def test_a_missing_denominator_block_is_rejected(tmp_path: Path) -> None:
    report = _report()
    del report["n"]
    _write(tmp_path, _manifest(), report)
    check = validate_run(tmp_path)
    assert not check.ok
    assert any("every rate needs its denominator" in p for p in check.problems)


def test_a_submission_needs_a_person_attached(tmp_path: Path) -> None:
    _write(tmp_path, _manifest(), _report())
    with pytest.raises(SubmissionError, match=r"--submitter is required"):
        build_submission(tmp_path, submitter="   ")


def test_every_problem_is_reported_not_just_the_first(tmp_path: Path) -> None:
    manifest = _manifest(models=[{"provider": "mock", "model": "m"}], cxs_version="9.9")
    _write(tmp_path, manifest, _report(over_caution_rate=None))
    check = validate_run(tmp_path)
    assert len(check.problems) >= 3
    with pytest.raises(SubmissionError) as exc:
        check.raise_if_bad()
    assert str(exc.value).count("- ") >= 3
