"""A score means nothing later unless the record says which scorer produced it.

`EvaluationResult` has always pinned `scenario_version`. `SCORERS` was a bare dict of
thirteen callables with no revision at all, so changing one silently rewrote the meaning
of every historical PASS: the stored verdict looked identical, the scenario version was
unchanged, and nothing in the record said the ruler had moved. Any settlement citing such
an evaluation cited a moving target.

These tests cover the three things pinning has to do to be worth anything:

  1. the revision is recorded, per score and per run;
  2. it cannot be forgotten -- editing a scorer without bumping it fails here, not in
     six months when someone tries to reproduce a verdict;
  3. it is acted on -- a comparison across differing revisions is refused rather than
     reported as a delta, because a change in the ruler and a change in the measured
     thing look identical in a number.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from acceptance_lab.models import CandidateOutput, Scenario
from acceptance_lab.reporting import compare_payload, render_run_markdown
from acceptance_lab.scorer_digest import (
    current_harness_lock,
    current_lock,
    digest_source,
    recorded_harness_lock,
    recorded_lock,
    scorer_digest,
)
from acceptance_lab.scoring import (
    EVALUATION_HARNESS_REVISION,
    SCORERS,
    evaluate_candidate,
    scorer_revisions,
)
from acceptance_lab.store import EventStore
from tests.helpers import asset_dict


class ScorerLockTests(unittest.TestCase):
    """The lock is what turns "please remember to bump it" into a gate."""

    def test_every_scorer_is_locked_and_every_lock_entry_is_a_scorer(self) -> None:
        self.assertEqual(set(SCORERS), set(recorded_lock()))

    def test_no_scorer_changed_without_its_revision_moving(self) -> None:
        recorded = recorded_lock()
        drifted = [
            name
            for name, spec in SCORERS.items()
            if scorer_digest(spec.scorer) != recorded[name]["digest"]
        ]
        self.assertEqual(
            [],
            drifted,
            "These scorers changed without their revision being bumped: "
            f"{drifted}. Bump the revision in SCORERS, then regenerate the lock with "
            "`python -m acceptance_lab.scorer_digest`. Do not regenerate it alone -- "
            "that records the change while erasing the fact that it happened.",
        )

    def test_the_locked_revision_matches_the_registry(self) -> None:
        recorded = recorded_lock()
        self.assertEqual(
            scorer_revisions(),
            {name: entry["revision"] for name, entry in recorded.items()},
        )

    def test_the_generator_reproduces_the_committed_lock(self) -> None:
        self.assertEqual(dict(recorded_lock()), current_lock())

    def test_a_changed_scorer_is_actually_detected(self) -> None:
        """The lock is only a gate if the digest moves for the edits that matter.

        A comparison flipped from `>=` to `>` changes verdicts and changes nothing a
        reader notices in a diff summary. That is the case this must catch -- and it
        must catch it while ignoring the rewording and reformatting that would
        otherwise force a revision bump for no change in meaning.
        """
        original = """
        def a_scorer(value: int) -> bool:
            \"\"\"Doc.\"\"\"
            # a comment
            return value >= 1
        """
        reworded = """
        def a_scorer(value: int) -> bool:
            \"\"\"An entirely different docstring, at length.\"\"\"
            # a completely different comment
            return value >= 1
        """
        reformatted = """
        def a_scorer(
            value: int,
        ) -> bool:
            \"\"\"Doc.\"\"\"
            return value >= 1
        """
        edited = """
        def a_scorer(value: int) -> bool:
            \"\"\"Doc.\"\"\"
            # a comment
            return value > 1
        """
        self.assertEqual(digest_source(original), digest_source(reworded))
        self.assertEqual(digest_source(original), digest_source(reformatted))
        self.assertNotEqual(digest_source(original), digest_source(edited))

    def test_the_digest_reads_a_live_function(self) -> None:
        """`scorer_digest` is what the lock actually runs, so it is exercised too."""
        for spec in SCORERS.values():
            self.assertEqual(64, len(scorer_digest(spec.scorer)))


class RecordedRevisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = Scenario.from_dict(asset_dict("change-with-verification.json"))
        self.output = CandidateOutput.from_dict(asset_dict("trajectory-good.json"))

    def test_each_score_carries_the_revision_that_produced_it(self) -> None:
        result = evaluate_candidate(self.scenario, self.output, "verified")
        for score in result.scores:
            self.assertEqual(SCORERS[score.check_type].revision, score.scorer_revision)

    def test_the_run_pins_only_the_scorers_it_used(self) -> None:
        """Adding a fourteenth scorer must not make an old three-scorer run incomparable."""
        result = evaluate_candidate(self.scenario, self.output, "verified")
        used = {check.type for check in self.scenario.checks}
        self.assertEqual(used, set(result.scorer_revisions))
        self.assertLess(len(result.scorer_revisions), len(SCORERS))

    def test_the_revision_reaches_the_event_log_and_the_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.db")
            result = evaluate_candidate(self.scenario, self.output, "verified")
            store.record_evaluation(
                result,
                scenario_snapshot=asset_dict("change-with-verification.json"),
                output_snapshot=asset_dict("trajectory-good.json"),
            )
            started = next(
                event for event in store.events(stream_id=result.run_id)
                if event["event_type"] == "run.started"
            )
            self.assertEqual(
                dict(result.scorer_revisions), started["payload"]["scorer_revisions"]
            )
            for score in store.get_scores(result.run_id):
                self.assertEqual(1, score["scorer_revision"])
            self.assertIn("@1`", render_run_markdown(store, result.run_id))


class ComparabilityTests(unittest.TestCase):
    """Pinning without refusing is decoration."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = EventStore(Path(self.directory.name) / "events.db")
        self.scenario_doc = asset_dict("change-with-verification.json")
        self.output_doc = asset_dict("trajectory-good.json")
        self.scenario = Scenario.from_dict(self.scenario_doc)
        self.output = CandidateOutput.from_dict(self.output_doc)

    def _record(self, candidate: str) -> str:
        result = evaluate_candidate(self.scenario, self.output, candidate)
        self.store.record_evaluation(
            result,
            scenario_snapshot=self.scenario_doc,
            output_snapshot=self.output_doc,
        )
        return result.run_id

    def _rewrite_recorded_revision(self, run_id: str, revision: int | None) -> None:
        """Force a revision mismatch the way one would actually arise: a run recorded by
        a different build. The event log is append-only and is not touched -- only the
        disposable projection is rewritten, which is the honest way to simulate reading
        a store that another version of this package wrote."""
        with self.store.connect() as connection:
            with connection:
                connection.execute(
                    "UPDATE projection_scores SET scorer_revision = ? WHERE run_id = ?",
                    (revision, run_id),
                )

    def test_matching_revisions_compare(self) -> None:
        baseline, candidate = self._record("baseline"), self._record("candidate")
        payload = compare_payload(self.store, baseline, candidate)
        self.assertEqual([], payload["regressions"])
        self.assertTrue(payload["scorer_revisions"])

    def test_a_differing_revision_refuses_to_compare(self) -> None:
        baseline, candidate = self._record("baseline"), self._record("candidate")
        self._rewrite_recorded_revision(baseline, 2)
        with self.assertRaises(ValueError) as caught:
            compare_payload(self.store, baseline, candidate)
        message = str(caught.exception)
        self.assertIn("not comparable", message)
        self.assertIn("baseline=2", message)
        self.assertIn("candidate=1", message)

    def test_an_unrecorded_revision_is_not_treated_as_a_match(self) -> None:
        """Two runs from before the pin existed are not comparable just because both
        are silent about it. Unknown is not equal."""
        baseline, candidate = self._record("baseline"), self._record("candidate")
        self._rewrite_recorded_revision(baseline, None)
        self._rewrite_recorded_revision(candidate, None)
        with self.assertRaises(ValueError) as caught:
            compare_payload(self.store, baseline, candidate)
        self.assertIn("unrecorded", str(caught.exception))


class LegacyStoreTests(unittest.TestCase):
    """The event log is authoritative and append-only, so runs recorded before the pin
    existed must stay readable -- and must not have a revision invented for them."""

    def test_a_run_recorded_before_the_pin_reads_back_as_unrecorded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.db")
            run_id = "legacy-run"
            # Exactly the payloads an older build wrote: no scorer_revisions on the run,
            # no scorer_revision on the score.
            store.append_event(
                stream_id=run_id,
                event_type="run.started",
                payload={
                    "run_id": run_id,
                    "scenario_id": "legacy",
                    "scenario_version": "1.0.0",
                    "candidate": "legacy-candidate",
                    "started_at": "2026-08-01T00:00:00+00:00",
                    "metadata": {},
                    "scenario_hash": "0" * 64,
                    "output_hash": "1" * 64,
                    "scenario_snapshot": {},
                    "output_snapshot": {},
                },
            )
            store.append_event(
                stream_id=run_id,
                event_type="score.recorded",
                payload={
                    "run_id": run_id,
                    "check_id": "a-check",
                    "check_type": "required_fact_coverage",
                    "dimension": "quality",
                    "score": 1.0,
                    "passed": True,
                    "hard_gate": True,
                    "summary": "1/1 required facts present",
                    "details": {},
                },
            )
            store.append_event(
                stream_id=run_id,
                event_type="run.completed",
                payload={
                    "run_id": run_id,
                    "status": "PASS",
                    "aggregate_score": 1.0,
                    "completed_at": "2026-08-01T00:00:01+00:00",
                },
            )
            store.rebuild_projections()

            run = store.get_run(run_id)
            self.assertEqual("PASS", run["status"])
            self.assertEqual({}, json.loads(run["scorer_revisions_json"]))
            self.assertIsNone(store.get_scores(run_id)[0]["scorer_revision"])

            # And it renders, rather than raising on a field it does not have.
            self.assertIn("@unrecorded", render_run_markdown(store, run_id))


if __name__ == "__main__":
    unittest.main()


class HarnessRevisionTests(unittest.TestCase):
    """The scorers are not the whole judgement.

    `score_candidate` decides whether a score clears its threshold and
    `evaluate_candidate` decides PASS / CONDITIONAL / FAIL. Change either and every
    recorded verdict means something new with no scorer having moved -- which is what
    testing the scorer lock with the wrong kind of edit revealed: flipping `>=` to `>`
    in `score_candidate` rewrote every verdict and the lock stayed green.
    """

    def test_the_harness_is_locked_too(self) -> None:
        self.assertEqual(dict(recorded_harness_lock()), current_harness_lock())

    def test_the_locked_harness_revision_matches_the_module(self) -> None:
        self.assertEqual(
            EVALUATION_HARNESS_REVISION, recorded_harness_lock()["revision"]
        )

    def test_the_run_records_the_harness_revision(self) -> None:
        scenario = Scenario.from_dict(asset_dict("change-with-verification.json"))
        output = CandidateOutput.from_dict(asset_dict("trajectory-good.json"))
        result = evaluate_candidate(scenario, output, "verified")
        self.assertEqual(EVALUATION_HARNESS_REVISION, result.harness_revision)

    def test_a_differing_harness_revision_refuses_to_compare(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.db")
            scenario_doc = asset_dict("change-with-verification.json")
            output_doc = asset_dict("trajectory-good.json")
            scenario = Scenario.from_dict(scenario_doc)
            output = CandidateOutput.from_dict(output_doc)
            runs = []
            for candidate in ("baseline", "candidate"):
                result = evaluate_candidate(scenario, output, candidate)
                store.record_evaluation(
                    result, scenario_snapshot=scenario_doc, output_snapshot=output_doc
                )
                runs.append(result.run_id)
            with store.connect() as connection:
                with connection:
                    connection.execute(
                        "UPDATE projection_runs SET harness_revision = 2 WHERE run_id = ?",
                        (runs[0],),
                    )
            with self.assertRaises(ValueError) as caught:
                compare_payload(store, runs[0], runs[1])
            self.assertIn("evaluation-harness revisions", str(caught.exception))
