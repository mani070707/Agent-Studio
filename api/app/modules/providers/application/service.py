import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.secret_resolver import resolve_secret
from app.core.security import encrypt_secret
from app.db.models import ProviderConnection, UserSecret
from app.modules.providers.domain import ProviderCatalog
from app.modules.providers.infrastructure import ProviderKeyValidator, SqlAlchemyProviderConnectionRepository


class ProviderConnectionService:
    def __init__(self, session: Session, catalog: ProviderCatalog | None = None,
                 validator: ProviderKeyValidator | None = None) -> None:
        self.session = session
        self.catalog = catalog or ProviderCatalog()
        self.validator = validator or ProviderKeyValidator()
        self.connections = SqlAlchemyProviderConnectionRepository(session)

    def list_connections(self, user_id: str):
        return self.connections.list_owned(user_id)

    def models(self, provider: str, connection_id: str, user_id: str):
        connection = self.require_owned(connection_id, user_id)
        if connection.provider != provider:
            raise ValueError("Connection provider mismatch")
        available = self.validator.available_models(provider, resolve_secret(self.session, user_id, connection.secret_ref))
        if provider == "openrouter":
            available.add("openrouter/free")
        return [model for model in self.catalog.require(provider).models if model.id in available]

    def create(self, provider: str, display_name: str, api_key: str, user_id: str):
        self.catalog.require(provider)
        if self.connections.name_exists(user_id, display_name):
            raise FileExistsError("A provider connection with this name already exists")
        available = self.validator.available_models(provider, api_key)
        if not available and provider != "openrouter":
            raise ValueError("The provider key has no available models")
        identifier = str(uuid.uuid4())
        secret_ref = f"provider-{identifier}"
        self.session.add(UserSecret(user_id=user_id, name=secret_ref, encrypted_value=encrypt_secret(api_key)))
        now = datetime.now(timezone.utc).isoformat()
        connection = ProviderConnection(id=identifier, user_id=user_id, provider=provider,
            display_name=display_name, secret_ref=secret_ref, validation_status="valid",
            last_validated_at=now, created_at=now)
        self.connections.add(connection)
        self.session.commit()
        self.session.refresh(connection)
        return connection

    def test(self, connection_id: str, user_id: str):
        connection = self.require_owned(connection_id, user_id)
        self.validator.available_models(connection.provider, resolve_secret(self.session, user_id, connection.secret_ref))
        connection.validation_status = "valid"
        connection.last_validated_at = datetime.now(timezone.utc).isoformat()
        self.session.commit()
        self.session.refresh(connection)
        return connection

    def rotate(self, connection_id: str, api_key: str, user_id: str):
        connection = self.require_owned(connection_id, user_id)
        self.validator.available_models(connection.provider, api_key)
        secret = (self.session.query(UserSecret).filter(UserSecret.user_id == user_id,
                                                        UserSecret.name == connection.secret_ref).first())
        if not secret:
            raise LookupError("Provider secret not found")
        secret.encrypted_value = encrypt_secret(api_key)
        connection.validation_status = "valid"
        connection.last_validated_at = datetime.now(timezone.utc).isoformat()
        self.session.commit()
        self.session.refresh(connection)
        return connection

    def delete(self, connection_id: str, user_id: str) -> None:
        connection = self.require_owned(connection_id, user_id)
        secret = (self.session.query(UserSecret).filter(UserSecret.user_id == user_id,
                                                        UserSecret.name == connection.secret_ref).first())
        self.connections.delete(connection)
        if secret:
            self.session.delete(secret)
        self.session.commit()

    def require_owned(self, connection_id: str, user_id: str):
        connection = self.connections.get_owned(connection_id, user_id)
        if not connection:
            raise LookupError("Provider connection not found")
        return connection
