import json
import sqlite3
from pathlib import Path

import pytest

from app.database.repository import Repository
from app.llm.schemas import StructuredJobSummary
from app.services.history_service import HistoryService


def _create_job(repo: Repository, user_id: int, title: str = "Vaga") -> int:
    summary = StructuredJobSummary(titulo=title)
    job = repo.create_job(
        telegram_user_id=user_id,
        title=title,
        raw_text=f"Título: {title}",
        structured_summary_json=json.dumps(summary.model_dump(mode="json"), ensure_ascii=False),
    )
    return job.id


def test_repository_creates_sqlite_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "bot.db"
    Repository(db_path)

    with sqlite3.connect(db_path) as conn:
        table_rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        tables = {row[0] for row in table_rows}

    assert {"users", "jobs", "candidates", "files", "analyses", "analysis_candidates"} <= tables


def test_history_returns_last_five_analyses(tmp_path: Path) -> None:
    repo = Repository(tmp_path / "bot.db")
    job_id = _create_job(repo, 1)
    for index in range(6):
        analysis = repo.create_analysis(
            telegram_user_id=1,
            job_id=job_id,
            job_title_snapshot=f"Vaga {index}",
            result_summary_json=json.dumps(
                {"rendered_header": f"Header {index}", "candidatos_analisados": 1},
                ensure_ascii=False,
            ),
        )
        repo.add_analysis_candidate(
            analysis_id=analysis.id,
            candidate_id=index + 1,
            candidate_name_snapshot=f"Candidato {index}",
            score=70 + index,
            classification="Média aderência",
            priority="Média",
            result_json="{}",
            rendered_message=f"Resultado {index}",
        )

    recent = repo.list_recent_analyses(1, limit=5)

    assert len(recent) == 5
    assert recent[0]["job_title_snapshot"] == "Vaga 5"


def test_result_validates_analysis_owner(tmp_path: Path) -> None:
    repo = Repository(tmp_path / "bot.db")
    user_one_job = _create_job(repo, 1, "Vaga User 1")
    user_two_job = _create_job(repo, 2, "Vaga User 2")
    analysis = repo.create_analysis(
        telegram_user_id=2,
        job_id=user_two_job,
        job_title_snapshot="Vaga User 2",
        result_summary_json=json.dumps({"rendered_header": "Header"}, ensure_ascii=False),
    )
    repo.add_analysis_candidate(
        analysis_id=analysis.id,
        candidate_id=10,
        candidate_name_snapshot="Candidato",
        score=90,
        classification="Alta aderência",
        priority="Alta",
        result_json="{}",
        rendered_message="Mensagem salva",
    )
    assert user_one_job

    history = HistoryService(repo)
    with pytest.raises(ValueError):
        history.get_saved_result_messages(1, analysis.id)
