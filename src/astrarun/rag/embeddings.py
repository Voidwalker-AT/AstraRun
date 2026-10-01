"""Local CPU embedding provider for AstraRun Hybrid RAG.

Utilizes BGE-small-EN-v1.5 via ONNX Runtime (CPUExecutionProvider) with
zero GPU VRAM allocation (~5ms latency on host CPU). Includes deterministic
fallback generation for offline/CI test environments.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import List, Optional
import numpy as np

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.rag.embeddings")

DEFAULT_MODEL_DIR = Path(r"E:\AI_Models\ONNX\bge-small-en-v1.5")


class EmbeddingProvider:
    """
    Computes 384-dimensional dense vector embeddings using local CPU inference.
    Guarantees 0.0 MB GPU VRAM consumption.
    """

    def __init__(
        self,
        model_dir: Optional[str | Path] = None,
        use_mock: bool = False,
    ):
        self.dimension: int = 384
        self._use_mock: bool = use_mock
        self._session = None
        self._tokenizer = None

        if not self._use_mock:
            self._init_onnx_runtime(model_dir)

    def _init_onnx_runtime(self, model_dir: Optional[str | Path]) -> None:
        """Attempt to locate and load the ONNX model and tokenizer."""
        # 1. Check passed model_dir
        # 2. Check environment variable
        # 3. Check default canonical path
        candidates = []
        if model_dir:
            candidates.append(Path(model_dir))
        env_dir = os.environ.get("ASTRARUN_EMBEDDING_DIR")
        if env_dir:
            candidates.append(Path(env_dir))
        candidates.append(DEFAULT_MODEL_DIR)

        resolved_dir: Optional[Path] = None
        for candidate in candidates:
            if (candidate / "model.onnx").exists() and (candidate / "tokenizer.json").exists():
                resolved_dir = candidate
                break

        if not resolved_dir:
            logger.warning(
                "BGE-small ONNX model not found in candidates (%s). Activating deterministic fallback generator.",
                [str(c) for c in candidates],
            )
            self._use_mock = True
            return

        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            model_path = str(resolved_dir / "model.onnx")
            tokenizer_path = str(resolved_dir / "tokenizer.json")

            # Configure thread pool for CPU execution to remain polite
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 2
            opts.inter_op_num_threads = 1
            opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

            self._tokenizer = Tokenizer.from_file(tokenizer_path)
            self._session = ort.InferenceSession(
                model_path,
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            logger.info("Initialized BGE-small ONNX embedding provider from %s", resolved_dir)
        except Exception as e:
            logger.warning(
                "Failed to initialize ONNX runtime (%s). Falling back to deterministic embedding generator.",
                e,
            )
            self._use_mock = True

    def embed_text(self, text: str) -> List[float]:
        """Compute normalized dense embedding for a single text string."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Compute normalized dense embeddings for a batch of text strings."""
        if not texts:
            return []

        if self._use_mock or self._session is None or self._tokenizer is None:
            return [self._generate_deterministic_vector(t) for t in texts]

        try:
            results: List[List[float]] = []
            for text in texts:
                # BGE recommendation: query prefix optional, represent text directly
                inputs = self._tokenizer.encode(text)
                input_ids = np.array([inputs.ids], dtype=np.int64)
                attention_mask = np.array([inputs.attention_mask], dtype=np.int64)
                token_type_ids = np.array([inputs.type_ids], dtype=np.int64)

                ort_inputs = {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                    "token_type_ids": token_type_ids,
                }
                outputs = self._session.run(None, ort_inputs)
                # CLS token embedding
                cls_embedding = outputs[0][0, 0, :].astype(np.float32)
                norm = float(np.linalg.norm(cls_embedding))
                if norm > 1e-12:
                    cls_embedding = cls_embedding / norm
                results.append(cls_embedding.tolist())
            return results
        except Exception as e:
            logger.error("Error during ONNX embedding inference: %s; using deterministic fallback", e)
            return [self._generate_deterministic_vector(t) for t in texts]

    def _generate_deterministic_vector(self, text: str) -> List[float]:
        """
        Deterministic pseudo-semantic vector generator for offline / CI environments.
        Computes stable hash projections that preserve identical-string equality
        and basic term-overlap cosine similarity without weights.
        """
        vec = np.zeros(self.dimension, dtype=np.float32)
        words = text.lower().split()
        if not words:
            vec[0] = 1.0
            return vec.tolist()

        for word in words:
            h = hashlib.sha256(word.encode("utf-8")).digest()
            # Map hash to dimensions
            for i in range(0, 16, 2):
                idx = int.from_bytes(h[i : i + 2], "little") % self.dimension
                val = (h[i] - 128) / 128.0
                vec[idx] += val

        norm = float(np.linalg.norm(vec))
        if norm > 1e-12:
            vec = vec / norm
        else:
            vec[0] = 1.0
        return vec.tolist()
