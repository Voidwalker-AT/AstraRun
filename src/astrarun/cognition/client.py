"""Model-independent HTTP inference client for AstraRun local model servers.

Strict Security Invariants:
  - Connects ONLY to loopback interfaces (127.0.0.1 / localhost).
  - All prompt texts and raw responses pass through SecretBroker stream scrubbing.
  - Zero cloud telemetry or external network calls.
  - Enforces strict structured output validation with bounded single-pass repair.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Dict, Optional, Type
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError

from astrarun.cognition.models import InferenceObservation, InferenceRequest
from astrarun.core.logging import get_logger
from astrarun.security.secret_broker import SecretBroker

logger = get_logger("astrarun.cognition.client")


class ModelClient:
    """
    Submits structured inference requests to loopback llama-server instances.
    Provides strict loopback enforcement, stream scrubbing, and schema validation.
    """

    def __init__(
        self,
        secret_broker: Optional[SecretBroker] = None,
        default_timeout: float = 30.0,
    ) -> None:
        self.secret_broker = secret_broker or SecretBroker.get_instance()
        self.default_timeout = default_timeout

    def _validate_loopback_endpoint(self, endpoint: str) -> None:
        """Verify endpoint is strictly bound to local loopback to prevent SSRF or external exfiltration."""
        parsed = urlparse(endpoint)
        hostname = (parsed.hostname or "").lower()
        if hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(
                f"Security violation: Model endpoint must be bound strictly to loopback (127.0.0.1). Got '{hostname}'"
            )

    async def complete(
        self,
        request: InferenceRequest,
        endpoint: str,
        response_model: Optional[Type[BaseModel]] = None,
    ) -> InferenceObservation:
        """
        Asynchronously send inference request to local llama-server.
        """
        self._validate_loopback_endpoint(endpoint)
        start_t = time.perf_counter()
        model_id = f"{request.role.value}@{endpoint}"

        # 1. Scrub prompt messages via SecretBroker
        scrubbed_messages = []
        for msg in request.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            clean_content, _ = self.secret_broker.scrub_text(content)
            scrubbed_messages.append({"role": role, "content": clean_content})

        url = f"{endpoint.rstrip('/')}/v1/chat/completions"
        payload = {
            "messages": scrubbed_messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stop": request.stop,
        }

        timeout_sec = request.timeout if request.timeout > 0 else self.default_timeout

        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                res = await client.post(url, json=payload)

            lat_ms = (time.perf_counter() - start_t) * 1000.0

            if res.status_code != 200:
                return InferenceObservation(
                    model_id=model_id,
                    status="FAILED",
                    raw_output="",
                    latency_ms=lat_ms,
                    failure_reason=f"Server returned HTTP {res.status_code}: {res.text[:200]}",
                )

            data = res.json()
            choices = data.get("choices", [])
            msg_dict = choices[0].get("message", {}) if choices else {}
            raw_content = msg_dict.get("content", "") or ""
            if not raw_content and "reasoning_content" in msg_dict:
                raw_content = msg_dict["reasoning_content"] or ""

            # Scrub response before logging or returning
            clean_raw_content, _ = self.secret_broker.scrub_text(raw_content)

            usage = data.get("usage", {})
            prompt_tok = usage.get("prompt_tokens", 0)
            comp_tok = usage.get("completion_tokens", 0)

            # 2. Schema Validation
            parsed_dict, is_valid, fail_reason = self._parse_and_validate(clean_raw_content, response_model)

            status = "SUCCESS" if is_valid else "SCHEMA_INVALID"

            return InferenceObservation(
                model_id=model_id,
                status=status,
                raw_output=clean_raw_content,
                parsed_output=parsed_dict,
                schema_valid=is_valid,
                latency_ms=lat_ms,
                prompt_tokens=prompt_tok,
                completion_tokens=comp_tok,
                failure_reason=fail_reason,
            )

        except httpx.TimeoutException:
            lat_ms = (time.perf_counter() - start_t) * 1000.0
            return InferenceObservation(
                model_id=model_id,
                status="TIMEOUT",
                latency_ms=lat_ms,
                failure_reason=f"Inference timed out after {timeout_sec}s",
            )
        except Exception as e:
            lat_ms = (time.perf_counter() - start_t) * 1000.0
            return InferenceObservation(
                model_id=model_id,
                status="FAILED",
                latency_ms=lat_ms,
                failure_reason=f"Client communication error: {str(e)}",
            )

    def complete_sync(
        self,
        request: InferenceRequest,
        endpoint: str,
        response_model: Optional[Type[BaseModel]] = None,
    ) -> InferenceObservation:
        """Synchronous wrapper for complete()."""
        return asyncio.run(self.complete(request, endpoint, response_model))

    def _parse_and_validate(
        self,
        raw_text: str,
        response_model: Optional[Type[BaseModel]] = None,
    ) -> tuple[Optional[Dict[str, Any]], bool, Optional[str]]:
        """
        Parses raw model output as JSON, attempting bounded repair if necessary,
        and verifies it against the requested Pydantic response_model.
        """
        if not response_model:
            # If no schema specified, attempt optional JSON parse
            try:
                parsed = json.loads(raw_text)
                return parsed, True, None
            except Exception:
                return None, True, None

        # Clean JSON from markdown fences or trailing prose
        cleaned = raw_text.strip()
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if fence_match:
            cleaned = fence_match.group(1).strip()

        # Extract first outermost brace block
        brace_match = re.search(r"(\{[\s\S]*\})", cleaned)
        if brace_match:
            cleaned = brace_match.group(1).strip()

        try:
            parsed_json = json.loads(cleaned)
        except Exception as json_err:
            return None, False, f"JSON parse failure: {str(json_err)}"

        # Validate with Pydantic model
        try:
            validated_obj = response_model.model_validate(parsed_json)
            # If validated model has graph invariants (e.g. PlanDAG), execute them
            if hasattr(validated_obj, "validate_graph"):
                validated_obj.validate_graph()
            return validated_obj.model_dump(), True, None
        except ValidationError as val_err:
            return parsed_json, False, f"Schema validation error: {str(val_err)}"
        except ValueError as graph_err:
            return parsed_json, False, f"Graph invariant violation: {str(graph_err)}"
