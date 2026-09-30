"""MP4 benchmark mode (official Benchmark-2): grader video in, PTZ simulation bypassed, same detector + tracker.

Robust to what the grader may hand over: any resolution / fps / codec, colour or mono, unknown beacon size
(estimated automatically), frames without the beacon, and no ground truth at all. Also contains a batch runner
with pass/fail thresholds and a generator for a suite of grader-style test videos with ground truth.
"""
from __future__ import annotations

import copy
import csv
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

from .config import CameraCfg, Scenario, preset
from .detect import BeaconDetector
from .metrics import PerfLog
from .scene import Renderer, Target
from .tracker import ACQUIRE, COAST, LOCK, REACQUIRE, Tracker

X_KEYS = ("x", "cx", "centroid_x", "gt_x", "X", "target_x")
Y_KEYS = ("y", "cy", "centroid_y", "gt_y", "Y", "target_y")


def load_gt(path: str | None, pixel_centre: bool = False) -> dict[int, tuple[float, float]]:
    """Ground-truth CSV -> {frame: (x, y)}. Accepts frame,x,y / cx,cy / centroid_x,... column names; empty = absent.

    Coordinates follow the continuous convention (pixel i spans [i, i+1)). Use pixel_centre=True when the grader's
    integer coordinates denote pixel centres (adds 0.5 px).
    """
    gt: dict[int, tuple[float, float]] = {}
    if not path:
        return gt
    off = 0.5 if pixel_centre else 0.0
    with open(path, newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        cols = rd.fieldnames or []
        kx = next((k for k in X_KEYS if k in cols), None)
        ky = next((k for k in Y_KEYS if k in cols), None)
        kf = next((k for k in ("frame", "frame_no", "Frame", "idx", "index") if k in cols), None)
        if kx is None or ky is None:
            raise ValueError(f"ground-truth CSV needs x/y columns, found {cols}")
        for i, row in enumerate(rd):
            k = int(float(row[kf])) if kf else i
            x, y = row.get(kx, ""), row.get(ky, "")
            if x.strip() not in ("", "nan", "NaN", "-1") and y.strip() not in ("", "nan", "NaN", "-1"):
                gt[k] = (float(x) + off, float(y) + off)
    return gt


def estimate_spot_size(gray: np.ndarray, x: float, y: float, r: int = 40) -> int:
    """Beacon side length (px) from the half-maximum area of the blob around (x, y)."""
    x0, y0 = max(0, int(x) - r), max(0, int(y) - r)
    patch = cv2.medianBlur(gray[y0:int(y) + r, x0:int(x) + r], 3).astype(np.float32)
    if patch.size < 25:
        return 10
    bg = float(np.median(patch))
    peak = float(cv2.GaussianBlur(patch, (3, 3), 0).max())
    if peak - bg < 5:
        return 10
    mask = (patch > bg + 0.5 * (peak - bg)).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return 10
    cy, cx = int(y) - y0, int(x) - x0
    i = lab[min(max(cy, 0), lab.shape[0] - 1), min(max(cx, 0), lab.shape[1] - 1)]
    if i == 0:
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return int(np.clip(round(math.sqrt(stats[i, cv2.CC_STAT_AREA])), 3, 40))


class VideoBenchmark:
    """Iterates a video frame by frame; each step returns overlay data for the GUI and logs metrics."""

    def __init__(self, video: str, gt_csv: str | None = None, target_size: int | None = None, view=(640, 480),
                 pixel_centre: bool = False):
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
        self.auto_size = target_size is None
        self._set_size(target_size or 10)
        self.trk = Tracker(self.dt, meas_sigma=1.5, accel_sigma=400.0)
        self.trk.ACQ_MISS_ALLOW = 2
        self.size_locked = False
        self.gt = load_gt(gt_csv, pixel_centre)
        self.view = np.array(view, float)
        self.center = np.array([self.W / 2, self.H / 2])
        self.frame_no, self.t = 0, 0.0
        self.false_alarms = 0
        self.centroids: list[tuple] = []
        self.log = PerfLog(CameraCfg().urad_per_px, {"scenario": Path(video).name, "seed": "-", "config_hash": "-",
                                                     "mode": "MP4 benchmark (PTZ bypassed)", "ground_truth": bool(self.gt),
                                                     "video": {"width": self.W, "height": self.H, "fps": self.fps,
                                                               "frames": self.n_frames}})
        self.t_wall0 = time.perf_counter()
        self.last: dict = {}

    def _set_size(self, size: int) -> None:
        self.size = int(size)
        cs = self.size * self.scale
        self.coarse = BeaconDetector(max(2, round(cs)), median=cs >= 3, min_snr=7.0)
        # single-frame threshold 7 is safe here: the tracker needs 3 consistent hits before it declares LOCK
        self.fine = BeaconDetector(self.size, min_snr=7.0, min_snr_near=5.0)  # small gate once locked -> weaker hits OK
        self.tile_i = 0

    def _tiles(self) -> list[tuple[int, int, int, int]]:
        """2 x 2 overlapping tiles of the full-resolution frame (tiled search when the coarse pass is blind)."""
        hx, hy, o = self.W // 2, self.H // 2, 32
        return [(0, 0, hx + o, hy + o), (hx - o, 0, self.W, hy + o), (0, hy - o, hx + o, self.H), (hx - o, hy - o, self.W, self.H)]

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
            r = int(g + 2 * self.size + 8)
            near = self.trk.near_gate() if self.trk.state in (LOCK, COAST) else 0.0
            det = self.fine.detect(gray, (pred[0], pred[1]), g,
                                   (int(pred[0]) - r, int(pred[1]) - r, int(pred[0]) + r, int(pred[1]) + r), near)
        if det is None and self.trk.state not in (LOCK, ACQUIRE):
            small = cv2.resize(gray, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA) if self.scale < 1 else gray
            c = self.coarse.detect(small)
            if c is None and self.scale < 1:  # tiny beacon lost in the downsampled frame: full-resolution tile search
                tile = self._tiles()[self.tile_i % 4]
                self.tile_i += 1
                c = self.fine.detect(gray, roi=tile)
                if c is not None:
                    c.x, c.y = c.x * self.scale, c.y * self.scale
            if c is not None:
                cx, cy = c.x / self.scale, c.y / self.scale
                rr = 2 * self.size + 30
                det = self.fine.detect(gray, (cx, cy), rr, (int(cx) - rr, int(cy) - rr, int(cx) + rr, int(cy) + rr))
        state = self.trk.update(None if det is None else np.array([det.x, det.y]))
        if self.auto_size and not self.size_locked and state == LOCK and det is not None:
            est = estimate_spot_size(gray, det.x, det.y)  # adopt the beacon size only once the track is confirmed
            self.size_locked = True
            if est != self.size:
                self._set_size(est)
        if self.trk.initialised:
            self.center = self.trk.pos  # virtual camera window follows the estimate
        proc_ms = (time.perf_counter() - t0) * 1000

        g = self.gt.get(self.frame_no)
        has_gt = g is not None
        gx, gy = (g if has_gt else (math.nan, math.nan))
        if self.gt and not has_gt and det is not None and state == LOCK:
            self.false_alarms += 1  # locked detection reported while the ground truth says there is no beacon
        cent = None if (det is None or not has_gt) else float(math.hypot(det.x - gx, det.y - gy))
        terr = float(math.hypot(self.center[0] - gx, self.center[1] - gy)) if has_gt else math.nan
        in_fov = bool(has_gt and abs(gx - self.center[0]) < self.view[0] / 2 and abs(gy - self.center[1]) < self.view[1] / 2)
        self.log.add(frame=self.frame_no, t=round(self.t, 4), state=state, visible=has_gt or not self.gt,
                     in_fov=in_fov if self.gt else True, true_x=gx, true_y=gy, bore_x=float(self.center[0]), bore_y=float(self.center[1]),
                     det_x=None if det is None else det.x, det_y=None if det is None else det.y,
                     tracking_err_px=terr, centroid_err_px=cent, proc_ms=proc_ms)
        self.centroids.append((self.frame_no, round(self.t, 4), state,
                               None if det is None else round(det.x, 3), None if det is None else round(det.y, 3),
                               None if det is None else round(det.snr, 1), None if cent is None else round(cent, 4)))
        self.last = dict(image=gray, det=det, state=state, center=self.center.copy(), gt=None if not has_gt else (gx, gy),
                         cent_err=cent, proc_ms=proc_ms, t=self.t, frame_no=self.frame_no)
        self.frame_no += 1
        self.t += self.dt
        return self.last

    def finish(self) -> dict:
        wall = time.perf_counter() - self.t_wall0
        self.log.extra = {
            "end_to_end_fps": round(self.frame_no / max(wall, 1e-6), 1),  # decode + detect + track + logging
            "estimated_target_size_px": self.size,
            "false_alarm_frames": self.false_alarms if self.gt else None,
            "detection_rate_pct": round(100 * sum(c[3] is not None for c in self.centroids) / max(len(self.centroids), 1), 2),
        }
        return self.log.summary()

    def run(self) -> dict:
        while self.step() is not None:
            pass
        return self.finish()

    def write(self, out_dir: str | Path, stem: str) -> dict:
        s = self.finish()
        self.log.write(out_dir, stem)
        with open(Path(out_dir) / f"{stem}_centroids.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["frame", "t", "state", "x", "y", "snr", "centroid_err_px"])
            w.writerows(self.centroids)
        return s


# ---------------------------------------------------------------- batch + thresholds
DEFAULT_THRESHOLDS = {  # "predefined error values": override with --thresholds file.yaml
    "centroid_rmse_px": ("<=", 1.0),
    "acquisition_time_s": ("<=", 2.0),
    "max_reacquisition_s": ("<=", 1.0),
    "lock_retention_pct": (">=", 95.0),
    "end_to_end_fps": (">=", 20.0),
}


def load_thresholds(path: str | None) -> dict:
    if not path:
        return dict(DEFAULT_THRESHOLDS)
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    out = {}
    for k, v in raw.items():
        if isinstance(v, (list, tuple)):
            out[k] = (str(v[0]), float(v[1]))
        else:  # bare number: "lower is better" unless the metric is a rate / percentage
            out[k] = (">=" if k.endswith(("_pct", "_fps")) else "<=", float(v))
    return out


def _cmp(v, op, lim):
    if v is None or v != v:
        return None
    return {"<=": v <= lim, "<": v < lim, ">=": v >= lim, ">": v > lim}[op]


def run_batch(folder: str, out_dir: str, thresholds: str | None = None, pixel_centre: bool = False) -> list[dict]:
    """Benchmark every video in a folder (GT = <stem>_gt.csv next to it, if present) -> table + per-video logs."""
    th = load_thresholds(thresholds)
    vids = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in (".mp4", ".avi", ".mov", ".mkv"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for v in vids:
        gt = v.with_name(v.stem + "_gt.csv")
        vb = VideoBenchmark(str(v), str(gt) if gt.exists() else None, pixel_centre=pixel_centre)
        vb.run()
        s = vb.write(out, v.stem)
        verdict = {k: _cmp(s.get(k), op, lim) for k, (op, lim) in th.items()}
        s["threshold_pass"] = verdict
        s["threshold_all_pass"] = all(x for x in verdict.values() if x is not None)
        rows.append({"video": v.name, **s})
        print(f"{v.name:34s} {'PASS' if s['threshold_all_pass'] else 'FAIL'}  rmse {s['centroid_rmse_px']}  acq {s['acquisition_time_s']}  "
              f"lock {s['lock_retention_pct']}  e2e {s['end_to_end_fps']} fps", flush=True)
    head = ["Video", "GT", "Size (est.)", "Centroid RMSE (px)", "Acq. (s)", "Max re-acq. (s)", "Lock ret. (%)", "Detect (%)",
            "False alarms", "E2E FPS", "Thresholds"]
    L = ["# Benchmark-2 batch report", "", "Thresholds: " + ", ".join(f"`{k} {op} {lim:g}`" for k, (op, lim) in th.items()), "",
         "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        L.append(f"| {r['video']} | {'yes' if r['false_alarm_frames'] is not None else 'no'} | {r['estimated_target_size_px']} | "
                 f"{r['centroid_rmse_px']} | {r['acquisition_time_s']} | {r['max_reacquisition_s']} | {r['lock_retention_pct']} | "
                 f"{r['detection_rate_pct']} | {r['false_alarm_frames'] if r['false_alarm_frames'] is not None else '–'} | "
                 f"{r['end_to_end_fps']} | {'✅ PASS' if r['threshold_all_pass'] else '❌ ' + ', '.join(k for k, x in r['threshold_pass'].items() if x is False)} |")
    n_ok = sum(r["threshold_all_pass"] for r in rows)
    L += ["", f"**{n_ok} / {len(rows)} videos meet every threshold.**"]
    (out / "batch_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (out / "batch_summary.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    return rows


# ---------------------------------------------------------------- test-video generation
def make_test_video(out_mp4: str, sc: Scenario, seconds: float = 20.0, size: int | tuple[int, int] = 2000,
                    colour: bool = False, gaps: list | None = None) -> str:
    """Grader-style video: the complete screen, noise, moving beacon; writes <name>_gt.csv next to it.

    size: square side or (width, height). gaps: [[t, duration], ...] where the beacon is absent (empty GT rows).
    """
    W, H = (size, size) if isinstance(size, int) else size
    sc = copy.deepcopy(sc)
    rng = np.random.default_rng(sc.seed)
    sc.camera.screen_w, sc.camera.screen_h = W, H
    if gaps:
        sc.target.occlusions = list(sc.target.occlusions) + [list(g) for g in gaps]
    tgt = Target(sc, rng)
    ren = Renderer(sc, rng)
    fps = sc.camera.rate_hz
    vw = cv2.VideoWriter(str(out_mp4), cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H), isColor=colour)
    gt_path = str(Path(out_mp4).with_name(Path(out_mp4).stem + "_gt.csv"))
    with open(gt_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame", "x", "y"])
        for i in range(int(seconds * fps)):
            t = i / fps
            pos = tgt.update(t, 1 / fps)
            vis = tgt.visible(t)
            frame, rel = ren.render_region((W / 2, H / 2), (W, H), pos, vis)
            if colour:
                ff = frame.astype(np.float32)
                frame = np.clip(np.dstack([ff * 1.05, ff * 0.9, ff * 0.75]), 0, 255).astype(np.uint8)
            vw.write(frame)
            w.writerow([i, round(float(rel[0]), 3), round(float(rel[1]), 3)] if vis else [i, "", ""])
    vw.release()
    return gt_path


SUITE = [  # (name, preset, overrides, video size, colour, gaps)
    ("01_official_clean", "SIH-OFFICIAL", {}, 2000, False, None),
    ("02_max_noise", "NOISY", {"disturb.jitter_px": 0.0}, 2000, False, None),
    ("03_fog_small_5px", "NOISY", {"disturb.weather": "fog", "target.size": 5}, 2000, False, None),
    ("04_rain_large_20px", "NOISY", {"disturb.weather": "rain", "target.size": 20}, 2000, False, None),
    ("05_lowlight_fast_random", "NOISY", {"disturb.weather": "lowlight", "target.motion": "random", "target.speed": 300.0}, 2000, False, None),
    ("06_haze_circle_shape", "NOISY", {"disturb.weather": "haze", "target.shape": "circle", "target.motion": "circle"}, 2000, False, None),
    ("07_colour_1080p", "NOISY", {"target.motion": "line"}, (1920, 1080), True, None),
    ("08_beacon_absent_gaps", "NOISY", {"target.motion": "random"}, 2000, False, [[3.0, 1.5], [7.0, 0.8]]),
]


def make_suite(folder: str, seconds: float = 10.0) -> list[str]:
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for name, pre, over, size, colour, gaps in SUITE:
        sc = preset(pre)
        sc.seed = 100 + len(made)
        sc.target.occlusions = []
        for k, v in over.items():
            o, a = k.split(".")
            setattr(getattr(sc, o), a, v)
        make_test_video(str(out / f"{name}.mp4"), sc, seconds, size, colour, gaps)
        made.append(name)
        print("made", name, flush=True)
    return made
