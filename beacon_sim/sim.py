"""Simulation engine: target + platform + pan-tilt mount + camera render + detection + tracking + control + logging.

Deterministic: the whole run is driven by one seeded numpy Generator, so (scenario, seed) always reproduces the
same frames and the same metrics.
"""
from __future__ import annotations

import copy
import math
import time

import cv2
import numpy as np

from .config import Scenario
from .control import PanTiltController
from .detect import BeaconDetector
from .feasibility import analyse
from .metrics import PerfLog
from .scene import Renderer, Target, apply_weather
from .tracker import ACQUIRE, COAST, LOCK, REACQUIRE, SEARCH, Tracker

WF_SCALE = 8  # wide-field acquisition sensor sees the whole screen at 1/8 resolution (250 x 250)


class Simulation:
    def __init__(self, sc: Scenario, wide_field_cue: bool = True):
        self.warnings = sc.validate()
        self.sc = sc
        self.rng = np.random.default_rng(sc.seed)
        c = sc.camera
        self.dt = 1.0 / c.rate_hz
        self.half = np.array([c.res_w / 2, c.res_h / 2])
        self.target = Target(sc, self.rng)
        self.decoys = []
        for _ in range(max(0, sc.target.count - 1)):  # optional multiple targets: dimmer decoy spots
            dsc = copy.deepcopy(sc)
            dsc.target.start, dsc.target.occlusions = "random", []
            if dsc.target.motion == "waypoints":
                dsc.target.motion = "random"
            self.decoys.append(Target(dsc, self.rng))
        self.renderer = Renderer(sc, self.rng)
        self.det = BeaconDetector(sc.target.size)
        self.near_k = 1.5
        self.wf_det = BeaconDetector(2, k_sigma=5.0, min_snr=7.0, median=False)
        self.trk = Tracker(self.dt, meas_sigma=self._meas_sigma(), accel_sigma=300.0, imm=True, manoeuvre_sigma=2500.0)
        self.ctl = PanTiltController(c)
        self.wide_field_cue = wide_field_cue and c.wide_field
        self.mount = np.array([c.screen_w / 2, c.screen_h / 2], float)  # official row 6: start at screen centre
        self.v_cmd = np.zeros(2)
        self.next_ctl = 0.0  # official row 15: pan-tilt commands run on their own clock (control_hz)
        self.plat = np.zeros(2)
        self.plat_v = np.zeros(2)
        self.plat_est = np.zeros(2)  # IMU-integrated platform offset (drifts slowly)
        self.plat_v_est = np.zeros(2)
        self.t, self.frame_no = 0.0, 0
        self.feasibility = analyse(sc)
        self.log = PerfLog(c.urad_per_px, {"scenario": sc.name, "seed": sc.seed, "config_hash": sc.hash(),
                                           "feasibility": self.feasibility, "warnings": self.warnings})
        self.wf_bg = cv2.resize(self.renderer.bg, (c.screen_w // WF_SCALE, c.screen_h // WF_SCALE), interpolation=cv2.INTER_AREA)
        self.wf_prev: np.ndarray | None = None
        self.cue_mem: tuple[np.ndarray, float] | None = None  # last confirmed cue (position, time)
        self.trail: list[tuple[float, float]] = []
        self.last = {}

    # ------------------------------------------------------------------
    def _platform(self) -> None:
        d, dt = self.sc.disturb, self.dt
        amp = d.platform_px * self.sc.camera.rate_hz  # px/frame -> px/s
        if d.platform == "linear":  # row 21.5 "+/-N px/frame": constant-speed back-and-forth along a line (4 s period)
            self.plat_v = amp * np.array([0.94, 0.34]) * (1.0 if (self.t % 4.0) < 2.0 else -1.0)
        elif d.platform == "circular":
            a = 2 * math.pi * self.t / 4.0
            self.plat_v = amp * np.array([math.cos(a), math.sin(a)])
        elif d.platform == "spiral":  # rotating velocity whose magnitude ramps up and resets every 8 s
            a = 2 * math.pi * self.t / 3.0
            self.plat_v = amp * ((self.t % 8.0) / 8.0) * np.array([math.cos(a), math.sin(a)])
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
        wander = 0.0
        if self.sc.disturb.turbulence_cn2 > 0:  # stationary std of the simulated beam wander (AR(1), rho 0.95)
            wander = 0.9 * math.sqrt(min(self.renderer.rytov, 4.0)) / math.sqrt(1 - 0.95 ** 2)
        return max(1.2, math.hypot(jit / 1.73, wander))

    def _wide_field(self, true_pos: np.ndarray, visible: bool, decoys: list) -> np.ndarray | None:
        """Low-resolution whole-screen acquisition sensor (as on real FSOC terminals) that cues the narrow camera.

        Each wide-field pixel integrates 8 x 8 screen pixels, so the image noise is the official noise averaged over
        64 pixels (salt-and-pepper impulses average out instead of surviving as bright dots). A cue is only issued
        when two consecutive wide-field detections agree (temporal confirmation).
        """
        d, tg = self.sc.disturb, self.sc.target
        f = self.wf_bg.copy()
        gain = min(1.0, (tg.size / WF_SCALE) ** 2 / 4 + 0.35)  # beacon energy spread over a 2 x 2 footprint
        spots = [(true_pos, tg.brightness)] if visible else []
        spots += [(dp, tg.brightness * tg.decoy_brightness) for dp in decoys]
        for pos, lvl in spots:
            p = pos / WF_SCALE
            x0, y0 = int(p[0] - 1), int(p[1] - 1)
            if 0 <= x0 < f.shape[1] - 2 and 0 <= y0 < f.shape[0] - 2:
                f[y0:y0 + 2, x0:x0 + 2] += lvl * gain
        f = apply_weather(f, d, streaks=False)
        sp = d.salt_pepper
        var = (d.gaussian_sigma / WF_SCALE) ** 2 + (sp / 2) * (255 ** 2) / 64 * (1 - sp) + 1.5 ** 2
        if d.poisson:
            var += float(np.mean(np.clip(f, 0, None))) / 64
        f = f + self.rng.normal(0, math.sqrt(var), f.shape)
        img = np.clip(f, 0, 255).astype(np.uint8)
        det = self.wf_det.detect(img)
        cur = None if det is None else np.array([det.x, det.y]) * WF_SCALE
        prev, self.wf_prev = self.wf_prev, cur
        mem = self.cue_mem[0] if (self.cue_mem and self.t - self.cue_mem[1] < 1.0) else None
        if cur is not None and any(q is not None and np.hypot(*(cur - q)) <= 64 for q in (prev, mem)):
            self.cue_mem = (cur, self.t)
            return cur
        return mem  # keep slewing to the last confirmed cue for up to 1 s instead of restarting the search

    def _command(self, state: str, cue: np.ndarray | None, lead: float, dt_ctl: float) -> np.ndarray:
        if state in (LOCK, ACQUIRE, COAST):
            # velocity feed-forward already carries the mount along; the P-term aims at the *current* estimate
            aim = self.trk.pos + self.trk.vel * lead
            return self.ctl.track(self.mount, aim - self.plat_est, self.trk.vel - self.plat_v_est, dt_ctl)
        if cue is not None:
            return self.ctl.track(self.mount, cue, -self.plat_v_est, dt_ctl)
        centre = self.trk.pos - self.plat_est if self.trk.initialised else self.mount
        return self.ctl.search(self.mount, centre, dt_ctl)

    # ------------------------------------------------------------------
    def step(self) -> dict:
        sc, dt = self.sc, self.dt
        true_pos = self.target.update(self.t, dt)
        visible = self.target.visible(self.t)
        decoy_pos = [dcy.update(self.t, dt) for dcy in self.decoys]
        self._platform()
        los = self.mount + self.plat
        jit = self.rng.uniform(-sc.disturb.jitter_px, sc.disturb.jitter_px, 2) if sc.disturb.jitter_px > 0 else np.zeros(2)
        view = los + jit
        frame, rel_true = self.renderer.render(view, true_pos, visible, decoy_pos)
        frame_colour = None
        if sc.camera.colour:  # optional colour camera: tinted sky; detection runs on the luminance channel
            ff = frame.astype(np.float32)
            frame_colour = np.clip(np.dstack([ff * 1.05, ff * 0.88, ff * 0.72]), 0, 255).astype(np.uint8)
            frame = cv2.cvtColor(frame_colour, cv2.COLOR_BGR2GRAY)
        jit_est = jit + self.rng.normal(0, 0.15 * sc.disturb.jitter_px / 1.73, 2) if (sc.imu_aid and sc.disturb.jitter_px > 0) else np.zeros(2)
        cam_est = self.mount + self.plat_est + jit_est  # where the IMU says the camera is looking (screen coords)

        t0 = time.perf_counter()
        pred = self.trk.predict()
        cue = None
        if self.wide_field_cue and self.trk.state in (SEARCH, ACQUIRE, REACQUIRE):
            cue = self._wide_field(true_pos - self.plat, visible, [dp - self.plat for dp in decoy_pos])
        det = None
        if pred is not None and self.trk.state in (LOCK, ACQUIRE, COAST, REACQUIRE):
            p_frame = pred - cam_est + self.half
            g = self.trk.gate()
            r = int(g + sc.target.size * 2)
            roi = (int(p_frame[0]) - r, int(p_frame[1]) - r, int(p_frame[0]) + r, int(p_frame[1]) + r)
            near = min(self.trk.near_gate(), self.near_k * sc.target.size + 6) if self.trk.state in (LOCK, COAST) else 0.0
            det = self.det.detect(frame, (p_frame[0], p_frame[1]), g, roi, near)
            if det is None and self.trk.state == REACQUIRE:
                det = self.det.detect(frame)
        else:
            det = self.det.detect(frame)
        if det is not None and cue is not None and self.trk.state in (SEARCH, ACQUIRE):
            # acquisition arbitration: a narrow-camera hit far from a confirmed wide-field cue is a false alarm
            if np.hypot(*(cam_est - self.half + np.array([det.x, det.y]) - self.plat_est - cue)) > 96:
                det = None
        meas = None if det is None else cam_est - self.half + np.array([det.x, det.y])
        state = self.trk.update(meas)

        # control clock: zero-order hold between pan-tilt updates at control_hz (may be faster or slower than frames)
        tick = 1.0 / sc.camera.control_hz
        seg, v = self.t, self.v_cmd
        while self.next_ctl < self.t + dt - 1e-9:
            self.mount = self.mount + v * (self.next_ctl - seg)
            seg = self.next_ctl
            v = self._command(state, cue, self.next_ctl - self.t, tick)
            self.next_ctl += tick
        self.mount = self.mount + v * (self.t + dt - seg)
        # gimbal range limit: the (IMU-estimated) line of sight never leaves the screen
        c = sc.camera
        self.mount = np.clip(self.mount + self.plat_est, [0, 0], [c.screen_w, c.screen_h]) - self.plat_est
        self.v_cmd = v
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
        self.last = dict(frame=frame, frame_colour=frame_colour, det=det, state=state, rel_true=rel_true, true_pos=true_pos,
                         los=los, view=view, decoys=decoy_pos,
                         pred=None if pred is None else pred - cam_est + self.half, cue=cue, visible=visible,
                         track_err=track_err, cent_err=cent_err, proc_ms=proc_ms, t=self.t)
        self.t += dt
        self.frame_no += 1
        return self.last

    def retune(self) -> None:
        """Re-derive tracker noise model after live disturbance changes (GUI sliders / scripted events)."""
        self.trk.set_meas_sigma(self._meas_sigma())

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
