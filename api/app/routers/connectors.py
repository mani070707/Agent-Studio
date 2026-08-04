from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.connectors.executor import execute_connector
from app.core.auth import get_current_user_id
from app.core.secret_resolver import SecretResolutionError, resolve_secret
from app.core.ssrf_guard import UnsafeUrlError
from app.db.crud_helpers import get_owned_or_404
from app.db.models import Connector
from app.db.session import get_db

router = APIRouter(prefix="/connectors", tags=["connectors"])


class ConnectorIn(BaseModel):
    name: str
    base_url: str
    auth_secret_ref: str | None = None
    request_template: dict


class ConnectorOut(ConnectorIn):
    id: str


class ConnectorTestIn(BaseModel):
    variables: dict = {}


@router.get("", response_model=list[ConnectorOut])
def list_connectors(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return db.query(Connector).filter(Connector.user_id == user_id).all()


@router.post("", response_model=ConnectorOut, status_code=201)
def create_connector(
    body: ConnectorIn, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    connector = Connector(user_id=user_id, **body.model_dump())
    db.add(connector)
    db.commit()
    db.refresh(connector)
    return connector


@router.get("/{connector_id}", response_model=ConnectorOut)
def get_connector(connector_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return get_owned_or_404(db, Connector, connector_id, user_id)


@router.post("/{connector_id}/test")
def test_connector(
    connector_id: str,
    body: ConnectorTestIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    connector = get_owned_or_404(db, Connector, connector_id, user_id)
    secret_value = None
    if connector.auth_secret_ref:
        try:
            secret_value = resolve_secret(db, user_id, connector.auth_secret_ref)
        except SecretResolutionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return execute_connector(connector.base_url, connector.request_template, body.variables, secret_value)
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Connector call failed: {exc}") from exc


@router.delete("/{connector_id}", status_code=204)
def delete_connector(
    connector_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    connector = get_owned_or_404(db, Connector, connector_id, user_id)
    db.delete(connector)
    db.commit()
