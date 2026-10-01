"""SecretBroker: Credential vault isolation and streaming redaction kernel for AstraRun 1.0."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.security.secret_broker")


@dataclass
class RedactionReport:
    """Metadata detailing redaction occurrences without exposing secrets."""
    redaction_count: int = 0
    redacted_types: List[str] = field(default_factory=list)
    has_redactions: bool = False


class SecretBroker:
    """
    Credential vault isolation and streaming scrubber.
    Ensures language models, logs, and telemetry only see opaque handles ('secret://...'),
    resolving raw secrets JIT at the execution boundary and scrubbing all outputs.
    """

    # Common API Key & Token Patterns
    COMMON_TOKEN_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
        ("BEARER_TOKEN", re.compile(r"Bearer\s+([A-Za-z0-9_\-\.~+/=]{16,})", re.IGNORECASE)),
        ("ANTHROPIC_KEY", re.compile(r"\b(sk-ant-[A-Za-z0-9_\-]{20,})\b")),
        ("OPENAI_KEY", re.compile(r"\b(sk-(?:proj-)?[A-Za-z0-9_\-]{20,})\b")),
        ("GITHUB_PAT", re.compile(r"\b(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,})\b")),
        ("AWS_KEY", re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b")),
        ("AUTH_HEADER", re.compile(r"(?i)(Authorization|api[-_]key|x-api[-_]key):\s*(?!\*\*\*REDACTED|Bearer \*\*\*REDACTED)([^\r\n]{8,})")),
        ("URL_CREDENTIAL", re.compile(r"https?://([^:@/\s]+):([^@/\s]+)@")),
        ("URL_QUERY_PARAM", re.compile(r"[?&](token|api_key|key|secret|password|access_token)=([^&\s]{8,})", re.IGNORECASE)),
    ]

    _instance: Optional[SecretBroker] = None

    def __init__(self) -> None:
        self._vault: Dict[str, str] = {}
        self._reverse_lookup: Dict[str, str] = {}  # plaintext -> handle
        self._known_secrets: Set[str] = set()

    @classmethod
    def get_instance(cls) -> SecretBroker:
        """Singleton accessor for shared SecretBroker instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_secret(self, handle: str, plaintext: str) -> None:
        """
        Register a secret under an opaque handle (e.g. 'secret://VAULT/github_token').
        """
        if not handle.startswith("secret://"):
            raise ValueError(f"Secret handle must begin with 'secret://': {handle}")
        if not plaintext:
            return

        self._vault[handle] = plaintext
        self._reverse_lookup[plaintext] = handle
        self._known_secrets.add(plaintext)
        logger.debug("Registered secret handle: %s (length=%d)", handle, len(plaintext))

    def resolve_handle(self, handle_or_str: str) -> str:
        """
        JIT resolution of secret handles at the execution boundary.
        If the string is not a secret handle, returns the string as-is.
        Supports:
          - secret://VAULT/<key>
          - secret://ENV/<VAR_NAME>
        """
        if not isinstance(handle_or_str, str) or not handle_or_str.startswith("secret://"):
            return handle_or_str

        # 1. Environment handle: secret://ENV/<VAR>
        if handle_or_str.startswith("secret://ENV/"):
            env_var = handle_or_str[len("secret://ENV/"):]
            val = os.environ.get(env_var, "")
            if val:
                self._known_secrets.add(val)
            return val

        # 2. Vault handle: secret://VAULT/<key> or generic secret://<path>
        if handle_or_str in self._vault:
            return self._vault[handle_or_str]

        logger.warning("Unresolved secret handle requested: %s", handle_or_str)
        return ""

    resolve_argument = resolve_handle

    def resolve_environment(self, env_dict: Optional[Dict[str, str]]) -> Dict[str, str]:
        """
        Resolve all secret handles in an environment dictionary before process spawning.
        """
        if not env_dict:
            return {}
        resolved = {}
        for k, v in env_dict.items():
            if isinstance(v, str) and v.startswith("secret://"):
                resolved[k] = self.resolve_handle(v)
            else:
                resolved[k] = v
        return resolved

    def scrub_text(self, text: str) -> Tuple[str, RedactionReport]:
        """
        Scrub a stream string, removing all known registered secrets, Bearer tokens,
        API keys, and URL query credentials.
        Returns:
            (scrubbed_text, RedactionReport)
        """
        if not text:
            return "", RedactionReport()

        report = RedactionReport()
        scrubbed = text

        # 1. Scrub registered vault secrets first (exact matching)
        for secret in sorted(self._known_secrets, key=len, reverse=True):
            if len(secret) < 4:
                continue
            if secret in scrubbed:
                count = scrubbed.count(secret)
                handle = self._reverse_lookup.get(secret, "secret://VAULT/REDACTED")
                scrubbed = scrubbed.replace(secret, f"***REDACTED:{handle}***")
                report.redaction_count += count
                report.redacted_types.append("REGISTERED_SECRET")
                report.has_redactions = True

        # 2. Scrub regex patterns
        for token_type, pattern in self.COMMON_TOKEN_PATTERNS:
            matches = list(pattern.finditer(scrubbed))
            if matches:
                report.has_redactions = True
                report.redacted_types.append(token_type)
                report.redaction_count += len(matches)

                if token_type == "URL_CREDENTIAL":
                    # Redact only the password part: https://user:pass@host -> https://user:***REDACTED***@host
                    scrubbed = pattern.sub(r"https://\1:***REDACTED***@", scrubbed)
                elif token_type == "URL_QUERY_PARAM":
                    # Redact query param value: ?token=xyz -> ?token=***REDACTED***
                    scrubbed = pattern.sub(r"&\1=***REDACTED***", scrubbed)
                elif token_type == "AUTH_HEADER":
                    scrubbed = pattern.sub(r"\1: ***REDACTED***", scrubbed)
                elif token_type == "BEARER_TOKEN":
                    scrubbed = pattern.sub(r"Bearer ***REDACTED***", scrubbed)
                else:
                    scrubbed = pattern.sub(f"***REDACTED:{token_type}***", scrubbed)

        return scrubbed, report

    def clear(self) -> None:
        """Clear all registered secrets (useful for testing)."""
        self._vault.clear()
        self._reverse_lookup.clear()
        self._known_secrets.clear()
