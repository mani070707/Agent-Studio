from cryptography.fernet import Fernet

from app.core.config import settings

_fernet = Fernet(settings.secret_encryption_key.encode())


def encrypt_secret(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet.decrypt(token.encode()).decode()
