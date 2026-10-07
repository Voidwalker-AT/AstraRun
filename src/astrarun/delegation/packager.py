"""ContextPackager: Sanitization, truncation, and budget-governed context builder.

Enforces zero-secret policy via SecretBroker, prevents terminal spam (e.g. 50k lines),
and formats structured prompts for external AI delegates.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrarun.security.secret_broker import SecretBroker

logger = logging.getLogger(__name__)


class ContextPackager:
    """Sanitizes, truncates, and budgets machine/execution context for external delegates."""

    def __init__(
        self,
        char_budget: int = 14000,
        max_stdout_lines: int = 150,
        secret_broker: Optional[SecretBroker] = None,
    ) -> None:
        self.char_budget = char_budget
        self.max_stdout_lines = max_stdout_lines
        self.secret_broker = secret_broker or SecretBroker.get_instance()

    def scrub(self, text: str) -> str:
        """Apply SecretBroker redactor to eliminate credentials/tokens."""
        scrubbed, _ = self.secret_broker.scrub_text(text)
        return scrubbed

    def format_terminal_output(
        self,
        stdout: str,
        stderr: str,
        raw_log_path: Optional[Path | str] = None,
    ) -> str:
        """Format large stdout/stderr safely without overwhelming delegate context window."""
        lines = stdout.splitlines()
        total_lines = len(lines)

        if total_lines > self.max_stdout_lines:
            head_lines = lines[:50]
            tail_lines = lines[-100:]
            omitted = total_lines - 150
            
            output_hash = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
            log_ref = f" (Full log stored at: {raw_log_path}, SHA256: {output_hash[:12]})" if raw_log_path else f" (SHA256: {output_hash[:12]})"

            truncated_stdout = (
                "\n".join(head_lines)
                + f"\n\n... [{omitted} lines omitted for context budget{log_ref}] ...\n\n"
                + "\n".join(tail_lines)
            )
        else:
            truncated_stdout = stdout

        parts = []
        if truncated_stdout.strip():
            parts.append(f"[STDOUT ({total_lines} lines total)]\n{truncated_stdout.strip()}")
        if stderr.strip():
            err_lines = stderr.splitlines()
            if len(err_lines) > 60:
                truncated_stderr = "\n".join(err_lines[:20]) + f"\n... [{len(err_lines) - 40} lines omitted] ...\n" + "\n".join(err_lines[-20:])
            else:
                truncated_stderr = stderr
            parts.append(f"[STDERR]\n{truncated_stderr.strip()}")

        combined = "\n\n".join(parts)
        return self.scrub(combined)

    def package_initial_objective(
        self,
        objective: str,
        workspace_path: Optional[Path | str] = None,
        existing_files: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
    ) -> str:
        """Package the initial goal and workspace constraints for delegate turn 1."""
        sections = [
            f"[OBJECTIVE]\n{objective.strip()}",
        ]
        if workspace_path:
            sections.append(f"[TARGET WORKSPACE]\n{workspace_path}")
        if existing_files:
            sections.append(f"[EXISTING FILES]\n" + "\n".join(f"- {f}" for f in existing_files[:30]))
        if constraints:
            sections.append("[CONSTRAINTS]\n" + "\n".join(f"- {c}" for c in constraints))

        sections.append(
            "[INSTRUCTIONS]\n"
            "1. Output your complete proposed implementation inside standard markdown code blocks.\n"
            "2. If proposing files, indicate the filename in the first comment line (e.g. `# filename: script.py`).\n"
            "3. If proposing shell commands to run, use ```bash or ```powershell blocks.\n"
            "4. Do not include API keys, passwords, or personal credentials."
        )

        full_text = "\n\n".join(sections)
        return self._enforce_budget(self.scrub(full_text))

    def package_execution_feedback(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        test_summary: Optional[str] = None,
        created_artifacts: Optional[List[str]] = None,
        current_source_files: Optional[Dict[str, str]] = None,
        raw_log_path: Optional[Path | str] = None,
    ) -> str:
        """Package execution results and errors to send back to the same delegate conversation."""
        sections = [
            f"[LOCAL EXECUTION RESULT]\nExit Code: {exit_code}\nStatus: {'SUCCESS' if exit_code == 0 else 'FAILURE'}"
        ]

        if test_summary:
            sections.append(f"[TEST SUMMARY]\n{test_summary.strip()}")

        term_output = self.format_terminal_output(stdout, stderr, raw_log_path=raw_log_path)
        if term_output:
            sections.append(term_output)

        if created_artifacts:
            sections.append("[CREATED ARTIFACTS]\n" + "\n".join(f"- {a}" for a in created_artifacts))

        if exit_code != 0 and current_source_files:
            # Include excerpt of current failing source
            src_sections = []
            for fname, content in list(current_source_files.items())[:3]:
                # Cap each source file to 100 lines if large
                lines = content.splitlines()
                if len(lines) > 100:
                    truncated = "\n".join(lines[:80]) + f"\n# ... [{len(lines)-80} lines omitted]"
                else:
                    truncated = content
                src_sections.append(f"File `{fname}`:\n```python\n{truncated}\n```")
            sections.append("[CURRENT SOURCE CONTEXT]\n" + "\n\n".join(src_sections))

        if exit_code != 0:
            sections.append(
                "[ACTION REQUESTED]\n"
                "The solution did not execute cleanly. Please analyze the error, provide the fix or modified code, "
                "and explain what was changed."
            )
        else:
            sections.append(
                "[ACTION REQUESTED]\n"
                "The program executed cleanly. Please review the output and artifacts, and state 'APPROVED' if complete."
            )

        full_text = "\n\n".join(sections)
        return self._enforce_budget(self.scrub(full_text))

    def package_review_request(
        self,
        objective: str,
        artifacts: List[Dict[str, Any]],
        execution_exit_code: int,
        verification_passed: bool,
    ) -> str:
        """Package final review prompt when local execution has succeeded."""
        sections = [
            f"[OBJECTIVE]\n{objective}",
            f"[LOCAL EMPIRICAL VERIFICATION]\nPassed: {verification_passed}\nExit Code: {execution_exit_code}",
        ]
        art_lines = []
        for a in artifacts:
            name = a.get("name", "unknown")
            size = a.get("size_bytes", 0)
            sha = a.get("sha256", "")[:12]
            art_lines.append(f"- {name} (size: {size} bytes, sha256: {sha})")
        if art_lines:
            sections.append("[VERIFIED ARTIFACTS]\n" + "\n".join(art_lines))

        sections.append(
            "[FINAL REVIEW REQUEST]\n"
            "Local execution and automated verification have succeeded. "
            "Please review the completed artifacts against your recommended design. "
            "If everything looks good, please reply with 'APPROVED'."
        )
        return self._enforce_budget(self.scrub("\n\n".join(sections)))

    def _enforce_budget(self, text: str) -> str:
        """Hard truncate to character budget if exceeded."""
        if len(text) <= self.char_budget:
            return text
        head = text[: int(self.char_budget * 0.4)]
        tail = text[-int(self.char_budget * 0.5) :]
        omitted = len(text) - len(head) - len(tail)
        return f"{head}\n\n... [{omitted} characters omitted for context budget] ...\n\n{tail}"
