import unittest

from app.modules.knowledge.domain import KnowledgeBaseStatus, normalize_knowledge_base_name


class KnowledgeBaseDomainTest(unittest.TestCase):
    def test_name_is_trimmed_and_internal_whitespace_is_normalized(self):
        self.assertEqual("Product Manuals", normalize_knowledge_base_name("  Product   Manuals  "))

    def test_blank_name_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "required"):
            normalize_knowledge_base_name("   ")

    def test_status_values_are_stable_api_values(self):
        self.assertEqual(["active", "archived"], [status.value for status in KnowledgeBaseStatus])


if __name__ == "__main__":
    unittest.main()
