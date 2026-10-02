"""Kev shadow router adapter for AstraRun v0.4.

Provides isolated, single-pass non-autoregressive semantic decision-making using
Kev-0.8B (Qwen3.5-0.8B backbone + PEFT LoRA adapter + PointerHead) without granting
production execution authority.
"""

from __future__ import annotations

import math
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from astrarun.core.logging import get_logger
from astrarun.core.models import Decision, RoutingContext
from astrarun.routing.base import BaseRouter

logger = get_logger("astrarun.routing.kev")

# Standard intent taxonomy defined in docs/INTENT_TAXONOMY.md
INTENT_CRITERIA: dict[str, str] = {
    "open_app": "Launch an installed desktop application",
    "open_folder": "Open a local folder in File Explorer",
    "open_url": "Navigate to a website URL",
    "open_project": "Open a software development workspace or project",
    "find_file": "Search for or open an individual document or file",
    "process_action": "Manage, restart, or kill running processes or ports",
    "system_action": "System, hardware, volume, or power actions",
    "ai_query": "Ask a conversational AI or coding question",
    "browser_action": "Search the web or perform in-browser actions",
    "unknown": "Ambiguous, unsupported, or unsafe request"
}

# Only these intents have live execution tools in AstraRun
EXECUTABLE_INTENTS = {"open_app", "open_folder", "open_url"}

# Kev token delimiters (reused Qwen FIM/box tokens)
SPECIAL_TOKENS = ["<|fim_prefix|>", "<|fim_middle|>", "<|box_start|>", "<|box_end|>", "<|fim_suffix|>"]
_SPECIAL_RE = re.compile(r"<\|([A-Za-z0-9_]+)\|>")


@dataclass
class KevDecision:
    """Rich semantic decision output produced by Kev."""
    intent: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)
    is_executable_now: bool = False
    requires_resolution: bool = False
    latency_ms: float = 0.0
    raw_result: dict[str, Any] = field(default_factory=dict)
    source: str = "kev"
    error: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.intent != "unknown" and self.error is None


def _choice_confidence(p: list[float]) -> float:
    """TypeSafe choice confidence formula: (p_max - 1/K) / (1 - 1/K)."""
    k = len(p)
    if k <= 1:
        return 1.0
    p_max = max(p)
    return max(0.0, min(1.0, (p_max - 1.0 / k) / (1.0 - 1.0 / k)))


class KevRouter(BaseRouter):
    """
    Adapter integrating the Kev decision engine behind AstraRun's BaseRouter interface.
    
    Operates strictly in shadow mode. Never executes tools directly.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", True))
        self.mode = str(self.config.get("mode", "shadow")).lower()
        self.model_id = str(self.config.get("model", "jaredpalmer/kev-0.8b"))
        self.base_model_id = str(self.config.get("base_model", "Qwen/Qwen3.5-0.8B-Base"))
        self.device = str(self.config.get("device", "cpu")).lower()
        self.confidence_threshold = float(self.config.get("confidence_threshold", 0.75))
        self.timeout_ms = float(self.config.get("timeout_ms", 5000.0))
        
        # Ensure canonical HF cache location (release vs development)
        from astrarun.core.paths import get_cache_dir, is_release_mode
        hf_cache_dir = str(get_cache_dir() / "huggingface") if is_release_mode() else "E:/AI_Models/HF_CACHE"
        os.environ.setdefault("HF_HOME", hf_cache_dir)
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        
        self._tokenizer = None
        self._model = None
        self._head = None
        self._temperature = 1.0
        self._load_lock = threading.Lock()
        self._load_failed = False
        self._load_error_msg = None

    def _resolve_device(self) -> str:
        if self.device in ("cpu", "cuda"):
            return self.device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def _load_engine(self) -> bool:
        """Thread-safe lazy loader for Kev model components."""
        if not self.enabled:
            return False
        if self._load_failed:
            return False
        if self._model is not None and self._head is not None and self._tokenizer is not None:
            return True

        with self._load_lock:
            if self._model is not None and self._head is not None:
                return True
            if self._load_failed:
                return False

            try:
                import torch
                import torch.nn as nn
                from peft import PeftModel
                from transformers import AutoModelForCausalLM, AutoTokenizer
                from huggingface_hub import snapshot_download

                target_device = self._resolve_device()
                logger.info(
                    "Loading Kev model '%s' (base '%s') on device '%s'...",
                    self.model_id, self.base_model_id, target_device
                )
                t0 = time.perf_counter()

                # Locate or download adapter snapshot
                try:
                    adapter_path = snapshot_download(self.model_id, local_files_only=True)
                except Exception:
                    adapter_path = snapshot_download(self.model_id)

                # Locate or download base snapshot
                try:
                    base_path = snapshot_download(self.base_model_id, local_files_only=True)
                except Exception:
                    base_path = snapshot_download(self.base_model_id)

                # Load tokenizer
                self._tokenizer = AutoTokenizer.from_pretrained(base_path)

                # Load base CausalLM backbone
                base_lm = AutoModelForCausalLM.from_pretrained(
                    base_path,
                    dtype=torch.float32,
                    attn_implementation="eager"
                ).model

                # Attach PEFT LoRA adapter
                peft_model = PeftModel.from_pretrained(base_lm, adapter_path)
                peft_model.eval()
                if target_device != "cpu":
                    peft_model.to(target_device)
                self._model = peft_model

                # Load PointerHead
                head_file = Path(adapter_path) / "head.pt"
                head_data = torch.load(head_file, map_location="cpu", weights_only=False)
                self._temperature = float(head_data.get("temperature", 2.3510958))
                head_dim = int(head_data.get("head_dim", 256))
                hidden_dim = base_lm.config.hidden_size

                class PointerHead(nn.Module):
                    def __init__(self, d: int, dp: int = 256, temp: float = 1.0):
                        super().__init__()
                        self.q = nn.Linear(d, dp)
                        self.k = nn.Linear(d, dp)
                        self.scale = 1.0 / math.sqrt(dp)
                        self.temperature = temp

                    def forward(self, h_decide: torch.Tensor, h_opts: torch.Tensor) -> torch.Tensor:
                        z = (self.k(h_opts) @ self.q(h_decide)) * self.scale
                        return z if self.temperature == 1.0 else z / self.temperature

                head_module = PointerHead(hidden_dim, dp=head_dim, temp=self._temperature)
                head_module.load_state_dict(head_data["head"])
                head_module.eval()
                if target_device != "cpu":
                    head_module.to(target_device)
                self._head = head_module

                load_sec = time.perf_counter() - t0
                logger.info(
                    "Kev model successfully loaded in %.2fs (T=%.4f, device=%s)",
                    load_sec, self._temperature, target_device
                )
                return True

            except ImportError as err:
                self._load_failed = True
                self._load_error_msg = f"Required dependency missing for Kev: {err}"
                logger.warning(self._load_error_msg)
                return False
            except Exception as err:
                self._load_failed = True
                self._load_error_msg = f"Failed to load Kev model: {err}"
                logger.error(self._load_error_msg, exc_info=True)
                return False

    def predict_intent(self, request: str) -> KevDecision:
        """
        Evaluate user request against the 10-class intent taxonomy using Kev.
        
        Returns structured KevDecision preserving full calibrated probability distribution.
        """
        clean_req = request.strip()
        if not clean_req:
            return KevDecision(
                intent="unknown",
                confidence=0.0,
                probabilities={},
                is_executable_now=False,
                requires_resolution=False,
                error="Empty request"
            )

        if not self._load_engine():
            return KevDecision(
                intent="unknown",
                confidence=0.0,
                probabilities={},
                is_executable_now=False,
                requires_resolution=False,
                error=self._load_error_msg or "Kev router disabled or unavailable"
            )

        t0 = time.perf_counter()
        try:
            import torch
            import torch.nn.functional as F

            tok = self._tokenizer
            model = self._model
            head = self._head
            device = next(model.parameters()).device

            # Format input using Kev delimiters
            keys = list(INTENT_CRITERIA.keys())
            options = [f"{k}: {v}" for k, v in INTENT_CRITERIA.items()]
            instr_text = "Which action does the user intend?"

            def user_tokens(text: str) -> list[int]:
                clean_text = _SPECIAL_RE.sub(r"<¦\1¦>", text)
                return tok(clean_text, add_special_tokens=False).input_ids

            state_tokens = user_tokens(clean_req)
            S = [tok.convert_tokens_to_ids(SPECIAL_TOKENS[0])] + state_tokens
            q_id, o_id, c_id, d_id = (tok.convert_tokens_to_ids(t) for t in SPECIAL_TOKENS[1:])
            
            instr = [q_id] + user_tokens(instr_text)
            spans = [[o_id] + user_tokens(o) + [c_id] for o in options]
            br = instr + [t for sp in spans for t in sp] + [d_id]
            
            ids = S + br
            pos = list(range(len(ids)))
            decide_idx = len(ids) - 1
            
            ends = []
            cursor = len(instr)
            for sp in spans:
                cursor += len(sp)
                ends.append(len(S) + cursor - 1)
            opt_idx = ends

            with torch.no_grad():
                input_ids = torch.tensor([ids], device=device)
                position_ids = torch.tensor([pos], device=device)
                out = model(input_ids=input_ids, position_ids=position_ids)
                h = out.last_hidden_state[0]
                h_decide = h[decide_idx]
                h_opts = h[torch.tensor(opt_idx, device=device)]
                logits = head(h_decide, h_opts)
                probs_tensor = F.softmax(logits, dim=-1)
                probs_list = probs_tensor.cpu().tolist()

            latency_ms = (time.perf_counter() - t0) * 1000.0

            probs_dict = {k: round(float(v), 4) for k, v in zip(keys, probs_list)}
            best_idx = int(torch.argmax(probs_tensor).item())
            chosen_intent = keys[best_idx]
            max_prob = float(probs_list[best_idx])
            confidence = round(_choice_confidence(probs_list), 4)

            is_exec = chosen_intent in EXECUTABLE_INTENTS and max_prob >= self.confidence_threshold
            requires_res = chosen_intent in ("open_project", "find_file") or chosen_intent in EXECUTABLE_INTENTS

            return KevDecision(
                intent=chosen_intent,
                confidence=confidence,
                probabilities=probs_dict,
                is_executable_now=is_exec,
                requires_resolution=requires_res,
                latency_ms=latency_ms,
                raw_result={
                    "argmax_prob": max_prob,
                    "choice_confidence": confidence,
                    "temperature": self._temperature,
                    "tokens": len(ids)
                },
                source="kev"
            )

        except Exception as err:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.error("Kev inference error on '%s': %s", clean_req, err, exc_info=True)
            return KevDecision(
                intent="unknown",
                confidence=0.0,
                probabilities={},
                is_executable_now=False,
                requires_resolution=False,
                latency_ms=latency_ms,
                error=str(err),
                source="kev"
            )

    def route(self, request: str, context: RoutingContext) -> Decision:
        """
        Conform to the BaseRouter contract.
        
        Maps KevDecision into AstraRun Decision.
        In shadow mode, this decision is logged/evaluated but NEVER executed.
        """
        kev_dec = self.predict_intent(request)
        
        if not kev_dec.is_resolved:
            return Decision(
                tool="unknown",
                args={},
                confidence=kev_dec.confidence,
                source="kev",
                explanation=f"Kev unresolved: {kev_dec.error or 'unknown intent'}"
            )

        intent = kev_dec.intent
        clean_target = re.sub(r"^(?:open|launch|start|run|show|go to|browse)\s+", "", request.strip(), flags=re.I).strip()

        if intent == "open_app":
            return Decision(
                tool="open_app",
                args={"app": clean_target},
                confidence=kev_dec.confidence,
                source="kev",
                explanation=f"Kev classified intent as open_app (confidence: {kev_dec.confidence:.2f})"
            )
        elif intent == "open_folder":
            return Decision(
                tool="open_folder",
                args={"folder": clean_target},
                confidence=kev_dec.confidence,
                source="kev",
                explanation=f"Kev classified intent as open_folder (confidence: {kev_dec.confidence:.2f})"
            )
        elif intent == "open_url":
            return Decision(
                tool="open_url",
                args={"url": clean_target},
                confidence=kev_dec.confidence,
                source="kev",
                explanation=f"Kev classified intent as open_url (confidence: {kev_dec.confidence:.2f})"
            )
        else:
            return Decision(
                tool="unknown",
                args={"intent": intent, "target": clean_target},
                confidence=kev_dec.confidence,
                source="kev",
                explanation=f"Kev classified intent as future/non-executable '{intent}' (confidence: {kev_dec.confidence:.2f})"
            )
