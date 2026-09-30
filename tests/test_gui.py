"""Offscreen GUI smoke tests: the scenario editor, live parameters, restart parameters and MP4 mode."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from beacon_sim.app import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _run(w, n):
    if not w.timer.isActive():
        w.toggle()
    w.timer.setInterval(10 ** 8)
    for _ in range(n):
        w.tick()


def test_editor_exposes_every_official_parameter(app):
    w = MainWindow()
    for k in ["camera.screen_w", "camera.res_w", "camera.fov_x_deg", "camera.rate_hz", "camera.control_hz",
              "camera.max_pan_dps", "camera.max_tilt_dps", "camera.colour", "target.shape", "target.size",
              "target.start", "target.motion", "target.count", "disturb.salt_pepper", "disturb.gaussian_sigma",
              "disturb.poisson", "disturb.jitter_px", "disturb.weather", "disturb.contrast", "disturb.brightness",
              "disturb.platform", "disturb.platform_px"]:
        assert k in w.widgets, k


def test_live_and_restart_parameters(app):
    w = MainWindow()
    w.widgets["disturb.gaussian_sigma"].setValue(20)       # live
    assert w.sim.sc.disturb.gaussian_sigma == 20
    w.widgets["camera.res_w"].setValue(800)                # needs restart
    assert w.sim.sc.camera.res_w == 640
    w.apply_restart()
    assert w.sim.sc.camera.res_w == 800
    _run(w, 45)
    assert w.sim.log.summary()["acquisition_time_s"] <= 2.0


def test_mp4_mode_runs_in_the_gui(app, tmp_path):
    from beacon_sim.config import preset
    from beacon_sim.video_bench import make_test_video
    video = tmp_path / "g.mp4"
    make_test_video(str(video), preset("NOISY"), seconds=1.0, size=1000)
    w = MainWindow()
    w.load_mp4(str(video))
    w.timer.setInterval(10 ** 8)
    for _ in range(20):
        w.tick()
    assert w.bench.log.rows
