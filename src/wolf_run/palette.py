"""The screen's colours.

One grey ink on near-black, like the dinosaur game's night mode, plus a single
candle orange for things that glow. Set GLOW to the ink colour for pure greyscale.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    bg: str
    ink: str
    dim: str
    soft: str
    glow: str


NIGHT = Palette(
    bg="#151617",
    ink="#d2d2d2",
    dim="#8b8d92",
    soft="#3a3c40",
    glow="#f0a13c",
)
