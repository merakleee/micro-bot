from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app import registry
from app.auth import require_admin
from app.config import get_settings
from app.errors import AppError
from app.ingestion import pipeline
from app.ingestion.runtime import get_embedder, get_vector_store
from app.schemas import (
    DocumentDeleteResponse,
    DocumentResponse,
    DocumentUploadResponse,
)

router = APIRouter()
_SUPPORTED_SUFFIXES = {".md", ".markdown", ".pdf", ".docx"}
_READ_BLOCK_BYTES = 64 * 1024


def _save_upload(file: UploadFile, destination: Path, max_bytes: int) -> None:
    size = 0
    with destination.open("wb") as output:
        while block := file.file.read(_READ_BLOCK_BYTES):
            size += len(block)
            if size > max_bytes:
                raise AppError(
                    413,
                    "file_too_large",
                    f"File exceeds the maximum size of {max_bytes} bytes.",
                )
            output.write(block)


def _to_response(document: registry.DocumentRecord) -> DocumentResponse:
    return DocumentResponse(
        doc_id=document["doc_id"],
        title=document["title"],
        visibility=document["visibility"],
        status=document["status"],
        error=document["error"],
        created_at=document["created_at"],
    )


@router.post(
    "/documents",
    response_model=DocumentUploadResponse,
    dependencies=[Depends(require_admin)],
)
def upload_document(
    file: Annotated[UploadFile, File()],
    visibility: Annotated[str, Form()],
) -> DocumentUploadResponse | JSONResponse:
    if visibility not in {"public", "members"}:
        raise AppError(
            422,
            "validation_error",
            "visibility must be public or members.",
        )

    filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    suffix = Path(filename).suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        raise AppError(
            415,
            "unsupported_file_type",
            "Supported file types are Markdown (.md, .markdown), PDF (.pdf), "
            "and Word (.docx).",
        )

    title = Path(filename).stem.strip()
    if not title:
        raise AppError(422, "validation_error", "The uploaded file needs a filename.")

    settings = get_settings()
    try:
        with TemporaryDirectory(prefix="micro-bot-upload-") as directory:
            path = Path(directory) / f"document{suffix}"
            _save_upload(file, path, settings.max_upload_bytes)
            try:
                doc_id, skipped = pipeline.ingest_file(
                    path,
                    title=title,
                    visibility=visibility,
                    embedder=get_embedder(),
                    store=get_vector_store(),
                )
            except ValueError as exc:
                if "different visibility" in str(exc):
                    raise AppError(
                        409,
                        "document_conflict",
                        "This file already exists with a different visibility.",
                    ) from exc
                raise AppError(422, "invalid_document", str(exc)) from exc
            except Exception as exc:
                raise AppError(
                    503,
                    "ingestion_unavailable",
                    "The document could not be processed right now.",
                ) from exc

            document = registry.get_document(doc_id)
            if document is None:
                raise AppError(500, "internal_error", "The uploaded document was not recorded.")
            response = DocumentUploadResponse(
                doc_id=doc_id,
                status=document["status"],
                skipped=skipped,
            )
            return JSONResponse(
                status_code=200 if skipped else 201,
                content=response.model_dump(),
            )
    finally:
        file.file.close()


@router.get(
    "/documents",
    response_model=list[DocumentResponse],
    dependencies=[Depends(require_admin)],
)
def list_documents() -> list[DocumentResponse]:
    return [_to_response(document) for document in registry.list_documents()]


@router.delete(
    "/documents/{doc_id}",
    response_model=DocumentDeleteResponse,
    dependencies=[Depends(require_admin)],
)
def remove_document(doc_id: str) -> DocumentDeleteResponse:
    deleted = pipeline.delete_document(doc_id, store=get_vector_store())
    if not deleted:
        raise AppError(404, "not_found", "Document not found.")
    return DocumentDeleteResponse(doc_id=doc_id, deleted=True)
