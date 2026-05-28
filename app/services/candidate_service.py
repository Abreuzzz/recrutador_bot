from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.database.models import (
    SOURCE_FILE,
    SOURCE_TEXT,
    STATUS_EXTRACTION_FAILED,
    STATUS_FILE_EXTRACTION_FAILED,
    STATUS_OK,
    STATUS_PENDING_NAME,
    Candidate,
)
from app.database.repository import Repository
from app.files.extractors import FileExtractionError, extract_text_from_file
from app.llm.ollama_client import OllamaClient, OllamaError
from app.llm.prompts import CANDIDATE_SCHEMA_KEYS, build_candidate_extraction_prompt
from app.llm.schemas import NAO_INFORMADO, StructuredCandidateSummary
from app.utils.text_parser import (
    extract_emails,
    extract_name,
    extract_phones,
    normalize_name,
    split_candidates,
    text_similarity,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DuplicateFinding:
    candidate_id: int
    reason: str


@dataclass(frozen=True)
class CandidateAddResult:
    candidate: Candidate | None
    duplicate: DuplicateFinding | None = None
    pending_payload: dict[str, object] | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReprocessResult:
    candidate: Candidate
    success: bool
    message: str


class CandidateService:
    def __init__(self, repository: Repository, llm_client: OllamaClient | None = None) -> None:
        self.repository = repository
        self.llm_client = llm_client

    def add_candidates_from_text(
        self,
        telegram_user_id: int,
        raw_text: str,
        source_type: str = SOURCE_TEXT,
        source_file_id: int | None = None,
        force_duplicate: bool = False,
    ) -> list[CandidateAddResult]:
        chunks = split_candidates(raw_text)
        if not chunks:
            return []
        return [
            self.add_single_candidate_from_text(
                telegram_user_id=telegram_user_id,
                raw_text=chunk,
                source_type=source_type,
                source_file_id=source_file_id,
                force_duplicate=force_duplicate,
            )
            for chunk in chunks
        ]

    def add_single_candidate_from_text(
        self,
        telegram_user_id: int,
        raw_text: str,
        source_type: str = SOURCE_TEXT,
        source_file_id: int | None = None,
        force_duplicate: bool = False,
    ) -> CandidateAddResult:
        active_job = self.repository.get_active_job(telegram_user_id)
        if active_job is None:
            raise ValueError("Cadastre ou selecione uma vaga antes de adicionar candidatos.")

        duplicate = self.detect_duplicate(
            telegram_user_id=telegram_user_id,
            job_id=active_job.id,
            raw_text=raw_text,
            source_file_id=source_file_id,
        )
        if duplicate and not force_duplicate:
            return CandidateAddResult(
                candidate=None,
                duplicate=duplicate,
                pending_payload={
                    "raw_text": raw_text,
                    "source_type": source_type,
                    "source_file_id": source_file_id,
                },
            )

        summary, extraction_ok, warnings = self._extract_summary(raw_text)
        explicit_name = extract_name(raw_text)
        llm_name = summary.nome if summary.nome != NAO_INFORMADO else None
        name = explicit_name or llm_name or "Nome pendente"
        status = STATUS_OK
        if not explicit_name and not llm_name:
            status = STATUS_PENDING_NAME
        elif not extraction_ok:
            status = STATUS_EXTRACTION_FAILED

        candidate = self.repository.create_candidate(
            telegram_user_id=telegram_user_id,
            job_id=active_job.id,
            name=name,
            raw_text=raw_text,
            structured_summary_json=_model_json(summary),
            status=status,
            source_type=source_type,
            source_file_id=source_file_id,
        )
        if source_file_id is not None:
            self.repository.update_file_candidate_link(source_file_id, candidate.id)
        logger.info(
            "Candidato criado user=%s job=%s candidate=%s status=%s",
            telegram_user_id,
            active_job.id,
            candidate.id,
            status,
        )
        return CandidateAddResult(candidate=candidate, warnings=warnings)

    def create_failed_file_candidate(
        self,
        telegram_user_id: int,
        file_id: int,
        original_filename: str,
        error_message: str,
    ) -> Candidate:
        active_job = self.repository.get_active_job(telegram_user_id)
        if active_job is None:
            raise ValueError("Cadastre ou selecione uma vaga antes de adicionar candidatos.")
        summary = StructuredCandidateSummary(
            nome="Nome pendente",
            observacoes_relevantes=[error_message],
        )
        candidate = self.repository.create_candidate(
            telegram_user_id=telegram_user_id,
            job_id=active_job.id,
            name=f"Nome pendente ({original_filename})",
            raw_text="",
            structured_summary_json=_model_json(summary),
            status=STATUS_FILE_EXTRACTION_FAILED,
            source_type=SOURCE_FILE,
            source_file_id=file_id,
        )
        self.repository.update_file_candidate_link(file_id, candidate.id)
        return candidate

    def update_candidate_text(
        self,
        telegram_user_id: int,
        candidate_id: int,
        raw_text: str,
    ) -> Candidate:
        candidate = self.repository.get_candidate(telegram_user_id, candidate_id)
        if candidate is None or candidate.is_removed:
            raise ValueError("Candidato não encontrado.")

        active_job = self.repository.get_active_job(telegram_user_id)
        if active_job is None or candidate.job_id != active_job.id:
            raise ValueError("O candidato não pertence à vaga ativa.")

        summary, extraction_ok, _warnings = self._extract_summary(raw_text)
        explicit_name = extract_name(raw_text)
        llm_name = summary.nome if summary.nome != NAO_INFORMADO else None
        name = explicit_name or llm_name or "Nome pendente"
        status = STATUS_OK
        if not explicit_name and not llm_name:
            status = STATUS_PENDING_NAME
        elif not extraction_ok:
            status = STATUS_EXTRACTION_FAILED

        updated = self.repository.update_candidate(
            telegram_user_id=telegram_user_id,
            candidate_id=candidate_id,
            raw_text=raw_text,
            name=name,
            structured_summary_json=_model_json(summary),
            status=status,
        )
        if updated is None:
            raise ValueError("Não foi possível atualizar o candidato.")
        logger.info("Candidato atualizado user=%s candidate=%s", telegram_user_id, candidate_id)
        return updated

    def detect_duplicate(
        self,
        telegram_user_id: int,
        job_id: int,
        raw_text: str,
        source_file_id: int | None = None,
    ) -> DuplicateFinding | None:
        candidates = self.repository.list_candidates(telegram_user_id, job_id)
        incoming_name = normalize_name(extract_name(raw_text))
        incoming_emails = extract_emails(raw_text)
        incoming_phones = extract_phones(raw_text)

        for candidate in candidates:
            if source_file_id is not None and candidate.source_file_id == source_file_id:
                return DuplicateFinding(candidate.id, "mesmo arquivo já cadastrado")

            if incoming_name and incoming_name == normalize_name(candidate.name):
                return DuplicateFinding(candidate.id, "mesmo nome normalizado")

            shared_emails = incoming_emails & extract_emails(candidate.raw_text)
            if shared_emails:
                return DuplicateFinding(candidate.id, "mesmo e-mail encontrado")

            shared_phones = incoming_phones & extract_phones(candidate.raw_text)
            if shared_phones:
                return DuplicateFinding(candidate.id, "mesmo telefone encontrado")

            if text_similarity(raw_text, candidate.raw_text) >= 0.92:
                return DuplicateFinding(candidate.id, "texto muito semelhante")

        return None

    def reprocess_candidate(self, telegram_user_id: int, candidate_id: int) -> ReprocessResult:
        candidate = self.repository.get_candidate(telegram_user_id, candidate_id)
        active_job = self.repository.get_active_job(telegram_user_id)
        if candidate is None or candidate.is_removed:
            raise ValueError("Candidato não encontrado.")
        if active_job is None or candidate.job_id != active_job.id:
            raise ValueError("O candidato não pertence à vaga ativa.")

        raw_text = candidate.raw_text
        if candidate.source_file_id:
            file_record = self.repository.get_file(telegram_user_id, candidate.source_file_id)
            if file_record and Path(file_record.stored_path).exists():
                try:
                    raw_text = extract_text_from_file(file_record.stored_path)
                except FileExtractionError as exc:
                    updated = self.repository.update_candidate(
                        telegram_user_id=telegram_user_id,
                        candidate_id=candidate.id,
                        raw_text=candidate.raw_text,
                        name=candidate.name,
                        structured_summary_json=candidate.structured_summary_json,
                        status=STATUS_FILE_EXTRACTION_FAILED,
                    )
                    return ReprocessResult(
                        candidate=updated or candidate,
                        success=False,
                        message=str(exc),
                    )

        updated = self.update_candidate_text(telegram_user_id, candidate_id, raw_text)
        return ReprocessResult(
            candidate=updated,
            success=updated.status == STATUS_OK,
            message="Candidato reprocessado com sucesso."
            if updated.status == STATUS_OK
            else "Reprocessamento concluído, mas ainda há pendências.",
        )

    def reprocess_failures(self, telegram_user_id: int) -> list[ReprocessResult]:
        active_job = self.repository.get_active_job(telegram_user_id)
        if active_job is None:
            raise ValueError("Nenhuma vaga ativa selecionada.")
        candidates = self.repository.list_candidates(telegram_user_id, active_job.id)
        failed = [
            candidate
            for candidate in candidates
            if candidate.status in {STATUS_EXTRACTION_FAILED, STATUS_FILE_EXTRACTION_FAILED}
        ]
        results: list[ReprocessResult] = []
        for candidate in failed:
            try:
                results.append(self.reprocess_candidate(telegram_user_id, candidate.id))
            except Exception as exc:  # noqa: BLE001 - lote não deve ser interrompido.
                logger.exception("Falha ao reprocessar candidato %s", candidate.id)
                results.append(
                    ReprocessResult(candidate=candidate, success=False, message=str(exc))
                )
        return results

    def _extract_summary(self, raw_text: str) -> tuple[StructuredCandidateSummary, bool, list[str]]:
        explicit_name = extract_name(raw_text)
        fallback = StructuredCandidateSummary(nome=explicit_name or NAO_INFORMADO)
        if self.llm_client is None:
            return (
                fallback,
                False,
                ["Resumo estruturado não gerado porque o Ollama não foi iniciado."],
            )

        prompt = build_candidate_extraction_prompt(raw_text)
        try:
            summary = self.llm_client.generate_validated_json(
                prompt=prompt,
                schema=StructuredCandidateSummary,
                schema_description=json.dumps(CANDIDATE_SCHEMA_KEYS, ensure_ascii=False, indent=2),
            )
            if explicit_name:
                summary.nome = explicit_name
            return summary, True, []
        except OllamaError as exc:
            logger.warning("Falha ao estruturar candidato via Ollama: %s", exc)
            return (
                fallback,
                False,
                [
                    "❌ Não consegui conectar ao Ollama ou validar o resumo do candidato. "
                    "O texto foi salvo para reprocessamento."
                ],
            )


def _model_json(model: StructuredCandidateSummary) -> str:
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False)
