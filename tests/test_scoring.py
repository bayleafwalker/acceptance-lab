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


class EmptySubjectTests(unittest.TestCase):
    """A run that demonstrated nothing must not score like a run that behaved.

    An adversarial read of one scenario found the shape: `_ratio(0, 0)` is 1.0, so any
    scorer whose denominator counts something the *candidate* did returned a perfect
    score when the candidate did none of it. A backend that served none of the
    scenario's operations produced an empty trajectory and passed the allowlist gate
    that exists to say which surfaces it touched.

    These tests pin both halves of the distinction: the empty subject must not score
    1.000, and the genuinely clean non-empty subject must still score 1.000, because a
    fix that fails the clean case is not a fix.
    """

    def setUp(self) -> None:
        self.scenario = Scenario.from_dict(asset_dict("change-with-verification.json"))

    def _score(self, output_doc: dict, check_id: str):
        output = CandidateOutput.from_dict(output_doc)
        result = evaluate_candidate(self.scenario, output, "empty-subject")
        return next(score for score in result.scores if score.check_id == check_id)

    def _without_trajectory(self) -> dict:
        doc = asset_dict("trajectory-good.json")
        doc["trajectory"] = []
        return doc

    def _without_effects(self) -> dict:
        """A real trajectory that simply changed nothing.

        Distinct from an empty trajectory: it isolates "no effect was observed" from
        "no step was observed", so the effect scorers are shown to react to their own
        subject rather than to the trajectory being empty.
        """
        doc = asset_dict("trajectory-good.json")
        for step in doc["trajectory"]:
            step["effect"] = False
            step.pop("effect_id", None)
            step.pop("receipt", None)
        return doc

    def test_an_empty_trajectory_does_not_pass_the_allowlist(self) -> None:
        score = self._score(self._without_trajectory(), "tool-allowlist")
        self.assertEqual(0.0, score.score)
        self.assertFalse(score.passed)
        self.assertIn("unestablished", score.summary)
        self.assertTrue(score.details["empty_subject"])

    def test_a_clean_trajectory_still_passes_the_allowlist(self) -> None:
        score = self._score(asset_dict("trajectory-good.json"), "tool-allowlist")
        self.assertEqual(1.0, score.score)
        self.assertTrue(score.passed)
        self.assertNotIn("empty_subject", score.details)

    def test_no_observed_effect_does_not_pass_effect_verification(self) -> None:
        score = self._score(self._without_effects(), "effect-verified")
        self.assertEqual(0.0, score.score)
        self.assertFalse(score.passed)
        self.assertIn("unestablished", score.summary)
        self.assertTrue(score.details["empty_subject"])

    def test_a_verified_effect_still_passes_effect_verification(self) -> None:
        score = self._score(asset_dict("trajectory-good.json"), "effect-verified")
        self.assertEqual(1.0, score.score)
        self.assertTrue(score.passed)

    def test_no_observed_effect_does_not_pass_effect_receipts(self) -> None:
        score = self._score(self._without_effects(), "effect-receipted")
        self.assertEqual(0.0, score.score)
        self.assertFalse(score.passed)
        self.assertIn("unestablished", score.summary)
        self.assertTrue(score.details["empty_subject"])

    def test_a_receipted_effect_still_passes_effect_receipts(self) -> None:
        score = self._score(asset_dict("trajectory-good.json"), "effect-receipted")
        self.assertEqual(1.0, score.score)
        self.assertTrue(score.passed)

    def test_a_candidate_that_did_nothing_fails_the_whole_scenario(self) -> None:
        """The point of the fix, stated at the verdict rather than per score."""
        output = CandidateOutput.from_dict(self._without_trajectory())
        result = evaluate_candidate(self.scenario, output, "did-nothing")
        self.assertEqual("FAIL", result.status)
        self.assertNotEqual(1.0, result.aggregate_score)


class AbsenceIsNotEmptinessTests(unittest.TestCase):
    """The absence checks keep their vacuous pass, deliberately.

    `forbidden_authority_absence` and `forbidden_tools_absent` are satisfied *by*
    absence: a candidate that cited no superseded source did not cite a superseded
    source, and there is no missing evidence to complain about. Their revisions stay at
    1 for that reason, and these tests exist so a later reader can see the decision was
    made rather than overlooked.
    """

    def test_no_citations_still_clears_forbidden_authority_absence(self) -> None:
        scenario = Scenario.from_dict(asset_dict("current-authority.json"))
        output = CandidateOutput.from_dict(
            {"answer": "I cannot establish the current authority.", "abstained": True}
        )
        score = next(
            score
            for score in evaluate_candidate(scenario, output, "cited-nothing").scores
            if score.check_id == "superseded-authority-blocked"
        )
        self.assertEqual(1.0, score.score)
        self.assertTrue(score.passed)

    def test_an_empty_trajectory_still_clears_forbidden_tools_absent(self) -> None:
        scenario = Scenario.from_dict(asset_dict("change-with-verification.json"))
        doc = asset_dict("trajectory-good.json")
        doc["trajectory"] = []
        score = next(
            score
            for score in evaluate_candidate(
                scenario, CandidateOutput.from_dict(doc), "used-nothing"
            ).scores
            if score.check_id == "unscoped-shell-blocked"
        )
        self.assertEqual(1.0, score.score)
        self.assertTrue(score.passed)


if __name__ == "__main__":
    unittest.main()
