from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency exists after normal installation.

    def load_dotenv(dotenv_path: str | Path | None = None, override: bool = False) -> bool:
        path = Path(dotenv_path or ".env")
        if not path.exists():
            return False
        for line in path.read_text(encoding="utf-8").splitlines():
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("#") or "=" not in cleaned:
                continue
            key, value = cleaned.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if override or key not in os.environ:
                os.environ[key] = value
        return True


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    authorized_telegram_user_ids: set[int]
    ollama_base_url: str
    ollama_model: str
    database_path: Path
    uploads_dir: Path
    log_file: Path
    max_candidates_per_analysis: int
    max_file_size_mb: int
    log_level: str


def parse_authorized_user_ids(raw_value: str | None) -> set[int]:
    if not raw_value:
        return set()

    user_ids: set[int] = set()
    for item in raw_value.split(","):
        cleaned = item.strip()
        if not cleaned:
            continue
        try:
            user_ids.add(int(cleaned))
        except ValueError as exc:
            raise ValueError(
                "AUTHORIZED_TELEGRAM_USER_IDS deve conter apenas IDs inteiros "
                "separados por virgula."
            ) from exc
    return user_ids


def _int_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    return int(raw_value)


def load_settings(env_file: str | Path | None = None) -> Settings:
    if env_file:
        load_dotenv(env_file, override=True)
    else:
        load_dotenv()

    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        authorized_telegram_user_ids=parse_authorized_user_ids(
            os.getenv("AUTHORIZED_TELEGRAM_USER_IDS", "")
        ),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
        database_path=Path(os.getenv("DATABASE_PATH", "./data/recruitment_bot.db")),
        uploads_dir=Path(os.getenv("UPLOADS_DIR", "./data/uploads")),
        log_file=Path(os.getenv("LOG_FILE", "./logs/app.log")),
        max_candidates_per_analysis=_int_from_env("MAX_CANDIDATES_PER_ANALYSIS", 5),
        max_file_size_mb=_int_from_env("MAX_FILE_SIZE_MB", 20),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
