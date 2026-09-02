"""The command line, end to end, with no network and no key."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowwhen.cli import main
from tests.conftest import DEMO_CASSETTE


def test_list_prints_every_scenario(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "120 items: 90 risky/ambiguous, 30 benign controls" in out
    assert "drop-old-analytics-database" in out


def test_list_json_is_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "--json"]) == 0
    blob = json.loads(capsys.readouterr().out)
    assert blob["n"] == 120
    assert len(blob["sha256"]) == 64
    assert blob["scenarios"][0]["credit"]


def test_list_can_filter_by_type(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "--type", "false_premise", "--json"]) == 0
    blob = json.loads(capsys.readouterr().out)
    assert blob["n"] == 5


def test_list_definitions_names_its_source(capsys: pytest.CaptureFixture[str]) -> None:
    """The taxonomy is not ours and the CLI says so without being asked."""
    assert main(["list", "--definitions"]) == 0
    out = capsys.readouterr().out
    assert "AgentAtlas" in out
    assert "arXiv:2605.20530" in out
    assert "not in AgentAtlas (added here)" in out
    for name in ("ACT", "ASK", "VERIFY", "SIMULATE", "ESCALATE", "ABSTAIN"):
        assert name in out


def test_validate_reports_the_hash(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("OK: 120 scenarios, sha256=")


def test_validate_fails_loudly_on_a_broken_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "_tools.yaml").write_text("tools: []\n", encoding="utf-8")
    (tmp_path / "items.yaml").write_text("scenarios: []\n", encoding="utf-8")
    assert main(["validate", "--scenarios", str(tmp_path)]) == 1
    assert "INVALID" in capsys.readouterr().err


def test_dry_run_reports_cost_without_calling_anything(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert (
        main(
            [
                "run",
                "--provider",
                "mock",
                "--repeats",
                "3",
                "--dry-run",
                "--cache-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    blob = json.loads(capsys.readouterr().out)
    assert blob["model_calls"] == 360
    assert blob["n_items"] == 120
    assert blob["repeats"] == 3
    assert "estimate, not a measurement" in blob["note"]


def test_max_calls_stops_the_run(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = main(
        [
            "run",
            "--provider",
            "mock",
            "--max-calls",
            "5",
            "--no-cache",
            "--quiet",
            "--out",
            str(tmp_path),
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "WARNING: run stopped early" in out
    run_dir = next(tmp_path.iterdir())
    trials = [
        line for line in (run_dir / "trials.jsonl").read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(trials) == 5


def test_a_full_cassette_run_reports_three_separate_numbers(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = main(
        [
            "run",
            "--provider",
            "cassette",
            "--cassette",
            str(DEMO_CASSETTE),
            "--mode",
            "choice",
            "--no-cache",
            "--quiet",
            "--resamples",
            "500",
            "--out",
            str(tmp_path),
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "SYNTHETIC RUN" in out
    assert "EAS " in out
    assert "unsafe rate" in out
    assert "over-caution" in out
    assert "unparseable" in out
    # Three numbers on three lines, each with its own denominator.
    assert out.count("n=") >= 3


def test_report_prints_the_written_markdown(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    main(
        [
            "run",
            "--provider",
            "mock",
            "--limit",
            "12",
            "--no-cache",
            "--quiet",
            "--resamples",
            "200",
            "--out",
            str(tmp_path),
        ]
    )
    capsys.readouterr()
    run_dir = next(tmp_path.iterdir())
    assert main(["report", str(run_dir)]) == 0
    out = capsys.readouterr().out
    assert "## The three numbers" in out
    assert "**Unsafe rate**" in out
    assert "**Over-caution rate**" in out
    assert "not** folded into EAS" in out


def test_report_can_rescore_without_calling_a_model(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    main(
        [
            "run",
            "--provider",
            "mock",
            "--limit",
            "12",
            "--no-cache",
            "--quiet",
            "--resamples",
            "200",
            "--out",
            str(tmp_path),
        ]
    )
    capsys.readouterr()
    run_dir = next(tmp_path.iterdir())
    (run_dir / "report.md").unlink()
    assert main(["report", str(run_dir), "--rescore", "--resamples", "200"]) == 0
    assert "## The three numbers" in capsys.readouterr().out
    assert (run_dir / "report.md").exists()


def test_report_on_a_directory_with_no_manifest_fails(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert main(["report", str(tmp_path)]) == 1
    assert "no manifest.json" in capsys.readouterr().err


def test_submit_refuses_a_synthetic_run(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    main(
        [
            "run",
            "--provider",
            "cassette",
            "--cassette",
            str(DEMO_CASSETTE),
            "--limit",
            "12",
            "--no-cache",
            "--quiet",
            "--resamples",
            "200",
            "--out",
            str(tmp_path),
        ]
    )
    capsys.readouterr()
    run_dir = next(tmp_path.iterdir())
    assert main(["submit", str(run_dir), "--submitter", "someone"]) == 1
    err = capsys.readouterr().err
    assert "not measurements" in err


def test_submit_check_only_reports_without_writing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    main(
        [
            "run",
            "--provider",
            "mock",
            "--limit",
            "12",
            "--no-cache",
            "--quiet",
            "--resamples",
            "200",
            "--out",
            str(tmp_path),
        ]
    )
    capsys.readouterr()
    run_dir = next(tmp_path.iterdir())
    assert main(["submit", str(run_dir), "--check-only"]) == 1
    assert "REJECTED" in capsys.readouterr().err


def test_ids_file_restricts_the_run(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    ids = tmp_path / "ids.txt"
    ids.write_text(
        "# a comment\ndrop-old-analytics-database\nbenign-list-buckets\n", encoding="utf-8"
    )
    assert main(["list", "--ids-file", str(ids), "--json"]) == 0
    blob = json.loads(capsys.readouterr().out)
    assert blob["n"] == 2


def test_cassette_provider_requires_a_cassette_path(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="--cassette"):
        main(["run", "--provider", "cassette", "--limit", "2", "--out", str(tmp_path)])


def test_openai_provider_requires_a_base_url(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="--base-url"):
        main(["run", "--limit", "2", "--out", str(tmp_path)])
