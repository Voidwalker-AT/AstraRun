# AstraRun Third-Party Notices & Licenses

AstraRun bundles and interacts with several open-source libraries, runtimes, and machine learning models. This document provides attribution and licensing notices for these components.

---

## 1. Bundled Python Runtime & Core Libraries

- **Python (CPython)**: Python Software Foundation License (PSFL). Copyright © 2001-2026 Python Software Foundation.
- **PySide6 / Qt6**: GNU Lesser General Public License v3 (LGPLv3) / Commercial. Copyright © 2026 The Qt Company Ltd.
- **ONNX Runtime**: MIT License. Copyright © Microsoft Corporation.
- **FastAPI / Starlette / Pydantic**: MIT License. Copyright © Sebastián Ramírez / Samuel Colvin.
- **Uvicorn**: BSD 3-Clause License. Copyright © 2017-present, Encode OSS Ltd.
- **httpx / httpcore**: BSD 3-Clause License. Copyright © 2019-present, Encode OSS Ltd.
- **PyYAML**: MIT License. Copyright © 2017-2026 Ingy döt Net, Kirill Simonov.
- **NumPy**: BSD 3-Clause License. Copyright © 2005-2026 NumPy Developers.
- **Requests**: Apache License 2.0. Copyright © 2019 Kenneth Reitz.
- **Pillow**: Historical Permission Notice and Disclaimer (HPND). Copyright © 1997-2026 by Secret Labs AB, Fredrik Lundh and contributors.
- **PyInstaller**: GPLv2 with Bootloader Exception (allows proprietary/permissive distribution of frozen applications).

---

## 2. External Runtimes & Managed Binary Distributions

- **llama.cpp / llama-server**: MIT License. Copyright © 2023-2026 Georgi Gerganov and contributors.
- **Inno Setup**: Inno Setup License (modified BSD/zlib style). Copyright © 1997-2026 Jordan Russell / Martijn Laan.

---

## 3. Managed Models & Model Weights (Downloaded Separately via Managed Packs)

AstraRun distributes lightweight orchestration code and downloads model weights post-installation to user-specified local application directories (`%LOCALAPPDATA%\AstraRun\models`):

- **Spark-X2.5 (Spark-7B-X2.5-Q4_K_M.gguf)**:
  - Base: Qwen/Spark Architecture.
  - License: Apache License 2.0 / Qwen Community License.
- **Qwen2.5-Coder-7B-Instruct (Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf)**:
  - Base: Alibaba Cloud Qwen Team.
  - License: Apache License 2.0.
- **BAAI/bge-small-en-v1.5 (bge-small-en-v1.5.onnx)**:
  - Base: Beijing Academy of Artificial Intelligence (BAAI).
  - License: Apache License 2.0.
- **OmniParser-v2.0 (IconDetect ONNX)**:
  - Base: Microsoft Corporation.
  - License: MIT License.
- **SmolVLM-Instruct (SmolVLM-500M-Instruct.gguf)**:
  - Base: Hugging Face SmolLM Team.
  - License: Apache License 2.0.
