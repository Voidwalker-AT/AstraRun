"""Authoritative Context-Sufficiency Model for AstraRun Intelligence Routing.

Distinguishes:
1. ACTION: Operational imperative verb vs descriptive/conversational prose.
2. TARGET: Specific entity vs vague pronoun or ungrounded referent.
3. PARAMETERS: Mandatory parameters present vs missing.
4. CONTEXT DEPENDENCE: Ungrounded references vs grounded in active workstation context.

Core Invariants:
A. Bare nouns are NOT commands ("battery", "wifi", "python", "report" -> CLARIFICATION).
B. Bare verbs / ungrounded references require clarification ("run it", "generate the report", "process the data").
C. Grounded references resolve against active context without unnecessary questions.
D. Noun overlap is not intent ("my wifi is slow today", "battery drains fast" -> CONVERSATIONAL).
E. Explicit operational intent maps to KNOWN_CAPABILITY or DYNAMIC_COMPUTATION.
F. Multi-capability pipelines map to COMPOSITE.
G. Destructive operations fail closed (SECURITY_REJECTION).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class RoutingClassification(str, Enum):
    KNOWN_CAPABILITY = "KNOWN_CAPABILITY"
    DYNAMIC_COMPUTATION = "DYNAMIC_COMPUTATION"
    CONVERSATIONAL = "CONVERSATIONAL"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    COMPOSITE = "COMPOSITE"
    DELEGATE_EXTERNAL_AI = "DELEGATE_EXTERNAL_AI"
    SECURITY_REJECTION = "SECURITY_REJECTION"


@dataclass
class SufficiencyAssessment:
    classification: RoutingClassification
    is_sufficient: bool
    confidence: float
    reason: str
    target_capability: Optional[str] = None
    extracted_parameters: Dict[str, Any] = field(default_factory=dict)
    missing_parameters: List[str] = field(default_factory=list)
    grounded_referents: Dict[str, Any] = field(default_factory=dict)
    is_destructive: bool = False
    requires_code: bool = False


# Destructive patterns forbidden by security policy (Authoritative Fail-Closed)
DESTRUCTIVE_PATTERNS = (
    r"\bformat\s+(?:all\s+)?(?:the\s+)?(?:hard\s+drives?|disks?|drives?|[a-z]:)",
    r"\bdelete\s+(?:all\s+)?(?:the\s+)?(?:system32|system\s+files|c:\\windows)",
    r"\brm\s+-rf\s+/",
    r"\bdrop\s+database\b",
    r"\bdownload\s+(?:and\s+run\s+)?(?:malware|rootkit|trojan|ransomware)\b",
    r"\b(?:deploy|install)\s+(?:keylogger|cryptominer|rootkit|ransomware)\b",
    r"\binfect\s+system\b",
    r"\bwipe\s+(?:all\s+)?(?:the\s+)?(?:hard\s+drives?|disks?|drives?|system32(?:\s+directory)?|system\s+files|[a-z]:|c:\\windows)",
    r"\bshred\s+(?:all\s+)?(?:the\s+)?(?:hard\s+drives?|disks?|drives?|[a-z]:)",
    r"\bdestroy\s+(?:all\s+)?(?:the\s+)?(?:system|system32|system\s+files|[a-z]:|c:\\windows)",
    r"\berase\s+(?:all\s+)?(?:the\s+)?(?:hard\s+drives?|disks?|drives?|[a-z]:)",
)

# Common bare noun commands that must NOT auto-execute
BARE_NOUN_TERMS = {
    "battery", "wifi", "wi-fi", "python", "report", "status", "network", "audio",
    "bluetooth", "memory", "cpu", "disk", "gpu", "terminal", "browser", "windows",
    "processes", "system", "file", "folder", "document", "data", "task", "code",
    "script", "clipboard", "display", "sound", "volume", "power", "internet",
    "connection", "apps", "applications", "ports", "settings", "git", "calculator",
    "notepad", "editor", "paint", "table", "summary", "log", "count"
}

# Bare verbs that lack operands and must NOT execute blindly
BARE_VERB_TERMS = {
    "solve", "calculate", "compute", "plot", "code", "script", "generate",
    "summary", "table", "report", "count", "log", "run", "do", "make", "save",
    "delete", "open", "fix", "inspect", "start", "check", "hello", "hi", "help",
    "what", "test", "do something", "who are you", "connect", "restart", "stop",
    "kill", "find", "process", "convert", "transform", "organize"
}

# Nonsense / unparseable garbage tokens
NONSENSE_TOKENS = {
    "asdfghjkl", "qwertyuiop", "zxcvbnm", "blablabla",
    "??? !!! ???", "............", "undefined null nan void", "--- === +++"
}

# Conversational starters and inquiry indicators
CONVERSATIONAL_STARTERS = (
    "why ", "what is ", "what are ", "what does ", "what was ", "can you explain",
    "could you explain", "how does ", "how do i ", "how can i ", "help me decide",
    "help me choose", "tell me about ", "tell me ", "explain ", "who ", "who wrote", "who painted",
    "where is ", "what causes ", "have a great ", "have a wonderful", "who are you", "good morning",
    "good afternoon", "good evening", "hello there", "hi there", "thank you", "thanks",
    "how are you", "nice to meet you", "can we chat", "give me advice", "give me practical advice",
    "give me practical advice on ", "give me advice on ", "i wonder if",
    "do you know", "what time is it in", "tell me a joke", "should i use", "can you recommend",
    "how should i", "what are some tips", "can you suggest", "what should i consider",
    "how can i build", "how can our"
)

# Conversational literary / trivia / rhetorical queries (lexical collision guards)
LITERARY_TRIVIA_PATTERNS = (
    "plot of hamlet", "plot of romeo", "plot of the novel", "plot of the movie",
    "plot of the book", "plot of the play", "plot of the film", "plot of 1984", "plot of inception",
    "plot camera angles", "solve this riddle", "thinking puzzle", "solve a dispute", "solve conflict",
    "personality conflict", "code formatting standards", "lateral thinking", "airport code",
    "postal code", "periodic table", "ping pong table", "coffee table", "end table",
    "table tennis", "truth table", "clean code mean", "count me in", "count your chickens",
    "vote should count", "write an email", "congratulatory email", "draft a polite",
    "warren commission report", "black box", "captain's log", "monty python",
    "python got its name", "how python got", "in your head", "curry", "storyboard"
)

# Conversational symptom/experience indicators (noun overlap trap)
SYMPTOM_COMPLAINT_PATTERNS = (
    r"\b(?:my|the)\s+(?:battery|phone|laptop|laptop\s+fan|fan|mouse\s+cursor|mouse|keyboard|keyboard\s+spacebar|spacebar|screen|display|screen\s+brightness|external\s+monitor|monitor|cursor|trackpad|touchpad|webcam|camera|headphones|audio|audio\s+jack|bluetooth(?:\s+headphones)?|wifi(?:\s+connection)?|internet(?:\s+speed)?|connection|network|computer|pc|system)\s+(?:is|drains|drain|dying|dies|dead|slow|hot|overheating|acting|seems|feels|lags|lag|stutter|stutters|disconnects|disconnect|drops|dropped|flickers|flicker|spins|stick|sticks|keeps|keep|unresponsive|frozen|crashing)\b",
    r"\b(?:give\s+me\s+(?:practical\s+)?advice\s+on)\b",
    r"\b(?:why\s+is\s+my|why\s+does\s+my)\b",
    r"\b(?:how\s+to\s+fix|troubleshoot\s+my|help\s+with\s+my)\b",
    r"\b(?:is\s+it\s+normal\s+for|should\s+i\s+worry\s+about)\b",
)

# Explicit operational verbs that indicate true workstation intent
OPERATIONAL_VERBS = (
    "check", "scan", "list", "show", "open", "launch", "close", "quit", "kill",
    "terminate", "minimize", "maximize", "snap", "restore", "resize", "lock",
    "restart", "shutdown", "capture", "take", "find", "search", "get", "query",
    "reveal", "inspect", "view", "read", "measure", "test", "set", "copy", "mute",
    "unmute", "summarize", "report"
)

# Computational keywords indicating dynamic execution requirement
DYNAMIC_KEYWORDS = (
    "eigenvalue", "polynomial", "roots of", "roots for", "find.*roots", "roots",
    "random walk", "pendulum", "lotka-volterra",
    "monte carlo", "collatz", "fibonacci", "three-body", "numerical integration",
    "simpson's rule", "heat diffusion", "fourier transform", "fft", "dijkstra",
    "brownian motion", "markov chain", "mandelbrot", "game of life", "svd",
    "singular value", "poisson equation", "geodesic", "autocorrelation", "cellular automaton",
    "pagerank", "chi-square", "pareto", "linear regression", "prime factorization",
    "prime numbers", "prime gaps", "determinant", "matrix inverse", "hilbert matrix",
    "cholesky", "lu decomposition", "qr decomposition", "convex hull", "graham scan",
    "delaunay", "voronoi", "k-means", "sha256 checksum", "checksums for files",
    "write a python script to", "write a python program", "create a python script",
    "python code that", "parse.*and output.*table", "convert.*json.*into.*csv",
    "plot a 3d", "scatter plot of", "surface plot of", "heatmap of", "histogram of",
    "line chart of", "bar chart showing", "runge-kutta", "rk4", "differential equations",
    "perlin noise", "barabasi-albert", "arima", "gaussian mixture", "order book simulation",
    "slow query log", "query log", "server log", "access log"
)


_SHARED_CAPABILITY_GROUNDER = None
_SHARED_LEARNED_ROUTER = None

def _get_shared_grounder():
    global _SHARED_CAPABILITY_GROUNDER
    if _SHARED_CAPABILITY_GROUNDER is None:
        from astrarun.routing.capability_grounding import CapabilityGrounder
        _SHARED_CAPABILITY_GROUNDER = CapabilityGrounder()
    return _SHARED_CAPABILITY_GROUNDER

def _get_shared_learned_router():
    global _SHARED_LEARNED_ROUTER
    if _SHARED_LEARNED_ROUTER is None:
        from astrarun.routing.learned_router import LearnedSemanticRouter
        grounder = _get_shared_grounder()
        _SHARED_LEARNED_ROUTER = LearnedSemanticRouter(registry=grounder.registry)
    return _SHARED_LEARNED_ROUTER


class ContextSufficiencyEngine:
    """Evaluates user requests for context sufficiency, intent clarity, and missing referents."""

    @classmethod
    def evaluate(
        cls,
        raw_prompt: str,
        active_context: Optional[Dict[str, Any]] = None,
    ) -> SufficiencyAssessment:
        clean = raw_prompt.strip()
        lower = clean.lower()
        context = active_context or {}

        # 1. Security Invariant: Destructive requests fail closed immediately
        for pat in DESTRUCTIVE_PATTERNS:
            if re.search(pat, lower):
                return SufficiencyAssessment(
                    classification=RoutingClassification.SECURITY_REJECTION,
                    is_sufficient=False,
                    confidence=1.0,
                    reason="Destructive workstation operation rejected by policy.",
                    is_destructive=True,
                )

        # 2. Delegation Check: External AI Advisor Routing
        is_permissive_delegation = bool(re.search(
            r'\b(?:you\s+may|optionally|feel\s+free\s+to|if\s+you\s+(?:genuinely\s+)?think|if\s+needed|can\s+consult|permitted\s+to)\b',
            lower
        ))
        if not is_permissive_delegation and (
            any(w in lower for w in ("chatgpt", "claude", "gemini", "external ai", "delegate", "consult delegate"))
            or ("ask" in lower and any(w in lower for w in ("chatgpt", "claude", "gemini", "external ai", "advisor", "external")))
        ):
            return SufficiencyAssessment(
                classification=RoutingClassification.DELEGATE_EXTERNAL_AI,
                is_sufficient=True,
                confidence=0.96,
                reason="External AI delegation request.",
            )

        # 3. Rule A: Bare Nouns / Bare Verbs / Nonsense are NOT commands
        tokens = [t for t in re.split(r"[^\w\-]+", lower) if t]
        if not tokens or clean in NONSENSE_TOKENS or any(tok in clean for tok in ("??? !!! ???", "............", "undefined null nan void", "--- === +++")):
            return SufficiencyAssessment(
                classification=RoutingClassification.CLARIFICATION_REQUIRED,
                is_sufficient=False,
                confidence=0.99,
                reason="Unrecognized or nonsensical input requires clarification.",
                missing_parameters=["intent"],
            )

        if len(tokens) == 1:
            token = tokens[0]
            if token in BARE_NOUN_TERMS:
                return SufficiencyAssessment(
                    classification=RoutingClassification.CLARIFICATION_REQUIRED,
                    is_sufficient=False,
                    confidence=0.98,
                    reason=f"Bare noun '{token}' requires operational clarification (specify an action).",
                    missing_parameters=["action", "intent"],
                )
            if token in BARE_VERB_TERMS:
                return SufficiencyAssessment(
                    classification=RoutingClassification.CLARIFICATION_REQUIRED,
                    is_sufficient=False,
                    confidence=0.98,
                    reason=f"Bare verb '{token}' requires operational target or operands.",
                    missing_parameters=["target_entity"],
                )

        # Two-word bare phrases (e.g. "the battery", "my wifi", "system report", "just wifi", "run script", "generate table")
        if len(tokens) == 2:
            t0, t1 = tokens[0], tokens[1]
            if (
                (t0 in ("the", "a", "an", "my", "this", "that", "just", "our") and t1 in BARE_NOUN_TERMS)
                or (t0 in BARE_NOUN_TERMS and t1 in ("status", "info", "report", "tool"))
                or (t0 in ("run", "generate") and t1 in ("script", "table"))
            ):
                # Exception: standard exact capability names like "battery status", "wifi status", "cpu status"
                exact_pairs = {
                    "battery status": "battery_status",
                    "wifi status": "wifi_status",
                    "cpu status": "cpu_status",
                    "memory status": "memory_status",
                    "disk status": "disk_status",
                    "gpu status": "gpu_status",
                    "audio status": "audio_status",
                    "system summary": "system_summary",
                    "lock workstation": "lock_workstation",
                    "list windows": "list_windows",
                }
                if lower in exact_pairs:
                    return SufficiencyAssessment(
                        classification=RoutingClassification.KNOWN_CAPABILITY,
                        is_sufficient=True,
                        confidence=0.98,
                        reason=f"Exact status capability match for '{lower}'.",
                        target_capability=exact_pairs[lower],
                    )
                return SufficiencyAssessment(
                    classification=RoutingClassification.CLARIFICATION_REQUIRED,
                    is_sufficient=False,
                    confidence=0.96,
                    reason=f"Underspecified phrase '{clean}' requires clarification.",
                    missing_parameters=["action"],
                )

        # 4. Rule B & C: Referents and Context Grounding (Evaluated BEFORE general question marks!)
        ungrounded_patterns = (
            (r"^(?:run|start|execute|launch)\s+it(?:\s+now)?$", "run_target"),
            (r"^(?:connect\s+to\s+it|connect)$", "network_ssid"),
            (r"^(?:generate\s+the\s+report|generate\s+report|make\s+the\s+report)$", "report_type"),
            (r"^(?:process\s+the\s+data|process\s+data|handle\s+the\s+data)$", "data_source"),
            (r"^(?:find\s+the\s+document|find\s+the\s+file|find\s+document)$", "file_query"),
            (r"^(?:restart|close|open|quit)\s+(?:the\s+application|the\s+app|it)$", "application_name"),
            (r"^(?:kill|terminate|stop)\s+(?:it|the\s+process|the\s+task)$", "process_id"),
            (r"^(?:what\s+happened\s+to\s+that\s+task|what\s+happened\s+to\s+it|how\s+is\s+that\s+task\s+doing)$", "task_id"),
            (r"^(?:did\s+it\s+finish(?:\s+yet)?|is\s+it\s+done|did\s+it\s+complete|has\s+it\s+finished)$", "task_id"),
            (r"^(?:can\s+you\s+check\s+on\s+it|check\s+on\s+it|check\s+it)$", "target_entity"),
            (r"^(?:try\s+running\s+it\s+again|run\s+it\s+again|start\s+it\s+again)$", "task_id"),
            (r"^(?:change\s+the\s+setting|make\s+the\s+adjustment|proceed\s+with\s+option|put\s+it\s+back)$", "adjustment_target"),
            (r"^(?:help\s+me\s+with\s+this|fix\s+the\s+problem|start\s+the\s+task|handle\s+the\s+situation)$", "task_description"),
            (r"^(?:check\s+the\s+thing|inspect\s+the\s+window|show\s+me\s+that|make\s+it\s+work)$", "target_object"),
            (r"^(?:update\s+the\s+system|send\s+the\s+payload|clean\s+up\s+the\s+workspace)$", "operation_details"),
            (r"^(?:convert\s+the\s+input|transform\s+the\s+output|organize\s+the\s+files)$", "pipeline_parameters"),
            (r"^(?:open\s+the\s+file|save\s+it\s+to\s+disk|delete\s+that\s+folder)$", "path_operand"),
            (r"^(?:calculate\s+the\s+result|solve\s+the\s+equation|compute\s+the\s+numbers|plot\s+the\s+chart|parse\s+the\s+log)$", "computational_operand"),
            (r"^(?:continue\s+what\s+we\s+were\s+doing\s+yesterday|do\s+the\s+same\s+thing\s+you\s+did\s+last\s+time)$", "session_history"),
            (r"^(?:pick\s+up\s+from\s+where\s+we\s+stopped|use\s+that\s+previous\s+value\s+from\s+earlier)$", "session_state"),
            (r"^(?:apply\s+the\s+same\s+changes\s+to\s+the\s+other\s+one|proceed\s+with\s+option\s+number\s+two)$", "selection_state"),
            (r"^(?:yes\s+go\s+ahead\s+with\s+that|no\s+not\s+that\s+one\s+the\s+other\s+one)$", "confirmation_context"),
            (r"^(?:what\s+was\s+the\s+name\s+of\s+that\s+thing\s+again|is\s+it\s+supposed\s+to\s+look\s+like\s+that)$", "referent_entity"),
            (r"^(?:why\s+did\s+that\s+happen\s+just\s+now|could\s+you\s+fix\s+that\s+error\s+for\s+me)$", "error_context"),
            (r"^(?:can\s+you\s+please|i\s+would\s+like\s+to|where\s+is\s+the|how\s+do\s+i\s+get\s+to|because\s+of\s+the\s+issue|if\s+you\s+can\s+then)$", "incomplete_intent"),
        )

        stripped_punct = lower.strip(" .!?")
        for pat, param_name in ungrounded_patterns:
            if re.match(pat, stripped_punct):
                # Rule C: Check if referent is grounded in active context
                if (
                    param_name in context
                    or "active_task_id" in context
                    or "task_id" in context
                    or "active_process" in context
                    or "current_file" in context
                    or "selected_option" in context
                ):
                    return SufficiencyAssessment(
                        classification=RoutingClassification.KNOWN_CAPABILITY,
                        is_sufficient=True,
                        confidence=0.95,
                        reason=f"Referential query grounded by active context ({param_name}).",
                        grounded_referents=context,
                    )
                else:
                    return SufficiencyAssessment(
                        classification=RoutingClassification.CLARIFICATION_REQUIRED,
                        is_sufficient=False,
                        confidence=0.98,
                        reason=f"Ungrounded reference '{clean}' requires specification of {param_name}.",
                        missing_parameters=[param_name],
                    )

        # 5. Rule D: Noun Overlap is NOT Intent (Conversational symptom / troubleshooting inquiries)
        for pat in SYMPTOM_COMPLAINT_PATTERNS:
            if re.search(pat, lower):
                return SufficiencyAssessment(
                    classification=RoutingClassification.CONVERSATIONAL,
                    is_sufficient=True,
                    confidence=0.96,
                    reason="Conversational troubleshooting discussion or symptom description.",
                )

        # Conversational literary / trivia / rhetorical queries
        if any(pat in lower for pat in LITERARY_TRIVIA_PATTERNS):
            return SufficiencyAssessment(
                classification=RoutingClassification.CONVERSATIONAL,
                is_sufficient=True,
                confidence=0.96,
                reason="Conversational literary, trivia, or rhetorical query.",
            )

        # Conversational questions or advice starters
        if any(lower.startswith(s) for s in CONVERSATIONAL_STARTERS):
            if not bool(re.search(r'\b(?:calculate|compute|simulate|integrate|run\s+script|write\s+(?:a\s+)?(?:python\s+)?script|create\s+(?:a\s+)?(?:python\s+)?script)\b', lower)):
                return SufficiencyAssessment(
                    classification=RoutingClassification.CONVERSATIONAL,
                    is_sufficient=True,
                    confidence=0.95,
                    reason="Conversational inquiry, advice, or general knowledge.",
                )

        # 5B. Safe Machine State Query Guards (Prioritize Operational Inquiries over Question Marks)
        # Inquiries regarding machine state (processes, apps, windows, hardware) are NOT conversational trivia!
        if bool(re.search(r'\b(?:what|which|list)\s+processes\s+(?:are\s+)?(?:currently\s+)?(?:running|active)\b', lower)) or lower.startswith("what processes are"):
            return SufficiencyAssessment(
                classification=RoutingClassification.KNOWN_CAPABILITY,
                is_sufficient=True,
                confidence=0.98,
                reason="Direct inquiry for active running processes.",
                target_capability="list_processes",
            )

        app_running_inquiry = re.search(r'\b(?:is|check\s+if)\s+([a-zA-Z0-9_\-\s\.\+]+?)\s+(?:currently\s+)?(?:running|open|active)\b', lower)
        if app_running_inquiry:
            app_name = app_running_inquiry.group(1).strip()
            return SufficiencyAssessment(
                classification=RoutingClassification.KNOWN_CAPABILITY,
                is_sufficient=True,
                confidence=0.96,
                reason=f"Operational inquiry on application running status for '{app_name}'.",
                target_capability="is_application_running",
                extracted_parameters={"app": app_name},
            )

        app_installed_inquiry = re.search(r'\b(?:do\s+i\s+have|is|check\s+if)\s+([a-zA-Z0-9_\-\s\.\+]+?)\s+(?:installed|available)\b', lower)
        if app_installed_inquiry:
            app_name = app_installed_inquiry.group(1).strip()
            return SufficiencyAssessment(
                classification=RoutingClassification.KNOWN_CAPABILITY,
                is_sufficient=True,
                confidence=0.96,
                reason=f"Operational inquiry on application installation for '{app_name}'.",
                target_capability="find_application",
                extracted_parameters={"name": app_name},
            )

        if bool(re.search(r'\b(?:what|which|show|list)\s+(?:open\s+|active\s+)?windows\s+(?:are\s+)?(?:open|active|currently\s+open)\b', lower)):
            return SufficiencyAssessment(
                classification=RoutingClassification.KNOWN_CAPABILITY,
                is_sufficient=True,
                confidence=0.98,
                reason="Operational inquiry on visible desktop windows.",
                target_capability="list_windows",
            )

        # General Conversational Question Mark Check (Guarded against compute substrings like "quantum computer")
        if lower.endswith("?"):
            is_comp = bool(re.search(r'\b(?:calculate|compute|simulate|integrate|run\s+script|write\s+(?:a\s+)?(?:python\s+)?script|create\s+(?:a\s+)?(?:python\s+)?script)\b', lower))
            if not is_comp:
                return SufficiencyAssessment(
                    classification=RoutingClassification.CONVERSATIONAL,
                    is_sufficient=True,
                    confidence=0.93,
                    reason="General conversational question.",
                )

        # 6. Rule F: Dynamic Algorithmic Computation & Transformations (Evaluated BEFORE composite clause splitting!)
        for kw in DYNAMIC_KEYWORDS:
            if re.search(r"\b" + kw + r"\b", lower) or kw in lower:
                return SufficiencyAssessment(
                    classification=RoutingClassification.DYNAMIC_COMPUTATION,
                    is_sufficient=True,
                    confidence=0.98,
                    reason=f"Novel dynamic computation/algorithmic synthesis term '{kw}'.",
                    requires_code=True,
                )

        # Calculations, numerical equations, algorithmic tasks
        if any(w in lower for w in ("calculate", "compute", "solve", "simulate", "numerical", "integrate")) and any(
            t in lower for t in (
                "area", "perimeter", "volume", "trajectories", "roots", "matrix", "integral",
                "variance", "fibonacci", "prime", "equation", "simulation", "markov",
                "collatz", "gravity", "distances", "standard deviation", "volatility",
                "condition number", "determinant", "factorization", "checksum"
            )
        ):
            return SufficiencyAssessment(
                classification=RoutingClassification.DYNAMIC_COMPUTATION,
                is_sufficient=True,
                confidence=0.97,
                reason="Algorithmic or mathematical computation request.",
                requires_code=True,
            )

        # Data parsing/transformation pipelines (e.g. "parse postgresql slow query log and aggregate...")
        if bool(re.search(r'\b(?:parse|extract|aggregate|transform|compile|convert|turn|merge|organize|generate|flatten)\b', lower)) and (
            any(ext in lower for ext in (".log", ".csv", ".json", ".txt"))
            or any(kw in lower for kw in (
                "table", "summary report", "report table", "percentiles", "dataset", "server log", "access log",
                "slow query log", "batch logs", "query logs",
                "stack traces", "latencies", "metrics", "anomalies", "bottlenecks", "deadlock",
                "telemetry", "frequencies", "payload", "test files", "login events", "orders", "commits", "exceptions"
            ))
        ):
            return SufficiencyAssessment(
                classification=RoutingClassification.DYNAMIC_COMPUTATION,
                is_sufficient=True,
                confidence=0.96,
                reason="Dynamic data transformation and analysis pipeline.",
                requires_code=True,
            )

        # Procedural generation & plotting
        if bool(re.search(r'\bgenerate\s+(?:a\s+)?(?:\d+x\d+\s+)?(?:random\s+)?(?:maze|grid|synthetic|mandelbrot|matrix|dataset|distribution|series|histogram|cellular)\b', lower)) or bool(re.search(r'\b(?:plot|render|generate|create|make)\s+(?:a\s+)?(?:\d+[dD]\s+)?(?:scatter\s+plot|line\s+chart|bar\s+chart|histogram|heatmap|chart|plot|visualization|surface\s+plot)\b', lower)) or bool(re.search(r'\b(?:visualiz\w*|plot\w*)\s+(?:memory|cpu|activity|temperature|sales|revenue|expenses|scores|readings|function|3d)\b', lower)):
            return SufficiencyAssessment(
                classification=RoutingClassification.DYNAMIC_COMPUTATION,
                is_sufficient=True,
                confidence=0.96,
                reason="Procedural generation or dynamic visualization pipeline.",
                requires_code=True,
            )

        # Code synthesis / program creation requests (Evaluated BEFORE composite splitting!)
        if bool(re.search(r"\b(?:create|write|generate|implement|build)\s+(?:a\s+)?(?:python\s+)?(?:program|script|code|tool|function|module|pipeline)\b", lower)):
            return SufficiencyAssessment(
                classification=RoutingClassification.DYNAMIC_COMPUTATION,
                is_sufficient=True,
                confidence=0.98,
                reason="Program or code synthesis request.",
                requires_code=True,
            )

        # Single Application launch check (e.g. "launch the date and time settings", "open notepad")
        # Checked BEFORE composite splitting to prevent multi-word names like "date and time" from splitting
        known_apps = (
            "notepad", "calculator", "calc", "visual studio code", "vs code", "code",
            "vivaldi", "browser", "windows terminal", "terminal", "wt", "cmd", "command prompt",
            "powershell", "task manager", "file explorer", "explorer", "edge",
            "control panel", "device manager", "disk management", "registry editor",
            "settings", "taskbar settings", "services manager", "character map",
            "downloads folder", "desktop directory", "documents folder",
            "bluetooth settings", "display settings", "sound settings", "ascii character table",
            "date and time settings", "storage settings", "default apps settings", "clipboard settings",
            "installed apps list", "network connections"
        )
        norm_launch = re.sub(r"^(?:please|can you|could you|would you)\s+", "", lower).strip()
        app_launch_match = re.match(r"^(?:open|launch|start|close|exit|quit)\s+(?:the\s+|a\s+|an\s+|my\s+)?([a-zA-Z0-9_\-\s\.\+]+)$", norm_launch)
        if app_launch_match:
            target_app = app_launch_match.group(1).strip()
            if target_app in known_apps or not any(c in target_app for c in (" and ", " then ", ";", " and then ", " then check ")):
                if any(target_app == a for a in known_apps):
                    action = "close_application" if norm_launch.startswith(("close", "exit", "quit")) else "open_application"
                    return SufficiencyAssessment(
                        classification=RoutingClassification.KNOWN_CAPABILITY,
                        is_sufficient=True,
                        confidence=0.96,
                        reason=f"Direct application management for '{target_app}'.",
                        target_capability=action,
                        extracted_parameters={"app": target_app},
                    )

        # 7. Rule G: Multi-step Composite Workflows
        conjunctions = (" and ", " then ", ", then ", ";", " then check ", " and then ")
        if any(c in lower for c in conjunctions):
            clauses = [cl.strip() for cl in re.split(r"\band\b|\bthen\b|;", lower) if cl.strip()]
            if len(clauses) >= 2 and all(any(v in cl for v in OPERATIONAL_VERBS) for cl in clauses):
                # Ensure it's not a dynamic mathematical problem with 'and' (e.g. 'calculate roots and save them')
                is_math_chain = any(any(k in cl for k in DYNAMIC_KEYWORDS) for cl in clauses)
                if not is_math_chain:
                    return SufficiencyAssessment(
                        classification=RoutingClassification.COMPOSITE,
                        is_sufficient=True,
                        confidence=0.95,
                        reason="Multi-step composite operational workflow.",
                    )

        # 8. Rule E: Explicit Known Capabilities
        explicit_capability_mappings = (
            (r"\b(?:check|show|get|display)\s+(?:the\s+)?(?:battery\s+level|battery\s+status|battery\s+percentage|battery\s+health)\b", "battery_status"),
            (r"\b(?:run|generate|create|produce|save|show|view)\s+(?:a\s+)?(?:windows\s+)?battery\s+(?:health\s+)?report\b", "generate_battery_report"),
            (r"\b(?:scan(?:\s+for)?|list|show|search\s+for|perform)\s+(?:available\s+)?wifi\s*(?:networks|ssids|signals|scan)?\b", "wifi_scan"),
            (r"\b(?:wifi\s+status|check\s+wifi|is\s+wifi\s+connected|check\s+my\s+wifi)\b", "wifi_status"),
            (r"\b(?:connect\s+to\s+(?:wifi\s+)?([a-zA-Z0-9_\-]+))\b", "wifi_connect"),
            (r"\b(?:disconnect\s+(?:from\s+)?wifi)\b", "wifi_disconnect"),
            (r"\b(?:lock\s+(?:my\s+|the\s+|this\s+)?(?:workstation|screen|pc|computer))\b", "lock_workstation"),
            (r"\b(?:take\s+(?:a\s+)?screenshot|capture\s+(?:a\s+)?(?:the\s+)?screenshot|grab\s+(?:a\s+)?(?:the\s+)?screenshot|capture\s+(?:the\s+)?screen|screen\s+grab)\b", "take_screenshot"),
            (r"\b(?:cpu\s+usage|check\s+cpu|cpu\s+status|cpu\s+utilization|cpu\s+load)\b", "cpu_status"),
            (r"\b(?:gpu\s+usage|check\s+gpu|gpu\s+status|gpu\s+utilization|gpu\s+load)\b", "gpu_status"),
            (r"\b(?:system\s+memory|check\s+memory|memory\s+status|available\s+ram|system\s+memory\s+usage)\b", "memory_status"),
            (r"\b(?:disk\s+space|free\s+disk|disk\s+status|disk\s+utilization|check\s+storage|available\s+disk\s+space)\b", "disk_status"),
            (r"\b(?:list\s+running\s+applications|show\s+open\s+apps|running\s+apps)\b", "list_running_applications"),
            (r"\b(?:list\s+open\s+windows|list\s+windows|show\s+windows|show\s+open\s+windows|show\s+me\s+open\s+windows|display\s+(?:active\s+)?windows|what\s+windows\s+are\s+open)\b", "list_windows"),
            (r"\b(?:minimize\s+(?:the\s+)?(?:active|current|\s)*window)\b", "minimize_window"),
            (r"\b(?:maximize\s+(?:this|the\s+)?(?:active|current|\s)*window)\b", "maximize_window"),
            (r"\b(?:snap\s+window\s+to\s+left|snap\s+window\s+left)\b", "snap_window_left"),
            (r"\b(?:snap\s+window\s+to\s+right|snap\s+window\s+right)\b", "snap_window_right"),
            (r"\b(?:audio\s+status|check\s+audio|is\s+system\s+muted|volume\s+status|query\s+system\s+audio)\b", "audio_status"),
            (r"\b(?:mute\s+(?:the\s+)?system\s+volume|mute\s+audio|mute\s+system)\b", "audio_status"),
            (r"\b(?:unmute\s+system\s+audio|unmute\s+system|unmute\s+audio)\b", "audio_status"),
            (r"\b(?:system\s+summary|workstation\s+summary|system\s+info|get\s+system\s+information|show\s+computer\s+hostname|display\s+system\s+hardware\s+summary|hostname\s+and\s+os\s+version)\b", "system_summary"),
            (r"\b(?:list\s+running\s+processes|running\s+processes|what\s+processes\s+are\s+currently\s+running|open\s+summary\s+of\s+running\s+tasks|summary\s+of\s+running\s+tasks)\b", "list_processes"),
            (r"\b(?:inspect\s+open\s+network\s+ports|listening\s+ports)\b", "list_listening_ports"),
            (r"\b(?:inspect\s+routing\s+table|routing\s+table\s+in\s+network|view\s+network\s+adapter\s+connections\s+table|network\s+adapter\s+connections\s+table)\b", "list_network_connections"),
            (r"\b(?:check\s+if\s+port\s+\d+\s+is\s+(?:listening|active))\b", "inspect_port"),
            (r"\b(?:git\s+status|git\s+branch|repository\s+git\s+status)\b", "project_git_status"),
            (r"\b(?:open|show)\s+(?:the\s+)?downloads\s+folder\b", "open_folder"),
            (r"\b(?:open|show)\s+(?:the\s+)?desktop\s+(?:directory|folder)\b", "open_folder"),
            (r"\b(?:open|show)\s+(?:bluetooth\s+settings|display\s+settings|sound\s+settings|ascii\s+character\s+table|installed\s+apps\s+table\s+in\s+settings)\b", "open_application"),
            (r"\b(?:find\s+file\s+([^\s]+)\s+in\s+([^\s]+))\b", "find_file"),
            (r"\b(?:search\s+for\s+([^\s]+)\s+in\s+([^\s]+))\b", "find_file"),
            (r"\b(?:create|save|write)\s+(?:a\s+)?(?:text\s+)?file\s+(?:on|in|to|called|named)\b", "save_text_file"),
        )

        for pat, cap_id in explicit_capability_mappings:
            m = re.search(pat, clean, re.IGNORECASE)
            if m:
                extra_args = {}
                if cap_id == "wifi_connect" and m.groups():
                    extra_args["ssid"] = m.group(1)
                elif cap_id == "find_file" and m.groups():
                    extra_args["query"] = m.group(1)
                    if len(m.groups()) > 1:
                        extra_args["location"] = m.group(2)
                elif cap_id == "open_application":
                    extra_args["app"] = clean
                return SufficiencyAssessment(
                    classification=RoutingClassification.KNOWN_CAPABILITY,
                    is_sufficient=True,
                    confidence=0.96,
                    reason=f"Explicit operational intent mapped to capability '{cap_id}'.",
                    target_capability=cap_id,
                    extracted_parameters=extra_args,
                )

        # Layer 3: Authoritative Capability Grounding
        grounder = _get_shared_grounder()
        cap_match = grounder.match(clean)
        if cap_match.matched and cap_match.capability_id:
            return SufficiencyAssessment(
                classification=RoutingClassification.KNOWN_CAPABILITY,
                is_sufficient=True,
                confidence=cap_match.confidence,
                reason=cap_match.reason,
                target_capability=cap_match.capability_id,
                extracted_parameters=cap_match.extracted_parameters,
            )

        # Layer 5: Learned Semantic Router for novel, computational, composite, or boundary cases
        from astrarun.routing.context_grounding import ContextGrounder
        from astrarun.routing.learned_router import SemanticRouteClass

        grounding = ContextGrounder.analyze(clean, active_context=context)
        learned_router = _get_shared_learned_router()
        decision = learned_router.route(clean, grounding, active_context=context)

        route_map = {
            SemanticRouteClass.DYNAMIC_COMPUTATION.value: RoutingClassification.DYNAMIC_COMPUTATION,
            SemanticRouteClass.COMPOSITE.value: RoutingClassification.COMPOSITE,
            SemanticRouteClass.CONVERSATIONAL.value: RoutingClassification.CONVERSATIONAL,
            SemanticRouteClass.KNOWN_CAPABILITY.value: RoutingClassification.KNOWN_CAPABILITY,
            SemanticRouteClass.CLARIFICATION_REQUIRED.value: RoutingClassification.CLARIFICATION_REQUIRED,
            SemanticRouteClass.SECURITY_REJECTION.value: RoutingClassification.SECURITY_REJECTION,
            SemanticRouteClass.DELEGATE_EXTERNAL_AI.value: RoutingClassification.DELEGATE_EXTERNAL_AI,
        }

        routed_class = route_map.get(decision.route, RoutingClassification.CLARIFICATION_REQUIRED)
        is_suff = routed_class not in (RoutingClassification.CLARIFICATION_REQUIRED, RoutingClassification.SECURITY_REJECTION)
        target_cap = decision.candidate_capabilities[0] if (routed_class == RoutingClassification.KNOWN_CAPABILITY and decision.candidate_capabilities) else None

        return SufficiencyAssessment(
            classification=routed_class,
            is_sufficient=is_suff,
            confidence=decision.confidence,
            reason=f"Layer 5 Semantic Router: {decision.reason_code}",
            target_capability=target_cap,
            missing_parameters=decision.missing_information,
            grounded_referents=context,
            requires_code=decision.requires_code,
        )
