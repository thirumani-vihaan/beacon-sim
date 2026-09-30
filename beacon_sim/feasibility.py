"""Physical feasibility check: can ANY pan-tilt controller meet the official specs for this scenario?

The mount's slew budget (rows 13-14) must cover platform motion (row 21.5) plus target motion, and closing the
initial pointing offset needs the spare slew. When a scenario asks for more than the mount can physically do,
the performance report says so instead of silently blaming the tracker.
"""
from __future__ import annotations

from .config import Scenario

MAX_START_OFFSET_PX = 600.0  # random start radius used by the scene (250-600 px from the boresight)


def analyse(sc: Scenario) -> dict:
    c, t, d = sc.camera, sc.target, sc.disturb
    slew_px = min(c.max_pan_dps * c.px_per_deg, c.max_tilt_dps * c.px_per_deg_y)
    plat_px = d.platform_px * c.rate_hz if d.platform != "none" else 0.0
    need_px = plat_px + t.speed
    spare = slew_px - need_px
    offset = 0.0 if t.start == "centre" else MAX_START_OFFSET_PX
    worst_acq = offset / spare if spare > 0 else float("inf")
    notes = []
    if spare <= 0:
        notes.append(f"platform ({plat_px:.0f} px/s) + target ({t.speed:.0f} px/s) exceed the {slew_px:.0f} px/s slew limit: "
                     f"needs >= {need_px / c.px_per_deg:.1f} deg/s")
    elif worst_acq > 2.0:
        notes.append(f"worst-case start geometry needs {worst_acq:.1f} s to close {offset:.0f} px with {spare:.0f} px/s spare slew "
                     f"(acquisition <= 2 s is guaranteed only above {(need_px + offset / 2.0) / c.px_per_deg:.1f} deg/s)")
    return {
        "slew_px_s": round(slew_px, 1),
        "required_px_s": round(need_px, 1),
        "spare_px_s": round(spare, 1),
        "worst_case_acquisition_s": round(worst_acq, 2) if worst_acq != float("inf") else None,
        "tracking_feasible": spare > 0,
        "acquisition_guaranteed": spare > 0 and worst_acq <= 2.0,
        "notes": notes,
    }
