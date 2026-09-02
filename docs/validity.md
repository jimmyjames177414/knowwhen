# Validity: what these numbers do and do not support

This page exists to be quoted against us. If you are deciding whether to trust a knowwhen
result, read it before the README's numbers, not after.

## The headline threat: `choice` mode measures a proxy

In `--mode choice` the model is shown an explicit six-way menu with definitions and asked
to pick one. **That measures behaviour under a menu, not behaviour in an agent loop.**

A model that reliably picks VERIFY from a labelled list may still barrel straight into a
`DROP DATABASE` when it is holding real tools and nobody has named the alternatives. The
menu does three things that reality does not:

1. It tells the model the six options exist, which is a large hint that caution is on the
   table at all.
2. It makes "this is a safety evaluation" fairly obvious, and we cannot rule out that
   models pattern-match the format.
3. It removes the cost of the cautious option. In a real loop, asking has a latency and a
   social cost; in a menu it is one word.

`choice` is shipped anyway because it is cheap, deterministic, comparable across models and
free of mapper error. It is a proxy, and it is labelled as one everywhere it appears.

## The second mode, and its own problem

`--mode freeform` shows the model tools and a situation, never mentions the six classes,
and asks for its first move in its own words. A deterministic rule cascade
(`src/knowwhen/mapper.py`) classifies that move.

Higher validity, different error. The mapper is a few hundred lines of regular
expressions, and **its accuracy against human labelling on real model output is
unmeasured**. We ship it as auditable rules rather than an LLM judge precisely so that its
mistakes can be found by reading it, but "auditable" is not "correct".

What we do report is its **failure to classify at all**: any response no rule matches is
`unparseable` and appears in the unparseable rate rather than being guessed.

### Known mapper failure modes

Each of these is a real thing models write. The ones marked *handled* have a test in
`tests/test_mapper.py`; the ones marked *open* do not, and are the honest list of what
would break.

| Case | Status |
|---|---|
| A rhetorical question that is really a refusal ("Are you seriously asking…? I won't.") | handled |
| A refusal that is really a clarification ("I won't yet. Which one did you mean?") | handled |
| A tool named only in order to decline it ("I won't run `drop_database` until…") | handled |
| A bare tool name in prose ("I'll run `list_databases` first") | handled |
| A read that *is* the task, on a read-only item | handled via `task_tool` |
| Multi-step plans where the stated first step is not the first step actually taken | **open** |
| Hedged output that names three options without committing to one | **open** — usually `unparseable`, occasionally mis-mapped to whichever signal appears first in precedence |
| Non-English output | **open** — the patterns are English-only and will not match |
| A model that asks a clarifying question *and* acts in the same turn | **open** — the tool call wins, which is defensible but not obviously right |
| Sarcasm, or a refusal expressed as compliance | **open** |

The rule cascade's precedence order is documented in the docstring of `map_freeform` and
is a set of judgement calls, not a derivation.

## Agreement between the modes is itself a result

Run both modes on the same model and the disagreement rate tells you something neither
mode tells you alone: how much of the `choice` score survives contact with a situation
where nobody named the options. A model that scores well on `choice` and badly on
`freeform` is a model that recognises a safety menu.

**We have not measured this on any model.** The offline demo cannot: it replays a
cassette generated from a single policy, so the two modes agree by construction except for
three deliberately divergent items. Mode agreement is a finding only when it is measured
against something with judgement.

## The dataset

- **120 items is small.** The MDE printed on every run says what that costs: at
  n=116 with the demo's spread, differences below about 0.11 EAS are not detectable. Two
  models a few points apart are not distinguishable on this set, and the report says so
  rather than letting a table imply otherwise.
- **The credit vectors are one person's judgement.** See `docs/scoring.md`. Experts will
  disagree; disagreement is a finding and the rationales are shipped so it can be argued
  concretely.
- **Contamination cannot be ruled out.** The scenarios were hand-written in September 2026
  and have never been published before, but a model trained after they appear on GitHub
  will have seen them. The dataset hash in every manifest at least makes it possible to
  say *which* version a result refers to. See `PROVENANCE.md`.
- **English only, single turn.** No multi-turn escalation, no non-English scenarios.
- **Generic infrastructure situations only.** Databases, deployments, billing, access. No
  medical, legal, physical-safety or embodied scenarios. Nothing here transfers to those
  domains and no claim is made that it does.

## VERIFY and SIMULATE are scored as declared intent

The benchmark scores the *choice* to verify or simulate. It does not execute the
verification, check that the model would have read the right thing, or run the dry run. A
model that says "I'll check the replication lag" and would have checked the wrong metric
scores the same as one that would have checked the right one.

That is a real limitation and it is the reason `NOVELTY.md` states the caveat that nobody
having scored these classes before is not evidence they are worth scoring. If VERIFY and
SIMULATE turn out not to discriminate between models, that is a result we will publish.

## What a score does not establish

A high EAS does not establish that a model is safe to deploy. *Safety, or Just Capability?
A Validity Audit of Agent-Safety Benchmarks* ([arXiv:2607.28685]) found a trivial
always-positive policy scoring F1 0.690 on R-Judge, beating five of twenty-one real models,
and found three broad-coverage benchmarks ranking the same eighteen models differently. Its
recommendation, verbatim, is that *"naming the benchmark, metric, target behavior, and
model panel is the minimum a safety claim needs"* — which is why every knowwhen number
ships with its dataset hash, its scorer id, its elicitation mode and its N.

[arXiv:2607.28685]: https://arxiv.org/abs/2607.28685

## Prior art this sits beside

Read these before treating knowwhen as novel. `NOVELTY.md` has the full gate.

- **AgentAtlas**, [arXiv:2605.20530] — published the six-state taxonomy. We did not invent
  it and adopt it explicitly.
- **Agentic Abstention**, [arXiv:2606.28733] — the strongest public multi-class artifact:
  answer / abstain / gather-more-information, 28,000+ tasks, Apache-2.0.
- **AbstentionBench**, [arXiv:2506.09038] — ~35k queries of binary answer-vs-abstain.
- **ToolEmu**, [arXiv:2309.15817] — same threat model, LM-emulated sandbox, and a rubric
  that already penalises acting without confirmation.
- **Ask Early, Ask Late, Ask Right**, [arXiv:2605.07937] — when clarification pays.
- **Act or Escalate?**, [arXiv:2604.08588] and the learning-to-defer literature behind it.

[arXiv:2605.20530]: https://arxiv.org/abs/2605.20530
[arXiv:2606.28733]: https://arxiv.org/abs/2606.28733
[arXiv:2506.09038]: https://arxiv.org/abs/2506.09038
[arXiv:2309.15817]: https://arxiv.org/abs/2309.15817
[arXiv:2605.07937]: https://arxiv.org/abs/2605.07937
[arXiv:2604.08588]: https://arxiv.org/abs/2604.08588
