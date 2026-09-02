# schemas/ — vendored CXS v0.1

These are a **vendored copy** of the Context Experiment Interchange Spec (CXS) v0.1, not a
dependency. knowwhen does not import any sibling project and no sibling project imports
knowwhen; interoperability here is a claim about **files**, testable by
`tests/test_cxs_conformance.py`, which validates a real run of the demo against these
schemas.

A shared runtime package would make every project using CXS rise and fall together and
would stop any of them being clonable in isolation. A duplicated schema file is cheaper
than a version knot.

## Files

| File | Object |
|---|---|
| `model-descriptor.schema.json` | What was asked, precisely enough to re-run |
| `intervention.schema.json` | A named transformation of the context. knowwhen ships one, `kind: noop` |
| `trial.schema.json` | One execution. Raw, never aggregated in place |
| `outcome.schema.json` | The scored result of a trial |
| `run-manifest.schema.json` | The reproducibility envelope |
| `submission.schema.json` | knowwhen-specific: a third-party result offered for the leaderboard |

## One deliberate refinement to the spec

`outcome.schema.json` allows `score` and `passed` to be **null**, and requires them to be
null exactly when `detail.parse_status` is `"unparseable"`.

The CXS text shows `score` as a number. Making it nullable is a narrowing, not a
widening: it lets the file format distinguish "the model chose the worst available
action" (`score: 0.0`) from "this tool could not read the model's output"
(`score: null`). Collapsing those two into `0.0` would convert a measurement failure into
a model failure, silently, in the one place a reader would never look for it. That is the
single dishonesty this benchmark most needs to avoid, so it is enforced by the schema and
by `tests/test_unparseable.py`.

Anything reading knowwhen output as generic CXS should treat a null `score` as "no score
recorded", not as zero.

## Not in scope for v0.1

`ContextUnit` and `FailurePredicate` are part of CXS but knowwhen neither produces nor
consumes them, so they are not vendored here. Vendoring a schema nothing validates against
would be furniture.
