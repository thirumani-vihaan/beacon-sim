"""Scenario configuration. Defaults reproduce the official SIH26169 parameter table (preset SIH-OFFICIAL)."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml


@dataclass
class CameraCfg:
    screen_w: int = 2000          # official row 1: screen size min 2000 x 2000
    screen_h: int = 2000
    res_w: int = 640              # row 3: 640 x 480
    res_h: int = 480
    fov_x_deg: float = 4.0        # row 4: default 4 x 3 deg
    fov_y_deg: float = 3.0
    rate_hz: float = 30.0         # row 5: >= 30 Hz
    max_pan_dps: float = 5.0      # rows 13-14: default 5 deg/s
    max_tilt_dps: float = 5.0
    control_hz: float = 30.0      # row 15: >= 20 Hz (pan-tilt command rate, independent of the frame rate)
    colour: bool = False          # row 2: monochrome FPA (default) | optional colour
    wide_field: bool = True       # acquisition aid: low-res whole-screen sensor cues the narrow camera

    @property
    def px_per_deg(self) -> float:
        return self.res_w / self.fov_x_deg

    @property
    def px_per_deg_y(self) -> float:
        return self.res_h / self.fov_y_deg

    @property
    def urad_per_px(self) -> float:
        return math.radians(self.fov_x_deg / self.res_w) * 1e6


@dataclass
class TargetCfg:
    size: int = 10                # row 10: 5-20 px, default 10
    shape: str = "square"         # row 9: square (default) | circle | diamond | gaussian
    motion: str = "figure8"       # row 12: line | circle | figure8 | random | spiral | sine | waypoints
    speed: float = 120.0          # px/s on the screen
    start: str = "random"         # row 11: random (default) | centre | xy  (xy uses start_xy)
    start_xy: list = field(default_factory=lambda: [1300.0, 800.0])
    waypoints: list = field(default_factory=lambda: [[700, 700], [1300, 700], [1300, 1300], [700, 1300]])  # user-defined path
    brightness: float = 230.0
    count: int = 1                # row 8: 1 mandatory; >1 adds dimmer decoy spots (multiple targets, optional)
    decoy_brightness: float = 0.55  # decoy intensity relative to the beacon
    occlusions: list = field(default_factory=lambda: [[18.0, 0.6]])  # [t_start, duration]: beacon off, tests re-acquisition


@dataclass
class DisturbCfg:
    salt_pepper: float = 0.0      # row 21.1: fraction of pixels (~0.10 official)
    gaussian_sigma: float = 0.0   # row 21.2: max 20
    poisson: bool = False
    jitter_px: float = 0.0        # row 21.3: max +/-20 px/frame
    weather: str = "clear"        # row 21.4: clear | haze | fog | rain | lowlight
    contrast: float = 1.0         # row 21.4: user-defined contrast factor (applied on top of the weather preset)
    brightness: float = 0.0       # row 21.4: user-defined brightness offset (grey levels, negative = darker)
    platform: str = "none"        # row 21.5: none | linear | circular | random | spiral | figure8
    platform_px: float = 0.0      # max +/-20 px/frame
    turbulence_cn2: float = 0.0   # advanced physics layer (m^-2/3); 0 = off
    path_km: float = 2.0


@dataclass
class Scenario:
    name: str = "SIH-OFFICIAL"
    seed: int = 42
    duration_s: float = 40.0
    imu_aid: bool = True  # gyro/IMU feed-forward of platform motion + LOS jitter (residual 2 % / 15 %)
    ai_verifier: bool = True  # CNN verifier re-ranks detector candidates (beacon vs clutter); see beacon_sim/ai.py
    camera: CameraCfg = field(default_factory=CameraCfg)
    target: TargetCfg = field(default_factory=TargetCfg)
    disturb: DisturbCfg = field(default_factory=DisturbCfg)

    def to_dict(self) -> dict:
        return asdict(self)

    def validate(self) -> list[str]:
        """Clamp every parameter into a range the simulator supports; returns human-readable warnings."""
        w: list[str] = []

        def clamp(obj, name, lo, hi):
            v = getattr(obj, name)
            nv = type(v)(min(max(v, lo), hi))
            if nv != v:
                w.append(f"{name}={v} clamped to {nv} (allowed {lo}..{hi})")
                setattr(obj, name, nv)

        c, t, d = self.camera, self.target, self.disturb
        clamp(c, "screen_w", 800, 8000), clamp(c, "screen_h", 800, 8000)
        clamp(c, "res_w", 160, 2048), clamp(c, "res_h", 120, 2048)
        clamp(c, "fov_x_deg", 0.5, 60.0), clamp(c, "fov_y_deg", 0.5, 60.0)
        clamp(c, "rate_hz", 10.0, 240.0), clamp(c, "control_hz", 5.0, 1000.0)
        clamp(c, "max_pan_dps", 0.5, 60.0), clamp(c, "max_tilt_dps", 0.5, 60.0)
        clamp(t, "size", 2, 60), clamp(t, "speed", 0.0, 2000.0), clamp(t, "brightness", 20.0, 255.0)
        clamp(d, "salt_pepper", 0.0, 0.5), clamp(d, "gaussian_sigma", 0.0, 60.0)
        clamp(d, "jitter_px", 0.0, 60.0), clamp(d, "platform_px", 0.0, 60.0)
        clamp(d, "contrast", 0.05, 2.0), clamp(d, "brightness", -150.0, 150.0)
        clamp(t, "count", 1, 8), clamp(t, "decoy_brightness", 0.1, 1.0)
        for name, allowed in (("shape", SHAPES), ("motion", MOTIONS), ("start", STARTS)):
            if getattr(t, name) not in allowed:
                w.append(f"{name}={getattr(t, name)!r} unknown -> {allowed[0]}")
                setattr(t, name, allowed[0])
        if d.weather not in WEATHERS:
            w.append(f"weather={d.weather!r} unknown -> clear"); d.weather = "clear"
        if d.platform not in PLATFORMS:
            w.append(f"platform={d.platform!r} unknown -> none"); d.platform = "none"
        if len(t.waypoints) < 2:
            w.append("waypoints need at least 2 points -> default square path")
            t.waypoints = TargetCfg().waypoints
        return w

    def hash(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()[:12]

    @classmethod
    def from_dict(cls, d: dict) -> "Scenario":
        s = cls()
        for k, v in d.items():
            if k in ("camera", "target", "disturb"):
                sub = getattr(s, k)
                for kk, vv in v.items():
                    setattr(sub, kk, vv)
            else:
                setattr(s, k, v)
        return s

    @classmethod
    def load(cls, path: str | Path) -> "Scenario":
        return cls.from_dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})

    def save(self, path: str | Path) -> None:
        Path(path).write_text(yaml.safe_dump(self.to_dict(), sort_keys=False), encoding="utf-8")


# Official performance specifications (rows 16-20): metric -> (operator, limit)
SPECS = {
    "acquisition_time_s": ("<=", 2.0),
    "mean_tracking_error_px": ("<=", 10.0),
    "target_loss_pct": ("<", 5.0),
    "max_reacquisition_s": ("<=", 1.0),
    "processing_fps": (">=", 20.0),
}

SHAPES = ["square", "circle", "diamond", "gaussian"]
MOTIONS = ["line", "circle", "figure8", "random", "spiral", "sine", "waypoints"]
STARTS = ["random", "centre", "xy"]
WEATHERS = ["clear", "haze", "fog", "rain", "lowlight"]
PLATFORMS = ["none", "linear", "circular", "random", "spiral", "figure8"]

PRESETS = ["SIH-OFFICIAL", "NOISY", "FOG-JITTER", "RAIN-LOWLIGHT", "SIH-MAX", "SEVERE"]


def preset(name: str) -> Scenario:
    s = Scenario(name=name)
    d, t = s.disturb, s.target
    if name == "SIH-OFFICIAL":
        pass
    elif name == "NOISY":
        d.salt_pepper, d.gaussian_sigma, d.poisson, d.jitter_px = 0.10, 20.0, True, 6.0
    elif name == "FOG-JITTER":
        d.weather, d.jitter_px, d.gaussian_sigma, d.platform, d.platform_px = "fog", 12.0, 10.0, "linear", 4.0
        t.motion = "circle"
    elif name == "RAIN-LOWLIGHT":
        d.weather, d.gaussian_sigma, d.salt_pepper = "rain", 12.0, 0.03
        t.motion = "random"
    elif name == "SIH-MAX":  # every official disturbance at its maximum at once (rows 21.1-21.5)
        d.salt_pepper, d.gaussian_sigma, d.poisson, d.jitter_px = 0.10, 20.0, True, 20.0
        d.platform, d.platform_px = "linear", 20.0
        t.motion = "random"
        s.camera.max_pan_dps = s.camera.max_tilt_dps = 10.0  # rows 13-14 upper limit: 5 deg/s cannot outrun 600 px/s platform motion
    elif name == "SEVERE":  # beyond the official spec: SIH maxima + haze + circular platform + turbulence
        d.salt_pepper, d.gaussian_sigma, d.poisson, d.jitter_px = 0.10, 20.0, True, 20.0
        d.weather, d.platform, d.platform_px, d.turbulence_cn2 = "haze", "circular", 8.0, 1e-14
        t.motion = "random"
    else:
        raise ValueError(f"unknown preset {name}")
    return copy.deepcopy(s)
