from __future__ import annotations

import pytest

from app.conversation_memory import ConversationMemory


def test_first_question_is_used_as_retrieval_query():
    memory = ConversationMemory()

    query = memory.build_retrieval_query(
        "conversation-1",
        "What events does MicroClub organize?",
        "public",
    )

    assert query == "What events does MicroClub organize?"


def test_follow_up_query_contains_previous_question():
    memory = ConversationMemory()

    memory.record_turn(
        "conversation-1",
        "What events does MicroClub organize?",
        "public",
    )

    query = memory.build_retrieval_query(
        "conversation-1",
        "Where are they held?",
        "public",
    )

    assert query == (
        "What events does MicroClub organize? "
        "Where are they held?"
    )


def test_only_recent_turns_are_kept():
    memory = ConversationMemory(
        max_turns_per_conversation=2,
    )

    memory.record_turn(
        "conversation-1",
        "First question",
        "public",
    )
    memory.record_turn(
        "conversation-1",
        "Second question",
        "public",
    )
    memory.record_turn(
        "conversation-1",
        "Third question",
        "public",
    )

    query = memory.build_retrieval_query(
        "conversation-1",
        "Current question",
        "public",
    )

    assert "First question" not in query
    assert "Second question" in query
    assert "Third question" in query
    assert "Current question" in query


def test_query_is_size_capped():
    memory = ConversationMemory(
        max_query_chars=40,
    )

    memory.record_turn(
        "conversation-1",
        "A" * 100,
        "public",
    )

    query = memory.build_retrieval_query(
        "conversation-1",
        "B" * 100,
        "public",
    )

    assert len(query) <= 40
    assert query.endswith("B" * 40)


def test_public_access_does_not_reuse_members_turns():
    memory = ConversationMemory()

    memory.record_turn(
        "conversation-1",
        "What are the private member benefits?",
        "members",
    )

    query = memory.build_retrieval_query(
        "conversation-1",
        "Tell me more.",
        "public",
    )

    assert query == "Tell me more."
    assert "private member benefits" not in query


def test_members_access_can_reuse_public_and_members_turns():
    memory = ConversationMemory()

    memory.record_turn(
        "conversation-1",
        "What public events exist?",
        "public",
    )
    memory.record_turn(
        "conversation-1",
        "What are the member benefits?",
        "members",
    )

    query = memory.build_retrieval_query(
        "conversation-1",
        "Tell me more.",
        "members",
    )

    assert "What public events exist?" in query
    assert "What are the member benefits?" in query
    assert "Tell me more." in query


def test_conversation_count_is_capped():
    memory = ConversationMemory(
        max_conversations=2,
    )

    memory.record_turn(
        "conversation-1",
        "First",
        "public",
    )
    memory.record_turn(
        "conversation-2",
        "Second",
        "public",
    )
    memory.record_turn(
        "conversation-3",
        "Third",
        "public",
    )

    assert memory.size() == 2

    assert memory.build_retrieval_query(
        "conversation-1",
        "Follow-up",
        "public",
    ) == "Follow-up"


def test_clear_removes_conversation():
    memory = ConversationMemory()

    memory.record_turn(
        "conversation-1",
        "Question",
        "public",
    )
    memory.clear("conversation-1")

    assert memory.build_retrieval_query(
        "conversation-1",
        "Follow-up",
        "public",
    ) == "Follow-up"


@pytest.mark.parametrize(
    ("conversation_id", "question", "access_level"),
    [
        ("", "Question", "public"),
        ("conversation-1", "", "public"),
        ("conversation-1", "Question", "admin"),
    ],
)
def test_invalid_inputs_are_rejected(
    conversation_id,
    question,
    access_level,
):
    memory = ConversationMemory()

    with pytest.raises(ValueError):
        memory.record_turn(
            conversation_id,
            question,
            access_level,
        )
