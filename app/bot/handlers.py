from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.bot.access_control import is_authorized, log_unauthorized
from app.bot.keyboards import (
    analysis_confirm_keyboard,
    analysis_selection_keyboard,
    confirm_clear_keyboard,
    confirm_remove_candidate_keyboard,
    confirm_remove_job_keyboard,
    confirm_replace_job_keyboard,
    duplicate_candidate_keyboard,
    file_context_keyboard,
    job_file_decision_keyboard,
    start_keyboard,
)
from app.bot.messages import (
    HELP_TEXT,
    OLLAMA_ERROR_TEXT,
    START_TEXT,
    format_analysis_candidates,
    format_candidate_created,
    format_job_created,
    format_job_updated,
    format_jobs,
    format_list,
)
from app.config import Settings
from app.database.models import SOURCE_FILE, STATUS_FILE_EXTRACTION_FAILED
from app.database.repository import Repository
from app.files.extractors import FileExtractionError, extract_text_from_file
from app.files.storage import save_telegram_file_reference
from app.llm.ollama_client import OllamaClient, OllamaError
from app.services.analysis_service import AnalysisService
from app.services.candidate_service import CandidateService
from app.services.history_service import HistoryService
from app.services.job_service import JobService

logger = logging.getLogger(__name__)


def build_application(settings: Settings) -> Application:
    repository = Repository(settings.database_path)
    llm_client = OllamaClient(settings)

    application = ApplicationBuilder().token(settings.telegram_bot_token).build()
    application.bot_data.update(
        {
            "settings": settings,
            "repository": repository,
            "job_service": JobService(repository, llm_client),
            "candidate_service": CandidateService(repository, llm_client),
            "analysis_service": AnalysisService(
                repository,
                llm_client,
                max_candidates_per_analysis=settings.max_candidates_per_analysis,
            ),
            "history_service": HistoryService(repository),
        }
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("vaga", vaga_command))
    application.add_handler(CommandHandler("candidato", candidato_command))
    application.add_handler(CommandHandler("listar", listar_command))
    application.add_handler(CommandHandler("analisar", analisar_command))
    application.add_handler(CommandHandler("limpar", limpar_command))
    application.add_handler(CommandHandler("historico", historico_command))
    application.add_handler(CommandHandler("resultado", resultado_command))
    application.add_handler(CommandHandler("vagas", vagas_command))
    application.add_handler(CommandHandler("selecionar", selecionar_command))
    application.add_handler(CommandHandler("remover_candidato", remover_candidato_command))
    application.add_handler(CommandHandler("editar_candidato", editar_candidato_command))
    application.add_handler(CommandHandler("remover_vaga", remover_vaga_command))
    application.add_handler(CommandHandler("reprocessar_candidato", reprocessar_candidato_command))
    application.add_handler(CommandHandler("reprocessar_falhas", reprocessar_falhas_command))
    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    return application


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    await _reply(update, START_TEXT, reply_markup=start_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    await _reply(update, HELP_TEXT)


async def vaga_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    telegram_user_id = _user_id(update)
    text = _command_remainder(update)
    repository = _repository(context)
    if not text:
        repository.set_pending_action(telegram_user_id, "awaiting_job_text")
        await _reply(update, "Envie a descrição da vaga em texto ou arquivo PDF, DOCX ou TXT.")
        return
    await _create_job_from_text(update, context, telegram_user_id, text)


async def candidato_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    telegram_user_id = _user_id(update)
    repository = _repository(context)
    if repository.get_active_job(telegram_user_id) is None:
        await _reply(update, "Cadastre ou selecione uma vaga antes de adicionar candidatos.")
        return

    text = _command_remainder(update)
    if not text:
        repository.set_pending_action(telegram_user_id, "awaiting_candidate_text")
        await _reply(
            update,
            "Envie o texto do candidato, múltiplos candidatos separados por --- ou arquivos.",
        )
        return
    await _add_candidates_from_text(update, context, telegram_user_id, text)


async def listar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    await _send_current_list(update, context)


async def vagas_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    telegram_user_id = _user_id(update)
    repository = _repository(context)
    state = repository.get_state(telegram_user_id)
    await _reply(update, format_jobs(repository.list_jobs(telegram_user_id), state.active_job_id))


async def selecionar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    telegram_user_id = _user_id(update)
    job_id = _first_int_arg(context)
    if job_id is None:
        await _reply(update, "Informe o ID da vaga. Exemplo: /selecionar 3")
        return
    repository = _repository(context)
    job = repository.get_job(telegram_user_id, job_id)
    if job is None or job.is_removed:
        await _reply(update, "Vaga não encontrada ou removida.")
        return
    repository.set_active_job(telegram_user_id, job_id)
    await _reply(update, f"✅ Vaga selecionada: {job.title} — ID {job.id}")


async def limpar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    await _reply(
        update,
        "Deseja limpar a seleção de vaga ativa e estados pendentes? O histórico será mantido.",
        reply_markup=confirm_clear_keyboard(),
    )


async def remover_candidato_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    telegram_user_id = _user_id(update)
    candidate_id = _first_int_arg(context)
    if candidate_id is None:
        await _reply(update, "Informe o ID do candidato. Exemplo: /remover_candidato 3")
        return
    repository = _repository(context)
    active_job = repository.get_active_job(telegram_user_id)
    candidate = repository.get_candidate(telegram_user_id, candidate_id)
    if (
        active_job is None
        or candidate is None
        or candidate.job_id != active_job.id
        or candidate.is_removed
    ):
        await _reply(update, "Candidato não encontrado na vaga ativa.")
        return
    await _reply(
        update,
        f"Confirmar remoção lógica do candidato ID {candidate.id} — {candidate.name}?",
        reply_markup=confirm_remove_candidate_keyboard(candidate.id),
    )


async def remover_vaga_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    telegram_user_id = _user_id(update)
    job_id = _first_int_arg(context)
    if job_id is None:
        await _reply(update, "Informe o ID da vaga. Exemplo: /remover_vaga 3")
        return
    job = _repository(context).get_job(telegram_user_id, job_id)
    if job is None or job.is_removed:
        await _reply(update, "Vaga não encontrada ou já removida.")
        return
    await _reply(
        update,
        f"Confirmar remoção lógica da vaga ID {job.id} — {job.title}?",
        reply_markup=confirm_remove_job_keyboard(job.id),
    )


async def editar_candidato_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    telegram_user_id = _user_id(update)
    candidate_id = _first_int_arg(context)
    if candidate_id is None:
        await _reply(update, "Informe o ID do candidato. Exemplo: /editar_candidato 3")
        return

    text = _command_remainder_after_first_arg(update)
    if not text:
        _repository(context).set_pending_action(
            telegram_user_id,
            "awaiting_candidate_edit",
            {"candidate_id": candidate_id},
        )
        await _reply(update, f"Envie o novo texto completo para o candidato ID {candidate_id}.")
        return

    await _edit_candidate_text(update, context, telegram_user_id, candidate_id, text)


async def analisar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    await _prepare_analysis(update, context)


async def historico_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    history_service = _history_service(context)
    await _reply(update, history_service.render_recent_history(_user_id(update)))


async def resultado_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    analysis_id = _first_int_arg(context)
    if analysis_id is None:
        await _reply(update, "Informe o ID da análise. Exemplo: /resultado 7")
        return
    try:
        messages = _history_service(context).get_saved_result_messages(
            _user_id(update),
            analysis_id,
        )
    except ValueError as exc:
        await _reply(update, str(exc))
        return
    for message in messages:
        await _reply(update, message)


async def reprocessar_candidato_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    candidate_id = _first_int_arg(context)
    if candidate_id is None:
        await _reply(update, "Informe o ID do candidato. Exemplo: /reprocessar_candidato 3")
        return
    try:
        result = _candidate_service(context).reprocess_candidate(_user_id(update), candidate_id)
    except ValueError as exc:
        await _reply(update, str(exc))
        return
    await _reply(update, f"{'✅' if result.success else '❌'} {result.message}")


async def reprocessar_falhas_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    try:
        results = _candidate_service(context).reprocess_failures(_user_id(update))
    except ValueError as exc:
        await _reply(update, str(exc))
        return
    if not results:
        await _reply(update, "Nenhum candidato com falha para reprocessar na vaga ativa.")
        return
    success_count = sum(1 for result in results if result.success)
    lines = [
        f"Reprocessamento concluído: {success_count}/{len(results)} candidatos corrigidos.",
        "",
    ]
    lines.extend(
        f"- ID {result.candidate.id} — {result.candidate.name}: {result.message}"
        for result in results
    )
    await _reply(update, "\n".join(lines))


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    telegram_user_id = _user_id(update)
    text = update.effective_message.text or ""
    repository = _repository(context)
    state = repository.get_state(telegram_user_id)

    if state.pending_action == "awaiting_job_text":
        await _create_job_from_text(update, context, telegram_user_id, text)
        return

    if state.pending_action == "awaiting_candidate_text":
        repository.set_pending_action(telegram_user_id, None)
        await _add_candidates_from_text(update, context, telegram_user_id, text)
        return

    if state.pending_action == "awaiting_candidate_edit":
        payload = repository.get_pending_payload(telegram_user_id)
        candidate_id = int(payload["candidate_id"])
        repository.set_pending_action(telegram_user_id, None)
        await _edit_candidate_text(update, context, telegram_user_id, candidate_id, text)
        return

    await _reply(update, "Não há fluxo ativo para esta mensagem. Use /help para ver os comandos.")


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    telegram_user_id = _user_id(update)
    document = update.effective_message.document
    if document is None:
        return
    payload = {
        "file_id": document.file_id,
        "file_name": document.file_name or "arquivo",
        "file_size": int(document.file_size or 0),
    }
    repository = _repository(context)
    state = repository.get_state(telegram_user_id)

    if state.pending_action == "awaiting_candidate_text":
        await _process_candidate_file(update, context, telegram_user_id, payload)
        return

    if state.pending_action == "awaiting_job_text":
        await _prepare_or_process_job_file(update, context, telegram_user_id, payload)
        return

    repository.set_pending_action(telegram_user_id, "awaiting_file_context", payload)
    await _reply(
        update,
        "Este arquivo corresponde a quê?",
        reply_markup=file_context_keyboard(),
    )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _require_authorized(update, context):
        return
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    data = query.data or ""
    telegram_user_id = _user_id(update)

    if data.startswith("cmd:"):
        await _handle_start_button(update, context, data.removeprefix("cmd:"))
    elif data == "clear:yes":
        _repository(context).clear_session(telegram_user_id)
        await _reply(update, "✅ Sessão limpa. Histórico preservado.")
    elif data == "clear:no":
        await _reply(update, "Limpeza cancelada.")
    elif data.startswith("cand_remove:yes:"):
        await _confirm_candidate_removal(update, context, int(data.rsplit(":", 1)[1]))
    elif data == "cand_remove:no":
        await _reply(update, "Remoção de candidato cancelada.")
    elif data.startswith("job_remove:yes:"):
        await _confirm_job_removal(update, context, int(data.rsplit(":", 1)[1]))
    elif data == "job_remove:no":
        await _reply(update, "Remoção de vaga cancelada.")
    elif data.startswith("filectx:"):
        await _handle_file_context_callback(update, context, data)
    elif data.startswith("jobfile:"):
        await _handle_job_file_callback(update, context, data)
    elif data.startswith("dup:"):
        await _handle_duplicate_callback(update, context, data)
    elif data.startswith("an:"):
        await _handle_analysis_callback(update, context, data)


async def _handle_start_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    command: str,
) -> None:
    telegram_user_id = _user_id(update)
    repository = _repository(context)
    if command == "vaga":
        repository.set_pending_action(telegram_user_id, "awaiting_job_text")
        await _reply(update, "Envie a descrição da vaga em texto ou arquivo PDF, DOCX ou TXT.")
    elif command == "candidato":
        if repository.get_active_job(telegram_user_id) is None:
            await _reply(update, "Cadastre ou selecione uma vaga antes de adicionar candidatos.")
            return
        repository.set_pending_action(telegram_user_id, "awaiting_candidate_text")
        await _reply(update, "Envie texto ou arquivo de candidato.")
    elif command == "listar":
        await _send_current_list(update, context)
    elif command == "analisar":
        await _prepare_analysis(update, context)
    elif command == "historico":
        await _reply(update, _history_service(context).render_recent_history(telegram_user_id))
    elif command == "help":
        await _reply(update, HELP_TEXT)


async def _handle_file_context_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    telegram_user_id = _user_id(update)
    repository = _repository(context)
    payload = repository.get_pending_payload(telegram_user_id)
    if not payload:
        await _reply(update, "Não encontrei arquivo pendente.")
        return
    if data == "filectx:cancel":
        repository.set_pending_action(telegram_user_id, None)
        await _reply(update, "Envio de arquivo cancelado.")
        return
    if data == "filectx:candidate":
        repository.set_pending_action(telegram_user_id, None)
        await _process_candidate_file(update, context, telegram_user_id, payload)
        return
    if data == "filectx:job":
        await _prepare_or_process_job_file(update, context, telegram_user_id, payload)


async def _handle_job_file_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    telegram_user_id = _user_id(update)
    repository = _repository(context)
    payload = repository.get_pending_payload(telegram_user_id)
    if data == "jobfile:cancel":
        repository.set_pending_action(telegram_user_id, None)
        await _reply(update, "Operação com arquivo de vaga cancelada.")
        return
    if not payload:
        await _reply(update, "Não encontrei arquivo de vaga pendente.")
        return
    if data == "jobfile:new":
        repository.set_pending_action(telegram_user_id, None)
        await _process_job_file(update, context, telegram_user_id, payload, mode="new")
        return
    if data == "jobfile:replace":
        repository.set_pending_action(telegram_user_id, "confirm_replace_job_file", payload)
        await _reply(
            update,
            "Confirmar substituição da vaga ativa?\n\n"
            "O texto e o resumo estruturado da vaga serão atualizados.\n"
            "Os candidatos já cadastrados continuarão vinculados à mesma vaga.\n"
            "Análises anteriores permanecerão no histórico.\n"
            "Uma nova análise poderá ser executada depois com /analisar.",
            reply_markup=confirm_replace_job_keyboard(),
        )
        return
    if data == "jobfile:replace_confirm":
        repository.set_pending_action(telegram_user_id, None)
        await _process_job_file(update, context, telegram_user_id, payload, mode="replace")


async def _handle_duplicate_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    telegram_user_id = _user_id(update)
    repository = _repository(context)
    payload = repository.get_pending_payload(telegram_user_id)
    if data == "dup:no":
        repository.set_pending_action(telegram_user_id, None)
        await _reply(update, "Cadastro duplicado cancelado.")
        return
    if not payload:
        await _reply(update, "Não encontrei candidato duplicado pendente.")
        return
    repository.set_pending_action(telegram_user_id, None)
    result = _candidate_service(context).add_single_candidate_from_text(
        telegram_user_id=telegram_user_id,
        raw_text=str(payload["raw_text"]),
        source_type=str(payload.get("source_type") or "texto"),
        source_file_id=payload.get("source_file_id"),
        force_duplicate=True,
    )
    if result.candidate:
        await _reply(update, format_candidate_created(result.candidate, result.warnings))


async def _handle_analysis_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    telegram_user_id = _user_id(update)
    repository = _repository(context)
    payload = repository.get_pending_payload(telegram_user_id)
    active_job = repository.get_active_job(telegram_user_id)
    if active_job is None:
        await _reply(update, "Nenhuma vaga ativa selecionada.")
        return

    if data == "an:cancel":
        repository.set_pending_action(telegram_user_id, None)
        await _reply(update, "Análise cancelada.")
        return

    if data.startswith("an:toggle:"):
        candidate_id = int(data.rsplit(":", 1)[1])
        selected_ids = [int(item) for item in payload.get("selected_ids", [])]
        limit = _settings(context).max_candidates_per_analysis
        if candidate_id in selected_ids:
            selected_ids.remove(candidate_id)
        elif len(selected_ids) >= limit:
            await _reply(update, f"Selecione no máximo {limit} candidatos.")
            return
        else:
            selected_ids.append(candidate_id)
        payload["selected_ids"] = selected_ids
        repository.set_pending_action(telegram_user_id, "select_analysis_candidates", payload)
        candidates = repository.list_eligible_candidates(telegram_user_id, active_job.id)
        text = f"Selecione até {limit} candidatos para análise."
        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.edit_text(
                text,
                reply_markup=analysis_selection_keyboard(candidates, selected_ids, limit),
            )
        return

    if data == "an:confirm":
        selected_ids = [int(item) for item in payload.get("selected_ids", [])]
        if not selected_ids:
            await _reply(update, "Selecione ao menos um candidato para analisar.")
            return
        await _run_analysis(update, context, telegram_user_id, selected_ids)


async def _prepare_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _user_id(update)
    repository = _repository(context)
    active_job = repository.get_active_job(telegram_user_id)
    if active_job is None:
        await _reply(update, "Nenhuma vaga ativa selecionada.")
        return

    candidates = repository.list_eligible_candidates(telegram_user_id, active_job.id)
    if not candidates:
        await _reply(update, "Nenhum candidato elegível para análise na vaga ativa.")
        return

    limit = _settings(context).max_candidates_per_analysis
    if len(candidates) <= limit:
        selected_ids = [candidate.id for candidate in candidates]
        repository.set_pending_action(
            telegram_user_id,
            "confirm_analysis",
            {"selected_ids": selected_ids},
        )
        await _reply(
            update,
            f"{format_analysis_candidates(candidates)}\n\nConfirmar análise?",
            reply_markup=analysis_confirm_keyboard(),
        )
        return

    repository.set_pending_action(
        telegram_user_id,
        "select_analysis_candidates",
        {"selected_ids": [], "eligible_ids": [candidate.id for candidate in candidates]},
    )
    await _reply(
        update,
        f"Há {len(candidates)} candidatos elegíveis. Selecione até {limit} para esta execução.",
        reply_markup=analysis_selection_keyboard(candidates, [], limit),
    )


async def _run_analysis(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_user_id: int,
    selected_ids: list[int],
) -> None:
    repository = _repository(context)
    repository.set_pending_action(telegram_user_id, None)
    await _reply(
        update,
        "⏳ Análise iniciada. Estou comparando a vaga com os candidatos selecionados.",
    )

    async def progress(index: int, total: int, candidate: Any) -> None:
        await _reply(update, f"Analisando {index}/{total} — {candidate.name}")

    try:
        result = await _analysis_service(context).run_analysis(
            telegram_user_id=telegram_user_id,
            candidate_ids=selected_ids,
            progress_callback=progress,
        )
    except OllamaError:
        logger.exception("Falha de Ollama durante análise")
        await _reply(update, OLLAMA_ERROR_TEXT)
        return
    except ValueError as exc:
        await _reply(update, str(exc))
        return

    await _reply(update, "Finalizando ranking...")
    await _reply(update, result.header_message)
    for message in result.candidate_messages:
        await _reply(update, message)


async def _create_job_from_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_user_id: int,
    text: str,
) -> None:
    result = _job_service(context).create_job_from_text(telegram_user_id, text)
    await _reply(update, format_job_created(result.job, result.warnings))


async def _add_candidates_from_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_user_id: int,
    text: str,
) -> None:
    try:
        results = _candidate_service(context).add_candidates_from_text(telegram_user_id, text)
    except ValueError as exc:
        await _reply(update, str(exc))
        return
    if not results:
        await _reply(update, "Não encontrei texto de candidato para cadastrar.")
        return
    await _send_candidate_results(update, context, telegram_user_id, results)


async def _send_candidate_results(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_user_id: int,
    results: list[Any],
) -> None:
    repository = _repository(context)
    for result in results:
        if result.duplicate:
            repository.set_pending_action(
                telegram_user_id,
                "confirm_duplicate_candidate",
                result.pending_payload,
            )
            await _reply(
                update,
                "⚠️ Possível duplicidade detectada.\n"
                f"Candidato semelhante: ID {result.duplicate.candidate_id}\n"
                f"Motivo: {result.duplicate.reason}\n\n"
                "Deseja cadastrar mesmo assim?",
                reply_markup=duplicate_candidate_keyboard(),
            )
            continue
        if result.candidate:
            await _reply(update, format_candidate_created(result.candidate, result.warnings))


async def _edit_candidate_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_user_id: int,
    candidate_id: int,
    text: str,
) -> None:
    try:
        candidate = _candidate_service(context).update_candidate_text(
            telegram_user_id,
            candidate_id,
            text,
        )
    except ValueError as exc:
        await _reply(update, str(exc))
        return
    await _reply(update, f"✅ Candidato atualizado: {candidate.name} — ID {candidate.id}")


async def _prepare_or_process_job_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_user_id: int,
    payload: dict[str, Any],
) -> None:
    repository = _repository(context)
    if repository.get_active_job(telegram_user_id) is not None:
        repository.set_pending_action(telegram_user_id, "awaiting_job_file_decision", payload)
        await _reply(
            update,
            "O que deseja fazer com este arquivo?",
            reply_markup=job_file_decision_keyboard(),
        )
        return
    repository.set_pending_action(telegram_user_id, None)
    await _process_job_file(update, context, telegram_user_id, payload, mode="new")


async def _process_job_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_user_id: int,
    payload: dict[str, Any],
    mode: str,
) -> None:
    repository = _repository(context)
    active_job = repository.get_active_job(telegram_user_id)
    if mode == "replace" and active_job is None:
        await _reply(update, "Nenhuma vaga ativa para substituir.")
        return

    try:
        stored = await save_telegram_file_reference(
            bot=context.bot,
            file_id=str(payload["file_id"]),
            original_filename=str(payload.get("file_name") or "arquivo"),
            size_bytes=int(payload.get("file_size") or 0),
            settings=_settings(context),
        )
        extracted_text = extract_text_from_file(stored.stored_path)
    except FileExtractionError as exc:
        job_id = active_job.id if active_job else None
        stored_path = str(payload.get("file_name") or "arquivo")
        repository.create_file_record(
            telegram_user_id=telegram_user_id,
            job_id=job_id,
            candidate_id=None,
            original_filename=str(payload.get("file_name") or "arquivo"),
            stored_path=stored_path,
            extension="",
            size_bytes=int(payload.get("file_size") or 0),
            extraction_status="falha_extracao",
            extracted_text="",
        )
        await _reply(update, f"❌ Falha ao extrair arquivo de vaga: {exc}")
        return

    if mode == "replace" and active_job is not None:
        result = _job_service(context).replace_job_text(
            telegram_user_id,
            active_job.id,
            extracted_text,
        )
        job = result.job
        repository.create_file_record(
            telegram_user_id=telegram_user_id,
            job_id=job.id,
            candidate_id=None,
            original_filename=stored.original_filename,
            stored_path=str(stored.stored_path),
            extension=stored.extension,
            size_bytes=stored.size_bytes,
            extraction_status="ok",
            extracted_text=extracted_text,
        )
        await _reply(update, format_job_updated(job, result.warnings))
        return

    result = _job_service(context).create_job_from_text(telegram_user_id, extracted_text)
    repository.create_file_record(
        telegram_user_id=telegram_user_id,
        job_id=result.job.id,
        candidate_id=None,
        original_filename=stored.original_filename,
        stored_path=str(stored.stored_path),
        extension=stored.extension,
        size_bytes=stored.size_bytes,
        extraction_status="ok",
        extracted_text=extracted_text,
    )
    await _reply(update, format_job_created(result.job, result.warnings))


async def _process_candidate_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_user_id: int,
    payload: dict[str, Any],
) -> None:
    repository = _repository(context)
    active_job = repository.get_active_job(telegram_user_id)
    if active_job is None:
        await _reply(update, "Cadastre ou selecione uma vaga antes de adicionar candidatos.")
        return

    try:
        stored = await save_telegram_file_reference(
            bot=context.bot,
            file_id=str(payload["file_id"]),
            original_filename=str(payload.get("file_name") or "arquivo"),
            size_bytes=int(payload.get("file_size") or 0),
            settings=_settings(context),
        )
        extracted_text = extract_text_from_file(stored.stored_path)
        file_record = repository.create_file_record(
            telegram_user_id=telegram_user_id,
            job_id=active_job.id,
            candidate_id=None,
            original_filename=stored.original_filename,
            stored_path=str(stored.stored_path),
            extension=stored.extension,
            size_bytes=stored.size_bytes,
            extraction_status="ok",
            extracted_text=extracted_text,
        )
    except FileExtractionError as exc:
        file_record = repository.create_file_record(
            telegram_user_id=telegram_user_id,
            job_id=active_job.id,
            candidate_id=None,
            original_filename=str(payload.get("file_name") or "arquivo"),
            stored_path=str(payload.get("file_name") or "arquivo"),
            extension="",
            size_bytes=int(payload.get("file_size") or 0),
            extraction_status=STATUS_FILE_EXTRACTION_FAILED,
            extracted_text="",
        )
        candidate = _candidate_service(context).create_failed_file_candidate(
            telegram_user_id=telegram_user_id,
            file_id=file_record.id,
            original_filename=file_record.original_filename,
            error_message=str(exc),
        )
        await _reply(
            update,
            "❌ Falha ao extrair texto do arquivo. "
            "Se for PDF escaneado, envie DOCX, TXT ou PDF com texto selecionável.\n"
            f"Registro criado para reprocessamento: candidato ID {candidate.id}.",
        )
        return

    result = _candidate_service(context).add_single_candidate_from_text(
        telegram_user_id=telegram_user_id,
        raw_text=extracted_text,
        source_type=SOURCE_FILE,
        source_file_id=file_record.id,
    )
    await _send_candidate_results(update, context, telegram_user_id, [result])


async def _send_current_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_user_id = _user_id(update)
    repository = _repository(context)
    active_job = repository.get_active_job(telegram_user_id)
    candidates = []
    if active_job is not None:
        candidates = repository.list_candidates(telegram_user_id, active_job.id)
    await _reply(update, format_list(active_job, candidates))


async def _confirm_candidate_removal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    candidate_id: int,
) -> None:
    telegram_user_id = _user_id(update)
    repository = _repository(context)
    active_job = repository.get_active_job(telegram_user_id)
    if active_job is None:
        await _reply(update, "Nenhuma vaga ativa selecionada.")
        return
    removed = repository.mark_candidate_removed(telegram_user_id, candidate_id, active_job.id)
    message = (
        "✅ Candidato removido logicamente."
        if removed
        else "Candidato não encontrado na vaga ativa."
    )
    await _reply(update, message)


async def _confirm_job_removal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    job_id: int,
) -> None:
    removed = _repository(context).remove_job(_user_id(update), job_id)
    await _reply(update, "✅ Vaga removida logicamente." if removed else "Vaga não encontrada.")


async def _require_authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = _settings(context)
    telegram_user_id = update.effective_user.id if update.effective_user else None
    if is_authorized(telegram_user_id, settings):
        _repository(context).ensure_user(int(telegram_user_id))
        logger.info("Comando/interacao recebida user=%s", telegram_user_id)
        return True
    log_unauthorized(telegram_user_id)
    if update.callback_query:
        await update.callback_query.answer("Acesso não autorizado.", show_alert=True)
        if update.callback_query.message:
            await update.callback_query.message.reply_text("Acesso não autorizado.")
    elif update.effective_message:
        await update.effective_message.reply_text("Acesso não autorizado.")
    return False


async def _reply(update: Update, text: str, reply_markup: Any | None = None) -> None:
    chunks = _split_telegram_message(text)
    for index, chunk in enumerate(chunks):
        markup = reply_markup if index == len(chunks) - 1 else None
        if update.effective_message:
            await update.effective_message.reply_text(chunk, reply_markup=markup)


def _split_telegram_message(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def _command_remainder(update: Update) -> str:
    text = update.effective_message.text or ""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _command_remainder_after_first_arg(update: Update) -> str:
    text = _command_remainder(update)
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _first_int_arg(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    if not context.args:
        return None
    try:
        return int(context.args[0])
    except ValueError:
        return None


def _user_id(update: Update) -> int:
    if update.effective_user is None:
        raise RuntimeError("Update sem usuário efetivo.")
    return update.effective_user.id


def _settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.application.bot_data["settings"]


def _repository(context: ContextTypes.DEFAULT_TYPE) -> Repository:
    return context.application.bot_data["repository"]


def _job_service(context: ContextTypes.DEFAULT_TYPE) -> JobService:
    return context.application.bot_data["job_service"]


def _candidate_service(context: ContextTypes.DEFAULT_TYPE) -> CandidateService:
    return context.application.bot_data["candidate_service"]


def _analysis_service(context: ContextTypes.DEFAULT_TYPE) -> AnalysisService:
    return context.application.bot_data["analysis_service"]


def _history_service(context: ContextTypes.DEFAULT_TYPE) -> HistoryService:
    return context.application.bot_data["history_service"]
