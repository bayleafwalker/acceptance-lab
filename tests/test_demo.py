from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from acceptance_lab.demo import run_demo
from acceptance_lab.reporting import compare_payload
from acceptance_lab.store import EventStore


class DemoTests(unittest.TestCase):
    def test_demo_produces_two_fail_to_pass_comparisons(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            run_ids = run_demo(root)
            store = EventStore(root / "acceptance.db")
            retrieval = compare_payload(
                store,
                run_ids["retrieval_naive"],
                run_ids["retrieval_authority_aware"],
            )
            trajectory = compare_payload(
                store,
                run_ids["trajectory_unsafe"],
                run_ids["trajectory_verified"],
            )
            self.assertEqual("FAIL", retrieval["baseline"]["status"])
            self.assertEqual("PASS", retrieval["candidate"]["status"])
            self.assertGreater(retrieval["status_delta"], 0)
            self.assertEqual("FAIL", trajectory["baseline"]["status"])
            self.assertEqual("PASS", trajectory["candidate"]["status"])
            self.assertGreater(trajectory["status_delta"], 0)
            self.assertTrue((root / "reports" / "summary.md").exists())
            persisted = json.loads((root / "run-ids.json").read_text())
            self.assertEqual(run_ids, persisted)


if __name__ == "__main__":
    unittest.main()
