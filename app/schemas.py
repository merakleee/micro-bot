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


class DocumentResponse(BaseModel):
    doc_id: str
    title: str
    visibility: Literal["public", "members"]
    status: Literal["processing", "ready", "failed"]
    error: str | None
    created_at: str


class DocumentUploadResponse(BaseModel):
    doc_id: str
    status: Literal["processing", "ready", "failed"]
    skipped: bool


class DocumentDeleteResponse(BaseModel):
    doc_id: str
    deleted: bool


FeedbackRating = Literal["up", "down"]
FeedbackComment = Annotated[str, StringConstraints(
    strip_whitespace=True, max_length=1000)]
ConversationId = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1)]


class FeedbackRequest(BaseModel):
    conversation_id: ConversationId
    rating: FeedbackRating
    comment: FeedbackComment | None = None


class FeedbackResponse(BaseModel):
    feedback_id: int
