from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.crud_helpers import get_owned_or_404
from app.db.models import (Agent, AgentVersion, EvaluationCase, EvaluationCaseResult, EvaluationDataset,
                           EvaluationRun)
from app.db.session import get_db
from app.evaluation.service import EvaluationService

router = APIRouter(tags=["evaluation"])


class DatasetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    threshold: float = Field(default=0.9, ge=0, le=1)
    retrieval_recall_threshold: float = Field(default=0.8, ge=0, le=1)
    citation_precision_threshold: float = Field(default=1.0, ge=0, le=1)
    grounding_threshold: float = Field(default=1.0, ge=0, le=1)


class DatasetOut(DatasetIn):
    id: str
    agent_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class CaseIn(BaseModel):
    input: dict
    expected_output: dict
    compare_fields: list[str] = []
    expected_document_ids: list[str] = []
    expected_chunk_ids: list[str] = []
    retrieval_k: int = Field(default=6, ge=1, le=20)


class CaseOut(CaseIn):
    id: str
    dataset_id: str


class EvaluationRunOut(BaseModel):
    id: str
    agent_version_id: str
    dataset_id: str
    score: float
    status: str
    completed_cases: int
    total_cases: int
    metrics: dict
    gate_results: dict
    error_code: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class CaseResultOut(BaseModel):
    id: str
    evaluation_case_id: str
    run_id: str | None
    status: str
    retrieved_sources: list
    expected_evidence: dict
    metrics: dict
    field_mismatches: list
    latency_ms: int
    token_usage: dict
    error_code: str | None
    error_message: str | None


@router.post("/agents/{agent_id}/evaluation-datasets", response_model=DatasetOut, status_code=201)
def create_dataset(agent_id: str, body: DatasetIn, db: Session = Depends(get_db),
                   user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, Agent, agent_id, user_id)
    now = datetime.now(timezone.utc)
    dataset = EvaluationDataset(agent_id=agent_id, user_id=user_id, status="active", created_at=now,
                                updated_at=now, **body.model_dump())
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


@router.get("/agents/{agent_id}/evaluation-datasets", response_model=list[DatasetOut])
def list_datasets(agent_id: str, status: str = "active", db: Session = Depends(get_db),
                  user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, Agent, agent_id, user_id)
    if status not in {"active", "archived"}:
        raise HTTPException(status_code=422, detail="Invalid dataset status")
    return (db.query(EvaluationDataset).filter(EvaluationDataset.agent_id == agent_id,
                                               EvaluationDataset.user_id == user_id,
                                               EvaluationDataset.status == status)
            .order_by(EvaluationDataset.created_at, EvaluationDataset.id).all())


@router.put("/evaluation-datasets/{dataset_id}", response_model=DatasetOut)
def update_dataset(dataset_id: str, body: DatasetIn, db: Session = Depends(get_db),
                   user_id: str = Depends(get_current_user_id)):
    dataset = EvaluationService(db).owned_dataset(dataset_id, user_id, active=True)
    for key, value in body.model_dump().items():
        setattr(dataset, key, value)
    dataset.name = dataset.name.strip()
    dataset.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(dataset)
    return dataset


@router.delete("/evaluation-datasets/{dataset_id}", status_code=204)
def archive_dataset(dataset_id: str, db: Session = Depends(get_db),
                    user_id: str = Depends(get_current_user_id)):
    dataset = EvaluationService(db).owned_dataset(dataset_id, user_id, active=True)
    dataset.status = "archived"
    dataset.updated_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)


@router.post("/evaluation-datasets/{dataset_id}/cases", response_model=CaseOut, status_code=201)
def add_case(dataset_id: str, body: CaseIn, db: Session = Depends(get_db),
             user_id: str = Depends(get_current_user_id)):
    service = EvaluationService(db)
    dataset = service.owned_dataset(dataset_id, user_id, active=True)
    service.validate_evidence(user_id, body.expected_document_ids, body.expected_chunk_ids)
    case = EvaluationCase(dataset_id=dataset.id, **body.model_dump())
    db.add(case)
    dataset.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(case)
    return case


@router.get("/evaluation-datasets/{dataset_id}/cases", response_model=list[CaseOut])
def list_cases(dataset_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    dataset = EvaluationService(db).owned_dataset(dataset_id, user_id)
    return db.query(EvaluationCase).filter(EvaluationCase.dataset_id == dataset.id).order_by(EvaluationCase.id).all()


@router.put("/evaluation-cases/{case_id}", response_model=CaseOut)
def update_case(case_id: str, body: CaseIn, db: Session = Depends(get_db),
                user_id: str = Depends(get_current_user_id)):
    case = (db.query(EvaluationCase).join(EvaluationDataset, EvaluationDataset.id == EvaluationCase.dataset_id)
            .filter(EvaluationCase.id == case_id, EvaluationDataset.user_id == user_id,
                    EvaluationDataset.status == "active").first())
    if not case:
        raise HTTPException(status_code=404, detail="Evaluation case not found")
    EvaluationService(db).validate_evidence(user_id, body.expected_document_ids, body.expected_chunk_ids)
    for key, value in body.model_dump().items():
        setattr(case, key, value)
    dataset = db.query(EvaluationDataset).filter(EvaluationDataset.id == case.dataset_id).one()
    dataset.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(case)
    return case


@router.delete("/evaluation-cases/{case_id}", status_code=204)
def delete_case(case_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    case = (db.query(EvaluationCase).join(EvaluationDataset, EvaluationDataset.id == EvaluationCase.dataset_id)
            .filter(EvaluationCase.id == case_id, EvaluationDataset.user_id == user_id,
                    EvaluationDataset.status == "active").first())
    if not case:
        raise HTTPException(status_code=404, detail="Evaluation case not found")
    dataset = db.query(EvaluationDataset).filter(EvaluationDataset.id == case.dataset_id).one()
    db.delete(case)
    dataset.updated_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)


@router.post("/agents/{agent_id}/versions/{version_id}/evaluate", response_model=EvaluationRunOut, status_code=202)
def evaluate_version(agent_id: str, version_id: str, dataset_id: str, db: Session = Depends(get_db),
                     user_id: str = Depends(get_current_user_id)):
    return EvaluationService(db).queue(agent_id, version_id, dataset_id, user_id)


@router.get("/evaluation-runs/compare")
def compare_evaluations(baseline_id: str, candidate_id: str, db: Session = Depends(get_db),
                        user_id: str = Depends(get_current_user_id)):
    service = EvaluationService(db)
    baseline = service.owned_run(baseline_id, user_id)
    candidate = service.owned_run(candidate_id, user_id)
    if baseline.dataset_id != candidate.dataset_id:
        raise HTTPException(status_code=422, detail="Evaluations must use the same dataset")
    names = set((baseline.metrics or {})) | set((candidate.metrics or {}))
    deltas = {name: float((candidate.metrics or {}).get(name, 0)) - float((baseline.metrics or {}).get(name, 0))
              for name in names}
    baseline_cases = {row.evaluation_case_id: row for row in db.query(EvaluationCaseResult).filter(
        EvaluationCaseResult.evaluation_run_id == baseline.id, EvaluationCaseResult.user_id == user_id).all()}
    candidate_cases = {row.evaluation_case_id: row for row in db.query(EvaluationCaseResult).filter(
        EvaluationCaseResult.evaluation_run_id == candidate.id, EvaluationCaseResult.user_id == user_id).all()}

    def runtime_summary(evaluation, rows):
        version = db.query(AgentVersion).filter(AgentVersion.id == evaluation.agent_version_id,
                                                AgentVersion.user_id == user_id).first()
        count = max(len(rows), 1)
        return {
            "runtime_engine": (version.harness_config or {}).get("runtime_engine", "direct") if version else "direct",
            "average_latency_ms": sum(row.latency_ms for row in rows.values()) / count,
            "input_tokens": sum((row.token_usage or {}).get("input_tokens", 0) for row in rows.values()),
            "output_tokens": sum((row.token_usage or {}).get("output_tokens", 0) for row in rows.values()),
            "model_calls": sum((row.token_usage or {}).get("model_calls", 0) for row in rows.values()),
            "orchestration_overhead_ms": sum((row.token_usage or {}).get("orchestration_overhead_ms", 0)
                                             for row in rows.values()),
        }

    baseline_runtime = runtime_summary(baseline, baseline_cases)
    candidate_runtime = runtime_summary(candidate, candidate_cases)
    runtime_deltas = {name: candidate_runtime[name] - baseline_runtime[name] for name in (
        "average_latency_ms", "input_tokens", "output_tokens", "model_calls", "orchestration_overhead_ms")}
    behavioral = [case_id for case_id in baseline_cases.keys() & candidate_cases.keys()
                  if (baseline_cases[case_id].status, baseline_cases[case_id].error_code,
                      (baseline_cases[case_id].metrics or {}).get("citation_validity")) !=
                     (candidate_cases[case_id].status, candidate_cases[case_id].error_code,
                      (candidate_cases[case_id].metrics or {}).get("citation_validity"))]
    return {"baseline_id": baseline.id, "candidate_id": candidate.id, "deltas": deltas,
            "regressions": [name for name, delta in deltas.items() if delta < 0],
            "baseline_runtime": baseline_runtime, "candidate_runtime": candidate_runtime,
            "runtime_deltas": runtime_deltas, "behavioral_regression_case_ids": behavioral}


@router.get("/evaluation-runs/{evaluation_id}", response_model=EvaluationRunOut)
def get_evaluation(evaluation_id: str, db: Session = Depends(get_db),
                   user_id: str = Depends(get_current_user_id)):
    return EvaluationService(db).owned_run(evaluation_id, user_id)


@router.get("/evaluation-runs/{evaluation_id}/cases", response_model=list[CaseResultOut])
def evaluation_cases(evaluation_id: str, db: Session = Depends(get_db),
                     user_id: str = Depends(get_current_user_id)):
    EvaluationService(db).owned_run(evaluation_id, user_id)
    return (db.query(EvaluationCaseResult).filter(EvaluationCaseResult.evaluation_run_id == evaluation_id,
                                                  EvaluationCaseResult.user_id == user_id)
            .order_by(EvaluationCaseResult.created_at).all())


@router.get("/agents/{agent_id}/evaluation-runs", response_model=list[EvaluationRunOut])
def list_evaluations(agent_id: str, db: Session = Depends(get_db),
                     user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, Agent, agent_id, user_id)
    return (db.query(EvaluationRun).join(EvaluationDataset, EvaluationDataset.id == EvaluationRun.dataset_id)
            .filter(EvaluationDataset.agent_id == agent_id, EvaluationRun.user_id == user_id)
            .order_by(EvaluationRun.created_at.desc()).all())


@router.post("/evaluation-runs/{evaluation_id}/retry", response_model=EvaluationRunOut)
def retry_evaluation(evaluation_id: str, db: Session = Depends(get_db),
                     user_id: str = Depends(get_current_user_id)):
    evaluation = EvaluationService(db).owned_run(evaluation_id, user_id)
    if evaluation.status != "failed" or not evaluation.error_code:
        raise HTTPException(status_code=409, detail="Only infrastructure-failed evaluations can be retried")
    evaluation.status = "queued"
    evaluation.available_at = datetime.now(timezone.utc)
    evaluation.completed_at = None
    evaluation.error_code = evaluation.error_message = None
    db.commit()
    db.refresh(evaluation)
    return evaluation
