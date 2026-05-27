"""Live telemetry graph panel using pyqtgraph.

Two groups of scrolling plots:
  - PSU: voltage, current, power
  - Load: voltage, current

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

# Colour palette for curves
_COLOURS = {
    ("PSU", "voltage"): "#2196F3",   # blue
    ("PSU", "current"): "#FF9800",   # orange
    ("PSU", "power"):   "#4CAF50",   # green
    ("LOAD", "voltage"): "#9C27B0",  # purple
    ("LOAD", "current"): "#F44336",  # red
}

# Maximum data points to keep (ring buffer)
_MAX_POINTS = 10_000

# Window options: (label, seconds); 0 = "All"
_WINDOW_OPTIONS = [
    ("10 s", 10),
    ("30 s", 30),
    ("60 s", 60),
    ("120 s", 120),
    ("All", 0),
]


class _PlotGroup(QGroupBox):
    """A single PlotWidget with named curves and limit lines."""

    def __init__(self, title: str, curves_meta: list[tuple[str, str]], parent=None) -> None:
        super().__init__(title, parent)
        self._curves_meta = curves_meta  # [(source, parameter), ...]

        pg.setConfigOptions(antialias=True)
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("#1e1e1e")
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.setLabel("left", "Value")
        self._plot_widget.setLabel("bottom", "Time (s ago)")
        self._plot_widget.addLegend()

        # Ring buffers: key = (source, parameter)
        self._ts: dict[tuple, deque] = {}
        self._vals: dict[tuple, deque] = {}
        self._curves: dict[tuple, pg.PlotDataItem] = {}
        self._limit_lines: dict[str, pg.InfiniteLine] = {}

        for source, param in curves_meta:
            key = (source, param)
            colour = _COLOURS.get(key, "#ffffff")
            self._ts[key] = deque(maxlen=_MAX_POINTS)
            self._vals[key] = deque(maxlen=_MAX_POINTS)
            self._curves[key] = self._plot_widget.plot(
                [], [],
                pen=pg.mkPen(colour, width=2),
                name=f"{source} {param}",
            )

        layout = QVBoxLayout()
        layout.addWidget(self._plot_widget)
        self.setLayout(layout)

    def add_sample(self, sample: TelemetrySample) -> None:
        key = (sample.source, sample.parameter)
        if key not in self._curves:
            return
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

    def update_limits(self, limits: dict[str, LimitPair], source: str) -> None:
        """Redraw dashed limit lines for this group's source."""
        # Remove existing lines
        for line in self._limit_lines.values():
            self._plot_widget.removeItem(line)
        self._limit_lines.clear()

        for key_str, pair in limits.items():
            if not key_str.startswith(source):
                continue
            param = key_str[len(source) + 1:]  # "PSU_voltage" → "voltage"
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
            writer.writerow(["timestamp", "source", "parameter", "value"])
            for (src, param), ts_buf in self._ts.items():
                vs_buf = self._vals[(src, param)]
                for t, v in zip(ts_buf, vs_buf):
                    if window_seconds > 0 and t < now - window_seconds:
                        continue
                    writer.writerow([
                        f"{t:.3f}",
                        src,
                        param,
                        f"{v:.6g}",
                    ])

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

        self._psu_group = _PlotGroup(
            "PSU Telemetry",
            [("PSU", "voltage"), ("PSU", "current"), ("PSU", "power")],
        )
        self._load_group = _PlotGroup(
            "Load Telemetry",
            [("LOAD", "voltage"), ("LOAD", "current")],
        )

        # Window selector
        self._window_combo = QComboBox()
        for label, _ in _WINDOW_OPTIONS:
            self._window_combo.addItem(label)
        self._window_combo.setCurrentIndex(2)  # default: 60s
        self._window_combo.currentIndexChanged.connect(self._on_window_changed)

        # Refresh timer
        self._timer = pg.QtCore.QTimer()
        self._timer.timeout.connect(self._refresh_plots)
        self._timer.start(200)  # 5 fps refresh

        # Layout
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Time window:"))
        top_row.addWidget(self._window_combo)
        top_row.addStretch()

        # Context menu for export on each plot
        self._psu_group._plot_widget.scene().sigMouseClicked.connect(
            lambda ev: self._on_plot_click(ev, self._psu_group, "PSU")
        )
        self._load_group._plot_widget.scene().sigMouseClicked.connect(
            lambda ev: self._on_plot_click(ev, self._load_group, "Load")
        )

        layout = QVBoxLayout()
        layout.addLayout(top_row)
        layout.addWidget(self._psu_group)
        layout.addWidget(self._load_group)
        self.setLayout(layout)

    def add_sample(self, sample: TelemetrySample) -> None:
        """Route sample to the correct plot group."""
        if sample.source == "PSU":
            self._psu_group.add_sample(sample)
        else:
            self._load_group.add_sample(sample)

    def update_limits(self, limits: dict[str, LimitPair]) -> None:
        """Update dashed limit lines on both groups."""
        self._psu_group.update_limits(limits, "PSU")
        self._load_group.update_limits(limits, "LOAD")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_window_changed(self, index: int) -> None:
        self._window_seconds = _WINDOW_OPTIONS[index][1]

    def _refresh_plots(self) -> None:
        self._psu_group.refresh(self._window_seconds)
        self._load_group.refresh(self._window_seconds)

    def _on_plot_click(self, event, group: _PlotGroup, label: str) -> None:
        from PyQt6.QtCore import Qt
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
