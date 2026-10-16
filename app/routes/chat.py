from __future__ import annotations

import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request

from app.auth import get_access_level
from app.errors import AppError
from app.ingestion.runtime import get_embedder, get_vector_store
from app.language import detect_language
from app.llm.client import create_chat_completion
from app.prompting import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    build_grounded_prompt,
    finalize_answer,
    refusal_message,
)
from app.retrieval import retrieve
from app.schemas import ChatRequest, ChatResponse, Source, Usage
from app.conversation_memory import conversation_memory

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    request: Request,
    access: Literal["public", "members"] = Depends(get_access_level),
) -> ChatResponse:
    request.state.access_level = access
    start = time.perf_counter()
    conversation_id = req.conversation_id or f"c_{uuid.uuid4().hex[:8]}"
    language = detect_language(req.message)

    retrieval_query = conversation_memory.build_retrieval_query(
        conversation_id,
        req.message,
        access,
    )

    try:
        retrieval = retrieve(
            retrieval_query,
            access,
            5,
            embedder=get_embedder(),
            store=get_vector_store(),
        )
    except AppError as exc:
        if exc.code != "no_relevant_context":
            raise

        request.state.grounded = False
        conversation_memory.record_turn(
            conversation_id,
            req.message,
            access,
        )

        return ChatResponse(
            answer=refusal_message(language),
            conversation_id=conversation_id,
            grounded=False,
            sources=[],
            usage=Usage(
                llm_calls=0,
                prompt_tokens=0,
                completion_tokens=0,
            ),
            latency_ms=int(
                (time.perf_counter() - start) * 1000
            ),
        )

    prompt = build_grounded_prompt(
        retrieval.results,
        req.message,
        language,
    )

    request.state.llm_calls = None
    request.state.prompt_tokens = None
    request.state.completion_tokens = None
    completion = create_chat_completion(
        prompt.messages,
        temperature=DEFAULT_TEMPERATURE,
        max_tokens=DEFAULT_MAX_TOKENS,
    )
    request.state.llm_calls = completion.llm_calls
    request.state.prompt_tokens = completion.prompt_tokens
    request.state.completion_tokens = completion.completion_tokens

    answer, grounded = finalize_answer(
        completion.content,
        language,
    )
    request.state.grounded = grounded

    conversation_memory.record_turn(
        conversation_id,
        req.message,
        access,
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
        latency_ms=int(
            (time.perf_counter() - start) * 1000
        ),
    )
