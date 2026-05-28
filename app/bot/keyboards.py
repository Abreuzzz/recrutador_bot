from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import Candidate


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Cadastrar vaga", callback_data="cmd:vaga")],
            [InlineKeyboardButton("Adicionar candidato", callback_data="cmd:candidato")],
            [InlineKeyboardButton("Listar dados atuais", callback_data="cmd:listar")],
            [InlineKeyboardButton("Analisar aderência", callback_data="cmd:analisar")],
            [InlineKeyboardButton("Ver histórico", callback_data="cmd:historico")],
            [InlineKeyboardButton("Ajuda", callback_data="cmd:help")],
        ]
    )


def confirm_clear_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirmar limpeza", callback_data="clear:yes"),
                InlineKeyboardButton("Cancelar", callback_data="clear:no"),
            ]
        ]
    )


def confirm_remove_candidate_keyboard(candidate_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Confirmar remoção",
                    callback_data=f"cand_remove:yes:{candidate_id}",
                ),
                InlineKeyboardButton("Cancelar", callback_data="cand_remove:no"),
            ]
        ]
    )


def confirm_remove_job_keyboard(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirmar remoção", callback_data=f"job_remove:yes:{job_id}"),
                InlineKeyboardButton("Cancelar", callback_data="job_remove:no"),
            ]
        ]
    )


def file_context_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Vaga", callback_data="filectx:job"),
                InlineKeyboardButton("Candidato", callback_data="filectx:candidate"),
            ],
            [InlineKeyboardButton("Cancelar", callback_data="filectx:cancel")],
        ]
    )


def job_file_decision_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Criar nova vaga", callback_data="jobfile:new"),
                InlineKeyboardButton("Substituir vaga ativa", callback_data="jobfile:replace"),
            ],
            [InlineKeyboardButton("Cancelar", callback_data="jobfile:cancel")],
        ]
    )


def confirm_replace_job_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Confirmar substituição",
                    callback_data="jobfile:replace_confirm",
                ),
                InlineKeyboardButton("Cancelar", callback_data="jobfile:cancel"),
            ]
        ]
    )


def duplicate_candidate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Cadastrar mesmo assim", callback_data="dup:yes"),
                InlineKeyboardButton("Cancelar cadastro", callback_data="dup:no"),
            ]
        ]
    )


def analysis_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirmar análise", callback_data="an:confirm"),
                InlineKeyboardButton("Cancelar", callback_data="an:cancel"),
            ]
        ]
    )


def analysis_selection_keyboard(
    candidates: list[Candidate],
    selected_ids: list[int],
    limit: int,
) -> InlineKeyboardMarkup:
    selected = set(selected_ids)
    rows: list[list[InlineKeyboardButton]] = []
    for candidate in candidates:
        marker = "✅" if candidate.id in selected else "⬜"
        label = f"{marker} ID {candidate.id} — {candidate.name}"
        if len(label) > 54:
            label = label[:51] + "..."
        rows.append([InlineKeyboardButton(label, callback_data=f"an:toggle:{candidate.id}")])
    rows.append(
        [
            InlineKeyboardButton(
                f"Confirmar análise ({len(selected_ids)}/{limit})",
                callback_data="an:confirm",
            ),
            InlineKeyboardButton("Cancelar", callback_data="an:cancel"),
        ]
    )
    return InlineKeyboardMarkup(rows)
