from fastapi import APIRouter
from pydantic import BaseModel
from app.tools.registry import definitions

router = APIRouter(prefix="/tools", tags=["tools"])


class PlatformToolOut(BaseModel):
    name: str
    description: str
    input_schema: dict
    output_schema: dict


@router.get("/platform", response_model=list[PlatformToolOut])
def list_platform_tools():
    return definitions()
