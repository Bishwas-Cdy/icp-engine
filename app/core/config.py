from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SignalForge"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./signalforge.db"

    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    llm_retries: int = Field(default=2, ge=0, le=5)

    scrape_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    scrape_max_bytes: int = Field(default=2_000_000, ge=10_000, le=10_000_000)
    scrape_max_pages: int = Field(default=4, ge=1, le=10)
    scrape_retries: int = Field(default=2, ge=0, le=5)
    max_batch_rows: int = Field(default=100, ge=1, le=1000)
    icp_config_path: Path = Path("config/default_icp.json")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
