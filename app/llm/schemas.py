from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

NAO_INFORMADO = "Não informado"

Classification = Literal[
    "Alta aderência",
    "Média aderência",
    "Média aderência com restrição",
    "Baixa aderência",
]
Priority = Literal["Alta", "Média", "Baixa"]


def _missing_as_default(data: object, defaults: dict[str, object]) -> object:
    if not isinstance(data, dict):
        return data
    normalized = dict(data)
    for key, value in defaults.items():
        if key not in normalized or normalized[key] in (None, "", []):
            normalized[key] = value
    return normalized


def _coerce_text(value: object) -> str:
    if value in (None, "", []):
        return NAO_INFORMADO
    if isinstance(value, list):
        return "; ".join(str(item).strip() for item in value if str(item).strip()) or NAO_INFORMADO
    return str(value).strip() or NAO_INFORMADO


def _coerce_list(value: object) -> list[str]:
    if value in (None, "", []):
        return [NAO_INFORMADO]
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else [NAO_INFORMADO]
    if isinstance(value, list):
        cleaned_items = [str(item).strip() for item in value if str(item).strip()]
        return cleaned_items or [NAO_INFORMADO]
    return [str(value).strip() or NAO_INFORMADO]


class StructuredJobSummary(BaseModel):
    titulo: str = NAO_INFORMADO
    localizacao: str = NAO_INFORMADO
    senioridade: str = NAO_INFORMADO
    modelo_trabalho: str = NAO_INFORMADO
    segmento_mercado: str = NAO_INFORMADO
    principais_responsabilidades: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])
    requisitos_obrigatorios: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])
    requisitos_imprescindiveis_eliminatorios: list[str] = Field(
        default_factory=lambda: [NAO_INFORMADO]
    )
    requisitos_desejaveis: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])
    conhecimentos_tecnicos: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])
    certificacoes: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])
    idiomas: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])
    observacoes_relevantes: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])

    @model_validator(mode="before")
    @classmethod
    def fill_missing(cls, data: object) -> object:
        return _missing_as_default(
            data,
            {
                "titulo": NAO_INFORMADO,
                "localizacao": NAO_INFORMADO,
                "senioridade": NAO_INFORMADO,
                "modelo_trabalho": NAO_INFORMADO,
                "segmento_mercado": NAO_INFORMADO,
                "principais_responsabilidades": [NAO_INFORMADO],
                "requisitos_obrigatorios": [NAO_INFORMADO],
                "requisitos_imprescindiveis_eliminatorios": [NAO_INFORMADO],
                "requisitos_desejaveis": [NAO_INFORMADO],
                "conhecimentos_tecnicos": [NAO_INFORMADO],
                "certificacoes": [NAO_INFORMADO],
                "idiomas": [NAO_INFORMADO],
                "observacoes_relevantes": [NAO_INFORMADO],
            },
        )

    @field_validator(
        "titulo",
        "localizacao",
        "senioridade",
        "modelo_trabalho",
        "segmento_mercado",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value: object) -> str:
        return _coerce_text(value)

    @field_validator(
        "principais_responsabilidades",
        "requisitos_obrigatorios",
        "requisitos_imprescindiveis_eliminatorios",
        "requisitos_desejaveis",
        "conhecimentos_tecnicos",
        "certificacoes",
        "idiomas",
        "observacoes_relevantes",
        mode="before",
    )
    @classmethod
    def normalize_list_fields(cls, value: object) -> list[str]:
        return _coerce_list(value)


class StructuredCandidateSummary(BaseModel):
    nome: str = NAO_INFORMADO
    localizacao: str = NAO_INFORMADO
    cargo_atual: str = NAO_INFORMADO
    senioridade_estimada: str = NAO_INFORMADO
    tempo_total_experiencia: str = NAO_INFORMADO
    principais_experiencias: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])
    segmento_mercado_atuacao: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])
    conhecimentos_tecnicos: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])
    certificacoes: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])
    idiomas: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])
    formacao_academica: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])
    observacoes_relevantes: list[str] = Field(default_factory=lambda: [NAO_INFORMADO])

    @model_validator(mode="before")
    @classmethod
    def fill_missing(cls, data: object) -> object:
        return _missing_as_default(
            data,
            {
                "nome": NAO_INFORMADO,
                "localizacao": NAO_INFORMADO,
                "cargo_atual": NAO_INFORMADO,
                "senioridade_estimada": NAO_INFORMADO,
                "tempo_total_experiencia": NAO_INFORMADO,
                "principais_experiencias": [NAO_INFORMADO],
                "segmento_mercado_atuacao": [NAO_INFORMADO],
                "conhecimentos_tecnicos": [NAO_INFORMADO],
                "certificacoes": [NAO_INFORMADO],
                "idiomas": [NAO_INFORMADO],
                "formacao_academica": [NAO_INFORMADO],
                "observacoes_relevantes": [NAO_INFORMADO],
            },
        )

    @field_validator(
        "nome",
        "localizacao",
        "cargo_atual",
        "senioridade_estimada",
        "tempo_total_experiencia",
        mode="before",
    )
    @classmethod
    def normalize_text_fields(cls, value: object) -> str:
        return _coerce_text(value)

    @field_validator(
        "principais_experiencias",
        "segmento_mercado_atuacao",
        "conhecimentos_tecnicos",
        "certificacoes",
        "idiomas",
        "formacao_academica",
        "observacoes_relevantes",
        mode="before",
    )
    @classmethod
    def normalize_list_fields(cls, value: object) -> list[str]:
        return _coerce_list(value)


def classification_from_score(score: int, has_critical_gap: bool = False) -> str:
    if has_critical_gap and score >= 60:
        return "Média aderência com restrição"
    if score >= 80:
        return "Alta aderência"
    if score >= 60:
        return "Média aderência"
    return "Baixa aderência"


class CandidateAnalysisResult(BaseModel):
    nome: str
    score: int = Field(ge=0, le=100)
    classificacao: Classification
    prioridade: Priority
    parecer: str
    pontos_aderencia: list[str]
    pontos_atencao: list[str] = Field(default_factory=list)
    pontos_validacao_manual: list[str] = Field(default_factory=list)
    recomendacao: str
    evidencias_diretas: list[str] = Field(default_factory=list)
    inferencias: list[str] = Field(default_factory=list)
    nao_evidenciado: list[str] = Field(default_factory=list)
    requisitos_imprescindiveis_nao_atendidos: list[str] = Field(default_factory=list)
    requisitos_criticos_nao_evidenciados: list[str] = Field(default_factory=list)

    @field_validator(
        "pontos_aderencia",
        "pontos_atencao",
        "pontos_validacao_manual",
        "evidencias_diretas",
        "inferencias",
        "nao_evidenciado",
        "requisitos_imprescindiveis_nao_atendidos",
        "requisitos_criticos_nao_evidenciados",
        mode="before",
    )
    @classmethod
    def normalize_list_fields(cls, value: object) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    @model_validator(mode="after")
    def enforce_classification_ceiling(self) -> CandidateAnalysisResult:
        has_critical_gap = bool(
            self.requisitos_imprescindiveis_nao_atendidos
            or self.requisitos_criticos_nao_evidenciados
        )
        expected = classification_from_score(self.score, has_critical_gap=has_critical_gap)
        if self.classificacao == "Alta aderência" and expected != "Alta aderência":
            self.classificacao = expected  # type: ignore[misc]
        return self


class ConsolidatedAnalysisResult(BaseModel):
    vaga: str
    candidatos_analisados: int = Field(ge=0)
    melhor_score: int = Field(ge=0, le=100)
    ranking: list[CandidateAnalysisResult]

    @model_validator(mode="after")
    def sort_ranking(self) -> ConsolidatedAnalysisResult:
        self.ranking.sort(key=lambda item: item.score, reverse=True)
        return self
