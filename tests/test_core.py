import numpy as np
import pytest

from beacon_sim.config import SPECS, Scenario, preset
from beacon_sim.detect import BeaconDetector
from beacon_sim.sim import Simulation
from beacon_sim.video_bench import VideoBenchmark, make_test_video


def _run(sc: Scenario, seconds: float) -> dict:
    sc.duration_s = seconds
    sim = Simulation(sc)
    return sim.run()


def test_official_specs_are_the_published_ones():
    assert SPECS["acquisition_time_s"] == ("<=", 2.0)
    assert SPECS["mean_tracking_error_px"] == ("<=", 10.0)
    assert SPECS["target_loss_pct"] == ("<", 5.0)
    assert SPECS["max_reacquisition_s"] == ("<=", 1.0)
    assert SPECS["processing_fps"] == (">=", 20.0)
    cam = preset("SIH-OFFICIAL").camera
    assert (cam.res_w, cam.res_h, cam.fov_x_deg, cam.fov_y_deg) == (640, 480, 4.0, 3.0)
    assert cam.px_per_deg == pytest.approx(160.0)


def test_detector_subpixel_centroid_on_noisy_frame():
    rng = np.random.default_rng(0)
    img = rng.normal(40, 12, (480, 640)).clip(0, 255)
    x0, y0, s = 300.3, 200.7, 10
    yy, xx = np.mgrid[0:480, 0:640]
    cx, cy = x0 + s / 2, y0 + s / 2
    img[(xx + 0.5 >= x0) & (xx + 0.5 < x0 + s) & (yy + 0.5 >= y0) & (yy + 0.5 < y0 + s)] += 150
    det = BeaconDetector().detect(img.clip(0, 255).astype(np.uint8))
    assert det is not None
    assert abs(det.x - cx) < 1.0 and abs(det.y - cy) < 1.0


def test_same_seed_is_deterministic():
    a = _run(preset("NOISY"), 4.0)
    b = _run(preset("NOISY"), 4.0)
    for k in ("acquisition_time_s", "mean_tracking_error_px", "centroid_rmse_px", "target_loss_pct"):
        assert a[k] == b[k]


@pytest.mark.parametrize("name", ["SIH-OFFICIAL", "NOISY", "SEVERE"])
def test_presets_meet_official_specs(name):
    s = _run(preset(name), 12.0)
    assert s["all_pass"], s["pass"]


def test_occlusion_is_reacquired_within_one_second():
    sc = preset("SIH-OFFICIAL")
    sc.target.occlusions = [[5.0, 0.6]]
    s = _run(sc, 9.0)
    assert s["reacquisitions"] >= 1
    assert s["max_reacquisition_s"] <= 1.0


def test_mp4_benchmark_roundtrip(tmp_path):
    sc = preset("NOISY")
    video = tmp_path / "clip.mp4"
    gt = make_test_video(str(video), sc, seconds=3.0, size=1200)
    vb = VideoBenchmark(str(video), gt)
    s = vb.run()
    assert s["acquisition_time_s"] <= 2.0
    assert s["centroid_rmse_px"] < 1.5
    assert s["lock_retention_pct"] > 90


def test_scenario_yaml_roundtrip(tmp_path):
    sc = preset("FOG-JITTER")
    p = tmp_path / "s.yaml"
    sc.save(p)
    back = Scenario.load(p)
    assert back.hash() == sc.hash()
