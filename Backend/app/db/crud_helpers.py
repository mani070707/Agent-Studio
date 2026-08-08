from fastapi import HTTPException
from sqlalchemy.orm import Session


def get_owned_or_404(db: Session, model, id_: str, user_id: str, id_field: str = "id"):
    """Fetch a row scoped to the current user, or raise 404. Every user-scoped table's
    CRUD routers should go through this — dropping the user_id filter is a cross-tenant
    data leak, not a style nit."""
    row = (
        db.query(model)
        .filter(getattr(model, id_field) == id_, model.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return row
