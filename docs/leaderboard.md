# Leaderboard

## No submissions yet, be the first

There are no model results here because nobody has run knowwhen against a real model and
submitted the output. An empty table is the correct state until that happens. A
plausible-looking row for a model we did not run would be a fabrication, and it is the one
thing this project cannot recover from.

| Model | Mode | EAS (95% CI) | Unsafe rate | Over-caution | Unparseable | N | Repeats | Dataset | Submitted by |
|---|---|---|---|---|---|---|---|---|---|
| _(none yet)_ | | | | | | | | | |

## The bar: degenerate baselines

These rows *are* filled in, and they are not a contradiction of the empty table above. A
baseline is a deterministic property of the scenario set (no model, no API call, no
sampling), so publishing one is arithmetic, not a claim about anybody's system. Reproduce
every figure with:

```bash
knowwhen baselines
```

Over all 120 items of `v1`, dataset sha256 `3456f3bc…`:

| Policy | EAS | Unsafe rate | Over-caution | Note |
|---|---|---|---|---|
| `always-ACT` | 0.268 | **100.0%** | 0.0% | does the task every time |
| `always-ASK` | 0.533 | 0.0% | **100.0%** | never acts, never harms, never helps |
| `always-VERIFY` | **0.782** | 0.0% | **100.0%** | the bar |
| `always-SIMULATE` | 0.375 | 0.0% | 100.0% | |
| `always-ESCALATE` | 0.413 | 0.0% | 100.0% | |
| `always-ABSTAIN` | 0.270 | 0.0% | 100.0% | |
| `random-uniform` | 0.440 | 16.7% | 83.3% | exact expectation, not sampled |
| `majority-class` | **0.782** | 0.0% | **100.0%** | VERIFY, best on 54/120 items |

Read the first column against the third. `always-VERIFY` posts EAS 0.782 with a 0%
unsafe rate; under a single number it would look like an exemplary, careful model. The
over-caution column is what gives it away, and it is the reason 30 of the 120 items are
benign controls.

A model has demonstrated nothing on EAS until it clears 0.782 by more than the minimum
detectable effect, roughly 0.11 on this item set. Every run prints these rows beside the
model and names any the model failed to clear.

## How to add a row

You run it and you pay for it. The maintainers review a JSON file. That is deliberate:
requiring the maintainer to fund every result is how benchmarks end up with three rows and
a stale leaderboard.

```bash
# 1. Run it. Any OpenAI-compatible endpoint works, including a local Ollama.
knowwhen run \
  --model qwen3:8b \
  --base-url http://localhost:11434/v1 \
  --mode choice \
  --repeats 5

# 2. Check it will be accepted before you write anything up.
knowwhen submit results/<experiment_id>/ --check-only

# 3. Produce the submission file.
knowwhen submit results/<experiment_id>/ \
  --submitter "your name or handle" \
  --evidence-url "https://..." \
  --out submissions/<model>-<mode>.json
```

Then open a pull request adding that file under `submissions/` and a row to the table
above. `CONTRIBUTING.md` has the checklist.

## What gets rejected, and why

`knowwhen submit` refuses anything that would put an unverifiable number in front of a
reader:

| Rejected | Reason |
|---|---|
| `--provider mock` or `--provider cassette` | Replayed and mocked runs demonstrate the pipeline. They are not measurements. |
| A run flagged `synthetic` | Same. |
| A run truncated by `--max-calls` | An incomplete item set is not comparable to a complete one. |
| A missing EAS, unsafe rate or over-caution rate | All three or none. A submission that drops the unsafe rate is exactly the omission this benchmark exists to prevent. |
| Any of those three without an interval | A point estimate is not a result. |
| An unknown action class in `action_counts` | Somebody has changed the taxonomy without saying so. |
| No submitter | A result needs a person attached to it. |

Both modes are welcome and both are reported. If you run both, say so: the agreement
between them is more interesting than either number alone, and nobody has measured it yet.

## Reading a row, when there are rows

- EAS alone tells you very little. Read it with the unsafe rate, always.
- Check the N and the MDE. Two models within the MDE of each other are not
  distinguishable on 120 items, whatever the ordering suggests.
- Check the dataset hash. A row against a different hash is a row about a different
  benchmark.
- Check the mode. `choice` measures a proxy. See `docs/validity.md`.
