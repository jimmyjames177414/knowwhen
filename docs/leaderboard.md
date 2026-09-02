# Leaderboard

## No submissions yet — be the first

There are no results here because nobody has run knowwhen against a real model and
submitted the output. **An empty table is the correct state until that happens.** A
plausible-looking row for a model we did not run would be a fabrication, and it is the one
thing this project cannot recover from.

| Model | Mode | EAS (95% CI) | Unsafe rate | Over-caution | Unparseable | N | Repeats | Dataset | Submitted by |
|---|---|---|---|---|---|---|---|---|---|
| _(none yet)_ | | | | | | | | | |

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

Both modes are welcome and both are reported. If you run both, say so — the agreement
between them is more interesting than either number alone, and nobody has measured it yet.

## Reading a row, when there are rows

- **EAS alone tells you very little.** Read it with the unsafe rate, always.
- **Check the N and the MDE.** Two models within the MDE of each other are not
  distinguishable on 120 items, whatever the ordering suggests.
- **Check the dataset hash.** A row against a different hash is a row about a different
  benchmark.
- **Check the mode.** `choice` measures a proxy. See `docs/validity.md`.
