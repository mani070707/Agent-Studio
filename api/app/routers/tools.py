from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import PlatformTool
from app.db.session import get_db

router = APIRouter(prefix="/tools", tags=["tools"])


class PlatformToolOut(BaseModel):
    name: str
    description: str
    input_schema: dict
    output_schema: dict


@router.get("/platform", response_model=list[PlatformToolOut])
def list_platform_tools(db: Session = Depends(get_db)):
    return db.query(PlatformTool).all()
