from pathlib import Path

import pytest
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.files.extractors import FileExtractionError, extract_text_from_file, validate_file_size


def test_extract_txt_utf8(tmp_path: Path) -> None:
    path = tmp_path / "candidato.txt"
    path.write_text("Nome: TXT Teste", encoding="utf-8")

    assert extract_text_from_file(path) == "Nome: TXT Teste"


def test_extract_docx(tmp_path: Path) -> None:
    path = tmp_path / "candidato.docx"
    document = Document()
    document.add_paragraph("Nome: DOCX Teste")
    document.save(path)

    assert "Nome: DOCX Teste" in extract_text_from_file(path)


def test_extract_pdf_with_selectable_text(tmp_path: Path) -> None:
    path = tmp_path / "candidato.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    resources = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    page[NameObject("/Resources")] = resources
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 24 Tf 100 700 Td (Nome: PDF Teste) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as file:
        writer.write(file)

    assert "Nome: PDF Teste" in extract_text_from_file(path)


def test_reject_file_above_limit() -> None:
    with pytest.raises(FileExtractionError):
        validate_file_size(21 * 1024 * 1024, max_file_size_mb=20)


def test_pdf_without_text_is_controlled_error(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as file:
        writer.write(file)

    with pytest.raises(FileExtractionError, match="escaneado|sem texto"):
        extract_text_from_file(path)
