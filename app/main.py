from __future__ import annotations

import logging
import sys

from telegram import Update

from app.bot.handlers import build_application
from app.config import load_settings
from app.database.connection import init_db
from app.utils.logger import configure_logging


def main() -> None:
    settings = load_settings()
    configure_logging(settings)
    logger = logging.getLogger(__name__)

    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN não configurado.")
        raise SystemExit("Configure TELEGRAM_BOT_TOKEN no .env antes de iniciar o bot.")

    if not settings.authorized_telegram_user_ids:
        logger.error("AUTHORIZED_TELEGRAM_USER_IDS não configurado.")
        raise SystemExit("Configure AUTHORIZED_TELEGRAM_USER_IDS no .env antes de iniciar o bot.")

    init_db(settings.database_path)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.log_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Inicializando bot Telegram de recrutamento.")
    application = build_application(settings)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
