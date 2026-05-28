from pathlib import Path

import pytest

from app.bot.access_control import is_authorized
from app.config import load_settings, parse_authorized_user_ids


def test_parse_authorized_user_ids_multiple_values() -> None:
    assert parse_authorized_user_ids("123, 456,789") == {123, 456, 789}


def test_parse_authorized_user_ids_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        parse_authorized_user_ids("123,abc")


def test_access_control_allows_only_configured_ids() -> None:
    settings = load_settings()
    configured = settings.__class__(
        **{**settings.__dict__, "authorized_telegram_user_ids": {10, 20}}
    )

    assert is_authorized(10, configured)
    assert not is_authorized(30, configured)


def test_load_settings_from_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "TELEGRAM_BOT_TOKEN=token",
                "AUTHORIZED_TELEGRAM_USER_IDS=1,2",
                "DATABASE_PATH=./custom.db",
                "MAX_FILE_SIZE_MB=7",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("AUTHORIZED_TELEGRAM_USER_IDS", raising=False)

    settings = load_settings(env_file)

    assert settings.telegram_bot_token == "token"
    assert settings.authorized_telegram_user_ids == {1, 2}
    assert settings.database_path == Path("./custom.db")
    assert settings.max_file_size_mb == 7
