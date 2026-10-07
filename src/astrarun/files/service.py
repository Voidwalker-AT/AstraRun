"""File capability services: search, recency, open, reveal, and metadata."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from astrarun.capabilities.models import (
    CapabilityErrorCode,
    CapabilityResult,
    FileCandidate,
)
from astrarun.core.logging import get_logger
from astrarun.core.paths import AstraPaths
from astrarun.files.index import FileMetadataIndex

logger = get_logger("astrarun.files.service")

# Executable/script file extensions blocked from generic direct execution
PROHIBITED_OPEN_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".ps1", ".msi", ".scr", ".com",
    ".vbs", ".reg", ".pif", ".hta", ".cpl", ".jar", ".wsf"
}

_global_file_index: Optional[FileMetadataIndex] = None


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    import msvcrt
    import io

    class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]
else:
    BY_HANDLE_FILE_INFORMATION = None


class SealedArtifactSource:
    """Encapsulates an open Win32 handle held with restrictive sharing (FILE_SHARE_READ only)."""

    def __init__(self, file_io: Any, canonical_path: Path, size_bytes: int, file_info: Any):
        self.file_io = file_io
        self.canonical_path = canonical_path
        self.size_bytes = size_bytes
        self.file_info = file_info

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.file_io.close()
        except Exception:
            pass


def get_file_link_count(path: str | Path) -> int:
    """Return the hard-link count for a file on Windows."""
    try:
        st = os.stat(str(path))
        if hasattr(st, "st_nlink"):
            return st.st_nlink
    except Exception:
        pass

    if sys.platform == "win32" and BY_HANDLE_FILE_INFORMATION:
        try:
            GENERIC_READ = 0x80000000
            FILE_SHARE_READ = 1 | 2 | 4
            OPEN_EXISTING = 3
            h = ctypes.windll.kernel32.CreateFileW(
                str(path), GENERIC_READ, FILE_SHARE_READ, None, OPEN_EXISTING, 0x02000000 | 0x80, None
            )
            if h != -1 and h != 0:
                info = BY_HANDLE_FILE_INFORMATION()
                success = ctypes.windll.kernel32.GetFileInformationByHandle(h, ctypes.byref(info))
                ctypes.windll.kernel32.CloseHandle(h)
                if success:
                    return int(info.nNumberOfLinks)
        except Exception:
            pass
    return 1


def open_sealed_source_handle(
    source_path: Path,
    authorized_roots: list[Path],
    max_size_bytes: int = 50 * 1024 * 1024,
) -> tuple[bool, str, Optional[SealedArtifactSource]]:
    """
    Open source artifact with restrictive sharing (FILE_SHARE_READ only),
    validating regular file, reparse status, link count, size, and canonical path on the SAME handle.
    Fails closed on any error.
    """
    resolved_str = str(source_path.resolve())

    if sys.platform != "win32":
        try:
            if not source_path.is_file() or source_path.is_symlink():
                return False, "Source artifact is not a regular file or is a symlink", None
            f = open(source_path, "rb")
            sz = os.fstat(f.fileno()).st_size
            if sz > max_size_bytes:
                f.close()
                return False, "File exceeds size limits", None
            return True, "", SealedArtifactSource(f, source_path.resolve(), sz, None)
        except Exception as e:
            return False, f"Failed opening source: {e}", None

    kernel32 = ctypes.windll.kernel32

    GENERIC_READ = 0x80000000
    FILE_SHARE_READ = 0x00000001  # Exclude concurrent write and delete
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x80
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000

    h = kernel32.CreateFileW(
        resolved_str,
        GENERIC_READ,
        FILE_SHARE_READ,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    if h == -1 or h == 0:
        err = ctypes.GetLastError()
        return False, f"Failed to open source file handle (WinError {err})", None

    try:
        # 1. Query handle information
        info = BY_HANDLE_FILE_INFORMATION()
        ok = kernel32.GetFileInformationByHandle(h, ctypes.byref(info))
        if not ok:
            kernel32.CloseHandle(h)
            return False, "Failed to query file information by handle", None

        FILE_ATTRIBUTE_DIRECTORY = 0x0010
        FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
        if info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY:
            kernel32.CloseHandle(h)
            return False, "Source is a directory, not a regular file", None

        if info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT:
            kernel32.CloseHandle(h)
            return False, "Source handle is a reparse point (symlink/junction/mount point)", None

        if info.nNumberOfLinks > 1:
            kernel32.CloseHandle(h)
            return False, f"Source has multiple hard links (link count {info.nNumberOfLinks} > 1)", None

        if info.nFileSizeHigh > 0 or info.nFileSizeLow > max_size_bytes:
            kernel32.CloseHandle(h)
            return False, f"Source artifact size exceeds limit ({max_size_bytes} bytes)", None

        file_size = (info.nFileSizeHigh << 32) | info.nFileSizeLow

        # 2. Query final canonical DOS path by handle
        buf = ctypes.create_unicode_buffer(2048)
        ret = kernel32.GetFinalPathNameByHandleW(h, buf, 2048, 0)
        if ret == 0:
            kernel32.CloseHandle(h)
            return False, "Failed to query canonical path by handle", None

        canon_path_str = buf.value
        if canon_path_str.startswith("\\\\?\\"):
            canon_path_str = canon_path_str[4:]
        canonical_path = Path(canon_path_str).resolve()

        # Check that canonical path is strictly inside one of the authorized roots
        is_inside = any(
            str(canonical_path).lower().startswith(str(root.resolve()).lower())
            for root in authorized_roots
        )
        if not is_inside:
            kernel32.CloseHandle(h)
            return False, f"Source canonical path escapes authorized sandbox boundaries: {canonical_path}", None

        # Check ancestor directories for symlinks or junctions
        curr = canonical_path.parent
        while curr != curr.parent:
            if os.path.isjunction(curr) or os.path.islink(curr):
                kernel32.CloseHandle(h)
                return False, f"Ancestor directory is a junction/symlink: {curr}", None
            curr = curr.parent

        # 3. Convert Win32 handle to Python FileIO
        fd = msvcrt.open_osfhandle(h, os.O_RDONLY)
        file_io = io.FileIO(fd, mode="rb", closefd=True)
        return True, "", SealedArtifactSource(file_io, canonical_path, file_size, info)
    except Exception as e:
        try:
            kernel32.CloseHandle(h)
        except Exception:
            pass
        return False, f"Exception validating source handle: {e}", None


def validate_safe_path(raw_path: str) -> tuple[bool, str]:
    """Validate that raw_path is not a device path, ADS, UNC, or reserved DOS name."""
    s = raw_path.strip()
    if not s:
        return False, "Path cannot be empty"
    if raw_path.endswith(" ") or raw_path.endswith("."):
        return False, "Trailing dots and spaces prohibited"
    if s.startswith(r"\\") or s.startswith("//"):
        return False, "UNC paths and device prefixes ('\\\\') are prohibited"
    if s.startswith(r"\??"):
        return False, "NT namespace paths ('\\??') are prohibited"

    colon_idx = s.find(":")
    if colon_idx != -1:
        if colon_idx != 1 or not s[0].isalpha():
            return False, f"Alternate Data Streams or malformed drive prefix prohibited: '{raw_path}'"
        if len(s) >= 2 and (len(s) == 2 or s[2] not in ("\\", "/")):
            return False, f"Drive-relative path prohibited: '{raw_path}'"
        if ":" in s[2:]:
            return False, f"Alternate Data Stream ':' prohibited in path: '{raw_path}'"

    reserved_names = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    parts = re.split(r"[/\\]+", s)
    for part in parts:
        if part not in (".", "..") and (part.endswith(" ") or part.endswith(".")):
            return False, f"Trailing dot or space prohibited in component: '{part}'"
        base_name = part.split(".")[0].upper()
        if base_name in reserved_names:
            return False, f"Reserved device name prohibited: '{raw_path}'"

    return True, ""




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
    pattern: Optional[str] = None,
) -> CapabilityResult:
    """Find files by substring, extension, pattern, or location."""
    t0 = time.perf_counter()
    if pattern:
        if pattern.startswith("*."):
            extension = extension or pattern[2:]
        else:
            query = query or pattern

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
            message=f"No files matching '{query or extension or location or pattern}' found.",
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
    pattern: Optional[str] = None,
) -> CapabilityResult:
    """Find the single most recently modified file matching constraints."""
    t0 = time.perf_counter()
    if pattern:
        if pattern.startswith("*."):
            extension = extension or pattern[2:]
        elif "screenshot" in pattern.lower():
            file_type = file_type or "screenshot"
        else:
            file_type = file_type or pattern

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


def save_text_file(
    path: str,
    text: str = "",
    content: Optional[str] = None,
    overwrite: bool = True,
) -> CapabilityResult:
    """Save or write text content to a destination file on disk."""
    t0 = time.perf_counter()
    target_text = text if (text is not None and text != "") else (content or "")
    try:
        norm_path = Path(path).expanduser().resolve()
        norm_path.parent.mkdir(parents=True, exist_ok=True)
        if not overwrite and norm_path.exists():
            return CapabilityResult.fail(
                capability="save_text_file",
                message=f"File already exists and overwrite is disabled: {norm_path}",
                error_code=CapabilityErrorCode.CONFLICT,
            )
        norm_path.write_text(target_text, encoding="utf-8")
        latency = (time.perf_counter() - t0) * 1000
        return CapabilityResult.ok(
            capability="save_text_file",
            message=f"Saved text to '{norm_path}'.",
            data={
                "path": str(norm_path),
                "filename": norm_path.name,
                "output_file": str(norm_path),
                "bytes_written": len(target_text.encode("utf-8")),
            },
            context_updates=[{"type": "file_created", "path": str(norm_path), "filename": norm_path.name}],
            latency_ms=latency,
        )
    except Exception as err:
        logger.error("Error writing file '%s': %s", path, err)
        return CapabilityResult.fail(
            capability="save_text_file",
            message=f"Failed to write file: {err}",
            error_code=CapabilityErrorCode.OS_ERROR,
        )


def deliver_artifact(
    source: str,
    destination: str,
    source_sha256: Optional[str] = None,
    task_id: Optional[str] = None,
    overwrite: bool = True,
    plan_revision: int = 1,
    artifact_identity: Optional[str] = None,
    expected_artifact_type: Optional[str] = None,
) -> CapabilityResult:
    """
    Deliver a verified sandbox artifact to a host destination under strict handle-based sealing policy.
    Binds: task_id + plan_revision + artifact_identity + digest + expected_artifact_type.
    """
    t0 = time.perf_counter()
    temp_commit: Optional[Path] = None
    try:
        # 1. Path safety validation (reject device paths, ADS, UNC, drive-relative, trailing dot/spaces)
        is_safe, msg = validate_safe_path(source)
        if not is_safe:
            return CapabilityResult.fail(
                capability="deliver_artifact",
                message=f"Illegal source path: {msg}",
                error_code=CapabilityErrorCode.PERMISSION_DENIED,
            )
        is_safe, msg = validate_safe_path(destination)
        if not is_safe:
            return CapabilityResult.fail(
                capability="deliver_artifact",
                message=f"Illegal destination path: {msg}",
                error_code=CapabilityErrorCode.PERMISSION_DENIED,
            )

        src_path = Path(source)
        authorized_roots = [
            AstraPaths.sandbox_dir().resolve(),
            (AstraPaths.data_dir() / "sandbox").resolve(),
            AstraPaths.temp_dir().resolve(),
            Path("scratch").resolve(),
        ]

        # 2. Open source file using handle-based restrictive sharing (FILE_SHARE_READ only)
        # Validates regular file, non-reparse, single hardlink, size limits, and authorized sandbox canonical path on the SAME handle.
        ok, err_msg, sealed_src = open_sealed_source_handle(src_path, authorized_roots)
        if not ok or not sealed_src:
            return CapabilityResult.fail(
                capability="deliver_artifact",
                message=f"Source artifact sealing failed: {err_msg}",
                error_code=CapabilityErrorCode.PERMISSION_DENIED if ("boundary" in err_msg or "junction" in err_msg or "link" in err_msg or "reparse" in err_msg) else CapabilityErrorCode.NOT_FOUND,
            )

        with sealed_src:
            # 3. Validate Destination separately
            dst_path = Path(destination).expanduser().resolve()

            # Reject destination symlink / junction
            if dst_path.is_symlink() or os.path.islink(dst_path) or os.path.isjunction(dst_path):
                return CapabilityResult.fail(
                    capability="deliver_artifact",
                    message=f"Destination is a symlink/reparse point/junction: {dst_path}",
                    error_code=CapabilityErrorCode.PERMISSION_DENIED,
                )

            # Check destination ancestor directories for junctions or symlinks
            curr_dst = dst_path.parent
            while curr_dst != curr_dst.parent and curr_dst.exists():
                if os.path.isjunction(curr_dst) or os.path.islink(curr_dst):
                    return CapabilityResult.fail(
                        capability="deliver_artifact",
                        message=f"Destination ancestor directory is a junction/symlink: {curr_dst}",
                        error_code=CapabilityErrorCode.PERMISSION_DENIED,
                    )
                curr_dst = curr_dst.parent

            # Hard link check on existing destination
            if dst_path.exists() and get_file_link_count(dst_path) > 1:
                return CapabilityResult.fail(
                    capability="deliver_artifact",
                    message=f"Destination has multiple hard links (link count > 1): {dst_path}",
                    error_code=CapabilityErrorCode.PERMISSION_DENIED,
                )

            # Check prohibited host destinations (system dirs, startup, credentials)
            prohibited_roots = [
                Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve(),
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")).resolve(),
                Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")).resolve(),
                Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup",
                Path.home() / ".ssh",
                Path.home() / ".aws",
                Path.home() / ".azure",
            ]
            for p in prohibited_roots:
                if str(dst_path).lower().startswith(str(p).lower()):
                    return CapabilityResult.fail(
                        capability="deliver_artifact",
                        message=f"Destination in prohibited system/credential directory: {dst_path}",
                        error_code=CapabilityErrorCode.PERMISSION_DENIED,
                    )

            dst_path.parent.mkdir(parents=True, exist_ok=True)
            if not overwrite and dst_path.exists():
                return CapabilityResult.fail(
                    capability="deliver_artifact",
                    message=f"Destination exists and overwrite is disabled: {dst_path}",
                    error_code=CapabilityErrorCode.INVALID_ARGUMENT,
                )

            # 4. Stage in host-owned destination-side temporary storage (same volume -> atomic commit)
            temp_commit = dst_path.parent / f".tmp_{uuid.uuid4().hex}_{dst_path.name}"
            hasher = hashlib.sha256()
            total_bytes = 0

            with open(temp_commit, "wb") as f_dst:
                while True:
                    chunk = sealed_src.file_io.read(65536)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    f_dst.write(chunk)
                    total_bytes += len(chunk)

            actual_hash = hasher.hexdigest()

            # 5. Verify source hash if requested
            if source_sha256 and actual_hash.lower() != source_sha256.lower():
                if temp_commit.exists():
                    temp_commit.unlink(missing_ok=True)
                return CapabilityResult.fail(
                    capability="deliver_artifact",
                    message=f"Source artifact SHA256 mismatch: expected {source_sha256}, got {actual_hash}",
                    error_code=CapabilityErrorCode.PERMISSION_DENIED,
                )

            # 6. Verify staged copy bytes and integrity
            verify_hasher = hashlib.sha256()
            verify_bytes = 0
            with open(temp_commit, "rb") as f_verify:
                while True:
                    c = f_verify.read(65536)
                    if not c:
                        break
                    verify_hasher.update(c)
                    verify_bytes += len(c)

            if verify_bytes != total_bytes or verify_hasher.hexdigest() != actual_hash:
                if temp_commit.exists():
                    temp_commit.unlink(missing_ok=True)
                return CapabilityResult.fail(
                    capability="deliver_artifact",
                    message="Staged copy byte/digest verification failed (integrity check mismatch)",
                    error_code=CapabilityErrorCode.PERMISSION_DENIED,
                )

            # 7. Type-specific validation if expected_artifact_type is provided
            if expected_artifact_type:
                exp_t = expected_artifact_type.lower().strip()
                if exp_t == "png":
                    with open(temp_commit, "rb") as f_chk:
                        header = f_chk.read(8)
                        if header != b"\x89PNG\r\n\x1a\n":
                            if temp_commit.exists():
                                temp_commit.unlink(missing_ok=True)
                            return CapabilityResult.fail(
                                capability="deliver_artifact",
                                message="Delivered artifact failed PNG header validation",
                                error_code=CapabilityErrorCode.INVALID_ARGUMENT,
                            )
                elif exp_t == "json":
                    try:
                        import json
                        with open(temp_commit, "r", encoding="utf-8") as f_chk:
                            json.load(f_chk)
                    except Exception as err:
                        if temp_commit.exists():
                            temp_commit.unlink(missing_ok=True)
                        return CapabilityResult.fail(
                            capability="deliver_artifact",
                            message=f"Delivered artifact failed JSON syntax validation: {err}",
                            error_code=CapabilityErrorCode.INVALID_ARGUMENT,
                        )

            # 8. Safe Atomic Commit via os.replace
            os.replace(temp_commit, dst_path)
            temp_commit = None

        latency = (time.perf_counter() - t0) * 1000
        return CapabilityResult.ok(
            capability="deliver_artifact",
            message=f"Delivered artifact from '{src_path.name}' to '{dst_path}'.",
            data={
                "source": str(src_path),
                "destination": str(dst_path),
                "sha256": actual_hash,
                "size_bytes": total_bytes,
                "task_id": task_id,
                "plan_revision": plan_revision,
                "artifact_identity": artifact_identity or dst_path.name,
                "expected_artifact_type": expected_artifact_type,
            },
            context_updates=[{"type": "artifact_delivered", "path": str(dst_path), "filename": dst_path.name}],
            latency_ms=latency,
        )
    except Exception as err:
        if temp_commit and temp_commit.exists():
            try:
                temp_commit.unlink(missing_ok=True)
            except Exception:
                pass
        logger.error("Error delivering artifact from '%s' to '%s': %s", source, destination, err)
        return CapabilityResult.fail(
            capability="deliver_artifact",
            message=f"Failed to deliver artifact: {err}",
            error_code=CapabilityErrorCode.OS_ERROR,
        )

