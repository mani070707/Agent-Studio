from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase project (Auth + Postgres + Storage) — see README "Quick Start" for setup.
    supabase_url: str
    supabase_jwks_url: str
    supabase_service_role_key: str
    supabase_storage_bucket: str = "agent-studio-content"

    database_url: str

    # Fernet key encrypting user_secret.encrypted_value — generate with:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    secret_encryption_key: str

    # CORS: the deployed web app's origin(s), comma-separated.
    cors_allow_origins: str = "http://localhost:3000"

    # External cron hitting POST /internal/run-due-schedules must send this as
    # X-Internal-Cron-Secret — generate any random string.
    internal_cron_secret: str

    jwt_audience: str = "authenticated"

    # Explicit local-development escape hatch. Keep disabled in production.
    disable_auth: bool = False
    local_dev_user_id: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


settings = Settings()
