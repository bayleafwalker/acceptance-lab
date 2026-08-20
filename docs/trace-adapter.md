# Read-only trace adapter

The Acceptance Lab harness does not execute tools or own observability. A
runner/trace integration may pass an already-observed record through
`acceptance_lab.adapters.candidate_from_trace` to produce the existing
candidate-output contract.

## Boundary

```text
runner or trace observer
        |
        | trace_id, tool_calls, receipts, versioned provenance
        v
candidate_from_trace(candidate observation, trace observation)
        |
        | candidate-output-shaped mapping
        v
Acceptance Lab validation and scoring
```

The adapter is pure and read-only. It does not call tools, fetch trace data,
mint receipts, or verify a receipt against an external system. The caller
remains responsible for supplying an observation from the runner or trace
owner.

## Minimal observed input

The current package-level adapter contract is intentionally explicit:

```json
{
  "trace_id": "trace:example:001",
  "provenance": {
    "model": "model-v1",
    "prompt_version": "prompt-v3",
    "harness_version": "runner-v2",
    "tool_set_version": "readonly-tools-v1",
    "corpus_version": "corpus-2026-08-20"
  },
  "tool_calls": [
    {
      "event_id": "span:tool:001",
      "observed_by": "runner",
      "seq": 1,
      "tool": {
        "name": "corpus.read",
        "identity": "runner-tool-registry/corpus.read@v1"
      },
      "action": "read the runbook",
      "effect": true,
      "effect_id": "read-001",
      "receipt": {"owner": "runner", "id": "receipt:read:001"}
    }
  ]
}
```

The candidate's own trajectory and arbitrary metadata are ignored. Tool
identity is not accepted as a bare string, and receipt strings are not accepted
without an explicit runner owner. An effect may have no receipt in the adapted
output; the deterministic `effect_receipts` check then reports the failure
instead of the adapter inventing evidence. Only the explicit observed
provenance allowlist and trace references are emitted into metadata.

## Deliberate schema gap

`candidate-output.schema.json` currently has compact trajectory fields only:
sequence, tool name, action, effect/effect ID, verification links, and receipt
ID. A live trace commonly has more evidence: event timestamps, parent/span
relationships, attempt IDs, tool identity attestations, receipt issuer and
digest, authorization decisions, and a raw trace location. The adapter keeps
stable `trace_id`, `trace_event_ids`, and `tool_identities` in metadata and
does not pretend those richer values fit the compact trajectory fields. Full
raw traces remain with their trace/runner owner.

Adding a versioned live-trace schema is a follow-on change once one real runner
contract is available; this package does not infer one from fixture data.
