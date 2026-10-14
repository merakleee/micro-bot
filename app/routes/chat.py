from __future__ import annotations

import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends

from app.auth import get_access_level
from app.ingestion.runtime import get_embedder, get_vector_store
from app.retrieval import retrieve
from app.schemas import ChatRequest, ChatResponse, Source, Usage

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    access: Literal["public", "members"] = Depends(get_access_level),
) -> ChatResponse:
    start = time.perf_counter()
    conversation_id = req.conversation_id or f"c_{uuid.uuid4().hex[:8]}"

    retrieval = retrieve(
        req.message,
        access,
        5,
        embedder=get_embedder(),
        store=get_vector_store(),
    )

    sources = [
        Source(
            doc_id=result.doc_id,
            title=result.title,
            snippet=result.text,
        )
        for result in retrieval.results
    ]

    return ChatResponse(
        answer="Relevant context retrieved.",
        conversation_id=conversation_id,
        grounded=True,
        sources=sources,
        usage=Usage(
            llm_calls=0,
            prompt_tokens=0,
            completion_tokens=0,
        ),
        latency_ms=int((time.perf_counter() - start) * 1000),
    )
