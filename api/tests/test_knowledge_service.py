import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import ContentItem, KnowledgeBase
from app.modules.knowledge.application import KnowledgeBaseConflict, KnowledgeBaseNotFound, KnowledgeBaseService
from app.modules.knowledge.domain import KnowledgeBaseStatus


class KnowledgeBaseServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        KnowledgeBase.__table__.create(self.engine)
        ContentItem.__table__.create(self.engine)
        self.session = Session(self.engine)
        self.service = KnowledgeBaseService(self.session)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_create_normalizes_and_list_is_tenant_scoped(self):
        created = self.service.create("  Product   Manuals ", " Docs ", "tenant-a")
        self.service.create("Private", "", "tenant-b")
        visible = self.service.list("tenant-a", KnowledgeBaseStatus.ACTIVE)
        self.assertEqual([created.id], [item.id for item in visible])
        self.assertEqual("Product Manuals", visible[0].name)

    def test_duplicate_active_name_is_case_insensitive(self):
        self.service.create("Policies", "", "tenant-a")
        with self.assertRaises(KnowledgeBaseConflict):
            self.service.create(" policies ", "", "tenant-a")

    def test_archive_preserves_content_and_blocks_mutation(self):
        created = self.service.create("Policies", "", "tenant-a")
        self.session.add(ContentItem(id="doc-1", user_id="tenant-a", agent_id=None,
                                     knowledge_base_id=created.id, filename="policy.txt",
                                     storage_path="tenant-a/path", extracted_text="content"))
        self.session.commit()
        self.service.archive(created.id, "tenant-a")
        archived = self.service.list("tenant-a", KnowledgeBaseStatus.ARCHIVED)
        self.assertEqual(1, archived[0].document_count)
        with self.assertRaises(KnowledgeBaseConflict):
            self.service.update(created.id, "Changed", "", "tenant-a")

    def test_cross_tenant_lookup_looks_not_found(self):
        created = self.service.create("Policies", "", "tenant-a")
        with self.assertRaises(KnowledgeBaseNotFound):
            self.service.get(created.id, "tenant-b")


if __name__ == "__main__":
    unittest.main()
