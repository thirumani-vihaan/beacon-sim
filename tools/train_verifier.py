"""Train the AI beacon verifier (small CNN) on candidates mined from the BEACON-SIM simulator.

    python tools/train_verifier.py            # a few minutes on a laptop CPU
Writes beacon_sim/models/verifier.onnx and beacon_sim/models/verifier_card.json.

Data: randomised scenarios spanning every official disturbance (salt-and-pepper, Gaussian, Poisson, weather,
contrast/brightness, turbulence), beacon sizes 5-20 px and all shapes. The classical detector proposes candidates at
a deliberately low threshold; candidates within 0.35 x size of the ground truth are positives, those farther than
max(4, size) px are negatives (noise clumps, stars, rain streaks, filter artefacts). Train/validation split is by
scenario, so validation frames come from scenes the network never saw.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from beacon_sim.ai import MODEL_PATH, PATCH, extract_patch  # noqa: E402
from beacon_sim.config import SHAPES, WEATHERS, Scenario  # noqa: E402
from beacon_sim.detect import BeaconDetector  # noqa: E402
from beacon_sim.scene import Renderer, Target  # noqa: E402

N_SCENES, FRAMES = 900, 10
SEED = 2026


def random_scenario(rng: np.random.Generator, i: int) -> Scenario:
    sc = Scenario(name=f"train{i}", seed=int(rng.integers(1 << 30)))
    t, d = sc.target, sc.disturb
    t.size = int(rng.integers(5, 21))
    t.shape = SHAPES[0] if rng.random() < 0.5 else str(rng.choice(SHAPES))
    t.motion = str(rng.choice(["line", "circle", "figure8", "random"]))
    t.brightness = float(rng.uniform(110, 245))
    t.occlusions = []
    d.weather = str(rng.choice(WEATHERS))
    d.salt_pepper = float(rng.choice([0.0, rng.uniform(0, 0.12)]))
    d.gaussian_sigma = float(rng.uniform(0, 24))
    d.poisson = bool(rng.random() < 0.5)
    d.contrast = float(rng.uniform(0.6, 1.2))
    d.brightness = float(rng.uniform(-30, 30))
    d.turbulence_cn2 = float(rng.choice([0.0, 0.0, 0.0, 1e-15, 1e-14]))
    return sc


def mine(n_scenes: int, rng: np.random.Generator):
    X, Y, G = [], [], []
    for i in range(n_scenes):
        sc = random_scenario(rng, i)
        r = np.random.default_rng(sc.seed)
        tgt, ren = Target(sc, r), Renderer(sc, r)
        det = BeaconDetector(sc.target.size, k_sigma=4.0, min_snr=4.0)
        size = sc.target.size
        for f in range(FRAMES):
            pos = tgt.update(f * 0.25, 0.25)
            view = pos + (rng.uniform(-260, 260, 2) if rng.random() < 0.75 else rng.uniform(-1500, 1500, 2))
            frame, rel = ren.render(view, pos, True)
            inside = 0 <= rel[0] < frame.shape[1] and 0 <= rel[1] < frame.shape[0]
            for c in det.candidates(frame, k=10, min_snr=4.0):
                dist = float(np.hypot(c.x - rel[0], c.y - rel[1])) if inside else 1e9
                if dist <= max(1.5, 0.35 * size):
                    for _ in range(3):  # sub-pixel augmentation of the (rarer) positives
                        jx, jy = rng.normal(0, 0.5, 2)
                        X.append(extract_patch(frame, c.x + jx, c.y + jy, size)), Y.append(1), G.append(i)
                elif dist > max(4.0, size):
                    X.append(extract_patch(frame, c.x, c.y, size)), Y.append(0), G.append(i)
        if (i + 1) % 100 == 0:
            print(f"  mined {i + 1}/{n_scenes} scenes · {len(Y)} patches · {int(np.sum(Y))} positive", flush=True)
    return np.stack(X)[:, None], np.array(Y, np.float32), np.array(G)


class VerifierNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.f = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),     # 16 x 16
            nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),    # 8 x 8
            nn.Conv2d(32, 48, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),    # 4 x 4
            nn.Flatten(), nn.Linear(48 * 16, 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, 1))

    def forward(self, x):
        return torch.sigmoid(self.f(x))


def auc(y, p):
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    npos = y.sum()
    return float((ranks[y == 1].sum() - npos * (npos + 1) / 2) / (npos * (len(y) - npos)))


def main():
    t0 = time.time()
    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)
    print("mining candidates from the simulator ...", flush=True)
    X, Y, G = mine(N_SCENES, rng)
    val = G >= int(N_SCENES * 0.8)
    Xtr, Ytr, Xva, Yva = torch.tensor(X[~val]), torch.tensor(Y[~val]), torch.tensor(X[val]), torch.tensor(Y[val])
    print(f"train {len(Ytr)} ({int(Ytr.sum())} pos) · val {len(Yva)} ({int(Yva.sum())} pos)", flush=True)
    net = VerifierNet()
    opt = torch.optim.Adam(net.parameters(), lr=2e-3, weight_decay=1e-4)
    w_pos = float((1 - Ytr.mean()) / Ytr.mean())
    for ep in range(10):
        net.train()
        perm = torch.randperm(len(Ytr))
        tot = 0.0
        for b in range(0, len(perm), 256):
            idx = perm[b:b + 256]
            xb = Xtr[idx]
            if torch.rand(1).item() < 0.5:  # flips / 90-degree rotations: the beacon has no preferred orientation
                xb = torch.flip(xb, dims=[3])
            xb = torch.rot90(xb, int(torch.randint(0, 4, (1,)).item()), dims=[2, 3])
            p = net(xb).squeeze(1).clamp(1e-6, 1 - 1e-6)
            yb = Ytr[idx]
            loss = -(w_pos * yb * torch.log(p) + (1 - yb) * torch.log(1 - p)).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item() * len(idx)
        net.eval()
        with torch.no_grad():
            pv = torch.cat([net(Xva[b:b + 2048]) for b in range(0, len(Yva), 2048)]).squeeze(1).numpy()
        yv = Yva.numpy()
        print(f"epoch {ep + 1:2d}  loss {tot / len(Ytr):.4f}  val AUC {auc(yv, pv):.4f}  "
              f"recall@0.5 {np.mean(pv[yv == 1] >= 0.5):.3f}  false-pos@0.5 {np.mean(pv[yv == 0] >= 0.5):.4f}", flush=True)

    MODEL_PATH.parent.mkdir(exist_ok=True)
    net.eval()
    torch.onnx.export(net, torch.zeros(1, 1, PATCH, PATCH), str(MODEL_PATH), input_names=["patch"], output_names=["p_beacon"],
                      dynamic_axes={"patch": {0: "n"}, "p_beacon": {0: "n"}}, opset_version=13, dynamo=False)
    import cv2
    cvnet = cv2.dnn.readNetFromONNX(str(MODEL_PATH))
    cvnet.setInput(X[val][:64])
    diff = float(np.abs(cvnet.forward().reshape(-1) - pv[:64]).max())
    yv = Yva.numpy()
    card = {
        "model": "BEACON-SIM verifier CNN (3 conv + 2 FC, sigmoid)", "params": int(sum(p.numel() for p in net.parameters())),
        "input": f"1x{PATCH}x{PATCH} scale-normalised patch (side = 3 x beacon size, robust z-score)",
        "training_scenes": int(N_SCENES * 0.8), "validation_scenes": N_SCENES - int(N_SCENES * 0.8),
        "train_patches": int(len(Ytr)), "val_patches": int(len(Yva)), "val_positive": int(yv.sum()),
        "val_auc": round(auc(yv, pv), 4),
        "val_recall_at_0.5": round(float(np.mean(pv[yv == 1] >= 0.5)), 4),
        "val_false_positive_rate_at_0.5": round(float(np.mean(pv[yv == 0] >= 0.5)), 5),
        "opencv_vs_torch_max_abs_diff": diff, "seed": SEED, "train_time_s": round(time.time() - t0, 1),
        "torch": torch.__version__,
    }
    MODEL_PATH.with_name("verifier_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    print(json.dumps(card, indent=2))


if __name__ == "__main__":
    main()
