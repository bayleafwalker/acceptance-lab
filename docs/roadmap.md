# Roadmap

## Phase 0 — deterministic local prototype

Implemented in this bundle:

- versioned JSON scenarios;
- candidate records;
- deterministic scorers;
- append-only hash-chained events;
- rebuildable projections;
- per-run and comparison reports;
- retrieval-authority and trajectory-authority examples.

Exit evidence: `make test` and `make demo` pass; the intended baselines fail for
the declared reasons.

## Phase 1 — one live traced candidate

This connects the currently separate observability and evidence steps. Add one adapter for an existing agent workload. Prefer a bounded read or test
task before any production write.

Required evidence:

- tool calls come from the trace or runner, not model self-report;
- model, prompt, harness, tool set, and corpus versions are recorded;
- raw trace identifiers remain available;
- fixture and live candidate use the same scenario schema;
- at least one schema gap is documented rather than silently flattened.

## Phase 2 — trajectory and recovery semantics

Add:

- explicit attempt identity;
- effect lifecycle (`proposed`, `authorized`, `applied`, `verified`, `recovered`);
- effect-to-receipt binding;
- expected failure and recovery cases;
- human assessment events;
- metamorphic checks for workloads without a complete answer key.

## Phase 3 — external observability adapters

Export traces and scores to existing systems rather than recreating them:

- MLflow for model/application evaluation and judge workflows;
- OpenTelemetry for trace transport;
- Prometheus for operational counters and budgets;
- Loki for diagnostic logs;
- homelab-analytics for cross-run analysis where appropriate.

The local event record remains useful as the acceptance receipt even when those
systems own visualization.

## Phase 4 — shared component decision

Reassess Vuoro extraction after a second real consumer exists. The decision
must name state ownership, producer identity, arbitration, replay, migration,
and rollback. “The schemas look reusable” is not sufficient evidence.
