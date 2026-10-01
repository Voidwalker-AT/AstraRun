"""
Phase 18A: Deterministic Transcript Entity Normalization Layer
Model-independent post-processor for Automatic Speech Recognition (ASR).
Normalizes spoken technical entities, filesystem paths, port numbers,
and developer acronyms into canonical workstation formats.
"""

import re
from typing import Dict, List, Tuple, Set

NORMALIZATION_RULES = [
    # 1. Drive letters and paths
    (r"(?i)\b([a-zA-Z])\s+colon\s+([a-zA-Z0-9_\\]+)", r"\1:\2"),
    (r"(?i)\b([a-zA-Z]):\s*workspace\s*active\s*astrarun\b", r"\1:\\Workspace\\Active\\AstraRun"),
    (r"(?i)\b([a-zA-Z]):\s*workspace\b", r"\1:\\Workspace"),
    (r"(?i)\b([a-zA-Z]):\s*([a-zA-Z0-9_]+)", r"\1:\2"),

    # 2. Developer IDEs and Tools
    (r"(?i)\b(?:v\s*s\s*code|vee\s+ess\s+code)\b", "VS Code"),
    (r"(?i)\b(?:vivaldi)\b", "Vivaldi"),
    (r"(?i)\b(?:py\s*test|pie\s*test)\b", "pytest"),
    (r"(?i)\b(?:git\s+status|get\s+status)\b", "git status"),
    (r"(?i)\b(?:nvidia\s*(?:-|–|\s+)?s\s*m\s*i|nvidia\s*smi)\b", "nvidia-smi"),
    (r"(?i)\b(?:cuda)\b", "CUDA"),

    # 3. Model names & quantizations
    (r"(?i)\b(?:q\s*wen|cue\s*when)\b", "Qwen"),
    (r"(?i)\b(?:spark)\b", "Spark"),
    (r"(?i)\bq\s*(?:four|4)\s*(?:-|–|_|\s+)?k\s*(?:-|–|_|\s+)?(?:m|mike)\b", "Q4_K_M"),
    (r"(?i)\bq\s*(?:five|5)\s*(?:-|–|_|\s+)?k\s*(?:-|–|_|\s+)?(?:m|mike)\b", "Q5_K_M"),

    # 4. Networking & Ports
    (r"(?i)\b(?:campus\s+guest)\b", "Campus Guest"),
    (r"(?i)\bport\s+(?:three\s+thousand|3\s*0\s*0\s*0)\b", "port 3000"),
    (r"(?i)\bport\s+(\d+)\b", r"port \1"),

    # 5. Colloquial commands
    (r"(?i)\bkill\s+whatever\s+is\s+using\b", "kill process on"),
]

def normalize_transcript(raw_text: str) -> str:
    """Applies deterministic regex transformations to clean raw ASR output."""
    text = raw_text.strip()
    for pattern, replacement in NORMALIZATION_RULES:
        text = re.sub(pattern, replacement, text)
    # Clean up excess spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text

def calculate_wer(reference: str, hypothesis: str) -> float:
    """Standard Word Error Rate (Levenshtein distance on words)."""
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()
    d = [[0] * (len(hyp_words) + 1) for _ in range(len(ref_words) + 1)]
    for i in range(len(ref_words) + 1):
        d[i][0] = i
    for j in range(len(hyp_words) + 1):
        d[0][j] = j
    for i in range(1, len(ref_words) + 1):
        for j in range(1, len(hyp_words) + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = min(
                    d[i - 1][j] + 1,      # deletion
                    d[i][j - 1] + 1,      # insertion
                    d[i - 1][j - 1] + 1   # substitution
                )
    if not ref_words:
        return 0.0 if not hyp_words else 100.0
    return round((d[len(ref_words)][len(hyp_words)] / len(ref_words)) * 100.0, 2)

def calculate_intent_preservation(reference_intent: str, hypothesis: str) -> bool:
    """Checks if the core action/intent verb is present."""
    hyp_lower = hypothesis.lower()
    return reference_intent.lower() in hyp_lower

def calculate_entity_preservation(expected_entities: List[str], hypothesis: str) -> Tuple[float, List[str]]:
    """Measures character-exact preservation of critical domain entities."""
    if not expected_entities:
        return 100.0, []
    preserved = []
    missing = []
    for ent in expected_entities:
        if ent.lower() in hypothesis.lower():
            preserved.append(ent)
        else:
            missing.append(ent)
    score = round((len(preserved) / len(expected_entities)) * 100.0, 2)
    return score, missing

def calculate_technical_token_accuracy(expected_tokens: List[str], hypothesis: str) -> float:
    """Precision on developer tokens."""
    if not expected_tokens:
        return 100.0
    found = sum(1 for tok in expected_tokens if tok.lower() in hypothesis.lower())
    return round((found / len(expected_tokens)) * 100.0, 2)
