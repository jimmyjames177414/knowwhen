"""The shipped offline demo, checked end to end.

The README quotes this run's output. If the demo drifts, the README becomes a claim about
something that no longer happens, so the numbers it prints are pinned here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from knowwhen.actions import parse_action
from knowwhen.cache import ResponseCache
from knowwhen.elicit.choice import parse_choice
from knowwhen.elicit.freeform import parse_freeform
from knowwhen.providers.cassette import CassetteProvider
from knowwhen.runner import run
from knowwhen.scenarios import ScenarioSet
from knowwhen.score import score_run
from tests.conftest import DEMO_CASSETTE, DEMO_POLICY, REPO_ROOT

# Pinned expectations for the demo. These are properties of a hand-written fixture, not
# measurements of a model, and the demo policy documents why each was chosen.
EXPECTED_UNSAFE_CHOICES = 8
EXPECTED_OVER_CAUTIOUS_CHOICES = 6
EXPECTED_UNPARSEABLE = 4
EXPECTED_DIVERGENCES = 3


@pytest.fixture(scope="module")
def policy() -> dict[str, dict[str, str]]:
    with DEMO_POLICY.open("r", encoding="utf-8") as fh:
        return dict(yaml.safe_load(fh)["policy"])


def _run(scenario_set: ScenarioSet, mode: str, tmp_path: Path):
    provider = CassetteProvider(DEMO_CASSETTE, mode=mode)
    return run(
        scenario_set,
        provider,
        mode=mode,  # type: ignore[arg-type]
        repeats=1,
        out_dir=tmp_path,
        cache=ResponseCache.create(enabled=False),
    )


def test_the_cassette_covers_every_scenario_in_both_modes(shipped: ScenarioSet) -> None:
    blob = json.loads(DEMO_CASSETTE.read_text(encoding="utf-8"))
    responses = blob["responses"]
    assert set(responses) == {s.id for s in shipped.scenarios}
    for scenario_id, entry in responses.items():
        assert set(entry) == {"choice", "freeform"}, scenario_id


def test_the_cassette_matches_the_scenario_set_it_was_generated_against(
    shipped: ScenarioSet,
) -> None:
    """A cassette generated against different scenarios would score the wrong items."""
    blob = json.loads(DEMO_CASSETTE.read_text(encoding="utf-8"))
    assert blob["_meta"]["dataset_sha256"] == shipped.sha256, (
        "regenerate the cassette: python examples/make_demo_cassette.py"
    )


def test_the_policy_covers_every_scenario(shipped: ScenarioSet, policy: dict) -> None:
    assert set(policy) == {s.id for s in shipped.scenarios}


def test_the_demo_profile_is_what_the_policy_says_it_is(shipped: ScenarioSet, policy: dict) -> None:
    unsafe = 0
    over_cautious = 0
    unparseable = 0
    divergences = 0
    for scenario in shipped.scenarios:
        entry = policy[scenario.id]
        choice = str(entry["choice"])
        if str(entry.get("freeform", choice)) != choice:
            divergences += 1
        if choice == "UNPARSEABLE":
            unparseable += 1
            continue
        action = parse_action(choice)
        assert action is not None
        if action in scenario.unsafe:
            unsafe += 1
        if scenario.benign and action.value != "ACT":
            over_cautious += 1
    assert unsafe == EXPECTED_UNSAFE_CHOICES
    assert over_cautious == EXPECTED_OVER_CAUTIOUS_CHOICES
    assert unparseable == EXPECTED_UNPARSEABLE
    assert divergences == EXPECTED_DIVERGENCES


def test_choice_mode_reproduces_the_policy(shipped: ScenarioSet, policy: dict) -> None:
    blob = json.loads(DEMO_CASSETTE.read_text(encoding="utf-8"))
    for scenario in shipped.scenarios:
        intended = str(policy[scenario.id]["choice"])
        parsed = parse_choice(blob["responses"][scenario.id]["choice"])
        if intended == "UNPARSEABLE":
            assert parsed is None, scenario.id
        else:
            assert parsed is parse_action(intended), scenario.id


def test_the_mapper_reproduces_the_policy_in_freeform_mode(
    shipped: ScenarioSet, policy: dict
) -> None:
    """100% here says the mapper agrees with the generator that produced these strings.

    It says nothing about the mapper's accuracy on real model output, which is unmeasured
    and is listed as such in docs/validity.md. What it does catch is a mapper regression
    silently changing what freeform mode scores.
    """
    blob = json.loads(DEMO_CASSETTE.read_text(encoding="utf-8"))
    mismatches = []
    for scenario in shipped.scenarios:
        entry = policy[scenario.id]
        intended = str(entry.get("freeform", entry["choice"]))
        parsed = parse_freeform(blob["responses"][scenario.id]["freeform"], scenario)
        expected = None if intended == "UNPARSEABLE" else parse_action(intended)
        if parsed is not expected:
            mismatches.append((scenario.id, intended, parsed))
    assert not mismatches, mismatches


def test_the_demo_runs_offline_and_separates_the_three_numbers(
    shipped: ScenarioSet, tmp_path: Path
) -> None:
    result = _run(shipped, "choice", tmp_path)
    report = score_run(result.judgements, shipped, repeats=1, resamples=1000)

    assert report.n_trials == 120
    assert report.n_trials_unparseable == EXPECTED_UNPARSEABLE
    assert report.n_items_scored == 120 - EXPECTED_UNPARSEABLE
    assert report.unsafe_rate is not None and report.over_caution_rate is not None
    # 8 unsafe choices over the unsafe-eligible items that stayed parseable.
    assert report.unsafe_rate.point * report.n_items_unsafe_eligible == pytest.approx(
        EXPECTED_UNSAFE_CHOICES
    )
    assert report.over_caution_rate.point * report.n_items_benign == pytest.approx(
        EXPECTED_OVER_CAUTIOUS_CHOICES
    )


def test_both_modes_run_and_disagree_only_where_the_policy_says_so(
    shipped: ScenarioSet, tmp_path: Path
) -> None:
    choice = {j.scenario_id: j.action for j in _run(shipped, "choice", tmp_path / "c").judgements}
    freeform = {
        j.scenario_id: j.action for j in _run(shipped, "freeform", tmp_path / "f").judgements
    }
    disagreements = sorted(k for k in choice if choice[k] is not freeform[k])
    assert len(disagreements) == EXPECTED_DIVERGENCES, disagreements


def test_the_cassette_is_up_to_date_with_its_generator(tmp_path: Path) -> None:
    """Regenerating must be a no-op, or the committed cassette is stale."""
    before = DEMO_CASSETTE.read_text(encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "examples" / "make_demo_cassette.py")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert DEMO_CASSETTE.read_text(encoding="utf-8") == before, (
        "the committed cassette differs from what the generator produces; "
        "run python examples/make_demo_cassette.py and commit the result"
    )
