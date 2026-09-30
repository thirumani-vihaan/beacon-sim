"""MP4 benchmark mode (official Benchmark-2): grader video in, PTZ simulation bypassed, same detector + tracker.

Also contains a generator for grader-style test videos (full screen @ 30 fps, noise, moving beacon, ground-truth CSV).
"""
from __future__ import annotations

import csv
import math
import time
from pathlib import Path

import cv2
import numpy as np

from .config import CameraCfg, Scenario
from .detect import BeaconDetector
from .metrics import PerfLog
from .scene import Renderer, Target
from .tracker import ACQUIRE, COAST, LOCK, REACQUIRE, Tracker


def load_gt(path: str | None) -> dict[int, tuple[float, float]]:
    gt: dict[int, tuple[float, float]] = {}
    if not path:
        return gt
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            k = int(row.get("frame", i))
            x, y = row.get("x", ""), row.get("y", "")
            if x not in ("", "nan") and y not in ("", "nan"):
                gt[k] = (float(x), float(y))
    return gt


class VideoBenchmark:
    """Iterates a video frame by frame; each step returns overlay data for the GUI and logs metrics."""

    def __init__(self, video: str, gt_csv: str | None = None, target_size: int = 10, view=(640, 480)):
        self.cap = cv2.VideoCapture(str(video))
        if not self.cap.isOpened():
            raise IOError(f"cannot open {video}")
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and 1 < fps < 1000 else 30.0  # dt from the file, never hard-coded
        self.dt = 1.0 / self.fps
        self.W = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.H = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.n_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.scale = min(1.0, 640 / max(self.W, self.H))
        self.coarse = BeaconDetector(max(2, round(target_size * self.scale)), median=target_size * self.scale >= 3)
        self.fine = BeaconDetector(target_size)
        self.trk = Tracker(self.dt, meas_sigma=1.5, accel_sigma=400.0)
        self.gt = load_gt(gt_csv)
        self.view = np.array(view, float)
        self.center = np.array([self.W / 2, self.H / 2])
        self.frame_no, self.t = 0, 0.0
        self.log = PerfLog(CameraCfg().urad_per_px, {"scenario": Path(video).name, "seed": "-", "config_hash": "-",
                                 "mode": "MP4 benchmark (PTZ bypassed)", "ground_truth": bool(self.gt)})
        self.last: dict = {}

    def step(self) -> dict | None:
        ok, img = self.cap.read()
        if not ok:
            return None
        gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        t0 = time.perf_counter()
        pred = self.trk.predict()
        det = None
        if pred is not None and self.trk.state in (LOCK, ACQUIRE, COAST, REACQUIRE):
            g = self.trk.gate()
            r = int(g + 24)
            det = self.fine.detect(gray, (pred[0], pred[1]), g, (int(pred[0]) - r, int(pred[1]) - r, int(pred[0]) + r, int(pred[1]) + r))
        if det is None and self.trk.state not in (LOCK, ACQUIRE):
            small = cv2.resize(gray, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA) if self.scale < 1 else gray
            c = self.coarse.detect(small)
            if c is not None:
                cx, cy = c.x / self.scale, c.y / self.scale
                det = self.fine.detect(gray, (cx, cy), 40, (int(cx) - 40, int(cy) - 40, int(cx) + 40, int(cy) + 40))
        state = self.trk.update(None if det is None else np.array([det.x, det.y]))
        if self.trk.initialised:
            self.center = self.trk.pos  # virtual camera window follows the estimate
        proc_ms = (time.perf_counter() - t0) * 1000

        g = self.gt.get(self.frame_no)
        has_gt = g is not None
        gx, gy = (g if has_gt else (math.nan, math.nan))
        cent = None if (det is None or not has_gt) else float(math.hypot(det.x - gx, det.y - gy))
        terr = float(math.hypot(self.center[0] - gx, self.center[1] - gy)) if has_gt else math.nan
        in_fov = bool(has_gt and abs(gx - self.center[0]) < self.view[0] / 2 and abs(gy - self.center[1]) < self.view[1] / 2)
        self.log.add(frame=self.frame_no, t=round(self.t, 4), state=state, visible=has_gt or not self.gt,
                     in_fov=in_fov if self.gt else True, true_x=gx, true_y=gy, bore_x=float(self.center[0]), bore_y=float(self.center[1]),
                     det_x=None if det is None else det.x, det_y=None if det is None else det.y,
                     tracking_err_px=terr, centroid_err_px=cent, proc_ms=proc_ms)
        self.last = dict(image=gray, det=det, state=state, center=self.center.copy(), gt=None if not has_gt else (gx, gy),
                         cent_err=cent, proc_ms=proc_ms, t=self.t, frame_no=self.frame_no)
        self.frame_no += 1
        self.t += self.dt
        return self.last

    def run(self) -> dict:
        while self.step() is not None:
            pass
        return self.log.summary()


def make_test_video(out_mp4: str, sc: Scenario, seconds: float = 20.0, size: int = 2000) -> str:
    """Grader-style video: the complete screen, noise, moving beacon; writes <name>_gt.csv next to it."""
    rng = np.random.default_rng(sc.seed)
    sc.camera.screen_w = sc.camera.screen_h = size
    tgt = Target(sc, rng)
    ren = Renderer(sc, rng)
    fps = sc.camera.rate_hz
    vw = cv2.VideoWriter(str(out_mp4), cv2.VideoWriter_fourcc(*"mp4v"), fps, (size, size), isColor=False)
    gt_path = str(Path(out_mp4).with_name(Path(out_mp4).stem + "_gt.csv"))
    with open(gt_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame", "x", "y"])
        for i in range(int(seconds * fps)):
            t = i / fps
            pos = tgt.update(t, 1 / fps)
            vis = tgt.visible(t)
            frame, rel = ren.render_region((size / 2, size / 2), (size, size), pos, vis)
            vw.write(frame)
            w.writerow([i, round(float(rel[0]), 3), round(float(rel[1]), 3)] if vis else [i, "", ""])
    vw.release()
    return gt_path
