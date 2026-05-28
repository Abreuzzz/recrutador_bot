import pytest
from pydantic import ValidationError

from app.llm.schemas import CandidateAnalysisResult, classification_from_score


def test_score_classification_ranges() -> None:
    assert classification_from_score(100) == "Alta aderência"
    assert classification_from_score(80) == "Alta aderência"
    assert classification_from_score(79) == "Média aderência"
    assert classification_from_score(60) == "Média aderência"
    assert classification_from_score(59) == "Baixa aderência"
    assert classification_from_score(0) == "Baixa aderência"


def test_score_must_be_between_zero_and_one_hundred() -> None:
    with pytest.raises(ValidationError):
        CandidateAnalysisResult(
            nome="João",
            score=101,
            classificacao="Alta aderência",
            prioridade="Alta",
            parecer="Parecer.",
            pontos_aderencia=["Experiência aderente."],
            recomendacao="Priorizar abordagem",
        )


def test_critical_requirement_blocks_high_classification() -> None:
    result = CandidateAnalysisResult(
        nome="João",
        score=88,
        classificacao="Alta aderência",
        prioridade="Média",
        parecer="Boa aderência, mas há requisito crítico não evidenciado.",
        pontos_aderencia=["Experiência na função."],
        pontos_atencao=["Espanhol não evidenciado."],
        pontos_validacao_manual=["Confirmar espanhol fluente."],
        recomendacao="Avaliar com cautela",
        requisitos_criticos_nao_evidenciados=["Espanhol fluente"],
    )

    assert result.classificacao == "Média aderência com restrição"
