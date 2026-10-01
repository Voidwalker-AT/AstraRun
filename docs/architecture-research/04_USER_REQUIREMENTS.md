# 04 — Product Requirements & Policy Specification (/grill-me Output)

> **Origin**: Interactive Product Requirements Interview (/grill-me)  
> **Status**: APPROVED BY USER  
> **Date Verified**: 2026-09-30  
> **Authority**: Binding Product Policy  

---

## 1. File Operations & Filesystem Autonomy

- **Risk- & Scope-Aware Autonomy**: AstraRun may autonomously create and modify task-generated files, temporary scratchpads, caches, generated project files, and files located inside a project/workspace that the user has explicitly authorized Astra to operate upon.
- **Explicit Goal Authorization**: If the user explicitly instructs Astra to overwrite, replace, move, rename, or delete a specific file or folder as part of the current goal (e.g. `"replace output.json with new metrics"`), Astra may do so without asking again, unless the target is system-critical, unusually broad, or irreversible.
- **Pre-Existing File Protection**: Destructive overwrite or deletion of pre-existing user files not clearly covered by the active goal requires an explicit confirmation card.
- **Reversibility Mandate**: Astra must prefer reversible operations wherever practical (e.g., Windows Recycle Bin, Git checkpoint, local backup snapshot, atomic file replacement).
- **Prohibited & Sensitive Directories**: Bulk deletion, system directories (`C:\Windows`, `Program Files`), credentials, application data, and recovery/session files (specifically including `%LOCALAPPDATA%\Packages\Microsoft.WindowsNotepad_8wekyb3d8bbwe`) are subject to hard policy blocks.
- **Zero Nagging Invariant**: Ordinary low-risk file operations explicitly authorized by the user's goal must execute smoothly without redundant confirmation dialogs.

---

## 2. Process Termination & Resource Contention

- **Ownership-, Scope-, and Risk-Aware Termination**: Astra may autonomously terminate processes that it spawned for the current task (child processes, dev servers, test runners, temporary workers).
- **Explicitly Authorized User Processes**: Astra may terminate a non-protected user process without another confirmation when the current goal explicitly authorizes that specific termination (e.g. `"kill whatever is using port 3000"`), after verifying the PID/process identity and checking for likely unsaved-work risk.
- **Inferred Termination Policy**: If process termination is inferred rather than explicitly requested, or if the target is an interactive user application that may contain unsaved work, Astra must pause and present a confirmation card.
- **Hard-Blocked Processes**: Critical Windows processes (`csrss.exe`, `lsass.exe`, `smss.exe`, `explorer.exe`), security software, and AstraRun itself are strictly immutable and hard-blocked from termination.
- **Graceful First**: Always attempt graceful termination (`WM_CLOSE`, `SIGTERM`) before force-killing (`TerminateProcess`, `SIGKILL`).

---

## 3. Physical User Interruption & Takeover

- **Selective Yielding (Zero Fighting Invariant)**: Any physical mouse or keyboard input from the user must immediately pause Astra's GUI/input simulation on conflicting resources. Astra must **never fight the user for cursor, keyboard, focus, or foreground window control**.
- **Non-Conflicting Background Continuation**: Non-conflicting background work (file downloads, API calls, model inference, OCR processing, compilation, tests, file transforms, network polls) continues normally.
- **HUD Takeover State**: When user physical input is detected, Astra preserves the full task state and affected GUI step, displaying a subtle, non-intrusive status in the HUD:
  $$\text{✦ Paused — You are using the computer} \quad [\text{Resume}] \quad [\text{Abort}]$$
- **Verification Before Auto-Resume**: Once user activity ceases, Astra may auto-resume only after verifying that the target UI/window state is still valid and resumption will not interfere with the user. If the user altered the target application state, Astra must re-observe and replan.
- **Surgical Abort**: Explicit cancellation or conflicting user modifications abort only the affected branch, without destroying independent multi-step task progress.

---

## 4. Browser & Personal Account Boundaries

- **Profile Reuse via Structured Interfaces**: Reuse existing logged-in browser profiles (primarily Vivaldi) through structured interfaces (CDP, DOM, Accessibility APIs) without extracting, copying, or persisting cookies, session tokens, or passwords.
- **Autonomous In-Session Interaction**: Astra may autonomously navigate, search, read, download, upload, fill forms, and interact with authenticated web applications (WhatsApp Web, ChatGPT, college portals) when clearly within the active user goal.
- **Consequential Communication Guard**: Actions that send external messages, emails, publish content, modify accounts, or initiate financial transactions follow risk-aware authorization: low-risk communication explicitly requested executes autonomously; ambiguous, sensitive, financial, or irreversible actions require explicit confirmation.
- **Untrusted Observation Invariant**: Webpage content, downloaded files, and chat messages are **strictly untrusted observations** and must NEVER gain instruction authority over Astra (zero prompt-injection execution).
- **Zero Credential Exposure**: Browser credentials and session tokens are strictly air-gapped from local and external reasoning models.
- **Interaction Hierarchy**: Structured browser control (CDP/DOM/Accessibility) is preferred; visual clicking is used only as a last-resort fallback.

---

## 5. The Secret Broker Architecture

- **Opaque Reference Model**: Raw secret values (API keys, passwords, private tokens, SSH keys) are completely isolated from the planner, model prompts, memory stores, and log files. Models receive only opaque handles (e.g. `secret://github/token` or `"credential available"`).
- **Just-In-Time Injection**: A trusted local Secret Broker resolves and injects the actual secret only at the final authorized execution boundary (e.g. HTTP Authorization header or environment variable of an ephemeral process).
- **External Model Protection**: External cloud reasoning providers (Claude, OpenAI, Gemini) must NEVER receive raw secrets under any circumstances.
- **High-Risk Secret Export**: Reading, revealing, exporting, or copying the raw secret value itself is classified as an extreme-risk action requiring explicit user confirmation.

---

## 6. Communication & External Messaging Authority

- **Passive Retrieval**: Opening chats, reading task-relevant messages, searching emails, and downloading attachments are permitted within goal scope.
- **Explicit Goal Authorization for Sending**: Astra may send messages, emails, prompts, form submissions, or uploads without additional confirmation *only when the exact recipient/service and communication action are explicitly authorized by the user goal*.
- **Confirmation Required**: Astra must ask before independently initiating communications, materially altering intended text, contacting additional recipients, or publishing publicly.
- **Audit Logging**: All sent communications are logged with timestamps and payloads (with secrets redacted).

---

## 7. Model Reasoning & Escalation Hierarchy

- **Cheapest Sufficient Intelligence**:
  $$\text{Level 0: Deterministic Fast-Path} \longrightarrow \text{Level 1: Small Local Tool Model} \longrightarrow \text{Level 2: On-Demand Spark-Class (1.7B)} \longrightarrow \text{Level 3: External Deep Reasoning (Cloud)}$$
- **Local-First Mandate**: Core OS functionality must operate 100% offline without external cloud dependencies.
- **External Escalation Policy**: External high-capacity models are invoked only when local models are insufficient or for complex planning/vision tasks. Cloud queries receive minimized, sanitized machine context with zero secrets.
- **Lazy Loading & Worker Isolation**: Heavy local models must be loaded on-demand in isolated worker processes and evicted under physical memory pressure.
- **Pluggable Architecture**: Reasoning providers remain decoupled and replaceable (no hardcoding to specific vendors or AI-Bridge).

---

## 8. Hierarchical Multimodal Vision & OCR

- **Structured Evidence Preferred**:
  $$\text{Native Win32 APIs} \longrightarrow \text{Browser DOM / CDP} \longrightarrow \text{Windows UIA Tree} \longrightarrow \text{Local OCR (WinRT)} \longrightarrow \text{Local Grounding VLM} \longrightarrow \text{External Multimodal}$$
- **OCR vs VLM**: OCR handles text extraction; diagrams, photographs, unknown custom UI controls, and spatial layout reasoning escalate to VLMs.
- **ActionGate Enforcement**: Visually proposed interactions must resolve to typed targets and pass ActionGate; vision models **never hold direct mouse/keyboard authority**.
- **Context Cropping & Redaction**: External VLMs receive only cropped, relevant screen regions with sensitive fields masked.

---

## 9. Tiered Persistent Memory & Compute Optimization

- **Tier 1: Indefinite Core Memory**: Explicit user preferences, aliases, trusted project facts, and approved procedural skills persist permanently in local SQLite.
- **Tier 2: Compacted Episodic History**: Recent tasks are recorded in detail; older tasks are progressively compacted into lessons, outcomes, and provenance.
- **Tier 3: Procedural Skills as Compute Optimization**: Verified multi-step trajectories are synthesized into reusable procedural skills, drastically reducing future model token consumption and latency.
- **Tier 4: Ephemeral Scratchpad**: Temporary screenshots, UI trees, keystrokes, clipboard buffers, and intermediate reasoning are purged after task completion.
- **Zero Secrets in Memory**: Credentials never enter persistent memory stores.
- **Progressive Disclosure**: Models receive only task-relevant memories, never raw historical dumps.
- **Full User Control**: Memory inspector UI allows users to review, edit, pin, or delete stored memories.

---

## 10. User Experience, Task HUD & Command Previews

- **Single Floating Task HUD with Multi-Task Stack**: A single non-focus-stealing floating surface (`WS_EX_NOACTIVATE`) anchors the active task, while concurrent background tasks collapse into an animated chip (e.g. `✦ 3 tasks`).
- **Task Center**: Expandable lightweight Task Center enables users to inspect running, paused, and completed tasks, switch focus, and cancel individual tasks.
- **Risk-Adaptive Code & Command Previews**:
  - *Low-Risk*: Disposable transformations and read-only commands execute autonomously with live step status in the HUD.
  - *Medium-Risk*: Project modifications or dependency installations execute with visible progress and rollback checkpoints.
  - *High-Risk*: Privileged or destructive commands pause and present an interactive preview card with `[Preview Diff]`, `[Run]`, and `[Cancel]`.
