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

- **Spark-X2.5-1.7B (Spark-X2.5-1.7B-Q4_K_M.gguf)**:
  - Base: Liquid AI Spark-X2.5 1.7B Architecture.
  - License: Apache License 2.0.
  - Size: 1,107,457,856 bytes (~1.03 GB).
  - SHA-256: `902bde2522394954ac17821b3e5fd0df02defbc6944f122253f2580acf0503f4`.
- **Qwen2.5-Coder-1.5B-Instruct (qwen2.5-coder-1.5b-instruct-q4_k_m.gguf)**:
  - Base: Alibaba Cloud Qwen Team.
  - License: Apache License 2.0.
  - Size: 1,117,320,768 bytes (~1.04 GB).
  - SHA-256: `cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046`.
- **BAAI/bge-small-en-v1.5 (bge-small-en-v1.5/model.onnx)**:
  - Base: Beijing Academy of Artificial Intelligence (BAAI).
  - License: MIT License.
  - Size: 133,093,490 bytes (~127 MB).
  - SHA-256: `828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35`.
- **OmniParser-v2.0 (OmniParser/icon_detect/model.pt)**:
  - Base: Microsoft Corporation.
  - License: MIT License.
  - Size: 40,623,819 bytes (~38.7 MB).
  - SHA-256: `dab3d4351ad00b035db829909a4db98354d5a90f6990e4ac00222a9a95d4bf57`.
- **SmolVLM-500M-Instruct (SmolVLM-500M/model.safetensors)**:
  - Base: Hugging Face SmolLM Team.
  - License: Apache License 2.0.
  - Size: 1,015,025,832 bytes (~968 MB).
  - SHA-256: `d05b567eeaf534e83d375551f068ed57b5f52d37c657197f644af5ef9db091a2`.
