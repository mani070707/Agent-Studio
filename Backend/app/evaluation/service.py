from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import (Agent, AgentVersion, AgentVersionKnowledgeBase, ContentItem, DocumentChunk,
                           EvaluationCase, EvaluationDataset, EvaluationRun)
from app.observability.service import emit


class EvaluationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def owned_dataset(self, dataset_id: str, user_id: str, *, active: bool = False) -> EvaluationDataset:
        query = self.db.query(EvaluationDataset).filter(EvaluationDataset.id == dataset_id,
                                                         EvaluationDataset.user_id == user_id)
        if active:
            query = query.filter(EvaluationDataset.status == "active")
        dataset = query.first()
        if not dataset:
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        return dataset

    def validate_evidence(self, user_id: str, document_ids: list[str], chunk_ids: list[str],
                          *, bound_base_ids: list[str] | None = None) -> None:
        if len(set(document_ids)) != len(document_ids) or len(set(chunk_ids)) != len(chunk_ids):
            raise HTTPException(status_code=422, detail="Expected evidence identifiers must be unique")
        if document_ids:
            query = self.db.query(ContentItem.id).filter(ContentItem.user_id == user_id,
                                                         ContentItem.id.in_(document_ids))
            if bound_base_ids is not None:
                query = query.filter(ContentItem.knowledge_base_id.in_(bound_base_ids))
            if {row[0] for row in query.all()} != set(document_ids):
                raise HTTPException(status_code=422, detail="Expected documents must be owned and bound to this version")
        if chunk_ids:
            query = self.db.query(DocumentChunk.id).filter(DocumentChunk.user_id == user_id,
                                                           DocumentChunk.id.in_(chunk_ids))
            if bound_base_ids is not None:
                query = query.filter(DocumentChunk.knowledge_base_id.in_(bound_base_ids))
            if {row[0] for row in query.all()} != set(chunk_ids):
                raise HTTPException(status_code=422, detail="Expected chunks must be owned and bound to this version")

    def queue(self, agent_id: str, version_id: str, dataset_id: str, user_id: str) -> EvaluationRun:
        agent = self.db.query(Agent).filter(Agent.id == agent_id, Agent.user_id == user_id).first()
        version = self.db.query(AgentVersion).filter(AgentVersion.id == version_id,
                                                     AgentVersion.agent_id == agent_id,
                                                     AgentVersion.user_id == user_id).first()
        if not agent or not version:
            raise HTTPException(status_code=404, detail="Agent version not found")
        dataset = self.owned_dataset(dataset_id, user_id, active=True)
        if dataset.agent_id != agent_id:
            raise HTTPException(status_code=422, detail="Dataset belongs to another agent")
        cases = self.db.query(EvaluationCase).filter(EvaluationCase.dataset_id == dataset.id).order_by(EvaluationCase.id).all()
        if not cases:
            raise HTTPException(status_code=400, detail="Dataset has no cases")
        base_ids = [row.knowledge_base_id for row in self.db.query(AgentVersionKnowledgeBase).filter(
            AgentVersionKnowledgeBase.agent_version_id == version.id,
            AgentVersionKnowledgeBase.user_id == user_id).all()]
        for case in cases:
            self.validate_evidence(user_id, case.expected_document_ids or [], case.expected_chunk_ids or [],
                                   bound_base_ids=base_ids)
        now = datetime.now(timezone.utc)
        snapshot = [{"id": case.id, "input": case.input, "expected_output": case.expected_output,
                     "compare_fields": case.compare_fields or [],
                     "expected_document_ids": case.expected_document_ids or [],
                     "expected_chunk_ids": case.expected_chunk_ids or [], "retrieval_k": case.retrieval_k}
                    for case in cases]
        config = {
            "dataset_updated_at": dataset.updated_at.isoformat(),
            "thresholds": {"case_pass_rate": dataset.threshold,
                           "retrieval_recall": dataset.retrieval_recall_threshold,
                           "citation_precision": dataset.citation_precision_threshold,
                           "grounding_compliance": dataset.grounding_threshold},
            "retrieval_config": version.retrieval_config,
        }
        evaluation = EvaluationRun(user_id=user_id, agent_version_id=version.id, dataset_id=dataset.id,
                                   status="queued", total_cases=len(snapshot), dataset_snapshot=snapshot,
                                   config_snapshot=config, available_at=now, created_at=now)
        self.db.add(evaluation)
        self.db.flush()
        emit(self.db, user_id=user_id, resource_type="evaluation", resource_id=evaluation.id,
             event_type="queued", payload={"total_cases": len(snapshot)})
        self.db.commit()
        self.db.refresh(evaluation)
        return evaluation

    def owned_run(self, evaluation_id: str, user_id: str) -> EvaluationRun:
        evaluation = self.db.query(EvaluationRun).filter(EvaluationRun.id == evaluation_id,
                                                         EvaluationRun.user_id == user_id).first()
        if not evaluation:
            raise HTTPException(status_code=404, detail="Evaluation run not found")
        return evaluation
