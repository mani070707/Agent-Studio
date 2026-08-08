from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.session import get_db
from app.modules.providers.application import ProviderConnectionService
from app.modules.providers.domain import ProviderCatalog
from app.modules.providers.infrastructure.validator import ProviderValidationError

router = APIRouter(tags=["providers"])


class CreateConnectionRequest(BaseModel):
    provider: str
    display_name: str = Field(min_length=1)
    api_key: str = Field(min_length=1)


class RotateKeyRequest(BaseModel):
    api_key: str = Field(min_length=1)


class ConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    provider: str
    display_name: str
    validation_status: str
    last_validated_at: str | None
    created_at: str


def service(db: Session = Depends(get_db)) -> ProviderConnectionService:
    return ProviderConnectionService(db)


def translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(404, detail=str(exc))
    if isinstance(exc, FileExistsError):
        return HTTPException(409, detail=str(exc))
    if isinstance(exc, ProviderValidationError) and exc.rate_limited:
        return HTTPException(429, detail=str(exc))
    return HTTPException(400, detail=str(exc))


@router.get("/model-providers")
def providers():
    return [asdict(provider) for provider in ProviderCatalog().all()]


@router.get("/model-providers/{provider}/models")
def models(provider: str, connection_id: str, user_id: str = Depends(get_current_user_id),
           use_case: ProviderConnectionService = Depends(service)):
    try:
        return [asdict(model) for model in use_case.models(provider, connection_id, user_id)]
    except Exception as exc:
        raise translate_error(exc) from exc


@router.get("/provider-connections", response_model=list[ConnectionResponse])
def connections(user_id: str = Depends(get_current_user_id), use_case=Depends(service)):
    return use_case.list_connections(user_id)


@router.post("/provider-connections", response_model=ConnectionResponse, status_code=201)
def create_connection(body: CreateConnectionRequest, user_id: str = Depends(get_current_user_id),
                      use_case=Depends(service)):
    try:
        return use_case.create(body.provider, body.display_name.strip(), body.api_key, user_id)
    except Exception as exc:
        use_case.session.rollback()
        raise translate_error(exc) from exc


@router.post("/provider-connections/{connection_id}/test", response_model=ConnectionResponse)
def test_connection(connection_id: str, user_id: str = Depends(get_current_user_id), use_case=Depends(service)):
    try:
        return use_case.test(connection_id, user_id)
    except Exception as exc:
        raise translate_error(exc) from exc


@router.put("/provider-connections/{connection_id}/key", response_model=ConnectionResponse)
def rotate_connection(connection_id: str, body: RotateKeyRequest,
                      user_id: str = Depends(get_current_user_id), use_case=Depends(service)):
    try:
        return use_case.rotate(connection_id, body.api_key, user_id)
    except Exception as exc:
        use_case.session.rollback()
        raise translate_error(exc) from exc


@router.delete("/provider-connections/{connection_id}", status_code=204)
def delete_connection(connection_id: str, user_id: str = Depends(get_current_user_id), use_case=Depends(service)):
    try:
        use_case.delete(connection_id, user_id)
        return Response(status_code=204)
    except Exception as exc:
        use_case.session.rollback()
        raise translate_error(exc) from exc
