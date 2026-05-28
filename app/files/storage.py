from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from telegram import Document as TelegramDocument

from app.config import Settings
from app.files.extractors import SUPPORTED_EXTENSIONS, FileExtractionError, validate_file_size


@dataclass(frozen=True)
class StoredUpload:
    original_filename: str
    stored_path: Path
    extension: str
    size_bytes: int


def safe_extension(filename: str) -> str:
    extension = Path(filename or "").suffix.casefold()
    if extension not in SUPPORTED_EXTENSIONS:
        raise FileExtractionError("Formato não suportado. Envie PDF, DOCX ou TXT.")
    return extension


def safe_original_filename(filename: str | None) -> str:
    if not filename:
        return "arquivo"
    cleaned = re.sub(r"[\r\n\t]+", " ", filename).strip()
    return cleaned or "arquivo"


def build_stored_path(settings: Settings, original_filename: str) -> Path:
    extension = safe_extension(original_filename)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    return settings.uploads_dir / f"{uuid.uuid4().hex}{extension}"


async def save_telegram_document(
    bot: object,
    document: TelegramDocument,
    settings: Settings,
) -> StoredUpload:
    return await save_telegram_file_reference(
        bot=bot,
        file_id=document.file_id,
        original_filename=document.file_name,
        size_bytes=int(document.file_size or 0),
        settings=settings,
    )


async def save_telegram_file_reference(
    bot: object,
    file_id: str,
    original_filename: str | None,
    size_bytes: int,
    settings: Settings,
) -> StoredUpload:
    original_filename = safe_original_filename(original_filename)
    extension = safe_extension(original_filename)
    validate_file_size(size_bytes, settings.max_file_size_mb)

    stored_path = build_stored_path(settings, original_filename)
    telegram_file = await bot.get_file(file_id)  # type: ignore[attr-defined]
    await telegram_file.download_to_drive(custom_path=stored_path)

    return StoredUpload(
        original_filename=original_filename,
        stored_path=stored_path,
        extension=extension,
        size_bytes=size_bytes,
    )
