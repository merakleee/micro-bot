from __future__ import annotations

from fastapi import APIRouter

from app import feedback as feedback_store
from app.schemas import FeedbackRequest, FeedbackResponse

router = APIRouter()


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=201,
)
def submit_feedback(req: FeedbackRequest) -> FeedbackResponse:
    feedback_id = feedback_store.create_feedback(
        conversation_id=req.conversation_id,
        rating=req.rating,
        comment=req.comment,
    )
    return FeedbackResponse(feedback_id=feedback_id)
