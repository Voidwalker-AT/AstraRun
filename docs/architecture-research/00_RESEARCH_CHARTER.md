# 00 — Research Charter & Absolute Guardrails

> **Project**: AstraRun — Workstation Agent Architecture Research & Reality Audit  
> **Repository**: `E:\Workspace\Active\AstraRun`  
> **Baseline Frozen At**: AstraRun v0.11.1 (`commit 4c57098`, 395/395 tests passing)  
> **Status**: APPROVED & IN EFFECT  
> **Date**: 2026-09-30  

---

## 1. Absolute Operating Invariants

This phase is strictly **research, audit, torture-study design, and architectural discovery**. The following invariants are absolute:

1. **NO Production Code Modification**: Do not modify, refactor, or delete any files in `src/astrarun/` or existing production test suites.
2. **DO NOT Begin v0.12**: No feature implementation of browser automation, dynamic execution runtimes, or visual computer use during this phase.
3. **DO NOT Integrate External Frameworks**: Do not integrate Spark, Hermes, Agent S, or UFO into production code.
4. **DO NOT Download Multi-GB Models**: No multi-gigabyte model weights may be downloaded without explicit user authorization.
5. **DO NOT Fine-Tune Models**: No training or fine-tuning pipelines may be executed during this planning phase.
6. **Zero-Secret / Zero-Credentials Invariant**: Never inspect, extract, copy, stage, or log browser session cookies, active WhatsApp chats, private emails, or passwords.
7. **Strict Machine Safety**: Never terminate external user processes, modify Windows registry settings, change display drivers, or cause destructive disk operations.

---

## 2. Research Objectives

The goal of this architectural discovery phase is to determine **what AstraRun should become**, replacing architectural intuition with empirical proof:

- **Repository Reality Audit**: Challenge documentation against code, establishing an honest Claim / Evidence Matrix.
- **Physical Machine & Memory Profiling**: Characterize the exact memory and compute ceiling on the physical host machine (12th Gen Core i5-12450H, 16 GB RAM with ~3.3 GB free physical RAM, RTX 2050 4 GB VRAM with ~3.4 GB free VRAM).
- **Competitor Framework Deep Dives**: Investigate Microsoft UFO² / UFO³, Agent S, Browser Use, Open Interpreter, and Hermes Agent to extract reusable architectural patterns and pitfalls.
- **Spark-X2.5 Role-by-Role Torture Study**: Design an adversarial torture benchmark to find where small reasoning models break rather than proving they work.
- **Controlled Dynamic Code Execution Runtime**: Design a sandboxed execution runtime for long-tail developer and data-processing tasks without an unrestricted model-to-shell path.
- **Competing Architectures Evaluation**: Formulate and compare four distinct architectural alternatives (A, B, C, D) and recommend the evidence-backed blueprint for future milestones.
