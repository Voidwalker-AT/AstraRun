"""WorkspaceIndexer for AstraRun Hybrid RAG.

Provides content-aware AST/symbol chunking (Python, Markdown, JSON, Configs),
incremental change detection via SHA-256 digests, and background indexing
with strict exclusion of build, dependency, and model caches.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set

from astrarun.core.logging import get_logger
from astrarun.rag.embeddings import EmbeddingProvider
from astrarun.rag.models import (
    ChunkMetadata,
    DocType,
    DocumentChunk,
    ProvenanceRecord,
    TrustLevel,
)
from astrarun.rag.store import MemoryStore

logger = get_logger("astrarun.rag.indexer")

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".github",
    ".vscode",
    ".idea",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "cache",
    "outputs",
    "artifacts",
    "AI_Models",
    "AI_Runtimes",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

BINARY_EXTENSIONS = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".gguf",
    ".onnx",
    ".pth",
    ".pt",
    ".h5",
    ".safetensors",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".iso",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".pdf",
    ".pyc",
}


class WorkspaceIndexer:
    """
    Crawls and indexes source code, documentation, and configuration files into MemoryStore.
    """

    def __init__(
        self,
        store: MemoryStore,
        embeddings: EmbeddingProvider,
        excluded_dirs: Optional[Set[str]] = None,
    ):
        self.store = store
        self.embeddings = embeddings
        self.excluded_dirs = excluded_dirs or DEFAULT_EXCLUDED_DIRS

    @staticmethod
    def compute_sha256(content: str | bytes) -> str:
        """Compute SHA-256 digest of file content."""
        if isinstance(content, str):
            content = content.encode("utf-8", errors="replace")
        return hashlib.sha256(content).hexdigest()

    def index_workspace(self, root_path: str | Path, synchronous: bool = True) -> int:
        """
        Recursively index all non-excluded files in the workspace.
        Returns the total number of indexed/updated chunks.
        """
        root = Path(root_path).resolve()
        if not root.exists() or not root.is_dir():
            logger.warning("Workspace root %s does not exist", root_path)
            return 0

        total_chunks = 0
        for file_path in self._walk_files(root):
            try:
                chunks = self.index_file(file_path, synchronous=synchronous)
                total_chunks += chunks
            except Exception as e:
                logger.debug("Failed to index file %s: %s", file_path, e)

        logger.info("Workspace indexing complete for %s. Indexed %d chunks.", root, total_chunks)
        return total_chunks

    def index_file(self, file_path: Path, synchronous: bool = True) -> int:
        """
        Incrementally index a single file if its content has changed.
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return 0

        content_hash = self.compute_sha256(content)
        str_path = str(file_path)

        # Check existing provenance
        prov = self.store.get_provenance(str_path)
        if prov and prov.content_hash == content_hash:
            # File is unchanged; skip
            return 0

        # Delete any previous chunks for this file
        self.store.delete_chunks_by_source(str_path)

        # Parse into typed chunks
        chunks = self.chunk_file(file_path, content, content_hash)
        if not chunks:
            return 0

        # Generate embeddings
        if synchronous:
            texts = [c.content for c in chunks]
            vectors = self.embeddings.embed_batch(texts)
            for c, vec in zip(chunks, vectors):
                c.embedding = vec
                self.store.insert_chunk(c)
        else:
            for c in chunks:
                self.store.insert_chunk(c)

        return len(chunks)

    def chunk_file(self, file_path: Path, content: str, content_hash: str) -> List[DocumentChunk]:
        """Parse file content into structured chunks based on extension."""
        ext = file_path.suffix.lower()
        if ext == ".py":
            return self._chunk_python(file_path, content, content_hash)
        elif ext == ".md":
            return self._chunk_markdown(file_path, content, content_hash)
        elif ext in (".json", ".yaml", ".yml", ".toml"):
            return self._chunk_config(file_path, content, content_hash)
        else:
            return self._chunk_generic_text(file_path, content, content_hash)

    def _chunk_python(self, file_path: Path, content: str, content_hash: str) -> List[DocumentChunk]:
        """AST-based chunker for Python code."""
        chunks: List[DocumentChunk] = []
        str_path = str(file_path)
        lines = content.splitlines()

        try:
            tree = ast.parse(content, filename=str(file_path))
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    start = node.lineno
                    end = getattr(node, "end_lineno", start + 1)
                    node_text = "\n".join(lines[start - 1 : end])
                    sym_type = "class" if isinstance(node, ast.ClassDef) else "function"

                    meta = ChunkMetadata(
                        file_path=str_path,
                        file_name=file_path.name,
                        line_start=start,
                        line_end=end,
                        symbol_name=node.name,
                        symbol_type=sym_type,
                        language="python",
                    )
                    prov = ProvenanceRecord(
                        entity_id="",
                        source_path=str_path,
                        content_hash=content_hash,
                    )
                    chunk = DocumentChunk(
                        content=node_text,
                        doc_type=DocType.CODE,
                        metadata=meta,
                        token_count=max(1, int(len(node_text) / 3.8)),
                        provenance=prov,
                    )
                    prov.entity_id = chunk.id
                    chunks.append(chunk)

            # If no classes or functions found (or module script), chunk whole file
            if not chunks and content.strip():
                return self._chunk_generic_text(file_path, content, content_hash, doc_type=DocType.CODE)
            return chunks
        except SyntaxError:
            # Fallback to text chunker on syntax errors
            return self._chunk_generic_text(file_path, content, content_hash, doc_type=DocType.CODE)

    def _chunk_markdown(self, file_path: Path, content: str, content_hash: str) -> List[DocumentChunk]:
        """Header-based chunker for Markdown documents."""
        chunks: List[DocumentChunk] = []
        str_path = str(file_path)
        lines = content.splitlines()

        current_header = "Intro"
        current_lines: List[str] = []
        start_line = 1

        for idx, line in enumerate(lines, start=1):
            if line.startswith("#"):
                if current_lines:
                    chunk_text = "\n".join(current_lines).strip()
                    if chunk_text:
                        meta = ChunkMetadata(
                            file_path=str_path,
                            file_name=file_path.name,
                            line_start=start_line,
                            line_end=idx - 1,
                            symbol_name=current_header,
                            symbol_type="section",
                            language="markdown",
                        )
                        prov = ProvenanceRecord(
                            entity_id="",
                            source_path=str_path,
                            content_hash=content_hash,
                        )
                        chunk = DocumentChunk(
                            content=chunk_text,
                            doc_type=DocType.MARKDOWN,
                            metadata=meta,
                            token_count=max(1, int(len(chunk_text) / 3.8)),
                            provenance=prov,
                        )
                        prov.entity_id = chunk.id
                        chunks.append(chunk)
                current_header = line.lstrip("#").strip()
                current_lines = [line]
                start_line = idx
            else:
                current_lines.append(line)

        if current_lines:
            chunk_text = "\n".join(current_lines).strip()
            if chunk_text:
                meta = ChunkMetadata(
                    file_path=str_path,
                    file_name=file_path.name,
                    line_start=start_line,
                    line_end=len(lines),
                    symbol_name=current_header,
                    symbol_type="section",
                    language="markdown",
                )
                prov = ProvenanceRecord(
                    entity_id="",
                    source_path=str_path,
                    content_hash=content_hash,
                )
                chunk = DocumentChunk(
                    content=chunk_text,
                    doc_type=DocType.MARKDOWN,
                    metadata=meta,
                    token_count=max(1, int(len(chunk_text) / 3.8)),
                    provenance=prov,
                )
                prov.entity_id = chunk.id
                chunks.append(chunk)

        return chunks

    def _chunk_config(self, file_path: Path, content: str, content_hash: str) -> List[DocumentChunk]:
        """Chunker for JSON and structured configuration files."""
        str_path = str(file_path)
        chunks: List[DocumentChunk] = []

        if file_path.suffix.lower() == ".json":
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    for key, val in data.items():
                        chunk_text = f'"{key}": {json.dumps(val, indent=2)}'
                        meta = ChunkMetadata(
                            file_path=str_path,
                            file_name=file_path.name,
                            symbol_name=str(key),
                            symbol_type="key",
                            language="json",
                        )
                        prov = ProvenanceRecord(
                            entity_id="",
                            source_path=str_path,
                            content_hash=content_hash,
                        )
                        chunk = DocumentChunk(
                            content=chunk_text,
                            doc_type=DocType.JSON,
                            metadata=meta,
                            token_count=max(1, int(len(chunk_text) / 3.8)),
                            provenance=prov,
                        )
                        prov.entity_id = chunk.id
                        chunks.append(chunk)
                    return chunks
            except Exception:
                pass

        return self._chunk_generic_text(file_path, content, content_hash, doc_type=DocType.CONFIG)

    def _chunk_generic_text(
        self,
        file_path: Path,
        content: str,
        content_hash: str,
        doc_type: DocType = DocType.TEXT,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
    ) -> List[DocumentChunk]:
        """Sliding-window chunker for generic text and unstructured content."""
        chunks: List[DocumentChunk] = []
        str_path = str(file_path)
        start = 0
        total_len = len(content)

        while start < total_len:
            end = min(start + chunk_size, total_len)
            chunk_text = content[start:end].strip()
            if chunk_text:
                meta = ChunkMetadata(
                    file_path=str_path,
                    file_name=file_path.name,
                    language=file_path.suffix.lstrip("."),
                )
                prov = ProvenanceRecord(
                    entity_id="",
                    source_path=str_path,
                    content_hash=content_hash,
                )
                chunk = DocumentChunk(
                    content=chunk_text,
                    doc_type=doc_type,
                    metadata=meta,
                    token_count=max(1, int(len(chunk_text) / 3.8)),
                    provenance=prov,
                )
                prov.entity_id = chunk.id
                chunks.append(chunk)
            if end == total_len:
                break
            start += chunk_size - chunk_overlap

        return chunks

    def _walk_files(self, root: Path) -> Generator[Path, None, None]:
        """Traverse directory while pruning excluded paths and binary extensions."""
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune excluded directories in-place
            dirnames[:] = [d for d in dirnames if d not in self.excluded_dirs and not d.startswith(".")]

            for fname in filenames:
                ext = Path(fname).suffix.lower()
                if ext in BINARY_EXTENSIONS or fname.startswith("."):
                    continue
                yield Path(dirpath) / fname
