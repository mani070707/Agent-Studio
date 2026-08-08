import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Agent, KnowledgeBase
from app.modules.knowledge.domain import KnowledgeBaseRecord, KnowledgeBaseStatus, normalize_knowledge_base_name
from app.modules.knowledge.infrastructure import SqlAlchemyKnowledgeBaseRepository


class KnowledgeBaseNotFound(LookupError):
    pass


class KnowledgeBaseConflict(ValueError):
    pass


class KnowledgeBaseService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SqlAlchemyKnowledgeBaseRepository(session)

    def list(self, user_id: str, status: KnowledgeBaseStatus) -> list[KnowledgeBaseRecord]:
        return [self._record(row, count) for row, count in self.repository.list_owned(user_id, status.value)]

    def get(self, knowledge_base_id: str, user_id: str) -> KnowledgeBaseRecord:
        row = self.require_owned(knowledge_base_id, user_id)
        return self._record(row, self.repository.document_count(row.id))

    def create(self, name: str, description: str, user_id: str) -> KnowledgeBaseRecord:
        normalized = normalize_knowledge_base_name(name)
        if self.repository.active_name_exists(user_id, normalized):
            raise KnowledgeBaseConflict("An active knowledge base with this name already exists")
        now = datetime.now(timezone.utc)
        row = KnowledgeBase(id=str(uuid.uuid4()), user_id=user_id, name=normalized,
                            description=description.strip(), status=KnowledgeBaseStatus.ACTIVE.value,
                            legacy_agent_id=None, created_at=now, updated_at=now)
        self.repository.add(row)
        self._commit_or_conflict()
        return self._record(row, 0)

    def update(self, knowledge_base_id: str, name: str, description: str, user_id: str) -> KnowledgeBaseRecord:
        row = self.require_owned(knowledge_base_id, user_id)
        self._require_active(row)
        normalized = normalize_knowledge_base_name(name)
        if self.repository.active_name_exists(user_id, normalized, excluding_id=row.id):
            raise KnowledgeBaseConflict("An active knowledge base with this name already exists")
        row.name = normalized
        row.description = description.strip()
        row.updated_at = datetime.now(timezone.utc)
        self._commit_or_conflict()
        return self._record(row, self.repository.document_count(row.id))

    def archive(self, knowledge_base_id: str, user_id: str) -> None:
        row = self.require_owned(knowledge_base_id, user_id)
        self._require_active(row)
        row.status = KnowledgeBaseStatus.ARCHIVED.value
        row.updated_at = datetime.now(timezone.utc)
        self.session.commit()

    def list_content(self, knowledge_base_id: str, user_id: str):
        self.require_owned(knowledge_base_id, user_id)
        return self.repository.list_content(knowledge_base_id, user_id)

    def require_active(self, knowledge_base_id: str, user_id: str) -> KnowledgeBase:
        row = self.require_owned(knowledge_base_id, user_id)
        self._require_active(row)
        return row

    def resolve_legacy_agent_base(self, agent_id: str, user_id: str) -> KnowledgeBase:
        agent = self.session.query(Agent).filter(Agent.id == agent_id, Agent.user_id == user_id).first()
        if not agent:
            raise KnowledgeBaseNotFound("Agent not found")
        existing = self.repository.get_legacy_agent_base(agent_id, user_id)
        if existing:
            self._require_active(existing)
            return existing
        base_name = normalize_knowledge_base_name(f"{agent.name} Knowledge")
        if self.repository.active_name_exists(user_id, base_name):
            base_name = normalize_knowledge_base_name(f"{agent.name} Knowledge ({agent.id[:8]})")
        now = datetime.now(timezone.utc)
        row = KnowledgeBase(id=str(uuid.uuid4()), user_id=user_id, name=base_name,
                            description="Created for legacy agent content.", status="active",
                            legacy_agent_id=agent.id, created_at=now, updated_at=now)
        self.repository.add(row)
        self._commit_or_conflict()
        return row

    def require_owned(self, knowledge_base_id: str, user_id: str) -> KnowledgeBase:
        row = self.repository.get_owned(knowledge_base_id, user_id)
        if not row:
            raise KnowledgeBaseNotFound("Knowledge base not found")
        return row

    @staticmethod
    def _require_active(row: KnowledgeBase) -> None:
        if row.status != KnowledgeBaseStatus.ACTIVE.value:
            raise KnowledgeBaseConflict("Archived knowledge bases are immutable")

    def _commit_or_conflict(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise KnowledgeBaseConflict("Knowledge base conflicts with an existing record") from exc

    @staticmethod
    def _record(row: KnowledgeBase, count: int) -> KnowledgeBaseRecord:
        return KnowledgeBaseRecord(row.id, row.name, row.description, KnowledgeBaseStatus(row.status),
                                   count, row.created_at, row.updated_at)
