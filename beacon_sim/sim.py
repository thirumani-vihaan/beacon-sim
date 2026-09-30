"""Simulation engine: target + platform + pan-tilt mount + camera render + detection + tracking + control + logging.

Deterministic: the whole run is driven by one seeded numpy Generator, so (scenario, seed) always reproduces the
same frames and the same metrics.
"""
from __future__ import annotations

import math
import time

import cv2
import numpy as np

from .config import Scenario
from .control import PanTiltController
from .detect import BeaconDetector
from .metrics import PerfLog
from .scene import Renderer, Target
from .tracker import ACQUIRE, COAST, LOCK, REACQUIRE, SEARCH, Tracker

WF_SCALE = 8  # wide-field acquisition sensor sees the whole screen at 1/8 resolution (250 x 250)


class Simulation:
    def __init__(self, sc: Scenario, wide_field_cue: bool = True):
        self.sc = sc
        self.rng = np.random.default_rng(sc.seed)
        c = sc.camera
        self.dt = 1.0 / c.rate_hz
        self.half = np.array([c.res_w / 2, c.res_h / 2])
        self.target = Target(sc, self.rng)
        self.renderer = Renderer(sc, self.rng)
        self.det = BeaconDetector(sc.target.size)
        self.wf_det = BeaconDetector(2, k_sigma=5.0, min_snr=7.0, median=False)
        self.trk = Tracker(self.dt, meas_sigma=self._meas_sigma(), accel_sigma=300.0)
        self.ctl = PanTiltController(c)
        self.wide_field_cue = wide_field_cue
        self.mount = np.array([c.screen_w / 2, c.screen_h / 2], float)  # official row 6: start at screen centre
        self.plat = np.zeros(2)
        self.plat_v = np.zeros(2)
        self.plat_est = np.zeros(2)  # IMU-integrated platform offset (drifts slowly)
        self.plat_v_est = np.zeros(2)
        self.t, self.frame_no = 0.0, 0
        self.log = PerfLog(c.urad_per_px, {"scenario": sc.name, "seed": sc.seed, "config_hash": sc.hash()})
        self.wf_bg = cv2.resize(self.renderer.bg, (c.screen_w // WF_SCALE, c.screen_h // WF_SCALE), interpolation=cv2.INTER_AREA)
        self.trail: list[tuple[float, float]] = []
        self.last = {}

    # ------------------------------------------------------------------
    def _platform(self) -> None:
        d, dt = self.sc.disturb, self.dt
        amp = d.platform_px * self.sc.camera.rate_hz  # px/frame -> px/s
        if d.platform == "linear":
            self.plat_v = amp * np.array([0.94, 0.34])
        elif d.platform == "circular":
            a = 2 * math.pi * self.t / 4.0
            self.plat_v = amp * np.array([math.cos(a), math.sin(a)])
        elif d.platform == "figure8":
            a = 2 * math.pi * self.t / 5.0
            self.plat_v = amp * np.array([math.cos(a), math.cos(2 * a)])
        elif d.platform == "random":
            self.plat_v += self.rng.normal(0, amp * 0.6, 2) * math.sqrt(dt) - 0.8 * self.plat_v * dt
            n = np.linalg.norm(self.plat_v)
            if n > amp:
                self.plat_v *= amp / n
        else:
            self.plat_v[:] = 0
        self.plat += self.plat_v * dt
        if self.sc.imu_aid:
            gyro_sigma = 0.02 * np.abs(self.plat_v) + 1.0
            self.plat_v_est = self.plat_v + self.rng.normal(0, 1, 2) * gyro_sigma
            self.plat_est += self.plat_v_est * dt
        else:
            self.plat_v_est[:] = 0
            self.plat_est[:] = 0

    def _meas_sigma(self) -> float:
        jit = self.sc.disturb.jitter_px * (0.15 if self.sc.imu_aid else 1.0)
        return max(1.2, jit / 1.73)

    def _wide_field(self, true_pos: np.ndarray, visible: bool) -> np.ndarray | None:
        """Low-resolution whole-screen acquisition sensor (as on real FSOC terminals) that cues the narrow camera."""
        d = self.sc.disturb
        f = self.wf_bg.copy()
        if visible:
            p = true_pos / WF_SCALE
            x0, y0 = int(p[0] - 1), int(p[1] - 1)
            if 0 <= x0 < f.shape[1] - 2 and 0 <= y0 < f.shape[0] - 2:
                # beacon energy integrated into a 2x2 wide-field pixel footprint
                f[y0:y0 + 2, x0:x0 + 2] += self.sc.target.brightness * min(1.0, (self.sc.target.size / WF_SCALE) ** 2 / 4 + 0.35)
        sig = d.gaussian_sigma / 3 + 2
        f = f + self.rng.normal(0, sig, f.shape)
        if d.weather == "fog":
            f = f * 0.4 + 95
        img = np.clip(f, 0, 255).astype(np.uint8)
        if d.salt_pepper > 0:
            m = self.rng.random(img.shape)
            img[m < d.salt_pepper / 20] = 255
        det = self.wf_det.detect(img)
        return None if det is None else np.array([det.x, det.y]) * WF_SCALE

    # ------------------------------------------------------------------
    def step(self) -> dict:
        sc, dt = self.sc, self.dt
        true_pos = self.target.update(self.t, dt)
        visible = self.target.visible(self.t)
        self._platform()
        los = self.mount + self.plat
        jit = self.rng.uniform(-sc.disturb.jitter_px, sc.disturb.jitter_px, 2) if sc.disturb.jitter_px > 0 else np.zeros(2)
        view = los + jit
        frame, rel_true = self.renderer.render(view, true_pos, visible)
        jit_est = jit + self.rng.normal(0, 0.15 * sc.disturb.jitter_px / 1.73, 2) if (sc.imu_aid and sc.disturb.jitter_px > 0) else np.zeros(2)
        cam_est = self.mount + self.plat_est + jit_est  # where the IMU says the camera is looking (screen coords)

        t0 = time.perf_counter()
        pred = self.trk.predict()
        det = None
        if pred is not None and self.trk.state in (LOCK, ACQUIRE, COAST, REACQUIRE):
            p_frame = pred - cam_est + self.half
            g = self.trk.gate()
            r = int(g + sc.target.size * 2)
            roi = (int(p_frame[0]) - r, int(p_frame[1]) - r, int(p_frame[0]) + r, int(p_frame[1]) + r)
            det = self.det.detect(frame, (p_frame[0], p_frame[1]), g, roi)
            if det is None and self.trk.state == REACQUIRE:
                det = self.det.detect(frame)
        else:
            det = self.det.detect(frame)
        meas = None if det is None else cam_est - self.half + np.array([det.x, det.y])
        state = self.trk.update(meas)

        cue = None
        if state in (LOCK, ACQUIRE, COAST):
            aim = self.trk.pos + self.trk.vel * dt
            v_cmd = self.ctl.track(self.mount, aim - self.plat_est, self.trk.vel - self.plat_v_est, dt)
        else:
            if self.wide_field_cue:
                cue = self._wide_field(true_pos - self.plat, visible)
            if cue is not None:
                v_cmd = self.ctl.track(self.mount, cue, -self.plat_v_est, dt)
            else:
                centre = self.trk.pos - self.plat_est if self.trk.initialised else self.mount
                v_cmd = self.ctl.search(self.mount, centre, dt)
        self.mount = self.mount + v_cmd * dt
        proc_ms = (time.perf_counter() - t0) * 1000

        in_fov = bool(np.all(np.abs(true_pos - los) < self.half)) and visible
        track_err = float(np.hypot(*(true_pos - los)))
        cent_err = None
        if det is not None and visible:
            cent_err = float(np.hypot(det.x - rel_true[0], det.y - rel_true[1]))
        self.log.add(frame=self.frame_no, t=round(self.t, 4), state=state, visible=visible, in_fov=in_fov,
                     true_x=float(true_pos[0]), true_y=float(true_pos[1]), bore_x=float(los[0]), bore_y=float(los[1]),
                     det_x=None if det is None else det.x, det_y=None if det is None else det.y,
                     tracking_err_px=track_err, centroid_err_px=cent_err, proc_ms=proc_ms)
        self.trail.append((float(true_pos[0]), float(true_pos[1])))
        self.trail = self.trail[-90:]
        self.last = dict(frame=frame, det=det, state=state, rel_true=rel_true, true_pos=true_pos, los=los, view=view,
                         pred=None if pred is None else pred - cam_est + self.half, cue=cue, visible=visible,
                         track_err=track_err, cent_err=cent_err, proc_ms=proc_ms, t=self.t)
        self.t += dt
        self.frame_no += 1
        return self.last

    def retune(self) -> None:
        """Re-derive tracker noise model after live disturbance changes (GUI sliders / scripted events)."""
        self.trk.kf.R = np.eye(2) * self._meas_sigma() ** 2

    def run(self, duration: float | None = None) -> dict:
        n = int(round((duration or self.sc.duration_s) / self.dt))
        for _ in range(n):
            self.step()
        return self.log.summary()


def run_headless(sc: Scenario, out_dir: str | None = None, stem: str | None = None, wide_field_cue: bool = True) -> dict:
    sim = Simulation(sc, wide_field_cue)
    sim.run()
    if out_dir:
        return sim.log.write(out_dir, stem or f"{sc.name}_seed{sc.seed}")
    return sim.log.summary()
