"""BEACON-SIM desktop GUI (PySide6 + pyqtgraph)."""
from __future__ import annotations

import copy
import html
import math
import sys
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from .config import MOTIONS, PLATFORMS, PRESETS, SHAPES, STARTS, WEATHERS, Scenario, preset
from .sim import Simulation, WF_SCALE
from .tracker import ACQUIRE, COAST, LOCK, REACQUIRE, SEARCH
from .video_bench import VideoBenchmark

STATE_COL = {SEARCH: (130, 130, 140), ACQUIRE: (60, 180, 230), LOCK: (90, 200, 110), COAST: (70, 140, 235), REACQUIRE: (60, 80, 230)}
QSS = """
* { font-family: 'Segoe UI'; color: #e6e8ee; }
QMainWindow, QWidget#root { background: #14171c; }
QGroupBox { border: 1px solid #2e343d; border-radius: 8px; margin-top: 14px; padding: 8px; background: #1b1f26; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #ffe45c; }
QLabel#card { background: #1f242c; border: 1px solid #333a45; border-radius: 8px; padding: 6px 10px; }
QComboBox, QSpinBox { background: #252b34; border: 1px solid #3a414d; border-radius: 5px; padding: 3px 6px; }
QPushButton { background: #2a313b; border: 1px solid #3f4754; border-radius: 6px; padding: 7px 10px; font-weight: 600; }
QPushButton:hover { background: #343c48; }
QPushButton#primary { background: #ffe45c; color: #111; border: 2px solid #111; }
QPushButton#judge { background: #7c5cff; color: white; }
QSlider::groove:horizontal { height: 5px; background: #333a45; border-radius: 2px; }
QSlider::handle:horizontal { background: #ffe45c; width: 14px; margin: -5px 0; border-radius: 7px; }
QCheckBox::indicator { width: 15px; height: 15px; }
QTabWidget::pane { background: #1b1f26; border: 1px solid #333a45; border-radius: 6px; top: -1px; }
QTabWidget > QWidget, QTabWidget QWidget#qt_tabwidget_stackedwidget, QTabWidget QStackedWidget > QWidget { background: #1b1f26; }
QTabBar::tab { background: #252b34; color: #9aa3b2; padding: 5px 14px; border: 1px solid #333a45; border-bottom: none;
               border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 3px; font-weight: 600; }
QTabBar::tab:selected { background: #ffe45c; color: #111; }
QLineEdit, QDoubleSpinBox, QSpinBox { background: #252b34; border: 1px solid #3a414d; border-radius: 5px; padding: 2px 6px; color: #e6e8ee; }
QLabel { background: transparent; }
"""

# Scripted judge demo: (time_s, action, value)
JUDGE_SCRIPT = [
    (0.0, "preset", "SIH-OFFICIAL"), (0.0, "motion", "figure8"),
    (7.0, "noise", (0.10, 20.0, True)),
    (12.0, "occlude", 0.6),
    (15.0, "weather", "fog"), (15.0, "jitter", 10.0),
    (21.0, "motion", "random"), (21.0, "weather", "rain"),
    (27.0, "weather", "lowlight"), (27.0, "platform", ("linear", 6.0)),
    (33.0, "weather", "haze"), (33.0, "turbulence", 1e-14),
    (39.0, "end", None),
]


def np_to_pixmap(img: np.ndarray) -> QtGui.QPixmap:
    img = np.ascontiguousarray(img)
    h, w = img.shape[:2]
    if img.ndim == 2:
        q = QtGui.QImage(img.data, w, h, w, QtGui.QImage.Format_Grayscale8)
    else:
        q = QtGui.QImage(img.data, w, h, 3 * w, QtGui.QImage.Format_BGR888)
    return QtGui.QPixmap.fromImage(q.copy())


class Card(QtWidgets.QLabel):
    def __init__(self, title: str, spec: str):
        super().__init__()
        self.setObjectName("card")
        self.title, self.spec = title, spec
        self.setMinimumHeight(74)
        self.set("—", None)

    def set(self, value: str, ok: bool | None, sub: str = "") -> None:
        col = "#8a93a3" if ok is None else ("#5fd07a" if ok else "#ff6b5b")
        badge = "" if ok is None else ("PASS" if ok else "FAIL")
        self.setText(f"<div style='font-size:12px;color:#9aa3b2'>{self.title} <span style='float:right;color:{col};font-weight:700'>&nbsp;&nbsp;{badge}</span></div>"
                     f"<div style='font-size:26px;font-weight:700;color:{col if ok is not None else '#e6e8ee'}'>{value}</div>"
                     f"<div style='font-size:11px;color:#7d8696'>{html.escape(sub or self.spec)}</div>")


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, record_dir: str | None = None, judge: bool = False):
        super().__init__()
        self.setWindowTitle("BEACON-SIM — AI-based virtual camera tracking for FSOC coarse alignment (SIH26169)")
        self.record_dir = Path(record_dir) if record_dir else None
        self.recording = bool(record_dir)
        self.sim: Simulation | None = None
        self.bench: VideoBenchmark | None = None
        self.script: list = []
        self.err_hist, self.t_hist, self.state_hist = deque(maxlen=600), deque(maxlen=600), deque(maxlen=420)
        self.fps_hist = deque(maxlen=30)
        self.events: deque = deque(maxlen=5)
        self._last_state = None
        self.last_wall = time.perf_counter()
        self._build()
        self.setStyleSheet(QSS)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.reset("SIH-OFFICIAL")
        if judge:
            self.start_judge()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QtWidgets.QWidget(objectName="root")
        self.setCentralWidget(root)
        outer = QtWidgets.QVBoxLayout(root)
        outer.setContentsMargins(12, 8, 12, 10)
        # header
        hdr = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("<span style='font-size:26px;font-weight:800;color:#ffe45c'>BEACON-SIM</span>"
                                 "<span style='font-size:13px;color:#9aa3b2'>&nbsp;&nbsp;Virtual camera tracking · FSOC coarse alignment · ISRO SIH26169</span>")
        self.info = QtWidgets.QLabel()
        self.info.setStyleSheet("color:#b8c0cc;font-size:13px")
        self.badge = QtWidgets.QLabel()
        self.badge.setMinimumWidth(170)
        self.badge.setAlignment(QtCore.Qt.AlignCenter)
        hdr.addWidget(title)
        hdr.addStretch(1)
        hdr.addWidget(self.info)
        hdr.addSpacing(16)
        hdr.addWidget(self.badge)
        outer.addLayout(hdr)

        body = QtWidgets.QHBoxLayout()
        outer.addLayout(body, 1)
        # left: camera + overview + timeline
        left = QtWidgets.QVBoxLayout()
        self.cam = QtWidgets.QLabel()
        self.cam.setFixedSize(960, 720)
        self.cam.setStyleSheet("background:#000;border:2px solid #2e343d;border-radius:6px")
        left.addWidget(self.cam)
        low = QtWidgets.QHBoxLayout()
        self.overview = QtWidgets.QLabel()
        self.overview.setFixedSize(190, 190)
        self.overview.setStyleSheet("border:1px solid #2e343d")
        low.addWidget(self.overview)
        tl = QtWidgets.QVBoxLayout()
        tl.addWidget(QtWidgets.QLabel("<b style='color:#ffe45c'>Lock state timeline</b> <span style='color:#7d8696'>(last 14 s)</span>"))
        self.timeline = QtWidgets.QLabel()
        self.timeline.setFixedSize(752, 34)
        tl.addWidget(self.timeline)
        legend = "  ".join(f"<span style='color:rgb({c[2]},{c[1]},{c[0]})'>■</span> {s}" for s, c in STATE_COL.items())
        tl.addWidget(QtWidgets.QLabel(f"<span style='font-size:12px'>{legend}</span>"))
        self.status = QtWidgets.QLabel()
        self.status.setStyleSheet("color:#9aa3b2;font-size:12px")
        tl.addWidget(self.status)
        self.events_lbl = QtWidgets.QLabel()
        self.events_lbl.setStyleSheet("background:#1b1f26;border:1px solid #2e343d;border-radius:6px;padding:6px 10px;font-family:Consolas;font-size:11px")
        self.events_lbl.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self.events_lbl.setMinimumHeight(96)
        tl.addWidget(self.events_lbl, 1)
        self.status.hide()
        low.addLayout(tl, 1)
        left.addLayout(low)
        body.addLayout(left)

        # right: scorecard, chart, controls
        right = QtWidgets.QVBoxLayout()
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(8)
        self.cards = {
            "fps": Card("Processing speed", "spec ≥ 20 FPS"),
            "acq": Card("Acquisition time", "spec ≤ 2 s"),
            "err": Card("Tracking error (mean)", "spec ≤ 10 px"),
            "cent": Card("Centroid RMSE", "vs ground truth"),
            "ret": Card("Lock retention", "after first lock"),
            "loss": Card("Target loss", "spec < 5 %"),
            "reacq": Card("Re-acquisition (max)", "spec ≤ 1 s"),
            "t": Card("Simulation time", ""),
        }
        for i, c in enumerate(self.cards.values()):
            grid.addWidget(c, i // 2, i % 2)
        right.addLayout(grid)
        pg.setConfigOptions(antialias=True, background="#1b1f26", foreground="#9aa3b2")
        self.plot = pg.PlotWidget()
        self.plot.setFixedHeight(190)
        self.plot.setTitle("<span style='color:#ffe45c'>Tracking error (px)</span>")
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.setYRange(0, 30)
        self.curve = self.plot.plot(pen=pg.mkPen("#ffe45c", width=2))
        self.plot.addItem(pg.InfiniteLine(pos=10, angle=0, pen=pg.mkPen("#ff6b5b", width=1.5, style=QtCore.Qt.DashLine),
                                          label="limit 10 px", labelOpts={"color": "#ff6b5b", "position": 0.08}))
        right.addWidget(self.plot)

        self.ctl = self._build_editor()
        right.addWidget(self.ctl)
        btns = QtWidgets.QGridLayout()
        self.bt_run = QtWidgets.QPushButton("▶  Run", objectName="primary")
        bt_reset = QtWidgets.QPushButton("⟲  Reset")
        bt_occ = QtWidgets.QPushButton("Occlude beacon 0.6 s")
        bt_judge = QtWidgets.QPushButton("★  Judge demo", objectName="judge")
        bt_mp4 = QtWidgets.QPushButton("MP4 benchmark…")
        bt_exp = QtWidgets.QPushButton("Export performance log")
        for i, b in enumerate([self.bt_run, bt_reset, bt_judge, bt_occ, bt_mp4, bt_exp]):
            btns.addWidget(b, i // 3, i % 3)
        right.addLayout(btns)
        right.addStretch(1)
        body.addLayout(right, 1)

        self.bt_run.clicked.connect(self.toggle)
        bt_reset.clicked.connect(lambda: self.reset(self.cb_preset.currentText()))
        bt_occ.clicked.connect(self.occlude)
        bt_judge.clicked.connect(self.start_judge)
        bt_mp4.clicked.connect(self.open_mp4)
        bt_exp.clicked.connect(self.export)

    # ------------------------------------------------------------------ scenario editor
    # (section, object, attribute, label, kind, lo, hi, step, live, extra)
    #   kind: int | float | pct | bool | choice | cn2 | xy | waypoints ; live=False -> needs "Apply & restart"
    PARAMS = [
        ("Target", "target", "shape", "Shape (row 9)", "choice", 0, 0, 0, True, SHAPES),
        ("Target", "target", "size", "Size px (row 10)", "int", 2, 60, 1, True, None),
        ("Target", "target", "motion", "Motion (row 12)", "choice", 0, 0, 0, True, MOTIONS),
        ("Target", "target", "speed", "Speed px/s", "float", 0, 1000, 10, True, None),
        ("Target", "target", "brightness", "Brightness", "float", 20, 255, 5, True, None),
        ("Target", "target", "start", "Start (row 11)", "choice", 0, 0, 0, False, STARTS),
        ("Target", "target", "start_xy", "Start x, y", "xy", 0, 8000, 10, False, None),
        ("Target", "target", "count", "Targets (row 8)", "int", 1, 8, 1, False, None),
        ("Target", "target", "decoy_brightness", "Decoy level", "float", 0.1, 1.0, 0.05, True, None),
        ("Target", "target", "waypoints", "Waypoints", "waypoints", 0, 0, 0, True, None),
        ("Camera & mount", "camera", "screen_w", "Screen W (row 1)", "int", 800, 8000, 100, False, None),
        ("Camera & mount", "camera", "screen_h", "Screen H", "int", 800, 8000, 100, False, None),
        ("Camera & mount", "camera", "res_w", "Camera W (row 3)", "int", 160, 2048, 16, False, None),
        ("Camera & mount", "camera", "res_h", "Camera H", "int", 120, 2048, 16, False, None),
        ("Camera & mount", "camera", "fov_x_deg", "FOV x ° (row 4)", "float", 0.5, 60, 0.5, False, None),
        ("Camera & mount", "camera", "fov_y_deg", "FOV y °", "float", 0.5, 60, 0.5, False, None),
        ("Camera & mount", "camera", "rate_hz", "Frame Hz (row 5)", "float", 10, 240, 1, False, None),
        ("Camera & mount", "camera", "control_hz", "Control Hz (row 15)", "float", 5, 1000, 5, True, None),
        ("Camera & mount", "camera", "max_pan_dps", "Pan °/s (row 13)", "float", 0.5, 60, 0.5, True, None),
        ("Camera & mount", "camera", "max_tilt_dps", "Tilt °/s (row 14)", "float", 0.5, 60, 0.5, True, None),
        ("Camera & mount", "camera", "colour", "Colour camera (row 2)", "bool", 0, 0, 0, True, None),
        ("Camera & mount", "camera", "wide_field", "Wide-field cue", "bool", 0, 0, 0, True, None),
        ("Camera & mount", "", "imu_aid", "IMU feed-forward", "bool", 0, 0, 0, True, None),
        ("Disturbances", "disturb", "salt_pepper", "Salt & pepper %", "pct", 0, 50, 1, True, None),
        ("Disturbances", "disturb", "gaussian_sigma", "Gaussian σ", "float", 0, 60, 1, True, None),
        ("Disturbances", "disturb", "poisson", "Poisson noise", "bool", 0, 0, 0, True, None),
        ("Disturbances", "disturb", "jitter_px", "Jitter ±px/frame", "float", 0, 60, 1, True, None),
        ("Disturbances", "disturb", "weather", "Weather (21.4)", "choice", 0, 0, 0, True, WEATHERS),
        ("Disturbances", "disturb", "contrast", "Contrast ×", "float", 0.05, 2.0, 0.05, True, None),
        ("Disturbances", "disturb", "brightness", "Brightness ±", "float", -150, 150, 5, True, None),
        ("Disturbances", "disturb", "platform", "Platform (21.5)", "choice", 0, 0, 0, True, PLATFORMS),
        ("Disturbances", "disturb", "platform_px", "Platform ±px/frame", "float", 0, 60, 1, True, None),
        ("Disturbances", "disturb", "turbulence_cn2", "Turbulence Cn²", "cn2", 0, 0, 0, True, None),
    ]
    CN2 = [("off", 0.0), ("weak 1e-15", 1e-15), ("moderate 1e-14", 1e-14), ("strong 5e-14", 5e-14)]

    def _build_editor(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Scenario editor  ·  every official parameter")
        v = QtWidgets.QVBoxLayout(box)
        v.setContentsMargins(8, 14, 8, 6)
        top = QtWidgets.QHBoxLayout()
        self.cb_preset = QtWidgets.QComboBox()
        self.cb_preset.addItems(PRESETS)
        self.cb_preset.activated.connect(lambda _: self.reset(self.cb_preset.currentText()))
        self.sp_seed = QtWidgets.QSpinBox()
        self.sp_seed.setRange(0, 99999)
        self.sp_seed.setPrefix("seed ")
        bt_load = QtWidgets.QPushButton("Load…")
        bt_save = QtWidgets.QPushButton("Save…")
        self.bt_apply = QtWidgets.QPushButton("Apply && restart")
        bt_load.clicked.connect(self.load_scenario)
        bt_save.clicked.connect(self.save_scenario)
        self.bt_apply.clicked.connect(self.apply_restart)
        for w in (QtWidgets.QLabel("Preset"), self.cb_preset, self.sp_seed, bt_load, bt_save, self.bt_apply):
            top.addWidget(w)
        top.setStretch(1, 1)
        v.addLayout(top)
        tabs = QtWidgets.QTabWidget()
        self.widgets: dict[str, QtWidgets.QWidget] = {}
        grids: dict[str, QtWidgets.QGridLayout] = {}
        counts: dict[str, int] = {}
        for sec, obj, attr, label, kind, lo, hi, step, live, extra in self.PARAMS:
            if sec not in grids:
                page = QtWidgets.QWidget()
                grids[sec] = QtWidgets.QGridLayout(page)
                grids[sec].setContentsMargins(6, 6, 6, 4)
                grids[sec].setHorizontalSpacing(8)
                grids[sec].setVerticalSpacing(4)
                tabs.addTab(page, sec.replace("&", "&&"))
                counts[sec] = 0
            w = self._make_widget(kind, lo, hi, step, extra)
            key = f"{obj}.{attr}"
            self.widgets[key] = w
            self._connect(w, kind, lambda *_, k=key: self._on_param(k))
            i = counts[sec]
            span = 3 if kind == "waypoints" else 1
            if span == 3 and i % 2:
                i += 1
            r, c = divmod(i, 2)
            lab = QtWidgets.QLabel(label + ("" if live else " ⟲"))
            lab.setToolTip("applies live" if live else "applies after 'Apply & restart'")
            grids[sec].addWidget(lab, r, c * 2)
            grids[sec].addWidget(w, r, c * 2 + 1, 1, span)
            counts[sec] = i + (2 if span == 3 else 1)
        for g in grids.values():
            g.setColumnStretch(1, 1)
            g.setColumnStretch(3, 1)
        v.addWidget(tabs)
        self.feas = QtWidgets.QLabel()
        self.feas.setWordWrap(True)
        self.feas.setStyleSheet("font-size:11px")
        v.addWidget(self.feas)
        return box

    def _make_widget(self, kind, lo, hi, step, extra):
        if kind == "choice":
            w = QtWidgets.QComboBox()
            w.addItems(extra)
        elif kind == "cn2":
            w = QtWidgets.QComboBox()
            w.addItems([n for n, _ in self.CN2])
        elif kind == "bool":
            w = QtWidgets.QCheckBox()
        elif kind == "int":
            w = QtWidgets.QSpinBox()
            w.setRange(int(lo), int(hi))
            w.setSingleStep(int(step))
        elif kind == "xy":
            w = QtWidgets.QLineEdit()
            w.setPlaceholderText("x, y")
        elif kind == "waypoints":
            w = QtWidgets.QLineEdit()
            w.setPlaceholderText("x1,y1; x2,y2; …  (user-defined path)")
        else:
            w = QtWidgets.QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setSingleStep(step)
            w.setDecimals(2 if step < 1 else 1)
        return w

    @staticmethod
    def _connect(w, kind, fn):
        if isinstance(w, QtWidgets.QComboBox):
            w.currentTextChanged.connect(fn)
        elif isinstance(w, QtWidgets.QCheckBox):
            w.toggled.connect(fn)
        elif isinstance(w, QtWidgets.QLineEdit):
            w.editingFinished.connect(fn)
        else:
            w.valueChanged.connect(fn)

    def _spec(self, key):
        return next(p for p in self.PARAMS if f"{p[1]}.{p[2]}" == key)

    @staticmethod
    def _owner(sc: Scenario, obj: str):
        return getattr(sc, obj) if obj else sc

    def _read(self, key):
        _, obj, attr, _, kind, *_ = self._spec(key)
        w = self.widgets[key]
        if kind == "choice":
            return w.currentText()
        if kind == "cn2":
            return self.CN2[w.currentIndex()][1]
        if kind == "bool":
            return w.isChecked()
        if kind == "pct":
            return w.value() / 100.0
        if kind == "int":
            return int(w.value())
        if kind in ("xy", "waypoints"):
            try:
                pts = [[float(a) for a in part.split(",")] for part in w.text().split(";") if part.strip()]
                pts = [q for q in pts if len(q) == 2]
            except ValueError:
                return None
            return (pts[0] if pts else None) if kind == "xy" else (pts if len(pts) >= 2 else None)
        return float(w.value())

    def _write(self, key, value):
        _, obj, attr, _, kind, *_ = self._spec(key)
        w = self.widgets[key]
        if kind == "choice":
            w.setCurrentText(str(value))
        elif kind == "cn2":
            w.setCurrentIndex(min(range(len(self.CN2)), key=lambda i: abs(self.CN2[i][1] - value)))
        elif kind == "bool":
            w.setChecked(bool(value))
        elif kind == "pct":
            w.setValue(value * 100.0)
        elif kind == "xy":
            w.setText(f"{value[0]:.0f}, {value[1]:.0f}")
        elif kind == "waypoints":
            w.setText("; ".join(f"{x:.0f},{y:.0f}" for x, y in value))
        else:
            w.setValue(value)

    def reset(self, name: str) -> None:
        sc = preset(name)
        sc.seed = self.sp_seed.value() if hasattr(self, "sp_seed") and self.sim is not None else sc.seed
        self._start(sc)

    def _start(self, sc: Scenario) -> None:
        self.bench = None
        self.ctl.setEnabled(True)
        self.sim = Simulation(sc)
        self.edit_sc = copy.deepcopy(self.sim.sc)
        self.err_hist.clear(), self.t_hist.clear(), self.state_hist.clear()
        self.events.clear()
        self._last_state = None
        self._event(0.0, f"scenario {sc.name} loaded (seed {sc.seed}, config {sc.hash()})", '#9aa3b2')
        for wmsg in self.sim.warnings:
            self._event(0.0, "param: " + wmsg, "#ffb35c")
        self._load_controls(self.sim.sc)
        self.render()

    def _load_controls(self, sc: Scenario) -> None:
        self.edit_sc = copy.deepcopy(sc)
        for w in list(self.widgets.values()) + [self.cb_preset, self.sp_seed]:
            w.blockSignals(True)
        if sc.name in PRESETS:
            self.cb_preset.setCurrentText(sc.name)
        self.sp_seed.setValue(int(sc.seed))
        for key in self.widgets:
            _, obj, attr, *_ = self._spec(key)
            self._write(key, getattr(self._owner(sc, obj), attr))
        for w in list(self.widgets.values()) + [self.cb_preset, self.sp_seed]:
            w.blockSignals(False)
        self._pending(False)
        self._update_feasibility()

    def _on_param(self, key):
        if not self.sim:
            return
        _, obj, attr, _, kind, lo, hi, step, live, extra = self._spec(key)
        val = self._read(key)
        if val is None:
            return
        setattr(self._owner(self.edit_sc, obj), attr, val)
        if not self.edit_sc.name.endswith("*"):
            self.edit_sc.name += "*"  # edited copy of a preset
        if not live:
            self._pending(True)
        else:
            sc = self.sim.sc
            setattr(self._owner(sc, obj), attr, val)
            if attr == "size":
                self.sim.det.size = int(val)
            elif attr in ("max_pan_dps", "max_tilt_dps"):
                self.sim.ctl = type(self.sim.ctl)(sc.camera)
            elif attr == "wide_field":
                self.sim.wide_field_cue = bool(val)
            self.sim.retune()
            self._event(self.sim.t, f"set {attr} = {val}", "#b59cff")
        self._update_feasibility()

    def apply_controls(self, *_):  # kept for the scripted judge demo
        if self.sim:
            self.sim.retune()

    def _pending(self, on: bool) -> None:
        self.bt_apply.setStyleSheet("background:#ffb35c;color:#111;border:2px solid #111" if on else "")

    def apply_restart(self):
        sc = copy.deepcopy(self.edit_sc)
        sc.seed = self.sp_seed.value()
        self._start(sc)

    def _update_feasibility(self):
        from .feasibility import analyse
        f = analyse(copy.deepcopy(self.edit_sc))
        if f["acquisition_guaranteed"]:
            self.feas.setText(f"<span style='color:#5fd07a'>✓ physically feasible</span> <span style='color:#7d8696'>· slew {f['slew_px_s']:.0f} px/s, "
                              f"needed {f['required_px_s']:.0f} px/s, worst-case acquisition {f['worst_case_acquisition_s']} s</span>")
        else:
            self.feas.setText("<span style='color:#ffb35c'>⚠ " + html.escape(" · ".join(f["notes"])) + "</span>")

    def load_scenario(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Scenario (.yaml)", "scenarios", "YAML (*.yaml *.yml)")
        if path:
            self._start(Scenario.load(path))

    def save_scenario(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save scenario", f"scenarios/{self.edit_sc.name.lower()}_custom.yaml", "YAML (*.yaml)")
        if path:
            sc = copy.deepcopy(self.edit_sc)
            sc.seed = self.sp_seed.value()
            sc.save(path)
            self._event(self.sim.t if self.sim else 0.0, f"scenario saved: {Path(path).name}", "#9aa3b2")

    def occlude(self):
        if self.sim:
            self.sim.target.cfg.occlusions.append([self.sim.t, 0.6])

    def toggle(self):
        if self.timer.isActive():
            self.timer.stop()
            self.bt_run.setText("▶  Run")
        else:
            self.timer.start(0 if self.record_dir else 33)
            self.bt_run.setText("⏸  Pause")

    def start_judge(self):
        self.reset("SIH-OFFICIAL")
        self.sim.sc.target.occlusions = []
        self.script = list(JUDGE_SCRIPT)
        if not self.timer.isActive():
            self.toggle()

    def open_mp4(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Grader video (.mp4)", "", "Video (*.mp4 *.avi *.mov)")
        if path:
            self.load_mp4(path)

    def load_mp4(self, path: str, gt: str | None = None):
        if gt is None:
            cand = Path(path).with_name(Path(path).stem + "_gt.csv")
            gt = str(cand) if cand.exists() else None
        self.bench = VideoBenchmark(path, gt)
        self.script = []
        self.ctl.setEnabled(False)
        self.err_hist.clear(), self.t_hist.clear(), self.state_hist.clear()
        self.events.clear()
        self._last_state = None
        self._event(0.0, f"MP4 loaded: {Path(path).name} ({self.bench.n_frames} frames, GT {'yes' if gt else 'no'})", '#b59cff')
        if not self.timer.isActive():
            self.toggle()

    def export(self):
        out = Path("runs") / time.strftime("%Y%m%d_%H%M%S")
        s = self.bench.write(out, "run") if self.bench else self.sim.log.write(out, "run")
        self.status.show()
        self.status.setText(f"Performance log written to {out.resolve()}  ·  all specs met: {s.get('all_pass')}")

    def _run_script(self):
        while self.script and self.sim and self.sim.t >= self.script[0][0]:
            _, act, val = self.script.pop(0)
            if act not in ("preset", "end"):
                self._event(self.sim.t, f"inject {act} = {val}", '#b59cff')
            d = self.sim.sc.disturb
            if act == "motion":
                self.sim.sc.target.motion = val
            elif act == "noise":
                d.salt_pepper, d.gaussian_sigma, d.poisson = val
            elif act == "occlude":
                self.sim.target.cfg.occlusions.append([self.sim.t, val])
            elif act == "weather":
                d.weather = val
            elif act == "jitter":
                d.jitter_px = val
            elif act == "platform":
                d.platform, d.platform_px = val
            elif act == "turbulence":
                d.turbulence_cn2 = val
            elif act == "end":
                self.toggle()
                self.export()
            self.sim.retune()
            self._load_controls(self.sim.sc)

    # ------------------------------------------------------------------ loop
    def tick(self):
        if self.bench:
            if self.bench.step() is None:
                self.toggle()
                self.export()
                return
        else:
            self._run_script()
            if not self.timer.isActive():
                return
            self.sim.step()
        now = time.perf_counter()
        self.fps_hist.append(now - self.last_wall)
        self.last_wall = now
        self.render()
        if self.record_dir:
            self.record_dir.mkdir(parents=True, exist_ok=True)
            n = len(list(self.record_dir.glob("*.png"))) if not hasattr(self, "_rec_n") else self._rec_n
            self._rec_n = n + 1
            self.grab().save(str(self.record_dir / f"{n:05d}.png"))

    def render(self):
        if self.bench:
            return self._render_bench()
        L = self.sim.last
        cam = self.sim.sc.camera
        if not L:
            frame = np.zeros((cam.res_h, cam.res_w), np.uint8)
            L = dict(state=SEARCH, det=None, pred=None, cue=None, visible=True, track_err=0.0, t=0.0, proc_ms=0.0, los=self.sim.mount, true_pos=self.sim.target.pos)
        else:
            frame = L["frame"]
        src = L.get("frame_colour") if L.get("frame_colour") is not None else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        # letterbox any camera resolution into the 960 x 720 view
        k = min(960 / cam.res_w, 720 / cam.res_h)
        vw, vh = int(cam.res_w * k), int(cam.res_h * k)
        img = np.zeros((720, 960, 3), np.uint8)
        ox, oy = (960 - vw) // 2, (720 - vh) // 2
        img[oy:oy + vh, ox:ox + vw] = cv2.resize(src, (vw, vh), interpolation=cv2.INTER_NEAREST)
        c = (ox + vw // 2, oy + vh // 2)
        P = lambda x, y: (int(ox + x * k), int(oy + y * k))  # noqa: E731  camera px -> view px
        state = L["state"]
        col = STATE_COL[state]
        cv2.line(img, (c[0] - 26, c[1]), (c[0] + 26, c[1]), (90, 220, 120), 2)
        cv2.line(img, (c[0], c[1] - 26), (c[0], c[1] + 26), (90, 220, 120), 2)
        cv2.circle(img, c, int(10 * k), (90, 220, 120), 1)
        if L.get("pred") is not None and state != SEARCH:
            p = P(*L["pred"])
            g = int(self.sim.trk.gate() * k)
            cv2.circle(img, p, min(g, 600), (160, 120, 60), 1)
        det = L.get("det")
        if det is not None:
            d = P(det.x, det.y)
            cv2.rectangle(img, (d[0] - 20, d[1] - 20), (d[0] + 20, d[1] + 20), (92, 228, 255), 2)
            cv2.line(img, c, d, (92, 228, 255), 1)
            cv2.putText(img, f"centroid ({det.x:.2f}, {det.y:.2f})  SNR {det.snr:.0f}", (d[0] + 26, d[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (92, 228, 255), 1, cv2.LINE_AA)
        hud = (f"t {L['t']:5.1f} s   FOV {cam.fov_x_deg:g}x{cam.fov_y_deg:g} deg   {cam.res_w}x{cam.res_h} {'colour' if cam.colour else 'mono'}   "
               f"{cam.rate_hz:g} Hz   err {L['track_err']:.1f} px ({L['track_err'] * cam.urad_per_px:.0f} urad)")
        cv2.rectangle(img, (0, 0), (960, 40), (20, 20, 24), -1)
        cv2.putText(img, hud, (14, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 232, 238), 1, cv2.LINE_AA)
        if state in (COAST, REACQUIRE) or (state == SEARCH and L["t"] > 0.1):
            msg = {COAST: "BEACON LOST - COASTING ON KALMAN", REACQUIRE: "RE-ACQUIRING", SEARCH: "SEARCHING - WIDE-FIELD CUE"}[state]
            cv2.rectangle(img, (0, 680), (960, 720), (40, 40, 200) if state != SEARCH else (80, 80, 80), -1)
            cv2.putText(img, msg, (14, 708), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)
        self.cam.setPixmap(np_to_pixmap(img))
        self._overview(L)
        self._common(state, L["t"], L["track_err"] if L.get("visible", True) else float("nan"), self.sim.log, L["proc_ms"])
        sc = self.sim.sc
        self.info.setText(f"Scenario <b>{sc.name}</b> · seed {sc.seed} · motion <b>{sc.target.motion}</b> · weather <b>{sc.disturb.weather}</b>")

    def _render_bench(self):
        L = self.bench.last
        if not L:
            return
        g = L["image"]
        cx, cy = L["center"]
        vw, vh = 640, 480
        x0, y0 = int(cx - vw / 2), int(cy - vh / 2)
        pad = cv2.copyMakeBorder(g, vh, vh, vw, vw, cv2.BORDER_CONSTANT, value=0)
        crop = pad[y0 + vh:y0 + 2 * vh, x0 + vw:x0 + 2 * vw]
        img = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR), (960, 720), interpolation=cv2.INTER_NEAREST)
        k = 1.5
        cv2.line(img, (454, 360), (506, 360), (90, 220, 120), 2)
        cv2.line(img, (480, 334), (480, 386), (90, 220, 120), 2)
        det = L["det"]
        if det is not None:
            d = (int((det.x - x0) * k), int((det.y - y0) * k))
            cv2.rectangle(img, (d[0] - 20, d[1] - 20), (d[0] + 20, d[1] + 20), (92, 228, 255), 2)
            txt = f"centroid ({det.x:.2f}, {det.y:.2f})" + (f"  err {L['cent_err']:.2f} px" if L["cent_err"] is not None else "")
            cv2.putText(img, txt, (d[0] + 26, d[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (92, 228, 255), 1, cv2.LINE_AA)
        if L["gt"] is not None:
            gx, gy = (int((L["gt"][0] - x0) * k), int((L["gt"][1] - y0) * k))
            cv2.drawMarker(img, (gx, gy), (80, 80, 255), cv2.MARKER_TILTED_CROSS, 14, 1)
        cv2.rectangle(img, (0, 0), (960, 40), (40, 30, 90), -1)
        cv2.putText(img, f"MP4 BENCHMARK - PTZ BYPASSED   {self.bench.W}x{self.bench.H} @ {self.bench.fps:.0f} fps   frame {L['frame_no']}/{self.bench.n_frames}",
                    (14, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        self.cam.setPixmap(np_to_pixmap(img))
        small = cv2.resize(g, (190, 190), interpolation=cv2.INTER_AREA)
        ov = cv2.cvtColor(cv2.normalize(small, None, 0, 255, cv2.NORM_MINMAX), cv2.COLOR_GRAY2BGR)
        s = 190 / max(self.bench.W, self.bench.H)
        cv2.rectangle(ov, (int(x0 * s), int(y0 * s)), (int((x0 + vw) * s), int((y0 + vh) * s)), (92, 228, 255), 1)
        self.overview.setPixmap(np_to_pixmap(ov))
        self._common(L["state"], L["t"], L["cent_err"] if L["cent_err"] is not None else float("nan"), self.bench.log, L["proc_ms"])
        self.info.setText(f"Input <b>{self.bench.log.meta['scenario']}</b> · ground truth: <b>{'yes' if self.bench.gt else 'no'}</b>")

    def _overview(self, L):
        sc = self.sim.sc.camera
        s = 190 / max(sc.screen_w, sc.screen_h)
        ov = cv2.resize(self.sim.renderer.bg, (int(sc.screen_w * s), int(sc.screen_h * s)), interpolation=cv2.INTER_AREA)
        ov = cv2.cvtColor(np.clip(ov * 3, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        pts = [(int(x * s), int(y * s)) for x, y in self.sim.trail]
        for a, b in zip(pts, pts[1:]):
            cv2.line(ov, a, b, (60, 90, 255), 1)
        if pts:
            cv2.circle(ov, pts[-1], 3, (60, 90, 255), -1)
        for dp in L.get("decoys") or []:
            cv2.circle(ov, (int(dp[0] * s), int(dp[1] * s)), 2, (150, 150, 150), -1)
        los = L["los"]
        hw, hh = sc.res_w / 2, sc.res_h / 2
        cv2.rectangle(ov, (int((los[0] - hw) * s), int((los[1] - hh) * s)), (int((los[0] + hw) * s), int((los[1] + hh) * s)), (92, 228, 255), 1)
        if L.get("cue") is not None:
            cv2.drawMarker(ov, (int(L["cue"][0] * s), int(L["cue"][1] * s)), (255, 120, 255), cv2.MARKER_CROSS, 10, 1)
        ov = cv2.copyMakeBorder(ov, 0, 190 - ov.shape[0], 0, 190 - ov.shape[1], cv2.BORDER_CONSTANT, value=(20, 23, 28))
        cv2.putText(ov, f"SCREEN {sc.screen_w}x{sc.screen_h}", (4, 184), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (200, 200, 200), 1, cv2.LINE_AA)
        self.overview.setPixmap(np_to_pixmap(ov))

    def _event(self, t: float, msg: str, col: str) -> None:
        self.events.append(f"<span style='color:#7d8696'>{t:6.2f}s</span>&nbsp; <span style='color:{col}'>{html.escape(msg)}</span>")
        self.events_lbl.setText("<b style='color:#ffe45c;font-family:Segoe UI'>Event log</b><br>" + "<br>".join(self.events))

    def _common(self, state, t, err, log, proc_ms):
        if state != self._last_state:
            c = STATE_COL[state]
            self._event(t, f"state -> {state}", f"rgb({c[2]},{c[1]},{c[0]})")
            self._last_state = state
        col = STATE_COL[state]
        self.badge.setText(f"● {state}")
        self.badge.setStyleSheet(f"background: rgb({col[2]},{col[1]},{col[0]}); color:white; font-weight:800; font-size:16px; border-radius:8px; padding:6px 14px")
        self.t_hist.append(t)
        self.err_hist.append(err)
        self.state_hist.append(state)
        self.curve.setData(np.array(self.t_hist), np.nan_to_num(np.array(self.err_hist), nan=0.0))
        strip = np.zeros((34, 752, 3), np.uint8)
        n = len(self.state_hist)
        wseg = 752 / 420
        for i, s in enumerate(self.state_hist):
            x = int((420 - n + i) * wseg)
            strip[:, x:x + int(math.ceil(wseg)) + 1] = STATE_COL[s]
        self.timeline.setPixmap(np_to_pixmap(strip))
        if len(log.rows) % 10 == 1 or not self.timer.isActive():
            s = log.summary()
            if s:
                P = s["pass"]
                self.cards["fps"].set(f"{s['processing_fps']:.0f} FPS", P["processing_fps"], f"{s['processing_ms_mean']:.1f} ms/frame · p95 {s['processing_ms_p95']:.1f}")
                acq = s["acquisition_time_s"]
                self.cards["acq"].set("—" if acq != acq else f"{acq:.2f} s", None if acq != acq else P["acquisition_time_s"])
                e = s["mean_tracking_error_px"]
                self.cards["err"].set("—" if e != e else f"{e:.1f} px", None if e != e else P["mean_tracking_error_px"],
                                      "" if e != e else f"{s['mean_tracking_error_urad']:.0f} µrad · max {s['max_tracking_error_px']:.0f} px")
                r = s["centroid_rmse_px"]
                self.cards["cent"].set("—" if r != r else f"{r:.2f} px", None, "sub-pixel centroid vs ground truth")
                self.cards["ret"].set(f"{s['lock_retention_pct']:.1f} %", None)
                self.cards["loss"].set(f"{s['target_loss_pct']:.1f} %", P["target_loss_pct"])
                self.cards["reacq"].set(f"{s['max_reacquisition_s']:.2f} s", P["max_reacquisition_s"], f"{s['reacquisitions']} re-acquisitions")
        sub = f"frame {len(log.rows)} · 30 Hz sim clock" if self.recording else (f"{1 / max(np.mean(self.fps_hist), 1e-3):.0f} FPS end-to-end (render + track + GUI)" if self.fps_hist else "")
        self.cards["t"].set(f"{t:.1f} s", None, sub)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", help="save a PNG of the window every frame (for demo videos)")
    ap.add_argument("--judge", action="store_true", help="start the scripted judge demo immediately")
    ap.add_argument("--mp4", help="start in MP4 benchmark mode with this video")
    a = ap.parse_args(argv)
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow(a.record, a.judge)
    w.resize(1780, 990)
    w.show()
    if a.mp4:
        w.load_mp4(a.mp4)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
