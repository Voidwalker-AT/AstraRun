# DESKTOP_LAYOUTS.md — Deterministic Desktop Tiling Layouts & Mathematics

> **Milestone**: AstraRun v0.9 (Daily Driver Integration & Window Intelligence)  
> **Status**: APPROVED  
> **Subsystem**: `src/astrarun/windows/layouts.py`  
> **Target Audience**: Desktop Windowing Engineers, Systems Developers  
> **Last Updated**: 2026-09-27  

---

## 1. Overview & Layout Taxonomy

AstraRun v0.9 provides 11 deterministic tiling layout patterns computed mathematically against the active monitor's `work_area` (`(mx, my, mw, mh)`):

```text
LayoutType (11 Enums):
├── FULL               # 100% W x 100% H (Entire work area)
├── LEFT_HALF          # 50% W x 100% H (Left side split)
├── RIGHT_HALF         # 50% W x 100% H (Right side split)
├── TOP_HALF           # 100% W x 50% H (Upper horizontal split)
├── BOTTOM_HALF        # 100% W x 50% H (Lower horizontal split)
├── TOP_LEFT           # 50% W x 50% H (Upper-left quadrant)
├── TOP_RIGHT          # 50% W x 50% H (Upper-right quadrant)
├── BOTTOM_LEFT        # 50% W x 50% H (Lower-left quadrant)
├── BOTTOM_RIGHT       # 50% W x 50% H (Lower-right quadrant)
├── LEFT_TWO_THIRDS    # 66.6% W x 100% H (Wide coding focus split)
└── RIGHT_ONE_THIRD    # 33.3% W x 100% H (Narrow sidebar/documentation split)
```

---

## 2. Geometric Mathematics & Coordinate Calculation

Given a monitor work area $(m_x, m_y, m_w, m_h)$, `DesktopLayoutEngine.compute_layout_bounds()` computes exact pixel rectangles $(x, y, w, h)$:

### 2.1 Full Work Area
$$\begin{aligned}
x &= m_x, & y &= m_y \\
w &= m_w, & h &= m_h
\end{aligned}$$

### 2.2 Half Splits (Horizontal & Vertical)
- **`LEFT_HALF`**:
  $$x = m_x, \quad y = m_y, \quad w = \lfloor m_w / 2 \rfloor, \quad h = m_h$$
- **`RIGHT_HALF`**:
  $$x = m_x + \lfloor m_w / 2 \rfloor, \quad y = m_y, \quad w = m_w - \lfloor m_w / 2 \rfloor, \quad h = m_h$$
- **`TOP_HALF`**:
  $$x = m_x, \quad y = m_y, \quad w = m_w, \quad h = \lfloor m_h / 2 \rfloor$$
- **`BOTTOM_HALF`**:
  $$x = m_x, \quad y = m_y + \lfloor m_h / 2 \rfloor, \quad w = m_w, \quad h = m_h - \lfloor m_h / 2 \rfloor$$

*Note: Floor division and remainder subtractions guarantee that pixel rounding errors never produce 1px desktop gaps or offscreen overspills.*

### 2.3 Quadrant Corners (2x2 Grid)
- **`TOP_LEFT`**:
  $$x = m_x, \quad y = m_y, \quad w = \lfloor m_w / 2 \rfloor, \quad h = \lfloor m_h / 2 \rfloor$$
- **`TOP_RIGHT`**:
  $$x = m_x + \lfloor m_w / 2 \rfloor, \quad y = m_y, \quad w = m_w - \lfloor m_w / 2 \rfloor, \quad h = \lfloor m_h / 2 \rfloor$$
- **`BOTTOM_LEFT`**:
  $$x = m_x, \quad y = m_y + \lfloor m_h / 2 \rfloor, \quad w = \lfloor m_w / 2 \rfloor, \quad h = m_h - \lfloor m_h / 2 \rfloor$$
- **`BOTTOM_RIGHT`**:
  $$x = m_x + \lfloor m_w / 2 \rfloor, \quad y = m_y + \lfloor m_h / 2 \rfloor, \quad w = m_w - \lfloor m_w / 2 \rfloor, \quad h = m_h - \lfloor m_h / 2 \rfloor$$

### 2.4 Two-Thirds & One-Third Splits (Coding + Reference Layout)
- **`LEFT_TWO_THIRDS`**:
  $$w_1 = \lfloor m_w \times 2 / 3 \rfloor, \quad x = m_x, \quad y = m_y, \quad w = w_1, \quad h = m_h$$
- **`RIGHT_ONE_THIRD`**:
  $$w_1 = \lfloor m_w \times 2 / 3 \rfloor, \quad x = m_x + w_1, \quad y = m_y, \quad w = m_w - w_1, \quad h = m_h$$

---

## 3. Atomic Desktop Arrangement (`arrange_desktop`)

In addition to single-window snapping, AstraRun can tile all visible desktop windows simultaneously into clean multi-window layouts:
1. **Pre-Validation**: Enumerates candidate user windows, discarding protected shell processes and AstraRun itself.
2. **Snapshot Capture**: Captures pre-arrangement geometries for all target windows onto the undo stack.
3. **Partition Computation**:
   - `split_horizontal`: Partitions work width equally across $N$ windows: $w_i = \lfloor m_w / N \rfloor$.
   - `split_vertical`: Partitions work height equally across $N$ windows: $h_i = \lfloor m_h / N \rfloor$.
   - `quad`: Arranges up to 4 windows into the 4 quadrant corners.
4. **Atomic Batch Application**: Applies coordinates via Win32 `DeferWindowPos` / `SetWindowPos`, providing a single-frame desktop transition without visual flickering.
