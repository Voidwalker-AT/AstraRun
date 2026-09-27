"""Sanitization, hashing, and deterministic summary serialization for Task History."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

# Secret Patterns to Redact
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9_.-]+", re.IGNORECASE),
    re.compile(r"--api-key(?:=|\s+)[^\s]+", re.IGNORECASE),
    re.compile(r"--token(?:=|\s+)[^\s]+", re.IGNORECASE),
    re.compile(r"--password(?:=|\s+)[^\s]+", re.IGNORECASE),
    re.compile(r"(?:api_key|secret|password|passwd|auth_token)\s*[:=]\s*['\"]?[^\s'\"]+", re.IGNORECASE),
]


def sanitize_request(text: Optional[str]) -> str:
    """
    Sanitize raw user request string by masking API keys, bearer tokens, and credentials.
    """
    if not text:
        return ""
    sanitized = text.strip()
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def hash_request(text: Optional[str]) -> str:
    """
    Compute a deterministic SHA-256 hash of the request text for privacy indexing.
    """
    clean = (text or "").strip().lower().encode("utf-8")
    return hashlib.sha256(clean).hexdigest()


def generate_task_title(request_text: Optional[str], default_cap: Optional[str] = None) -> str:
    """
    Deterministically generate a clear, human-readable task title without calling an LLM.
    """
    if not request_text:
        if default_cap:
            return default_cap.replace("_", " ").title()
        return "Workstation Task"

    raw = request_text.strip()
    low = raw.lower()

    # Common patterns
    m_port = re.search(r"(?:running on|using|on port|port)\s*:?\s*(\d{2,5})", low)
    if "inspect" in low and m_port:
        return f"Inspect Port {m_port.group(1)}"
    if ("what" in low or "who" in low) and m_port:
        return f"Inspect Port {m_port.group(1)}"
    if ("stop" in low or "kill" in low) and m_port:
        return f"Stop Process on Port {m_port.group(1)}"

    if "vscode" in low or "code" in low:
        m_proj = re.search(r"open\s+(?:project\s+)?([\w-]+)\s+in\s+(?:vscode|code)", low)
        if m_proj:
            return f"Open {m_proj.group(1).title()} in VS Code"
        m_proj2 = re.search(r"(?:vscode|code)\s+(?:for\s+)?([\w-]+)", low)
        if m_proj2:
            return f"Open {m_proj2.group(1).title()} in VS Code"

    if "screenshot" in low:
        return "Find Latest Screenshot"

    if "gpu" in low and "status" in low:
        return "Inspect GPU Status"
    if "cpu" in low and "status" in low:
        return "Inspect CPU Status"
    if "memory" in low or "ram" in low:
        return "Inspect Memory Status"
    if "system" in low and ("status" in low or "summary" in low or "info" in low):
        return "System Summary"

    if "running apps" in low or "running applications" in low:
        return "List Running Applications"

    if "recent files" in low:
        return "List Recent Files"

    if "git status" in low:
        m_git = re.search(r"git status\s+([\w-]+)", low)
        if m_git:
            return f"Git Status ({m_git.group(1).title()})"
        return "Check Git Status"

    # Truncate and clean sanitized request
    sanitized = sanitize_request(raw)
    if len(sanitized) > 48:
        return sanitized[:45] + "..."
    return sanitized.title() if sanitized else "Workstation Task"


def sanitize_capability_payload(capability_id: str, data: Any) -> Any:
    """
    Extract minimal, safe summary fields for persistent task history.
    Prevents leaking raw command-line secrets, memory dumps, or unbounded lists into SQLite.
    """
    if not data:
        return {}

    if isinstance(data, list):
        return data[:50]

    if not isinstance(data, dict):
        return {}

    sanitized: dict[str, Any] = {}

    if capability_id == "inspect_process":
        for k in ("pid", "name", "status", "cpu_percent", "memory_rss_mb", "num_threads", "ports"):
            if k in data:
                sanitized[k] = data[k]
        if "cmdline" in data:
            sanitized["cmdline"] = sanitize_request(str(data["cmdline"]))[:100]

    elif capability_id in ("find_process_on_port", "inspect_port"):
        for k in ("port", "status", "pid", "name", "path", "protocol"):
            if k in data:
                sanitized[k] = data[k]

    elif capability_id == "system_summary":
        for k in ("os", "release", "cpu_model", "cpu_count", "memory_total_gb", "memory_used_gb", "memory_percent", "battery_percent", "power_plugged"):
            if k in data:
                sanitized[k] = data[k]
        if "gpu" in data and isinstance(data["gpu"], dict):
            sanitized["gpu"] = {
                "name": data["gpu"].get("name"),
                "total_vram_mb": data["gpu"].get("total_vram_mb"),
                "used_vram_mb": data["gpu"].get("used_vram_mb"),
            }

    elif capability_id in ("project_git_status", "project_status"):
        for k in ("project_id", "path", "branch", "is_dirty", "modified_count", "untracked_count"):
            if k in data:
                sanitized[k] = data[k]

    elif capability_id in ("find_file", "find_latest_file", "list_recent_files"):
        if "matches" in data and isinstance(data["matches"], list):
            sanitized["matches_count"] = len(data["matches"])
            sanitized["top_matches"] = [
                {"name": m.get("name"), "size": m.get("size"), "modified": m.get("modified")}
                for m in data["matches"][:3]
                if isinstance(m, dict)
            ]
        elif "path" in data:
            sanitized["path"] = data.get("path")
            sanitized["name"] = data.get("name")
            sanitized["size"] = data.get("size")

    elif capability_id in ("list_running_applications", "list_windows"):
        if "applications" in data and isinstance(data["applications"], list):
            sanitized["count"] = len(data["applications"])
            sanitized["sample"] = [
                a.get("name") or a.get("title") for a in data["applications"][:5] if isinstance(a, dict)
            ]
        elif "windows" in data and isinstance(data["windows"], list):
            sanitized["count"] = len(data["windows"])
            sanitized["sample"] = [w.get("title") for w in data["windows"][:5] if isinstance(w, dict)]

    else:
        # Default bounded extraction
        for k, v in data.items():
            if isinstance(v, (int, float, bool, str)) and len(str(v)) < 120:
                sanitized[k] = v
            elif isinstance(v, list):
                sanitized[f"{k}_count"] = len(v)

    return sanitized


def generate_capability_summary(capability_id: str, data: dict[str, Any], default_message: str) -> str:
    """
    Generate a concise deterministic summary sentence from structured capability data.
    """
    if capability_id == "find_process_on_port" or capability_id == "inspect_port":
        if data.get("pid"):
            return f"Port {data.get('port')} is used by {data.get('name', 'process')} (PID {data.get('pid')})."
        return f"Port {data.get('port')} is not currently active."

    if capability_id == "process_resource_usage":
        return f"Process {data.get('name', data.get('pid'))} is using {data.get('memory_rss_mb', 0):.1f} MB RAM (CPU: {data.get('cpu_percent', 0):.1f}%)."

    if capability_id == "terminate_process":
        return f"Process {data.get('name', '')} (PID {data.get('pid')}) was terminated."

    if capability_id == "project_git_status":
        branch = data.get("branch", "unknown")
        mod = data.get("modified_count", 0)
        return f"Branch {branch} with {mod} modified files."

    if capability_id == "system_summary":
        cpu = data.get("cpu_percent", data.get("cpu_load", ""))
        ram = data.get("memory_percent", "")
        return f"System health optimal: CPU {cpu}%, RAM {ram}%."

    if capability_id == "find_latest_file":
        name = data.get("name") or (data.get("path") and data["path"].split("\\")[-1]) or "file"
        return f"Found latest file: {name}."

    return default_message


# Backward compatibility alias
generate_task_summary = generate_capability_summary
