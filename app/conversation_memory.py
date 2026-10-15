from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from threading import RLock
from typing import Literal

AccessLevel = Literal["public", "members"]

MAX_CONVERSATIONS = 1000
MAX_TURNS_PER_CONVERSATION = 4
MAX_QUERY_CHARS = 2000


@dataclass(frozen=True)
class ConversationTurn:
    question: str
    access_level: AccessLevel


class ConversationMemory:
    def __init__(
        self,
        *,
        max_conversations: int = MAX_CONVERSATIONS,
        max_turns_per_conversation: int = MAX_TURNS_PER_CONVERSATION,
        max_query_chars: int = MAX_QUERY_CHARS,
    ) -> None:
        if max_conversations <= 0:
            raise ValueError("max_conversations must be positive.")

        if max_turns_per_conversation <= 0:
            raise ValueError(
                "max_turns_per_conversation must be positive."
            )

        if max_query_chars <= 0:
            raise ValueError("max_query_chars must be positive.")

        self._max_conversations = max_conversations
        self._max_turns = max_turns_per_conversation
        self._max_query_chars = max_query_chars

        self._conversations: OrderedDict[
            str,
            deque[ConversationTurn],
        ] = OrderedDict()

        self._lock = RLock()

    def build_retrieval_query(
        self,
        conversation_id: str,
        question: str,
        access_level: AccessLevel,
    ) -> str:
        self._validate_inputs(
            conversation_id,
            question,
            access_level,
        )

        current_question = question.strip()

        with self._lock:
            turns = self._conversations.get(conversation_id)

            if turns is None:
                return current_question

            # Refresh LRU order whenever the conversation is used.
            self._conversations.move_to_end(conversation_id)

            # A public request must never reuse questions from a
            # members-only conversation. The current retrieval call
            # still applies the vector-store visibility filter.
            usable_turns = [
                turn
                for turn in turns
                if access_level == "members"
                or turn.access_level == "public"
            ]

        previous_questions = [
            turn.question
            for turn in usable_turns
        ]

        if not previous_questions:
            return current_question

        combined = " ".join(
            [*previous_questions, current_question]
        )

        return combined[-self._max_query_chars:]

    def record_turn(
        self,
        conversation_id: str,
        question: str,
        access_level: AccessLevel,
    ) -> None:
        self._validate_inputs(
            conversation_id,
            question,
            access_level,
        )

        turn = ConversationTurn(
            question=question.strip(),
            access_level=access_level,
        )

        with self._lock:
            turns = self._conversations.get(conversation_id)

            if turns is None:
                turns = deque(maxlen=self._max_turns)
                self._conversations[conversation_id] = turns

            turns.append(turn)
            self._conversations.move_to_end(conversation_id)

            while len(self._conversations) > self._max_conversations:
                self._conversations.popitem(last=False)

    def clear(self, conversation_id: str) -> None:
        with self._lock:
            self._conversations.pop(conversation_id, None)

    def size(self) -> int:
        with self._lock:
            return len(self._conversations)

    def _validate_inputs(
        self,
        conversation_id: str,
        question: str,
        access_level: AccessLevel,
    ) -> None:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValueError(
                "conversation_id must be a non-empty string."
            )

        if not isinstance(question, str) or not question.strip():
            raise ValueError(
                "question must be a non-empty string."
            )

        if access_level not in {"public", "members"}:
            raise ValueError(
                "access_level must be public or members."
            )


conversation_memory = ConversationMemory()
