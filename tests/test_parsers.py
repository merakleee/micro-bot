from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from app.ingestion import parsers
from app.ingestion.parsers import ParsedDocument


def test_parse_md_returns_title_and_normalized_text(tmp_path: Path):
    path = tmp_path / "membership.md"
    path.write_text("  # Adhésion\r\n\r\nMicroClub  ", encoding="utf-8")

    assert parsers.parse_md(path) == ParsedDocument(
        title="membership",
        text="# Adhésion\n\nMicroClub",
    )


def test_parse_md_rejects_empty_file(tmp_path: Path):
    path = tmp_path / "empty.md"
    path.write_text(" \n\t", encoding="utf-8")

    with pytest.raises(ValueError, match="Markdown file is empty"):
        parsers.parse_md(path)


def test_parse_md_rejects_invalid_utf8(tmp_path: Path):
    path = tmp_path / "invalid.md"
    path.write_bytes(b"\xff\xfe")

    with pytest.raises(ValueError, match="Unable to read Markdown"):
        parsers.parse_md(path)


def test_parse_pdf_returns_text_from_pages(tmp_path: Path, monkeypatch):
    path = tmp_path / "events.pdf"
    monkeypatch.setattr(
        parsers,
        "PdfReader",
        lambda _: SimpleNamespace(
            pages=[
                SimpleNamespace(extract_text=lambda: " First page "),
                SimpleNamespace(extract_text=lambda: "Second page"),
            ]
        ),
    )

    assert parsers.parse_pdf(path) == ParsedDocument(
        title="events",
        text="First page\n\nSecond page",
    )


def test_parse_pdf_rejects_document_without_text(tmp_path: Path, monkeypatch):
    path = tmp_path / "scanned.pdf"
    monkeypatch.setattr(
        parsers,
        "PdfReader",
        lambda _: SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: None)]),
    )

    with pytest.raises(ValueError, match="PDF file has no readable text"):
        parsers.parse_pdf(path)


def test_parse_docx_returns_non_empty_paragraphs(tmp_path: Path):
    path = tmp_path / "membership.docx"
    document = Document()
    document.add_paragraph("Membership")
    document.add_paragraph("L'adhésion est ouverte aux étudiants.")
    document.save(path)

    assert parsers.parse_docx(path) == ParsedDocument(
        title="membership",
        text="Membership\nL'adhésion est ouverte aux étudiants.",
    )


def test_parse_docx_rejects_empty_document(tmp_path: Path):
    path = tmp_path / "empty.docx"
    Document().save(path)

    with pytest.raises(ValueError, match="DOCX file has no readable text"):
        parsers.parse_docx(path)


@pytest.mark.parametrize(
    ("filename", "parser_name"),
    [
        ("document.md", "parse_md"),
        ("document.markdown", "parse_md"),
        ("document.pdf", "parse_pdf"),
        ("document.docx", "parse_docx"),
    ],
)
def test_parse_document_selects_parser(
    tmp_path: Path, monkeypatch, filename: str, parser_name: str
):
    expected = ParsedDocument(title="document", text="content")
    monkeypatch.setattr(parsers, parser_name, lambda _: expected)

    assert parsers.parse_document(tmp_path / filename) == expected


def test_parse_document_rejects_unsupported_format(tmp_path: Path):
    with pytest.raises(ValueError, match="Unsupported document format"):
        parsers.parse_document(tmp_path / "document.txt")
