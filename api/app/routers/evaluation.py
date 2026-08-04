from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.crud_helpers import get_owned_or_404
from app.db.models import Agent, AgentVersion, EvaluationCase, EvaluationDataset, EvaluationRun, Run
from app.db.session import get_db
from app.runs.executor import execute_run

router = APIRouter(tags=["evaluation"])


class DatasetIn(BaseModel):
    name: str
    threshold: float = 0.9


class DatasetOut(DatasetIn):
    id: str
    agent_id: str


class CaseIn(BaseModel):
    input: dict
    expected_output: dict
    compare_fields: list[str] = []


class CaseOut(CaseIn):
    id: str
    dataset_id: str


class EvaluationRunOut(BaseModel):
    id: str
    agent_version_id: str
    dataset_id: str
    score: float
    status: str


@router.post("/agents/{agent_id}/evaluation-datasets", response_model=DatasetOut, status_code=201)
def create_dataset(
    agent_id: str, body: DatasetIn, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    get_owned_or_404(db, Agent, agent_id, user_id)
    dataset = EvaluationDataset(agent_id=agent_id, **body.model_dump())
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


@router.get("/agents/{agent_id}/evaluation-datasets", response_model=list[DatasetOut])
def list_datasets(agent_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, Agent, agent_id, user_id)
    return db.query(EvaluationDataset).filter(EvaluationDataset.agent_id == agent_id).all()


@router.post("/evaluation-datasets/{dataset_id}/cases", response_model=CaseOut, status_code=201)
def add_case(
    dataset_id: str, body: CaseIn, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    dataset = _get_owned_dataset(db, dataset_id, user_id)
    case = EvaluationCase(dataset_id=dataset.id, **body.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.get("/evaluation-datasets/{dataset_id}/cases", response_model=list[CaseOut])
def list_cases(dataset_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    dataset = _get_owned_dataset(db, dataset_id, user_id)
    return db.query(EvaluationCase).filter(EvaluationCase.dataset_id == dataset.id).all()


@router.post("/agents/{agent_id}/versions/{version_id}/evaluate", response_model=EvaluationRunOut)
async def evaluate_version(
    agent_id: str,
    version_id: str,
    dataset_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    get_owned_or_404(db, Agent, agent_id, user_id)
    version = db.query(AgentVersion).filter(AgentVersion.id == version_id, AgentVersion.agent_id == agent_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Agent version not found")
    dataset = _get_owned_dataset(db, dataset_id, user_id)
    cases = db.query(EvaluationCase).filter(EvaluationCase.dataset_id == dataset.id).all()
    if not cases:
        raise HTTPException(status_code=400, detail="Dataset has no cases")

    passed = 0
    for case in cases:
        run = Run(agent_version_id=version_id, user_id=user_id, input=case.input, status="pending")
        db.add(run)
        db.commit()
        db.refresh(run)
        await execute_run(db, run, version, agent_id, user_id)
        db.refresh(run)
        if run.status == "completed" and _matches_expected(run.output, case.expected_output, case.compare_fields):
            passed += 1

    score = passed / len(cases)
    status = "passed" if score >= dataset.threshold else "failed"
    eval_run = EvaluationRun(agent_version_id=version_id, dataset_id=dataset.id, score=score, status=status)
    db.add(eval_run)
    db.commit()
    db.refresh(eval_run)
    return eval_run


def _matches_expected(actual: dict | None, expected: dict, compare_fields: list[str]) -> bool:
    if actual is None:
        return False
    fields = compare_fields or list(expected.keys())
    return all(actual.get(f) == expected.get(f) for f in fields)


def _get_owned_dataset(db: Session, dataset_id: str, user_id: str) -> EvaluationDataset:
    dataset = (
        db.query(EvaluationDataset)
        .join(Agent, Agent.id == EvaluationDataset.agent_id)
        .filter(EvaluationDataset.id == dataset_id, Agent.user_id == user_id)
        .first()
    )
    if not dataset:
        raise HTTPException(status_code=404, detail="Evaluation dataset not found")
    return dataset
