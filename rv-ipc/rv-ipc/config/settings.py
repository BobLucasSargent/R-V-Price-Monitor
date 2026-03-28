"""R&V IPC — Configuration."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://rv_ipc:rv_ipc_dev@localhost:5432/rv_ipc"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://rv_ipc:rv_ipc_dev@localhost:5432/rv_ipc"

    # App
    APP_NAME: str = "R&V IPC"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    # Scraping
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3

    # IPC empalme
    EMPALME_FECHA: str = "2026-02-01"
    EMPALME_NIVEL_GENERAL: float = 10714.63

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
