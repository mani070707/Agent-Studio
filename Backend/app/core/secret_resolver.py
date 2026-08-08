from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.db.models import ProviderConnection, UserSecret


class SecretResolutionError(ValueError):
    pass


def resolve_secret(db: Session, user_id: str, name: str) -> str:
    """Resolve a secretRef (a name) to its decrypted value, scoped to one user.
    Callers must never log or persist the return value."""
    secret = db.query(UserSecret).filter(UserSecret.user_id == user_id, UserSecret.name == name).first()
    if not secret:
        raise SecretResolutionError(f"No secret named '{name}' found for this user")
    return decrypt_secret(secret.encrypted_value)


def resolve_provider_key(db: Session, user_id: str, runtime_model: dict) -> str:
    connection_id = runtime_model.get("provider_connection_id")
    if connection_id:
        connection = (
            db.query(ProviderConnection)
            .filter(ProviderConnection.id == connection_id, ProviderConnection.user_id == user_id)
            .first()
        )
        if not connection:
            raise SecretResolutionError("Provider connection was not found for this user")
        if connection.provider != runtime_model.get("provider"):
            raise SecretResolutionError("Provider connection does not match the selected provider")
        return resolve_secret(db, user_id, connection.secret_ref)
    legacy_ref = runtime_model.get("api_key_secret_ref")
    if not legacy_ref:
        raise SecretResolutionError("No provider connection or legacy API key reference is configured")
    return resolve_secret(db, user_id, legacy_ref)
