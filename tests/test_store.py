from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from acceptance_lab.models import CandidateOutput, Scenario
from acceptance_lab.scoring import evaluate_candidate
from acceptance_lab.store import EventStore, StoreIntegrityError
from tests.helpers import asset_dict


class EventStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "events.db"
        self.store = EventStore(self.path)
        scenario_raw = asset_dict("change-with-verification.json")
        output_raw = asset_dict("trajectory-good.json")
        self.scenario = Scenario.from_dict(scenario_raw)
        self.output = CandidateOutput.from_dict(output_raw)
        self.result = evaluate_candidate(
            self.scenario, self.output, "verified", run_id="run-1"
        )
        self.store.record_evaluation(
            self.result,
            scenario_snapshot=scenario_raw,
            output_snapshot=output_raw,
        )

    def test_chain_and_projection_rebuild(self) -> None:
        valid, detail = self.store.verify_chain()
        self.assertTrue(valid, detail)
        started = self.store.events(stream_id="run-1")[0]["payload"]
        self.assertEqual("change-with-verification", started["scenario_snapshot"]["id"])
        self.assertEqual("1", started["output_snapshot"]["schema_version"])
        with self.store.connect() as connection:
            with connection:
                connection.execute("DELETE FROM projection_scores")
                connection.execute("DELETE FROM projection_runs")
        self.store.rebuild_projections()
        self.assertEqual("PASS", self.store.get_run("run-1")["status"])
        self.assertGreater(len(self.store.get_scores("run-1")), 0)

    def test_tampering_is_detected_and_blocks_rebuild(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "UPDATE events SET payload_json = ? WHERE seq = 1",
                ('{"tampered":true}',),
            )
            connection.commit()
        valid, detail = self.store.verify_chain()
        self.assertFalse(valid)
        self.assertIn("hash mismatch", detail)
        with self.assertRaises(StoreIntegrityError):
            self.store.rebuild_projections()


if __name__ == "__main__":
    unittest.main()
