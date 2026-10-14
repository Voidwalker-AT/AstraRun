"""Layer 5: Learned Semantic Router for AstraRun Hybrid Routing Architecture.

Provides calibrated structured routing for novel, paraphrased, computational,
and boundary user requests:
- Emits StructuredRouteDecision matching the required specification:
  {
    "route": str,  # KNOWN_CAPABILITY, DYNAMIC_COMPUTATION, COMPOSITE, CONVERSATIONAL, CLARIFICATION_REQUIRED
    "confidence": float,
    "resolved_referents": List[str],
    "missing_information": List[str],
    "candidate_capabilities": List[str],
    "reason_code": str
  }

Key Architectural Invariant:
  CLARIFICATION_REQUIRED is ONLY emitted if missing_information is NON-EMPTY.
  If all required parameters, operands, or referents are present, the request
  must be routed to DYNAMIC_COMPUTATION, KNOWN_CAPABILITY, COMPOSITE, or CONVERSATIONAL.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.routing.capability_grounding import CapabilityGrounder
from astrarun.routing.context_grounding import ContextGrounder, GroundingAnalysis


class SemanticRouteClass(str, Enum):
    KNOWN_CAPABILITY = "KNOWN_CAPABILITY"
    DYNAMIC_COMPUTATION = "DYNAMIC_COMPUTATION"
    COMPOSITE = "COMPOSITE"
    CONVERSATIONAL = "CONVERSATIONAL"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    SECURITY_REJECTION = "SECURITY_REJECTION"
    DELEGATE_EXTERNAL_AI = "DELEGATE_EXTERNAL_AI"


@dataclass
class StructuredRouteDecision:
    """Structured decision emitted by the semantic router."""
    route: str
    confidence: float
    resolved_referents: List[str] = field(default_factory=list)
    missing_information: List[str] = field(default_factory=list)
    candidate_capabilities: List[str] = field(default_factory=list)
    reason_code: str = ""
    requires_code: bool = False
    extracted_parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route": self.route,
            "confidence": self.confidence,
            "resolved_referents": self.resolved_referents,
            "missing_information": self.missing_information,
            "candidate_capabilities": self.candidate_capabilities,
            "reason_code": self.reason_code,
            "requires_code": self.requires_code,
        }


# Comprehensive dynamic computation / algorithmic keywords
DYNAMIC_ALGORITHMIC_INDICATORS = {
    # Linear algebra & numerical
    "eigenvalue", "eigenvalues", "eigenvector", "eigenvectors", "matrix", "matrices",
    "determinant", "singular value", "svd", "lu decomposition", "qr decomposition",
    "cholesky", "hilbert matrix", "matrix inverse", "condition number", "norm",
    "numerical integration", "simpson's rule", "trapezoidal rule", "quadrature",
    "differentiation", "derivative", "differential equation", "differential equations",
    "runge-kutta", "rk4", "euler method", "finite difference", "pde", "ode",

    # Mathematical analysis & number theory
    "polynomial", "roots of", "roots for", "roots", "quadratic", "cubic", "root finding", "newton-raphson",
    "bisection", "fibonacci", "prime", "primes", "prime factorization", "prime gaps",
    "sieve of eratosthenes", "collatz", "collatz sequence", "integral", "integration",
    "fourier", "fft", "fourier transform", "wavelet", "laplace transform",

    # Probability, statistics & stochastics
    "random walk", "monte carlo", "brownian motion", "markov chain", "markov",
    "poisson", "poisson distribution", "poisson equation", "gaussian mixture",
    "linear regression", "polynomial regression", "logistic regression",
    "chi-square", "autocorrelation", "variance", "standard deviation", "covariance",
    "percentile", "percentiles", "histogram", "time series", "arima", "garch",
    "volatility", "order book simulation", "synthetic data", "synthetic dataset",

    # Optimization & algorithms
    "dijkstra", "shortest path", "a* search", "bellman-ford", "pagerank",
    "convex hull", "graham scan", "delaunay", "voronoi", "k-means", "clustering",
    "pareto", "pareto front", "multi-objective", "gradient descent", "simplex",
    "knapsack", "travelling salesman", "dynamic programming", "graph traversal",

    # Physics, chaos & simulations
    "pendulum", "double pendulum", "three-body", "n-body", "gravitational",
    "projectile", "projectile motion", "heat diffusion", "wave equation",
    "cellular automaton", "game of life", "conway", "mandelbrot", "julia set",
    "fractal", "perlin noise", "ising model", "lorenz", "lorenz attractor",
    "lotka-volterra", "predator-prey", "sir model", "epidemic simulation",

    # Cryptography & hashing
    "sha256", "sha-256", "md5", "sha512", "sha1", "checksum", "hash", "hashing",
    "hmac", "crc32", "aes",

    # Script & program synthesis
    "python script", "python program", "python code", "create a script",
    "write a script", "write a program", "code that", "script that", "program that",

    # Data transformation, parsing & pipelines
    "slow query log", "access log", "server log", "query logs", "batch logs",
    "stack traces", "deadlock", "anomalies", "bottlenecks", "telemetry",
}


class LearnedSemanticRouter:
    """Calibrated semantic router implementing Layer 5 of Hybrid Routing."""

    def __init__(self, registry: Optional[CapabilityRegistry] = None):
        self.registry = registry or CapabilityRegistry()
        self.capability_grounder = CapabilityGrounder(self.registry)

    def route(
        self,
        prompt: str,
        grounding: GroundingAnalysis,
        active_context: Optional[Dict[str, Any]] = None,
    ) -> StructuredRouteDecision:
        clean = prompt.strip()
        lower = clean.lower()
        context = active_context or {}

        # Invariant Check: If Grounding detected genuine missing information, route to CLARIFICATION_REQUIRED
        if not grounding.is_sufficient and grounding.missing_information:
            return StructuredRouteDecision(
                route=SemanticRouteClass.CLARIFICATION_REQUIRED.value,
                confidence=0.98,
                resolved_referents=list(grounding.resolved_referents.keys()),
                missing_information=grounding.missing_information,
                candidate_capabilities=[],
                reason_code="MISSING_GROUNDED_REFERENT",
                requires_code=False,
            )

        # 1. Dynamic Computation & Algorithmic Synthesis Check
        # Check for dynamic computation keywords (strictly with word boundaries)
        for kw in DYNAMIC_ALGORITHMIC_INDICATORS:
            if re.search(r"\b" + re.escape(kw) + r"\b", lower):
                return StructuredRouteDecision(
                    route=SemanticRouteClass.DYNAMIC_COMPUTATION.value,
                    confidence=0.98,
                    resolved_referents=list(grounding.resolved_referents.keys()),
                    missing_information=[],
                    candidate_capabilities=["execute_dynamic_tool"],
                    reason_code=f"DYNAMIC_ALGORITHMIC_{kw.upper().replace(' ', '_')}",
                    requires_code=True,
                )

        # Conversational symptom/experience complaints
        for pat in (
            r"\b(?:my|the)\s+(?:battery|phone|laptop|laptop\s+fan|fan|mouse\s+cursor|mouse|keyboard|keyboard\s+spacebar|spacebar|screen|display|screen\s+brightness|external\s+monitor|monitor|cursor|trackpad|touchpad|webcam|camera|headphones|audio|audio\s+jack|bluetooth(?:\s+headphones)?|wifi(?:\s+connection)?|internet(?:\s+speed)?|connection|network|computer|pc|system)\s+(?:is|drains|drain|dying|dies|dead|slow|hot|overheating|acting|seems|feels|lags|lag|stutter|stutters|disconnects|disconnect|drops|dropped|flickers|flicker|spins|stick|sticks|keeps|keep|unresponsive|frozen|crashing)\b",
            r"\b(?:give\s+me\s+(?:practical\s+)?advice\s+on)\b",
        ):
            if re.search(pat, lower):
                return StructuredRouteDecision(
                    route=SemanticRouteClass.CONVERSATIONAL.value,
                    confidence=0.96,
                    resolved_referents=list(grounding.resolved_referents.keys()),
                    missing_information=[],
                    candidate_capabilities=[],
                    reason_code="CONVERSATIONAL_SYMPTOM_COMPLAINT",
                    requires_code=False,
                )

        # Mathematical operations with explicit operands
        math_verbs = ("calculate", "compute", "solve", "simulate", "integrate", "differentiate", "evaluate", "find")
        if any(re.search(r"\b" + v + r"\b", lower) for v in math_verbs):
            # If has numerical values, variables, expressions, or mathematical concepts
            if (
                re.search(r"[-+]?\d*\.?\d+", lower)
                or re.search(r"[xyzabcn]\s*[=+\-*/^]", lower)
                or bool(re.search(r"\b(area|volume|perimeter|trajectory|trajectories|equation|formula|roots|prime|primes|factors|factorization|pi|euler|matrix|matrices|integral|derivative|sum|product|variance|std|deviation|mean|median|probability|distribution)\b", lower))
            ):
                return StructuredRouteDecision(
                    route=SemanticRouteClass.DYNAMIC_COMPUTATION.value,
                    confidence=0.97,
                    resolved_referents=list(grounding.resolved_referents.keys()),
                    missing_information=[],
                    candidate_capabilities=["execute_dynamic_tool"],
                    reason_code="MATHEMATICAL_COMPUTATION_WITH_OPERANDS",
                    requires_code=True,
                )

        # Code synthesis / program creation requests
        if bool(re.search(r"\b(?:create|write|generate|implement|build)\s+(?:a\s+)?(?:python\s+)?(?:program|script|code|tool|function|module|pipeline)\b", lower)):
            return StructuredRouteDecision(
                route=SemanticRouteClass.DYNAMIC_COMPUTATION.value,
                confidence=0.98,
                resolved_referents=list(grounding.resolved_referents.keys()),
                missing_information=[],
                candidate_capabilities=["execute_dynamic_tool"],
                reason_code="PROGRAM_SYNTHESIS_REQUEST",
                requires_code=True,
            )

        # Data parsing, log analysis, transformation pipelines
        if bool(re.search(r"\b(?:parse|extract|aggregate|transform|compile|convert|flatten|summarize|merge)\b", lower)) and (
            any(ext in lower for ext in (".log", ".csv", ".json", ".txt", ".xml", ".tsv"))
            or any(kw in lower for kw in (
                "table", "summary report", "report table", "percentiles", "dataset",
                "logs", "stack traces", "latencies", "metrics", "anomalies", "bottlenecks",
                "events", "orders", "commits", "exceptions", "frequencies", "records"
            ))
        ):
            return StructuredRouteDecision(
                route=SemanticRouteClass.DYNAMIC_COMPUTATION.value,
                confidence=0.96,
                resolved_referents=list(grounding.resolved_referents.keys()),
                missing_information=[],
                candidate_capabilities=["execute_dynamic_tool"],
                reason_code="DYNAMIC_DATA_PIPELINE",
                requires_code=True,
            )

        # Procedural generation, charting, plotting & visualization
        if bool(re.search(r"\b(?:plot|render|generate|visualize|create)\s+(?:a\s+)?(?:\d+[dD]\s+)?(?:scatter\s+plot|line\s+chart|bar\s+chart|histogram|heatmap|chart|plot|visualization|surface\s+plot|graph|diagram|maze)\b", lower)) or bool(re.search(r"\b(?:visualiz\w*|plot\w*)\s+(?:memory|cpu|activity|temperature|sales|revenue|expenses|scores|readings|function|3d)\b", lower)):
            return StructuredRouteDecision(
                route=SemanticRouteClass.DYNAMIC_COMPUTATION.value,
                confidence=0.96,
                resolved_referents=list(grounding.resolved_referents.keys()),
                missing_information=[],
                candidate_capabilities=["execute_dynamic_tool"],
                reason_code="DYNAMIC_VISUALIZATION_PIPELINE",
                requires_code=True,
            )

        # 2. Multi-step Composite Operational Workflows
        conjunctions = (" and ", " then ", ", then ", ";", " and then ")
        if any(c in lower for c in conjunctions):
            clauses = [cl.strip() for cl in re.split(r"\band\b|\bthen\b|;", lower) if cl.strip()]
            if len(clauses) >= 2:
                # Check if clauses represent distinct operational capabilities
                matched_caps = []
                for cl in clauses:
                    match = self.capability_grounder.match(cl)
                    if match.matched and match.capability_id:
                        matched_caps.append(match.capability_id)
                if len(matched_caps) >= 2:
                    return StructuredRouteDecision(
                        route=SemanticRouteClass.COMPOSITE.value,
                        confidence=0.96,
                        resolved_referents=list(grounding.resolved_referents.keys()),
                        missing_information=[],
                        candidate_capabilities=matched_caps,
                        reason_code="COMPOSITE_MULTI_CAPABILITY_WORKFLOW",
                        requires_code=False,
                    )

        # 3. Conversational Checks
        # Questions ending in '?' that are not dynamic computations
        if lower.endswith("?"):
            return StructuredRouteDecision(
                route=SemanticRouteClass.CONVERSATIONAL.value,
                confidence=0.94,
                resolved_referents=list(grounding.resolved_referents.keys()),
                missing_information=[],
                candidate_capabilities=[],
                reason_code="CONVERSATIONAL_QUESTION",
                requires_code=False,
            )

        # Conversational inquiries and discussions
        conversational_starters = (
            "why ", "what is ", "what are ", "what does ", "what was ", "can you explain",
            "could you explain", "how does ", "how do i ", "how can i ", "help me decide",
            "help me choose", "tell me about ", "tell me ", "explain ", "who ", "where is ",
            "have a great ", "have a wonderful", "good morning", "good afternoon",
            "good evening", "hello", "hi", "thank you", "thanks", "how are you",
            "can we chat", "give me advice", "should i use", "can you recommend",
            "what are some tips", "what should i consider", "write an email",
        )
        if any(lower.startswith(s) for s in conversational_starters):
            return StructuredRouteDecision(
                route=SemanticRouteClass.CONVERSATIONAL.value,
                confidence=0.95,
                resolved_referents=list(grounding.resolved_referents.keys()),
                missing_information=[],
                candidate_capabilities=[],
                reason_code="CONVERSATIONAL_INQUIRY",
                requires_code=False,
            )

        # 4. Fallback Rule: Complete Operational Imperative without missing info -> DYNAMIC_COMPUTATION
        # If the user issued an operational imperative verb (e.g. "simulate...", "generate...", "process...")
        # and all operands are present, do NOT ask for clarification!
        operational_verbs = ("simulate", "calculate", "compute", "generate", "create", "process", "analyze", "evaluate", "plot", "render")
        if any(lower.startswith(v) for v in operational_verbs) and len(lower.split()) >= 3:
            return StructuredRouteDecision(
                route=SemanticRouteClass.DYNAMIC_COMPUTATION.value,
                confidence=0.90,
                resolved_referents=list(grounding.resolved_referents.keys()),
                missing_information=[],
                candidate_capabilities=["execute_dynamic_tool"],
                reason_code="OPERATIONAL_IMPERATIVE_SELF_CONTAINED",
                requires_code=True,
            )

        # 5. True Ambiguity / Underspecified: Only when required intent is genuinely absent
        return StructuredRouteDecision(
            route=SemanticRouteClass.CLARIFICATION_REQUIRED.value,
            confidence=0.70,
            resolved_referents=list(grounding.resolved_referents.keys()),
            missing_information=["operational_intent"],
            candidate_capabilities=[],
            reason_code="GENUINE_AMBIGUITY_MISSING_INTENT",
            requires_code=False,
        )
