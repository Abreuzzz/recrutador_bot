from __future__ import annotations

import logging

from app.config import Settings

logger = logging.getLogger(__name__)


def is_authorized(telegram_user_id: int | None, settings: Settings) -> bool:
    if telegram_user_id is None:
        return False
    return telegram_user_id in settings.authorized_telegram_user_ids


def log_unauthorized(telegram_user_id: int | None) -> None:
    logger.warning("Usuario nao autorizado tentou usar o bot: %s", telegram_user_id)
