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
    control_hz: float = 30.0      # row 15: >= 20 Hz

    @property
    def px_per_deg(self) -> float:
        return self.res_w / self.fov_x_deg

    @property
    def urad_per_px(self) -> float:
        return math.radians(self.fov_x_deg / self.res_w) * 1e6


@dataclass
class TargetCfg:
    size: int = 10                # row 10: 5-20 px, default 10 (square, row 9)
    motion: str = "figure8"       # row 12: line | circle | figure8 | random | spiral | sine
    speed: float = 120.0          # px/s on the screen
    brightness: float = 230.0
    occlusions: list = field(default_factory=lambda: [[18.0, 0.6]])  # [t_start, duration]: beacon off, tests re-acquisition


@dataclass
class DisturbCfg:
    salt_pepper: float = 0.0      # row 21.1: fraction of pixels (~0.10 official)
    gaussian_sigma: float = 0.0   # row 21.2: max 20
    poisson: bool = False
    jitter_px: float = 0.0        # row 21.3: max +/-20 px/frame
    weather: str = "clear"        # row 21.4: clear | haze | fog | rain | lowlight
    platform: str = "none"        # row 21.5: none | linear | circular | random | figure8
    platform_px: float = 0.0      # max +/-20 px/frame
    turbulence_cn2: float = 0.0   # advanced physics layer (m^-2/3); 0 = off
    path_km: float = 2.0


@dataclass
class Scenario:
    name: str = "SIH-OFFICIAL"
    seed: int = 42
    duration_s: float = 40.0
    imu_aid: bool = True  # gyro/IMU feed-forward of platform motion + LOS jitter (residual 2 % / 15 %)
    camera: CameraCfg = field(default_factory=CameraCfg)
    target: TargetCfg = field(default_factory=TargetCfg)
    disturb: DisturbCfg = field(default_factory=DisturbCfg)

    def to_dict(self) -> dict:
        return asdict(self)

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

PRESETS = ["SIH-OFFICIAL", "NOISY", "FOG-JITTER", "RAIN-LOWLIGHT", "SEVERE"]


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
    elif name == "SEVERE":
        d.salt_pepper, d.gaussian_sigma, d.poisson, d.jitter_px = 0.10, 20.0, True, 20.0
        d.weather, d.platform, d.platform_px, d.turbulence_cn2 = "haze", "circular", 8.0, 1e-14
        t.motion = "random"
    else:
        raise ValueError(f"unknown preset {name}")
    return copy.deepcopy(s)
