from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from app.database.models import Candidate
from app.database.repository import Repository
from app.llm.ollama_client import OllamaClient
from app.llm.prompts import ANALYSIS_SCHEMA_KEYS, build_candidate_analysis_prompt
from app.llm.schemas import CandidateAnalysisResult, ConsolidatedAnalysisResult

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int, Candidate], Awaitable[None]]


@dataclass(frozen=True)
class AnalysisExecutionResult:
    analysis_id: int
    header_message: str
    candidate_messages: list[str]


class AnalysisService:
    def __init__(
        self,
        repository: Repository,
        llm_client: OllamaClient,
        max_candidates_per_analysis: int = 5,
    ) -> None:
        self.repository = repository
        self.llm_client = llm_client
        self.max_candidates_per_analysis = max_candidates_per_analysis

    async def run_analysis(
        self,
        telegram_user_id: int,
        candidate_ids: list[int] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> AnalysisExecutionResult:
        job = self.repository.get_active_job(telegram_user_id)
        if job is None:
            raise ValueError("Nenhuma vaga ativa selecionada.")

        candidates = self._resolve_candidates(telegram_user_id, job.id, candidate_ids)
        if not candidates:
            raise ValueError("Nenhum candidato elegível para análise.")
        if len(candidates) > self.max_candidates_per_analysis:
            raise ValueError(f"Selecione no máximo {self.max_candidates_per_analysis} candidatos.")

        logger.info(
            "Analise iniciada user=%s job=%s candidates=%s",
            telegram_user_id,
            job.id,
            [candidate.id for candidate in candidates],
        )

        results: list[tuple[Candidate, CandidateAnalysisResult]] = []
        total = len(candidates)
        for index, candidate in enumerate(candidates, start=1):
            if progress_callback:
                await progress_callback(index, total, candidate)
            prompt = build_candidate_analysis_prompt(
                job_raw_text=job.raw_text,
                job_summary_json=job.structured_summary_json,
                candidate_raw_text=candidate.raw_text,
                candidate_summary_json=candidate.structured_summary_json,
            )
            result = self.llm_client.generate_validated_json(
                prompt=prompt,
                schema=CandidateAnalysisResult,
                schema_description=json.dumps(ANALYSIS_SCHEMA_KEYS, ensure_ascii=False, indent=2),
            )
            result.nome = candidate.name
            results.append((candidate, result))

        results.sort(key=lambda item: item[1].score, reverse=True)
        best_score = results[0][1].score
        consolidated = ConsolidatedAnalysisResult(
            vaga=job.title,
            candidatos_analisados=len(results),
            melhor_score=best_score,
            ranking=[result for _candidate, result in results],
        )
        header = render_analysis_header(job.title, len(results), best_score)
        candidate_messages = [
            render_candidate_result(position, candidate.name, result)
            for position, (candidate, result) in enumerate(results, start=1)
        ]

        analysis_payload = {
            **consolidated.model_dump(mode="json"),
            "rendered_header": header,
            "prompt_version": "2026-05-23-v1",
        }
        analysis = self.repository.create_analysis(
            telegram_user_id=telegram_user_id,
            job_id=job.id,
            job_title_snapshot=job.title,
            result_summary_json=json.dumps(analysis_payload, ensure_ascii=False),
        )
        for message, (candidate, result) in zip(candidate_messages, results, strict=True):
            self.repository.add_analysis_candidate(
                analysis_id=analysis.id,
                candidate_id=candidate.id,
                candidate_name_snapshot=candidate.name,
                score=result.score,
                classification=result.classificacao,
                priority=result.prioridade,
                result_json=json.dumps(result.model_dump(mode="json"), ensure_ascii=False),
                rendered_message=message,
            )

        logger.info("Analise concluida user=%s analysis=%s", telegram_user_id, analysis.id)
        return AnalysisExecutionResult(
            analysis_id=analysis.id,
            header_message=header,
            candidate_messages=candidate_messages,
        )

    def _resolve_candidates(
        self,
        telegram_user_id: int,
        job_id: int,
        candidate_ids: list[int] | None,
    ) -> list[Candidate]:
        eligible = self.repository.list_eligible_candidates(telegram_user_id, job_id)
        if candidate_ids is None:
            return eligible
        selected_ids = set(candidate_ids)
        selected = [candidate for candidate in eligible if candidate.id in selected_ids]
        missing = selected_ids - {candidate.id for candidate in selected}
        if missing:
            raise ValueError("Um ou mais candidatos selecionados não são elegíveis para análise.")
        return selected


def render_analysis_header(job_title: str, candidate_count: int, best_score: int) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    return (
        "🏆 Análise concluída\n\n"
        f"Vaga: {job_title}\n"
        f"Candidatos analisados: {candidate_count}\n"
        f"Melhor score: {best_score}%\n"
        f"Data/hora: {now}"
    )


def render_candidate_result(
    position: int,
    candidate_name: str,
    result: CandidateAnalysisResult,
) -> str:
    lines = [
        f"🏆 Ranking #{position} — {candidate_name}",
        "",
        f"📊 Aderência: {result.score}%",
        f"Classificação: {result.classificacao}",
        f"🎯 Prioridade: {result.prioridade}",
        "",
        "📌 Parecer de triagem:",
        result.parecer,
        "",
        "✅ Principais pontos de aderência:",
        *_bullet_lines(result.pontos_aderencia),
        "",
        "⚠️ Pontos de atenção:",
        *_bullet_lines(result.pontos_atencao or ["Nenhum ponto crítico evidenciado."]),
    ]
    if result.pontos_validacao_manual:
        lines.extend(
            [
                "",
                "🔎 Pontos para validação manual:",
                *_bullet_lines(result.pontos_validacao_manual),
            ]
        )
    lines.extend(["", "🎯 Recomendação:", result.recomendacao])
    return "\n".join(lines)


def _bullet_lines(items: list[str]) -> list[str]:
    return [f"• {item}" for item in items if item.strip()]
