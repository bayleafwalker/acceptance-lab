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

    def test_a_check_declaring_an_empty_subject_is_rejected(self) -> None:
        """A check with an empty subject list is satisfied by any candidate at all.

        It is the scenario-side half of the vacuous-truth defect: `params.facts: []`
        gives the scorer a zero denominator, which scores 1.000 and reads in the record
        exactly like a requirement that was met. Refused at the contract, so no scorer
        has to carry a case that cannot be scored.
        """
        value = asset_dict("current-authority.json")
        value["checks"][0]["params"]["facts"] = []
        with self.assertRaisesRegex(ModelValidationError, "non-empty subject"):
            Scenario.from_dict(value)

    def test_a_subject_of_blank_strings_is_rejected_too(self) -> None:
        """`_params_list` discards blank entries, so this reaches a scorer as empty."""
        value = asset_dict("current-authority.json")
        value["checks"][0]["params"]["facts"] = ["   "]
        with self.assertRaisesRegex(ModelValidationError, "non-empty subject"):
            Scenario.from_dict(value)

    def test_a_check_with_no_params_at_all_is_still_valid(self) -> None:
        """`effect_verification` and `effect_receipts` take no parameters; the rule is
        about an empty *declared subject*, not about an absent parameter block."""
        scenario = Scenario.from_dict(asset_dict("change-with-verification.json"))
        effect_check = next(
            check for check in scenario.checks if check.type == "effect_verification"
        )
        self.assertEqual({}, dict(effect_check.params))



if __name__ == "__main__":
    unittest.main()
