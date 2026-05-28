from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.database.models import Job
from app.database.repository import Repository
from app.llm.ollama_client import OllamaClient, OllamaError
from app.llm.prompts import JOB_SCHEMA_KEYS, build_job_extraction_prompt
from app.llm.schemas import NAO_INFORMADO, StructuredJobSummary
from app.utils.text_parser import extract_title, fallback_title

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobResult:
    job: Job
    warnings: list[str] = field(default_factory=list)


class JobService:
    def __init__(self, repository: Repository, llm_client: OllamaClient | None = None) -> None:
        self.repository = repository
        self.llm_client = llm_client

    def create_job_from_text(self, telegram_user_id: int, raw_text: str) -> JobResult:
        summary, warnings = self._extract_summary(raw_text)
        title = self._resolve_title(raw_text, summary)
        if summary.titulo == NAO_INFORMADO:
            summary.titulo = title
        job = self.repository.create_job(
            telegram_user_id=telegram_user_id,
            title=title,
            raw_text=raw_text,
            structured_summary_json=_model_json(summary),
        )
        logger.info("Vaga criada user=%s job=%s title=%s", telegram_user_id, job.id, title)
        return JobResult(job=job, warnings=warnings)

    def replace_job_text(self, telegram_user_id: int, job_id: int, raw_text: str) -> JobResult:
        summary, warnings = self._extract_summary(raw_text)
        title = self._resolve_title(raw_text, summary)
        if summary.titulo == NAO_INFORMADO:
            summary.titulo = title
        job = self.repository.update_job(
            telegram_user_id=telegram_user_id,
            job_id=job_id,
            title=title,
            raw_text=raw_text,
            structured_summary_json=_model_json(summary),
        )
        if job is None:
            raise ValueError("Vaga não encontrada ou removida.")
        logger.info("Vaga atualizada user=%s job=%s title=%s", telegram_user_id, job.id, title)
        return JobResult(job=job, warnings=warnings)

    def _extract_summary(self, raw_text: str) -> tuple[StructuredJobSummary, list[str]]:
        explicit_title = extract_title(raw_text)
        fallback = StructuredJobSummary(titulo=explicit_title or fallback_title(raw_text))
        if self.llm_client is None:
            return fallback, [
                "Resumo estruturado não gerado porque o cliente Ollama não foi iniciado."
            ]

        prompt = build_job_extraction_prompt(raw_text)
        try:
            summary = self.llm_client.generate_validated_json(
                prompt=prompt,
                schema=StructuredJobSummary,
                schema_description=json.dumps(JOB_SCHEMA_KEYS, ensure_ascii=False, indent=2),
            )
            if explicit_title:
                summary.titulo = explicit_title
            return summary, []
        except OllamaError as exc:
            logger.warning("Falha ao estruturar vaga via Ollama: %s", exc)
            return fallback, [
                "❌ Não consegui conectar ao Ollama ou validar o resumo da vaga. "
                "A vaga foi salva e pode ser reprocessada depois."
            ]

    @staticmethod
    def _resolve_title(raw_text: str, summary: StructuredJobSummary) -> str:
        explicit_title = extract_title(raw_text)
        if explicit_title:
            return explicit_title
        if summary.titulo and summary.titulo != NAO_INFORMADO:
            return summary.titulo
        return fallback_title(raw_text)


def _model_json(model: StructuredJobSummary) -> str:
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False)
