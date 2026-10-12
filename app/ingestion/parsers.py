from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    text: str


def parse_md(path: Path) -> ParsedDocument:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Unable to read Markdown file: {path}") from exc

    text = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError(f"Markdown file is empty: {path}")

    return ParsedDocument(title=path.stem, text=text)


def _extract_pdf_pages(path: Path) -> list[str]:
    try:
        reader = PdfReader(path)
        return [(page.extract_text() or "").strip() for page in reader.pages]
    except (OSError, PdfReadError) as exc:
        raise ValueError(f"Unable to read PDF file: {path}") from exc


def parse_pdf(path: Path) -> ParsedDocument:
    try:
        import ocrmypdf
    except ImportError as exc:
        raise ValueError(
            "OCR is required for PDF ingestion. Install OCRmyPDF and Tesseract "
            "with the eng, fra, and ara language data."
        ) from exc

    try:
        with TemporaryDirectory() as temporary_directory:
            ocr_path = Path(temporary_directory) / "ocr.pdf"
            ocrmypdf.ocr(
                str(path),
                str(ocr_path),
                language="eng+fra+ara",
                redo_ocr=True,
                output_type="pdf",
                jobs=1,
                progress_bar=False,
            )
            pages = _extract_pdf_pages(ocr_path)
    except Exception as exc:
        raise ValueError(f"Unable to OCR PDF file: {path}") from exc

    text = "\n\n".join(page for page in pages if page)
    if not text:
        raise ValueError(f"PDF file has no readable text: {path}")

    return ParsedDocument(title=path.stem, text=text)


def parse_docx(path: Path) -> ParsedDocument:
    try:
        document = Document(path)
    except (OSError, BadZipFile, PackageNotFoundError) as exc:
        raise ValueError(f"Unable to read DOCX file: {path}") from exc

    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
    text = "\n".join(paragraph for paragraph in paragraphs if paragraph)
    if not text:
        raise ValueError(f"DOCX file has no readable text: {path}")

    return ParsedDocument(title=path.stem, text=text)


def parse_document(path: Path) -> ParsedDocument:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return parse_md(path)
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix == ".docx":
        return parse_docx(path)
    raise ValueError(f"Unsupported document format: {suffix or '<none>'}")
