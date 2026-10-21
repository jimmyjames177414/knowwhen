# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Changes to the **scenario set** are called out separately, because they change the dataset
hash and therefore make earlier results incomparable.

## [Unreleased]

### Fixed

- `new_experiment_id()` is now monotonic within a process. Ids made in the same
  millisecond used to sort by their random tail rather than in the order they were made,
  which broke the "time-sortable" promise and made
  `test_experiment_ids_are_unique_and_time_sortable` fail about one run in six. The id
  format is unchanged.
- README, `docs/validity.md` and `docs/leaderboard.md`: 0.11 is no longer called the
  smallest difference the set can detect. It is the
  minimum detectable difference on the demo run's spread, an upper bound, and each run
  prints its own. The demo block's run id is refreshed; the rest of the block still
  matches the command's output.

## [0.1.0] - 2026-09-02

First release.

### Added

- 120 hand-written scenarios across 14 types: 90 risky or ambiguous, 30 benign
  controls. Each carries a credit vector over the six action classes, an unsafe set, a
  scenario-type tag and a rationale. Provenance and an honest contamination statement in
  `PROVENANCE.md`. Dataset sha256
  `3456f3bc96de437a05242bb13ad15a011442ee8f206f2bd18350076d5794ea5f`.
- The Epistemic Action Score (EAS): a cost-sensitive multi-class scoring rule with
  partial credit over a substitutability structure. Reported alongside, and never folded
  into, the unsafe rate and the over-caution rate, each with its own denominator.
  Deliberately *not* named after "decision calibration", which is a formally defined
  property from Zhao et al., NeurIPS 2021 (arXiv:2107.05719) and would have been both a
  name collision and a technical misdescription.
- Eight degenerate baselines, reported in the same table as the model on every run:
  a constant per action class, `random-uniform` as an exact expectation, and
  `majority-class`. `knowwhen baselines` prints them standalone. A submission that does
  not carry them is rejected.
- Six action classes: ACT, ASK, VERIFY, SIMULATE, ESCALATE, ABSTAIN. The taxonomy is
  AgentAtlas's (arXiv:2605.20530); VERIFY and SIMULATE are added here.
- Two elicitation modes: `choice` (explicit six-way menu, deterministic parse) and
  `freeform` (tools on the table, first move classified by an auditable rule cascade).
- Unparseable handling. Responses no parser can read are reported as their own rate,
  excluded from every denominator, and written with `score: null`. Never scored zero.
- Providers: OpenAI-compatible HTTP as the base case, plus offline `mock` and
  `cassette`. A cassette must declare whether its contents are recorded or synthetic or it
  will not load.
- CXS v0.1 output: `manifest.json`, `interventions.json`, append-only `trials.jsonl`,
  `outcomes.jsonl`, `report.json`, `report.md`. Schemas vendored under `schemas/` with a
  conformance test that validates a real run.
- Statistics: 95% percentile bootstrap over items, N reported everywhere, and an MDE
  so a null result is distinguishable from an underpowered one.
- `knowwhen submit`, which validates a run and produces a reviewable submission. Rejects
  mocked and replayed runs, truncated runs, missing intervals, unknown action classes and
  results with nobody's name attached.
- CLI: `list`, `validate`, `run`, `report`, `submit`, with `--dry-run`, `--max-calls`,
  content-addressed caching, and resume after a crash.
- An offline demo. A synthetic cassette generated from a committed policy file, so the
  whole pipeline runs with no API key.

### Notes

- The model leaderboard is empty. No model has been run and no result is claimed. An
  empty table is the correct state until somebody submits one. The baseline rows *are*
  published, because a baseline is arithmetic over the dataset rather than a claim about
  anybody's system.
- **`always-VERIFY` scores EAS 0.782 on this set**, because VERIFY is optimal on 54 of 120
  items. Any model must clear that by more than the MDE before its EAS means anything. This
  is a real weakness of the v1 item distribution and is documented rather than rebalanced
  away; a v2 that lowers the bar without lowering realism is a `help-wanted` issue.
- `choice` mode measures a proxy for agent behaviour, the freeform mapper's accuracy on
  real model output is unmeasured, and 120 items is a modest N. All three are stated in
  the README and argued in `docs/validity.md`.
