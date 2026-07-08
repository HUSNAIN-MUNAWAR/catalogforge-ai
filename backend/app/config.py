from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CatalogForge AI"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./catalogforge.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "catalogforge-local-demo-secret-32bytes-minimum"
    storage_backend: str = "local"
    local_storage_path: str = "../demo_data/source_documents"
    ocr_provider: str = "deterministic"
    llm_provider: str = "deterministic"
    demo_mode: bool = True
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    @property
    def storage_path(self) -> Path:
        return Path(self.local_storage_path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
