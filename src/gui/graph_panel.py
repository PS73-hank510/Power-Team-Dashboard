"""Live telemetry graph panel using pyqtgraph.

Two groups of scrolling plots:
  - PSU group: voltage, current, power for each connected PSU
  - Load group: voltage, current for each connected load

Each instrument index gets its own colour variant.  Curves are added
dynamically the first time a sample with a new (source_index, parameter)
combination arrives — no pre-configuration required.

Features:
  - Configurable time window (10/30/60/120/All seconds)
  - Dashed InfiniteLine for each active limit
  - Right-click context menu: Save image (PNG) / Export data as CSV
  - Y-axis auto-scales with 10% headroom
"""

from __future__ import annotations

import csv
import time
from collections import deque
from pathlib import Path
from typing import Optional

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from src.core.models import LimitPair, TelemetrySample

# ---------------------------------------------------------------------------
# Colour palette
# Each entry is a tuple of variants — one per instrument index (cycles if >4).
# ---------------------------------------------------------------------------
_COLOUR_TABLE: dict[tuple[str, str], tuple[str, ...]] = {
    ("PSU",  "voltage"): ("#2196F3", "#64B5F6", "#0D47A1", "#1565C0"),
    ("PSU",  "current"): ("#FF9800", "#FFB74D", "#E65100", "#BF360C"),
    ("PSU",  "power"):   ("#4CAF50", "#81C784", "#1B5E20", "#2E7D32"),
    ("LOAD", "voltage"): ("#9C27B0", "#BA68C8", "#4A148C", "#6A1B9A"),
    ("LOAD", "current"): ("#F44336", "#EF9A9A", "#B71C1C", "#880E4F"),
}

# Maximum data points to keep per curve (ring buffer)
_MAX_POINTS = 10_000

# Window options: (label, seconds); 0 = "All"
_WINDOW_OPTIONS = [
    ("10 s", 10),
    ("30 s", 30),
    ("60 s", 60),
    ("120 s", 120),
    ("All", 0),
]


def _curve_colour(source: str, source_index: int, parameter: str) -> str:
    """Return a hex colour string for a given source × index × parameter."""
    variants = _COLOUR_TABLE.get((source, parameter), ("#ffffff",))
    return variants[source_index % len(variants)]


class _PlotGroup(QGroupBox):
    """A single PlotWidget that dynamically creates curves for each instrument.

    Curves are created on-demand the first time a sample with a new
    (source_index, parameter) key arrives.
    """

    def __init__(self, title: str, source: str, parent=None) -> None:
        super().__init__(title, parent)
        self._source = source  # "PSU" or "LOAD"

        pg.setConfigOptions(antialias=True)
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("#1e1e1e")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.setLabel("left", "Value")
        self._plot_widget.setLabel("bottom", "Time (s ago)")
        self._plot_widget.addLegend()

        # Dynamic ring buffers and curves: key = (source_index, parameter)
        self._ts:     dict[tuple, deque] = {}
        self._vals:   dict[tuple, deque] = {}
        self._curves: dict[tuple, pg.PlotDataItem] = {}

        # Dashed limit lines: key = "parameter_min" / "parameter_max"
        self._limit_lines: dict[str, pg.InfiniteLine] = {}

        layout = QVBoxLayout()
        layout.addWidget(self._plot_widget)
        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_sample(self, sample: TelemetrySample) -> None:
        """Buffer a new sample, creating a curve if this is a new instrument."""
        key = (sample.source_index, sample.parameter)
        if key not in self._curves:
            self._create_curve(sample.source_index, sample.parameter)
        self._ts[key].append(sample.timestamp)
        self._vals[key].append(sample.value)

    def refresh(self, window_seconds: int) -> None:
        """Redraw all curves clipped to the time window."""
        now = time.time()
        for key, curve in self._curves.items():
            ts = list(self._ts[key])
            vs = list(self._vals[key])
            if not ts:
                continue
            if window_seconds > 0:
                cutoff = now - window_seconds
                pairs = [(t, v) for t, v in zip(ts, vs) if t >= cutoff]
                if pairs:
                    ts, vs = zip(*pairs)
                else:
                    ts, vs = [], []
            # Convert to "seconds ago" for x-axis
            x = [t - now for t in ts]
            curve.setData(x, list(vs))

        self._auto_scale_y()

    def update_limits(self, limits: dict[str, LimitPair]) -> None:
        """Redraw dashed limit lines for this group's source."""
        for line in self._limit_lines.values():
            self._plot_widget.removeItem(line)
        self._limit_lines.clear()

        prefix = self._source + "_"
        for key_str, pair in limits.items():
            if not key_str.startswith(prefix):
                continue
            param = key_str[len(prefix):]  # e.g. "PSU_voltage" → "voltage"
            if pair.max is not None:
                line = pg.InfiniteLine(
                    pos=pair.max, angle=0,
                    pen=pg.mkPen("#FF5252", width=1, style=Qt.PenStyle.DashLine),
                    label=f"{param} max={pair.max:.3g}",
                    labelOpts={"color": "#FF5252"},
                )
                self._plot_widget.addItem(line)
                self._limit_lines[f"{param}_max"] = line
            if pair.min is not None:
                line = pg.InfiniteLine(
                    pos=pair.min, angle=0,
                    pen=pg.mkPen("#FFC107", width=1, style=Qt.PenStyle.DashLine),
                    label=f"{param} min={pair.min:.3g}",
                    labelOpts={"color": "#FFC107"},
                )
                self._plot_widget.addItem(line)
                self._limit_lines[f"{param}_min"] = line

    def save_image(self, path: str) -> None:
        """Export the plot as a PNG."""
        exporter = pg.exporters.ImageExporter(self._plot_widget.plotItem)
        exporter.export(path)

    def export_csv(self, path: str, window_seconds: int) -> None:
        """Export current window data to CSV."""
        now = time.time()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "source", "source_index", "parameter", "value"])
            for (src_idx, param), ts_buf in self._ts.items():
                vs_buf = self._vals[(src_idx, param)]
                for t, v in zip(ts_buf, vs_buf):
                    if window_seconds > 0 and t < now - window_seconds:
                        continue
                    writer.writerow([
                        f"{t:.3f}",
                        self._source,
                        src_idx,
                        param,
                        f"{v:.6g}",
                    ])

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_curve(self, source_index: int, parameter: str) -> None:
        """Dynamically add a new plot curve for an instrument/parameter combo."""
        key = (source_index, parameter)
        colour = _curve_colour(self._source, source_index, parameter)
        self._ts[key] = deque(maxlen=_MAX_POINTS)
        self._vals[key] = deque(maxlen=_MAX_POINTS)
        # Label uses 1-based numbering for readability
        label = (
            f"{self._source}-{source_index + 1} {parameter}"
            if source_index > 0
            else f"{self._source} {parameter}"
        )
        self._curves[key] = self._plot_widget.plot(
            [], [],
            pen=pg.mkPen(colour, width=2),
            name=label,
        )

    def _auto_scale_y(self) -> None:
        """Auto-scale Y axis with 10% headroom."""
        all_vals = []
        for vals in self._vals.values():
            all_vals.extend(vals)
        if not all_vals:
            return
        mn, mx = min(all_vals), max(all_vals)
        span = mx - mn
        pad = span * 0.1 if span > 0 else 1.0
        self._plot_widget.setYRange(mn - pad, mx + pad, padding=0)


class GraphPanel(QWidget):
    """Container for PSU and Load plot groups with window selector."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._window_seconds = 60

        self._psu_group = _PlotGroup("PSU Telemetry", "PSU")
        self._load_group = _PlotGroup("Load Telemetry", "LOAD")

        # Window selector
        self._window_combo = QComboBox()
        for label, _ in _WINDOW_OPTIONS:
            self._window_combo.addItem(label)
        self._window_combo.setCurrentIndex(2)  # default: 60s
        self._window_combo.currentIndexChanged.connect(self._on_window_changed)

        # Refresh timer — 5 fps
        self._timer = pg.QtCore.QTimer()
        self._timer.timeout.connect(self._refresh_plots)
        self._timer.start(200)

        # Context menu on right-click for each group
        self._psu_group._plot_widget.scene().sigMouseClicked.connect(
            lambda ev: self._on_plot_click(ev, self._psu_group, "PSU")
        )
        self._load_group._plot_widget.scene().sigMouseClicked.connect(
            lambda ev: self._on_plot_click(ev, self._load_group, "Load")
        )

        # Layout
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Time window:"))
        top_row.addWidget(self._window_combo)
        top_row.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(top_row)
        layout.addWidget(self._psu_group)
        layout.addWidget(self._load_group)
        self.setLayout(layout)

    def add_sample(self, sample: TelemetrySample) -> None:
        """Route a telemetry sample to the correct plot group."""
        if sample.source == "PSU":
            self._psu_group.add_sample(sample)
        elif sample.source == "LOAD":
            self._load_group.add_sample(sample)

    def update_limits(self, limits: dict[str, LimitPair]) -> None:
        """Update dashed limit lines on both groups."""
        self._psu_group.update_limits(limits)
        self._load_group.update_limits(limits)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_window_changed(self, index: int) -> None:
        self._window_seconds = _WINDOW_OPTIONS[index][1]

    def _refresh_plots(self) -> None:
        self._psu_group.refresh(self._window_seconds)
        self._load_group.refresh(self._window_seconds)

    def _on_plot_click(self, event, group: _PlotGroup, label: str) -> None:
        from PyQt6.QtWidgets import QMenu
        if event.button() != Qt.MouseButton.RightButton:
            return
        menu = QMenu()
        save_img = menu.addAction(f"Save {label} image (PNG)...")
        export_csv = menu.addAction(f"Export {label} data as CSV...")
        action = menu.exec(event.screenPos().toPoint())
        if action == save_img:
            path, _ = QFileDialog.getSaveFileName(
                None, f"Save {label} Graph", f"{label}_graph.png", "PNG Images (*.png)"
            )
            if path:
                group.save_image(path)
        elif action == export_csv:
            path, _ = QFileDialog.getSaveFileName(
                None, f"Export {label} Data", f"{label}_data.csv", "CSV Files (*.csv)"
            )
            if path:
                group.export_csv(path, self._window_seconds)
