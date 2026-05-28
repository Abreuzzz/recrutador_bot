from __future__ import annotations

import json

PROMPT_VERSION = "2026-05-23-v1"


JOB_SCHEMA_KEYS = {
    "titulo": "string",
    "localizacao": "string",
    "senioridade": "string",
    "modelo_trabalho": "string",
    "segmento_mercado": "string",
    "principais_responsabilidades": ["string"],
    "requisitos_obrigatorios": ["string"],
    "requisitos_imprescindiveis_eliminatorios": ["string"],
    "requisitos_desejaveis": ["string"],
    "conhecimentos_tecnicos": ["string"],
    "certificacoes": ["string"],
    "idiomas": ["string"],
    "observacoes_relevantes": ["string"],
}

CANDIDATE_SCHEMA_KEYS = {
    "nome": "string",
    "localizacao": "string",
    "cargo_atual": "string",
    "senioridade_estimada": "string",
    "tempo_total_experiencia": "string",
    "principais_experiencias": ["string"],
    "segmento_mercado_atuacao": ["string"],
    "conhecimentos_tecnicos": ["string"],
    "certificacoes": ["string"],
    "idiomas": ["string"],
    "formacao_academica": ["string"],
    "observacoes_relevantes": ["string"],
}

ANALYSIS_SCHEMA_KEYS = {
    "nome": "string",
    "score": "integer 0-100",
    "classificacao": (
        "Alta aderência | Média aderência | Média aderência com restrição | Baixa aderência"
    ),
    "prioridade": "Alta | Média | Baixa",
    "parecer": "string com 2 a 4 linhas",
    "pontos_aderencia": ["string"],
    "pontos_atencao": ["string"],
    "pontos_validacao_manual": ["string"],
    "recomendacao": (
        "Priorizar abordagem | Avaliar com cautela | Baixa prioridade | Não priorizar neste momento"
    ),
    "evidencias_diretas": ["string"],
    "inferencias": ["string"],
    "nao_evidenciado": ["string"],
    "requisitos_imprescindiveis_nao_atendidos": ["string"],
    "requisitos_criticos_nao_evidenciados": ["string"],
}


def _json_schema_text(schema: dict[str, object]) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2)


def build_job_extraction_prompt(raw_job_text: str) -> str:
    return f"""
Versão do prompt: {PROMPT_VERSION}

Você é um analista sênior de Recrutamento e Seleção.
Extraia um resumo estruturado da vaga abaixo.

Regras obrigatórias:
- Responda somente com JSON válido.
- Não use markdown, comentários ou texto fora do JSON.
- Não invente informações.
- Quando algo não estiver claro ou ausente, use exatamente "Não informado".
- Aceite texto em português, inglês ou espanhol.
- Responda sempre em português do Brasil.
- Separe requisitos obrigatórios, imprescindíveis/eliminatórios e desejáveis.
- Requisitos eliminatórios devem aparecer em requisitos_imprescindiveis_eliminatorios.

JSON esperado:
{_json_schema_text(JOB_SCHEMA_KEYS)}

Texto da vaga:
\"\"\"{raw_job_text}\"\"\"
""".strip()


def build_candidate_extraction_prompt(raw_candidate_text: str) -> str:
    return f"""
Versão do prompt: {PROMPT_VERSION}

Você é um analista sênior de Recrutamento e Seleção.
Extraia um resumo estruturado do candidato abaixo.

Regras obrigatórias:
- Responda somente com JSON válido.
- Não use markdown, comentários ou texto fora do JSON.
- Não invente informações.
- Quando algo não estiver claro ou ausente, use exatamente "Não informado".
- Aceite texto em português, inglês ou espanhol.
- Responda sempre em português do Brasil.
- Diferencie experiência direta de inferência apenas nos campos de observação quando for relevante.

JSON esperado:
{_json_schema_text(CANDIDATE_SCHEMA_KEYS)}

Texto do candidato:
\"\"\"{raw_candidate_text}\"\"\"
""".strip()


def build_candidate_analysis_prompt(
    job_raw_text: str,
    job_summary_json: str,
    candidate_raw_text: str,
    candidate_summary_json: str,
) -> str:
    return f"""
Versão do prompt: {PROMPT_VERSION}

Você é um especialista de triagem de Recrutamento e Seleção.
Compare o candidato com a vaga usando obrigatoriamente:
1. texto bruto da vaga;
2. resumo estruturado da vaga;
3. texto bruto do candidato;
4. resumo estruturado do candidato.

Regras de avaliação:
- Responda somente com JSON válido.
- Não use markdown, comentários ou texto fora do JSON.
- Não invente informações e não presuma atendimento sem evidência.
- A resposta final deve estar em português do Brasil.
- Avalie localização, experiência na função, tempo de experiência, conhecimentos técnicos,
  certificações, senioridade, idiomas e segmento/mercado.
- Não use pesos fixos rígidos: inferir pesos conforme relevância da vaga.
- Requisitos desejáveis contam como bônus, não como bloqueio.
- Requisito imprescindível não atendido impede "Alta aderência".
- Requisito imprescindível claramente eliminatório não evidenciado limita a classificação máxima
  a "Média aderência com restrição" e deve aparecer em pontos_validacao_manual.
- Se a ausência parecer apenas falta de informação, sinalize como "não evidenciado" e recomende
  validação manual.
- Se houver contradição clara, considere não atendimento.
- Use score inteiro de 0 a 100.
- Classificação esperada por faixa: 80-100 Alta aderência; 60-79 Média aderência;
  0-59 Baixa aderência.
- Use "Média aderência com restrição" quando houver score bom, mas gap crítico ou requisito
  imprescindível limitante.
- A prioridade é separada da classificação e deve considerar risco de falso positivo.
- Parecer: 2 a 4 linhas, profissional, objetivo e útil para decisão humana.
- Inclua evidencias_diretas, inferencias e nao_evidenciado apenas para pontos críticos,
  restrições, gaps relevantes ou requisito obrigatório não comprovado.

JSON esperado:
{_json_schema_text(ANALYSIS_SCHEMA_KEYS)}

Texto bruto da vaga:
\"\"\"{job_raw_text}\"\"\"

Resumo estruturado da vaga:
{job_summary_json}

Texto bruto do candidato:
\"\"\"{candidate_raw_text}\"\"\"

Resumo estruturado do candidato:
{candidate_summary_json}
""".strip()


def build_json_retry_prompt(
    original_prompt: str,
    invalid_response: str,
    validation_error: str,
    schema_description: str,
) -> str:
    return f"""
Sua resposta anterior não pôde ser validada pelo sistema.

Erro de validação:
{validation_error}

Resposta anterior:
\"\"\"{invalid_response}\"\"\"

Corrija a resposta seguindo exatamente este schema:
{schema_description}

Regras:
- Responda somente com JSON válido.
- Não use markdown.
- Não inclua comentários.
- Não inclua texto antes ou depois do JSON.
- Preserve as conclusões defensáveis a partir do prompt original.
- Não invente informações.

Prompt original:
{original_prompt}
""".strip()
