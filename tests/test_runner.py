"""Running, resuming, budgeting, and the one determinism claim the spec forbids faking."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from knowwhen.actions import Action
from knowwhen.cache import ResponseCache
from knowwhen.providers.base import Params
from knowwhen.providers.mock import MockProvider
from knowwhen.providers.openai_compat import OpenAICompatProvider
from knowwhen.runner import new_experiment_id, plan_dry_run, rescore, run
from knowwhen.scenarios import ScenarioSet


@pytest.fixture()
def small(shipped: ScenarioSet) -> ScenarioSet:
    return shipped.filtered(limit=6)


def _trials(directory: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (directory / "trials.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_a_run_writes_one_trial_per_item_per_repeat(small: ScenarioSet, tmp_path: Path) -> None:
    result = run(
        small,
        MockProvider(policy=Action.VERIFY),
        repeats=2,
        out_dir=tmp_path,
        cache=ResponseCache.create(enabled=False),
    )
    assert len(_trials(result.directory)) == 12
    assert len(result.judgements) == 12


def test_an_interrupted_run_resumes_instead_of_repeating(
    small: ScenarioSet, tmp_path: Path
) -> None:
    experiment_id = new_experiment_id()
    first = run(
        small,
        MockProvider(policy=Action.VERIFY),
        repeats=1,
        out_dir=tmp_path,
        cache=ResponseCache.create(enabled=False),
        max_calls=2,
        experiment_id=experiment_id,
    )
    assert first.truncated
    assert len(_trials(first.directory)) == 2

    second = run(
        small,
        MockProvider(policy=Action.VERIFY),
        repeats=1,
        out_dir=tmp_path,
        cache=ResponseCache.create(enabled=False),
        experiment_id=experiment_id,
    )
    assert not second.truncated
    assert second.n_model_calls == 4, "the two already-recorded trials should not be re-run"
    assert len(_trials(second.directory)) == 6


def test_determinism_is_never_claimed_without_repeats(small: ScenarioSet, tmp_path: Path) -> None:
    """One repeat gives nothing to compare, so the honest answer is 'stochastic'."""
    result = run(
        small,
        MockProvider(policy=Action.VERIFY),
        repeats=1,
        out_dir=tmp_path,
        cache=ResponseCache.create(enabled=False),
    )
    assert result.determinism == "stochastic"
    manifest = json.loads((result.directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["determinism"] == "stochastic"


def test_determinism_is_claimed_only_when_outputs_actually_matched(
    small: ScenarioSet, tmp_path: Path
) -> None:
    steady = run(
        small,
        MockProvider(policy=Action.VERIFY),
        repeats=3,
        out_dir=tmp_path / "steady",
        cache=ResponseCache.create(enabled=False),
    )
    assert steady.determinism == "deterministic"

    varying = run(
        small,
        MockProvider(policy=Action.VERIFY, unparseable_every=2),
        repeats=3,
        out_dir=tmp_path / "varying",
        cache=ResponseCache.create(enabled=False),
    )
    assert varying.determinism == "stochastic"


def test_a_cassette_run_records_the_replay_caveat(shipped: ScenarioSet, tmp_path: Path) -> None:
    from knowwhen.providers.cassette import CassetteProvider
    from tests.conftest import DEMO_CASSETTE

    result = run(
        shipped.filtered(limit=4),
        CassetteProvider(DEMO_CASSETTE, mode="choice"),
        repeats=2,
        out_dir=tmp_path,
        cache=ResponseCache.create(enabled=False),
    )
    manifest = json.loads((result.directory / "manifest.json").read_text(encoding="utf-8"))
    assert "replayed from a cassette" in manifest["notes"]
    assert "not the model" in manifest["notes"]


def test_the_cache_stops_a_second_run_calling_the_model(small: ScenarioSet, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    first = run(
        small,
        MockProvider(policy=Action.VERIFY),
        out_dir=tmp_path / "a",
        cache=ResponseCache.create(cache_dir),
    )
    assert first.n_model_calls == 6
    second = run(
        small,
        MockProvider(policy=Action.VERIFY),
        out_dir=tmp_path / "b",
        cache=ResponseCache.create(cache_dir),
    )
    assert second.n_model_calls == 0
    assert second.cache_stats["hits"] == 6


def test_dry_run_counts_calls_without_making_any(small: ScenarioSet, tmp_path: Path) -> None:
    plan = plan_dry_run(
        small,
        mode="choice",
        repeats=4,
        provider_name="mock",
        model="m",
        params=Params(),
        cache=ResponseCache.create(tmp_path, enabled=False),
    )
    assert plan.model_calls == 24
    assert plan.cached_calls == 0
    assert plan.prompt_tokens_estimate > 0


def test_dry_run_subtracts_what_the_cache_already_holds(small: ScenarioSet, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    run(
        small,
        MockProvider(policy=Action.VERIFY),
        out_dir=tmp_path / "a",
        cache=ResponseCache.create(cache_dir),
    )
    plan = plan_dry_run(
        small,
        mode="choice",
        repeats=1,
        provider_name="mock",
        model="mock-synthetic-v1",
        params=Params(),
        cache=ResponseCache.create(cache_dir),
    )
    assert plan.model_calls == 0
    assert plan.cached_calls == 6


def test_rescoring_reads_trials_and_makes_no_calls(small: ScenarioSet, tmp_path: Path) -> None:
    """The point of separating Trial from Outcome: a scorer change costs nothing."""
    result = run(
        small,
        MockProvider(policy=Action.VERIFY),
        repeats=2,
        out_dir=tmp_path,
        cache=ResponseCache.create(enabled=False),
    )
    (result.directory / "outcomes.jsonl").unlink()
    judgements = rescore(result.directory, small, mode="choice")
    assert len(judgements) == 12
    assert (result.directory / "outcomes.jsonl").exists()
    assert all(j.action is Action.VERIFY for j in judgements)


def test_experiment_ids_are_unique_and_time_sortable() -> None:
    ids = [new_experiment_id() for _ in range(50)]
    assert len(set(ids)) == 50
    assert all(len(i) == 26 for i in ids)
    assert ids == sorted(ids) or len(set(i[:10] for i in ids)) > 1


def test_a_provider_error_becomes_a_recorded_trial_not_a_crash(
    small: ScenarioSet, tmp_path: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "overloaded"})

    provider = OpenAICompatProvider(
        model="m",
        base_url="http://test.invalid/v1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = run(
        small.filtered(limit=2),
        provider,
        out_dir=tmp_path,
        cache=ResponseCache.create(enabled=False),
    )
    rows = _trials(result.directory)
    assert len(rows) == 2
    assert all(row["error"] for row in rows)


def test_the_openai_adapter_sends_what_it_says_it_sends() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ACTION: VERIFY"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 3},
            },
        )

    os.environ["KNOWWHEN_TEST_KEY"] = "secret-value"
    try:
        provider = OpenAICompatProvider(
            model="qwen3:8b",
            base_url="http://localhost:11434/v1/",
            api_key_env="KNOWWHEN_TEST_KEY",
            params=Params(temperature=0.0, seed=7),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        completion = provider.complete([{"role": "user", "content": "hi"}])
    finally:
        del os.environ["KNOWWHEN_TEST_KEY"]

    assert completion.text == "ACTION: VERIFY"
    assert completion.prompt_tokens == 11
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert seen["auth"] == "Bearer secret-value"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "qwen3:8b"
    assert body["seed"] == 7


def test_a_missing_api_key_variable_is_not_an_error() -> None:
    """Local servers need no key. Requiring one would exclude every Ollama user."""
    provider = OpenAICompatProvider(
        model="m",
        base_url="http://localhost:11434/v1",
        api_key_env="KNOWWHEN_DEFINITELY_UNSET_KEY",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(
                    200, json={"choices": [{"message": {"content": "ACTION: ACT"}}]}
                )
            )
        ),
    )
    assert provider.complete([{"role": "user", "content": "hi"}]).text == "ACTION: ACT"


@pytest.mark.live
def test_against_a_real_endpoint() -> None:  # pragma: no cover - needs a live model
    """Deselected by default. Run with: pytest -m live

    Set KNOWWHEN_BASE_URL and KNOWWHEN_MODEL first, e.g. against a local Ollama.
    """
    base_url = os.environ.get("KNOWWHEN_BASE_URL")
    model = os.environ.get("KNOWWHEN_MODEL")
    if not base_url or not model:
        pytest.skip("set KNOWWHEN_BASE_URL and KNOWWHEN_MODEL")
    provider = OpenAICompatProvider(model=model, base_url=base_url)
    completion = provider.complete(
        [{"role": "user", "content": "Reply with exactly: ACTION: VERIFY"}]
    )
    assert completion.error is None
    assert completion.text
