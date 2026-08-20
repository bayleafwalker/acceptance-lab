# Trace-grounded campaign — 20 August 2026

This campaign applies Acceptance Lab to two bounded observations. It does not
execute either candidate and does not promote a production system.

- `local-inference-manifest` scores the real local `worker-fast` manifest-fix
  outcome. The declared outcome and mechanical gates pass, while the required
  fact explicitly preserves its `experimental_unqualified` route status.
- `takeover-current-state` scores whether a read-only reducer reports the
  takeover package at commit `4412ca1` honestly. A `PASS` here means the reducer
  correctly reports G1 as unproven, G7/G8 as pending, and the final verdict as
  withheld. It does **not** mean the takeover experiment passes.

The trace JSON files are sanitized reductions of runner-owned evidence. They
contain no prompts, model text, command output, credentials, or raw transcripts.
Source hashes and exact commits are recorded in `provenance.json`; the original
local-inference bundle remains host-persistent and is not published.

Rebuild and check the committed candidate outputs and stable reports:

```bash
PYTHONPATH=src python scripts/run_campaign.py --write
PYTHONPATH=src python scripts/run_campaign.py
```

The script also records each evaluation in a disposable SQLite event store,
verifies its hash chain, and rebuilds projections. Wall-clock timestamps and
event UUIDs are omitted from the committed report so regeneration is
byte-deterministic.
