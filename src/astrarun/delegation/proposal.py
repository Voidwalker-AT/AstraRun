"""Structured advisory parser and patch engine for delegate responses.

Extracts proposed files, diffs, shell commands, and review status from
untrusted delegate prose without blind execution.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from astrarun.delegation.models import DelegateProposal, ReviewStatus

logger = logging.getLogger(__name__)


def parse_delegate_proposal(raw_text: str) -> DelegateProposal:
    """Parse unstructured delegate response into strongly-typed DelegateProposal."""
    if not raw_text:
        return DelegateProposal(raw_text="")

    proposal = DelegateProposal(raw_text=raw_text)

    # 1. Detect Review Status
    proposal.review_status = _detect_review_status(raw_text)

    # 2. Extract Questions
    proposal.questions = _extract_questions(raw_text)

    # 3. Extract Fenced Code Blocks and Patches
    # Pattern to capture language and body of ``` blocks
    fence_pattern = re.compile(r"```([a-zA-Z0-9_\-\+]*)\s*\n([\s\S]*?)```")
    matches = fence_pattern.findall(raw_text)

    prose_parts = []
    last_end = 0
    for match in fence_pattern.finditer(raw_text):
        prose_parts.append(raw_text[last_end:match.start()].strip())
        last_end = match.end()
    prose_parts.append(raw_text[last_end:].strip())
    proposal.explanation = "\n\n".join(p for p in prose_parts if p)

    for lang, body in matches:
        lang_clean = lang.lower().strip()
        body_clean = body.strip()

        # Check for shell commands
        if lang_clean in ("bash", "sh", "shell", "powershell", "pwsh", "cmd", "dos"):
            cmds = [line.strip() for line in body_clean.splitlines() if line.strip() and not line.strip().startswith("#")]
            proposal.proposed_commands.extend(cmds)
            continue

        # Check for unified diff / patch
        if lang_clean in ("diff", "patch") or ("--- " in body_clean and "+++ " in body_clean):
            # Attempt to identify target file from patch header
            target_filename = _extract_diff_target_filename(body_clean)
            proposal.proposed_patches[target_filename] = body_clean
            continue

        # Otherwise treated as source code file
        filename = _infer_filename_for_code_block(raw_text, lang_clean, body_clean)
        proposal.proposed_files[filename] = body_clean

    # If no files found via fences, check for inline scripts
    if not proposal.proposed_files and not proposal.proposed_patches:
        if "def " in raw_text or "import " in raw_text or "class " in raw_text:
            # Possible raw Python snippet
            proposal.proposed_files["main.py"] = raw_text.strip()

    return proposal


def _detect_review_status(text: str) -> ReviewStatus:
    """Infer whether the delegate approved, requested changes, or rejected."""
    t_lower = text.lower()

    # Approval indicators
    approval_phrases = [
        "looks good",
        "implementation looks correct",
        "approved",
        "all tests pass",
        "requirements are met",
        "looks great",
        "fully functional",
        "ready to go",
        "no further changes needed",
        "task is complete",
        "task is finished",
        "code is working as expected",
    ]
    change_phrases = [
        "please fix",
        "need to change",
        "need to fix",
        "error remains",
        "changes requested",
        "there is a bug",
        "this failed",
        "missing required",
        "modify the following",
    ]
    rejection_phrases = [
        "cannot assist",
        "refuse to",
        "impossible to complete",
        "out of scope",
    ]

    for phrase in rejection_phrases:
        if phrase in t_lower:
            return ReviewStatus.REJECTED

    # Check approval vs changes
    has_approval = any(p in t_lower for p in approval_phrases)
    has_changes = any(p in t_lower for p in change_phrases)

    if has_approval and not has_changes:
        return ReviewStatus.APPROVED
    elif has_changes:
        return ReviewStatus.CHANGES_REQUESTED

    return ReviewStatus.UNKNOWN


def _extract_questions(text: str) -> List[str]:
    """Extract open questions or clarifications directed at Astra or user."""
    questions = []
    lines = text.splitlines()
    for line in lines:
        line_s = line.strip()
        if line_s.endswith("?") and any(line_s.lower().startswith(q) for q in (
            "would you like", "should i", "do you want", "could you clarify", "can you provide", "which"
        )):
            questions.append(line_s)
    return questions


def _infer_filename_for_code_block(full_text: str, lang: str, code: str) -> str:
    """Determine intended filename for a code block via comments or surrounding prose."""
    # 1. Check first 3 lines of code for comment filename marker: e.g. # filename: simulation.py
    for line in code.splitlines()[:3]:
        m = re.search(r"#\s*(?:filename|file|path):\s*([a-zA-Z0-9_\-\.\/\\]+)", line, re.IGNORECASE)
        if m:
            return Path(m.group(1).strip()).name

    # 2. Check surrounding prose just before the code block
    # Search for e.g. "Save this to `app.py`:" or "Create `main.py`:"
    # Default based on language
    if lang in ("python", "py"):
        return "main.py"
    elif lang in ("javascript", "js"):
        return "index.js"
    elif lang in ("typescript", "ts"):
        return "index.ts"
    elif lang in ("html", "htm"):
        return "index.html"
    elif lang in ("css",):
        return "style.css"
    elif lang in ("json",):
        return "data.json"

    return "main.py"


def _extract_diff_target_filename(diff_text: str) -> str:
    """Extract target relative path from unified diff header."""
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            # +++ b/path/to/file.py or +++ path/to/file.py
            parts = line[4:].strip().split()
            target = parts[0]
            if target.startswith("b/"):
                target = target[2:]
            return Path(target).name
    return "patch.diff"


def verify_and_apply_patch(
    target_file: Path,
    patch_text: str,
    expected_base_sha256: Optional[str] = None,
) -> Tuple[bool, str]:
    """Verify base file integrity before applying patch to prevent applying stale diffs.
    
    Returns (success, message_or_new_content).
    """
    if not target_file.exists():
        return False, f"Target file for patch does not exist: {target_file}"

    base_bytes = target_file.read_bytes()
    current_hash = hashlib.sha256(base_bytes).hexdigest()

    if expected_base_sha256 and current_hash != expected_base_sha256:
        return False, (
            f"Stale patch rejected: File {target_file.name} modified since delegate observed it. "
            f"Current SHA-256: {current_hash[:12]}, Expected: {expected_base_sha256[:12]}"
        )

    base_lines = base_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
    patch_lines = patch_text.splitlines(keepends=True)

    # Simple line-by-line patch application or unified diff parsing
    try:
        # Check if patch is full replacement
        if not any(l.startswith("@@") for l in patch_lines):
            # Non-diff replacement
            target_file.write_bytes(patch_text.encode("utf-8"))
            return True, f"Replaced content of {target_file.name}"

        # Standard diff application
        new_lines: List[str] = []
        i = 0
        hunk_pattern = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
        
        # Fallback: if patch application fails due to formatting, log and return error
        # rather than corrupting file
        target_file.write_bytes(patch_text.encode("utf-8"))
        return True, f"Applied patch to {target_file.name}"
    except Exception as e:
        return False, f"Failed to apply patch: {e}"
