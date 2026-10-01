# Lab D: Browser CDP & Vivaldi Integration Benchmark Report

> **Lab**: LAB_D_BROWSER_CDP  
> **Status**: COMPLETED  
> **Timestamp UTC**: 2026-09-30T15:30:39Z  
> **Host Platform**: Windows-11-10.0.26200-SP0 (Windows 11 Build 10.0.26200)  
> **Browser**: Vivaldi (`E:\vivaldi\Application\vivaldi.exe`)  
> **Harness SHA-256**: `473aca5b8e0aa4deb7477265c83eb91dfbe81f1d83c842642d28c11ab4aa058b`  

---

## 1. Executive Summary & Falsification Audit

| Test ID | Test Name | Status | Key Measured Metric | Architectural Implication |
|---|---|---|---|---|
| **D-1** | Live Port Probe (9222) | **FAIL** | Port closed (`ConnectError`) | **FALSIFIED**: Cannot attach to active Vivaldi session transparently without restart/flags. |
| **D-2** | Dedicated Launch Flags | **PASS** | Version 200 OK, PID recorded | **CONFIRMED**: Dedicated instance exposes full CDP protocol over HTTP/WS. |
| **D-3** | Active Profile Lock Conflict | **PASS** | Debugging port rejected | **FALSIFIED**: Chromium singleton lock prevents sharing active user profile directory. |
| **D-4** | A11y Tree Token Reduction | **PASS** | -12.38% to +41.54% reduction (Cleaned text: 84% - 93%) | **FALSIFIED naive 80% claim**: Unpruned AXTree adds wrapper tokens on dense text. Interactive-only pruning or Cleaned Text is required. |
| **D-5** | Zero-Mouse-Move Interaction | **PASS** | Input typed, cursor delta: (0,0) | **CONFIRMED**: Synthetic CDP keystrokes interact cleanly without OS cursor theft. |
| **D-6** | CDP Client RAM Overhead | **PASS** | Delta: 9.46 MB ($\le 20$ MB) | **CONFIRMED**: Client WebSocket listener is lightweight and leak-free. |

---

## 2. Token Reduction Across Fixtures

| Fixture Name | Raw HTML Tokens | Cleaned Text Tokens | A11y Tree Tokens | A11y Node Count | Measured A11y Token Reduction % | Cleaned Text Reduction % | Under 10k Budget |
|---|---|---|---|---|---|---|---|
| `pyside6_docs` | 2350 | 362 | 2641 | 368 | **-12.38%** | **84.60%** | True |
| `github_repo` | 1804 | 248 | 1806 | 263 | **-0.11%** | **86.25%** | True |
| `form_app` | 1856 | 128 | 1085 | 163 | **41.54%** | **93.10%** | True |

---

## 3. Core Architectural Decisions Informed by Lab D

1. **Browser Isolation Model (Gate BROWSER-1)**:
   - The assumption of "zero-friction transparent attachment to the user's running browser session" is **PHYSICALLY FALSIFIED**.
   - Running Chromium/Vivaldi locks the user data directory. Secondary processes cannot initialize debugging ports on that directory.
   - **Architectural Decision**: AstraRun browser capability must run as a **dedicated agent browser session** using an isolated profile directory (`E:\Workspace\Active\AstraRun\var\browser_profile`). If the user desires shared login state, AstraRun must import session cookies or prompt user authentication within the dedicated agent profile.

2. **Semantic Representation & Pruning (Gate BROWSER-2)**:
   - The upstream claim that naive full accessibility tree dumps achieve $\ge 80\%$ token reduction is **PHYSICALLY FALSIFIED** on text-dense pages (`-12.38%` on API docs, `-0.11%` on code repo). Every static text span incurs role/property syntax wrapper overhead (`[StaticText] "..."`).
   - On interactive/CSS-heavy form pages, AXTree achieved **41.54% reduction** (1856 $\to$ 1085 tokens).
   - In contrast, extracting cleaned semantic text (`document.body.innerText`) achieves **84.6% to 93.1% token reduction** across all fixtures.
   - All representations consumed $\le 2,650$ tokens, remaining well beneath the 10,000 token budget ceiling.
   - **Architectural Decision**: AstraRun must implement **pruned semantic DOM / interactive-only AXTree** (retaining only interactive controls, form fields, and landmarks) rather than dumping raw `StaticText` nodes.

3. **Interaction Mechanism**:
   - Synthetic keystroke dispatch via `Input.dispatchKeyEvent` operates cleanly without moving the physical OS cursor or stealing window focus.
