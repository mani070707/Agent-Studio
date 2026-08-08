from typing import Literal

from fastapi import APIRouter, Depends
from jsonschema.validators import Draft202012Validator
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.crud_helpers import get_owned_or_404
from app.db.models import SchemaEntry
from app.db.session import get_db

router = APIRouter(prefix="/schemas", tags=["schemas"])


class SchemaEntryIn(BaseModel):
    name: str
    kind: Literal["input", "output"]
    json_schema: dict

    @field_validator("json_schema")
    @classmethod
    def must_be_valid_json_schema(cls, value: dict) -> dict:
        try:
            Draft202012Validator.check_schema(value)
        except Exception as exc:
            raise ValueError(f"Not a valid JSON Schema: {exc}") from exc
        return value


class SchemaEntryOut(BaseModel):
    id: str
    name: str
    kind: Literal["input", "output"]
    json_schema: dict
    version: str


@router.get("", response_model=list[SchemaEntryOut])
def list_schemas(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return db.query(SchemaEntry).filter(SchemaEntry.user_id == user_id).all()


@router.post("", response_model=SchemaEntryOut, status_code=201)
def create_schema(
    body: SchemaEntryIn, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    entry = SchemaEntry(user_id=user_id, **body.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/{schema_id}", response_model=SchemaEntryOut)
def get_schema(schema_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return get_owned_or_404(db, SchemaEntry, schema_id, user_id)


@router.delete("/{schema_id}", status_code=204)
def delete_schema(schema_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    entry = get_owned_or_404(db, SchemaEntry, schema_id, user_id)
    db.delete(entry)
    db.commit()
