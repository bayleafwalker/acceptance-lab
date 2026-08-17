from __future__ import annotations

import unittest

from acceptance_lab.models import CandidateOutput, ModelValidationError, Scenario
from tests.helpers import asset_dict


class ModelTests(unittest.TestCase):
    def test_fixture_contracts_load(self) -> None:
        scenario = Scenario.from_dict(asset_dict("change-with-verification.json"))
        output = CandidateOutput.from_dict(asset_dict("trajectory-good.json"))
        self.assertEqual("change-with-verification", scenario.id)
        self.assertEqual(4, len(output.trajectory))

    def test_duplicate_check_ids_are_rejected(self) -> None:
        value = asset_dict("current-authority.json")
        value["checks"].append(dict(value["checks"][0]))
        with self.assertRaisesRegex(ModelValidationError, "duplicate check ids"):
            Scenario.from_dict(value)

    def test_trajectory_sequence_must_be_unique_and_ascending(self) -> None:
        value = asset_dict("trajectory-good.json")
        value["trajectory"][1]["seq"] = 1
        with self.assertRaisesRegex(ModelValidationError, "unique and ascending"):
            CandidateOutput.from_dict(value)


if __name__ == "__main__":
    unittest.main()
