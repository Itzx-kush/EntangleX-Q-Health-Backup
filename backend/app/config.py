from functools import lru_cache
from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DISCLAIMER = (
    "Research Prototype: This platform provides model-generated disease-risk predictions "
    "for research and decision-support purposes. Predictions are based on benchmark or "
    "user-provided datasets and are not a substitute for professional medical diagnosis, "
    "treatment, or clinical validation."
)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QHEALTH_", env_file=PROJECT_ROOT / ".env", extra="ignore")
    # DATABASE_URL is intentionally supported without the QHEALTH_ prefix so
    # hosted Postgres providers can be connected using their standard variable.
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "QHEALTH_DATABASE_URL"),
    )
    storage_root: Path = PROJECT_ROOT
    storage_backend: str = Field(default="local", pattern="^(local|s3)$")
    object_storage_endpoint: str | None = None
    object_storage_bucket: str | None = None
    object_storage_access_key: str | None = None
    object_storage_secret_key: str | None = None
    object_storage_region: str = "us-east-1"
    object_storage_prefix: str = "qhealth"
    serverless: bool = False
    api_token: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080"
    trusted_hosts: str = "localhost,127.0.0.1,backend,testserver,*.vercel.app"
    upload_limit_mb: int = Field(default=20, ge=1, le=100)
    max_rows: int = Field(default=100000, ge=20, le=1000000)
    max_columns: int = Field(default=200, ge=2, le=500)
    quantum_max_samples: int = Field(default=256, ge=20, le=1024)
    max_queued_jobs: int = Field(default=3, ge=1, le=10)
    serverless_max_samples: int = Field(default=512, ge=30, le=2000)
    serverless_max_cv_folds: int = Field(default=3, ge=2, le=5)
    log_level: str = "INFO"

    @property
    def root(self) -> Path:
        return (PROJECT_ROOT / self.storage_root).resolve()

    @property
    def upload_limit(self) -> int:
        return self.upload_limit_mb * 1024 * 1024

    def initialize_directories(self) -> None:
        if self.storage_backend == "s3":
            return
        for name in ["data/datasets", "models", "experiments"]:
            (self.root / name).mkdir(parents=True, exist_ok=True)

@lru_cache
def get_settings() -> Settings:
    return Settings()
