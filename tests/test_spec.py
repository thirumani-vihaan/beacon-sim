"""Official parameter-table coverage (rows 1-21.5) and robustness tests."""
import numpy as np
import pytest

from beacon_sim.config import MOTIONS, PLATFORMS, SHAPES, WEATHERS, Scenario, preset
from beacon_sim.feasibility import analyse
from beacon_sim.scene import spot_patch
from beacon_sim.sim import Simulation


def _run(sc: Scenario, seconds: float) -> dict:
    sc.duration_s = seconds
    return Simulation(sc).run()


@pytest.mark.parametrize("shape", SHAPES)
def test_spot_shapes_render_without_centroid_bias(shape):
    s = 10
    cx, cy = 11.3, 12.7
    ix, iy, n = int(np.floor(cx - s / 2)) - 1, int(np.floor(cy - s / 2)) - 1, s + 3
    if shape == "gaussian":  # same centred support as the renderer
        ix, iy, n = ix - s // 2, iy - s // 2, 2 * s + 3
    p = spot_patch(shape, cx, cy, s, n, ix, iy)
    yy, xx = np.mgrid[iy:iy + n, ix:ix + n]
    assert abs((p * (xx + 0.5)).sum() / p.sum() - cx) < 0.05
    assert abs((p * (yy + 0.5)).sum() / p.sum() - cy) < 0.05


@pytest.mark.parametrize("size", [5, 20])
def test_target_size_limits_meet_specs(size):
    sc = preset("NOISY")
    sc.target.size = size
    s = _run(sc, 10.0)
    assert s["all_pass"], s["pass"]
    assert s["centroid_rmse_px"] < 0.5


def test_initial_positions_centre_and_user_xy():
    sc = preset("SIH-OFFICIAL")
    sc.target.start, sc.target.motion = "xy", "circle"
    sc.target.start_xy = [1500.0, 600.0]
    sim = Simulation(sc)
    sim.step()
    assert np.allclose(sim.target.pos, [1500, 600], atol=1e-6)
    sc = preset("SIH-OFFICIAL")
    sc.target.start, sc.target.motion = "centre", "line"
    sim = Simulation(sc)
    assert np.allclose(sim.target.pos, [1000, 1000])
    assert np.allclose(sim.mount, [1000, 1000])  # row 6: camera starts at the screen centre


def test_user_defined_waypoint_motion_follows_the_path():
    sc = preset("SIH-OFFICIAL")
    sc.target.motion, sc.target.speed = "waypoints", 100.0
    sc.target.waypoints = [[800, 800], [1200, 800]]
    sim = Simulation(sc)
    pts = [sim.step()["true_pos"].copy() for _ in range(90)]
    assert all(abs(p[1] - 800) < 1e-6 for p in pts)
    assert max(p[0] for p in pts) > 1050


def test_multiple_targets_lock_on_the_primary_beacon():
    sc = preset("NOISY")
    sc.target.count = 3
    s = _run(sc, 10.0)
    assert s["all_pass"] and s["centroid_rmse_px"] < 0.5


def test_colour_camera_option():
    sc = preset("NOISY")
    sc.camera.colour = True
    sim = Simulation(sc)
    L = sim.step()
    assert L["frame_colour"].shape == (480, 640, 3) and L["frame"].ndim == 2
    assert _run(sc, 8.0)["all_pass"]


@pytest.mark.parametrize("hz", [20.0, 100.0])
def test_control_rate_is_independent_of_frame_rate(hz):
    sc = preset("NOISY")
    sc.camera.control_hz = hz
    assert _run(sc, 8.0)["all_pass"]


def test_pan_and_tilt_limits_are_respected():
    sc = preset("SIH-OFFICIAL")
    sc.camera.max_pan_dps, sc.camera.max_tilt_dps = 5.0, 8.0
    sim = Simulation(sc)
    prev = sim.mount.copy()
    for _ in range(60):
        sim.step()
        v = np.abs(sim.mount - prev) / sim.dt
        assert v[0] <= 5.0 * 160 + 1e-6 and v[1] <= 8.0 * 160 + 1e-6
        prev = sim.mount.copy()


def test_user_contrast_and_brightness():
    sc = preset("SIH-OFFICIAL")
    base = Simulation(sc).step()["frame"].astype(float).mean()
    sc = preset("SIH-OFFICIAL")
    sc.disturb.contrast, sc.disturb.brightness = 0.5, 60.0
    dim = Simulation(sc).step()["frame"].astype(float).mean()
    assert dim > base + 30


def test_official_maxima_pass_at_max_slew():
    s = _run(preset("SIH-MAX"), 12.0)
    assert s["all_pass"], s["pass"]


def test_feasibility_flags_physically_impossible_scenarios():
    sc = preset("SIH-MAX")
    sc.camera.max_pan_dps = sc.camera.max_tilt_dps = 5.0
    sc.target.speed = 300.0
    f = analyse(sc)
    assert not f["tracking_feasible"] and f["notes"]
    assert analyse(preset("SIH-OFFICIAL"))["acquisition_guaranteed"]


def test_every_option_combination_runs_without_crashing():
    rng = np.random.default_rng(0)
    for i in range(12):
        sc = preset("SIH-OFFICIAL")
        sc.seed = i
        sc.target.shape = SHAPES[i % len(SHAPES)]
        sc.target.motion = MOTIONS[i % len(MOTIONS)]
        sc.target.size = int(rng.integers(5, 21))
        sc.target.count = int(rng.integers(1, 4))
        sc.disturb.weather = WEATHERS[i % len(WEATHERS)]
        sc.disturb.platform = PLATFORMS[i % len(PLATFORMS)]
        sc.disturb.platform_px = float(rng.uniform(0, 20))
        sc.disturb.jitter_px = float(rng.uniform(0, 20))
        sc.disturb.salt_pepper = float(rng.uniform(0, 0.1))
        sc.disturb.gaussian_sigma = float(rng.uniform(0, 20))
        sc.camera.colour = bool(i % 2)
        sim = Simulation(sc)
        for _ in range(20):
            sim.step()


def test_validation_clamps_out_of_range_values():
    sc = preset("SIH-OFFICIAL")
    sc.target.size, sc.disturb.salt_pepper, sc.target.motion = 500, 3.0, "teleport"
    w = sc.validate()
    assert sc.target.size == 60 and sc.disturb.salt_pepper == 0.5 and sc.target.motion == "line"
    assert len(w) == 3
