"""Out-of-process trusted renderer worker.

Renders validated declarative VisualizationSpec to PNG/SVG with zero execution of
worker code, zero network access, and zero ambient privileges.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Force non-interactive Agg backend before importing pyplot
os.environ["MPLBACKEND"] = "Agg"

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

from astrarun.visualization.models import ChartType, VisualizationSpec


def render(spec: VisualizationSpec, output_path: Path) -> None:
    # Set style theme
    if spec.theme == "dark":
        plt.style.use("dark_background")
    else:
        plt.style.use("default")

    fig_w = spec.width / spec.dpi
    fig_h = spec.height / spec.dpi
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=spec.dpi)

    is_3d = any(s.chart_type in (ChartType.SURFACE_3D, ChartType.SCATTER_3D) for s in spec.series)

    if is_3d:
        ax = fig.add_subplot(111, projection="3d")
        ax.view_init(elev=spec.camera.elevation, azim=spec.camera.azimuth)
        if spec.z_axis and spec.z_axis.label:
            ax.set_zlabel(spec.z_axis.label)
    else:
        ax = fig.add_subplot(111)

    if spec.title:
        ax.set_title(spec.title, fontsize=14, pad=12)

    if spec.x_axis.label:
        ax.set_xlabel(spec.x_axis.label, fontsize=11)
    if spec.y_axis.label:
        ax.set_ylabel(spec.y_axis.label, fontsize=11)

    if spec.x_axis.min_val is not None and spec.x_axis.max_val is not None:
        ax.set_xlim(spec.x_axis.min_val, spec.x_axis.max_val)
    if spec.y_axis.min_val is not None and spec.y_axis.max_val is not None:
        ax.set_ylim(spec.y_axis.min_val, spec.y_axis.max_val)

    if not is_3d and spec.x_axis.log_scale:
        ax.set_xscale("log")
    if not is_3d and spec.y_axis.log_scale:
        ax.set_yscale("log")

    if spec.show_grid:
        ax.grid(True, linestyle="--", alpha=0.6)

    # Render each series
    has_labels = False
    for s in spec.series:
        label = s.name
        if label:
            has_labels = True

        kwargs = {}
        if s.color:
            kwargs["color"] = s.color
        if s.alpha is not None:
            kwargs["alpha"] = s.alpha

        if s.chart_type == ChartType.LINE:
            if s.line_style:
                kwargs["linestyle"] = s.line_style
            if s.line_width:
                kwargs["linewidth"] = s.line_width
            if s.marker:
                kwargs["marker"] = s.marker
            ax.plot(s.x, s.y, label=label, **kwargs)

        elif s.chart_type == ChartType.SCATTER:
            if s.marker:
                kwargs["marker"] = s.marker
            ax.scatter(s.x, s.y, label=label, **kwargs)

        elif s.chart_type == ChartType.BAR:
            ax.bar(s.x, s.y, label=label, **kwargs)

        elif s.chart_type == ChartType.HISTOGRAM:
            bins = s.bins or 30
            ax.hist(s.x, bins=bins, label=label, **kwargs)

        elif s.chart_type == ChartType.SCATTER_3D:
            if s.marker:
                kwargs["marker"] = s.marker
            ax.scatter(s.x, s.y, s.z, label=label, **kwargs)

        elif s.chart_type == ChartType.SURFACE_3D:
            if s.z_matrix:
                z_arr = np.array(s.z_matrix, dtype=float)
                ny, nx = z_arr.shape
                x_vals = np.array(s.x) if len(s.x) == nx else np.arange(nx)
                y_vals = np.array(s.y) if len(s.y) == ny else np.arange(ny)
                x_grid, y_grid = np.meshgrid(x_vals, y_vals)
                cmap = s.color if (s.color and s.color in plt.colormaps()) else "viridis"
                surf = ax.plot_surface(x_grid, y_grid, z_arr, cmap=cmap, alpha=s.alpha or 0.9, edgecolor="none")
                fig.colorbar(surf, ax=ax, shrink=0.5, aspect=10)

    if spec.show_legend and has_labels:
        ax.legend(loc="best", framealpha=0.8)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), format=spec.output_format, dpi=spec.dpi)
    plt.close("all")


def main() -> int:
    parser = argparse.ArgumentParser(description="AstraRun Trusted Visualization Renderer")
    parser.add_argument("--spec-file", required=True, help="Path to validated JSON VisualizationSpec")
    parser.add_argument("--output-file", required=True, help="Path to output image (PNG/SVG)")
    args = parser.parse_args()

    spec_path = Path(args.spec_file).resolve()
    out_path = Path(args.output_file).resolve()

    if not spec_path.is_file():
        sys.stderr.write(f"Spec file not found: {spec_path}\n")
        return 1

    try:
        raw_json = json.loads(spec_path.read_text(encoding="utf-8"))
        spec = VisualizationSpec.model_validate(raw_json)
        render(spec, out_path)
        if not out_path.exists() or out_path.stat().st_size == 0:
            sys.stderr.write("Renderer completed but output file was not produced or empty\n")
            return 2
        return 0
    except Exception as e:
        sys.stderr.write(f"Visualization rendering error: {e}\n")
        return 3


if __name__ == "__main__":
    sys.exit(main())
