# Acceptance Lab agent guidance

Acceptance Lab is a deliberately small evaluation substrate. It records candidate
runs, scores explicit acceptance rules, and projects reports. It is not an agent
runtime, generic observability product, or model-judge framework.

## Boundaries

- Keep the event log append-only. Fix projections or append corrective events;
  never rewrite historical events through application code.
- Keep deterministic requirements deterministic. A model judge may supplement a
  semantic criterion but must not override authority, evidence, execution, or
  budget gates.
- Candidate outputs are observations supplied to the harness. The current package
  does not grant credentials or execute production effects.
- Retrieval is one example workload. Do not turn the package into a RAG framework.
- SQLite is the local authority. Projections are disposable and must rebuild from
  events.
- Do not extract this into Vuoro until at least two real consumers need the same
  event contract.

## Validation

```bash
python -m pip install -e ".[dev]"
make validate
```

The demo intentionally contains failing candidates. The demo command itself must
succeed and produce reports showing why those candidates failed.
