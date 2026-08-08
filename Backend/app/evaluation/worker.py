import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from time import monotonic

from sqlalchemy import or_

from app.db.models import AgentVersion, EvaluationCaseResult, EvaluationRun, Run, RunStep
from app.evaluation.metrics import citation_metrics, output_metrics, ranking_metrics
from app.runs.executor import execute_run
from app.observability.service import emit, maybe_heartbeat


class EvaluationWorker:
    def __init__(self, session_factory, *, lease_seconds: int = 900) -> None:
        self.session_factory = session_factory
        self.lease_seconds = lease_seconds
        self.worker_id = str(uuid.uuid4())

    def run_once(self) -> bool:
        db = self.session_factory()
        try:
            maybe_heartbeat(self, db, "evaluation")
            evaluation = self._claim(db)
            if not evaluation:
                return False
            evaluation_id = evaluation.id
        finally:
            db.close()
        try:
            asyncio.run(self._process(evaluation_id))
        except Exception:
            self._retry_or_fail(evaluation_id)
        return True

    def _claim(self, db):
        now = datetime.now(timezone.utc)
        evaluation = (db.query(EvaluationRun)
                      .filter(EvaluationRun.available_at <= now,
                              or_(EvaluationRun.status.in_(["queued", "retry_wait"]),
                                  (EvaluationRun.status == "running") & (EvaluationRun.lease_until < now)))
                      .order_by(EvaluationRun.available_at, EvaluationRun.created_at)
                      .with_for_update(skip_locked=True).first())
        if not evaluation:
            db.rollback()
            return None
        evaluation.status = "running"
        evaluation.attempt_count += 1
        evaluation.lease_owner = self.worker_id
        evaluation.lease_until = now + timedelta(seconds=self.lease_seconds)
        evaluation.started_at = evaluation.started_at or now
        emit(db, user_id=evaluation.user_id, resource_type="evaluation", resource_id=evaluation.id,
             event_type="started", payload={"attempt": evaluation.attempt_count,
                                             "total_cases": evaluation.total_cases})
        db.commit()
        return evaluation

    async def _process(self, evaluation_id: str) -> None:
        db = self.session_factory()
        try:
            evaluation = db.query(EvaluationRun).filter(EvaluationRun.id == evaluation_id,
                                                        EvaluationRun.lease_owner == self.worker_id).first()
            if not evaluation:
                return
            version = db.query(AgentVersion).filter(AgentVersion.id == evaluation.agent_version_id,
                                                    AgentVersion.user_id == evaluation.user_id).first()
            if not version:
                raise RuntimeError("Evaluated agent version no longer exists")
            existing = {row.evaluation_case_id for row in db.query(EvaluationCaseResult).filter(
                EvaluationCaseResult.evaluation_run_id == evaluation.id).all()}
            for case in evaluation.dataset_snapshot:
                if case["id"] in existing:
                    continue
                started = monotonic()
                run = Run(agent_version_id=version.id, user_id=evaluation.user_id,
                          input=case["input"], status="pending")
                db.add(run)
                db.commit()
                db.refresh(run)
                await execute_run(db, run, version, version.agent_id, evaluation.user_id)
                db.refresh(run)
                evidence = self._retrieved_evidence(db, run.id)[:case.get("retrieval_k", 6)]
                expected_chunks = case.get("expected_chunk_ids") or []
                expected_documents = case.get("expected_document_ids") or []
                ranked_ids = ([item["chunk_id"] for item in evidence] if expected_chunks
                              else [item["document_id"] for item in evidence])
                ranking = ranking_metrics(ranked_ids, expected_chunks or expected_documents)
                citation = citation_metrics(run.citations or [], evidence, expected_documents)
                output_score, mismatches = output_metrics(run.output, case["expected_output"], case["compare_fields"])
                grounding = self._grounding_score(run, evidence)
                metrics = {**ranking, **citation, "output_match": output_score,
                           "grounding_compliance": grounding,
                           "document_diversity": len({item["document_id"] for item in evidence})}
                result = EvaluationCaseResult(
                    user_id=evaluation.user_id, evaluation_run_id=evaluation.id,
                    evaluation_case_id=case["id"], run_id=run.id,
                    status="passed" if run.status == "completed" and output_score == 1.0 else "failed",
                    retrieved_sources=evidence,
                    expected_evidence={"document_ids": expected_documents, "chunk_ids": expected_chunks},
                    metrics=metrics, field_mismatches=mismatches,
                    latency_ms=int((monotonic() - started) * 1000), token_usage=self._token_usage(db, run),
                    error_code=None if run.status == "completed" else (run.output or {}).get("failure", {}).get("code"),
                    error_message=None if run.status == "completed" else (run.output or {}).get("failure", {}).get("reason"),
                )
                db.add(result)
                evaluation.completed_cases += 1
                emit(db, user_id=evaluation.user_id, resource_type="evaluation", resource_id=evaluation.id,
                     event_type="progress", payload={"completed_cases": evaluation.completed_cases,
                                                      "total_cases": evaluation.total_cases})
                evaluation.lease_until = datetime.now(timezone.utc) + timedelta(seconds=self.lease_seconds)
                db.commit()
            self._finish(db, evaluation)
        finally:
            db.close()

    @staticmethod
    def _retrieved_evidence(db, run_id: str) -> list[dict]:
        step = (db.query(RunStep).filter(RunStep.run_id == run_id, RunStep.type == "knowledge_retrieved")
                .order_by(RunStep.step_num).first())
        return list((step.detail or {}).get("evidence", [])) if step else []

    @staticmethod
    def _grounding_score(run: Run, evidence: list[dict]) -> float:
        if evidence:
            return 1.0 if run.grounding_status == "grounded" and bool(run.citations) else 0.0
        return 1.0 if run.grounding_status in (None, "insufficient_evidence") else 0.0

    @staticmethod
    def _token_usage(db, run: Run) -> dict:
        step = db.query(RunStep).filter(RunStep.run_id == run.id, RunStep.type == "run_usage").first()
        if step:
            return step.detail or {}
        return ((run.output or {}).get("failure") or {}).get("consumed", {})

    def _finish(self, db, evaluation: EvaluationRun) -> None:
        results = db.query(EvaluationCaseResult).filter(EvaluationCaseResult.evaluation_run_id == evaluation.id).all()
        aggregate: dict[str, float] = {}
        metric_names = {key for result in results for key in (result.metrics or {})}
        for name in metric_names:
            values = [float(result.metrics[name]) for result in results if name in (result.metrics or {})]
            aggregate[name] = sum(values) / len(values)
        aggregate["case_pass_rate"] = sum(result.status == "passed" for result in results) / len(results)
        thresholds = evaluation.config_snapshot["thresholds"]
        gates = {
            "case_pass_rate": aggregate["case_pass_rate"] >= thresholds["case_pass_rate"],
            "retrieval_recall": ("recall" not in aggregate or aggregate["recall"] >= thresholds["retrieval_recall"]),
            "citation_precision": aggregate.get("citation_precision", 1.0) >= thresholds["citation_precision"],
            "grounding_compliance": aggregate.get("grounding_compliance", 1.0) >= thresholds["grounding_compliance"],
        }
        evaluation.score = aggregate["case_pass_rate"]
        evaluation.metrics = aggregate
        evaluation.gate_results = gates
        evaluation.status = "passed" if all(gates.values()) else "failed"
        evaluation.completed_at = datetime.now(timezone.utc)
        evaluation.lease_owner = evaluation.lease_until = None
        emit(db, user_id=evaluation.user_id, resource_type="evaluation", resource_id=evaluation.id,
             event_type="completed" if evaluation.status == "passed" else "failed",
             payload={"completed_cases": evaluation.completed_cases, "metrics": aggregate})
        db.commit()

    def _retry_or_fail(self, evaluation_id: str) -> None:
        db = self.session_factory()
        try:
            evaluation = db.query(EvaluationRun).filter(EvaluationRun.id == evaluation_id,
                                                        EvaluationRun.lease_owner == self.worker_id).first()
            if not evaluation:
                return
            now = datetime.now(timezone.utc)
            evaluation.error_code = "evaluation_worker_error"
            evaluation.error_message = "Evaluation was interrupted by an infrastructure error."
            evaluation.lease_owner = evaluation.lease_until = None
            if evaluation.attempt_count < evaluation.max_attempts:
                evaluation.status = "retry_wait"
                evaluation.available_at = now + timedelta(seconds=(5, 30, 120)[evaluation.attempt_count - 1])
            else:
                evaluation.status = "failed"
                evaluation.completed_at = now
            emit(db, user_id=evaluation.user_id, resource_type="evaluation", resource_id=evaluation.id,
                 event_type="retrying" if evaluation.status == "retry_wait" else "failed",
                 payload={"code": evaluation.error_code, "attempt": evaluation.attempt_count})
            db.commit()
        finally:
            db.close()
