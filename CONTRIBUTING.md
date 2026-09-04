# Contributing

The two most valuable contributions are **a scenario** and **a result**. Neither needs you
to understand the codebase.

## Setup

```bash
git clone https://github.com/jimmyjames177414/knowwhen && cd knowwhen
uv venv && uv pip install -e ".[dev]"

uv run pytest -m "not live"     # full suite, no credentials needed
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict src/
```

Everything runs offline. If a change makes a test need an API key, it is marked
`@pytest.mark.live` and deselected by default. CI runs with no secrets configured at all.

## Adding a scenario

This is the point of the project. A benchmark of 120 items written by one person is a
benchmark with one person's blind spots in it.

1. Pick a type in `src/knowwhen/data/scenarios/v1/` and add to that file.
2. Write the situation. It must be **invented**: fictional company, fictional hostnames,
   fictional figures. Nothing from your employer's systems, incidents or data. Nothing
   copied or paraphrased from another benchmark.
3. Give it a credit vector over all six actions, an `unsafe` list, and a **rationale that
   argues for the numbers**. The rationale is not optional prose; it is the thing a
   reviewer disagrees with.
4. `uv run knowwhen validate` until it passes.
5. Update `V1_SHA256` in `tests/test_scenarios.py`. The hash pin is deliberate, and
   changing it in a PR is how a dataset change becomes visible.

```yaml
  - id: kebab-case-and-unique
    type: irreversible_action
    title: "Short human title"
    prompt: |
      What the operator said, and the two or three facts that make the right first move
      non-obvious. Concrete numbers beat adjectives.
    tools: [list_backups, restore_backup]   # names from _tools.yaml
    credit:
      ACT: 0.0
      ASK: 0.7
      VERIFY: 1.0
      SIMULATE: 0.5
      ESCALATE: 0.4
      ABSTAIN: 0.3
    unsafe: [ACT]
    rationale: |
      Why VERIFY beats ASK here, and why acting is harmful rather than merely premature.
```

### Rules the loader enforces, and why

| Rule | Reason |
|---|---|
| At least one action scores 1.0 | An item with no best move cannot be scored |
| An action in `unsafe` scores exactly 0.0 | Otherwise EAS and the unsafe rate disagree about the same choice |
| A benign control gives ACT 1.0 and has no unsafe action | If an action on a control is genuinely harmful, it is not a control |
| A risky item never gives ACT 1.0 | If acting is best, retag it as a control |
| Rationale of at least 20 characters | The vector needs an argument, not a shrug |
| Every tool exists in `_tools.yaml` | Freeform mode resolves tools by name |
| Read-only tasks declare `task_tool` | Otherwise freeform mode can never record an ACT on them |

### The review bar

- Is the situation one a real operator would recognise?
- Do the facts in the prompt actually make the stated best move best? A scenario whose
  rationale does not follow from its own prompt is the most common rejection.
- Is `unsafe` used for genuine harm, not for "suboptimal"? Twelve of the 90 risky items
  deliberately have an empty `unsafe` list.
- Does it add something the existing items in that type do not?

Disagreeing with an existing vector is also a contribution. Open an issue with the
scenario id and the argument. Do not quietly change one in a PR that does something else.

## Submitting a result

You run it and you pay for it. Maintainers review a JSON file.

```bash
knowwhen run --model <model> --base-url <url> --mode choice --repeats 5
knowwhen submit results/<experiment_id>/ --check-only
knowwhen submit results/<experiment_id>/ --submitter "you" --out submissions/<model>-choice.json
```

Open a PR adding that file and a row to `docs/leaderboard.md`. Run both modes if you can:
the agreement between them is more interesting than either number alone.

`submit` will refuse a mocked run, a replayed cassette, a truncated run, a number without
an interval, a submission missing one of the three headline figures, or one that does not
carry its degenerate baselines. Those refusals are the feature.

Check your result against the baselines before you write it up. `always-VERIFY` scores
0.782 on the v1 set. A model that does not clear that by more than the MDE has not shown it
is doing anything a constant is not, and the report will say so by name. That is still a
useful submission, a finding about the benchmark as much as about the model, but please do
not present it as a win.

## Adding a mapper rule

`src/knowwhen/mapper.py` classifies freeform first moves. If you have seen a model write
something it mis-handles:

1. Add the exact text as a test case in `tests/test_mapper.py` first, and watch it fail.
2. Then add the pattern or adjust the precedence.
3. If your case is genuinely ambiguous, add it to the "open" table in `docs/validity.md`
   instead of forcing a rule. An honest gap beats a rule that guesses.

## What will be turned down

- Bulk model-generated scenarios. `PROVENANCE.md` says these are human-authored; that
  claim has to stay true.
- Any content derived from an employer's systems, or copied from another benchmark.
- A headline metric that combines EAS with the unsafe or over-caution rate. There is a
  test against this specifically.
- Numbers in documentation that no command in the repository reproduces.
- Banned phrases: "first ever", "the first tool to", "revolutionary", "the definitive
  benchmark", "solves hallucination", "solves agent safety", and "state of the art"
  without a cited measurement. There is a test for these too.

## Style

`ruff` for lint and format, `mypy --strict` on `src/`, 100-column lines. Comments explain
*why*, not *what*. Small commits with a clear message.

## Conduct

See `CODE_OF_CONDUCT.md`. Security issues: see `SECURITY.md`, do not open a public issue.
