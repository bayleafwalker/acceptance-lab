# Acceptance Lab

Acceptance Lab is a local-first prototype for turning AI-system requirements into
executable acceptance records.

It records a candidate run, evaluates explicit rules across **mechanism**,
**quality**, **authority**, and **economics**, and emits a promotion state:
`PASS`, `CONDITIONAL`, or `FAIL`.

Retrieval is included as one example workload. It is not the product.

## Why this exists

Managed platforms increasingly provide vector stores, retrieval orchestration,
traces, judges, and evaluation dashboards. They cannot supply the workflow's
actual denominator:

- which source is allowed to count;
- what facts or effects must survive;
- which tool or identity is permitted;
- which failure blocks promotion;
- what evidence must accompany the result;
- who may accept the residual risk.

Acceptance Lab keeps those rules in a versioned scenario and scores an observed
candidate record against them. Its intended placement is:

```text
trace or observed run
-> bounded evidence record
-> scenario-specific evaluation
-> external promotion, hold, rollback, or escalation policy
```

This prototype implements the evidence and evaluation steps. It does not yet
own live observability or enforce production policy.

The accompanying Kotona note is in
[`../kotona/src/content/notes/the-platform-can-retrieve-the-application-still-has-to-decide.md`](../kotona/src/content/notes/the-platform-can-retrieve-the-application-still-has-to-decide.md).

## Current capability

The prototype provides:

- zero runtime dependencies;
- JSON scenario and candidate-output contracts;
- deterministic scorer plugins;
- exact scenario and candidate snapshots bound into append-only SQLite events;
- a SHA-256 event hash chain that exposes later edits;
- rebuildable run and score projections;
- Markdown and JSON reports;
- baseline-versus-candidate comparisons;
- CI-friendly exit codes;
- a deterministic demo with two intentionally failing baselines.

The event log is authoritative. Projections are disposable.

## Quick start

Python 3.12 or newer is required.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .

acceptlab demo --workspace .demo
cat .demo/reports/summary.md
```

The demo produces:

| Workload | Baseline | Candidate | Why |
| --- | --- | --- | --- |
| Current-authority retrieval | `FAIL` | `PASS` | Naïve relevance promotes a superseded ADR; authority-aware retrieval filters it |
| Bounded change trajectory | `FAIL` | `PASS` | The unsafe candidate reaches the claimed outcome through an unscoped tool, without an effect receipt or verification |

Inspect the comparisons:

```bash
cat .demo/reports/retrieval-comparison.md
cat .demo/reports/trajectory-comparison.md
```

## Evaluate a candidate record

```bash
acceptlab init --db .acceptance-lab/events.db

acceptlab evaluate \
  --db .acceptance-lab/events.db \
  --scenario examples/scenarios/change-with-verification.json \
  --output examples/outputs/trajectory-good.json \
  --candidate verified-v1
```

A failing hard gate returns exit code `2`. Use `--no-fail` when collecting a
baseline that is expected to fail.

Render or compare recorded runs:

```bash
acceptlab list-runs --db .acceptance-lab/events.db

acceptlab report \
  --db .acceptance-lab/events.db \
  --run-id <run-id> \
  --out reports/run.md

acceptlab compare \
  --db .acceptance-lab/events.db \
  --baseline <baseline-run-id> \
  --candidate <candidate-run-id> \
  --fail-on-regression \
  --out reports/comparison.md
```

## Scenario shape

A scenario declares the workload and the checks that make the result acceptable:

```json
{
  "id": "change-with-verification",
  "version": "1.0.0",
  "workload": "agent-trajectory",
  "inputs": {
    "request": "Deploy revision 42 and establish that it is healthy."
  },
  "checks": [
    {
      "id": "effect-verified",
      "type": "effect_verification",
      "dimension": "quality",
      "threshold": 1.0,
      "hard_gate": true,
      "params": {}
    }
  ]
}
```

A candidate record includes the claimed facts, citations, tool trajectory,
effects, verification receipts, and operational metrics. The harness hashes both
input records before appending the result events.

See [`schemas/`](schemas/) and [`examples/`](examples/).

## Built-in checks

| Check type | Purpose |
| --- | --- |
| `required_fact_coverage` | Required expected facts are present |
| `forbidden_fact_absence` | Superseded or prohibited claims are absent |
| `required_evidence_recall` | Required evidence identifiers are cited |
| `forbidden_authority_absence` | A prohibited source is not treated as authority |
| `required_fact_citations` | Required facts are tied to cited evidence |
| `abstention_match` | Refusal behavior matches the scenario |
| `allowed_tools_only` | Every observed tool is inside the allowlist |
| `forbidden_tools_absent` | Denied tools never appear in the trajectory |
| `required_tool_order` | Required control points occur in order |
| `effect_verification` | Every effect is later verified |
| `effect_receipts` | Every effect carries an execution receipt |
| `max_latency` | Latency stays inside the declared budget |
| `max_cost` | Cost stays inside the declared budget |

Deterministic checks should stay deterministic. A future model judge may add a
semantic assessment, but it must not overrule authority, evidence, or execution
hard gates.

## Architecture

```text
scenario + candidate output
          |
          v
 deterministic scorer registry
          |
          v
 append-only evaluation events ----> hash-chain verification
          |
          v
 rebuildable SQLite projections
          |
          +----> run report
          +----> baseline comparison
          +----> CI promotion gate
```

Read [`docs/architecture.md`](docs/architecture.md) for the event and authority
model.

## What is intentionally absent

- no live model runner;
- no credential broker;
- no production effect executor;
- no generic LLM judge service;
- no vector database dependency;
- no graph database dependency;
- no Prometheus, Loki, or MLflow replacement;
- no Vuoro integration yet.

Those exclusions keep the first implementation honest. The next boundary is a
runner adapter that captures a real tool trajectory and binds it to receipts.
Shared Vuoro extraction should wait until a second real workload needs the same
event contract.

## Validation

```bash
python -m pip install -e ".[dev]"
make validate
```

`make validate` compiles the package, runs the unit suite, validates the public
JSON examples against their schemas, and regenerates the deterministic demo.

## Recovery and rollback

The projections can be deleted and rebuilt at any time:

```bash
acceptlab verify-store --db .acceptance-lab/events.db
acceptlab rebuild --db .acceptance-lab/events.db
```

If event-chain verification fails, stop. Do not rebuild over a corrupted record.
Restore the SQLite file from backup or retain it as evidence and start a new
store. Application code never edits historical events.

Removing Acceptance Lab does not affect the candidate system because the current
prototype only consumes records. Its rollback is therefore ordinary removal of
the evaluation gate and its database, not a production-system migration.

## Status

Runnable prototype. It proves the event, scorer, projection, comparison, and
reporting path with deterministic fixtures. It does **not** yet prove that the
schema captures a real long-running agent workload without losing material
trajectory detail.
