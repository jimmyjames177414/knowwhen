"""Turn an :class:`~knowwhen.score.EASReport` into ``report.json`` and ``report.md``.

The markdown is written to be pasted into an issue or a PR without editing, which means
every number it prints carries its interval and its N on the same line. There is no
summary line, no badge, and no single headline figure — by design.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knowwhen.actions import ACTION_ORDER
from knowwhen.baselines import Baseline, beaten_by, indistinguishable_from
from knowwhen.score import EASReport

_UNSAFE_NOTE = (
    "Unsafe rate is **not** folded into EAS. A model can post a respectable EAS while "
    "choosing an actively harmful action on a meaningful fraction of items; that is "
    "exactly the failure an average would hide."
)

_BASELINE_NOTE = (
    "Baselines are not an appendix. A validity audit of agent-safety benchmarks "
    "([arXiv:2607.28685](https://arxiv.org/abs/2607.28685)) found a trivial "
    "always-positive policy beating five of twenty-one real models on R-Judge, so a "
    "benchmark that does not print its constants alongside its models is not showing "
    "you enough to judge it. Every baseline below is scored over **the same items**, "
    "with the same scorer."
)


def build_report(
    report: EASReport,
    *,
    experiment_id: str,
    model: str,
    provider: str,
    mode: str,
    determinism: str,
    dataset_version: str,
    synthetic: bool,
    baselines: tuple[Baseline, ...] = (),
    notes: str = "",
) -> dict[str, Any]:
    """Assemble ``report.json``."""
    blob = report.as_dict()
    blob["experiment_id"] = experiment_id
    blob["model"] = model
    blob["provider"] = provider
    blob["elicitation_mode"] = mode
    blob["determinism"] = determinism
    blob["dataset_version"] = dataset_version
    blob["synthetic"] = synthetic
    blob["baselines"] = [b.as_dict() for b in baselines]
    blob["baselines_beating_model"] = list(beaten_by(report, baselines))
    blob["baselines_within_mde"] = list(indistinguishable_from(report, baselines))
    blob["notes"] = notes
    return blob


def write_report(directory: Path | str, blob: dict[str, Any], markdown: str) -> None:
    directory = Path(directory)
    with (directory / "report.json").open("w", encoding="utf-8") as fh:
        json.dump(blob, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with (directory / "report.md").open("w", encoding="utf-8") as fh:
        fh.write(markdown)


def _interval(blob: dict[str, Any] | None, *, percent: bool = False) -> str:
    """Render a serialised interval. Never collapses to the point estimate alone."""
    if blob is None:
        return "n/a"
    scale, suffix, places = (100.0, "%", 1) if percent else (1.0, "", 3)
    return (
        f"{blob['point'] * scale:.{places}f}{suffix} "
        f"[{blob['low'] * scale:.{places}f}, {blob['high'] * scale:.{places}f}]"
    )


def _rate(interval: Any) -> str:
    return interval.format(percent=True, places=1) if interval is not None else "n/a"


def render_markdown(report: EASReport, blob: dict[str, Any]) -> str:
    """Human-readable report. Three numbers, three denominators, never combined."""
    lines: list[str] = []
    add = lines.append

    add(f"# knowwhen run `{blob['experiment_id']}`")
    add("")
    if blob.get("synthetic"):
        add(
            "> **SYNTHETIC RUN.** The responses scored below were replayed or generated "
            "offline, not produced by a model exercising judgement. This demonstrates "
            "the pipeline. It measures nothing about any model and must never be quoted "
            "as a result."
        )
        add("")
    add(f"- model: `{blob['model']}` via `{blob['provider']}`")
    add(f"- elicitation mode: `{blob['elicitation_mode']}`")
    add(f"- determinism: `{blob['determinism']}`")
    add(f"- dataset: `{blob['dataset_version']}` sha256 `{report.dataset_sha256[:16]}…`")
    add("")

    add("## The three numbers")
    add("")
    add("| Metric | Value (95% CI) | Denominator |")
    add("|---|---|---|")
    add(
        f"| **EAS** | {report.eas.format()} | "
        f"{report.n_items_scored} items x {report.repeats} repeats |"
    )
    if report.unsafe_rate is not None:
        add(
            f"| **Unsafe rate** | {report.unsafe_rate.format(percent=True, places=1)} | "
            f"{report.n_items_unsafe_eligible} items with an unsafe action |"
        )
    else:
        add("| **Unsafe rate** | n/a | no item in this subset has an unsafe action |")
    if report.over_caution_rate is not None:
        add(
            f"| **Over-caution rate** | "
            f"{report.over_caution_rate.format(percent=True, places=1)} | "
            f"{report.n_items_benign} benign controls |"
        )
    else:
        add("| **Over-caution rate** | n/a | no benign controls in this subset |")
    add("")
    add(_UNSAFE_NOTE)
    add("")

    beaten = list(blob.get("baselines_beating_model") or [])
    within = list(blob.get("baselines_within_mde") or [])
    baselines = list(blob.get("baselines") or [])
    if baselines:
        if beaten or within:
            add("## FINDING: this result is not clear of the degenerate baselines")
            add("")
        if beaten:
            add(
                f"`{blob['model']}` did not beat "
                + ", ".join(f"`{name}`" for name in beaten)
                + " on EAS. A policy with no model in it scoring at least as well is a "
                "result about this benchmark as much as about that model, and it is "
                "stated here rather than left for a reader to compute."
            )
            add("")
        if within:
            add(
                f"`{blob['model']}` beats "
                + ", ".join(f"`{name}`" for name in within)
                + f" by less than the minimum detectable effect ({report.mde_eas:.3f}), "
                "so on this item set that gap has not been shown to exist. Edging past a "
                "constant policy is not evidence of doing something a constant does not."
            )
            add("")
            add(
                "The over-caution column is where the difference should show, if there "
                "is one: a constant that never acts posts 100% there by construction."
            )
            add("")
        add("## Baselines")
        add("")
        add(_BASELINE_NOTE)
        add("")
        add("| Policy | EAS (95% CI) | Unsafe rate | Over-caution | |")
        add("|---|---|---|---|---|")
        add(
            f"| **{blob['model']}** | {report.eas.format()} | "
            f"{_rate(report.unsafe_rate)} | {_rate(report.over_caution_rate)} | |"
        )
        for entry in baselines:
            marker = " **>= model**" if entry["id"] in beaten else ""
            detail = f" ({entry['detail']})" if entry.get("detail") else ""
            add(
                f"| `{entry['id']}`{detail} | {_interval(entry['eas'])} | "
                f"{_interval(entry['unsafe_rate'], percent=True)} | "
                f"{_interval(entry['over_caution_rate'], percent=True)} |{marker} |"
            )
        add("")
        add(
            "`always-ASK` is the row to look at when a model's caution looks impressive: "
            "it posts a 0% unsafe rate and a 100% over-caution rate, because refusing to "
            "do anything is perfectly safe and perfectly useless. `majority-class` is the "
            "constant an adversary would pick, chosen with the answer key in hand."
        )
        add("")

    add("## Parseability")
    add("")
    add(
        f"- unparseable trials: {report.n_trials_unparseable} / {report.n_trials} "
        f"({report.unparseable_rate * 100:.1f}%)"
    )
    add(
        f"- items with no parseable repeat at all: {report.n_items_all_unparseable} "
        f"(excluded from EAS, **not** scored zero)"
    )
    add("")

    add("## Power")
    add("")
    if report.mde_eas != report.mde_eas:  # NaN
        add("- MDE: undefined below two items.")
    else:
        add(
            f"- Minimum detectable EAS difference at n={report.n_items_scored}, "
            f"alpha=0.05, power=0.80: **{report.mde_eas:.3f}**. A gap smaller than this "
            "is not evidence of a difference, it is an underpowered comparison. The "
            "figure assumes uncorrelated runs, so it is a ceiling."
        )
    add("")

    add("## Action distribution")
    add("")
    add("| Action | Trials |")
    add("|---|---|")
    for action in ACTION_ORDER:
        add(f"| {action.value} | {report.action_counts.get(action, 0)} |")
    add(f"| (unparseable) | {report.n_trials_unparseable} |")
    add("")

    add("## By scenario type")
    add("")
    add("| Type | Items | EAS | Unsafe rate | Unsafe-eligible items |")
    add("|---|---|---|---|---|")
    for breakdown in report.per_type:
        unsafe = (
            f"{breakdown.unsafe_rate * 100:.1f}%" if breakdown.unsafe_rate is not None else "n/a"
        )
        eas = f"{breakdown.eas:.3f}" if breakdown.eas is not None else "n/a"
        add(
            f"| `{breakdown.scenario_type}` | {breakdown.n_items} | {eas} | {unsafe} | "
            f"{breakdown.n_items_unsafe_eligible} |"
        )
    add("")
    add(
        "Per-type rows carry no interval. Each type holds five to twelve items, which is "
        "too few for a bootstrap to say anything honest; read them as description, not "
        "as evidence."
    )
    add("")
    if blob.get("notes"):
        add("## Notes")
        add("")
        add(str(blob["notes"]))
        add("")

    return "\n".join(lines)


def render_terminal(report: EASReport, blob: dict[str, Any]) -> str:
    """Compact stdout summary. Same three numbers, same denominators."""
    lines: list[str] = []
    add = lines.append
    if blob.get("synthetic"):
        add("SYNTHETIC RUN - offline responses, measures nothing about any model")
    add(f"model            {blob['model']}  ({blob['provider']}, mode={blob['elicitation_mode']})")
    add(f"dataset          {blob['dataset_version']} sha256={report.dataset_sha256[:16]}...")
    add("")
    add(f"EAS              {report.eas.format()}   n={report.n_items_scored} items")
    if report.unsafe_rate is not None:
        add(
            f"unsafe rate      {report.unsafe_rate.format(percent=True, places=1)}   "
            f"n={report.n_items_unsafe_eligible} items with an unsafe action"
        )
    else:
        add("unsafe rate      n/a   no item in this subset has an unsafe action")
    if report.over_caution_rate is not None:
        add(
            f"over-caution     {report.over_caution_rate.format(percent=True, places=1)}   "
            f"n={report.n_items_benign} benign controls"
        )
    else:
        add("over-caution     n/a   no benign controls in this subset")
    add("")
    add(
        f"unparseable      {report.n_trials_unparseable}/{report.n_trials} trials "
        f"({report.unparseable_rate * 100:.1f}%) - reported, never scored 0"
    )
    add(f"MDE (EAS)        {report.mde_eas:.3f}   alpha=0.05 power=0.80, ceiling")
    add(f"repeats          {report.repeats}   determinism={blob['determinism']}")

    baselines = list(blob.get("baselines") or [])
    if baselines:
        beaten = set(blob.get("baselines_beating_model") or [])
        within = set(blob.get("baselines_within_mde") or [])
        add("")
        add("baselines        same items, same scorer   EAS / unsafe / over-caution")
        for entry in baselines:
            if entry["id"] in beaten:
                marker = "  <-- >= model"
            elif entry["id"] in within:
                marker = "  <-- within MDE of model"
            else:
                marker = ""
            add(
                f"  {entry['id']:<16} {entry['eas']['point']:.3f}   "
                f"{_pct(entry['unsafe_rate'])}   {_pct(entry['over_caution_rate'])}{marker}"
            )
        if beaten or within:
            add("")
            add(f"FINDING: {blob['model']} is not clear of the degenerate baselines.")
            add("         See report.md. A gap under the MDE is not a demonstrated gap.")
    return "\n".join(lines)


def _pct(blob: dict[str, Any] | None) -> str:
    return f"{blob['point'] * 100:5.1f}%" if blob is not None else "  n/a"
