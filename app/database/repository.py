from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.database.connection import get_connection, init_db
from app.database.models import (
    STATUS_FILE_EXTRACTION_FAILED,
    STATUS_PENDING_NAME,
    STATUS_REMOVED,
    Analysis,
    AnalysisCandidate,
    Candidate,
    FileRecord,
    Job,
    UserState,
)


def _job_from_row(row: Any) -> Job:
    return Job(
        id=row["id"],
        telegram_user_id=row["telegram_user_id"],
        title=row["title"],
        raw_text=row["raw_text"],
        structured_summary_json=row["structured_summary_json"],
        is_active=bool(row["is_active"]),
        is_removed=bool(row["is_removed"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _candidate_from_row(row: Any) -> Candidate:
    return Candidate(
        id=row["id"],
        telegram_user_id=row["telegram_user_id"],
        job_id=row["job_id"],
        name=row["name"],
        raw_text=row["raw_text"],
        structured_summary_json=row["structured_summary_json"],
        status=row["status"],
        source_type=row["source_type"],
        source_file_id=row["source_file_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        is_removed=bool(row["is_removed"]),
    )


def _file_from_row(row: Any) -> FileRecord:
    return FileRecord(
        id=row["id"],
        telegram_user_id=row["telegram_user_id"],
        job_id=row["job_id"],
        candidate_id=row["candidate_id"],
        original_filename=row["original_filename"],
        stored_path=row["stored_path"],
        extension=row["extension"],
        size_bytes=row["size_bytes"],
        extraction_status=row["extraction_status"],
        extracted_text=row["extracted_text"],
        created_at=row["created_at"],
    )


def _analysis_from_row(row: Any) -> Analysis:
    return Analysis(
        id=row["id"],
        telegram_user_id=row["telegram_user_id"],
        job_id=row["job_id"],
        job_title_snapshot=row["job_title_snapshot"],
        result_summary_json=row["result_summary_json"],
        created_at=row["created_at"],
    )


def _analysis_candidate_from_row(row: Any) -> AnalysisCandidate:
    return AnalysisCandidate(
        id=row["id"],
        analysis_id=row["analysis_id"],
        candidate_id=row["candidate_id"],
        candidate_name_snapshot=row["candidate_name_snapshot"],
        score=row["score"],
        classification=row["classification"],
        priority=row["priority"],
        result_json=row["result_json"],
        rendered_message=row["rendered_message"],
        created_at=row["created_at"],
    )


class Repository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        init_db(self.database_path)

    def ensure_user(self, telegram_user_id: int) -> None:
        with get_connection(self.database_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO users (telegram_user_id)
                VALUES (?)
                """,
                (telegram_user_id,),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO user_state (telegram_user_id)
                VALUES (?)
                """,
                (telegram_user_id,),
            )

    def get_state(self, telegram_user_id: int) -> UserState:
        self.ensure_user(telegram_user_id)
        with get_connection(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT
                    telegram_user_id,
                    active_job_id,
                    pending_action,
                    pending_payload_json,
                    updated_at
                FROM user_state
                WHERE telegram_user_id = ?
                """,
                (telegram_user_id,),
            ).fetchone()
        return UserState(
            telegram_user_id=row["telegram_user_id"],
            active_job_id=row["active_job_id"],
            pending_action=row["pending_action"],
            pending_payload_json=row["pending_payload_json"],
            updated_at=row["updated_at"],
        )

    def set_pending_action(
        self,
        telegram_user_id: int,
        action: str | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.ensure_user(telegram_user_id)
        payload_json = json.dumps(payload or {}, ensure_ascii=False) if action else None
        with get_connection(self.database_path) as conn:
            conn.execute(
                """
                UPDATE user_state
                SET pending_action = ?, pending_payload_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = ?
                """,
                (action, payload_json, telegram_user_id),
            )

    def get_pending_payload(self, telegram_user_id: int) -> dict[str, Any]:
        state = self.get_state(telegram_user_id)
        if not state.pending_payload_json:
            return {}
        return json.loads(state.pending_payload_json)

    def clear_session(self, telegram_user_id: int) -> None:
        self.ensure_user(telegram_user_id)
        with get_connection(self.database_path) as conn:
            conn.execute(
                """
                UPDATE user_state
                SET active_job_id = NULL,
                    pending_action = NULL,
                    pending_payload_json = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = ?
                """,
                (telegram_user_id,),
            )
            conn.execute(
                """
                UPDATE jobs
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = ?
                """,
                (telegram_user_id,),
            )

    def set_active_job(self, telegram_user_id: int, job_id: int | None) -> None:
        self.ensure_user(telegram_user_id)
        with get_connection(self.database_path) as conn:
            conn.execute(
                """
                UPDATE jobs
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = ?
                """,
                (telegram_user_id,),
            )
            if job_id is not None:
                conn.execute(
                    """
                    UPDATE jobs
                    SET is_active = 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND telegram_user_id = ? AND is_removed = 0
                    """,
                    (job_id, telegram_user_id),
                )
            conn.execute(
                """
                UPDATE user_state
                SET active_job_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = ?
                """,
                (job_id, telegram_user_id),
            )

    def create_job(
        self,
        telegram_user_id: int,
        title: str,
        raw_text: str,
        structured_summary_json: str,
    ) -> Job:
        self.ensure_user(telegram_user_id)
        with get_connection(self.database_path) as conn:
            conn.execute(
                """
                UPDATE jobs
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = ?
                """,
                (telegram_user_id,),
            )
            cursor = conn.execute(
                """
                INSERT INTO jobs (
                    telegram_user_id, title, raw_text, structured_summary_json, is_active
                )
                VALUES (?, ?, ?, ?, 1)
                """,
                (telegram_user_id, title, raw_text, structured_summary_json),
            )
            job_id = cursor.lastrowid
            conn.execute(
                """
                UPDATE user_state
                SET active_job_id = ?, pending_action = NULL, pending_payload_json = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = ?
                """,
                (job_id, telegram_user_id),
            )
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _job_from_row(row)

    def update_job(
        self,
        telegram_user_id: int,
        job_id: int,
        title: str,
        raw_text: str,
        structured_summary_json: str,
    ) -> Job | None:
        with get_connection(self.database_path) as conn:
            conn.execute(
                """
                UPDATE jobs
                SET title = ?, raw_text = ?, structured_summary_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND telegram_user_id = ? AND is_removed = 0
                """,
                (title, raw_text, structured_summary_json, job_id, telegram_user_id),
            )
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE id = ? AND telegram_user_id = ?
                """,
                (job_id, telegram_user_id),
            ).fetchone()
        return _job_from_row(row) if row else None

    def get_job(self, telegram_user_id: int, job_id: int) -> Job | None:
        with get_connection(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE id = ? AND telegram_user_id = ?
                """,
                (job_id, telegram_user_id),
            ).fetchone()
        return _job_from_row(row) if row else None

    def get_active_job(self, telegram_user_id: int) -> Job | None:
        state = self.get_state(telegram_user_id)
        if state.active_job_id is not None:
            job = self.get_job(telegram_user_id, state.active_job_id)
            if job and not job.is_removed:
                return job

        with get_connection(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM jobs
                WHERE telegram_user_id = ? AND is_active = 1 AND is_removed = 0
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (telegram_user_id,),
            ).fetchone()
        if not row:
            return None
        job = _job_from_row(row)
        self.set_active_job(telegram_user_id, job.id)
        return job

    def list_jobs(self, telegram_user_id: int, include_removed: bool = False) -> list[Job]:
        condition = "" if include_removed else "AND is_removed = 0"
        with get_connection(self.database_path) as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM jobs
                WHERE telegram_user_id = ? {condition}
                ORDER BY created_at DESC, id DESC
                """,
                (telegram_user_id,),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def remove_job(self, telegram_user_id: int, job_id: int) -> bool:
        with get_connection(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT is_active FROM jobs
                WHERE id = ? AND telegram_user_id = ? AND is_removed = 0
                """,
                (job_id, telegram_user_id),
            ).fetchone()
            if not row:
                return False

            conn.execute(
                """
                UPDATE jobs
                SET is_removed = 1, is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND telegram_user_id = ?
                """,
                (job_id, telegram_user_id),
            )

            if row["is_active"]:
                replacement = conn.execute(
                    """
                    SELECT id FROM jobs
                    WHERE telegram_user_id = ? AND is_removed = 0
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """,
                    (telegram_user_id,),
                ).fetchone()
                active_job_id = replacement["id"] if replacement else None
                if active_job_id is not None:
                    conn.execute(
                        """
                        UPDATE jobs
                        SET is_active = 1, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (active_job_id,),
                    )
                conn.execute(
                    """
                    UPDATE user_state
                    SET active_job_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_user_id = ?
                    """,
                    (active_job_id, telegram_user_id),
                )
        return True

    def create_candidate(
        self,
        telegram_user_id: int,
        job_id: int,
        name: str,
        raw_text: str,
        structured_summary_json: str,
        status: str,
        source_type: str,
        source_file_id: int | None = None,
    ) -> Candidate:
        with get_connection(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO candidates (
                    telegram_user_id, job_id, name, raw_text, structured_summary_json,
                    status, source_type, source_file_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_user_id,
                    job_id,
                    name,
                    raw_text,
                    structured_summary_json,
                    status,
                    source_type,
                    source_file_id,
                ),
            )
            candidate_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
        return _candidate_from_row(row)

    def update_candidate(
        self,
        telegram_user_id: int,
        candidate_id: int,
        raw_text: str,
        name: str,
        structured_summary_json: str,
        status: str,
    ) -> Candidate | None:
        with get_connection(self.database_path) as conn:
            conn.execute(
                """
                UPDATE candidates
                SET raw_text = ?, name = ?, structured_summary_json = ?, status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND telegram_user_id = ? AND is_removed = 0
                """,
                (raw_text, name, structured_summary_json, status, candidate_id, telegram_user_id),
            )
            row = conn.execute(
                "SELECT * FROM candidates WHERE id = ? AND telegram_user_id = ?",
                (candidate_id, telegram_user_id),
            ).fetchone()
        return _candidate_from_row(row) if row else None

    def get_candidate(self, telegram_user_id: int, candidate_id: int) -> Candidate | None:
        with get_connection(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM candidates
                WHERE id = ? AND telegram_user_id = ?
                """,
                (candidate_id, telegram_user_id),
            ).fetchone()
        return _candidate_from_row(row) if row else None

    def list_candidates(
        self,
        telegram_user_id: int,
        job_id: int,
        include_removed: bool = False,
    ) -> list[Candidate]:
        condition = "" if include_removed else "AND is_removed = 0"
        with get_connection(self.database_path) as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM candidates
                WHERE telegram_user_id = ? AND job_id = ? {condition}
                ORDER BY created_at ASC, id ASC
                """,
                (telegram_user_id, job_id),
            ).fetchall()
        return [_candidate_from_row(row) for row in rows]

    def list_eligible_candidates(self, telegram_user_id: int, job_id: int) -> list[Candidate]:
        blocked_statuses = (
            STATUS_PENDING_NAME,
            STATUS_FILE_EXTRACTION_FAILED,
            STATUS_REMOVED,
        )
        placeholders = ", ".join("?" for _ in blocked_statuses)
        with get_connection(self.database_path) as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM candidates
                WHERE telegram_user_id = ?
                  AND job_id = ?
                  AND is_removed = 0
                  AND status NOT IN ({placeholders})
                ORDER BY created_at ASC, id ASC
                """,
                (telegram_user_id, job_id, *blocked_statuses),
            ).fetchall()
        return [_candidate_from_row(row) for row in rows]

    def mark_candidate_removed(self, telegram_user_id: int, candidate_id: int, job_id: int) -> bool:
        with get_connection(self.database_path) as conn:
            cursor = conn.execute(
                """
                UPDATE candidates
                SET is_removed = 1, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND telegram_user_id = ? AND job_id = ? AND is_removed = 0
                """,
                (STATUS_REMOVED, candidate_id, telegram_user_id, job_id),
            )
        return cursor.rowcount > 0

    def create_file_record(
        self,
        telegram_user_id: int,
        job_id: int | None,
        candidate_id: int | None,
        original_filename: str,
        stored_path: str,
        extension: str,
        size_bytes: int,
        extraction_status: str,
        extracted_text: str,
    ) -> FileRecord:
        with get_connection(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO files (
                    telegram_user_id, job_id, candidate_id, original_filename, stored_path,
                    extension, size_bytes, extraction_status, extracted_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telegram_user_id,
                    job_id,
                    candidate_id,
                    original_filename,
                    stored_path,
                    extension,
                    size_bytes,
                    extraction_status,
                    extracted_text,
                ),
            )
            file_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        return _file_from_row(row)

    def update_file_candidate_link(self, file_id: int, candidate_id: int) -> None:
        with get_connection(self.database_path) as conn:
            conn.execute(
                """
                UPDATE files
                SET candidate_id = ?
                WHERE id = ?
                """,
                (candidate_id, file_id),
            )

    def get_file(self, telegram_user_id: int, file_id: int) -> FileRecord | None:
        with get_connection(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM files
                WHERE id = ? AND telegram_user_id = ?
                """,
                (file_id, telegram_user_id),
            ).fetchone()
        return _file_from_row(row) if row else None

    def create_analysis(
        self,
        telegram_user_id: int,
        job_id: int,
        job_title_snapshot: str,
        result_summary_json: str,
    ) -> Analysis:
        with get_connection(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO analyses (
                    telegram_user_id, job_id, job_title_snapshot, result_summary_json
                )
                VALUES (?, ?, ?, ?)
                """,
                (telegram_user_id, job_id, job_title_snapshot, result_summary_json),
            )
            analysis_id = cursor.lastrowid
            row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        return _analysis_from_row(row)

    def add_analysis_candidate(
        self,
        analysis_id: int,
        candidate_id: int,
        candidate_name_snapshot: str,
        score: int,
        classification: str,
        priority: str,
        result_json: str,
        rendered_message: str,
    ) -> AnalysisCandidate:
        with get_connection(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO analysis_candidates (
                    analysis_id, candidate_id, candidate_name_snapshot, score, classification,
                    priority, result_json, rendered_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    candidate_id,
                    candidate_name_snapshot,
                    score,
                    classification,
                    priority,
                    result_json,
                    rendered_message,
                ),
            )
            analysis_candidate_id = cursor.lastrowid
            row = conn.execute(
                "SELECT * FROM analysis_candidates WHERE id = ?",
                (analysis_candidate_id,),
            ).fetchone()
        return _analysis_candidate_from_row(row)

    def list_recent_analyses(self, telegram_user_id: int, limit: int = 5) -> list[dict[str, Any]]:
        with get_connection(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    a.id,
                    a.job_id,
                    a.job_title_snapshot,
                    a.result_summary_json,
                    a.created_at,
                    j.is_removed AS job_removed,
                    COUNT(ac.id) AS candidate_count,
                    (
                        SELECT candidate_name_snapshot
                        FROM analysis_candidates ac2
                        WHERE ac2.analysis_id = a.id
                        ORDER BY ac2.score DESC, ac2.id ASC
                        LIMIT 1
                    ) AS best_candidate
                FROM analyses a
                LEFT JOIN jobs j ON j.id = a.job_id
                LEFT JOIN analysis_candidates ac ON ac.analysis_id = a.id
                WHERE a.telegram_user_id = ?
                GROUP BY a.id
                ORDER BY a.created_at DESC, a.id DESC
                LIMIT ?
                """,
                (telegram_user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_analysis(self, telegram_user_id: int, analysis_id: int) -> Analysis | None:
        with get_connection(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM analyses
                WHERE id = ? AND telegram_user_id = ?
                """,
                (analysis_id, telegram_user_id),
            ).fetchone()
        return _analysis_from_row(row) if row else None

    def list_analysis_candidates(self, analysis_id: int) -> list[AnalysisCandidate]:
        with get_connection(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM analysis_candidates
                WHERE analysis_id = ?
                ORDER BY score DESC, id ASC
                """,
                (analysis_id,),
            ).fetchall()
        return [_analysis_candidate_from_row(row) for row in rows]
