"""AI beacon verifier: a small CNN that scores detector candidates (beacon vs clutter / noise / artefacts).

Trained offline with PyTorch on candidates mined from the simulator (tools/train_verifier.py) and shipped as an
ONNX file. At runtime it is executed with OpenCV's DNN module, so the application needs no deep-learning framework
and stays CPU-only. The classical detector proposes up to K candidates at a lowered SNR threshold; the verifier
rejects clutter, which keeps false locks down while faint beacons (fog, low light, 5 px spots) are still found.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

PATCH = 32
MODEL_PATH = Path(__file__).with_name("models") / "verifier.onnx"


def extract_patch(frame: np.ndarray, x: float, y: float, size: float) -> np.ndarray:
    """Scale-normalised 32 x 32 patch centred on (x, y): side = 3 x beacon size (min 24 px), robust z-scored."""
    side = int(max(24, round(3 * size)))
    half = side / 2.0
    x0, y0 = int(round(x - half)), int(round(y - half))
    h, w = frame.shape[:2]
    pad = side
    if x0 < 0 or y0 < 0 or x0 + side > w or y0 + side > h:
        f = cv2.copyMakeBorder(frame, pad, pad, pad, pad, cv2.BORDER_REFLECT)
        crop = f[y0 + pad:y0 + pad + side, x0 + pad:x0 + pad + side]
    else:
        crop = frame[y0:y0 + side, x0:x0 + side]
    p = cv2.resize(crop.astype(np.float32), (PATCH, PATCH), interpolation=cv2.INTER_AREA)
    med = float(np.median(p))
    mad = float(np.median(np.abs(p - med))) * 1.4826
    return np.clip((p - med) / (mad + 2.0), -6.0, 30.0).astype(np.float32)


class Verifier:
    """ONNX CNN -> probability that each candidate is the beacon."""

    def __init__(self, path: str | Path = MODEL_PATH, threshold: float = 0.5):
        self.path = Path(path)
        self.net = cv2.dnn.readNetFromONNX(str(self.path))
        self.threshold = threshold

    @classmethod
    def load_default(cls) -> "Verifier | None":
        return cls() if MODEL_PATH.exists() else None

    def probs(self, frame: np.ndarray, pts: list[tuple[float, float]], size: float) -> np.ndarray:
        if not pts:
            return np.zeros(0, np.float32)
        batch = np.stack([extract_patch(frame, x, y, size) for x, y in pts])[:, None]
        self.net.setInput(batch)
        out = self.net.forward()
        return out.reshape(-1).astype(np.float32)
