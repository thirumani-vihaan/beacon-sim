"""Virtual pan-tilt mount: PID + velocity feed-forward, slew-rate limit, deadzone, and a spiral search when lost."""
from __future__ import annotations

import math

import numpy as np

from .config import CameraCfg


class PanTiltController:
    def __init__(self, cam: CameraCfg, kp: float = 12.0, ki: float = 0.8, kd: float = 0.05, deadzone_px: float = 0.3):
        self.cam = cam
        self.kp, self.ki, self.kd, self.dz = kp, ki, kd, deadzone_px
        # official rows 13-14: independent pan / tilt limits, converted to screen px/s per axis
        self.max_v = np.array([cam.max_pan_dps * cam.px_per_deg, cam.max_tilt_dps * cam.px_per_deg_y])
        self.integ = np.zeros(2)
        self.prev_err = np.zeros(2)
        self.search_t = 0.0
        self.search_origin: np.ndarray | None = None

    def track(self, boresight: np.ndarray, aim: np.ndarray, target_vel: np.ndarray, dt: float) -> np.ndarray:
        """Returns the commanded mount velocity (px/s), saturated at the official max pan/tilt speed."""
        self.search_origin = None
        err = aim - boresight
        err[np.abs(err) < self.dz] = 0
        self.integ = np.clip(self.integ + err * dt, -40, 40)
        derr = (err - self.prev_err) / dt
        self.prev_err = err
        v = self.kp * err + self.ki * self.integ + self.kd * derr + target_vel
        return np.clip(v, -self.max_v, self.max_v)

    def search(self, boresight: np.ndarray, centre: np.ndarray, dt: float) -> np.ndarray:
        """Archimedean spiral scan around the last known / expected position (uncertainty cone)."""
        if self.search_origin is None:
            self.search_origin, self.search_t = centre.copy(), 0.0
            self.integ[:] = 0
        self.search_t += dt
        pitch = 0.8 * min(self.cam.res_w, self.cam.res_h) / (2 * math.pi)  # overlap successive turns
        th = math.sqrt(2 * 900 * self.search_t / pitch + 1e-9)            # ~constant along-path speed
        goal = self.search_origin + pitch * th * np.array([math.cos(th), math.sin(th)])
        return np.clip((goal - boresight) * 8.0, -self.max_v, self.max_v)
