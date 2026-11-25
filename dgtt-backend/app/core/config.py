"""Cấu hình ứng dụng, đọc từ biến môi trường / file .env (NFR-10)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "DGTT Backend"
    env: str = "dev"

    database_url: str = "postgresql+asyncpg://dgtt:dgtt@localhost:5432/dgtt"

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30  # NFR-04: hết hạn sau 30 phút không tương tác

    cors_origins: str = "http://localhost:5173,http://localhost:5500,http://127.0.0.1:5500"

    storage_dir: str = "storage"
    max_upload_mb: int = 10

    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 1

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
