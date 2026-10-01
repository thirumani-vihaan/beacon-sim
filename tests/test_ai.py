"""AI verifier: the ONNX model loads in OpenCV and separates beacons from noise."""
import numpy as np
import pytest

from beacon_sim.ai import MODEL_PATH, Verifier

pytestmark = pytest.mark.skipif(not MODEL_PATH.exists(), reason="verifier model not trained")


def test_verifier_scores_beacon_high_and_noise_low():
    v = Verifier()
    rng = np.random.default_rng(0)
    frame = np.clip(rng.normal(60, 12, (200, 200)), 0, 255).astype(np.uint8)
    frame[95:105, 95:105] = 200
    p = v.probs(frame, [(100.0, 100.0), (40.0, 40.0), (160.0, 60.0)], 10)
    assert p[0] > 0.9
    assert p[1] < 0.2 and p[2] < 0.2


def test_simulation_uses_the_verifier_by_default():
    from beacon_sim.config import preset
    from beacon_sim.sim import Simulation
    sim = Simulation(preset("SIH-OFFICIAL"))
    assert sim.det.verifier is not None
    sc = preset("SIH-OFFICIAL")
    sc.ai_verifier = False
    assert Simulation(sc).det.verifier is None
