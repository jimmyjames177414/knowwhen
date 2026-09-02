"""``knowwhen`` command line.

    knowwhen list
    knowwhen validate
    knowwhen run --provider mock --mode choice --repeats 3
    knowwhen run --model qwen3:8b --base-url http://localhost:11434/v1 --dry-run
    knowwhen report results/<experiment_id>/
    knowwhen submit results/<experiment_id>/ --submitter "you"

argparse rather than click: one fewer dependency, and every option here is a plain flag.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from knowwhen import __version__
from knowwhen.actions import ACTION_ORDER, AGENTATLAS_MAPPING, DEFINITIONS
from knowwhen.cache import ResponseCache
from knowwhen.elicit import MODES, Mode
from knowwhen.providers import (
    PROVIDER_NAMES,
    CassetteError,
    CassetteProvider,
    MockProvider,
    OpenAICompatProvider,
    Params,
    Provider,
)
from knowwhen.report import build_report, render_markdown, render_terminal, write_report
from knowwhen.runner import plan_dry_run, rescore, run
from knowwhen.scenarios import SCENARIO_TYPES, ScenarioError, ScenarioSet, load_scenarios
from knowwhen.score import score_run
from knowwhen.submit import SubmissionError, build_submission, validate_run


def _add_scenario_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scenarios",
        metavar="DIR",
        default=None,
        help="scenario directory (default: the bundled v1 set)",
    )
    parser.add_argument(
        "--type",
        dest="types",
        action="append",
        choices=SCENARIO_TYPES,
        help="restrict to a scenario type; repeatable",
    )
    parser.add_argument(
        "--ids-file",
        metavar="PATH",
        default=None,
        help="file of scenario ids, one per line, to restrict the run to",
    )
    parser.add_argument("--limit", type=int, default=None, help="use only the first N scenarios")


def _load_set(args: argparse.Namespace) -> ScenarioSet:
    scenario_set = load_scenarios(args.scenarios)
    ids: tuple[str, ...] | None = None
    if getattr(args, "ids_file", None):
        raw = Path(args.ids_file).read_text(encoding="utf-8").splitlines()
        ids = tuple(line.strip() for line in raw if line.strip() and not line.startswith("#"))
    types = tuple(args.types) if getattr(args, "types", None) else None
    if types or ids or getattr(args, "limit", None):
        return scenario_set.filtered(types=types, ids=ids, limit=args.limit)
    return scenario_set


def _build_provider(args: argparse.Namespace) -> Provider:
    params = Params(
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
        seed=args.model_seed,
    )
    if args.provider == "mock":
        return cast(
            Provider,
            MockProvider(params=params, freeform=args.mode == "freeform"),
        )
    if args.provider == "cassette":
        if not args.cassette:
            raise SystemExit("--cassette PATH is required with --provider cassette")
        return cast(Provider, CassetteProvider(args.cassette, mode=args.mode, params=params))
    if not args.base_url:
        raise SystemExit("--base-url is required with --provider openai-compatible")
    return cast(
        Provider,
        OpenAICompatProvider(
            model=args.model,
            base_url=args.base_url,
            api_key_env=args.api_key_env,
            params=params,
        ),
    )


def cmd_list(args: argparse.Namespace) -> int:
    if args.definitions:
        print("The six epistemic action classes.")
        print(
            "Taxonomy source: AgentAtlas, arXiv:2605.20530 (2026-05-19). We did not "
            "invent it; VERIFY and SIMULATE are the two classes we add."
        )
        print()
        for action in ACTION_ORDER:
            print(f"  {action.value:<9} {DEFINITIONS[action]}")
            print(f"  {'':<9} AgentAtlas: {AGENTATLAS_MAPPING[action]}")
        return 0

    scenario_set = _load_set(args)
    if args.json:
        print(
            json.dumps(
                {
                    "version": scenario_set.version,
                    "sha256": scenario_set.sha256,
                    "n": len(scenario_set),
                    "scenarios": [s.canonical() for s in scenario_set.scenarios],
                },
                indent=2,
            )
        )
        return 0

    print(f"knowwhen scenarios {scenario_set.version}  sha256={scenario_set.sha256}")
    print(
        f"{len(scenario_set)} items: {len(scenario_set.risky)} risky/ambiguous, "
        f"{len(scenario_set.benign)} benign controls"
    )
    print()
    for scenario in scenario_set.scenarios:
        best = "/".join(a.value for a in scenario.best_actions)
        flag = "control" if scenario.benign else "risky  "
        print(f"  {scenario.id:<44} {flag}  {scenario.type:<24} best={best}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        scenario_set = load_scenarios(args.scenarios)
    except ScenarioError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    counts: dict[str, int] = {}
    for scenario in scenario_set.scenarios:
        counts[scenario.type] = counts.get(scenario.type, 0) + 1
    print(f"OK: {len(scenario_set)} scenarios, sha256={scenario_set.sha256}")
    print(f"    {len(scenario_set.risky)} risky, {len(scenario_set.benign)} benign controls")
    for scenario_type in SCENARIO_TYPES:
        print(f"    {scenario_type:<26} {counts.get(scenario_type, 0)}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    scenario_set = _load_set(args)
    mode = cast(Mode, args.mode)
    cache = ResponseCache.create(args.cache_dir, enabled=not args.no_cache)

    if args.dry_run:
        params = Params(
            temperature=args.temperature,
            top_p=args.top_p,
            max_tokens=args.max_tokens,
            seed=args.model_seed,
        )
        plan = plan_dry_run(
            scenario_set,
            mode=mode,
            repeats=args.repeats,
            provider_name=args.provider,
            model=args.model,
            params=params,
            cache=cache,
        )
        print(json.dumps(plan.as_dict(), indent=2))
        return 0

    try:
        provider = _build_provider(args)
    except CassetteError as exc:
        print(f"cassette error: {exc}", file=sys.stderr)
        return 1

    synthetic = getattr(provider, "is_synthetic", False) or provider.name == "mock"

    def progress(done: int, total: int, scenario_id: str) -> None:
        if not args.quiet:
            print(f"\r[{done}/{total}] {scenario_id[:48]:<48}", end="", file=sys.stderr)

    result = run(
        scenario_set,
        provider,
        mode=mode,
        repeats=args.repeats,
        out_dir=args.out,
        cache=cache,
        max_calls=args.max_calls,
        seed=args.seed,
        on_progress=progress,
    )
    if not args.quiet:
        print("", file=sys.stderr)

    report = score_run(
        result.judgements,
        scenario_set,
        repeats=args.repeats,
        resamples=args.resamples,
        seed=args.seed,
    )
    blob = build_report(
        report,
        experiment_id=result.experiment_id,
        model=provider.model,
        provider=provider.name,
        mode=mode,
        determinism=result.determinism,
        dataset_version=scenario_set.version,
        synthetic=bool(synthetic),
        notes=(
            "Synthetic or replayed responses: this run demonstrates the pipeline and "
            "measures nothing about any model."
            if synthetic
            else ""
        ),
    )
    write_report(result.directory, blob, render_markdown(report, blob))
    print(render_terminal(report, blob))
    print()
    print(f"written to {result.directory}")
    if result.truncated:
        print("WARNING: run stopped early by --max-calls; the item set is incomplete")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        print(f"no manifest.json in {directory}", file=sys.stderr)
        return 1
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))

    if not args.rescore:
        report_path = directory / "report.md"
        if report_path.exists():
            print(report_path.read_text(encoding="utf-8"), end="")
            return 0

    scenario_set = load_scenarios(args.scenarios)
    mode = cast(Mode, manifest.get("elicitation_mode", "choice"))
    ids = tuple(
        json.loads(line)["item_id"]
        for line in (directory / "trials.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    subset = scenario_set.filtered(ids=tuple(dict.fromkeys(ids)))
    judgements = rescore(directory, subset, mode=mode)
    report = score_run(
        judgements, subset, repeats=int(manifest.get("repeats", 1)), resamples=args.resamples
    )
    model = manifest["models"][0]
    blob = build_report(
        report,
        experiment_id=str(manifest["experiment_id"]),
        model=str(model.get("model")),
        provider=str(model.get("provider")),
        mode=mode,
        determinism=str(manifest.get("determinism", "stochastic")),
        dataset_version=str(manifest["dataset"]["name"]).rsplit("-", 1)[-1],
        synthetic=str(model.get("provider")) in {"cassette", "mock"},
        notes=str(manifest.get("notes", "")),
    )
    markdown = render_markdown(report, blob)
    write_report(directory, blob, markdown)
    print(markdown, end="")
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    if args.check_only:
        check = validate_run(directory)
        if check.ok:
            print("OK: this run can be submitted")
            return 0
        for problem in check.problems:
            print(f"REJECTED: {problem}", file=sys.stderr)
        return 1
    try:
        submission = build_submission(
            directory,
            submitter=args.submitter or "",
            evidence_url=args.evidence_url,
            note=args.note,
        )
    except SubmissionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    blob = json.dumps(submission, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(blob, encoding="utf-8")
        print(f"written to {args.out}")
    else:
        print(blob, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="knowwhen",
        description="Benchmark whether an agent should have started, not whether it finished.",
    )
    parser.add_argument("--version", action="version", version=f"knowwhen {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list scenarios, or the six action definitions")
    _add_scenario_flags(p_list)
    p_list.add_argument("--json", action="store_true", help="machine-readable output")
    p_list.add_argument(
        "--definitions", action="store_true", help="print the six classes and their provenance"
    )
    p_list.set_defaults(func=cmd_list)

    p_validate = sub.add_parser("validate", help="validate a scenario set and print its hash")
    p_validate.add_argument("--scenarios", metavar="DIR", default=None)
    p_validate.set_defaults(func=cmd_validate)

    p_run = sub.add_parser("run", help="run the benchmark against a provider")
    _add_scenario_flags(p_run)
    p_run.add_argument("--provider", choices=PROVIDER_NAMES, default="openai-compatible")
    p_run.add_argument("--model", default="unspecified", help="model id sent to the provider")
    p_run.add_argument("--base-url", default=None, help="OpenAI-compatible base URL")
    p_run.add_argument(
        "--api-key-env",
        default="KNOWWHEN_API_KEY",
        help="environment variable holding the API key (never pass the key itself)",
    )
    p_run.add_argument("--cassette", default=None, help="cassette JSON, with --provider cassette")
    p_run.add_argument("--mode", choices=MODES, default="choice")
    p_run.add_argument("--repeats", type=int, default=1)
    p_run.add_argument("--temperature", type=float, default=0.0)
    p_run.add_argument("--top-p", type=float, default=1.0)
    p_run.add_argument("--max-tokens", type=int, default=512)
    p_run.add_argument(
        "--model-seed", type=int, default=None, help="seed passed to the provider, if it honours it"
    )
    p_run.add_argument("--seed", type=int, default=7, help="seed for the bootstrap, not the model")
    p_run.add_argument("--resamples", type=int, default=10_000)
    p_run.add_argument("--out", default="results", help="results root directory")
    p_run.add_argument("--cache-dir", default=None)
    p_run.add_argument("--no-cache", action="store_true")
    p_run.add_argument("--max-calls", type=int, default=None, help="hard stop after N model calls")
    p_run.add_argument(
        "--dry-run", action="store_true", help="print the call count and token estimate, then exit"
    )
    p_run.add_argument("--quiet", action="store_true")
    p_run.set_defaults(func=cmd_run)

    p_report = sub.add_parser("report", help="print the report for a results directory")
    p_report.add_argument("directory")
    p_report.add_argument("--scenarios", metavar="DIR", default=None)
    p_report.add_argument(
        "--rescore",
        action="store_true",
        help="re-derive outcomes from trials.jsonl without calling any model",
    )
    p_report.add_argument("--resamples", type=int, default=10_000)
    p_report.set_defaults(func=cmd_report)

    p_submit = sub.add_parser("submit", help="validate a run and emit a submission file")
    p_submit.add_argument("directory")
    p_submit.add_argument("--submitter", default=None, help="who ran it; required")
    p_submit.add_argument("--evidence-url", default=None, help="link to logs or a write-up")
    p_submit.add_argument("--note", default="")
    p_submit.add_argument("--out", default=None, help="write the submission JSON here")
    p_submit.add_argument(
        "--check-only", action="store_true", help="validate without producing a submission"
    )
    p_submit.set_defaults(func=cmd_submit)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ScenarioError as exc:
        print(f"scenario error: {exc}", file=sys.stderr)
        return 1
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
