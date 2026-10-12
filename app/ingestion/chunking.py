import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    doc_id: str
    title: str
    visibility: str
    chunk_index: int


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sections(text: str) -> list[str]:
    sections = re.split(r"(?m)(?=^#{1,6}\s+)", text)
    paragraphs: list[str] = []

    for section in sections:
        parts = re.split(r"\n\s*\n", section)
        paragraphs.extend(
            part.strip()
            for part in parts
            if part.strip()
        )

    return paragraphs


def split_large_text(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    step = chunk_size - overlap
    chunks: list[str] = []

    for start in range(0, len(text), step):
        chunk = text[start:start + chunk_size].strip()

        if chunk:
            chunks.append(chunk)

    return chunks


def chunk_text(
    text: str,
    *,
    doc_id: str,
    title: str,
    visibility: str,
    chunk_size: int,
    overlap: int,
) -> list[DocumentChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be between 0 and chunk_size"
        )

    normalized = normalize_text(text)

    if not normalized:
        return []

    sections = split_sections(normalized)
    raw_chunks: list[str] = []
    current = ""

    for section in sections:
        candidate = (
            f"{current}\n\n{section}".strip()
            if current
            else section
        )

        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            raw_chunks.extend(
                split_large_text(
                    current,
                    chunk_size,
                    overlap,
                )
            )

        raw_chunks.extend(
            split_large_text(
                section,
                chunk_size,
                overlap,
            )
        )

        current = ""

    if current:
        raw_chunks.extend(
            split_large_text(
                current,
                chunk_size,
                overlap,
            )
        )

    return [
        DocumentChunk(
            text=chunk,
            doc_id=doc_id,
            title=title,
            visibility=visibility,
            chunk_index=index,
        )
        for index, chunk in enumerate(raw_chunks)
        if chunk.strip()
    ]
