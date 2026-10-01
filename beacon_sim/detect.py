"""Beacon detection: robust pre-filtering + matched (box) filter + blob scoring + sub-pixel intensity-weighted centroid."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Detection:
    x: float          # sub-pixel centroid, frame coords
    y: float
    snr: float        # peak response / robust noise
    area: int
    score: float = 0.0          # classical ranking score
    p_ai: float | None = None   # AI verifier probability (None when the verifier is off)


class BeaconDetector:
    """Classical detector tuned for the official noise set.

    Pipeline: median 3x3 (removes salt-and-pepper) -> background removal (large box blur, removes haze/fog veil and
    gradients) -> matched box filter sized to the beacon (optimal for a square spot in white noise) -> robust
    threshold (median + k * MAD) -> connected components scored by peak response and distance to the prediction
    -> intensity-weighted sub-pixel centroid on the de-noised image.
    """

    def __init__(self, target_size: int = 10, k_sigma: float = 6.0, min_snr: float = 9.0, median: bool = True,
                 min_snr_near: float = 6.5, verifier=None, min_snr_ai: float = 6.0, k_ai: int = 6):
        self.size, self.k, self.min_snr, self.median = target_size, k_sigma, min_snr, median
        self.min_snr_near = min_snr_near  # gated detection: a weaker hit is accepted right where the tracker predicts
        self.edge_frac = 0.08
        self.verifier = verifier          # optional AI verifier (beacon_sim.ai.Verifier)
        self.min_snr_ai, self.k_ai = min_snr_ai, k_ai  # with the verifier: lower threshold, top-K candidates
        self.ai_veto = 0.1  # a classically confident candidate is dropped only if the CNN gives it < 10 %
        self.last_candidates: list[Detection] = []

    def detect(self, frame: np.ndarray, predict: tuple[float, float] | None = None, gate: float = 1e9,
               roi: tuple[int, int, int, int] | None = None, near: float = 0.0) -> Detection | None:
        """Best beacon detection. With the AI verifier: top-K candidates at a lower SNR threshold, clutter rejected."""
        if self.verifier is None:
            c = self.candidates(frame, predict, gate, roi, near, k=1)
            return c[0] if c else None
        c = self.candidates(frame, predict, gate, roi, near, k=self.k_ai, min_snr=min(self.min_snr, self.min_snr_ai))
        self.last_candidates = c
        if not c:
            return None
        probs = self.verifier.probs(frame, [(d.x, d.y) for d in c], self.size)
        # cascade: classically confident candidates survive unless the CNN strongly vetoes them; the CNN decides the
        # ambiguous low-SNR ones (this is where it adds recall without adding false locks)
        best = None
        for d, pr in zip(c, probs):
            d.p_ai = float(pr)
            ok = pr >= self.verifier.threshold or (d.snr >= self.min_snr and pr >= self.ai_veto)
            if ok and (best is None or pr + 0.01 * d.score > best.p_ai + 0.01 * best.score):
                best = d
        return best

    def candidates(self, frame: np.ndarray, predict: tuple[float, float] | None = None, gate: float = 1e9,
                   roi: tuple[int, int, int, int] | None = None, near: float = 0.0, k: int = 1,
                   min_snr: float | None = None) -> list[Detection]:
        """Up to k refined candidates, best classical score first."""
        min_far = self.min_snr if min_snr is None else min_snr
        ox = oy = 0
        img = frame
        if roi is not None:
            x0, y0, x1, y1 = roi
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(frame.shape[1], x1), min(frame.shape[0], y1)
            if x1 - x0 < 16 or y1 - y0 < 16:
                return []
            img, ox, oy = frame[y0:y1, x0:x1], x0, y0
        med = (cv2.medianBlur(img, 3) if self.median else img).astype(np.float32)
        bgk = max(31, self.size * 4 + 1)
        hp = med - cv2.blur(med, (bgk, bgk))
        k = max(3, int(round(self.size * 0.8)))
        resp = cv2.blur(hp, (k, k))
        sample = resp[::4, ::4]
        mu = float(np.median(sample))
        mad = max(float(np.median(np.abs(sample - mu))) * 1.4826, 1.0)  # floor: clean frames must not threshold at ~0
        k_thr = min(self.k, self.min_snr_near) if (predict is not None and near > 0) else self.k
        thr = mu + min(k_thr, min_far) * mad
        mask = (resp > thr).astype(np.uint8)
        n, lab, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if n <= 1:
            return []
        areas = stats[1:, cv2.CC_STAT_AREA]
        cand = np.where(areas >= 3)[0] + 1
        if cand.size > 25:  # keep the 25 largest blobs: bounded cost even in heavy clutter
            cand = cand[np.argsort(-areas[cand - 1])[:25]]
        found = []
        for i in cand:
            area = stats[i, cv2.CC_STAT_AREA]
            x, y, w, h = stats[i, :4]
            peak = float(resp[y:y + h, x:x + w].max())
            snr = (peak - mu) / mad
            cx, cy = cents[i][0] + ox, cents[i][1] + oy
            close = predict is not None and near > 0 and np.hypot(cx - predict[0], cy - predict[1]) <= near
            if snr < (self.min_snr_near if close else min_far):
                continue
            m = max(2, self.size // 2)
            if cx < m or cy < m or cx > frame.shape[1] - m or cy > frame.shape[0] - m:
                continue  # filter/border artefacts at the image edge
            score = snr
            if predict is not None:
                dist = np.hypot(cx - predict[0], cy - predict[1])
                if dist > gate:
                    continue
                score -= 0.08 * dist
            size_pen = abs(np.sqrt(area) - self.size) / max(self.size, 1)
            score -= 3.0 * size_pen
            found.append((score, cx, cy, snr, area))
        found.sort(key=lambda f: -f[0])
        out = []
        for score, cx, cy, snr, area in found[:k]:
            d = self._refine(med, hp, cx - ox, cy - oy, snr, area, ox, oy)
            d.score = float(score)
            out.append(d)
        return out

    def _refine(self, med, hp, cx, cy, snr, area, ox, oy) -> Detection:
        r = self.size // 2 + max(4, self.size // 3)
        x0, y0 = int(max(0, round(cx) - r)), int(max(0, round(cy) - r))
        x1, y1 = int(min(hp.shape[1], round(cx) + r + 1)), int(min(hp.shape[0], round(cy) + r + 1))
        patch = hp[y0:y1, x0:x1]
        if patch.shape[0] < 5 or patch.shape[1] < 5:
            return Detection(cx + ox, cy + oy, snr, area)
        # background level from the window's outer ring (never from the spot itself, whatever its size)
        ring = np.concatenate([patch[:2].ravel(), patch[-2:].ravel(), patch[2:-2, :2].ravel(), patch[2:-2, -2:].ravel()])
        base = float(np.median(ring))
        wts = np.clip(patch - base, 0, None)
        ring_sig = 1.4826 * float(np.median(np.abs(ring - base))) + 1e-6
        # keep every pixel clearly above the local noise (partial-coverage edge pixels included -> unbiased centroid)
        wts = wts * (wts > max(3.0 * ring_sig, self.edge_frac * wts.max()))
        s = wts.sum()
        if s <= 0:
            return Detection(cx + ox, cy + oy, snr, area)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        # +0.5: pixel i covers [i, i+1), so its centre is at i + 0.5
        return Detection(float((wts * xx).sum() / s) + 0.5 + ox, float((wts * yy).sum() / s) + 0.5 + oy, snr, area)
