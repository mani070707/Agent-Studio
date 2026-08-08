from pydantic import model_validator
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
    supabase_jwt_issuer: str = ""

    # Explicit local-development escape hatch. Keep disabled in production.
    disable_auth: bool = False
    local_dev_user_id: str = ""
    environment: str = "local"
    metrics_token: str = ""
    embedded_ingestion_worker: bool = True
    ingestion_poll_seconds: float = 2.0
    ingestion_lease_seconds: int = 120
    embedded_indexing_worker: bool = True
    indexing_poll_seconds: float = 2.0
    indexing_lease_seconds: int = 600
    indexing_timeout_seconds: int = 300
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_cache_dir: str = ".model-cache"
    embedding_batch_size: int = 32
    indexing_worker_concurrency: int = 1
    semantic_index_version: int = 1
    preload_embedding_model: bool = True
    embedded_evaluation_worker: bool = True
    evaluation_poll_seconds: float = 2.0
    evaluation_lease_seconds: int = 900
    embedded_workflow_worker: bool = True
    workflow_poll_seconds: float = 2.0
    workflow_lease_seconds: int = 900
    checkpoint_encryption_key: str = ""
    workflow_checkpoint_retention_days: int = 30
    conversation_retention_days: int = 30
    conversation_cleanup_seconds: int = 3600
    event_retention_days: int = 7
    event_poll_seconds: float = 1.0
    event_batch_size: int = 100
    sse_max_connections_per_tenant: int = 3
    sse_max_duration_seconds: int = 300
    worker_heartbeat_seconds: int = 20

    @model_validator(mode="after")
    def prohibit_production_auth_bypass(self):
        if self.environment.lower() in {"production", "prod"} and self.disable_auth:
            raise ValueError("DISABLE_AUTH cannot be enabled in production")
        if not 1 <= self.indexing_worker_concurrency <= 8:
            raise ValueError("INDEXING_WORKER_CONCURRENCY must be between 1 and 8")
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


settings = Settings()
