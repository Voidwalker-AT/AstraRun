"""Optional statistical linguistic parser backed by spaCy.

Provides part-of-speech tags, lemmatization, and dependency trees for
conversational phrasing. Operates non-blockingly and gracefully falls back
to deterministic rules if unavailable or disabled.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_SPACY_NLP: Any = None
_SPACY_AVAILABLE: bool | None = None


def is_spacy_available() -> bool:
    """Check if spaCy and its English model are installed and importable."""
    global _SPACY_AVAILABLE, _SPACY_NLP
    if _SPACY_AVAILABLE is not None:
        return _SPACY_AVAILABLE

    try:
        import spacy
        # Attempt to load small model without NER to save RAM and time
        _SPACY_NLP = spacy.load("en_core_web_sm", disable=["ner"])
        _SPACY_AVAILABLE = True
    except Exception as exc:
        logger.debug("spaCy unavailable or model not found: %s", exc)
        _SPACY_AVAILABLE = False
        _SPACY_NLP = None

    return _SPACY_AVAILABLE


def parse_spacy_tokens(text: str) -> list[dict[str, Any]]:
    """Parse text with spaCy and return structured token annotations.
    
    Returns an empty list if spaCy is unavailable.
    """
    if not is_spacy_available() or _SPACY_NLP is None:
        return []

    try:
        doc = _SPACY_NLP(text)
        return [
            {
                "text": token.text,
                "lemma": token.lemma_,
                "pos": token.pos_,
                "tag": token.tag_,
                "dep": token.dep_,
                "head": token.head.text,
                "head_i": token.head.i,
                "start": token.idx,
                "end": token.idx + len(token.text),
            }
            for token in doc
        ]
    except Exception as exc:
        logger.debug("spaCy parse error: %s", exc)
        return []
