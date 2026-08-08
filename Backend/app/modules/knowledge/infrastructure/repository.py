from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import ContentItem, KnowledgeBase


class SqlAlchemyKnowledgeBaseRepository:
    """Every operation requires a tenant ID; unscoped reads are intentionally absent."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_owned(self, user_id: str, status: str) -> list[tuple[KnowledgeBase, int]]:
        return (
            self.session.query(KnowledgeBase, func.count(ContentItem.id))
            .outerjoin(ContentItem, ContentItem.knowledge_base_id == KnowledgeBase.id)
            .filter(KnowledgeBase.user_id == user_id, KnowledgeBase.status == status)
            .group_by(KnowledgeBase.id)
            .order_by(KnowledgeBase.name.asc(), KnowledgeBase.id.asc())
            .all()
        )

    def get_owned(self, knowledge_base_id: str, user_id: str) -> KnowledgeBase | None:
        return (
            self.session.query(KnowledgeBase)
            .filter(KnowledgeBase.id == knowledge_base_id, KnowledgeBase.user_id == user_id)
            .first()
        )

    def get_legacy_agent_base(self, agent_id: str, user_id: str) -> KnowledgeBase | None:
        return (
            self.session.query(KnowledgeBase)
            .filter(KnowledgeBase.legacy_agent_id == agent_id, KnowledgeBase.user_id == user_id)
            .first()
        )

    def active_name_exists(self, user_id: str, name: str, excluding_id: str | None = None) -> bool:
        query = self.session.query(KnowledgeBase.id).filter(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.status == "active",
            func.lower(KnowledgeBase.name) == name.lower(),
        )
        if excluding_id:
            query = query.filter(KnowledgeBase.id != excluding_id)
        return query.first() is not None

    def document_count(self, knowledge_base_id: str) -> int:
        return self.session.query(func.count(ContentItem.id)).filter(
            ContentItem.knowledge_base_id == knowledge_base_id
        ).scalar() or 0

    def list_content(self, knowledge_base_id: str, user_id: str) -> list[ContentItem]:
        return (
            self.session.query(ContentItem)
            .filter(ContentItem.knowledge_base_id == knowledge_base_id, ContentItem.user_id == user_id)
            .order_by(ContentItem.filename.asc(), ContentItem.id.asc())
            .all()
        )

    def add(self, knowledge_base: KnowledgeBase) -> None:
        self.session.add(knowledge_base)
