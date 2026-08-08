import unittest

from app.evaluation.metrics import citation_metrics, output_metrics, ranking_metrics


class RankingMetricsTest(unittest.TestCase):
    def test_hand_calculated_ranking_metrics(self):
        result = ranking_metrics(["wrong", "a", "b"], ["a", "b"])
        self.assertEqual(result["recall"], 1.0)
        self.assertAlmostEqual(result["precision"], 2 / 3)
        self.assertEqual(result["mrr"], 0.5)
        self.assertGreater(result["ndcg"], 0.6)
        self.assertLess(result["ndcg"], 1.0)

    def test_unlabelled_case_is_excluded(self):
        self.assertEqual(ranking_metrics(["a"], []), {})


class DeterministicAnswerMetricsTest(unittest.TestCase):
    def test_output_mismatches_are_field_level(self):
        score, mismatches = output_metrics({"answer": 2, "ignored": True}, {"answer": 3}, ["answer"])
        self.assertEqual(score, 0.0)
        self.assertEqual(mismatches, [{"field": "answer", "expected": 3, "actual": 2}])

    def test_invented_citation_is_rejected(self):
        retrieved = [{"source_id": "S1", "document_id": "doc-1"}]
        citations = [{"source_id": "S9", "document_id": "doc-1"}]
        result = citation_metrics(citations, retrieved, ["doc-1"])
        self.assertEqual(result["citation_validity"], 0.0)
        self.assertEqual(result["citation_precision"], 0.0)
        self.assertEqual(result["citation_recall"], 0.0)
        self.assertEqual(result["invented_source_count"], 1)

    def test_valid_citation_covers_expected_document(self):
        retrieved = [{"source_id": "S1", "document_id": "doc-1"}]
        result = citation_metrics(retrieved, retrieved, ["doc-1"])
        self.assertEqual(result["citation_precision"], 1.0)
        self.assertEqual(result["citation_recall"], 1.0)


if __name__ == "__main__":
    unittest.main()
