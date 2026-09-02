# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | yes |

This is a pre-1.0 research tool. There is no long-term support branch.

## Reporting a vulnerability

**Do not open a public issue.** Use GitHub's private vulnerability reporting on this
repository (Security → Report a vulnerability), or contact the maintainer through their
GitHub profile.

Please include what you did, what happened, and what you expected. A proof of concept
helps. You will get an acknowledgement within a week.

## What this tool touches

Worth knowing before you assess the risk surface:

- **It makes outbound HTTPS requests** to whatever `--base-url` you give it, and to
  nothing else. There is no telemetry, no analytics, no phone-home.
- **It reads one environment variable for credentials**, named by `--api-key-env`
  (default `KNOWWHEN_API_KEY`). The key is never accepted as a command-line argument, so it
  cannot land in a shell history or a CI log, and it is never written to disk, to a run
  manifest, or to a cache entry.
- **It writes to two places**: the results directory you choose (default `results/`) and
  the response cache (default `~/.cache/knowwhen`, override with `--cache-dir`, disable
  with `--no-cache`).
- **It executes no model output.** Responses are parsed with regular expressions and
  written to disk as text. Nothing in a model response is ever evaluated, shelled out, or
  used as a path.
- **It loads YAML with `yaml.safe_load`** only. A scenario file cannot construct arbitrary
  Python objects.
- **Cassettes and scenario files are data, not code.** A malicious cassette can make the
  scoring wrong; it cannot make the tool run anything.

## Things that are not vulnerabilities

- A cassette or scenario file producing a misleading score. That is a data-integrity
  problem and belongs in a normal issue. `knowwhen submit` and the submission schema exist
  to stop such a run reaching a leaderboard.
- A model output that the mapper classifies incorrectly. That is a validity issue; see
  `docs/validity.md` and open a normal issue with the exact text.
- Cost incurred by running against a paid endpoint. Use `--dry-run` and `--max-calls`.

## Reporting a data-integrity problem in the benchmark itself

If you find a scenario whose credit vector is wrong, a leaderboard row that cannot be
reproduced, or a number in the documentation that no command produces, open a **public**
issue. Those are the failures this project most wants reported loudly.
