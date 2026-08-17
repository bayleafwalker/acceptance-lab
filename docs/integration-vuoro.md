# Vuoro integration boundary

Do not integrate Acceptance Lab into Vuoro yet.

The event vocabulary is intentionally compatible with a later append-only
component:

```text
run.started
score.recorded
run.completed
baseline.promoted        # future
regression.detected      # future
human.assessment.added   # future
```

That resemblance is not enough to establish ownership.

## Extraction gate

Promote this into a shared Vuoro component only when at least two real consumers
need all of the following:

- the same scenario identity and version contract;
- the same run/event lifecycle;
- shared baseline promotion;
- remote or concurrent writes;
- common projections or operator views;
- an explicit arbitration rule for duplicate or conflicting producers.

Until then, the local package should export JSON or NDJSON that Vuoro can ingest
as ordinary evidence. Reuse the record before reusing the service.

## Possible mapping

| Acceptance Lab | Possible Vuoro owner |
| --- | --- |
| Scenario definition | project repository or domain pack |
| Run lifecycle | evaluation component or ActionQ-adjacent worker record |
| Immutable score events | audit/event substrate |
| Current baseline projection | dedicated evaluation read model |
| Promotion decision | human or policy-owned action, never inferred from mean score |

## Migration path

1. Freeze scenario and event schemas at a tagged version.
2. Add an NDJSON export with source event hash and stream identity.
3. Build a read-only Vuoro projection first.
4. Compare local and served projections from the same exported log.
5. Only then move write authority, with producer identity and replay rules.
6. Retain a downgrade path that can export the served stream back to the local
   SQLite format.
