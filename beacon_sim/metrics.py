"""Performance logging: per-frame records, run summary with the official metrics, pass/fail against the PS specs."""
from __future__ import annotations

import csv
import json
import platform
import time
import warnings
from pathlib import Path

import numpy as np

from .config import SPECS
from .tracker import LOCK

FIELDS = ["frame", "t", "state", "visible", "in_fov", "true_x", "true_y", "bore_x", "bore_y", "det_x", "det_y",
          "tracking_err_px", "centroid_err_px", "proc_ms"]


class PerfLog:
    def __init__(self, urad_per_px: float, meta: dict):
        self.rows: list[dict] = []
        self.urad = urad_per_px
        self.meta = meta
        self.extra: dict = {}  # additional summary fields supplied by the caller (e.g. end-to-end FPS)
        self.t_wall0 = time.perf_counter()

    def add(self, **r) -> None:
        self.rows.append(r)

    # ------------------------------------------------------------------
    def summary(self) -> dict:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return self._summary()

    def _summary(self) -> dict:
        R = self.rows
        if not R:
            return {}
        dt = R[1]["t"] - R[0]["t"] if len(R) > 1 else 1 / 30
        first = next((i for i, r in enumerate(R) if r["state"] == LOCK), None)
        acq = R[first]["t"] if first is not None else float("nan")
        # alternative reading of row 16: time from the beacon first entering the camera FOV until LOCK
        fov0 = next((i for i, r in enumerate(R) if r["in_fov"]), None)
        acq_fov = (R[first]["t"] - R[fov0]["t"]) if (first is not None and fov0 is not None and fov0 <= first) else float("nan")
        post = R[first:] if first is not None else []
        vis = [r for r in post if r["visible"]]
        settle = acq + 0.5  # tracking-error statistics start 0.5 s after first lock (pull-in transient excluded)
        vis_s = [r for r in vis if r["t"] >= settle]
        lock_ret = 100 * sum(r["state"] == LOCK for r in vis) / max(len(vis), 1)
        loss = 100 * sum(not r["in_fov"] for r in vis) / max(len(vis), 1)
        te = np.array([r["tracking_err_px"] for r in vis_s]) if vis_s else np.array([np.nan])
        ce = np.array([r["centroid_err_px"] for r in post if r["centroid_err_px"] is not None and r["state"] == LOCK])
        ce = ce if ce.size else np.array([np.nan])
        # re-acquisition: every LOCK -> non-LOCK drop measured until LOCK again (counting from beacon re-appearance)
        reacq, lost_at = [], None
        for i in range(first or 0, len(R)):
            r = R[i]
            if lost_at is None and r["state"] != LOCK and i > (first or 0):
                lost_at = i
            elif lost_at is not None and r["state"] == LOCK:
                start = next((j for j in range(lost_at, i + 1) if R[j]["visible"]), lost_at)
                reacq.append((i - start + 1) * dt)  # includes the frame in which lock is re-declared
                lost_at = None
        proc = np.array([r["proc_ms"] for r in R])
        wall = time.perf_counter() - self.t_wall0
        s = {
            "simulation_duration_s": round(R[-1]["t"] + dt, 3),
            "frames": len(R),
            "processing_fps": round(1000 / max(float(proc.mean()), 1e-6), 1),
            "wall_fps": round(len(R) / max(wall, 1e-6), 1),
            "acquisition_time_s": round(acq, 3),
            "acquisition_from_fov_s": round(acq_fov, 3),
            "mean_tracking_error_px": round(float(np.nanmean(te)), 2),
            "max_tracking_error_px": round(float(np.nanmax(te)), 2),
            "mean_tracking_error_urad": round(float(np.nanmean(te)) * self.urad, 1),
            "centroid_rmse_px": round(float(np.sqrt(np.nanmean(ce ** 2))), 3),
            "mean_centroid_error_px": round(float(np.nanmean(ce)), 3),
            "lock_retention_pct": round(lock_ret, 2),
            "target_loss_pct": round(loss, 2),
            "reacquisitions": len(reacq),
            "max_reacquisition_s": round(max(reacq), 3) if reacq else 0.0,
            "mean_reacquisition_s": round(float(np.mean(reacq)), 3) if reacq else 0.0,
            "processing_ms_mean": round(float(proc.mean()), 2),
            "processing_ms_p95": round(float(np.percentile(proc, 95)), 2),
        }
        s["pass"] = {k: _check(s[k], *SPECS[k]) for k in SPECS}
        if self.meta.get("ground_truth") is False:  # MP4 without ground truth: truth-based metrics are not applicable
            for k in ("mean_tracking_error_px", "target_loss_pct"):
                s["pass"][k] = None
        s.update(self.extra)
        s["all_pass"] = bool(all(v for v in s["pass"].values() if v is not None))
        return s

    def write(self, out_dir: str | Path, stem: str = "run") -> dict:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        with open(out / f"{stem}_frames.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, FIELDS)
            w.writeheader()
            for r in self.rows:
                w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k in FIELDS})
        s = self.summary()
        meta = dict(self.meta, python=platform.python_version(), machine=platform.processor() or platform.machine())
        (out / f"{stem}_summary.json").write_text(json.dumps({"meta": meta, "metrics": s}, indent=2), encoding="utf-8")
        (out / f"{stem}_summary.md").write_text(to_markdown(meta, s), encoding="utf-8")
        return s


def _check(v, op, lim) -> bool:
    if v != v:  # NaN
        return False
    return bool({"<=": v <= lim, "<": v < lim, ">=": v >= lim}[op])


def to_markdown(meta: dict, s: dict) -> str:
    L = ["# BEACON-SIM performance log", "",
         f"Scenario **{meta.get('scenario')}** · seed {meta.get('seed')} · config {meta.get('config_hash')} · {meta.get('mode', 'simulation')}", "",
         "| Metric | Value | Official spec | Result |", "|---|---|---|---|"]
    spec_txt = {k: f"{op} {lim}" for k, (op, lim) in SPECS.items()}
    for k, v in s.items():
        if k in ("pass", "all_pass"):
            continue
        res = ({True: "PASS", False: "FAIL", None: "N/A"}[s["pass"][k]]) if k in s["pass"] else ""
        L.append(f"| {k} | {v} | {spec_txt.get(k, '')} | {res} |")
    L += ["", f"**Overall: {'ALL OFFICIAL SPECS MET' if s.get('all_pass') else 'SOME SPECS NOT MET'}**"]
    fz = meta.get("feasibility")
    if fz:
        L += ["", "## Physical feasibility", "",
              f"Slew budget {fz['slew_px_s']} px/s · required {fz['required_px_s']} px/s · spare {fz['spare_px_s']} px/s · "
              f"worst-case acquisition {fz['worst_case_acquisition_s']} s"]
        L += [f"- ⚠ {n}" for n in fz["notes"]] or ["- ✓ every official spec is physically achievable for this scenario"]
    if meta.get("warnings"):
        L += ["", "## Parameter warnings", ""] + [f"- {w}" for w in meta["warnings"]]
    return "\n".join(L) + "\n"
