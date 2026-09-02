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
from knowwhen.score import EASReport

_UNSAFE_NOTE = (
    "Unsafe rate is **not** folded into EAS. A model can post a respectable EAS while "
    "choosing an actively harmful action on a meaningful fraction of items; that is "
    "exactly the failure an average would hide."
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
    blob["notes"] = notes
    return blob


def write_report(directory: Path | str, blob: dict[str, Any], markdown: str) -> None:
    directory = Path(directory)
    with (directory / "report.json").open("w", encoding="utf-8") as fh:
        json.dump(blob, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    with (directory / "report.md").open("w", encoding="utf-8") as fh:
        fh.write(markdown)


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
    return "\n".join(lines)
