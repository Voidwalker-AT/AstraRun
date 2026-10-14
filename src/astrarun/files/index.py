"""Bounded file metadata indexing with reparse point safety."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from astrarun.capabilities.models import FileCandidate
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.files.index")

# Windows File Attribute Reparse Point mask
FILE_ATTRIBUTE_REPARSE_POINT = 0x400

# Standard directories to skip during traversal
EXCLUDED_DIR_NAMES = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", ".ruff_cache", "dist", "build", "cache",
    "AppData", "$Recycle.Bin", "System Volume Information"
}

# Standard document extensions
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".txt", ".md", ".csv"}

# Standard source code extensions
SOURCE_CODE_EXTENSIONS = {
    ".py", ".c", ".cpp", ".h", ".hpp", ".java", ".js", ".ts",
    ".jsx", ".tsx", ".json", ".yaml", ".yml", ".rs", ".go", ".cs"
}

# Image extensions
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}


class FileMetadataIndex:
    """
    Lightweight, bounded file metadata index.
    Indexes file paths, names, extensions, sizes, and timestamps without reading file contents.
    """

    def __init__(self, roots: Optional[list[Path | str]] = None, max_depth: int = 4) -> None:
        self.max_depth = max_depth
        self._candidates: list[FileCandidate] = []
        self._last_scan_time: float = 0.0
        self.roots: list[Path] = []

        if roots:
            self.roots = [Path(r).resolve() for r in roots]
        else:
            self._init_default_roots()

    def _init_default_roots(self) -> None:
        """Initialize standard safe user roots."""
        from astrarun.core.paths import AstraPaths
        home = Path.home()
        candidates = [
            AstraPaths.workspace_root(),
            home / "Downloads",
            home / "Documents",
            home / "Desktop",
            home / "Pictures",
        ]
        self.roots = [p.resolve() for p in candidates if p.exists() and p.is_dir()]

    def is_reparse_point(self, path: Path) -> bool:
        """Check if path is a symlink or Windows directory junction."""
        if path.is_symlink():
            return True
        try:
            stat_res = os.lstat(str(path))
            return bool(getattr(stat_res, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)
        except (OSError, ValueError):
            return False

    def scan(self, force: bool = False, max_files_per_root: int = 2000) -> int:
        """
        Scan configured roots for file metadata.
        Avoids traversing directory reparse points or excluded directories.
        """
        now = time.time()
        # Cache scans for at least 30 seconds unless forced
        if not force and (now - self._last_scan_time) < 30.0 and self._candidates:
            return len(self._candidates)

        discovered: list[FileCandidate] = []
        for root in self.roots:
            if not root.exists():
                continue
            root_count = 0
            for current_root, dirs, files in os.walk(str(root)):
                # Prune excluded directories and reparse points in-place
                dirs[:] = [
                    d for d in dirs
                    if d not in EXCLUDED_DIR_NAMES and
                    not self.is_reparse_point(Path(current_root) / d)
                ]

                # Check depth
                try:
                    rel = Path(current_root).relative_to(root)
                    if len(rel.parts) >= self.max_depth:
                        dirs.clear()
                except ValueError:
                    dirs.clear()

                for f in files:
                    if f.startswith("."):
                        continue
                    file_path = Path(current_root) / f
                    try:
                        stat = file_path.stat()
                        ext = file_path.suffix.lower()
                        discovered.append(
                            FileCandidate(
                                path=str(file_path),
                                filename=f,
                                score=1.0,
                                reason="metadata_index",
                                modified_time=stat.st_mtime,
                                size=stat.st_size,
                                extension=ext,
                            )
                        )
                        root_count += 1
                        if root_count >= max_files_per_root:
                            dirs.clear()
                            break
                    except (OSError, PermissionError):
                        continue

        self._candidates = discovered
        self._last_scan_time = time.time()
        logger.info("File metadata scan completed: %d files indexed across %d roots", len(discovered), len(self.roots))
        return len(discovered)

    def search(
        self,
        query: str = "",
        extension: Optional[str] = None,
        location: Optional[str] = None,
        file_type: Optional[str] = None,
        sort_by_newest: bool = False,
        limit: int = 10,
    ) -> list[FileCandidate]:
        """Search the indexed metadata using constraints and substring matching."""
        if not self._candidates:
            self.scan()

        clean_query = query.strip().lower()
        clean_ext = extension.strip().lower() if extension else None
        if clean_ext and not clean_ext.startswith("."):
            clean_ext = f".{clean_ext}"

        clean_loc = location.strip().lower() if location else None

        results: list[FileCandidate] = []
        for c in self._candidates:
            # Extension filter
            if clean_ext and c.extension != clean_ext:
                continue

            # File type category filter
            if file_type == "screenshot":
                is_screenshot = (
                    "screenshot" in c.filename.lower() or
                    "screen shot" in c.filename.lower() or
                    "snip" in c.filename.lower() or
                    "screenshots" in c.path.lower()
                ) and c.extension in IMAGE_EXTENSIONS
                if not is_screenshot:
                    continue
            elif file_type == "document":
                if c.extension not in DOCUMENT_EXTENSIONS:
                    continue
            elif file_type == "code":
                if c.extension not in SOURCE_CODE_EXTENSIONS:
                    continue

            # Location filter
            if clean_loc and clean_loc not in c.path.lower():
                continue

            # Query filter
            score = 1.0
            if clean_query:
                fn_lower = c.filename.lower()
                if clean_query == fn_lower:
                    score = 2.0
                elif fn_lower.startswith(clean_query):
                    score = 1.5
                elif clean_query in fn_lower:
                    score = 1.2
                elif clean_query in c.path.lower():
                    score = 1.0
                else:
                    continue

            candidate_copy = FileCandidate(
                path=c.path,
                filename=c.filename,
                score=score,
                reason=c.reason,
                modified_time=c.modified_time,
                size=c.size,
                extension=c.extension,
            )
            results.append(candidate_copy)

        if sort_by_newest:
            results.sort(key=lambda x: (x.score, x.modified_time), reverse=True)
        else:
            results.sort(key=lambda x: (x.score, x.modified_time), reverse=True)

        return results[:limit]
