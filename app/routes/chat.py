import time
import uuid
from typing import Literal
from fastapi import APIRouter, Depends
from app.auth import get_access_level
from app.schemas import ChatRequest, ChatResponse, Usage

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, access: Literal["public", "members"] = Depends(get_access_level)):
    start = time.perf_counter()
    conversation_id = req.conversation_id or f"c_{uuid.uuid4().hex[:8]}"
    return ChatResponse(
        answer="(stub) The RAG pipeline is not built yet.",
        conversation_id=conversation_id,
        grounded=False,
        sources=[],
        usage=Usage(llm_calls=0, prompt_tokens=0, completion_tokens=0),
        latency_ms=int((time.perf_counter() - start) * 1000),
    )
