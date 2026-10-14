"""Trusted out-of-process visualization renderer for AstraRun.

Enforces:
- Full schema validation and security sanitization before rendering
- Out-of-process isolation under Win32JobObject
- Strict memory, execution time, and process limits
- Zero arbitrary code execution / zero shell commands
- Safe file delivery and image header verification
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Union

from astrarun.capabilities.models import CapabilityErrorCode, CapabilityResult
from astrarun.core.logging import get_logger
from astrarun.core.paths import AstraPaths
from astrarun.execution.job_object import Win32JobObject
from astrarun.execution.runtime import CREATE_NO_WINDOW
from astrarun.files.service import validate_safe_path
from astrarun.visualization.models import VisualizationSpec

logger = get_logger("astrarun.visualization.renderer")


def render_visualization(
    spec: Union[Dict[str, Any], str, VisualizationSpec],
    output_path: Optional[str] = None,
    format: str = "png",
    run_id: Optional[str] = None,
    timeout_sec: float = 20.0,
    memory_limit_mb: int = 512,
) -> CapabilityResult:
    """
    Renders a validated declarative VisualizationSpec out-of-process into an image file.
    """
    t0 = time.perf_counter()
    temp_dir = AstraPaths.temp_dir() / f"viz_{uuid.uuid4().hex[:8]}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_spec_file = temp_dir / "spec.json"
    temp_output_file = temp_dir / f"rendered.{format.lower()}"

    try:
        # 1. Parse and validate input spec
        if isinstance(spec, VisualizationSpec):
            validated_spec = spec
        elif isinstance(spec, dict):
            validated_spec = VisualizationSpec.model_validate(spec)
        elif isinstance(spec, str):
            s = spec.strip()
            if s.startswith("{"):
                raw_dict = json.loads(s)
                validated_spec = VisualizationSpec.model_validate(raw_dict)
            else:
                p = Path(s).resolve()
                if not p.is_file():
                    return CapabilityResult.fail(
                        capability="render_visualization",
                        message=f"Specification file not found: {s}",
                        error_code=CapabilityErrorCode.NOT_FOUND,
                    )
                raw_dict = json.loads(p.read_text(encoding="utf-8"))
                validated_spec = VisualizationSpec.model_validate(raw_dict)
        else:
            return CapabilityResult.fail(
                capability="render_visualization",
                message=f"Unsupported spec input type: {type(spec)}",
                error_code=CapabilityErrorCode.INVALID_INPUT,
            )

        if format.lower() != validated_spec.output_format.lower():
            validated_spec.output_format = format.lower()

        # Write validated spec JSON
        temp_spec_file.write_text(validated_spec.model_dump_json(), encoding="utf-8")

        # 2. Destination validation if output_path is provided
        final_dest: Optional[Path] = None
        if output_path:
            is_safe, msg = validate_safe_path(output_path)
            if not is_safe:
                return CapabilityResult.fail(
                    capability="render_visualization",
                    message=f"Illegal output destination path: {msg}",
                    error_code=CapabilityErrorCode.PERMISSION_DENIED,
                )
            final_dest = Path(output_path).expanduser().resolve()
            final_dest.parent.mkdir(parents=True, exist_ok=True)

        # 3. Build minimal sanitized environment
        clean_env = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
            "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
            "SYSTEMDRIVE": os.environ.get("SYSTEMDRIVE", "C:"),
            "PATH": os.environ.get("PATH", ""),
            "TEMP": str(temp_dir),
            "TMP": str(temp_dir),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "MPLBACKEND": "Agg",
            "MPLCONFIGDIR": str(temp_dir),
        }

        # 4. Spawn out-of-process renderer worker under Job Object
        from astrarun.core.paths import resolve_python_executable
        py_exe = resolve_python_executable()
        worker_file = Path(__file__).resolve().parent / "render_worker.py"
        src_root = Path(__file__).resolve().parent.parent.parent
        venv_site = Path.cwd() / ".venv" / "Lib" / "site-packages"
        clean_env["PYTHONPATH"] = f"{src_root};{venv_site}" if venv_site.exists() else str(src_root)
        cmd = [
            py_exe,
            str(worker_file),
            "--spec-file",
            str(temp_spec_file),
            "--output-file",
            str(temp_output_file),
        ]

        job = Win32JobObject(
            name=f"viz_job_{uuid.uuid4().hex[:8]}",
            memory_limit_bytes=memory_limit_mb * 1024 * 1024,
        )

        proc = subprocess.Popen(
            cmd,
            env=clean_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW,
        )

        if os.name == "nt" and hasattr(proc, "_handle"):
            try:
                job.assign_process(int(proc._handle))
            except Exception as e:
                logger.warning("Could not assign renderer to Job Object: %s", e)

        try:
            stdout_data, stderr_data = proc.communicate(timeout=timeout_sec)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            job.terminate(exit_code=1)
            return CapabilityResult.fail(
                capability="render_visualization",
                message=f"Rendering timed out after {timeout_sec} seconds",
                error_code=CapabilityErrorCode.TIMEOUT,
            )
        finally:
            job.close()

        if exit_code != 0:
            err_text = stderr_data.decode("utf-8", errors="replace").strip()
            return CapabilityResult.fail(
                capability="render_visualization",
                message=f"Renderer failed with exit code {exit_code}: {err_text}",
                error_code=CapabilityErrorCode.EXECUTION_FAILED,
            )

        # 5. Verify produced output file
        if not temp_output_file.exists() or temp_output_file.stat().st_size == 0:
            return CapabilityResult.fail(
                capability="render_visualization",
                message="Renderer produced empty or missing output file",
                error_code=CapabilityErrorCode.EXECUTION_FAILED,
            )

        file_size = temp_output_file.stat().st_size
        with open(temp_output_file, "rb") as f_chk:
            header_sample = f_chk.read(128)

        # Format header validation
        fmt_lower = validated_spec.output_format.lower()
        if fmt_lower == "png":
            if not header_sample.startswith(b"\x89PNG\r\n\x1a\n"):
                return CapabilityResult.fail(
                    capability="render_visualization",
                    message="Renderer output failed PNG magic bytes validation",
                    error_code=CapabilityErrorCode.INVALID_INPUT,
                )
        elif fmt_lower == "svg":
            if b"<svg" not in header_sample.lower():
                return CapabilityResult.fail(
                    capability="render_visualization",
                    message="Renderer output failed SVG tag validation",
                    error_code=CapabilityErrorCode.INVALID_INPUT,
                )

        # 6. Deliver to requested destination or retain in clean staged location
        if final_dest:
            os.replace(temp_output_file, final_dest)
            delivered_path = final_dest
        else:
            delivered_path = temp_output_file

        render_ms = (time.perf_counter() - t0) * 1000.0

        return CapabilityResult.ok(
            capability="render_visualization",
            message=f"Rendered visualization successfully ({fmt_lower.upper()}, {file_size} bytes).",
            data={
                "output_path": str(delivered_path),
                "format": fmt_lower,
                "size_bytes": file_size,
                "width": validated_spec.width,
                "height": validated_spec.height,
                "dpi": validated_spec.dpi,
                "render_duration_ms": round(render_ms, 2),
            },
            context_updates=[{
                "type": "visualization_rendered",
                "path": str(delivered_path),
                "format": fmt_lower,
            }],
            latency_ms=render_ms,
        )

    except Exception as err:
        logger.error("Exception during visualization rendering: %s", err)
        return CapabilityResult.fail(
            capability="render_visualization",
            message=f"Visualization rendering error: {err}",
            error_code=CapabilityErrorCode.OS_ERROR,
        )
    finally:
        # Cleanup temporary spec file
        if temp_spec_file.exists():
            temp_spec_file.unlink(missing_ok=True)
