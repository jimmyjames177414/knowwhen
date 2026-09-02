"""Run a scenario set against a provider and write CXS-conformant files.

The on-disk layout is fixed by ``CONTEXT-SPEC-v0.1.md``::

    results/<experiment_id>/
      manifest.json        RunManifest
      interventions.json   [Intervention]
      trials.jsonl         one Trial per line, append-only, never rewritten
      outcomes.jsonl       one Outcome per line
      report.json          aggregated + statistics
      report.md            human-readable

``trials.jsonl`` being append-only is what makes a run resumable after a crash and
re-scorable without re-calling the model.
"""

from __future__ import annotations

import json
import secrets
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowwhen import CXS_VERSION, SCORER_ID, __version__
from knowwhen.cache import ResponseCache
from knowwhen.elicit import Mode, build_choice_prompt, build_freeform_prompt
from knowwhen.elicit.choice import parse_choice
from knowwhen.elicit.freeform import explain_freeform
from knowwhen.providers.base import (
    Completion,
    Message,
    ModelDescriptor,
    Provider,
    cache_key,
    estimate_tokens,
    prompt_sha256,
)
from knowwhen.scenarios import Scenario, ScenarioSet
from knowwhen.score import Judgement, judge

_B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: knowwhen presents every scenario exactly as authored. In CXS terms that is the control
#: arm and the only arm, which is why no intervention effect is reported anywhere.
NOOP_INTERVENTION: dict[str, Any] = {
    "id": "as-authored",
    "kind": "noop",
    "selector": {"type": "none", "value": None},
    "description": "The scenario is presented unmodified. knowwhen runs a control arm only.",
    "deterministic": True,
    "implementation": "knowwhen.runner:as-authored:v1",
}


def new_experiment_id() -> str:
    """Time-sortable 26-character id, ULID-shaped without taking a dependency for it."""
    ms = int(time.time() * 1000)
    time_part = "".join(_B32[(ms >> shift) & 0x1F] for shift in range(45, -1, -5))
    rand_part = "".join(_B32[secrets.randbelow(32)] for _ in range(16))
    return time_part + rand_part


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class DryRun:
    """What a run would cost, computed without contacting anything."""

    model_calls: int
    cached_calls: int
    prompt_tokens_estimate: int
    n_items: int
    repeats: int
    mode: Mode

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_calls": self.model_calls,
            "cached_calls": self.cached_calls,
            "prompt_tokens_estimate": self.prompt_tokens_estimate,
            "n_items": self.n_items,
            "repeats": self.repeats,
            "mode": self.mode,
            "note": "prompt_tokens_estimate is chars/4, an estimate, not a measurement",
        }


@dataclass(frozen=True, slots=True)
class RunResult:
    """Everything a caller needs after a run, without re-reading the directory."""

    experiment_id: str
    directory: Path
    judgements: list[Judgement]
    scenario_set: ScenarioSet
    repeats: int
    mode: Mode
    determinism: str
    truncated: bool
    n_model_calls: int
    cache_stats: dict[str, int]


def build_prompt(scenario: Scenario, mode: Mode) -> list[Message]:
    if mode == "choice":
        return build_choice_prompt(scenario)
    return build_freeform_prompt(scenario)


def plan_dry_run(
    scenario_set: ScenarioSet,
    *,
    mode: Mode,
    repeats: int,
    provider_name: str,
    model: str,
    params: Any,
    cache: ResponseCache,
) -> DryRun:
    """Count the calls a run would make. Consults the cache, contacts no model."""
    model_calls = 0
    cached = 0
    tokens = 0
    for scenario in scenario_set.scenarios:
        messages = build_prompt(scenario, mode)
        tokens += estimate_tokens("".join(m["content"] for m in messages)) * repeats
        key = cache_key(provider_name, model, params, messages)
        for _ in range(repeats):
            if cache.enabled and cache.get(key) is not None:
                cached += 1
            else:
                model_calls += 1
    # plan_dry_run's probes are accounting, not real traffic; do not let them pollute the
    # hit/miss counters the manifest reports.
    cache.hits = 0
    cache.misses = 0
    return DryRun(
        model_calls=model_calls,
        cached_calls=cached,
        prompt_tokens_estimate=tokens,
        n_items=len(scenario_set),
        repeats=repeats,
        mode=mode,
    )


def _existing_trials(path: Path) -> tuple[list[dict[str, Any]], set[tuple[str, int]]]:
    """Read an interrupted run's trials so it can be resumed rather than repeated."""
    if not path.exists():
        return [], set()
    rows: list[dict[str, Any]] = []
    done: set[tuple[str, int]] = set()
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            rows.append(row)
            done.add((str(row.get("item_id")), int(row.get("repeat_index", 0))))
    return rows, done


def _judge_trial(scenario: Scenario, text: str, mode: Mode, repeat_index: int) -> Judgement:
    if mode == "choice":
        action = parse_choice(text)
        detail = "choice-parse"
    else:
        mapped = explain_freeform(text, scenario)
        action = mapped.action
        detail = f"mapper:{mapped.rule}"
    return judge(scenario, action, repeat_index=repeat_index, detail=detail)


def _determinism(rows: list[dict[str, Any]], repeats: int) -> str:
    """``deterministic`` only when identical outputs were actually observed.

    With one repeat there is nothing to compare, so the answer is ``stochastic``. CXS
    forbids claiming determinism you have not seen.
    """
    if repeats < 2:
        return "stochastic"
    by_item: dict[str, set[str]] = {}
    for row in rows:
        by_item.setdefault(str(row.get("item_id")), set()).add(str(row.get("response_text", "")))
    return "deterministic" if all(len(v) == 1 for v in by_item.values()) else "stochastic"


def run(
    scenario_set: ScenarioSet,
    provider: Provider,
    *,
    mode: Mode = "choice",
    repeats: int = 1,
    out_dir: Path | str = "results",
    cache: ResponseCache | None = None,
    max_calls: int | None = None,
    seed: int = 7,
    experiment_id: str | None = None,
    notes: str = "",
    on_progress: Callable[[int, int, str], None] | None = None,
) -> RunResult:
    """Execute a run and write the CXS files. Returns everything needed to report."""
    cache = cache or ResponseCache.create(enabled=False)
    experiment_id = experiment_id or new_experiment_id()
    directory = Path(out_dir) / experiment_id
    directory.mkdir(parents=True, exist_ok=True)

    trials_path = directory / "trials.jsonl"
    rows, already_done = _existing_trials(trials_path)

    descriptor: ModelDescriptor = provider.descriptor()  # type: ignore[attr-defined]
    model_calls = 0
    truncated = False
    total = len(scenario_set) * repeats
    completed = len(already_done)

    with trials_path.open("a", encoding="utf-8") as trials_fh:
        for scenario in scenario_set.scenarios:
            messages = build_prompt(scenario, mode)
            key = cache_key(provider.name, provider.model, provider.params, messages)
            sha = prompt_sha256(messages)
            for repeat_index in range(repeats):
                if (scenario.id, repeat_index) in already_done:
                    continue
                if max_calls is not None and model_calls >= max_calls:
                    truncated = True
                    break

                cached = cache.get(key)
                if cached is not None:
                    completion: Completion = cached
                    from_cache = True
                else:
                    setter = getattr(provider, "set_scenario", None)
                    if callable(setter):
                        setter(scenario.id)
                    completion = provider.complete(messages)
                    model_calls += 1
                    from_cache = False
                    cache.put(key, completion)

                row: dict[str, Any] = {
                    "trial_id": f"{experiment_id}-{scenario.id}-{repeat_index}",
                    "experiment_id": experiment_id,
                    "intervention_id": NOOP_INTERVENTION["id"],
                    "item_id": scenario.id,
                    "repeat_index": repeat_index,
                    "model": descriptor.as_dict(),
                    "prompt_sha256": sha,
                    "response_text": completion.text,
                    "cached": from_cache,
                    "latency_ms": completion.latency_ms,
                    "usage": {
                        "prompt_tokens": completion.prompt_tokens,
                        "completion_tokens": completion.completion_tokens,
                    },
                    "error": completion.error,
                    "observed_at": _now(),
                }
                trials_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                trials_fh.flush()
                rows.append(row)
                completed += 1
                if on_progress is not None:
                    on_progress(completed, total, scenario.id)
            if truncated:
                break

    judgements = [
        _judge_trial(
            scenario_set.by_id(str(row["item_id"])),
            str(row.get("response_text", "")),
            mode,
            int(row.get("repeat_index", 0)),
        )
        for row in rows
    ]

    write_outcomes(directory, rows, judgements)

    determinism = _determinism(rows, repeats)
    write_manifest(
        directory,
        experiment_id=experiment_id,
        descriptor=descriptor,
        scenario_set=scenario_set,
        mode=mode,
        repeats=repeats,
        seed=seed,
        determinism=determinism,
        cache_stats=cache.stats(),
        model_calls=model_calls,
        rows=rows,
        notes=notes,
        truncated=truncated,
    )

    return RunResult(
        experiment_id=experiment_id,
        directory=directory,
        judgements=judgements,
        scenario_set=scenario_set,
        repeats=repeats,
        mode=mode,
        determinism=determinism,
        truncated=truncated,
        n_model_calls=model_calls,
        cache_stats=cache.stats(),
    )


def write_outcomes(
    directory: Path, rows: list[dict[str, Any]], judgements: list[Judgement]
) -> None:
    """Write one Outcome per Trial.

    An unparseable trial gets ``score: null`` and ``passed: null``, never ``0.0``. Zero is
    a real score meaning "the model chose the worst available action"; a parse failure is
    a statement about this tool, not about the model, and the file format has to keep the
    two apart.
    """
    path = directory / "outcomes.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row, judgement in zip(rows, judgements, strict=True):
            passed = judgement.credit == 1.0 if judgement.parse_status == "ok" else None
            fh.write(
                json.dumps(
                    {
                        "trial_id": row["trial_id"],
                        "scorer": SCORER_ID,
                        "score": judgement.credit,
                        "passed": passed,
                        "detail": {
                            "action": judgement.action.value if judgement.action else None,
                            "unsafe": judgement.unsafe,
                            "parse_status": judgement.parse_status,
                            "parser": judgement.detail,
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def write_manifest(
    directory: Path,
    *,
    experiment_id: str,
    descriptor: ModelDescriptor,
    scenario_set: ScenarioSet,
    mode: Mode,
    repeats: int,
    seed: int,
    determinism: str,
    cache_stats: dict[str, int],
    model_calls: int,
    rows: list[dict[str, Any]],
    notes: str,
    truncated: bool,
) -> None:
    """Write ``manifest.json`` and ``interventions.json``."""
    prompt_tokens = sum(int((r.get("usage") or {}).get("prompt_tokens") or 0) for r in rows)
    completion_tokens = sum(int((r.get("usage") or {}).get("completion_tokens") or 0) for r in rows)
    caveats = [notes] if notes else []
    if descriptor.provider == "cassette":
        caveats.append(
            "Responses were replayed from a cassette. 'determinism' describes the replay, "
            "not the model that produced (or did not produce) the text."
        )
    if truncated:
        caveats.append("Run stopped early by --max-calls; the item set is incomplete.")

    manifest = {
        "cxs_version": CXS_VERSION,
        "experiment_id": experiment_id,
        "tool": {"name": "knowwhen", "version": __version__},
        "created_at": _now(),
        "models": [descriptor.as_dict()],
        "interventions": [NOOP_INTERVENTION],
        "dataset": {
            "name": f"knowwhen-scenarios-{scenario_set.version}",
            "sha256": scenario_set.sha256,
            "n_items": len(scenario_set),
            "source": "https://github.com/jimmyjames177414/knowwhen",
        },
        "scorer": SCORER_ID,
        "repeats": repeats,
        "seed": seed,
        "determinism": determinism,
        "cache": {"hits": cache_stats.get("hits", 0), "misses": cache_stats.get("misses", 0)},
        "totals": {
            "model_calls": model_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
        "environment": {
            "python": ".".join(str(p) for p in sys.version_info[:3]),
            "platform": sys.platform,
        },
        "elicitation_mode": mode,
        "notes": " ".join(caveats),
    }
    _write_json(directory / "manifest.json", manifest)
    _write_json(directory / "interventions.json", [NOOP_INTERVENTION])


def _write_json(path: Path, blob: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(blob, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    tmp.replace(path)


def rescore(directory: Path | str, scenario_set: ScenarioSet, *, mode: Mode) -> list[Judgement]:
    """Re-derive judgements from ``trials.jsonl`` with no model calls.

    This is the point of keeping Trial and Outcome apart: a scorer change costs nothing to
    apply to a run that already happened.
    """
    rows, _ = _existing_trials(Path(directory) / "trials.jsonl")
    judgements = [
        _judge_trial(
            scenario_set.by_id(str(row["item_id"])),
            str(row.get("response_text", "")),
            mode,
            int(row.get("repeat_index", 0)),
        )
        for row in rows
    ]
    write_outcomes(Path(directory), rows, judgements)
    return judgements
