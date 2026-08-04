from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.core.security import encrypt_secret
from app.db.crud_helpers import get_owned_or_404
from app.db.models import UserSecret
from app.db.session import get_db

router = APIRouter(prefix="/secrets", tags=["secrets"])


class SecretIn(BaseModel):
    name: str
    value: str


class SecretOut(BaseModel):
    id: str
    name: str


@router.get("", response_model=list[SecretOut])
def list_secrets(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return db.query(UserSecret).filter(UserSecret.user_id == user_id).all()


@router.post("", response_model=SecretOut, status_code=201)
def create_secret(body: SecretIn, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    secret = UserSecret(user_id=user_id, name=body.name, encrypted_value=encrypt_secret(body.value))
    db.add(secret)
    db.commit()
    db.refresh(secret)
    return secret


@router.delete("/{secret_id}", status_code=204)
def delete_secret(secret_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    secret = get_owned_or_404(db, UserSecret, secret_id, user_id)
    db.delete(secret)
    db.commit()
