"""NetworkBroker for Governed Network Access in AstraRun 1.0.

Authoritative network gateway:
- Default DENY policy.
- Distinguishes low-risk public internet retrieval (GET/HEAD) from high-risk data exfiltration (POST/PUT).
- Enforces private IP / loopback protection (blocking metadata endpoints, LAN scans).
- Integrates with DownloadQuarantine for all file downloads.
"""

from __future__ import annotations

import ipaddress
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger
from astrarun.network.quarantine import DownloadQuarantine, QuarantineRecord
from astrarun.security.action_gate import ActionGate
from astrarun.security.models import ActionRequest, Operation, RiskLevel

logger = get_logger("astrarun.network.broker")


class NetworkOperation(str, Enum):
    HTTP_GET = "HTTP_GET"
    HTTP_HEAD = "HTTP_HEAD"
    DOWNLOAD = "DOWNLOAD"
    HTTP_POST = "HTTP_POST"


@dataclass
class NetworkResponse:
    """Standardized response from NetworkBroker operations."""
    status_code: int
    data: bytes
    headers: Dict[str, str]
    url: str
    quarantine_record: Optional[QuarantineRecord] = None
    error: Optional[str] = None

    @property
    def text(self) -> str:
        return self.data.decode("utf-8", errors="replace")

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


# Blocked IP networks (Private LAN, Link-Local, AWS/Cloud Metadata)
BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # Link local & Cloud metadata (169.254.169.254)
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
]


class NetworkBroker:
    """Authoritative broker and gatekeeper for all network traffic."""

    _instance: Optional[NetworkBroker] = None

    def __init__(
        self,
        quarantine: Optional[DownloadQuarantine] = None,
        action_gate: Optional[ActionGate] = None,
        allow_internal_inference: bool = True,
    ) -> None:
        self.quarantine = quarantine or DownloadQuarantine()
        self.action_gate = action_gate or ActionGate.get_instance()
        self.allow_internal_inference = allow_internal_inference
        # Allow internal llama-server ports if running locally
        self.allowed_internal_ports = {8080, 8081}

    @classmethod
    def get_instance(cls) -> NetworkBroker:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def validate_url(self, url: str) -> Tuple[bool, str]:
        """Validate URL protocol, hostname, and destination safety."""
        try:
            parsed = urllib.parse.urlparse(url)
        except Exception as e:
            return False, f"Invalid URL syntax: {e}"

        if parsed.scheme.lower() not in {"http", "https"}:
            return False, f"Unsupported network protocol '{parsed.scheme}'; only HTTP/HTTPS permitted."

        hostname = parsed.hostname
        if not hostname:
            return False, "URL is missing a valid hostname."

        # Check for local loopback / private IP access
        try:
            ip = ipaddress.ip_address(hostname)
            # Check internal inference exception
            if self.allow_internal_inference and ip.is_loopback:
                if parsed.port in self.allowed_internal_ports:
                    return True, "Permitted local inference endpoint."

            for net in BLOCKED_NETWORKS:
                if ip in net:
                    return False, f"Access to private/metadata IP address {ip} is strictly blocked."
        except ValueError:
            # Hostname is a domain name (e.g. docs.python.org)
            if hostname.lower() in {"localhost"}:
                if self.allow_internal_inference and parsed.port in self.allowed_internal_ports:
                    return True, "Permitted local inference endpoint."
                return False, "Access to localhost is blocked by network governance."

        return True, "URL validated successfully."

    def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 15.0,
    ) -> NetworkResponse:
        """Perform low-risk public HTTP GET retrieval."""
        valid, msg = self.validate_url(url)
        if not valid:
            logger.warning("NetworkBroker blocked GET: %s (%s)", url, msg)
            return NetworkResponse(status_code=403, data=b"", headers={}, url=url, error=msg)

        req_headers = {"User-Agent": "AstraRun/1.0 (+https://github.com/astrarun)"}
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, headers=req_headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                resp_headers = dict(resp.headers.items())
                return NetworkResponse(
                    status_code=resp.status,
                    data=data,
                    headers=resp_headers,
                    url=url,
                )
        except urllib.error.HTTPError as e:
            return NetworkResponse(status_code=e.code, data=e.read(), headers=dict(e.headers.items()), url=url, error=str(e))
        except Exception as e:
            return NetworkResponse(status_code=500, data=b"", headers={}, url=url, error=str(e))

    def head(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 10.0,
    ) -> NetworkResponse:
        """Perform HTTP HEAD metadata probe."""
        valid, msg = self.validate_url(url)
        if not valid:
            return NetworkResponse(status_code=403, data=b"", headers={}, url=url, error=msg)

        req_headers = {"User-Agent": "AstraRun/1.0"}
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, headers=req_headers, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_headers = dict(resp.headers.items())
                return NetworkResponse(status_code=resp.status, data=b"", headers=resp_headers, url=url)
        except urllib.error.HTTPError as e:
            return NetworkResponse(status_code=e.code, data=b"", headers=dict(e.headers.items()), url=url, error=str(e))
        except Exception as e:
            return NetworkResponse(status_code=500, data=b"", headers={}, url=url, error=str(e))

    def download_to_quarantine(
        self,
        url: str,
        suggested_filename: Optional[str] = None,
        timeout: float = 30.0,
    ) -> NetworkResponse:
        """Download remote resource directly into quarantine staging."""
        get_resp = self.get(url, timeout=timeout)
        if not get_resp.is_success:
            return get_resp

        fname = suggested_filename
        if not fname:
            fname = Path(urllib.parse.urlparse(url).path).name or "download.bin"

        content_type = get_resp.headers.get("Content-Type", "application/octet-stream")
        record = self.quarantine.stage_file(
            content=get_resp.data,
            filename=fname,
            source_url=url,
            content_type=content_type,
        )

        get_resp.quarantine_record = record
        return get_resp

    def post(
        self,
        url: str,
        data: bytes,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 15.0,
        authorization_token: Optional[str] = None,
    ) -> NetworkResponse:
        """Perform high-risk outbound POST request (governed by ActionGate)."""
        valid, msg = self.validate_url(url)
        if not valid:
            return NetworkResponse(status_code=403, data=b"", headers={}, url=url, error=msg)

        # Outbound data transmission requires ActionGate evaluation
        action_req = ActionRequest(
            operation=Operation.NETWORK_ACCESS,
            target=url,
            risk_level=RiskLevel.HIGH,
            description=f"Outbound POST payload ({len(data)} bytes) to {url}",
            user_facing_prompt=f"Authorize outbound data transmission to {url}?",
            authorization_ref=authorization_token,
        )
        verdict = self.action_gate.evaluate(action_req)
        if not verdict.permitted:
            return NetworkResponse(
                status_code=403,
                data=b"",
                headers={},
                url=url,
                error=f"Outbound network request denied by ActionGate: {verdict.reason}",
            )

        req_headers = {"User-Agent": "AstraRun/1.0"}
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_data = resp.read()
                return NetworkResponse(
                    status_code=resp.status,
                    data=resp_data,
                    headers=dict(resp.headers.items()),
                    url=url,
                )
        except urllib.error.HTTPError as e:
            return NetworkResponse(status_code=e.code, data=e.read(), headers=dict(e.headers.items()), url=url, error=str(e))
        except Exception as e:
            return NetworkResponse(status_code=500, data=b"", headers={}, url=url, error=str(e))
