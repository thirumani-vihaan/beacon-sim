"""Virtual scene: static 2000x2000 background, moving square beacon, and the camera-view renderer with disturbances."""
from __future__ import annotations

import math

import cv2
import numpy as np

from .config import Scenario

LAMBDA_M = 1550e-9  # FSOC beacon wavelength used by the turbulence layer


def make_background(w: int, h: int, rng: np.random.Generator) -> np.ndarray:
    """Dark sky with a faint gradient and a sparse star field (clutter for the detector)."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    bg = 18 + 14 * (yy / h) + 6 * np.sin(xx / w * 3.1) * np.cos(yy / h * 2.3)
    n = int(w * h / 9000)
    xs, ys = rng.integers(0, w, n), rng.integers(0, h, n)
    bg[ys, xs] += rng.uniform(15, 55, n)  # 1-px stars: dimmer and smaller than the beacon
    return cv2.GaussianBlur(bg, (0, 0), 0.6).astype(np.float32)


class Target:
    """Beacon trajectory on the screen (screen pixels). Official motions: line, circle, figure8, random (+ spiral, sine)."""

    def __init__(self, sc: Scenario, rng: np.random.Generator):
        self.cfg, self.rng = sc.target, rng
        self.W, self.H = sc.camera.screen_w, sc.camera.screen_h
        self.cx, self.cy = self.W / 2, self.H / 2
        self.phase = rng.uniform(0, 2 * math.pi)
        r0 = rng.uniform(250, 600)  # random start inside the uncertainty region around the boresight
        self.pos = np.array([self.cx + r0 * math.cos(self.phase), self.cy + r0 * math.sin(self.phase)])
        ang = rng.uniform(0, 2 * math.pi)
        self.vel = np.array([math.cos(ang), math.sin(ang)]) * self.cfg.speed
        self.start = self.pos.copy()

    def visible(self, t: float) -> bool:
        return not any(s <= t < s + d for s, d in self.cfg.occlusions)

    def update(self, t: float, dt: float) -> np.ndarray:
        m, v = self.cfg.motion, self.cfg.speed
        A = 600.0
        if m == "circle":
            w = v / A
            self.pos = np.array([self.cx + A * math.cos(self.phase + w * t), self.cy + A * math.sin(self.phase + w * t)])
        elif m == "figure8":
            w = v / (A * 1.25)
            a = self.phase + w * t
            self.pos = np.array([self.cx + A * math.sin(a), self.cy + 0.5 * A * math.sin(2 * a)])
        elif m == "spiral":
            w = v / 400
            r = 150 + 450 * (0.5 + 0.5 * math.sin(0.07 * t))
            self.pos = np.array([self.cx + r * math.cos(self.phase + w * t), self.cy + r * math.sin(self.phase + w * t)])
        elif m == "sine":
            self.pos = self.pos + np.array([self.vel[0], 0]) * dt
            self.pos[1] = self.cy + 350 * math.sin(2 * math.pi * 0.12 * t + self.phase)
            self._bounce()
        elif m == "random":
            # smooth random walk (Ornstein-Uhlenbeck on velocity), speed kept near the configured value
            self.vel += self.rng.normal(0, 1, 2) * v * 1.2 * math.sqrt(dt) - 0.4 * self.vel * dt
            sp = np.linalg.norm(self.vel) + 1e-9
            self.vel *= (0.8 * v + 0.2 * sp) / sp
            self.pos = self.pos + self.vel * dt
            self._bounce()
        else:  # line: straight line, reflects at the screen margins
            self.pos = self.pos + self.vel * dt
            self._bounce()
        return self.pos.copy()

    def _bounce(self, margin: float = 150.0) -> None:
        for i, lim in ((0, self.W), (1, self.H)):
            if self.pos[i] < margin or self.pos[i] > lim - margin:
                self.vel[i] = -self.vel[i]
                self.pos[i] = min(max(self.pos[i], margin), lim - margin)


def _coverage(lo: float, hi: float, n: int, start: int) -> np.ndarray:
    """Fraction of each pixel [start+i, start+i+1) covered by [lo, hi) -> sub-pixel accurate rendering."""
    edges = start + np.arange(n + 1, dtype=np.float64)
    return np.clip(np.minimum(edges[1:], hi) - np.maximum(edges[:-1], lo), 0, 1)


class Renderer:
    """Renders the 640x480 camera view of the screen with the official disturbances (+ optional turbulence layer)."""

    def __init__(self, sc: Scenario, rng: np.random.Generator):
        self.sc, self.rng = sc, rng
        c = sc.camera
        self.bg = make_background(c.screen_w, c.screen_h, rng)
        self.pad = 420  # sky continues beyond the screen edge (reflected), so the border never looks like a target
        self.bg_pad = cv2.copyMakeBorder(self.bg, self.pad, self.pad, self.pad, self.pad, cv2.BORDER_REFLECT)
        self.wander = np.zeros(2)
        d = sc.disturb
        k = 2 * math.pi / LAMBDA_M
        self.rytov = 1.23 * d.turbulence_cn2 * k ** (7 / 6) * (d.path_km * 1e3) ** (11 / 6) if d.turbulence_cn2 > 0 else 0.0
        self._banks: dict = {}

    def _bank(self, kind: str, shape: tuple[int, int]) -> np.ndarray:
        """Pre-generated noise fields; each frame takes a seeded random bank + offset (fast and still deterministic)."""
        key = (kind, shape)
        if key not in self._banks:
            h, w = shape
            gen = self.rng.standard_normal if kind == "normal" else self.rng.random
            nb = 12 if h * w <= 1_000_000 else 3  # keep memory bounded for full-screen (2000 x 2000) renders
            self._banks[key] = [gen((h + 64, w + 64), dtype=np.float32) for _ in range(nb)]
        bank = self._banks[key]
        b = bank[int(self.rng.integers(0, len(bank)))]
        oy, ox = int(self.rng.integers(0, 64)), int(self.rng.integers(0, 64))
        return b[oy:oy + shape[0], ox:ox + shape[1]]

    def render(self, view_center: np.ndarray, target_pos: np.ndarray, visible: bool) -> tuple[np.ndarray, np.ndarray]:
        """Returns (uint8 frame, apparent target position in frame coords)."""
        c, d, rng = self.sc.camera, self.sc.disturb, self.rng
        w, h = c.res_w, c.res_h
        x0 = int(round(view_center[0] - w / 2)) + self.pad
        y0 = int(round(view_center[1] - h / 2)) + self.pad
        H, W = self.bg_pad.shape
        frame = np.zeros((h, w), np.float32)
        sx0, sy0, sx1, sy1 = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
        if sx1 > sx0 and sy1 > sy0:
            frame[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = self.bg_pad[sy0:sy1, sx0:sx1]

        # turbulence layer: beam wander (low-frequency) + scintillation (log-normal intensity) + seeing blur
        amp, blur = 1.0, 0.0
        if self.rytov > 0:
            s2 = min(self.rytov, 4.0)
            self.wander = 0.95 * self.wander + rng.normal(0, 0.9 * math.sqrt(s2), 2)
            amp = float(np.exp(rng.normal(-s2 / 2, math.sqrt(s2))))
            blur = 0.6 + 0.8 * math.sqrt(s2)

        rel = target_pos - (view_center - np.array([w / 2, h / 2])) + self.wander
        if visible:
            s = self.sc.target.size
            lo_x, lo_y = rel[0] - s / 2, rel[1] - s / 2
            ix, iy = int(math.floor(lo_x)) - 1, int(math.floor(lo_y)) - 1
            n = s + 3
            patch = np.outer(_coverage(lo_y, lo_y + s, n, iy), _coverage(lo_x, lo_x + s, n, ix)) * self.sc.target.brightness * amp
            if blur > 0:
                patch = cv2.GaussianBlur(patch.astype(np.float32), (0, 0), blur)
            ax0, ay0, ax1, ay1 = max(ix, 0), max(iy, 0), min(ix + n, w), min(iy + n, h)
            if ax1 > ax0 and ay1 > ay0:
                frame[ay0:ay1, ax0:ax1] = np.maximum(frame[ay0:ay1, ax0:ax1], patch[ay0 - iy:ay1 - iy, ax0 - ix:ax1 - ix])

        frame = self._weather(frame)
        if d.poisson:  # shot noise: variance = signal (Gaussian approximation of Poisson, valid for these counts)
            frame += np.sqrt(np.clip(frame, 0, None)) * self._bank("normal", frame.shape)
        if d.gaussian_sigma > 0:
            frame += d.gaussian_sigma * self._bank("normal", frame.shape)
        out = np.clip(frame, 0, 255).astype(np.uint8)
        if d.salt_pepper > 0:
            m = self._bank("uniform", out.shape)
            out[m < d.salt_pepper / 2] = 0
            out[m > 1 - d.salt_pepper / 2] = 255
        return out, rel

    def _weather(self, f: np.ndarray) -> np.ndarray:
        wx = self.sc.disturb.weather
        if wx == "haze":
            f = f * 0.65 + 45
        elif wx == "fog":
            f = cv2.GaussianBlur(f, (0, 0), 1.6) * 0.4 + 95
        elif wx == "rain":
            f = f * 0.8 + 10
            for _ in range(40):
                x, y = self.rng.integers(0, f.shape[1]), self.rng.integers(0, f.shape[0])
                cv2.line(f, (int(x), int(y)), (int(x) + 4, int(y) + 22), 70.0, 1)
        elif wx == "lowlight":
            f = f * 0.35
        return f

    def full_screen(self, target_pos: np.ndarray, visible: bool) -> tuple[np.ndarray, np.ndarray]:
        """Whole-screen frame (for generating grader-style MP4 test videos with ground truth)."""
        c = self.sc.camera
        return self.render_region(np.array([c.screen_w / 2, c.screen_h / 2]), (c.screen_w, c.screen_h), target_pos, visible)

    def render_region(self, center, size, target_pos, visible):
        c = self.sc.camera
        saved = (c.res_w, c.res_h)
        c.res_w, c.res_h = size
        try:
            return self.render(np.asarray(center, float), target_pos, visible)
        finally:
            c.res_w, c.res_h = saved
