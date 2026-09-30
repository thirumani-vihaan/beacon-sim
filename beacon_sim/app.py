"""BEACON-SIM desktop GUI (PySide6 + pyqtgraph)."""
from __future__ import annotations

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

from .config import PRESETS, Scenario, preset
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

        ctl = QtWidgets.QGroupBox("Scenario && disturbances (live)")
        f = QtWidgets.QGridLayout(ctl)
        self.cb_preset = QtWidgets.QComboBox()
        self.cb_preset.addItems(PRESETS)
        self.cb_motion = QtWidgets.QComboBox()
        self.cb_motion.addItems(["line", "circle", "figure8", "random", "spiral", "sine"])
        self.cb_weather = QtWidgets.QComboBox()
        self.cb_weather.addItems(["clear", "haze", "fog", "rain", "lowlight"])
        self.cb_platform = QtWidgets.QComboBox()
        self.cb_platform.addItems(["none", "linear", "circular", "random", "figure8"])
        self.sl_speed = self._slider(20, 300, 120)
        self.sl_sp = self._slider(0, 10, 0)
        self.sl_sigma = self._slider(0, 20, 0)
        self.sl_jit = self._slider(0, 20, 0)
        self.sl_plat = self._slider(0, 20, 0)
        self.ck_poisson = QtWidgets.QCheckBox("Poisson")
        self.ck_turb = QtWidgets.QCheckBox("Turbulence (Cn² 1e-14)")
        self.ck_imu = QtWidgets.QCheckBox("IMU feed-forward (platform + jitter)")
        rows = [("Preset", self.cb_preset), ("Target motion", self.cb_motion), ("Speed (px/s)", self.sl_speed),
                ("Salt & pepper (%)", self.sl_sp), ("Gaussian σ", self.sl_sigma), ("Jitter (±px/frame)", self.sl_jit),
                ("Weather", self.cb_weather), ("Platform motion", self.cb_platform), ("Platform (px/frame)", self.sl_plat)]
        for r, (lab, w) in enumerate(rows):
            f.addWidget(QtWidgets.QLabel(lab), r, 0)
            f.addWidget(w, r, 1)
        f.addWidget(self.ck_poisson, len(rows), 0)
        f.addWidget(self.ck_turb, len(rows), 1)
        f.addWidget(self.ck_imu, len(rows) + 1, 0, 1, 2)
        right.addWidget(ctl)
        self.ctl = ctl
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
        self.cb_preset.activated.connect(lambda _: self.reset(self.cb_preset.currentText()))
        for w in (self.cb_motion, self.cb_weather, self.cb_platform):
            w.currentTextChanged.connect(self.apply_controls)
        for w in (self.sl_speed, self.sl_sp, self.sl_sigma, self.sl_jit, self.sl_plat):
            w.valueChanged.connect(self.apply_controls)
        for w in (self.ck_poisson, self.ck_turb, self.ck_imu):
            w.toggled.connect(self.apply_controls)

    def _slider(self, lo, hi, v) -> QtWidgets.QSlider:
        s = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(v)
        return s

    # ------------------------------------------------------------------ control
    def reset(self, name: str) -> None:
        self.bench = None
        self.ctl.setEnabled(True)
        sc = preset(name)
        self.sim = Simulation(sc)
        self.err_hist.clear(), self.t_hist.clear(), self.state_hist.clear()
        self.events.clear()
        self._last_state = None
        self._event(0.0, f"scenario {sc.name} loaded (seed {sc.seed})", '#9aa3b2')
        self._load_controls(sc)
        self.render()

    def _load_controls(self, sc: Scenario) -> None:
        widgets = [self.cb_preset, self.cb_motion, self.cb_weather, self.cb_platform, self.sl_speed, self.sl_sp,
                   self.sl_sigma, self.sl_jit, self.sl_plat, self.ck_poisson, self.ck_turb, self.ck_imu]
        for w in widgets:
            w.blockSignals(True)
        self.cb_preset.setCurrentText(sc.name)
        self.cb_motion.setCurrentText(sc.target.motion)
        self.cb_weather.setCurrentText(sc.disturb.weather)
        self.cb_platform.setCurrentText(sc.disturb.platform)
        self.sl_speed.setValue(int(sc.target.speed))
        self.sl_sp.setValue(int(round(sc.disturb.salt_pepper * 100)))
        self.sl_sigma.setValue(int(sc.disturb.gaussian_sigma))
        self.sl_jit.setValue(int(sc.disturb.jitter_px))
        self.sl_plat.setValue(int(sc.disturb.platform_px))
        self.ck_poisson.setChecked(sc.disturb.poisson)
        self.ck_turb.setChecked(sc.disturb.turbulence_cn2 > 0)
        self.ck_imu.setChecked(sc.imu_aid)
        for w in widgets:
            w.blockSignals(False)

    def apply_controls(self, *_):
        if not self.sim:
            return
        sc = self.sim.sc
        sc.target.motion = self.cb_motion.currentText()
        sc.target.speed = float(self.sl_speed.value())
        d = sc.disturb
        d.weather, d.platform = self.cb_weather.currentText(), self.cb_platform.currentText()
        d.salt_pepper, d.gaussian_sigma = self.sl_sp.value() / 100, float(self.sl_sigma.value())
        d.jitter_px, d.platform_px, d.poisson = float(self.sl_jit.value()), float(self.sl_plat.value()), self.ck_poisson.isChecked()
        d.turbulence_cn2 = 1e-14 if self.ck_turb.isChecked() else 0.0
        sc.imu_aid = self.ck_imu.isChecked()
        self.sim.retune()

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
        log = self.bench.log if self.bench else self.sim.log
        out = Path("runs") / time.strftime("%Y%m%d_%H%M%S")
        s = log.write(out, "run")
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
        if not L:
            frame = np.zeros((480, 640), np.uint8)
            L = dict(state=SEARCH, det=None, pred=None, cue=None, visible=True, track_err=0.0, t=0.0, proc_ms=0.0, los=self.sim.mount, true_pos=self.sim.target.pos)
        else:
            frame = L["frame"]
        img = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        img = cv2.resize(img, (960, 720), interpolation=cv2.INTER_NEAREST)
        k = 1.5
        c = (480, 360)
        state = L["state"]
        col = STATE_COL[state]
        cv2.line(img, (c[0] - 26, c[1]), (c[0] + 26, c[1]), (90, 220, 120), 2)
        cv2.line(img, (c[0], c[1] - 26), (c[0], c[1] + 26), (90, 220, 120), 2)
        cv2.circle(img, c, int(10 * k), (90, 220, 120), 1)
        if L.get("pred") is not None and state != SEARCH:
            p = (int(L["pred"][0] * k), int(L["pred"][1] * k))
            g = int(self.sim.trk.gate() * k)
            cv2.circle(img, p, min(g, 600), (160, 120, 60), 1)
        det = L.get("det")
        if det is not None:
            d = (int(det.x * k), int(det.y * k))
            cv2.rectangle(img, (d[0] - 20, d[1] - 20), (d[0] + 20, d[1] + 20), (92, 228, 255), 2)
            cv2.line(img, c, d, (92, 228, 255), 1)
            cv2.putText(img, f"centroid ({det.x:.2f}, {det.y:.2f})  SNR {det.snr:.0f}", (d[0] + 26, d[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (92, 228, 255), 1, cv2.LINE_AA)
        hud = f"t {L['t']:5.1f} s   FOV 4.0x3.0 deg   640x480 mono   30 Hz   err {L['track_err']:.1f} px ({L['track_err'] * self.sim.sc.camera.urad_per_px:.0f} urad)"
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
        s = 190 / sc.screen_w
        ov = cv2.resize(self.sim.renderer.bg, (190, 190), interpolation=cv2.INTER_AREA)
        ov = cv2.cvtColor(np.clip(ov * 3, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        pts = [(int(x * s), int(y * s)) for x, y in self.sim.trail]
        for a, b in zip(pts, pts[1:]):
            cv2.line(ov, a, b, (60, 90, 255), 1)
        if pts:
            cv2.circle(ov, pts[-1], 3, (60, 90, 255), -1)
        los = L["los"]
        cv2.rectangle(ov, (int((los[0] - 320) * s), int((los[1] - 240) * s)), (int((los[0] + 320) * s), int((los[1] + 240) * s)), (92, 228, 255), 1)
        if L.get("cue") is not None:
            cv2.drawMarker(ov, (int(L["cue"][0] * s), int(L["cue"][1] * s)), (255, 120, 255), cv2.MARKER_CROSS, 10, 1)
        cv2.putText(ov, "SCREEN 2000x2000", (4, 184), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (200, 200, 200), 1, cv2.LINE_AA)
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
