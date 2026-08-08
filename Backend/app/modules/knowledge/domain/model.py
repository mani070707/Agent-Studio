from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class KnowledgeBaseStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


def normalize_knowledge_base_name(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("Knowledge base name is required")
    if len(normalized) > 160:
        raise ValueError("Knowledge base name must be 160 characters or fewer")
    return normalized


@dataclass(frozen=True, slots=True)
class KnowledgeBaseRecord:
    id: str
    name: str
    description: str
    status: KnowledgeBaseStatus
    document_count: int
    created_at: datetime
    updated_at: datetime
