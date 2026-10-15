from __future__ import annotations

import pytest

from app.language import detect_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "What does MicroClub organize?",
            "en",
        ),
        (
            "How can I join the club?",
            "en",
        ),
        (
            "What are the club activities?",
            "en",
        ),
        (
            "Que fait MicroClub ?",
            "fr",
        ),
        (
            "Quelles activités le club organise-t-il ?",
            "fr",
        ),
        (
            "Comment rejoindre le club ?",
            "fr",
        ),
        (
            "ما هي أنشطة النادي؟",
            "ar",
        ),
        (
            "كيف يمكنني الانضمام إلى النادي؟",
            "ar",
        ),
        (
            "ماذا ينظم النادي؟",
            "ar",
        ),
    ],
)
def test_detect_language(text: str, expected: str):
    assert detect_language(text) == expected


def test_arabic_is_detected_even_when_text_contains_latin_words():
    assert detect_language("ما هي MicroClub activities؟") == "ar"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        None,
    ],
)
def test_detect_language_rejects_empty_text(text):
    with pytest.raises(ValueError, match="non-empty"):
        detect_language(text)


def test_ambiguous_latin_text_defaults_to_english():
    assert detect_language("MicroClub") == "en"
