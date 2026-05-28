from __future__ import annotations

import json

from app.database.repository import Repository


class HistoryService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def render_recent_history(self, telegram_user_id: int) -> str:
        analyses = self.repository.list_recent_analyses(telegram_user_id, limit=5)
        if not analyses:
            return "Nenhuma análise encontrada no histórico."

        lines = ["📌 Últimas análises:"]
        for analysis in analyses:
            removed_suffix = " — vaga removida" if analysis.get("job_removed") else ""
            best_candidate = analysis.get("best_candidate") or "Não informado"
            lines.append(
                "\n"
                f"ID {analysis['id']} — {analysis['job_title_snapshot']}{removed_suffix}\n"
                f"Data/hora: {analysis['created_at']}\n"
                f"Candidatos analisados: {analysis['candidate_count']}\n"
                f"Melhor candidato: {best_candidate}"
            )
        return "\n".join(lines)

    def get_saved_result_messages(self, telegram_user_id: int, analysis_id: int) -> list[str]:
        analysis = self.repository.get_analysis(telegram_user_id, analysis_id)
        if analysis is None:
            raise ValueError("Resultado não encontrado para este usuário.")

        payload = json.loads(analysis.result_summary_json)
        header = payload.get("rendered_header") or (
            "🏆 Análise concluída\n\n"
            f"Vaga: {analysis.job_title_snapshot}\n"
            f"Candidatos analisados: {payload.get('candidatos_analisados', 0)}\n"
            f"Melhor score: {payload.get('melhor_score', 0)}%"
        )
        candidate_messages = [
            item.rendered_message for item in self.repository.list_analysis_candidates(analysis_id)
        ]
        return [header, *candidate_messages]
