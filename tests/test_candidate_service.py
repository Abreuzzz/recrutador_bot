import json
from pathlib import Path

from app.database.repository import Repository
from app.llm.schemas import StructuredCandidateSummary, StructuredJobSummary
from app.services.candidate_service import CandidateService


class FakeCandidateLlm:
    def __init__(self, name: str = "Nome do LLM") -> None:
        self.name = name

    def generate_validated_json(self, **_kwargs: object) -> StructuredCandidateSummary:
        return StructuredCandidateSummary(nome=self.name)


def _repo_with_job(tmp_path: Path) -> Repository:
    repo = Repository(tmp_path / "test.db")
    summary = StructuredJobSummary(titulo="Analista de RH")
    repo.create_job(
        telegram_user_id=1,
        title="Analista de RH",
        raw_text="Título: Analista de RH",
        structured_summary_json=json.dumps(summary.model_dump(mode="json"), ensure_ascii=False),
    )
    return repo


def test_candidate_without_name_gets_pending_status(tmp_path: Path) -> None:
    service = CandidateService(_repo_with_job(tmp_path), llm_client=None)

    result = service.add_single_candidate_from_text(1, "Experiência em recrutamento.")

    assert result.candidate is not None
    assert result.candidate.status == "pendente_nome"
    assert result.candidate.name == "Nome pendente"


def test_nome_label_has_priority_over_llm_name(tmp_path: Path) -> None:
    service = CandidateService(_repo_with_job(tmp_path), llm_client=FakeCandidateLlm("Outro Nome"))

    result = service.add_single_candidate_from_text(1, "Nome: Carla Dias\nExperiência em R&S.")

    assert result.candidate is not None
    assert result.candidate.name == "Carla Dias"


def test_duplicate_detection_inside_same_job(tmp_path: Path) -> None:
    service = CandidateService(_repo_with_job(tmp_path), llm_client=FakeCandidateLlm("João Silva"))

    first = service.add_single_candidate_from_text(1, "Nome: João Silva\nE-mail: joao@test.com")
    second = service.add_single_candidate_from_text(1, "Nome: João Silva\nE-mail: joao@test.com")

    assert first.candidate is not None
    assert second.candidate is None
    assert second.duplicate is not None
    assert second.duplicate.candidate_id == first.candidate.id
