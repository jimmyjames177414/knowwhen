# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Changes to the **scenario set** are called out separately, because they change the dataset
hash and therefore make earlier results incomparable.

## [Unreleased]

## [0.1.0] — 2026-09-02

First release.

### Added

- **120 hand-written scenarios** across 14 types: 90 risky or ambiguous, 30 benign
  controls. Each carries a credit vector over the six action classes, an unsafe set, a
  scenario-type tag and a rationale. Provenance and an honest contamination statement in
  `PROVENANCE.md`. Dataset sha256
  `3456f3bc96de437a05242bb13ad15a011442ee8f206f2bd18350076d5794ea5f`.
- **The Epistemic Action Score (EAS)** — a cost-sensitive multi-class scoring rule with
  partial credit over a substitutability structure. Reported alongside, and never folded
  into, the **unsafe rate** and the **over-caution rate**, each with its own denominator.
- **Six action classes** — ACT, ASK, VERIFY, SIMULATE, ESCALATE, ABSTAIN. The taxonomy is
  AgentAtlas's (arXiv:2605.20530); VERIFY and SIMULATE are added here.
- **Two elicitation modes** — `choice` (explicit six-way menu, deterministic parse) and
  `freeform` (tools on the table, first move classified by an auditable rule cascade).
- **Unparseable handling** — responses no parser can read are reported as their own rate,
  excluded from every denominator, and written with `score: null`. Never scored zero.
- **Providers** — OpenAI-compatible HTTP as the base case, plus offline `mock` and
  `cassette`. A cassette must declare whether its contents are recorded or synthetic or it
  will not load.
- **CXS v0.1 output** — `manifest.json`, `interventions.json`, append-only `trials.jsonl`,
  `outcomes.jsonl`, `report.json`, `report.md`. Schemas vendored under `schemas/` with a
  conformance test that validates a real run.
- **Statistics** — 95% percentile bootstrap over items, N reported everywhere, and an MDE
  so a null result is distinguishable from an underpowered one.
- **`knowwhen submit`** — validates a run and produces a reviewable submission. Rejects
  mocked and replayed runs, truncated runs, missing intervals, unknown action classes and
  results with nobody's name attached.
- **CLI** — `list`, `validate`, `run`, `report`, `submit`, with `--dry-run`, `--max-calls`,
  content-addressed caching, and resume after a crash.
- **Offline demo** — a synthetic cassette generated from a committed policy file, so the
  whole pipeline runs with no API key.

### Notes

- The leaderboard is **empty**. No model has been run and no result is claimed. An empty
  table is the correct state until somebody submits one.
- `choice` mode measures a proxy for agent behaviour, the freeform mapper's accuracy on
  real model output is unmeasured, and 120 items is a modest N. All three are stated in
  the README and argued in `docs/validity.md`.
