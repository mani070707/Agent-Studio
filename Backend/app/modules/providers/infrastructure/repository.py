from sqlalchemy.orm import Session

from app.db.models import ProviderConnection


class SqlAlchemyProviderConnectionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_owned(self, user_id: str) -> list[ProviderConnection]:
        return (self.session.query(ProviderConnection)
                .filter(ProviderConnection.user_id == user_id)
                .order_by(ProviderConnection.display_name).all())

    def get_owned(self, connection_id: str, user_id: str) -> ProviderConnection | None:
        return (self.session.query(ProviderConnection)
                .filter(ProviderConnection.id == connection_id, ProviderConnection.user_id == user_id).first())

    def name_exists(self, user_id: str, display_name: str) -> bool:
        return (self.session.query(ProviderConnection.id)
                .filter(ProviderConnection.user_id == user_id,
                        ProviderConnection.display_name == display_name).first() is not None)

    def add(self, connection: ProviderConnection) -> None:
        self.session.add(connection)

    def delete(self, connection: ProviderConnection) -> None:
        self.session.delete(connection)
