r"""Deterministic mathematical claim verification for AstraRun cognition.

Guarantees:
- Model arithmetic is never blindly trusted.
- Deterministic mathematical claims (especially modular arithmetic, congruences,
  and products) are verified against ground-truth Python arithmetic.
- Erroneous mathematical claims are identified, audited, and corrected with true
  mathematical properties.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.cognition.math_verifier")


@dataclass
class MathClaimVerification:
    """Audit record of a verified or corrected mathematical claim."""
    original_expression: str
    repaired_expression: str
    is_valid: bool
    operation: str
    operands: Dict[str, Any]
    details: str


class MathClaimVerifier:
    @classmethod
    def verify_text(cls, text: str) -> List[MathClaimVerification]:
        """Scan text for claims and return verification list."""
        return cls.verify_and_repair(text)[1]

    @classmethod
    def repair_text(cls, text: str) -> str:
        """Scan text and return mathematically repaired text."""
        return cls.verify_and_repair(text)[0]

    @classmethod
    def verify_and_repair(cls, text: str) -> Tuple[str, List[MathClaimVerification]]:
        r"""
        Scan text for mathematical claims and verify them against ground-truth arithmetic.
        
        Supported patterns:
        1. Modular congruences:
           a * b \equiv c \pmod{m}
           a * b = c (mod m)
           a \cdot b \equiv c \pmod{m}
           a \times b \equiv c \pmod{m}
        2. Direct equations:
           a * b = c
        """
        if not text:
            return text, []

        verifications: List[MathClaimVerification] = []
        modified = text

        # 1. Check modular congruence claims: (a) * (b) =/equiv (c) (mod m)
        mod_pattern = re.compile(
            r"(?P<prefix>(?:for\s+example,?\s*|consider\s+|take\s+)?)"
            r"(?P<a>\d+)\s*"
            r"(?P<op>\*|\\times|\\cdot|x|\u00d7|\u22c5)\s*"
            r"(?P<b>\d+)\s*"
            r"(?P<eq>=|==|\\equiv|\u2261)\s*"
            r"(?P<c>\d+)\s*"
            r"(?P<mod_clause>\\pmod\s*\{?(?P<m1>\d+)\}?|\(?mod\s+(?P<m2>\d+)\)?)",
            re.IGNORECASE,
        )

        for match in list(mod_pattern.finditer(modified)):
            full_str = match.group(0)
            a = int(match.group("a"))
            b = int(match.group("b"))
            claimed_c = int(match.group("c"))
            m = int(match.group("m1") or match.group("m2"))

            actual_c = (a * b) % m
            is_valid = (actual_c == claimed_c)

            if is_valid:
                verifications.append(
                    MathClaimVerification(
                        original_expression=full_str,
                        repaired_expression=full_str,
                        is_valid=True,
                        operation="modular_congruence",
                        operands={"a": a, "b": b, "claimed_c": claimed_c, "mod": m, "actual_c": actual_c},
                        details=f"Verified: ({a} * {b}) % {m} == {claimed_c}",
                    )
                )
                continue

            # Invalid arithmetic detected!
            # e.g., 7 * 11 != 1 (mod 143)
            logger.warning("Detected invalid model arithmetic claim: '%s' -> (%d * %d) %% %d = %d != %d",
                           full_str, a, b, m, actual_c, claimed_c)

            # Check if this was a modular inverse claim (claimed_c == 1)
            true_inv: Optional[int] = None
            gcd = math.gcd(a, m)
            if gcd == 1:
                try:
                    true_inv = pow(a, -1, m)
                except ValueError:
                    pass

            # Formulate mathematically sound replacement using ASCII / LaTeX
            if claimed_c == 1 and true_inv is not None:
                # If m is 143 and true_inv is 41:
                # 7 * 41 = 287 = 1 (mod 143)
                repaired = f"{a} * {true_inv} = {a * true_inv} = 1 (mod {m})"
                # Also adjust surrounding text if it says "Thus 11 is the modular inverse of 7" -> "Thus {true_inv}..."
                inv_statement_pat1 = re.compile(
                    rf"\b{b}\s+is\s+(?:the\s+)?modular\s+inverse\s+of\s+{a}\b",
                    re.IGNORECASE
                )
                inv_statement_pat2 = re.compile(
                    rf"\b(?:the\s+)?modular\s+inverse\s+of\s+{a}\s+is\s+{b}\b",
                    re.IGNORECASE
                )
                modified = inv_statement_pat1.sub(f"{true_inv} is the modular inverse of {a}", modified)
                modified = inv_statement_pat2.sub(f"the modular inverse of {a} is {true_inv}", modified)
            else:
                repaired = f"{a} * {b} = {a * b} = {actual_c} (mod {m})"

            modified = modified.replace(full_str, repaired, 1)

            verifications.append(
                MathClaimVerification(
                    original_expression=full_str,
                    repaired_expression=repaired,
                    is_valid=False,
                    operation="modular_congruence",
                    operands={"a": a, "b": b, "claimed_c": claimed_c, "mod": m, "actual_c": actual_c, "true_inv": true_inv},
                    details=f"Corrected: ({a} * {b}) % {m} = {actual_c} != {claimed_c}. True inverse = {true_inv}.",
                )
            )

        # 2. Check standalone arithmetic product claims: a * b = c (outside mod)
        prod_pattern = re.compile(
            r"\b(?P<a>\d+)\s*(?P<op>\*|\\times|\\cdot|x|\u00d7|\u22c5)\s*(?P<b>\d+)\s*(?P<eq>=|==)\s*(?P<c>\d+)\b"
        )
        for match in list(prod_pattern.finditer(modified)):
            full_str = match.group(0)
            end_pos = match.end()
            trailing = modified[end_pos:end_pos + 15].lower()
            if "mod" in trailing or r"\pmod" in trailing:
                continue

            a = int(match.group("a"))
            b = int(match.group("b"))
            claimed_c = int(match.group("c"))
            actual_c = a * b

            if actual_c != claimed_c:
                repaired = f"{a} * {b} = {actual_c}"
                modified = modified.replace(full_str, repaired, 1)
                verifications.append(
                    MathClaimVerification(
                        original_expression=full_str,
                        repaired_expression=repaired,
                        is_valid=False,
                        operation="multiplication",
                        operands={"a": a, "b": b, "claimed_c": claimed_c, "actual_c": actual_c},
                        details=f"Corrected: {a} * {b} = {actual_c} != {claimed_c}",
                    )
                )

        return modified, verifications
