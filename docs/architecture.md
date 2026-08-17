# Architecture

## Claim

Acceptance Lab owns the acceptance record for an observed candidate run. It does
not own model execution, production credentials, or business effects.

The operating chain is:

```text
observability -> evidence -> evaluation -> policy
```

The current package receives an already-observed run, binds it into a bounded
evidence record, and evaluates it. Live trace capture and external policy
enforcement remain separate owners.

The package separates four dimensions that are often collapsed into one score:

1. **Mechanism** — did the candidate use the expected control path?
2. **Quality** — did the required facts or effects survive?
3. **Authority** — were the sources, tools, identities, and receipts admissible?
4. **Economics** — did the run remain inside its operational budget?

A run can be valid as a record and still fail as an outcome.

## Data flow

```text
versioned scenario
      +
candidate observation
      |
      v
scenario validation
candidate validation
      |
      v
deterministic scorers
      |
      v
run.started
score.recorded x N
run.completed
      |
      v
hash-chained SQLite event log
      |
      v
rebuildable run and score projections
      |
      +----> Markdown report
      +----> JSON report
      +----> comparison / CI decision
```

## Event authority

`events` is the local source of truth. Each event stores the preceding event hash
and a hash of its own stable envelope. The chain makes an edit visible; it does
not provide external notarization or protect a host an attacker fully controls.

The chain covers the complete store rather than one stream. This gives the local
prototype a simple global append order. A served or multi-writer implementation
would need producer identity, partitioning, sequence arbitration, and stronger
concurrency rules rather than pretending one SQLite sequence generalizes by
magic.

## Projection model

`projection_runs` and `projection_scores` are read models. `acceptlab rebuild`
deletes and recreates them by replaying the event log.

Do not patch a projection to fix history. Append a corrective event after the
event vocabulary supports one, or start a new run if the candidate record was
wrong.

## Scenario contract

A scenario is a versioned acceptance statement. Its checks name:

- a scorer type;
- a dimension;
- a threshold;
- whether failure blocks promotion;
- scorer-specific parameters.

The package deliberately does not calculate a universal risk-weighted score.
`FAIL` means at least one declared hard gate failed. `CONDITIONAL` means no hard
gate failed but at least one soft check did. `PASS` means every declared check
passed. The scenario owner remains responsible for whether those checks were the
right ones.

## Candidate contract

The candidate record contains:

- answer text;
- normalized facts claimed by the candidate;
- citations and which facts they support;
- abstention state;
- ordered tool trajectory;
- effects, effect identifiers, verification links, and receipts;
- cost and latency metrics;
- free metadata for model, prompt, harness, corpus, or provider versions.

A live adapter should construct this record from trace and runner evidence. It
should not trust a model to self-report its own authority or tool identity.

The exact scenario and bounded candidate snapshots are embedded in the
`run.started` event and hashed there. Large raw traces may remain in an external
content-addressed store, but their identifiers and digests belong in the candidate
metadata. Do not put credentials or unrestricted production payloads into an
Acceptance Lab record.

## Authority boundary

The harness currently receives already-observed candidate data. It does not run
commands or mint credentials. A future runner adapter must preserve this split:

```text
agent chooses an eligible operation
-> runner validates structure and authority
-> runner performs the effect
-> runner emits execution receipt
-> observer emits candidate trajectory
-> Acceptance Lab scores the record
```

The model may propose. The runner executes. The scenario declares acceptance.
Those are different owners.

## Judge integration

Semantic judges belong behind a scorer adapter. Their output should be recorded
with judge model, prompt, version, and supporting trace identifiers.

Judge output is advisory for criteria without a deterministic oracle. It must not
turn a denied tool call, missing effect receipt, or forbidden authority source
into a pass.

## Scale boundary

SQLite is appropriate for one operator and bounded local runs. Move to a served
store only when concurrent producers, remote inspection, or shared promotion
state become actual requirements. A future Postgres projection can retain the
same event vocabulary, but automatic synchronization with Vuoro is deliberately
out of scope until ownership and arbitration are explicit.
