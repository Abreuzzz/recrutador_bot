from __future__ import annotations

import re
from difflib import SequenceMatcher

NAME_PATTERN = re.compile(r"(?im)^\s*Nome\s*:\s*(?P<value>.+?)\s*$")
TITLE_PATTERN = re.compile(r"(?im)^\s*T[íi]tulo\s*:\s*(?P<value>.+?)\s*$")
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}")


def split_candidates(raw_text: str) -> list[str]:
    parts = re.split(r"(?m)^\s*---+\s*$", raw_text or "")
    return [part.strip() for part in parts if part.strip()]


def extract_name(raw_text: str) -> str | None:
    match = NAME_PATTERN.search(raw_text or "")
    if not match:
        return None
    return clean_single_line(match.group("value"))


def extract_title(raw_text: str) -> str | None:
    match = TITLE_PATTERN.search(raw_text or "")
    if not match:
        return None
    return clean_single_line(match.group("value"))


def fallback_title(raw_text: str, max_words: int = 8) -> str:
    words = re.findall(r"\w+", raw_text or "", flags=re.UNICODE)
    if not words:
        return "Vaga sem titulo"
    return " ".join(words[:max_words])


def clean_single_line(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" -:;\t\r\n")


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.casefold()
    normalized = re.sub(r"[^a-z0-9áàâãéêíóôõúüçñ ]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def extract_emails(raw_text: str) -> set[str]:
    return {item.casefold() for item in EMAIL_PATTERN.findall(raw_text or "")}


def extract_phones(raw_text: str) -> set[str]:
    return {re.sub(r"\D+", "", item) for item in PHONE_PATTERN.findall(raw_text or "")}


def text_similarity(left: str, right: str) -> float:
    left_norm = re.sub(r"\s+", " ", (left or "").casefold()).strip()
    right_norm = re.sub(r"\s+", " ", (right or "").casefold()).strip()
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()
