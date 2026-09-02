"""Degenerate baselines: they run, they are correct, and they reach the report.

The point of these is adversarial. A benchmark a constant policy can win is not measuring
what it claims to, so the constants have to be computed correctly, compared over the same
items as the model, and printed where a reader cannot miss them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowwhen.actions import ACTION_ORDER, Action
from knowwhen.baselines import (
    BASELINE_IDS,
    beaten_by,
    indistinguishable_from,
    majority_class,
    run_baselines,
)
from knowwhen.cache import ResponseCache
from knowwhen.cli import main
from knowwhen.providers.mock import MockProvider
from knowwhen.report import build_report, render_markdown, render_terminal
from knowwhen.runner import run
from knowwhen.scenarios import ScenarioSet
from knowwhen.score import judge, score_run
from tests.conftest import make_scenario, make_set


def _credit(**overrides: float) -> dict[Action, float]:
    credit = dict.fromkeys(ACTION_ORDER, 0.0)
    for name, value in overrides.items():
        credit[Action[name]] = value
    return credit


# ------------------------------------------------------------------- they run at all


def test_every_baseline_runs_on_the_shipped_set(shipped: ScenarioSet) -> None:
    baselines = run_baselines(shipped, resamples=200)
    assert tuple(b.id for b in baselines) == BASELINE_IDS
    assert len(baselines) == 8
    for baseline in baselines:
        assert baseline.report.n_items_scored == 120
        assert baseline.report.eas.low <= baseline.report.eas.point <= baseline.report.eas.high


def test_there_is_a_constant_for_every_action_class() -> None:
    """A missing constant is a class whose degenerate case nobody checked."""
    for action in ACTION_ORDER:
        assert f"always-{action.value}" in BASELINE_IDS


# ------------------------------------------------------------- they are computed right


def test_a_constant_baseline_scores_exactly_that_column_of_the_credit_vectors() -> None:
    scenarios = [
        make_scenario("a", credit=_credit(VERIFY=1.0, ASK=0.4)),
        make_scenario("b", credit=_credit(VERIFY=1.0, ASK=0.8)),
    ]
    baselines = {b.id: b for b in run_baselines(make_set(*scenarios), resamples=200)}
    assert baselines["always-VERIFY"].report.eas.point == pytest.approx(1.0)
    assert baselines["always-ASK"].report.eas.point == pytest.approx(0.6)
    assert baselines["always-ACT"].report.eas.point == pytest.approx(0.0)


def test_always_act_maximises_unsafe_and_minimises_over_caution(shipped: ScenarioSet) -> None:
    baselines = {b.id: b for b in run_baselines(shipped, resamples=200)}
    always_act = baselines["always-ACT"].report
    assert always_act.unsafe_rate is not None
    assert always_act.unsafe_rate.point == pytest.approx(1.0)
    assert always_act.over_caution_rate is not None
    assert always_act.over_caution_rate.point == pytest.approx(0.0)


def test_every_non_act_constant_is_perfectly_safe_and_perfectly_useless(
    shipped: ScenarioSet,
) -> None:
    """The always-ASK row is the whole argument for shipping benign controls: a policy
    that never acts has a 0% unsafe rate, which under a single number would read as
    exemplary caution."""
    baselines = {b.id: b for b in run_baselines(shipped, resamples=200)}
    for action in ACTION_ORDER:
        if action is Action.ACT:
            continue
        report = baselines[f"always-{action.value}"].report
        assert report.unsafe_rate is not None
        assert report.unsafe_rate.point == pytest.approx(0.0)
        assert report.over_caution_rate is not None
        assert report.over_caution_rate.point == pytest.approx(1.0)


def test_random_uniform_is_the_exact_expectation_not_a_lucky_draw(
    shipped: ScenarioSet,
) -> None:
    """A single seeded draw moved over-caution by more than 0.2 between seeds on 30
    controls. The reported figure is the closed-form expectation instead, so it carries
    no sampling noise: 1/6 unsafe, 5/6 over-cautious, exactly."""
    baselines = {b.id: b for b in run_baselines(shipped, resamples=200)}
    uniform = baselines["random-uniform"].report
    assert uniform.unsafe_rate is not None
    assert uniform.unsafe_rate.point == pytest.approx(1 / 6)
    assert uniform.over_caution_rate is not None
    assert uniform.over_caution_rate.point == pytest.approx(5 / 6)

    expected_eas = sum(sum(s.credit.values()) / len(ACTION_ORDER) for s in shipped.scenarios) / len(
        shipped
    )
    assert uniform.eas.point == pytest.approx(expected_eas)


def test_random_uniform_does_not_depend_on_the_seed(shipped: ScenarioSet) -> None:
    first = {b.id: b for b in run_baselines(shipped, seed=1, resamples=200)}
    second = {b.id: b for b in run_baselines(shipped, seed=999, resamples=200)}
    assert first["random-uniform"].report.eas.point == pytest.approx(
        second["random-uniform"].report.eas.point
    )


def test_majority_class_picks_the_most_frequently_optimal_action() -> None:
    scenarios = [
        make_scenario("a", credit=_credit(VERIFY=1.0)),
        make_scenario("b", credit=_credit(VERIFY=1.0)),
        make_scenario("c", credit=_credit(ASK=1.0)),
    ]
    action, hits = majority_class(tuple(scenarios))
    assert action is Action.VERIFY
    assert hits == 2


def test_majority_class_ties_break_deterministically() -> None:
    scenarios = [
        make_scenario("a", credit=_credit(ACT=0.0, ASK=1.0)),
        make_scenario("b", credit=_credit(VERIFY=1.0)),
    ]
    first = majority_class(tuple(scenarios))
    second = majority_class(tuple(reversed(scenarios)))
    assert first == second
    assert first[0] is Action.ASK  # earlier in ACTION_ORDER wins the tie


def test_majority_class_scores_at_least_as_well_as_every_other_constant(
    shipped: ScenarioSet,
) -> None:
    """It is the constant an adversary would choose, so nothing constant should beat it."""
    baselines = {b.id: b for b in run_baselines(shipped, resamples=200)}
    majority = baselines["majority-class"].report.eas.point
    for action in ACTION_ORDER:
        assert baselines[f"always-{action.value}"].report.eas.point <= majority + 1e-9


# ------------------------------------------------------ scored over the model's items


def test_baselines_are_scored_over_exactly_the_items_given(shipped: ScenarioSet) -> None:
    """Comparing a model's EAS over its parseable items against a baseline's over all of
    them would be comparing two different numbers and calling the difference a gap."""
    ids = tuple(s.id for s in shipped.scenarios[:20])
    baselines = run_baselines(shipped, item_ids=ids, resamples=200)
    for baseline in baselines:
        assert baseline.report.n_items_scored == 20


def test_a_run_reports_baselines_over_its_own_scored_items(
    shipped: ScenarioSet, tmp_path: Path
) -> None:
    subset = shipped.filtered(limit=10)
    result = run(
        subset,
        MockProvider(policy=Action.VERIFY, unparseable_every=4),
        out_dir=tmp_path,
        cache=ResponseCache.create(enabled=False),
    )
    report = score_run(result.judgements, subset, resamples=200)
    assert report.n_items_scored < 10, "the mock should have lost at least one item"
    baselines = run_baselines(subset, item_ids=report.scored_item_ids, resamples=200)
    for baseline in baselines:
        assert baseline.report.n_items_scored == report.n_items_scored


# ------------------------------------------------------------------ finding detection


def _report_for(eas_point: float, shipped: ScenarioSet):
    """Score a policy chosen to land near a target EAS, for the finding tests."""
    action = Action.VERIFY if eas_point > 0.5 else Action.ACT
    return score_run([judge(s, action) for s in shipped.scenarios], shipped, resamples=200)


def test_a_constant_beating_the_model_is_detected(shipped: ScenarioSet) -> None:
    weak = _report_for(0.2, shipped)  # always-ACT
    baselines = run_baselines(shipped, resamples=200)
    beaten = beaten_by(weak, baselines)
    assert "always-VERIFY" in beaten
    assert "majority-class" in beaten


def test_a_narrow_win_over_a_constant_is_reported_as_indistinguishable(
    shipped: ScenarioSet,
) -> None:
    strong = _report_for(0.9, shipped)  # always-VERIFY, so identical to a baseline
    baselines = run_baselines(shipped, resamples=200)
    flagged = set(beaten_by(strong, baselines)) | set(indistinguishable_from(strong, baselines))
    assert "always-VERIFY" in flagged


def test_the_two_finding_lists_never_overlap(shipped: ScenarioSet) -> None:
    report = _report_for(0.9, shipped)
    baselines = run_baselines(shipped, resamples=200)
    assert not set(beaten_by(report, baselines)) & set(indistinguishable_from(report, baselines))


# ------------------------------------------------------------------- they reach output


def test_baselines_appear_in_report_json_and_markdown(shipped: ScenarioSet) -> None:
    subset = shipped.filtered(limit=30)
    report = score_run([judge(s, Action.ASK) for s in subset.scenarios], subset, resamples=200)
    baselines = run_baselines(subset, item_ids=report.scored_item_ids, resamples=200)
    blob = build_report(
        report,
        experiment_id="01TEST",
        model="test-model",
        provider="mock",
        mode="choice",
        determinism="stochastic",
        dataset_version="v1",
        synthetic=True,
        baselines=baselines,
    )
    assert len(blob["baselines"]) == len(BASELINE_IDS)
    assert {b["id"] for b in blob["baselines"]} == set(BASELINE_IDS)

    markdown = render_markdown(report, blob)
    assert "## Baselines" in markdown
    for name in BASELINE_IDS:
        assert f"`{name}`" in markdown
    # Same table as the model, not an appendix.
    assert "**test-model**" in markdown.split("## Baselines", 1)[1]

    terminal = render_terminal(report, blob)
    for name in BASELINE_IDS:
        assert name in terminal


def test_the_report_states_the_finding_when_a_constant_wins(shipped: ScenarioSet) -> None:
    subset = shipped.filtered(limit=40)
    weak = score_run([judge(s, Action.ACT) for s in subset.scenarios], subset, resamples=200)
    baselines = run_baselines(subset, item_ids=weak.scored_item_ids, resamples=200)
    blob = build_report(
        weak,
        experiment_id="01TEST",
        model="weak-model",
        provider="mock",
        mode="choice",
        determinism="stochastic",
        dataset_version="v1",
        synthetic=True,
        baselines=baselines,
    )
    assert blob["baselines_beating_model"]
    markdown = render_markdown(weak, blob)
    assert "FINDING" in markdown
    assert "not clear of the degenerate baselines" in markdown
    assert "FINDING" in render_terminal(weak, blob)


def test_the_cli_run_writes_baselines_into_report_json(tmp_path: Path) -> None:
    code = main(
        [
            "run",
            "--provider",
            "mock",
            "--limit",
            "20",
            "--no-cache",
            "--quiet",
            "--resamples",
            "200",
            "--out",
            str(tmp_path),
        ]
    )
    assert code == 0
    run_dir = next(tmp_path.iterdir())
    blob = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert {b["id"] for b in blob["baselines"]} == set(BASELINE_IDS)
    assert "baselines_beating_model" in blob
    assert "baselines_within_mde" in blob
    assert "## Baselines" in (run_dir / "report.md").read_text(encoding="utf-8")


def test_the_baselines_command_prints_every_policy(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["baselines", "--resamples", "200"]) == 0
    out = capsys.readouterr().out
    for name in BASELINE_IDS:
        assert name in out
    assert "not a claim about" in out


def test_the_baselines_command_emits_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["baselines", "--json", "--resamples", "200"]) == 0
    blob = json.loads(capsys.readouterr().out)
    assert blob["n_items"] == 120
    assert len(blob["baselines"]) == len(BASELINE_IDS)
    for entry in blob["baselines"]:
        assert set(entry["eas"]) >= {"point", "low", "high", "n", "confidence"}
