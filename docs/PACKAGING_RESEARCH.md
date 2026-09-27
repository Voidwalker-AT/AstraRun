# PACKAGING_RESEARCH.md — Self-Contained Desktop Packaging & Distribution Research

> **Milestone**: AstraRun v0.9 (Daily Driver Integration & Window Intelligence)  
> **Status**: RESEARCH COMPLETED  
> **Target Audience**: Build Engineers, Platform Integrators, Systems Architects  
> **Last Updated**: 2026-09-27  

---

## 1. Executive Summary & Objective

AstraRun v0.9 currently runs from an isolated virtual environment (`.venv`) using Python 3.13 on Windows 11. To facilitate broad developer workstation deployment and optional standalone installation without requiring end-users to manage Python runtimes, this document investigates three premier packaging methodologies:
1. **PyInstaller** (Standard frozen bytecode archive)
2. **Nuitka** (Python-to-C++ optimizing compiler)
3. **PyOxidizer** (Rust-based in-memory embedded Python runtime)

We evaluate these approaches against cold startup latency, binary footprint, PySide6/Qt compatibility, C-extension dynamic linking, and Windows Defender / SmartScreen friction.

---

## 2. Comparative Matrix

| Evaluation Criteria | PyInstaller | Nuitka | PyOxidizer |
| :--- | :---: | :---: | :---: |
| **Startup Latency (Cold)** | Moderate (~350–500 ms) | **Fast (~120–180 ms)** | **Ultra-Fast (~80–120 ms)** |
| **Executable Size (Single EXE)** | ~85 MB | ~65 MB | ~95 MB |
| **PySide6 / Qt6 Compatibility** | **Excellent (Native hooks)** | Very Good (Plugin flag) | Complex (Custom resource rules) |
| **C-Extension Support (`psutil`, `spacy`)** | **Out-of-the-box** | Excellent (Compiled) | Difficult (Requires prebuilt wheels) |
| **Compilation Time** | **~45 seconds** | ~12–15 minutes | ~5–8 minutes |
| **Toolchain Prerequisites** | Python only | MSVC 2022 / C++ Build Tools | Rust Toolchain + Cargo |
| **SmartScreen False Positive Risk** | High | Low | Low |

---

## 3. Deep-Dive Technology Analysis

### 3.1 PyInstaller
- **Mechanism**: Bundles the Python interpreter, C-extension `.pyd` files, and `.pyc` bytecode into a compressed directory or single-file executable with a bootstrap stub.
- **Pros**:
  - Zero build tool dependencies beyond Python.
  - Battle-tested PySide6 and Win32 hook ecosystem.
  - Fastest build cycle (ideal for rapid CI verification).
- **Cons**:
  - Single-file mode (`--onefile`) decompresses files into `%TEMP%/_MEIxxxxxx` on startup, introducing a 200–300 ms extraction delay on cold launches.
  - Higher susceptibility to heuristic antivirus false positives.

### 3.2 Nuitka (Recommended for Production Binaries)
- **Mechanism**: Translates Python modules into C++ source code, applying compile-time constant folding and CPython C-API bindings before generating a native Win32 `.exe`.
- **Pros**:
  - True machine code execution eliminates bytecode interpretation overhead.
  - Drastically reduced cold-start latency (< 180 ms), meeting daily driver responsiveness standards.
  - Built-in `--enable-plugin=pyside6` cleanly handles Qt plugin discovery.
  - Lowest binary footprint (~65 MB).
- **Cons**:
  - Requires Visual Studio 2022 C++ build tools installed on the build machine.
  - Longer compilation times (~15 minutes).

### 3.3 PyOxidizer
- **Mechanism**: Embeds a custom CPython distribution into a Rust binary, loading modules and resources directly from memory using a custom in-memory importer rather than filesystem extraction.
- **Pros**:
  - Fastest possible cold-start latency (~80 ms) due to zero filesystem I/O.
- **Cons**:
  - In-memory importing frequently clashes with complex C-extensions (`psutil`, `numpy`, `spacy`) that expect physical DLL file handles.
  - Project maintenance has decelerated; configuration via Starlark is complex and brittle.

---

## 4. Packaging Recommendation & Roadmap

### Recommended Two-Tier Distribution Strategy:

1. **Development & Power-User Tier (Current Baseline)**:
   - Continue leveraging `.venv` + `start-astrarun.ps1`.
   - Zero compilation overhead, instant hot-reloading of modifications, and full access to test harnesses.
2. **Production Installer Tier (Target Milestone v1.0)**:
   - Adopt **Nuitka** with standalone directory packaging (`--standalone --enable-plugin=pyside6`).
   - Wrap the output directory using **Inno Setup** into a signed Windows installer (`AstraRun-Setup.exe`).
   - Configure Inno Setup to automatically register the Windows Startup Run key (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`) if selected by the user.
