# results/

`knowwhen run` writes here by default: `results/<experiment_id>/`.

Everything in this directory is gitignored except this file. That is deliberate. A
committed run is a published claim about a model, and a published claim needs the
provenance that `knowwhen submit` produces — a manifest, an interval, an N, and a named
person who ran it. Dropping a raw run directory into git history skips all of that.

If you want to publish a result, run:

```bash
knowwhen submit results/<experiment_id>/ --submitter "<your name or handle>"
```

and open a pull request with the file it prints. See `CONTRIBUTING.md`.
