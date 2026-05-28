from __future__ import annotations

import json

from app.database.models import STATUS_PENDING_NAME, Candidate, Job

START_TEXT = (
    "Olá. Sou seu bot local de apoio à triagem de candidatos.\n\n"
    "Use os botões abaixo ou envie /help para ver os comandos."
)

HELP_TEXT = """
Comandos disponíveis:

/vaga [texto] — cadastrar uma nova vaga
/candidato [texto] — cadastrar candidato(s) na vaga ativa
/listar — ver vaga ativa e candidatos
/analisar — analisar aderência dos candidatos
/limpar — limpar seleção ativa e pendências
/historico — ver últimas 5 análises
/resultado ID — recuperar análise antiga
/vagas — listar vagas
/selecionar ID — selecionar vaga ativa
/remover_candidato ID — remover candidato logicamente
/editar_candidato ID [texto] — substituir texto do candidato
/remover_vaga ID — remover vaga logicamente
/reprocessar_candidato ID — tentar reprocessar um candidato
/reprocessar_falhas — reprocessar candidatos com falha da vaga ativa

Arquivos aceitos como documento: PDF, DOCX e TXT.
""".strip()

OLLAMA_ERROR_TEXT = (
    "❌ Não consegui conectar ao Ollama ou ao modelo configurado.\n"
    "Verifique se o Ollama está rodando e se o modelo qwen2.5:7b foi baixado.\n"
    "Você pode tentar novamente depois com /analisar."
)


def format_list(active_job: Job | None, candidates: list[Candidate]) -> str:
    if active_job is None:
        return "Nenhuma vaga ativa. Cadastre uma vaga com /vaga."

    summary = _short_job_summary(active_job)
    lines = [
        f"Vaga ativa: {active_job.title} — ID {active_job.id}",
        "",
        f"Resumo: {summary}",
        "",
        f"Candidatos cadastrados: {len(candidates)}",
    ]

    if not candidates:
        lines.append("\nNenhum candidato cadastrado para esta vaga.")
        return "\n".join(lines)

    lines.append("\nCandidatos:")
    for candidate in candidates:
        status = candidate.status
        if candidate.status == STATUS_PENDING_NAME:
            status = "pendente de identificação do nome"
        lines.append(f"- ID {candidate.id} — {candidate.name} — Status: {status}")
    return "\n".join(lines)


def format_jobs(jobs: list[Job], active_job_id: int | None) -> str:
    if not jobs:
        return "Nenhuma vaga cadastrada."
    lines = ["Vagas cadastradas:"]
    for job in jobs:
        marker = "ativa" if job.id == active_job_id else "inativa"
        lines.append(f"- ID {job.id} — {job.title} — {marker}")
    return "\n".join(lines)


def format_candidate_created(candidate: Candidate, warnings: list[str] | None = None) -> str:
    lines = [f"✅ Candidato cadastrado: {candidate.name} — ID {candidate.id}"]
    if candidate.status == STATUS_PENDING_NAME:
        lines.append(
            "\nNão consegui identificar o nome do candidato. "
            f"Ele ficou pendente e pode ser corrigido com /editar_candidato {candidate.id}."
        )
    if warnings:
        lines.extend(["", *warnings])
    return "\n".join(lines)


def format_job_created(job: Job, warnings: list[str] | None = None) -> str:
    lines = [f"✅ Vaga cadastrada e selecionada como ativa: {job.title} — ID {job.id}"]
    if warnings:
        lines.extend(["", *warnings])
    return "\n".join(lines)


def format_job_updated(job: Job, warnings: list[str] | None = None) -> str:
    lines = [f"✅ Vaga ativa atualizada: {job.title} — ID {job.id}"]
    if warnings:
        lines.extend(["", *warnings])
    return "\n".join(lines)


def format_analysis_candidates(candidates: list[Candidate]) -> str:
    lines = ["Candidatos selecionados para análise:"]
    for candidate in candidates:
        lines.append(f"- ID {candidate.id} — {candidate.name}")
    return "\n".join(lines)


def _short_job_summary(job: Job) -> str:
    try:
        payload = json.loads(job.structured_summary_json)
    except json.JSONDecodeError:
        return _truncate(job.raw_text, 180)
    bits = [
        payload.get("senioridade"),
        payload.get("modelo_trabalho"),
        payload.get("localizacao"),
    ]
    clean_bits = [str(bit) for bit in bits if bit and bit != "Não informado"]
    if clean_bits:
        return " | ".join(clean_bits)
    return _truncate(job.raw_text, 180)


def _truncate(value: str, limit: int) -> str:
    clean = " ".join((value or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."
