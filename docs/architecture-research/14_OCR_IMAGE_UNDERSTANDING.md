# 14 — OCR & Screen Image Understanding Feasibility

> **Status**: APPROVED RESEARCH & ARCHITECTURAL SPECIFICATION  
> **Phase**: 5 — Windows Control Surfaces & Direct Interaction APIs  
> **Focus**: WinRT OCR, Tesseract, PaddleOCR, Lightweight Vision Transformers, and Screen Parsing Pipelines  
> **Target System**: Local Windows 11 Workstation (`E:\Workspace\Active\AstraRun`)  

---

## 1. Executive Summary & Evaluated OCR Technologies

Extracting text from user interfaces, terminal buffers, and desktop documents is a foundational capability for an autonomous workstation agent. However, heavy deep-learning OCR engines can easily overwhelm host physical RAM.

| Technology | Execution Layer | Memory Footprint | Latency (1080p Window) | External Dependencies | Accuracy on Modern UI Fonts | Evidence Tag |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **WinRT Native OCR** (`Windows.Media.Ocr`) | OS System Service (C++) | **0 MB** (Shared OS runtime) | `ESTIMATED` (15 – 45 ms) | **None** (Built into Windows 10/11) | `NOT_MEASURED` (High expected on Segoe UI) | `TARGET` |
| **Tesseract 5** (`tesseract.exe`) | CLI Binary (C++) | `ESTIMATED` (~80 MB RAM) | `ESTIMATED` (180 – 350 ms) | Scoop / Winget package | `NOT_MEASURED` (Known thin-font challenges) | `ESTIMATED` |
| **PaddleOCR / RapidOCR** (ONNX) | CPU / DirectML | `ESTIMATED` (~350 MB RAM) | `ESTIMATED` (120 – 250 ms) | Python wheels + ONNX runtime | `REPORTED_UPSTREAM` (High on standard benchmarks) | `REPORTED_UPSTREAM` |
| **EasyOCR** (PyTorch) | PyTorch (CUDA/CPU) | `ESTIMATED` (~800 MB – 1.2 GB) | `ESTIMATED` (300 – 600 ms) | Heavy PyTorch / Torchvision | `REPORTED_UPSTREAM` | `REPORTED_UPSTREAM` |
| **Florence-2 Large** (Transformers) | PyTorch / CUDA | `ESTIMATED` (~1.4 GB VRAM) | `ESTIMATED` (150 – 250 ms) | HuggingFace Transformers | `REPORTED_UPSTREAM` (SOTA document layout) | `REPORTED_UPSTREAM` |

---

## 2. Technical Deep-Dive: WinRT Native OCR

Windows 10 (1511+) and Windows 11 ship with an enterprise-grade OCR engine in `Windows.Media.Ocr.dll`, used internally by Windows Search, Snipping Tool, and PowerToys Text Extractor.

### 2.1 Mechanical Advantages
1. **Zero Memory Allocation**: Uses the operating system's pre-warmed Windows Runtime (WinRT) OCR service. AstraRun incurs virtually zero resident memory overhead.
2. **Speed Target**: Targets processing a $1920 \times 1080$ frame in **< 50 milliseconds** on CPU without requiring GPU allocation `[TARGET]` (to be empirically measured in Lab E `[NOT_MEASURED]`).
3. **Structured Geometry**: Returns hierarchical objects:
   - `OcrResult.Lines`: Collection of text lines.
   - `OcrLine.Words`: Individual words with exact pixel bounding rectangles (`Rect(X, Y, Width, Height)`).
4. **Multi-Language Support**: Automatically uses the user's installed Windows language packs.

### 2.2 Python Integration Architecture
WinRT OCR is accessible natively in Python without launching external binaries:
```python
# Architecture: WinRT C-bindings via winsdk or comtypes
from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.graphics.imaging import BitmapDecoder
from winsdk.windows.storage.streams import InMemoryRandomAccessStream

async def extract_ui_text_native(image_bytes: bytes):
    stream = InMemoryRandomAccessStream()
    await stream.write_async(image_bytes)
    decoder = await BitmapDecoder.create_async(stream)
    software_bitmap = await decoder.get_software_bitmap_async()
    
    engine = OcrEngine.try_create_from_user_profile_languages()
    result = await engine.recognize_async(software_bitmap)
    
    elements = []
    for line in result.lines:
        for word in line.words:
            elements.append({
                "text": word.text,
                "bbox": (word.bounding_rect.x, word.bounding_rect.y, 
                         word.bounding_rect.width, word.bounding_rect.height)
            })
    return elements
```

---

## 3. High-Fidelity Document & Table Understanding

When tasks involve parsing dense tabular data, complex PDFs, or diagram images (where spatial relationships matter more than raw character strings), pure word-level OCR is insufficient.

### 3.1 Candidate Document Models

```mermaid
flowchart LR
    Screen[Screen / Document Image] --> Classifier{Task Type}
    
    Classifier -->|UI Text, Buttons, Error Dialogs| WinRT[WinRT Native OCR\nTarget Latency: < 50ms | 0 MB VRAM\nPending Lab E Measurement]
    Classifier -->|Dense PDF, Invoices, Financial Tables| DocWorker[Evictable Worker Process\nFlorence-2 Large / GOT-OCR\nEstimated Latency: ~200ms | 1.4 GB VRAM]
    
    DocWorker --> StructuredJSON[Structured Markdown / Tables]
    WinRT --> DirectClick[Target Coordinate Calculation]
```

1. **Florence-2 Large (770M)**:
   - Capabilities: `<OCR>`, `<OCR_WITH_REGION>`, `<TABLE_RECOGNITION>`.
   - Generates structured Markdown tables from screenshot crops.
   - Can be loaded in an **evictable worker process**, executed on demand, and unloaded immediately to reclaim VRAM.
2. **GOT-OCR-2.0 (580M)**:
   - General OCR Theory model with native formula, table, and formatting extraction.
   - Extremely lightweight, but requires specialized tokenizer and CUDA acceleration.

---

## 4. Synthesis & Architectural Invariants

1. **WinRT OCR is a Candidate Fast-Path**: AstraRun evaluates Windows Native WinRT OCR in Lab E as the candidate zero-VRAM text-extraction engine for UI text and screen scraping `[HYPOTHESIS]`. If Lab E falsifies its accuracy or latency, alternative vision paths will be adopted per `41_ARCHITECTURE_DECISION_GATES.md`.
2. **Heavy PyTorch OCR Stacks Deprioritized**: Tesseract, EasyOCR, and PaddleOCR are deprioritized for AstraRun baseline installations due to redundant binary dependencies, slow startup, or heavy memory consumption `[TARGET]`.
3. **Evictable Document Worker for Complex Layouts**: Complex visual table extraction will be delegated to an on-demand, evictable worker running Florence-2 or offloaded to a remote teacher model `[TARGET]`.
