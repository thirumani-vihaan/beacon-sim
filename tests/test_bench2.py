"""Benchmark-2 (grader .mp4, PTZ bypassed) robustness tests."""
import csv

import numpy as np
import pytest

from beacon_sim.config import preset
from beacon_sim.video_bench import VideoBenchmark, estimate_spot_size, load_gt, make_test_video, run_batch


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("suite")
    sc = preset("NOISY")
    sc.target.occlusions = []
    make_test_video(str(d / "a_square.mp4"), sc, seconds=2.0, size=1000)
    sc2 = preset("NOISY")
    sc2.target.occlusions, sc2.target.size, sc2.seed = [], 18, 7
    make_test_video(str(d / "b_big_colour.mp4"), sc2, seconds=2.0, size=(1280, 720), colour=True, gaps=[[0.8, 0.4]])
    return d


def test_colour_non_square_video_with_gaps(clips):
    vb = VideoBenchmark(str(clips / "b_big_colour.mp4"), str(clips / "b_big_colour_gt.csv"))
    s = vb.run()
    assert (vb.W, vb.H) == (1280, 720)
    assert s["centroid_rmse_px"] < 1.0 and s["acquisition_time_s"] <= 2.0
    assert s["false_alarm_frames"] == 0
    assert abs(s["estimated_target_size_px"] - 18) <= 3


def test_no_ground_truth_reports_na_not_fail(clips):
    vb = VideoBenchmark(str(clips / "a_square.mp4"), None)
    s = vb.run()
    assert s["pass"]["mean_tracking_error_px"] is None and s["pass"]["target_loss_pct"] is None
    assert s["all_pass"] and s["detection_rate_pct"] > 90


def test_batch_with_predefined_thresholds(clips, tmp_path):
    th = tmp_path / "th.yaml"
    th.write_text("centroid_rmse_px: 1.0\nlock_retention_pct: 90\nend_to_end_fps: 5\n", encoding="utf-8")
    rows = run_batch(str(clips), str(tmp_path / "out"), str(th))
    assert len(rows) == 2 and all(r["threshold_all_pass"] for r in rows)
    assert (tmp_path / "out" / "batch_report.md").exists()
    assert (tmp_path / "out" / "a_square_centroids.csv").exists()


def test_ground_truth_column_aliases_and_pixel_centre(tmp_path):
    p = tmp_path / "gt.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["frame_no", "cx", "cy"])
        w.writerow([0, 10, 20])
        w.writerow([1, "", ""])
    assert load_gt(str(p)) == {0: (10.0, 20.0)}
    assert load_gt(str(p), pixel_centre=True) == {0: (10.5, 20.5)}


@pytest.mark.parametrize("size", [5, 10, 20])
def test_spot_size_estimation(size):
    img = np.full((200, 200), 30, np.uint8)
    img[90:90 + size, 80:80 + size] = 220
    assert abs(estimate_spot_size(img, 80 + size / 2, 90 + size / 2) - size) <= 1
