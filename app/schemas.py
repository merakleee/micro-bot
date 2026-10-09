from typing import Annotated, Literal
from pydantic import BaseModel, StringConstraints

Message = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=2000)]


class ChatRequest(BaseModel):
    message: Message
    conversation_id: str | None = None


class Source(BaseModel):
    doc_id: str
    title: str
    snippet: str


class Usage(BaseModel):
    llm_calls: int
    prompt_tokens: int
    completion_tokens: int


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    grounded: bool
    sources: list[Source]
    usage: Usage
    latency_ms: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    documents: int
