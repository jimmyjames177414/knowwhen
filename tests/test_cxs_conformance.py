"""CXS v0.1 conformance, asserted against a real run of the shipped demo.

Conformance is a claim about files, so this test makes files and validates them. It does
not check that a schema exists; it checks that output this tool actually produced passes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from knowwhen.providers.cassette import CassetteProvider
from knowwhen.runner import run
from knowwhen.scenarios import ScenarioSet
from knowwhen.submit import build_submission
from tests.conftest import DEMO_CASSETTE, SCHEMA_DIR

SCHEMA_FILES = (
    "model-descriptor.schema.json",
    "intervention.schema.json",
    "trial.schema.json",
    "outcome.schema.json",
    "run-manifest.schema.json",
    "submission.schema.json",
)


@pytest.fixture(scope="module")
def registry() -> Registry[Any]:
    """Schemas resolve each other by filename, so they need a registry keyed that way."""
    resources = []
    for name in SCHEMA_FILES:
        blob = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        resources.append((name, Resource.from_contents(blob)))
    return Registry().with_resources(resources)


def _validator(name: str, registry: Registry[Any]) -> Draft202012Validator:
    blob = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    return Draft202012Validator(blob, registry=registry)


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from knowwhen.cache import ResponseCache
    from knowwhen.scenarios import load_scenarios

    scenario_set: ScenarioSet = load_scenarios()
    provider = CassetteProvider(DEMO_CASSETTE, mode="choice")
    result = run(
        scenario_set,
        provider,
        mode="choice",
        repeats=1,
        out_dir=tmp_path_factory.mktemp("cxs"),
        cache=ResponseCache.create(enabled=False),
    )
    return result.directory


def _lines(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_every_schema_is_itself_valid(registry: Registry[Any]) -> None:
    for name in SCHEMA_FILES:
        blob = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(blob)


def test_the_run_produces_the_layout_the_spec_requires(demo_run: Path) -> None:
    for name in (
        "manifest.json",
        "interventions.json",
        "trials.jsonl",
        "outcomes.jsonl",
    ):
        assert (demo_run / name).exists(), f"missing {name}"


def test_the_manifest_validates(demo_run: Path, registry: Registry[Any]) -> None:
    manifest = json.loads((demo_run / "manifest.json").read_text(encoding="utf-8"))
    _validator("run-manifest.schema.json", registry).validate(manifest)
    assert manifest["cxs_version"] == "0.1"
    assert manifest["tool"]["name"] == "knowwhen"
    assert manifest["dataset"]["n_items"] == 120


def test_every_trial_validates(demo_run: Path, registry: Registry[Any]) -> None:
    validator = _validator("trial.schema.json", registry)
    rows = _lines(demo_run / "trials.jsonl")
    assert len(rows) == 120
    for row in rows:
        validator.validate(row)


def test_every_outcome_validates(demo_run: Path, registry: Registry[Any]) -> None:
    validator = _validator("outcome.schema.json", registry)
    rows = _lines(demo_run / "outcomes.jsonl")
    assert len(rows) == 120
    for row in rows:
        validator.validate(row)


def test_the_schema_itself_forbids_scoring_an_unparseable_trial(
    registry: Registry[Any],
) -> None:
    """The one deliberate refinement to CXS, enforced at the file level."""
    validator = _validator("outcome.schema.json", registry)
    bad = {
        "trial_id": "t",
        "scorer": "eas:v1",
        "score": 0.0,
        "passed": False,
        "detail": {"action": None, "unsafe": None, "parse_status": "unparseable"},
    }
    assert not validator.is_valid(bad), "an unparseable outcome scored 0.0 must not validate"
    bad["score"] = None
    bad["passed"] = None
    assert validator.is_valid(bad)


def test_the_intervention_is_the_control_arm(demo_run: Path, registry: Registry[Any]) -> None:
    """knowwhen runs one arm and reports no intervention effect, so the arm it runs is
    the control."""
    validator = _validator("intervention.schema.json", registry)
    interventions = json.loads((demo_run / "interventions.json").read_text(encoding="utf-8"))
    assert len(interventions) == 1
    validator.validate(interventions[0])
    assert interventions[0]["kind"] == "noop"


def test_trials_and_outcomes_are_one_to_one(demo_run: Path) -> None:
    trials = {row["trial_id"] for row in _lines(demo_run / "trials.jsonl")}
    outcomes = {row["trial_id"] for row in _lines(demo_run / "outcomes.jsonl")}
    assert trials == outcomes


def test_a_submission_built_from_a_real_run_validates(
    tmp_path: Path, registry: Registry[Any]
) -> None:
    """The demo run itself cannot be submitted, so this builds an equivalent manifest with
    a real provider to check the submission schema against a shape the tool produces."""
    manifest = {
        "cxs_version": "0.1",
        "experiment_id": "01ABC",
        "tool": {"name": "knowwhen", "version": "0.1.0"},
        "created_at": "2026-09-02T00:00:00Z",
        "models": [
            {
                "provider": "openai-compatible",
                "base_url": "http://localhost:11434/v1",
                "model": "qwen3:8b",
                "params": {"temperature": 0.0, "top_p": 1.0, "max_tokens": 512, "seed": None},
                "observed_at": "2026-09-02T00:00:00Z",
            }
        ],
        "dataset": {"name": "knowwhen-scenarios-v1", "sha256": "b" * 64, "n_items": 120},
        "scorer": "eas:v1",
        "repeats": 3,
        "determinism": "stochastic",
        "elicitation_mode": "choice",
    }
    interval = {"point": 0.6, "low": 0.5, "high": 0.7, "n": 120, "confidence": 0.95}
    report = {
        "eas": interval,
        "unsafe_rate": interval,
        "over_caution_rate": interval,
        "unparseable_rate": 0.0,
        "mde_eas": 0.1,
        "n": {"items_scored": 120, "repeats": 3},
        "action_counts": {
            "ACT": 1,
            "ASK": 1,
            "VERIFY": 1,
            "SIMULATE": 1,
            "ESCALATE": 1,
            "ABSTAIN": 1,
        },
        "dataset_sha256": "b" * 64,
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")

    submission = build_submission(tmp_path, submitter="a contributor")
    _validator("submission.schema.json", registry).validate(submission)


def test_the_submission_schema_rejects_a_replayed_provider(registry: Registry[Any]) -> None:
    validator = _validator("submission.schema.json", registry)
    submission = {
        "submission_version": "1",
        "cxs_version": "0.1",
        "submitted_by": "someone",
        "experiment_id": "01ABC",
        "tool": {"name": "knowwhen", "version": "0.1.0"},
        "created_at": "2026-09-02T00:00:00Z",
        "model": {"provider": "cassette", "model": "demo-synthetic-v1"},
        "dataset": {"name": "knowwhen-scenarios-v1", "sha256": "c" * 64, "n_items": 120},
        "repeats": 1,
        "determinism": "stochastic",
        "results": {
            "eas": {"point": 1.0, "low": 1.0, "high": 1.0, "n": 120, "confidence": 0.95},
            "unsafe_rate": {"point": 0.0, "low": 0.0, "high": 0.0, "n": 90, "confidence": 0.95},
            "over_caution_rate": {
                "point": 0.0,
                "low": 0.0,
                "high": 0.0,
                "n": 30,
                "confidence": 0.95,
            },
            "unparseable_rate": 0.0,
            "n": {"items_scored": 120, "repeats": 1},
        },
    }
    assert not validator.is_valid(submission)
