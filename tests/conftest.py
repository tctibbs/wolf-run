import os

import pytest

# Qt tests draw offscreen, so they run anywhere (including CI) with no display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FakeCanvas:
    """Records every pixel that gets filled, so drawing can be checked without Qt."""

    def __init__(self) -> None:
        self.pixels: dict[tuple[int, int], str] = {}
        self.calls = 0

    def fill(self, x: int, y: int, w: int, h: int, color: str) -> None:
        self.calls += 1
        for dy in range(h):
            for dx in range(w):
                self.pixels[(x + dx, y + dy)] = color

    def at(self, x: int, y: int) -> str | None:
        return self.pixels.get((x, y))


@pytest.fixture
def canvas() -> FakeCanvas:
    return FakeCanvas()
