"""Read-only adapters for observed runner/trace data.

The adapter in this module deliberately does not execute tools, resolve trace
IDs, or inspect a runner.  It only translates an already-observed trace into
the candidate-output contract.  In particular, trajectory and receipt fields
come from the trace; values supplied in the candidate's own ``trajectory`` or
provenance metadata are not authoritative.
"""

from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any, Mapping

from acceptance_lab.models import CandidateOutput


class TraceAdapterError(ValueError):
    """Raised when an observed trace does not meet the adapter boundary."""


_PROVENANCE_KEYS = (
    "model",
    "prompt_version",
    "harness_version",
    "tool_set_version",
    "corpus_version",
    "profile",
    "engine",
    "artifact_sha256",
)


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TraceAdapterError(f"{field} must be a non-empty string")
    return value.strip()


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TraceAdapterError(f"{field} must be an object")
    return value


def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise TraceAdapterError(f"{field} must be a list of non-empty strings")
    return [item.strip() for item in value]


def candidate_from_trace(
    candidate: Mapping[str, Any], trace: Mapping[str, Any]
) -> dict[str, Any]:
    """Build a candidate output from a candidate observation and an observed trace.

    ``candidate`` contributes answer/facts/citations/abstention/metrics only.
    The returned trajectory is reconstructed exclusively from ``trace``.  Each
    trace event must identify its observation source as ``trace`` or ``runner``
    and must carry a structured tool identity.  Effect receipts are accepted
    only when explicitly marked ``owner: runner``; a free-form receipt string
    cannot cross this boundary.

    The function is intentionally pure: it never performs I/O or mutates either
    input mapping.  Versioned execution provenance is required in the observed
    trace, while optional engine/profile/artifact fields are copied only when
    the trace supplies them.
    """

    candidate_map = _mapping(candidate, "candidate")
    trace_map = _mapping(trace, "trace")
    trace_id = _string(trace_map.get("trace_id"), "trace.trace_id")
    provenance = _mapping(trace_map.get("provenance"), "trace.provenance")
    required_provenance = (
        "model",
        "prompt_version",
        "harness_version",
        "tool_set_version",
        "corpus_version",
    )
    observed_provenance: dict[str, str] = {}
    for key in required_provenance:
        observed_provenance[key] = _string(
            provenance.get(key), f"trace.provenance.{key}"
        )
    for key in ("profile", "engine", "artifact_sha256"):
        if key in provenance:
            observed_provenance[key] = _string(
                provenance[key], f"trace.provenance.{key}"
            )
    artifact_sha256 = observed_provenance.get("artifact_sha256")
    if artifact_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", artifact_sha256):
        raise TraceAdapterError(
            "trace.provenance.artifact_sha256 must be lowercase hexadecimal SHA-256"
        )

    events = trace_map.get("tool_calls")
    if not isinstance(events, list):
        raise TraceAdapterError("trace.tool_calls must be a list")

    trajectory: list[dict[str, Any]] = []
    trace_event_ids: list[str] = []
    tool_identities: list[str] = []
    seen_seqs: set[int] = set()
    seen_event_ids: set[str] = set()
    last_seq = 0
    for index, raw_event in enumerate(events):
        event = _mapping(raw_event, f"trace.tool_calls[{index}]")
        event_id = _string(event.get("event_id"), f"trace.tool_calls[{index}].event_id")
        if event_id in seen_event_ids:
            raise TraceAdapterError(
                f"trace.tool_calls contains duplicate event_id {event_id}"
            )
        seen_event_ids.add(event_id)
        observed_by = _string(
            event.get("observed_by"), f"trace.tool_calls[{index}].observed_by"
        )
        if observed_by not in {"trace", "runner"}:
            raise TraceAdapterError(
                f"trace.tool_calls[{index}].observed_by must be 'trace' or 'runner'"
            )
        seq = event.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
            raise TraceAdapterError(f"trace.tool_calls[{index}].seq must be positive")
        if seq in seen_seqs:
            raise TraceAdapterError(f"trace.tool_calls contains duplicate seq {seq}")
        if seq <= last_seq:
            raise TraceAdapterError("trace.tool_calls seq values must be ascending")
        seen_seqs.add(seq)
        last_seq = seq
        tool = _mapping(event.get("tool"), f"trace.tool_calls[{index}].tool")
        tool_name = _string(tool.get("name"), f"trace.tool_calls[{index}].tool.name")
        tool_identity = _string(
            tool.get("identity"), f"trace.tool_calls[{index}].tool.identity"
        )
        action = _string(event.get("action"), f"trace.tool_calls[{index}].action")
        effect = event.get("effect", False)
        if not isinstance(effect, bool):
            raise TraceAdapterError(f"trace.tool_calls[{index}].effect must be boolean")
        step: dict[str, Any] = {
            "seq": seq,
            "tool": tool_name,
            "action": action,
        }
        if effect:
            step["effect"] = True
        if "effect_id" in event:
            step["effect_id"] = _string(
                event["effect_id"], f"trace.tool_calls[{index}].effect_id"
            )
        if "verifies" in event:
            step["verifies"] = _strings(
                event["verifies"], f"trace.tool_calls[{index}].verifies"
            )

        receipt = event.get("receipt")
        if receipt is not None:
            receipt_map = _mapping(receipt, f"trace.tool_calls[{index}].receipt")
            owner = _string(
                receipt_map.get("owner"),
                f"trace.tool_calls[{index}].receipt.owner",
            )
            if owner != "runner":
                raise TraceAdapterError(
                    f"trace.tool_calls[{index}].receipt.owner must be 'runner'"
                )
            step["receipt"] = _string(
                receipt_map.get("id"), f"trace.tool_calls[{index}].receipt.id"
            )

        trajectory.append(step)
        trace_event_ids.append(event_id)
        tool_identities.append(tool_identity)

    # Candidate metadata is not an authority source.  Preserve harmless
    # candidate annotations, but remove provenance-shaped claims unless the
    # observed trace replaces them below.
    candidate_metadata = candidate_map.get("metadata", {})
    candidate_metadata = _mapping(candidate_metadata, "candidate.metadata")
    metadata = {
        key: deepcopy(value)
        for key, value in candidate_metadata.items()
        if key not in _PROVENANCE_KEYS
        and key not in {"trace_id", "trace_event_ids", "tool_identities"}
    }
    metadata.update(observed_provenance)
    metadata.update(
        {
            "trace_id": trace_id,
            "trace_event_ids": trace_event_ids,
            "tool_identities": tool_identities,
        }
    )

    adapted = deepcopy(dict(candidate_map))
    adapted["trajectory"] = trajectory
    adapted["metadata"] = metadata
    # Normalize through the package model so the adapter returns the same
    # shape accepted by the evaluator, without allowing candidate trajectory
    # data to influence the result.
    normalized = CandidateOutput.from_dict(adapted).to_dict()
    # ``dataclasses.asdict`` keeps optional Python ``None`` values, while the
    # JSON schema represents absent optional fields by omission (not ``null``).
    # Keep the adapter's output directly schema-valid.
    for step in normalized["trajectory"]:
        for key in ("effect_id", "receipt"):
            if step[key] is None:
                del step[key]
    # Convert dataclass tuples to JSON arrays as the public adapter contract is
    # a JSON-shaped mapping, not an internal dataclass representation.
    return json.loads(json.dumps(normalized))


def adapt_trace_to_candidate(
    candidate: Mapping[str, Any], trace: Mapping[str, Any]
) -> dict[str, Any]:
    """Descriptive alias for :func:`candidate_from_trace`."""

    return candidate_from_trace(candidate, trace)


def adapt_candidate_from_trace(
    candidate: Mapping[str, Any], trace: Mapping[str, Any]
) -> dict[str, Any]:
    """Compatibility alias for callers that lead with the candidate object."""

    return candidate_from_trace(candidate, trace)


__all__ = [
    "TraceAdapterError",
    "candidate_from_trace",
    "adapt_trace_to_candidate",
    "adapt_candidate_from_trace",
]
