# AstraRun Intent Taxonomy Specification

> **Document Status**: APPROVED SPECIFICATION  
> **Milestone**: AstraRun v0.3  
> **Target Subsystem**: `LayaRouter` & Semantic Benchmark  
> **Date**: 2026-09-27  

---

## 1. Design Principles

AstraRun enforces a fundamental architectural boundary:
- **Intents are NOT executable tools**: Recognizing what the user wants is completely separate from whether AstraRun has the capability or security permission to perform it.
- **Mutual Exclusivity**: Categories are strictly defined to prevent semantic overlap.
- **Safe Abstention**: If an utterance is ambiguous, under-specified, or nonsensical, the only correct classification is `unknown`.

---

## 2. Intent Inventory

### 2.1. `open_app`
- **Definition**: User intends to launch an installed Windows desktop application.
- **Criteria**: Mentions an application executable, product name, or known software utility.
- **Examples**:
  - `open vscode`
  - `launch notepad`
  - `start vivaldi browser`
  - `open calculator`
  - `run cmd`
- **Counterexamples**:
  - `open my vivaldi project` $\to$ `open_project`
  - `find the vscode installer` $\to$ `find_file`
  - `ask AI why notepad is crashing` $\to$ `ai_query`
- **Required Resolver**: Application Cache (`App Paths`, Start Menu `.lnk`, Registry).
- **Risk Level**: `LOW`
- **Currently Executable**: **YES** (`open_app` tool).

---

### 2.2. `open_folder`
- **Definition**: User intends to open a local directory in Windows File Explorer.
- **Criteria**: Targets a known user folder (`Downloads`, `Documents`, `Desktop`, `Pictures`, `Videos`) or explicit local directory path.
- **Examples**:
  - `open downloads`
  - `show documents folder`
  - `go to desktop`
  - `explore pictures`
  - `open E:\Workspace`
- **Counterexamples**:
  - `search downloads for my receipt` $\to$ `find_file`
  - `delete downloads` $\to$ `system_action`
- **Required Resolver**: Windows User Shell Folders / dynamic path resolution.
- **Risk Level**: `LOW`
- **Currently Executable**: **YES** (`open_folder` tool).

---

### 2.3. `open_url`
- **Definition**: User intends to navigate directly to a specific website alias or explicit HTTP/HTTPS URL in their default browser.
- **Criteria**: Mentions a top-level web domain, configured web alias (`github`, `youtube`, `google`), or raw URL.
- **Examples**:
  - `open github`
  - `go to youtube`
  - `open https://news.ycombinator.com`
  - `open reddit`
- **Counterexamples**:
  - `search google for python tips` $\to$ `browser_action`
  - `download file from github` $\to$ `system_action`
- **Required Resolver**: URL configuration (`config/urls.json`) / default system browser.
- **Risk Level**: `LOW`
- **Currently Executable**: **YES** (`open_url` tool).

---

### 2.4. `open_project`
- **Definition**: User semantically refers to a software development workspace or code repository to resume development.
- **Criteria**: Mentions a project name, coding workspace, or development context.
- **Examples**:
  - `open my vivaldi project`
  - `resume AstraRun`
  - `continue working on server`
  - `switch to security workbench`
  - `open the browser project I was building`
- **Counterexamples**:
  - `open vivaldi` $\to$ `open_app`
  - `open active projects folder` $\to$ `open_folder`
- **Required Resolver**: Workspace Orchestrator (`workspace.json` / `wsctl`).
- **Risk Level**: `LOW`
- **Currently Executable**: **NO** (Planned for v0.6).

---

### 2.5. `find_file`
- **Definition**: User requests searching for, locating, or opening a specific individual file, note, or document.
- **Criteria**: Specifies a filename, file extension, or descriptive document query.
- **Examples**:
  - `find my latest screenshot`
  - `open my cryptography notes`
  - `search for invoice.pdf`
  - `find yesterday's report`
- **Counterexamples**:
  - `open documents` $\to$ `open_folder`
  - `delete invoice.pdf` $\to$ `system_action`
- **Required Resolver**: Local File Indexer.
- **Risk Level**: `LOW`
- **Currently Executable**: **NO** (Planned for v0.4/v0.6).

---

### 2.6. `process_action`
- **Definition**: User requests inspecting, restarting, or terminating a running operating system process, daemon, or network port.
- **Criteria**: References process termination, port listening, or service restarts.
- **Examples**:
  - `kill whatever is using port 3000`
  - `restart the node server`
  - `stop python process`
  - `terminate task 1234`
- **Counterexamples**:
  - `start node server` $\to$ `open_app` / `open_project`
  - `why is port 3000 busy?` $\to$ `ai_query`
- **Required Resolver**: Process Manager.
- **Risk Level**: `HIGH` (Requires secondary confirmation before execution).
- **Currently Executable**: **NO** (Planned for v0.7).

---

### 2.7. `system_action`
- **Definition**: Actions controlling hardware state, display settings, audio volume, or power state.
- **Criteria**: Operating system management functions.
- **Examples**:
  - `lock workstation`
  - `set volume to 50%`
  - `mute audio`
  - `turn off display`
  - `restart computer`
- **Counterexamples**:
  - `close notepad` $\to$ `process_action`
  - `open display settings` $\to$ `open_app`
- **Required Resolver**: Windows Win32 API System Controller.
- **Risk Level**: `MEDIUM` to `HIGH`.
- **Currently Executable**: **NO** (Planned for v0.7).

---

### 2.8. `ai_query`
- **Definition**: Conversational, generative, analytical, or reasoning query requiring LLM inference.
- **Criteria**: Asks for explanations, summarization, analysis, code generation, or translation.
- **Examples**:
  - `ask Gemini to analyze this error`
  - `explain how async generators work in python`
  - `summarize the latest pdf in downloads`
  - `how do I implement quicksort in C++`
- **Counterexamples**:
  - `open python docs` $\to$ `open_url`
  - `open notepad and type hello` $\to$ `unknown`
- **Required Resolver**: AI Bridge (`Active/AI-Bridge`).
- **Risk Level**: `LOW`.
- **Currently Executable**: **NO** (Planned for v0.5).

---

### 2.9. `browser_action`
- **Definition**: Search engine query or automated browser interaction beyond opening a bare URL.
- **Criteria**: Search commands or in-page navigation requests.
- **Examples**:
  - `search google for rust lifetimes`
  - `search youtube for lofi hip hop`
  - `lookup python packaging guide`
- **Counterexamples**:
  - `open google` $\to$ `open_url`
  - `open youtube` $\to$ `open_url`
- **Required Resolver**: Browser Deep Link / Automation Tool.
- **Risk Level**: `LOW`.
- **Currently Executable**: **NO** (Planned for v0.5).

---

### 2.10. `unknown`
- **Definition**: The request is ambiguous, under-specified, conversational chatter, nonsensical, destructive/adversarial without context, or unsupported.
- **Criteria**: Cannot be mapped with high confidence to any structured intent.
- **Examples**:
  - `asdfgh`
  - `open it`
  - `continue that`
  - `do the thing`
  - `fix it`
  - `delete system32`
  - `format c drive`
  - `run whatever command is here`
- **Required Resolver**: Rejection Handler (`tool="unknown"` $\to$ Nothing happens).
- **Risk Level**: `LOW` (Deterministic no-op).
- **Currently Executable**: **YES** (Standard graceful rejection).

---

## 3. Decision Schema Mapping

When Laya evaluates a query, it outputs:

```json
{
  "intent": "open_project",
  "confidence": 0.92,
  "probabilities": {
    "open_project": 0.92,
    "open_folder": 0.04,
    "open_app": 0.02,
    "unknown": 0.02
  },
  "is_executable_now": false,
  "target_tool": null,
  "risk_tier": "LOW",
  "source": "laya"
}
```

Only `open_app`, `open_folder`, and `open_url` have active tool execution implementations. All other intents have `is_executable_now: false`, guaranteeing zero execution authority even if predicted with 100% confidence.
