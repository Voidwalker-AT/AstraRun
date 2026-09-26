# Laya & Kev Integration Architecture

> **Document Status**: DRAFT / SPECIFICATION  
> **Target Release**: AstraRun v0.3 (Laya) & v0.4 (Kev)  

---

## 1. Architectural Role of Laya and Kev

AstraRun v0.1 establishes a strict boundary: the UI and execution subsystems interact exclusively with a clean router interface:

```python
route(request: str, context: RoutingContext) -> Decision
```

In v0.1, this interface is satisfied by `DeterministicRouter`. In subsequent releases, intelligence will be added without modifying the launcher UI or the tool registry.

```mermaid
flowchart TD
    UserReq["User Command (Natural Language)"] --> Norm["Request Normalizer"]
    Norm --> Det["1. Deterministic Router (Fastest, zero-overhead regex & prefix)"]
    
    Det -->|Matched (Confidence == 1.0)| Dec["Structured Decision"]
    Det -->|Unresolved / Low Confidence| Laya["2. Laya Classifier (Local Fast Intent Model)"]
    
    Laya -->|Matched (Confidence >= 0.85)| Dec
    Laya -->|Uncertain / Ambiguous| Kev["3. Kev Semantic Router (Local Embedding & Logic)"]
    
    Kev -->|Resolved| Dec
    Kev -->|Complex Generative / Open-Ended| AIBridge["4. AI Bridge / LLM Layer"]
    
    AIBridge --> Dec
    
    Dec --> Policy["Policy & Validation Engine"]
    Policy --> ToolReg["Tool Registry (Dispatch Safe Handlers)"]
    ToolReg --> OS["Windows Execution"]
```

---

## 2. Fundamental Safety Constraint

> [!IMPORTANT]
> **No AI model (Laya, Kev, or LLMs) will ever execute tools directly.**

Models are strictly information-processing units that output structured data conforming to the `Decision` schema:

```json
{
  "tool": "open_app",
  "args": {
    "app": "code",
    "target": "E:\\Workspace\\Active\\server"
  },
  "confidence": 0.94,
  "source": "laya",
  "explanation": "Resolved user request to opening server project in VS Code"
}
```

The `Policy & Validation Engine` validates the returned `tool` and `args` against the registered schema and security constraints before the `ToolRegistry` dispatches to OS execution.

---

## 3. Router Fallback Composition

The routing architecture will use a `CompositeRouter` pattern:

```python
class CompositeRouter(BaseRouter):
    def __init__(self, routers: list[BaseRouter]):
        self.routers = routers

    def route(self, request: str, context: RoutingContext) -> Decision:
        for router in self.routers:
            decision = router.route(request, context)
            if decision.is_resolved:
                return decision
        return Decision.unknown(request)
```

In v0.1:
`routers = [DeterministicRouter(app_cache, folder_cache, url_cache)]`

In v0.4:
`routers = [DeterministicRouter(...), LayaRouter(...), KevRouter(...), AIBridgeRouter(...)]`

This maintains modular testability and zero architectural rework.
