"""CLI entry point.

  python -m beacon_sim                         # GUI
  python -m beacon_sim --judge                 # GUI running the scripted judge demo
  python -m beacon_sim --headless --preset NOISY --seed 7 --duration 40 --out runs
  python -m beacon_sim --sweep --seeds 3 --out runs            # all presets x seeds -> comparison table
  python -m beacon_sim --bench video.mp4 [--gt video_gt.csv]   # MP4 benchmark (PTZ bypassed), headless
  python -m beacon_sim --make-video samples/test.mp4 --preset NOISY --seconds 20
  python -m beacon_sim --make-suite samples/suite --seconds 10                # 8 varied grader-style videos + GT
  python -m beacon_sim --bench-dir samples/suite [--thresholds th.yaml] --out runs/bench2   # batch Benchmark-2
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path


def main() -> None:
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    ap = argparse.ArgumentParser(prog="beacon_sim")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--preset", default="SIH-OFFICIAL")
    ap.add_argument("--scenario", help="YAML scenario file (overrides --preset)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--duration", type=float)
    ap.add_argument("--no-imu", action="store_true", help="disable IMU feed-forward (ablation)")
    ap.add_argument("--no-ai", action="store_true", help="disable the CNN candidate verifier in simulation (ablation)")
    ap.add_argument("--ai", action="store_true", help="enable the CNN verifier in MP4 benchmark mode (off by default)")
    ap.add_argument("--out", default="runs")
    ap.add_argument("--bench")
    ap.add_argument("--gt")
    ap.add_argument("--gt-pixel-centre", action="store_true", help="GT integer coords are pixel centres (+0.5 px)")
    ap.add_argument("--bench-dir", help="benchmark every video in this folder")
    ap.add_argument("--thresholds", help="YAML of predefined error thresholds for --bench-dir")
    ap.add_argument("--make-suite", help="write a suite of grader-style test videos into this folder")
    ap.add_argument("--make-video")
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--record")
    ap.add_argument("--mp4")
    a = ap.parse_args()

    from .config import PRESETS, Scenario, preset
    if a.make_suite:
        from .video_bench import make_suite
        make_suite(a.make_suite, a.seconds)
    elif a.bench_dir:
        from .video_bench import run_batch
        rows = run_batch(a.bench_dir, a.out, a.thresholds, a.gt_pixel_centre, ai=a.ai)
        print(f"{sum(r['threshold_all_pass'] for r in rows)} / {len(rows)} videos meet every threshold -> {Path(a.out) / 'batch_report.md'}")
    elif a.make_video:
        from .video_bench import make_test_video
        sc = Scenario.load(a.scenario) if a.scenario else preset(a.preset)
        sc.seed = a.seed
        gt = make_test_video(a.make_video, sc, a.seconds)
        print(f"wrote {a.make_video} and {gt}")
    elif a.bench:
        from .video_bench import VideoBenchmark
        gt = a.gt
        if gt is None:
            cand = Path(a.bench).with_name(Path(a.bench).stem + "_gt.csv")
            gt = str(cand) if cand.exists() else None
        vb = VideoBenchmark(a.bench, gt, pixel_centre=a.gt_pixel_centre, ai=a.ai)
        vb.run()
        s = vb.write(a.out, Path(a.bench).stem + "_bench")
        print(json.dumps(s, indent=2, default=str))
    elif a.sweep:
        from .sim import run_headless
        rows = ["| Preset | Seed | Acq (s) | Mean err (px) | Centroid RMSE (px) | Lock ret. (%) | Loss (%) | Max re-acq (s) | Proc FPS | All specs |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        for p in PRESETS:
            for sd in range(a.seeds):
                sc = preset(p)
                sc.seed = sd
                sc.imu_aid = not a.no_imu
                sc.ai_verifier = not a.no_ai
                if a.duration:
                    sc.duration_s = a.duration
                s = run_headless(sc, a.out)
                rows.append(f"| {p} | {sd} | {s['acquisition_time_s']} | {s['mean_tracking_error_px']} | {s['centroid_rmse_px']} | "
                            f"{s['lock_retention_pct']} | {s['target_loss_pct']} | {s['max_reacquisition_s']} | {s['processing_fps']} | "
                            f"{'PASS' if s['all_pass'] else 'FAIL: ' + ', '.join(k for k, v in s['pass'].items() if not v)} |")
                print(rows[-1], flush=True)
        Path(a.out).mkdir(parents=True, exist_ok=True)
        (Path(a.out) / "sweep_table.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    elif a.headless:
        from .sim import run_headless
        sc = Scenario.load(a.scenario) if a.scenario else preset(a.preset)
        sc.seed = a.seed
        sc.imu_aid = sc.imu_aid and not a.no_imu
        sc.ai_verifier = sc.ai_verifier and not a.no_ai
        if a.duration:
            sc.duration_s = a.duration
        s = run_headless(sc, a.out)
        print(json.dumps(s, indent=2, default=str))
    else:
        from .app import main as gui
        argv = []
        if a.judge:
            argv.append("--judge")
        if a.record:
            argv += ["--record", a.record]
        if a.mp4:
            argv += ["--mp4", a.mp4]
        gui(argv)


if __name__ == "__main__":
    main()
