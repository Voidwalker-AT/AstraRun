"""Quantitative Evaluation Benchmark for AstraRun Milestone 3 Hybrid RAG.

Measures:
  - Recall@1
  - Recall@3
  - MRR (Mean Reciprocal Rank)
  - Latency (p50, p95, mean)
  - Context tokens generated
  - False retrieval rate on negative distractors
"""

from __future__ import annotations

import time
from typing import Any, Dict, List
import numpy as np

from astrarun.cognition.context import ContextBudgetManager
from astrarun.rag.context import ContextBuilder
from astrarun.rag.embeddings import EmbeddingProvider
from astrarun.rag.models import (
    ChunkMetadata,
    DocType,
    DocumentChunk,
    EpisodicTrajectory,
    RetrievalMode,
    RetrievalQuery,
    SkillDefinition,
    TrustLevel,
)
from astrarun.rag.router import RetrievalRouter
from astrarun.rag.skills import SkillRegistry, SkillRetriever
from astrarun.rag.store import MemoryStore

CORPUS_DATA = [
    # Code Chunks
    ("code_auth", "class TokenAuthenticator:\n    def verify_token(self, token: str) -> bool:\n        return token.startswith('sk-')", "src/auth.py", "TokenAuthenticator", DocType.CODE),
    ("code_residency", "class ModelResidencyManager:\n    def handle_eviction(self, pressure: float):\n        # Evicts WARM or ON_DEMAND models when VRAM exceeds 3.2 GB\n        pass", "src/cognition/residency.py", "ModelResidencyManager", DocType.CODE),
    ("code_job_object", "class Win32JobObject:\n    def assign_process(self, pid: int):\n        # Assigns process to Windows Job Object with KILL_ON_JOB_CLOSE\n        pass", "src/execution/job_object.py", "Win32JobObject", DocType.CODE),
    ("code_secret_broker", "class SecretBroker:\n    def scrub_stream(self, text: str) -> str:\n        # Redacts API keys and private tokens from text streams\n        return text", "src/security/secret_broker.py", "SecretBroker", DocType.CODE),
    ("code_action_gate", "class ActionGate:\n    def evaluate_request(self, request: ActionRequest):\n        # Evaluates operations against security policies\n        return verdict", "src/security/action_gate.py", "ActionGate", DocType.CODE),
    ("code_supervisor", "class ModelSupervisor:\n    def spawn_server(self, port: int, model_path: str):\n        # Spawns llama-server.exe with CREATE_NO_WINDOW and Job Object\n        pass", "src/cognition/supervisor.py", "ModelSupervisor", DocType.CODE),
    ("code_router", "class CognitiveRouter:\n    def execute_cognitive_turn(self, query: str):\n        # Cheap-first hierarchy: deterministic -> Spark -> Qwen PlanDAG\n        pass", "src/cognition/router.py", "CognitiveRouter", DocType.CODE),
    ("code_dynamic_runtime", "class DynamicExecutionRuntime:\n    def execute(self, req: ExecutionRequest):\n        # Sandboxed process execution within strict memory quota\n        pass", "src/execution/runtime.py", "DynamicExecutionRuntime", DocType.CODE),

    # Markdown Docs
    ("doc_freeze", "# AstraRun 1.0 Architecture Freeze\nDocuments the approved 8-milestone roadmap, zero-window stealth invariant, and dual residency.", "docs/freeze.md", "Architecture Freeze", DocType.MARKDOWN),
    ("doc_resident_app", "# Resident Windows Desktop Application Specification\nExplains per-user session daemon, single-instance named mutex, and system tray lifecycle.", "docs/resident.md", "Resident App Spec", DocType.MARKDOWN),
    ("doc_benchmark_results", "# Benchmark Results v0.2\nDocuments the 88-query deterministic routing benchmark achieving 100% accuracy and 30.3 µs latency.", "docs/benchmarks.md", "Benchmark Results", DocType.MARKDOWN),
    ("doc_hardware_profile", "# Workstation Profile\nHost CPU: Intel Core i5-12450H | GPU: NVIDIA GeForce RTX 2050 (4 GB VRAM) | RAM: 16 GB.", "docs/hardware.md", "Hardware Profile", DocType.MARKDOWN),
    ("doc_security_model", "# Security & Sandbox Architecture\nActionGate operates as the single authoritative security boundary; LLMs have zero direct authority.", "docs/security.md", "Security Model", DocType.MARKDOWN),

    # JSON & Configs
    ("config_workspace", "{\n  'workspace_root': 'E:\\Workspace\\Active\\AstraRun',\n  'platform': 'Windows 11'\n}", "workspace.json", "Workspace Config", DocType.CONFIG),
    ("config_models", "{\n  'spark': {'port': 8090, 'role': 'FAST'},\n  'qwen': {'port': 8089, 'role': 'DEEP'}\n}", "config/models.json", "Model Settings", DocType.CONFIG),
    ("config_settings", "{\n  'hotkey': 'Alt+Space',\n  'start_with_windows': true\n}", "config/settings.json", "App Settings", DocType.CONFIG),

    # Distractors
    ("distractor_weather", "Tomorrow's weather forecast calls for intermittent rain and 22 degrees Celsius.", "random/weather.txt", "Weather Forecast", DocType.TEXT),
    ("distractor_recipe", "Ingredients: 2 cups flour, 1 tsp baking powder, 1/2 cup sugar, 2 eggs.", "random/recipe.txt", "Pancake Recipe", DocType.TEXT),
    ("distractor_travel", "Flights from Mumbai to Tokyo depart twice daily with connecting layovers.", "random/travel.txt", "Flight Schedule", DocType.TEXT),
]

BENCHMARK_QUERIES = [
    # 1. Exact Identifiers
    {"query": "TokenAuthenticator", "expected_id": "code_auth", "type": "exact_symbol"},
    {"query": "ModelResidencyManager", "expected_id": "code_residency", "type": "exact_symbol"},
    {"query": "workspace.json", "expected_id": "config_workspace", "type": "exact_filename"},
    {"query": "Win32JobObject", "expected_id": "code_job_object", "type": "exact_symbol"},
    {"query": "SecretBroker", "expected_id": "code_secret_broker", "type": "exact_symbol"},

    # 2. Semantic Paraphrases
    {"query": "where are API keys and tokens scrubbed from logs?", "expected_id": "code_secret_broker", "type": "semantic"},
    {"query": "how is process memory limit and parent kill containment enforced?", "expected_id": "code_job_object", "type": "semantic"},
    {"query": "how do models get evicted under VRAM memory pressure?", "expected_id": "code_residency", "type": "semantic"},
    {"query": "single instance named mutex and system tray daemon behavior", "expected_id": "doc_resident_app", "type": "semantic"},
    {"query": "hardware specs for i5 and RTX 2050 workstation", "expected_id": "doc_hardware_profile", "type": "semantic"},

    # 3. Code Navigation
    {"query": "where is the ActionGate authorization logic implemented?", "expected_id": "code_action_gate", "type": "code_nav"},
    {"query": "how are llama-server headless worker processes spawned?", "expected_id": "code_supervisor", "type": "code_nav"},
    {"query": "what manages the cheap-first execution hierarchy?", "expected_id": "code_router", "type": "code_nav"},
    {"query": "sandboxed process execution within strict memory quota", "expected_id": "code_dynamic_runtime", "type": "code_nav"},

    # 4. Config Lookups
    {"query": "ports for spark and qwen models", "expected_id": "config_models", "type": "config"},
    {"query": "default hotkey Alt+Space configuration", "expected_id": "config_settings", "type": "config"},

    # 5. Negative Distractors (expect low scores or no hallucinated top-1 match)
    {"query": "how to bake fluffy pancakes with flour and eggs", "expected_id": "distractor_recipe", "type": "distractor"},
    {"query": "what is the flight schedule to Tokyo?", "expected_id": "distractor_travel", "type": "distractor"},
]


def run_rag_benchmark() -> Dict[str, Any]:
    print("=" * 70)
    print("      ASTRARUN 1.0 MILESTONE 3 HYBRID RAG & RETRIEVAL BENCHMARK")
    print("=" * 70)

    store = MemoryStore(":memory:")
    embeddings = EmbeddingProvider(use_mock=False)
    router = RetrievalRouter(store, embeddings, rrf_k=60)
    builder = ContextBuilder()

    print(f"\n[1/3] Indexing Corpus ({len(CORPUS_DATA)} documents)...")
    t0_index = time.perf_counter()
    for cid, content, path, sym, doc_type in CORPUS_DATA:
        vec = embeddings.embed_text(content)
        chunk = DocumentChunk(
            id=cid,
            content=content,
            doc_type=doc_type,
            metadata=ChunkMetadata(file_path=path, symbol_name=sym),
            embedding=vec,
            token_count=max(1, int(len(content) / 3.8)),
        )
        store.insert_chunk(chunk)
    dt_index = (time.perf_counter() - t0_index) * 1000.0
    print(f"      Corpus indexed in {dt_index:.2f} ms ({dt_index/len(CORPUS_DATA):.2f} ms/doc)")

    print(f"\n[2/3] Executing {len(BENCHMARK_QUERIES)} Test Queries Across All Modalities...")

    latencies_ms: List[float] = []
    top_1_hits = 0
    top_3_hits = 0
    reciprocal_ranks: List[float] = []
    total_context_tokens: List[int] = []
    distractor_false_hits = 0
    distractor_queries = 0

    for item in BENCHMARK_QUERIES:
        q_text = item["query"]
        expected = item["expected_id"]
        q_type = item["type"]

        t0_q = time.perf_counter()
        results = router.retrieve(RetrievalQuery(text=q_text, mode=RetrievalMode.HYBRID, top_k=3))
        dt_q = (time.perf_counter() - t0_q) * 1000.0
        latencies_ms.append(dt_q)

        # Context assembly token measurement
        ctx = builder.build_turn_context(
            system_instruction="You are AstraRun.",
            task_prompt=q_text,
            history_turns=[],
            retrieved_docs=results,
        )
        total_context_tokens.append(ctx["breakdown"].total_input_tokens)

        # Evaluate rank
        ranked_ids = [r.chunk_id for r in results]
        rank = -1
        if expected in ranked_ids:
            rank = ranked_ids.index(expected) + 1

        if rank == 1:
            top_1_hits += 1
            top_3_hits += 1
            reciprocal_ranks.append(1.0)
        elif rank == 2:
            top_3_hits += 1
            reciprocal_ranks.append(0.5)
        elif rank == 3:
            top_3_hits += 1
            reciprocal_ranks.append(1.0 / 3.0)
        else:
            reciprocal_ranks.append(0.0)

        # Check negative distractor handling
        if q_type == "distractor":
            distractor_queries += 1
            # If distractor query returned non-distractor as top-1, that's a false retrieval
            if ranked_ids and ranked_ids[0] != expected:
                distractor_false_hits += 1

    total_q = len(BENCHMARK_QUERIES)
    recall_at_1 = (top_1_hits / total_q) * 100.0
    recall_at_3 = (top_3_hits / total_q) * 100.0
    mrr = float(np.mean(reciprocal_ranks))

    p50_lat = float(np.percentile(latencies_ms, 50))
    p95_lat = float(np.percentile(latencies_ms, 95))
    mean_lat = float(np.mean(latencies_ms))
    mean_tokens = float(np.mean(total_context_tokens))
    false_retrieval_rate = (distractor_false_hits / max(1, distractor_queries)) * 100.0

    print("\n[3/3] Quantitative RAG Evaluation Results:")
    print("-" * 70)
    print(f"  Recall@1 (Top-1 Accuracy) : {recall_at_1:.1f}%")
    print(f"  Recall@3 (Top-3 Accuracy) : {recall_at_3:.1f}%")
    print(f"  Mean Reciprocal Rank (MRR): {mrr:.4f}")
    print(f"  Median Latency (p50)      : {p50_lat:.2f} ms")
    print(f"  95th Percentile (p95)     : {p95_lat:.2f} ms")
    print(f"  Mean Query Latency        : {mean_lat:.2f} ms")
    print(f"  Avg Context Prompt Tokens : {mean_tokens:.1f} tokens")
    print(f"  False Retrieval Rate      : {false_retrieval_rate:.1f}%")
    print("=" * 70)

    return {
        "recall_at_1": recall_at_1,
        "recall_at_3": recall_at_3,
        "mrr": mrr,
        "p50_latency_ms": p50_lat,
        "p95_latency_ms": p95_lat,
        "mean_latency_ms": mean_lat,
        "avg_context_tokens": mean_tokens,
        "false_retrieval_rate": false_retrieval_rate,
    }


if __name__ == "__main__":
    run_rag_benchmark()
