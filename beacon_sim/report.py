"""Self-contained HTML performance report (inline SVG charts, no external assets) for every run."""
from __future__ import annotations

import html
import math

import numpy as np

from .config import SPECS

STATE_HEX = {"SEARCH": "#8c8c96", "ACQUIRE": "#e6b43c", "LOCK": "#5fd07a", "COAST": "#eb8c46", "REACQUIRE": "#e6503c"}
SPEC_TEXT = {"acquisition_time_s": ("Acquisition time", "s", "row 16"), "mean_tracking_error_px": ("Mean tracking error", "px", "row 17"),
             "target_loss_pct": ("Target loss", "%", "row 18"), "max_reacquisition_s": ("Re-acquisition (max)", "s", "row 19"),
             "processing_fps": ("Processing speed", "FPS", "row 20")}

CSS = """
*{box-sizing:border-box} body{margin:0;background:#fff;color:#111;font:15px/1.45 'Segoe UI',system-ui,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 26px 60px}
h1{font:900 42px/1 'Arial Black','Segoe UI',sans-serif;margin:0;letter-spacing:-1px}
h2{font:800 22px/1.2 'Segoe UI',sans-serif;margin:34px 0 12px;display:inline-block;background:#ffe45c;border:3px solid #111;padding:4px 14px;box-shadow:5px 5px 0 #111}
.sub{margin:10px 0 0;font-weight:600;color:#333}
.box{border:3px solid #111;box-shadow:7px 7px 0 #111;background:#fff;padding:16px 18px;margin:14px 0}
.banner{padding:18px 22px;font:900 26px/1.1 'Arial Black',sans-serif;border:4px solid #111;box-shadow:8px 8px 0 #111;margin:22px 0}
.ok{background:#7ade8c}.bad{background:#ff8fab}.na{background:#e5e5e5}.warn{background:#ffd08a}
.grid{display:grid;grid-template-columns:repeat(5,1fr);gap:16px}
.card{border:3px solid #111;box-shadow:5px 5px 0 #111;padding:12px 14px}
.card .t{font-weight:700;font-size:13px;text-transform:uppercase;letter-spacing:.4px}
.card .v{font:900 30px/1.1 'Arial Black',sans-serif;margin:8px 0 4px}
.card .s{font-size:12px;font-weight:600}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border:2px solid #111;padding:6px 10px;text-align:left} th{background:#111;color:#ffe45c}
tr:nth-child(even) td{background:#fafafa}
.chip{display:inline-block;border:2px solid #111;padding:1px 9px;font-weight:800;font-size:12px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:22px}
svg text{font:11px 'Segoe UI',sans-serif}
pre{background:#111;color:#e6e8ee;padding:14px;overflow:auto;border:3px solid #111;box-shadow:7px 7px 0 #ffe45c;font-size:12px}
.legend span{display:inline-block;margin-right:14px;font-weight:700;font-size:12px}
.legend i{display:inline-block;width:14px;height:14px;border:2px solid #111;vertical-align:-2px;margin-right:5px}
.foot{margin-top:40px;font-size:12px;color:#555}
"""


def _fmt(v, unit=""):
    if v is None or (isinstance(v, float) and v != v):
        return "–"
    return f"{v:g} {unit}".strip() if isinstance(v, (int, float)) else html.escape(str(v))


def _line_chart(xs, series, w=540, h=220, ymax=None, limit=None, ylabel="", xlabel="time (s)") -> str:
    """series: list of (values, colour, label). NaNs break the line."""
    pad_l, pad_r, pad_t, pad_b = 44, 12, 12, 30
    xs = np.asarray(xs, float)
    if xs.size < 2:
        return "<p>not enough data</p>"
    x0, x1 = float(xs[0]), float(xs[-1]) or 1.0
    allv = np.concatenate([np.asarray(s[0], float) for s in series])
    allv = allv[np.isfinite(allv)]
    top = ymax or (float(np.percentile(allv, 99)) * 1.15 if allv.size else 1.0)
    if limit:
        top = max(top, limit * 1.6)
    top = top or 1.0
    X = lambda x: pad_l + (x - x0) / max(x1 - x0, 1e-9) * (w - pad_l - pad_r)  # noqa: E731
    Y = lambda y: pad_t + (1 - min(y, top) / top) * (h - pad_t - pad_b)  # noqa: E731
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="border:3px solid #111;box-shadow:6px 6px 0 #111;background:#fff">']
    for k in range(5):
        yv = top * k / 4
        out.append(f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{Y(yv):.1f}" y2="{Y(yv):.1f}" stroke="#eee"/>'
                   f'<text x="{pad_l - 6}" y="{Y(yv) + 4:.1f}" text-anchor="end">{yv:.3g}</text>')
    for k in range(6):
        xv = x0 + (x1 - x0) * k / 5
        out.append(f'<text x="{X(xv):.1f}" y="{h - 10}" text-anchor="middle">{xv:.3g}</text>')
    if limit:
        out.append(f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{Y(limit):.1f}" y2="{Y(limit):.1f}" stroke="#e6503c" stroke-width="2" stroke-dasharray="7 5"/>'
                   f'<text x="{w - pad_r - 4}" y="{Y(limit) - 5:.1f}" text-anchor="end" fill="#e6503c" font-weight="700">limit {limit:g}</text>')
    for vals, col, _ in series:
        vals = np.asarray(vals, float)
        step = max(1, len(xs) // 1500)
        segs, cur = [], []
        for x, y in zip(xs[::step], vals[::step]):
            if np.isfinite(y):
                cur.append(f"{X(x):.1f},{Y(y):.1f}")
            elif cur:
                segs.append(cur)
                cur = []
        if cur:
            segs.append(cur)
        for sg in segs:
            out.append(f'<polyline fill="none" stroke="{col}" stroke-width="2" points="{" ".join(sg)}"/>')
    out.append(f'<line x1="{pad_l}" x2="{pad_l}" y1="{pad_t}" y2="{h - pad_b}" stroke="#111" stroke-width="2"/>'
               f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{h - pad_b}" y2="{h - pad_b}" stroke="#111" stroke-width="2"/>'
               f'<text x="{pad_l + 8}" y="{pad_t + 12}" font-weight="700" fill="#555">{html.escape(ylabel)}</text>'
               f'<text x="{w - pad_r}" y="{h - 1}" text-anchor="end">{xlabel}</text></svg>')
    return "".join(out)


def _state_strip(rows, w=1100, h=34) -> str:
    n = len(rows)
    if not n:
        return ""
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="border:3px solid #111;box-shadow:6px 6px 0 #111">']
    start, cur = 0, rows[0]["state"]
    for i in range(1, n + 1):
        st = rows[i]["state"] if i < n else None
        if st != cur:
            out.append(f'<rect x="{start / n * w:.2f}" y="0" width="{(i - start) / n * w + 0.5:.2f}" height="{h}" fill="{STATE_HEX.get(cur, "#ccc")}"/>')
            start, cur = i, st
    out.append("</svg>")
    return "".join(out)


def _trajectory(rows, sw, sh, size=420) -> str:
    s = size / max(sw, sh)
    pts_t = [(r["true_x"], r["true_y"]) for r in rows if r["true_x"] == r["true_x"]]
    pts_b = [(r["bore_x"], r["bore_y"]) for r in rows]
    step = max(1, len(rows) // 1200)

    def poly(pts, col, wd):
        return f'<polyline fill="none" stroke="{col}" stroke-width="{wd}" points="{" ".join(f"{x * s:.1f},{y * s:.1f}" for x, y in pts[::step])}"/>'
    return (f'<svg viewBox="0 0 {sw * s:.0f} {sh * s:.0f}" width="{size}" style="border:3px solid #111;box-shadow:6px 6px 0 #111;background:#1b1f26">'
            + poly(pts_t, "#ff8fab", 3) + poly(pts_b, "#ffe45c", 1.5)
            + f'<circle cx="{sw * s / 2:.1f}" cy="{sh * s / 2:.1f}" r="4" fill="#7ade8c" stroke="#111"/></svg>')


def make_html(rows: list[dict], s: dict, meta: dict, scenario: dict | None = None) -> str:
    t = np.array([r["t"] for r in rows], float)
    te = np.array([r["tracking_err_px"] if r["visible"] else np.nan for r in rows], float)
    ce = np.array([r["centroid_err_px"] if r["centroid_err_px"] is not None else np.nan for r in rows], float)
    pm = np.array([r["proc_ms"] for r in rows], float)
    verdict = s.get("all_pass")
    title = html.escape(str(meta.get("scenario")))
    cards = []
    for k, (name, unit, row) in SPEC_TEXT.items():
        ok = s.get("pass", {}).get(k)
        cls = "na" if ok is None else ("ok" if ok else "bad")
        op, lim = SPECS[k]
        cards.append(f'<div class="card {cls}"><div class="t">{name}</div><div class="v">{_fmt(s.get(k), unit)}</div>'
                     f'<div class="s">spec {html.escape(op)} {lim:g} {unit} · {row} · {"N/A" if ok is None else ("PASS" if ok else "FAIL")}</div></div>')
    table = "".join(f"<tr><td>{html.escape(k)}</td><td>{_fmt(v)}</td></tr>" for k, v in s.items() if k not in ("pass", "all_pass") and not isinstance(v, dict))
    fz = meta.get("feasibility")
    feas = ""
    if fz:
        cls = "ok" if fz["acquisition_guaranteed"] else "warn"
        notes = "".join(f"<li>{html.escape(n)}</li>" for n in fz["notes"]) or "<li>every official spec is physically achievable for this scenario</li>"
        feas = (f'<h2>Physical feasibility</h2><div class="box {cls}"><b>Slew budget {fz["slew_px_s"]} px/s · required {fz["required_px_s"]} px/s · '
                f'spare {fz["spare_px_s"]} px/s · worst-case acquisition {fz["worst_case_acquisition_s"]} s</b><ul>{notes}</ul></div>')
    cfg = ""
    if scenario:
        import yaml
        cfg = f"<h2>Scenario configuration</h2><pre>{html.escape(yaml.safe_dump(scenario, sort_keys=False))}</pre>"
    legend = "".join(f'<span><i style="background:{c}"></i>{n}</span>' for n, c in STATE_HEX.items())
    sw = (scenario or {}).get("camera", {}).get("screen_w") or (meta.get("video") or {}).get("width") or 2000
    sh = (scenario or {}).get("camera", {}).get("screen_h") or (meta.get("video") or {}).get("height") or 2000
    has_truth = np.isfinite(te).any()
    acq = s.get("acquisition_time_s")
    settled = te[(t >= (acq if acq == acq and acq is not None else 0) + 0.5) & np.isfinite(te)]
    te_top = max(30.0, float(np.percentile(settled, 99)) * 1.3) if settled.size else None
    hist_counts, edges = np.histogram(pm, bins=24, range=(0, max(float(np.percentile(pm, 99.5)), 1e-3)))
    hist = _line_chart(edges[:-1], [(hist_counts, "#7c5cff", "frames")], ylabel="frames", xlabel="processing time per frame (ms)")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>BEACON-SIM report · {title}</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>BEACON-SIM performance report</h1>
<p class="sub">{title} · seed {html.escape(str(meta.get("seed")))} · config {html.escape(str(meta.get("config_hash")))} · {html.escape(str(meta.get("mode", "closed-loop simulation")))} ·
{s.get("frames")} frames · {s.get("simulation_duration_s")} s</p>
<div class="banner {"ok" if verdict else "bad"}">{"✓ ALL OFFICIAL SPECS MET" if verdict else "✗ SOME SPECS NOT MET"}</div>
<div class="grid">{"".join(cards)}</div>
<h2>Tracking error</h2>
<div class="two"><div>{_line_chart(t, [(te, "#111", "tracking")], ymax=te_top, limit=10, ylabel="boresight - beacon (px), clipped") if has_truth else "<div class='box na'>No ground truth: tracking error not measurable.</div>"}</div>
<div>{_line_chart(t, [(ce, "#e6503c", "centroid")], ylabel="centroid error (px)") if np.isfinite(ce).any() else "<div class='box na'>No ground truth: centroid error not measurable.</div>"}</div></div>
<h2>Lock state timeline</h2>{_state_strip(rows)}<p class="legend">{legend}</p>
<h2>Trajectory &amp; processing</h2>
<div class="two"><div>{_trajectory(rows, sw, sh) if has_truth else ""}<p class="legend"><span><i style="background:#ff8fab"></i>beacon (truth)</span><span><i style="background:#ffe45c"></i>camera boresight</span></p></div>
<div>{hist}<p class="sub">mean {pm.mean():.2f} ms · p95 {np.percentile(pm, 95):.2f} ms · {1000 / max(pm.mean(), 1e-6):.0f} FPS</p></div></div>
{feas}
<h2>All metrics</h2><table><tr><th>Metric</th><th>Value</th></tr>{table}</table>
{cfg}
<p class="foot">Generated automatically by BEACON-SIM · per-frame data in the matching <code>*_frames.csv</code> · SIH26169 (ISRO)</p>
</div></body></html>"""
