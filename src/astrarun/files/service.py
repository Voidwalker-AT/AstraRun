"""File capability services: search, recency, open, reveal, and metadata."""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from astrarun.capabilities.models import (
    CapabilityErrorCode,
    CapabilityResult,
    FileCandidate,
)
from astrarun.core.logging import get_logger
from astrarun.files.index import FileMetadataIndex

logger = get_logger("astrarun.files.service")

# Executable/script file extensions blocked from generic direct execution
PROHIBITED_OPEN_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".ps1", ".msi", ".scr", ".com",
    ".vbs", ".reg", ".pif", ".hta", ".cpl", ".jar", ".wsf"
}

_global_file_index: Optional[FileMetadataIndex] = None


def get_file_index() -> FileMetadataIndex:
    """Retrieve or initialize the singleton file metadata index."""
    global _global_file_index
    if _global_file_index is None:
        _global_file_index = FileMetadataIndex()
    return _global_file_index


def find_file(
    query: str = "",
    extension: Optional[str] = None,
    location: Optional[str] = None,
    file_type: Optional[str] = None,
    limit: int = 10,
) -> CapabilityResult:
    """Find files by substring, extension, or location."""
    t0 = time.perf_counter()
    index = get_file_index()
    candidates = index.search(
        query=query,
        extension=extension,
        location=location,
        file_type=file_type,
        limit=limit,
    )
    latency = (time.perf_counter() - t0) * 1000

    if not candidates:
        return CapabilityResult.fail(
            capability="find_file",
            message=f"No files matching '{query or extension or location}' found.",
            error_code=CapabilityErrorCode.NOT_FOUND,
            latency_ms=latency,
        )

    # Check for close ambiguity if top 2 candidates have identical high scores
    if len(candidates) > 1 and candidates[0].score == candidates[1].score and candidates[0].score > 1.0:
        return CapabilityResult.ok(
            capability="find_file",
            message=f"Found {len(candidates)} file candidates. Multiple close matches found.",
            data={"candidates": [c.to_dict() for c in candidates], "count": len(candidates), "ambiguous": True},
            context_updates=[{"type": "file_candidates_found", "candidates": [c.path for c in candidates[:3]]}],
            latency_ms=latency,
        )

    return CapabilityResult.ok(
        capability="find_file",
        message=f"Found {len(candidates)} matching file(s).",
        data={"candidates": [c.to_dict() for c in candidates], "count": len(candidates)},
        context_updates=[{"type": "file_candidates_found", "candidates": [c.path for c in candidates[:3]]}],
        latency_ms=latency,
    )


def find_latest_file(
    extension: Optional[str] = None,
    location: Optional[str] = None,
    file_type: Optional[str] = None,
) -> CapabilityResult:
    """Find the single most recently modified file matching constraints."""
    t0 = time.perf_counter()
    index = get_file_index()
    candidates = index.search(
        query="",
        extension=extension,
        location=location,
        file_type=file_type,
        sort_by_newest=True,
        limit=5,
    )
    latency = (time.perf_counter() - t0) * 1000

    if not candidates:
        descriptor = file_type or extension or location or "file"
        return CapabilityResult.fail(
            capability="find_latest_file",
            message=f"No recent {descriptor} found.",
            error_code=CapabilityErrorCode.NOT_FOUND,
            latency_ms=latency,
        )

    top = candidates[0]
    dt_str = datetime.fromtimestamp(top.modified_time).strftime("%Y-%m-%d %H:%M:%S")
    return CapabilityResult.ok(
        capability="find_latest_file",
        message=f"Latest file: {top.filename} (modified {dt_str})",
        data={"file": top.to_dict(), "candidates": [c.to_dict() for c in candidates]},
        context_updates=[{"type": "latest_file_found", "path": top.path, "filename": top.filename}],
        latency_ms=latency,
    )


def list_recent_files(
    limit: int = 10,
    extension: Optional[str] = None,
    location: Optional[str] = None,
    file_type: Optional[str] = None,
) -> CapabilityResult:
    """List recently modified files across indexed roots."""
    t0 = time.perf_counter()
    index = get_file_index()
    candidates = index.search(
        query="",
        extension=extension,
        location=location,
        file_type=file_type,
        sort_by_newest=True,
        limit=limit,
    )
    latency = (time.perf_counter() - t0) * 1000

    return CapabilityResult.ok(
        capability="list_recent_files",
        message=f"Retrieved {len(candidates)} recent file(s).",
        data={"files": [c.to_dict() for c in candidates], "count": len(candidates)},
        latency_ms=latency,
    )


def open_file(path: str) -> CapabilityResult:
    """
    Open a verified local document or media file using its default Windows association.
    SECURITY: Prohibits execution of binary/script formats (.exe, .bat, .ps1, etc.).
    """
    t0 = time.perf_counter()
    try:
        norm_path = Path(path).resolve()
    except Exception as err:
        return CapabilityResult.fail(
            capability="open_file",
            message=f"Invalid file path: {err}",
            error_code=CapabilityErrorCode.INVALID_ARGUMENT,
        )

    if not norm_path.exists() or not norm_path.is_file():
        return CapabilityResult.fail(
            capability="open_file",
            message=f"File not found: {norm_path}",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    # Security Invariant: Executables and scripts are never executed via generic open_file
    ext = norm_path.suffix.lower()
    if ext in PROHIBITED_OPEN_EXTENSIONS:
        logger.error("Blocked execution of script/binary via open_file: %s", norm_path)
        return CapabilityResult.fail(
            capability="open_file",
            message=f"Direct opening of executable '{ext}' files is blocked by policy. You may reveal it in File Explorer instead.",
            error_code=CapabilityErrorCode.PERMISSION_DENIED,
            data={"path": str(norm_path), "extension": ext, "suggested_action": "reveal_file"},
        )

    try:
        os.startfile(str(norm_path))
        latency = (time.perf_counter() - t0) * 1000
        return CapabilityResult.ok(
            capability="open_file",
            message=f"Opened '{norm_path.name}'.",
            data={"path": str(norm_path), "filename": norm_path.name},
            context_updates=[{"type": "file_opened", "path": str(norm_path), "filename": norm_path.name}],
            latency_ms=latency,
        )
    except Exception as err:
        logger.error("Error opening file '%s': %s", norm_path, err)
        return CapabilityResult.fail(
            capability="open_file",
            message=f"Failed to open file: {err}",
            error_code=CapabilityErrorCode.OS_ERROR,
        )


def reveal_file(path: str) -> CapabilityResult:
    """Reveal a file or folder in Windows File Explorer with the item selected."""
    t0 = time.perf_counter()
    try:
        norm_path = Path(path).resolve()
    except Exception as err:
        return CapabilityResult.fail(
            capability="reveal_file",
            message=f"Invalid file path: {err}",
            error_code=CapabilityErrorCode.INVALID_ARGUMENT,
        )

    if not norm_path.exists():
        return CapabilityResult.fail(
            capability="reveal_file",
            message=f"Target path does not exist: {norm_path}",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    try:
        subprocess.run(["explorer.exe", f"/select,{str(norm_path)}"], check=False)
        latency = (time.perf_counter() - t0) * 1000
        return CapabilityResult.ok(
            capability="reveal_file",
            message=f"Revealed '{norm_path.name}' in File Explorer.",
            data={"path": str(norm_path), "filename": norm_path.name},
            context_updates=[{"type": "file_revealed", "path": str(norm_path), "filename": norm_path.name}],
            latency_ms=latency,
        )
    except Exception as err:
        return CapabilityResult.fail(
            capability="reveal_file",
            message=f"Failed to reveal file in Explorer: {err}",
            error_code=CapabilityErrorCode.OS_ERROR,
        )


def file_metadata(path: str) -> CapabilityResult:
    """Return structured metadata for a specific file path."""
    t0 = time.perf_counter()
    try:
        norm_path = Path(path).resolve()
    except Exception as err:
        return CapabilityResult.fail(
            capability="file_metadata",
            message=f"Invalid file path: {err}",
            error_code=CapabilityErrorCode.INVALID_ARGUMENT,
        )

    if not norm_path.exists():
        return CapabilityResult.fail(
            capability="file_metadata",
            message=f"File not found: {norm_path}",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    stat = norm_path.stat()
    meta = {
        "path": str(norm_path),
        "filename": norm_path.name,
        "extension": norm_path.suffix.lower(),
        "size_bytes": stat.st_size,
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
        "created_time": stat.st_ctime,
        "created_str": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
        "modified_time": stat.st_mtime,
        "modified_str": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "parent": str(norm_path.parent),
        "is_file": norm_path.is_file(),
        "is_dir": norm_path.is_dir(),
    }
    latency = (time.perf_counter() - t0) * 1000

    return CapabilityResult.ok(
        capability="file_metadata",
        message=f"Metadata for '{norm_path.name}': {meta['size_mb']} MB, modified {meta['modified_str']}",
        data=meta,
        latency_ms=latency,
    )
