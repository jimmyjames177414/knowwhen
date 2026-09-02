"""Providers and the response cache.

The rule this file mostly exists to enforce: a cassette that will not say where its
responses came from does not load. A fixture whose provenance is unstated is how a
synthetic response becomes a published measurement.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowwhen.actions import Action
from knowwhen.cache import ResponseCache
from knowwhen.providers.base import Completion, Params, cache_key, estimate_tokens, prompt_sha256
from knowwhen.providers.cassette import CassetteError, CassetteProvider
from knowwhen.providers.mock import MockProvider
from tests.conftest import DEMO_CASSETTE

MESSAGES = [{"role": "user", "content": "hello"}]


def _cassette(tmp_path: Path, blob: dict[str, object]) -> Path:
    path = tmp_path / "c.json"
    path.write_text(json.dumps(blob), encoding="utf-8")
    return path


# ------------------------------------------------------------------------------ mock


def test_the_mock_is_deterministic_for_the_same_prompt() -> None:
    first = MockProvider().complete(MESSAGES).text
    second = MockProvider().complete(MESSAGES).text
    assert first == second


def test_the_mock_can_be_pinned_to_one_action() -> None:
    provider = MockProvider(policy=Action.ESCALATE)
    assert "ACTION: ESCALATE" in provider.complete(MESSAGES).text


def test_the_mock_can_be_made_to_emit_unreadable_output() -> None:
    provider = MockProvider(policy=Action.ACT, unparseable_every=2)
    texts = [provider.complete(MESSAGES).text for _ in range(4)]
    assert sum("ACTION:" not in t for t in texts) == 2


def test_the_mock_emits_prose_in_freeform_mode() -> None:
    provider = MockProvider(policy=Action.ASK, freeform=True)
    text = provider.complete(MESSAGES).text
    assert "ACTION:" not in text
    assert "clarify" in text


# -------------------------------------------------------------------------- cassette


def test_a_cassette_without_declared_provenance_will_not_load(tmp_path: Path) -> None:
    path = _cassette(tmp_path, {"_meta": {"model": "x"}, "responses": {}})
    with pytest.raises(CassetteError, match=r"_meta.source must be one of"):
        CassetteProvider(path, mode="choice")


def test_a_cassette_claiming_an_invented_provenance_will_not_load(tmp_path: Path) -> None:
    path = _cassette(tmp_path, {"_meta": {"source": "vibes"}, "responses": {}})
    with pytest.raises(CassetteError, match=r"_meta.source"):
        CassetteProvider(path, mode="choice")


def test_a_cassette_with_no_meta_block_will_not_load(tmp_path: Path) -> None:
    path = _cassette(tmp_path, {"responses": {}})
    with pytest.raises(CassetteError, match=r"missing '_meta'"):
        CassetteProvider(path, mode="choice")


def test_a_missing_cassette_says_so(tmp_path: Path) -> None:
    with pytest.raises(CassetteError, match=r"cassette not found"):
        CassetteProvider(tmp_path / "nope.json", mode="choice")


def test_the_shipped_demo_cassette_declares_itself_synthetic() -> None:
    provider = CassetteProvider(DEMO_CASSETTE, mode="choice")
    assert provider.is_synthetic
    assert provider.model == "demo-synthetic-v1"
    assert "SYNTHETIC" in provider.meta["warning"]


def test_a_cassette_must_be_pointed_at_a_scenario_before_use() -> None:
    provider = CassetteProvider(DEMO_CASSETTE, mode="choice")
    with pytest.raises(CassetteError, match=r"set_scenario"):
        provider.complete(MESSAGES)


def test_a_cassette_miss_is_a_recorded_error_not_a_crash(tmp_path: Path) -> None:
    path = _cassette(tmp_path, {"_meta": {"source": "synthetic"}, "responses": {}})
    provider = CassetteProvider(path, mode="choice")
    provider.set_scenario("absent")
    completion = provider.complete(MESSAGES)
    assert completion.error is not None
    assert completion.text == ""


# ----------------------------------------------------------------------------- cache


def test_the_cache_round_trips_a_completion(tmp_path: Path) -> None:
    cache = ResponseCache.create(tmp_path)
    key = cache_key("mock", "m", Params(), MESSAGES)
    assert cache.get(key) is None
    cache.put(key, Completion(text="hello", prompt_tokens=3, completion_tokens=1))
    got = cache.get(key)
    assert got is not None and got.text == "hello"
    assert cache.stats() == {"hits": 1, "misses": 1}


def test_the_cache_key_changes_with_every_input_that_matters(tmp_path: Path) -> None:
    base = cache_key("mock", "m", Params(), MESSAGES)
    assert base != cache_key("other", "m", Params(), MESSAGES)
    assert base != cache_key("mock", "n", Params(), MESSAGES)
    assert base != cache_key("mock", "m", Params(temperature=0.7), MESSAGES)
    assert base != cache_key("mock", "m", Params(), [{"role": "user", "content": "bye"}])
    assert base == cache_key("mock", "m", Params(), MESSAGES)


def test_errors_are_never_cached(tmp_path: Path) -> None:
    """A transient failure must not become a permanent one."""
    cache = ResponseCache.create(tmp_path)
    key = cache_key("mock", "m", Params(), MESSAGES)
    cache.put(key, Completion(text="", error="503"))
    assert cache.get(key) is None


def test_a_disabled_cache_stores_nothing(tmp_path: Path) -> None:
    cache = ResponseCache.create(tmp_path, enabled=False)
    key = cache_key("mock", "m", Params(), MESSAGES)
    cache.put(key, Completion(text="hello"))
    assert cache.get(key) is None
    assert not list(tmp_path.iterdir())


def test_a_corrupt_cache_entry_is_a_miss_not_a_crash(tmp_path: Path) -> None:
    cache = ResponseCache.create(tmp_path)
    key = cache_key("mock", "m", Params(), MESSAGES)
    path = tmp_path / key[:2] / f"{key}.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert cache.get(key) is None


# ------------------------------------------------------------------------- helpers


def test_prompt_hash_is_stable_and_order_independent_within_a_message() -> None:
    a = prompt_sha256([{"role": "user", "content": "x"}])
    b = prompt_sha256([{"content": "x", "role": "user"}])
    assert a == b
    assert len(a) == 64


def test_token_estimate_is_never_zero() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100
