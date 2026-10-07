import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./kvitto.db"
    # Если секрет не задан, подпись вебхука не проверяем (удобно для локального запуска)
    webhook_secret: str | None = None


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", Settings.database_url),
        webhook_secret=os.getenv("WEBHOOK_SECRET") or None,
    )
