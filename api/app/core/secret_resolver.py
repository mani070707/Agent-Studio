from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.db.models import UserSecret


class SecretResolutionError(ValueError):
    pass


def resolve_secret(db: Session, user_id: str, name: str) -> str:
    """Resolve a secretRef (a name) to its decrypted value, scoped to one user.
    Callers must never log or persist the return value."""
    secret = db.query(UserSecret).filter(UserSecret.user_id == user_id, UserSecret.name == name).first()
    if not secret:
        raise SecretResolutionError(f"No secret named '{name}' found for this user")
    return decrypt_secret(secret.encrypted_value)
