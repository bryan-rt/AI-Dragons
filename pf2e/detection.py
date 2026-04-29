"""pf2e/detection.py — Detection and Visibility System (CP10.7)

Three-layer system:
  Layer 1: Lighting — LightLevel + LightSource + compute_light_level()
  Layer 2: Vision   — VisionType + perceived_light_level()
  Layer 3: Detection — DetectionState + compute_detection_state()

Light level is measured at the DEFENDER's position, perceived through
the ATTACKER's vision type.
(AoN: https://2e.aonprd.com/Rules.aspx?ID=2016 — Vision)
(AoN: https://2e.aonprd.com/Rules.aspx?ID=2347 — Light)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LightLevel(Enum):
    BRIGHT = "bright"
    DIM = "dim"
    DARK = "dark"


class VisionType(Enum):
    NORMAL = "normal"
    LOW_LIGHT = "low_light"
    DARKVISION = "darkvision"


class DetectionState(Enum):
    OBSERVED = "observed"
    CONCEALED = "concealed"
    HIDDEN = "hidden"
    UNDETECTED = "undetected"
    UNNOTICED = "unnoticed"


@dataclass(frozen=True)
class LightSource:
    """A dynamic light source (campfire, torch, Dancing Lights).

    Common sources (AoN verified):
      Campfire/Torch: bright_radius_ft=20, dim_radius_ft=40
      Dancing Lights: bright_radius_ft=0, dim_radius_ft=20
    (AoN: https://2e.aonprd.com/Equipment.aspx?ID=14)
    """
    position: tuple[int, int]
    bright_radius_ft: int
    dim_radius_ft: int
    name: str = ""


def _grid_distance_ft(a: tuple[int, int], b: tuple[int, int]) -> int:
    """PF2e grid distance. Duplicated to avoid import coupling."""
    dr = abs(a[0] - b[0])
    dc = abs(a[1] - b[1])
    diag = min(dr, dc)
    straight = abs(dr - dc)
    return (diag // 2) * 10 + ((diag + 1) // 2) * 5 + straight * 5


def compute_light_level(
    pos: tuple[int, int],
    light_sources: tuple[LightSource, ...],
    ambient: LightLevel,
) -> LightLevel:
    """Highest light level at pos from any source or ambient.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2347)
    """
    best = ambient
    for src in light_sources:
        d = _grid_distance_ft(pos, src.position)
        if src.bright_radius_ft > 0 and d <= src.bright_radius_ft:
            return LightLevel.BRIGHT
        if d <= src.dim_radius_ft and best == LightLevel.DARK:
            best = LightLevel.DIM
    return best


def perceived_light_level(
    actual: LightLevel, vision: VisionType,
) -> LightLevel:
    """What a creature with this vision perceives at actual light level.
    Low-light: dim -> bright. Darkvision: dim -> bright, dark -> dim.
    (AoN: https://2e.aonprd.com/Rules.aspx?ID=2016)
    """
    if actual == LightLevel.BRIGHT:
        return LightLevel.BRIGHT
    if actual == LightLevel.DIM:
        if vision in (VisionType.LOW_LIGHT, VisionType.DARKVISION):
            return LightLevel.BRIGHT
        return LightLevel.DIM
    # DARK
    if vision == VisionType.DARKVISION:
        return LightLevel.DIM
    return LightLevel.DARK


def compute_detection_state(
    attacker_pos: tuple[int, int],
    defender_pos: tuple[int, int],
    attacker_vision: VisionType,
    light_sources: tuple[LightSource, ...],
    ambient: LightLevel,
    defender_hidden: bool = False,
) -> DetectionState:
    """Detection state of defender from attacker's perspective.

    Light measured at DEFENDER's position, filtered by attacker's vision.
    (AoN: https://2e.aonprd.com/Conditions.aspx?ID=45)
    (AoN: https://2e.aonprd.com/Conditions.aspx?ID=19)
    """
    if defender_hidden:
        return DetectionState.HIDDEN

    raw = compute_light_level(defender_pos, light_sources, ambient)
    perceived = perceived_light_level(raw, attacker_vision)

    if perceived == LightLevel.BRIGHT:
        return DetectionState.OBSERVED
    if perceived == LightLevel.DIM:
        return DetectionState.CONCEALED
    return DetectionState.UNDETECTED
