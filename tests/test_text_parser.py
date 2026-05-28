from app.utils.text_parser import extract_name, split_candidates


def test_split_multiple_candidates_with_separator() -> None:
    raw_text = """
Nome: João Silva
Experiência em RH.

---

Nome: Maria Santos
Experiência em DP.
"""

    candidates = split_candidates(raw_text)

    assert len(candidates) == 2
    assert candidates[0].startswith("Nome: João Silva")
    assert candidates[1].startswith("Nome: Maria Santos")


def test_extract_name_prioritizes_nome_label() -> None:
    assert extract_name("Cargo atual: Analista\nNome: Ana Souza\nResumo...") == "Ana Souza"
