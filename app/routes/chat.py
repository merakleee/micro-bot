from __future__ import annotations

import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends

from app.auth import get_access_level
from app.ingestion.runtime import get_embedder, get_vector_store
from app.language import detect_language
from app.llm.client import create_chat_completion
from app.prompting import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    build_grounded_prompt,
    finalize_answer,
)
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

    language = detect_language(req.message)

    retrieval = retrieve(
        req.message,
        access,
        5,
        embedder=get_embedder(),
        store=get_vector_store(),
    )

    prompt = build_grounded_prompt(
        retrieval.results,
        req.message,
        language,
    )

    completion = create_chat_completion(
        prompt.messages,
        temperature=DEFAULT_TEMPERATURE,
        max_tokens=DEFAULT_MAX_TOKENS,
    )

    answer, grounded = finalize_answer(
        completion.content,
        language,
    )

    sources = [
        Source(
            doc_id=result.doc_id,
            title=result.title,
            snippet=result.text,
        )
        for result in prompt.included_results
    ]

    return ChatResponse(
        answer=answer,
        conversation_id=conversation_id,
        grounded=grounded,
        sources=sources,
        usage=Usage(
            llm_calls=completion.llm_calls,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
        ),
        latency_ms=int((time.perf_counter() - start) * 1000),
    )
