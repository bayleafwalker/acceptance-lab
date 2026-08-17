from __future__ import annotations

import unittest

from acceptance_lab.models import Scenario
from acceptance_lab.retrieval import Document, candidate_from_retrieval, retrieve
from acceptance_lab.scoring import evaluate_candidate
from tests.helpers import asset_dict, asset_list


class RetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = Scenario.from_dict(asset_dict("current-authority.json"))
        self.documents = tuple(Document.from_dict(item) for item in asset_list("documents.json"))

    def test_naive_retrieval_prefers_superseded_semantic_match(self) -> None:
        output = candidate_from_retrieval(
            self.scenario, self.documents, authority_aware=False
        )
        result = evaluate_candidate(self.scenario, output, "naive")
        self.assertEqual("adr-outctl-compression-v1", output.citations[0].id)
        self.assertEqual("FAIL", result.status)

    def test_authority_filter_changes_admissible_result(self) -> None:
        output = candidate_from_retrieval(
            self.scenario, self.documents, authority_aware=True
        )
        result = evaluate_candidate(self.scenario, output, "authority-aware")
        self.assertEqual("adr-outctl-pivot-v4", output.citations[0].id)
        self.assertEqual("PASS", result.status)


if __name__ == "__main__":
    unittest.main()
