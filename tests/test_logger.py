from __future__ import annotations

import logging

from app.utils.logger import RedactingFormatter, redact_sensitive_data


def test_redacts_telegram_token_inside_bot_url() -> None:
    raw = 'HTTP Request: POST https://api.telegram.org/bot123456:ABC_def-ghi/getMe "200 OK"'

    assert redact_sensitive_data(raw) == (
        'HTTP Request: POST https://api.telegram.org/bot***/getMe "200 OK"'
    )


def test_redacting_formatter_masks_formatted_args_and_exact_secrets() -> None:
    formatter = RedactingFormatter("%(message)s", secrets=("123456:ABC_def-ghi",))
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="url=%s token=%s",
        args=(
            "https://api.telegram.org/bot123456:ABC_def-ghi/getUpdates",
            "123456:ABC_def-ghi",
        ),
        exc_info=None,
    )

    output = formatter.format(record)

    assert "123456:ABC_def-ghi" not in output
    assert "bot***" in output
    assert "token=***" in output
