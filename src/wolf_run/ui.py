"""The only module that knows about Qt: a window that shows the current stage.

Scenes draw onto a 256x150 image; the window scales it up with no smoothing, so
the pixels stay square. On the Pi it runs full screen straight onto the
framebuffer; on a Mac it runs in a 1024x600 window.
"""

import os
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QRect, Qt, QTimer
from PyQt5.QtGui import QColor, QImage, QKeyEvent, QPainter, QPaintEvent
from PyQt5.QtWidgets import QApplication, QWidget

from wolf_run import clock
from wolf_run.pixels import Canvas

PANEL_W, PANEL_H = 1024, 600
FPS = 15

Scene = Callable[[Canvas, datetime, float], None]


class ImageCanvas:
    """A Canvas that paints into a QImage."""

    def __init__(self, image: QImage) -> None:
        self._painter = QPainter(image)
        self._colors: dict[str, QColor] = {}

    def fill(self, x: int, y: int, w: int, h: int, color: str) -> None:
        qcolor = self._colors.get(color)
        if qcolor is None:
            qcolor = self._colors[color] = QColor(color)
        self._painter.fillRect(x, y, w, h, qcolor)

    def finish(self) -> None:
        self._painter.end()


def render(scene: Scene, now: datetime, t: float) -> QImage:
    """Draw one frame of a scene at the screen's logical size."""
    image = QImage(clock.W, clock.H, QImage.Format_RGB32)
    canvas = ImageCanvas(image)
    try:
        scene(canvas, now, t)
    finally:
        canvas.finish()
    return image


def save_snapshot(
    path: Path, now: datetime, t: float, scene: Scene = clock.draw_clock
) -> Path:
    """Save one frame at the panel's real size, for checking a look without a Pi."""
    ensure_app(offscreen=True)
    image = render(scene, now, t).scaled(
        PANEL_W, PANEL_H, Qt.IgnoreAspectRatio, Qt.FastTransformation
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(path)):
        raise OSError(f"Couldn't save a screenshot to {path}.")
    return path


def fit(outer: QRect, w: int = clock.W, h: int = clock.H) -> QRect:
    """The biggest whole-number scale of a w x h picture that fits, centred."""
    scale = max(1, min(outer.width() // w, outer.height() // h))
    sw, sh = w * scale, h * scale
    return QRect(
        outer.x() + (outer.width() - sw) // 2,
        outer.y() + (outer.height() - sh) // 2,
        sw,
        sh,
    )


class ScreenWindow(QWidget):
    """Shows a scene, redrawn a few times a second."""

    def __init__(
        self,
        scene: Scene = clock.draw_clock,
        now: Callable[[], datetime] = datetime.now,
        seconds: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Wolf Run")
        self._scene, self._now, self._seconds = scene, now, seconds
        self._start = seconds()
        self._image = render(scene, now(), 0.0)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._timer.start(1000 // FPS)

    def tick(self) -> None:
        t = self._seconds() - self._start
        self._image = render(self._scene, self._now(), t)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt's name
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        painter.drawImage(fit(self.rect()), self._image)
        painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt's name
        if event.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.close()


def ensure_app(offscreen: bool = False) -> QApplication:
    """Reuse the running QApplication, or start one."""
    app = QApplication.instance()
    if app is None:
        if offscreen:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication([])
    return app


def run(windowed: bool) -> int:  # pragma: no cover - needs a real display
    """Show the screen until someone presses Esc or Q."""
    app = ensure_app()
    window = ScreenWindow()
    if windowed:
        window.resize(PANEL_W, PANEL_H)
        window.show()
    else:
        window.setCursor(Qt.BlankCursor)
        window.showFullScreen()
    return app.exec_()
