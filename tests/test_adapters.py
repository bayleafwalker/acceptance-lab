from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from acceptance_lab.adapters import TraceAdapterError, candidate_from_trace

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - jsonschema is a dev-only dependency
    Draft202012Validator = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]


def _load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class TraceAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = _load("examples/outputs/execution-provenance.json")
        self.candidate["trajectory"] = [
            {
                "seq": 1,
                "tool": "model.claimed.tool",
                "action": "untrusted self-report",
                "receipt": "model-claimed-receipt",
            }
        ]
        self.trace = _load("examples/traces/trace-owned.json")

    def test_reconstructs_trajectory_and_preserves_observed_provenance(self) -> None:
        original_candidate = copy.deepcopy(self.candidate)
        original_trace = copy.deepcopy(self.trace)
        result = candidate_from_trace(self.candidate, self.trace)

        self.assertEqual(
            ["corpus.search", "corpus.read"],
            [step["tool"] for step in result["trajectory"]],
        )
        self.assertNotIn("model.claimed.tool", json.dumps(result))
        self.assertEqual("trace:acceptance-lab:read-001", result["metadata"]["trace_id"])
        self.assertEqual(
            ["span:tool:001", "span:tool:002"],
            result["metadata"]["trace_event_ids"],
        )
        self.assertEqual("prompt-v3", result["metadata"]["prompt_version"])
        self.assertEqual(original_candidate, self.candidate)
        self.assertEqual(original_trace, self.trace)

    def test_receipt_must_be_runner_owned(self) -> None:
        self.trace["tool_calls"][0]["effect"] = True
        self.trace["tool_calls"][0]["effect_id"] = "effect-1"
        self.trace["tool_calls"][0]["receipt"] = {"owner": "model", "id": "claimed"}
        with self.assertRaisesRegex(TraceAdapterError, "receipt.owner"):
            candidate_from_trace(self.candidate, self.trace)

    def test_tool_identity_and_observer_are_required(self) -> None:
        del self.trace["tool_calls"][0]["tool"]["identity"]
        with self.assertRaisesRegex(TraceAdapterError, "tool.identity"):
            candidate_from_trace(self.candidate, self.trace)

    def test_candidate_provenance_claims_do_not_cross_boundary(self) -> None:
        result = candidate_from_trace(self.candidate, self.trace)
        self.assertEqual("fixture-model-v1", result["metadata"]["model"])
        self.assertEqual("worker-readonly", result["metadata"]["profile"])

    def test_missing_effect_receipt_is_left_for_deterministic_scorer(self) -> None:
        self.trace["tool_calls"][0]["effect"] = True
        self.trace["tool_calls"][0]["effect_id"] = "effect-1"
        result = candidate_from_trace(self.candidate, self.trace)
        self.assertNotIn("receipt", result["trajectory"][0])

    @unittest.skipIf(Draft202012Validator is None, "jsonschema not installed")
    def test_adapted_record_matches_candidate_schema(self) -> None:
        schema = _load("schemas/candidate-output.schema.json")
        result = candidate_from_trace(self.candidate, self.trace)
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(result)))


if __name__ == "__main__":
    unittest.main()
