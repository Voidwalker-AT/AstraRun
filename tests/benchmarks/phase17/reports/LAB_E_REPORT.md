# Phase 17 — Lab E Report: WinRT Native OCR Availability & Reality Audit

> **Timestamp**: 2026-09-30T15:18:11Z  
> **OS**: Windows-11-10.0.26200-SP0 (Version 10.0.26200)  
> **Python**: 3.13.0  
> **Summary**: 2/5 Passed (3 Failed)  

---

## 1. Test Results Breakdown

| Test ID | Test Name | Status | Key Measured Finding |
| :---: | :--- | :---: | :--- |
| **E-1** | `python_winsdk_import` | **FAIL** | winsdk is not installed in project venv; cannot import directly without external pip wheel. |
| **E-2** | `python_winrt_import` | **FAIL** | winrt is not installed in project venv. |
| **E-3** | `os_winrt_ocr_dll_presence` | **PASS** | OS-level C++ binary exists in System32. |
| **E-4** | `powershell_winrt_projection` | **FAIL** | PowerShell 5.1 cannot invoke WinRT IAsyncOperation::GetResults directly on COM objects without compiling custom C# interop assemblies referencing Windows.winmd. |
| **E-5** | `combase_winrt_exports` | **PASS** | Native WinRT C-API exports are present in combase.dll, but calling them from Python requires full C++ COM interface vtable bindings. |

---

## 2. Critical Falsification Finding for WinRT OCR

1. **The 'Zero-Dependency' Claim is FALSIFIED**: The prior research claim that `WinRT OCR is accessible natively in Python without dependencies` is empirically false.
   - Python 3.13 standard library has zero WinRT projections.
   - Neither `winsdk` nor `winrt` is installed in the project environment.
   - `winsdk` is an external package requiring pip installation.
2. **PowerShell Scripting Barrier**: In Windows PowerShell 5.1, `IAsyncOperation` cannot be awaited without compiled C# wrapper assemblies.
3. **Architectural Consequence**: WinRT OCR cannot serve as an immediate zero-install drop-in for AstraRun unless:
   - (a) A small compiled C++ DLL (`astrarun_ocr.dll`) is authored and bundled with AstraRun to wrap `RoGetActivationFactory` via ctypes, OR
   - (b) A lightweight OCR wheel (e.g. `winsdk` or ONNX RapidOCR) is explicitly approved and installed, OR
   - (c) An on-demand worker process (Florence-2 / VLM) handles visual extraction per `41_ARCHITECTURE_DECISION_GATES.md`.