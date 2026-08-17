from __future__ import annotations

import unittest

from acceptance_lab.models import CandidateOutput, Scenario
from acceptance_lab.scoring import evaluate_candidate
from tests.helpers import asset_dict


class ScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = Scenario.from_dict(asset_dict("change-with-verification.json"))

    def test_verified_trajectory_passes(self) -> None:
        output = CandidateOutput.from_dict(asset_dict("trajectory-good.json"))
        result = evaluate_candidate(self.scenario, output, "verified")
        self.assertEqual("PASS", result.status)
        self.assertTrue(all(score.passed for score in result.scores))

    def test_unsafe_trajectory_fails_authority_and_verification(self) -> None:
        output = CandidateOutput.from_dict(asset_dict("trajectory-bad.json"))
        result = evaluate_candidate(self.scenario, output, "unsafe")
        failed = {score.check_id for score in result.scores if not score.passed}
        self.assertEqual("FAIL", result.status)
        self.assertTrue(
            {
                "tool-allowlist",
                "unscoped-shell-blocked",
                "required-sequence",
                "effect-verified",
                "effect-receipted",
            }.issubset(failed)
        )
        self.assertIn("outcome-fact", {score.check_id for score in result.scores if score.passed})


if __name__ == "__main__":
    unittest.main()
