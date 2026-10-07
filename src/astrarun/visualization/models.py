"""Declarative visualization schemas and security-hardened validation models for AstraRun."""

from __future__ import annotations

import math
import re
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChartType(str, Enum):
    LINE = "line"
    SCATTER = "scatter"
    BAR = "bar"
    HISTOGRAM = "histogram"
    SURFACE_3D = "surface_3d"
    SCATTER_3D = "scatter_3d"


def _validate_safe_string(v: Optional[str], max_len: int = 200) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if len(s) > max_len:
        raise ValueError(f"String exceeds max length {max_len}")
    # Reject HTML tags, script execution, URLs
    lower = s.lower()
    if any(tag in lower for tag in ("<script", "<html", "<body", "<iframe", "<embed", "<object", "javascript:", "data:")):
        raise ValueError("HTML and script tags are prohibited in visualization text")
    if any(prefix in lower for prefix in ("http://", "https://", "ftp://", "file://")):
        raise ValueError("Remote URLs and URI schemes are prohibited in visualization text")
    return s


def _validate_finite_floats(nums: List[float], max_count: int = 100_000) -> List[float]:
    if len(nums) > max_count:
        raise ValueError(f"Array length {len(nums)} exceeds max allowed points {max_count}")
    for idx, val in enumerate(nums):
        if not isinstance(val, (int, float)):
            raise ValueError(f"Non-numeric value at index {idx}: {type(val)}")
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"Non-finite numeric value (NaN/Inf) at index {idx}")
    return nums


class SeriesSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    chart_type: ChartType = ChartType.LINE
    x: List[float] = Field(default_factory=list)
    y: List[float] = Field(default_factory=list)
    z: Optional[List[float]] = None
    z_matrix: Optional[List[List[float]]] = None
    color: Optional[str] = None
    marker: Optional[str] = None
    line_style: Optional[str] = None
    line_width: float = Field(default=1.5, ge=0.5, le=10.0)
    alpha: float = Field(default=1.0, ge=0.0, le=1.0)
    bins: Optional[int] = Field(default=None, ge=1, le=500)

    @field_validator("name", "color", "marker", "line_style")
    @classmethod
    def validate_strings(cls, v: Optional[str]) -> Optional[str]:
        return _validate_safe_string(v, max_len=60)

    @field_validator("x", "y")
    @classmethod
    def validate_coordinates(cls, v: List[float]) -> List[float]:
        return _validate_finite_floats(v, max_count=100_000)

    @field_validator("z")
    @classmethod
    def validate_z_coordinates(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is None:
            return None
        return _validate_finite_floats(v, max_count=100_000)

    @field_validator("z_matrix")
    @classmethod
    def validate_matrix(cls, v: Optional[List[List[float]]]) -> Optional[List[List[float]]]:
        if v is None:
            return None
        total_cells = 0
        for row_idx, row in enumerate(v):
            if not isinstance(row, list):
                raise ValueError(f"Matrix row {row_idx} is not a list")
            _validate_finite_floats(row, max_count=1000)
            total_cells += len(row)
            if total_cells > 250_000:
                raise ValueError("Matrix total elements exceed limit of 250,000")
        return v

    @model_validator(mode="after")
    def validate_series_consistency(self) -> SeriesSpec:
        if self.chart_type in (ChartType.LINE, ChartType.SCATTER, ChartType.BAR):
            if len(self.x) != len(self.y):
                raise ValueError(f"X and Y dimensions must match: got len(x)={len(self.x)}, len(y)={len(self.y)}")
        elif self.chart_type == ChartType.SCATTER_3D:
            if not self.z:
                raise ValueError("3D scatter plot requires Z coordinate array")
            if len(self.x) != len(self.y) or len(self.x) != len(self.z):
                raise ValueError("3D scatter plot X, Y, and Z array lengths must match")
        elif self.chart_type == ChartType.SURFACE_3D:
            if not self.z_matrix:
                raise ValueError("3D surface plot requires 2D 'z_matrix' array")
        return self


class AxisSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Optional[str] = None
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    log_scale: bool = False

    @field_validator("label")
    @classmethod
    def validate_label(cls, v: Optional[str]) -> Optional[str]:
        return _validate_safe_string(v, max_len=100)


class CameraSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elevation: float = Field(default=30.0, ge=-90.0, le=90.0)
    azimuth: float = Field(default=-60.0, ge=-360.0, le=360.0)


class VisualizationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    series: List[SeriesSpec] = Field(default_factory=list)
    x_axis: AxisSpec = Field(default_factory=AxisSpec)
    y_axis: AxisSpec = Field(default_factory=AxisSpec)
    z_axis: Optional[AxisSpec] = None
    camera: CameraSpec = Field(default_factory=CameraSpec)
    width: int = Field(default=1024, ge=200, le=4096)
    height: int = Field(default=768, ge=200, le=4096)
    dpi: int = Field(default=150, ge=50, le=300)
    theme: str = Field(default="default")
    show_grid: bool = True
    show_legend: bool = True
    output_format: str = Field(default="png")

    @field_validator("title", "theme")
    @classmethod
    def validate_strings(cls, v: Optional[str]) -> Optional[str]:
        return _validate_safe_string(v, max_len=200)

    @field_validator("output_format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        fmt = v.lower().strip()
        if fmt not in ("png", "svg"):
            raise ValueError(f"Unsupported output format '{v}'. Only 'png' and 'svg' are supported.")
        return fmt

    @model_validator(mode="after")
    def validate_total_points(self) -> VisualizationSpec:
        if not self.series:
            raise ValueError("VisualizationSpec must contain at least one data series")
        if len(self.series) > 20:
            raise ValueError(f"Series count {len(self.series)} exceeds maximum allowed series (20)")
        total_points = sum(len(s.x) + len(s.y) + (len(s.z) if s.z else 0) for s in self.series)
        if total_points > 100_000:
            raise ValueError(f"Total points across all series ({total_points}) exceeds limit of 100,000")
        return self
