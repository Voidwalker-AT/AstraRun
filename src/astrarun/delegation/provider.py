"""Provider-neutral abstraction and registry for Delegated AI agents.

Enables Astra to orchestrate conversations with external advisors (ChatGPT, Claude,
Gemini, local models, or test mocks) under a uniform interface.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from astrarun.delegation.models import DelegateProposal, DelegateResponse, DelegateSession

logger = logging.getLogger(__name__)


class DelegateProvider(ABC):
    """Abstract base class for all delegated AI advisors.
    
    All implementations provide advisory outputs only; Astra retains exclusive
    execution and verification authority.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier (e.g. 'chatgpt_web', 'mock', 'local_qwen')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the provider is currently accessible (e.g. browser open, backend running)."""
        pass

    @abstractmethod
    def ask(
        self,
        session: DelegateSession,
        prompt: str,
        context: Optional[str] = None,
    ) -> DelegateResponse:
        """Initiate or send a task inquiry to the delegate."""
        pass

    @abstractmethod
    def continue_conversation(
        self,
        session: DelegateSession,
        message: str,
        context: Optional[str] = None,
    ) -> DelegateResponse:
        """Continue an existing conversation thread on the delegate."""
        pass

    def provide_context(self, session: DelegateSession, context_payload: str) -> bool:
        """Feed background context or workspace facts into the session."""
        return True

    def request_review(
        self,
        session: DelegateSession,
        artifacts_summary: str,
        execution_summary: str,
    ) -> DelegateResponse:
        """Request the delegate review execution output and artifacts."""
        msg = (
            "Please review the execution results of your proposed solution:\n\n"
            f"[EXECUTION SUMMARY]\n{execution_summary}\n\n"
            f"[ARTIFACTS SUMMARY]\n{artifacts_summary}\n\n"
            "Evaluate if this meets the requirements. If satisfied, explicitly state 'APPROVED'. "
            "If issues remain, describe what needs fixing and provide the corrected code/patch."
        )
        return self.continue_conversation(session, msg)

    def request_debugging(
        self,
        session: DelegateSession,
        error_context: str,
        source_context: str,
    ) -> DelegateResponse:
        """Send runtime error/test failure context back to the delegate for repair."""
        msg = (
            "The proposed solution encountered errors during local execution:\n\n"
            f"[ERROR CONTEXT]\n{error_context}\n\n"
            f"[CURRENT SOURCE]\n{source_context}\n\n"
            "Analyze the failure, explain the root cause, and provide the corrected code or unified diff."
        )
        return self.continue_conversation(session, msg)

    def request_plan(self, session: DelegateSession, objective: str) -> DelegateResponse:
        """Ask the delegate for an architectural plan or strategy."""
        msg = f"Provide a concise implementation plan for the following objective:\n{objective}"
        return self.continue_conversation(session, msg)

    def request_code(self, session: DelegateSession, specification: str) -> DelegateResponse:
        """Request concrete source code from the delegate for a given specification."""
        msg = f"Provide complete, executable code for the following specification:\n{specification}"
        return self.continue_conversation(session, msg)

    def summarize(self, session: DelegateSession) -> str:
        """Summarize the history of the delegated session."""
        return f"Delegated session {session.session_id} with {self.provider_name} ({len(session.turns)} turns)."


class DelegateRegistry:
    """Global registry of available delegate providers."""

    _instance: Optional[DelegateRegistry] = None

    def __init__(self) -> None:
        self._providers: Dict[str, DelegateProvider] = {}
        self._default_provider: str = "mock"

    @classmethod
    def get_instance(cls) -> DelegateRegistry:
        if cls._instance is None:
            reg = cls()
            from astrarun.delegation.mock import MockDelegateProvider
            from astrarun.delegation.chatgpt_web import ChatGPTWebDelegate
            reg.register(MockDelegateProvider(name="mock"), set_default=True)
            reg.register(ChatGPTWebDelegate())
            cls._instance = reg
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def register(self, provider: DelegateProvider, set_default: bool = False) -> None:
        key = provider.provider_name.lower().strip()
        self._providers[key] = provider
        if set_default or len(self._providers) == 1:
            self._default_provider = key
        logger.debug("Registered delegate provider: %s", key)

    def get(self, name: str) -> Optional[DelegateProvider]:
        return self._providers.get(name.lower().strip())

    def list_providers(self) -> List[str]:
        return list(self._providers.keys())

    def resolve_provider(self, requested_name: Optional[str] = None) -> DelegateProvider:
        """Resolve a requested provider or fallback safely to available provider."""
        if requested_name:
            norm = requested_name.lower().strip()
            prov = self._providers.get(norm)
            if not prov:
                # Fuzzy match (e.g. 'chatgpt' -> 'chatgpt_web')
                for k, p in self._providers.items():
                    if norm in k or k in norm:
                        prov = p
                        break
            if prov and prov.is_available():
                return prov
            if prov and not prov.is_available():
                fallback = self._providers.get("mock") or self._providers.get(self._default_provider)
                if fallback and fallback.is_available():
                    logger.info("Requested provider '%s' is unavailable; falling back to '%s'", requested_name, fallback.provider_name)
                    return fallback
                return prov
            if prov:
                return prov
            raise ValueError(f"Requested delegate provider '{requested_name}' is not registered. Available: {list(self._providers.keys())}")

        default_prov = self._providers.get(self._default_provider)
        if default_prov:
            return default_prov
        if self._providers:
            return next(iter(self._providers.values()))
        raise RuntimeError("No delegate providers registered in DelegateRegistry.")
