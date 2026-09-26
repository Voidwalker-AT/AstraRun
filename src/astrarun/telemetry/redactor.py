"""Defensive redaction of sensitive credentials and tokens for local evaluation logs."""

from __future__ import annotations

import re

# Defensive patterns for common sensitive credentials
REDACTION_PATTERNS = [
    # API key patterns (OpenAI, Anthropic, Gemini, generic sk-)
    (re.compile(r"sk-[a-zA-Z0-9\-_]{16,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    # Bearer tokens
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{16,}", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    # Generic password / secret query parameters
    (re.compile(r"(password|pwd|secret|token|api_key|apikey)=([^\s&]+)", re.IGNORECASE), r"\1=[REDACTED]"),
    # Authorization header values
    (re.compile(r"(Authorization:\s*Basic\s+)[a-zA-Z0-9+/=]+", re.IGNORECASE), r"\1[REDACTED]"),
]


def redact_sensitive_text(text: str) -> str:
    """Scan and redact obvious passwords, API keys, and authorization tokens."""
    if not text:
        return text

    redacted = text
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)

    return redacted
