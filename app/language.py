from __future__ import annotations

import re
from typing import Literal

Language = Literal["en", "fr", "ar"]

_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")

_FRENCH_WORDS = {
    "a",
    "avec",
    "ce",
    "cette",
    "dans",
    "des",
    "du",
    "est",
    "et",
    "la",
    "le",
    "les",
    "organise",
    "organisent",
    "pour",
    "que",
    "qui",
    "sur",
    "une",
}

_ENGLISH_WORDS = {
    "a",
    "about",
    "and",
    "are",
    "does",
    "for",
    "how",
    "in",
    "is",
    "of",
    "on",
    "organize",
    "organizes",
    "the",
    "this",
    "what",
    "which",
    "who",
    "with",
}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[A-Za-zÀ-ÿ]+", text.lower()))


def detect_language(text: str) -> Language:
    """
    Detect the language of a user question.

    Arabic is detected by Unicode range. For Latin text, a small
    stop-word check distinguishes French from English. English is
    the safe default when the evidence is ambiguous.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string.")

    normalized = text.strip()

    if _ARABIC_RE.search(normalized):
        return "ar"

    words = _words(normalized)

    french_score = len(words & _FRENCH_WORDS)
    english_score = len(words & _ENGLISH_WORDS)

    if french_score > english_score:
        return "fr"

    return "en"
