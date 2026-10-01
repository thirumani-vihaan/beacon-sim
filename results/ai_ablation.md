# AI verifier — training card and ablation

## Model

| Item | Value |
|---|---|
| Architecture | 3 × (conv 3×3 + ReLU + max-pool) → FC 64 → sigmoid; **67,953 parameters** |
| Input | 32 × 32 scale-normalised patch around a detector candidate (side = 3 × beacon size, robust z-score) |
| Training data | 34,732 candidates mined from 900 randomised simulator scenes (all official disturbances, sizes 5–20 px, all shapes), labelled against ground truth |
| Split | by scene: 720 train / 180 validation scenes (validation scenes never seen in training) |
| Validation | **AUC 0.9989 · recall 97.1 % · false-positive rate 0.09 %** at p = 0.5 |
| Runtime | ONNX executed by OpenCV DNN (no deep-learning framework at runtime, CPU only); OpenCV vs PyTorch max difference 6 × 10⁻⁸ |
| Reproduce | `python tools/train_verifier.py` (seed 2026) → `beacon_sim/models/verifier.onnx` + `verifier_card.json` |

## How it is used (cascade)

The classical detector proposes its top 6 candidates at a lowered threshold (SNR ≥ 6 instead of 9). A classically confident candidate (SNR ≥ 9) is kept unless the CNN vetoes it (p < 0.1); a low-SNR candidate is accepted only if the CNN says p ≥ 0.5. The CNN therefore adds recall for faint beacons without adding false locks.

## Closed-loop ablation (3 seeds × 15 s each, default configuration with the wide-field cue)

| Scenario | Classical only | Classical + AI verifier |
|---|---|---|
| NOISY, 5 px beacon | acq 0.27 s · RMSE 0.23 px · 3/3 pass | identical |
| RAIN-LOWLIGHT, 5 px | acq 0.28 s · RMSE 0.14 px · 3/3 pass | identical |
| SIH-MAX, 5 px | acq 0.21 s · RMSE 0.22 px · 3/3 pass | identical |
| SEVERE, 5 px | acq 0.58 s · **RMSE 1.48 px** · 3 wrong-lock frames | acq 0.49 s · **RMSE 0.47 px** · **0 wrong-lock frames** |
| NOISY + fog, 5 px | **never acquires** (0/3 pass) | **acquires in 1.64 s**, 89 % lock retention (2/3 pass) |
| NOISY + low light, dim 6 px | acq 1.51 s · 1 wrong-lock frame · 2/3 pass | **acq 0.96 s · 0 wrong-lock frames · 3/3 pass** |

The AI never makes the default configuration worse and turns the faintest official cases from "not acquired" into "acquired".

**Honest trade-off (narrow camera only, wide-field cue disabled):** with only the 640 × 480 camera, the verifier raises lock retention (e.g. SIH-MAX 5 px: 67 → 100 %, fog 5 px: 32 → 90 %) but can delay the first lock by ~0.5–1 s while the spiral search passes faint candidates it is not yet sure about.
