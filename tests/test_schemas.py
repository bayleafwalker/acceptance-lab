from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - jsonschema is a dev-only dependency
    Draft202012Validator = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]


def _load(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


@unittest.skipIf(Draft202012Validator is None, "jsonschema not installed")
class CandidateOutputMetadataTests(unittest.TestCase):
    """The reserved execution-provenance keys in candidate-output metadata.

    Typing these keys is only worth doing if the constraints actually fire, and
    is only safe to land if everything that validated before still validates.
    Both halves are asserted here.
    """

    def setUp(self) -> None:
        schema = _load("schemas/candidate-output.schema.json")
        self.validator = Draft202012Validator(schema)
        self.base = _load("examples/outputs/execution-provenance.json")

    def _errors(self, **metadata: Any) -> list[Any]:
        doc = json.loads(json.dumps(self.base))
        for key, value in metadata.items():
            if value is _ABSENT:
                doc["metadata"].pop(key, None)
            else:
                doc["metadata"][key] = value
        return list(self.validator.iter_errors(doc))

    def test_example_is_valid(self) -> None:
        self.assertEqual([], self._errors())

    def test_artifact_sha256_must_be_lowercase_hex_64(self) -> None:
        for bad in ("A" * 64, "abc123", "z" * 64, "0" * 63):
            with self.subTest(value=bad):
                self.assertTrue(self._errors(artifact_sha256=bad))

    def test_profile_and_engine_must_be_non_empty_strings(self) -> None:
        self.assertTrue(self._errors(profile=""))
        self.assertTrue(self._errors(engine=""))
        self.assertTrue(self._errors(engine=5))

    def test_reserved_keys_stay_optional(self) -> None:
        self.assertEqual(
            [],
            self._errors(
                profile=_ABSENT, engine=_ABSENT, artifact_sha256=_ABSENT
            ),
        )

    def test_metadata_stays_open_to_other_domains(self) -> None:
        self.assertEqual([], self._errors(retrieval_mode="authority-aware"))

    def test_pre_existing_outputs_still_validate(self) -> None:
        for name in ("trajectory-good.json", "trajectory-bad.json"):
            with self.subTest(name=name):
                doc = _load(f"examples/outputs/{name}")
                self.assertEqual([], list(self.validator.iter_errors(doc)))


_ABSENT = object()


if __name__ == "__main__":
    unittest.main()
