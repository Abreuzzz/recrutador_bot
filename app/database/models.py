from __future__ import annotations

from dataclasses import dataclass

STATUS_OK = "ok"
STATUS_PENDING_NAME = "pendente_nome"
STATUS_EXTRACTION_FAILED = "extracao_falhou"
STATUS_FILE_EXTRACTION_FAILED = "falha_extracao"
STATUS_REMOVED = "removido"

SOURCE_TEXT = "texto"
SOURCE_FILE = "arquivo"


@dataclass(frozen=True)
class Job:
    id: int
    telegram_user_id: int
    title: str
    raw_text: str
    structured_summary_json: str
    is_active: bool
    is_removed: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Candidate:
    id: int
    telegram_user_id: int
    job_id: int
    name: str
    raw_text: str
    structured_summary_json: str
    status: str
    source_type: str
    source_file_id: int | None
    created_at: str
    updated_at: str
    is_removed: bool


@dataclass(frozen=True)
class FileRecord:
    id: int
    telegram_user_id: int
    job_id: int | None
    candidate_id: int | None
    original_filename: str
    stored_path: str
    extension: str
    size_bytes: int
    extraction_status: str
    extracted_text: str
    created_at: str


@dataclass(frozen=True)
class Analysis:
    id: int
    telegram_user_id: int
    job_id: int
    job_title_snapshot: str
    result_summary_json: str
    created_at: str


@dataclass(frozen=True)
class AnalysisCandidate:
    id: int
    analysis_id: int
    candidate_id: int
    candidate_name_snapshot: str
    score: int
    classification: str
    priority: str
    result_json: str
    rendered_message: str
    created_at: str


@dataclass(frozen=True)
class UserState:
    telegram_user_id: int
    active_job_id: int | None
    pending_action: str | None
    pending_payload_json: str | None
    updated_at: str
