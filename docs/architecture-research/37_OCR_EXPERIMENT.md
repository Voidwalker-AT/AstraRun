# 37 — WinRT OCR & Screen Parsing Experiment Protocol (Lab E)

> **Scope**: Phase 17 Lab E Specification  
> **Status**: APPROVED EXPERIMENT PROTOCOL  
> **Focus**: Native Windows 11 WinRT OCR Availability, Word Accuracy, Latency Profiling, and Escalation Boundaries  
> **Target System**: Local Windows 11 Workstation (`E:\Workspace\Active\AstraRun`)  

---

## 1. Experimental Objectives & Falsification Targets

This lab physically evaluates Windows Runtime Native OCR (`Windows.Media.Ocr`) to determine whether it can serve as AstraRun's primary zero-VRAM visual text detector:

1. **Python Integration Feasibility**: Can `Windows.Media.Ocr` execute cleanly via Python `winsdk` on Windows 11 Build 26100 without crashes or COM initialization errors?
2. **Latency Boundary**: Does a $1920 \times 1080$ frame process in $\le 50\,\text{ms}$ on CPU?
3. **Word Accuracy Threshold**: Does it achieve $\ge 95\%$ word accuracy across standard Windows UI fonts (Segoe UI, Cascadia Code)?
4. **Bounding Box Precision**: Are returned bounding rectangles accurate enough to compute precise click target coordinates without missing button boundaries?
5. **Escalation Boundary**: At what exact complexity threshold (dense tables, blurred icons, rotated text, non-text diagrams) does WinRT OCR break down, requiring escalation to a neural vision model?

---

## 2. Controlled Test Dataset & Fixtures

The experiment evaluates 50 controlled screenshot fixtures under `tests/benchmarks/fixtures/ocr/`:

| Fixture Category | Image Count | Content Characteristics | Evaluation Objective |
| :--- | :--- | :--- | :--- |
| **Category 1: Terminal & IDE** | 10 | Cascadia Code, dark background, ANSI colors, stack traces | Precision on monospace code and paths |
| **Category 2: Native Windows UI** | 10 | Windows 11 Settings, File Explorer, Task Manager (Segoe UI) | Button labels, tabs, menu items |
| **Category 3: Web Application UI** | 10 | GitHub, Vivaldi UI, form fields, light & dark themes | Web text elements and navigation links |
| **Category 4: Pathological Text** | 10 | 125% and 150% DPI scaling, low contrast (gray-on-dark), small 9pt fonts | Accuracy under visual degradation |
| **Category 5: Non-Text / Diagrams** | 10 | System architecture diagrams, flowchart boxes, icon grids | Detection of non-text graphical boundaries |

---

## 3. Experimental Procedure & Code Harness

```python
# Prototype Validation Harness (tests/benchmarks/phase17/test_winrt_ocr.py)
import time
from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.graphics.imaging import BitmapDecoder
from winsdk.windows.storage.streams import InMemoryRandomAccessStream

async def benchmark_ocr_frame(image_bytes: bytes):
    t0 = time.perf_counter()
    stream = InMemoryRandomAccessStream()
    await stream.write_async(image_bytes)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    
    t_decode = time.perf_counter() - t0
    
    t1 = time.perf_counter()
    engine = OcrEngine.try_create_from_user_profile_languages()
    ocr_result = await engine.recognize_async(bitmap)
    t_ocr = time.perf_counter() - t1
    
    words = []
    for line in ocr_result.lines:
        for word in line.words:
            words.append({
                "text": word.text,
                "rect": (word.bounding_rect.x, word.bounding_rect.y, 
                         word.bounding_rect.width, word.bounding_rect.height)
            })
            
    total_time_ms = (time.perf_counter() - t0) * 1000.0
    return words, total_time_ms, t_decode * 1000.0, t_ocr * 1000.0
```

---

## 4. Evaluation Metrics & Scoring Criteria

1. **Character Error Rate (CER)** & **Word Error Rate (WER)** computed against annotated ground truth strings:
   $$\text{WER} = \frac{S + D + I}{N}$$
2. **Intersection over Union (IoU)** of detected bounding boxes against ground-truth element boundaries:
   $$\text{IoU} = \frac{\text{Area}(\text{Box}_{\text{pred}} \cap \text{Box}_{\text{truth}})}{\text{Area}(\text{Box}_{\text{pred}} \cup \text{Box}_{\text{truth}})}$$
3. **Execution Latency**:
   - `P50` and `P95` latency (ms) across all 50 fixtures.
4. **VRAM Footprint**:
   - Verified via `pynvml` to ensure **0.0 MB VRAM** allocated on GPU.

---

## 5. Falsification Conditions for WinRT OCR

1. **Accuracy Deficit**: If WinRT OCR produces a Word Error Rate $> 10.0\%$ on Category 2 (Native Windows UI), it cannot serve as the primary visual grounding fast-path.
2. **Latency Bloat**: If full-screen OCR latency exceeds **100 ms**, it fails the real-time interaction constraint.
3. **Python Bridge Instability**: If `winsdk` encounters threading or async deadlocks in multi-threaded agent loops, native C++ ctypes bindings must replace it.
