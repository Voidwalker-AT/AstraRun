"""Data models for request ingress and boundary classification."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RequestOrigin(str, Enum):
    """Origin of a request entering AstraRun."""
    LAUNCHER = "LAUNCHER"
    CLI = "CLI"
    RUNTIME = "RUNTIME"
    CONFIRMATION_RESUME = "CONFIRMATION_RESUME"
    INTERNAL = "INTERNAL"


class IngressRoute(str, Enum):
    """High-level ingress boundary route."""
    META_COMMAND = "META_COMMAND"
    OPERATIONAL_GOAL = "OPERATIONAL_GOAL"


@dataclass(frozen=True)
class RequestEnvelope:
    """
    Immutable envelope representing an ingress request fact.
    
    Contains facts only. Does not contain model, routing, or execution decisions.
    """
    raw_query: str
    normalized_query: str
    origin: RequestOrigin = RequestOrigin.INTERNAL
    request_id: str = ""
    origin_hwnd: Optional[int] = None
    session_id: Optional[str] = None
    timestamp: float = 0.0
    dry_run: bool = False

    def __post_init__(self) -> None:
        if not self.request_id:
            object.__setattr__(self, "request_id", f"req-{uuid.uuid4().hex[:12]}")
        if self.timestamp == 0.0:
            object.__setattr__(self, "timestamp", time.time())
        if not self.normalized_query and self.raw_query is not None:
            norm = " ".join((self.raw_query or "").strip().split())
            object.__setattr__(self, "normalized_query", norm)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.raw_query == other or self.normalized_query == other
        if isinstance(other, RequestEnvelope):
            return (
                self.raw_query == other.raw_query
                and self.normalized_query == other.normalized_query
                and self.origin == other.origin
                and self.origin_hwnd == other.origin_hwnd
                and self.dry_run == other.dry_run
            )
        return False

    def __hash__(self) -> int:
        return hash((self.raw_query, self.origin, self.request_id))

    def __str__(self) -> str:
        return self.raw_query

    @classmethod
    def create(
        cls,
        raw_query: str,
        origin: RequestOrigin = RequestOrigin.INTERNAL,
        origin_hwnd: Optional[int] = None,
        session_id: Optional[str] = None,
        dry_run: bool = False,
        request_id: Optional[str] = None,
    ) -> RequestEnvelope:
        clean = (raw_query or "").strip()
        norm = " ".join(clean.split())
        return cls(
            request_id=request_id or f"req-{uuid.uuid4().hex[:12]}",
            raw_query=raw_query or "",
            normalized_query=norm,
            origin=origin,
            origin_hwnd=origin_hwnd,
            session_id=session_id,
            timestamp=time.time(),
            dry_run=dry_run,
        )


@dataclass(frozen=True)
class IngressDecision:
    """Decision made by the RequestBoundaryRouter at ingress."""
    route: IngressRoute
    reason_code: str
    normalized_query: str
    meta_family: Optional[str] = None
