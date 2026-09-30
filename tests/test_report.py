from beacon_sim.config import preset
from beacon_sim.sim import run_headless

def test_every_run_writes_a_self_contained_html_report(tmp_path):
    sc = preset("NOISY")
    sc.duration_s = 4.0
    run_headless(sc, str(tmp_path), "r")
    html = (tmp_path / "r_report.html").read_text(encoding="utf-8")
    assert "<svg" in html and "ALL OFFICIAL SPECS MET" in html and "http" not in html.split("<body>")[1][:2000]
    for f in ("r_frames.csv", "r_summary.json", "r_summary.md"):
        assert (tmp_path / f).exists()
