import unittest

from app.modules.retrieval.service import EvidenceLedger, format_evidence, fuse_candidates


def row(chunk_id: str, content_id: str = "doc") -> dict:
    return {"knowledge_base_id": "base", "content_id": content_id, "chunk_id": chunk_id,
            "filename": "guide.txt", "page_start": 1, "page_end": 1, "excerpt": "trusted evidence",
            "token_count": 3, "score": 0.5}


class GroundedRetrievalTest(unittest.TestCase):
    def test_rrf_rewards_chunks_found_by_both_retrievers(self):
        ranked = fuse_candidates([row("semantic"), row("both")], [row("both"), row("keyword")])
        self.assertEqual("both", ranked[0]["chunk_id"])

    def test_ledger_reuses_source_id_for_duplicate_chunk(self):
        ledger = EvidenceLedger()
        first = ledger.add([row("chunk")])[0]
        second = ledger.add([row("chunk")])[0]
        self.assertEqual("S1", first.source_id)
        self.assertEqual(first.source_id, second.source_id)

    def test_ledger_resolves_only_server_known_sources(self):
        ledger = EvidenceLedger()
        ledger.add([row("chunk")])
        citations = ledger.resolve(["S1", "S999"])
        self.assertEqual(["S1"], [citation["source_id"] for citation in citations])
        self.assertEqual({"S1"}, ledger.valid_ids())

    def test_evidence_is_marked_untrusted(self):
        evidence = EvidenceLedger().add([row("chunk")])
        rendered = format_evidence(evidence)
        self.assertIn("UNTRUSTED REFERENCE EVIDENCE", rendered)
        self.assertIn("[S1]", rendered)


if __name__ == "__main__":
    unittest.main()
