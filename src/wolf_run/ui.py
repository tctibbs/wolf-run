"""The only module that knows about Qt: a window that shows the current stage.

Scenes draw onto a 256x150 image; the window scales it up with no smoothing, so
the pixels stay square. On the Pi it runs full screen straight onto the
framebuffer; on a Mac it runs in a 1024x600 window.

Input: any key, click, or tap is "the button". The host's keys need Ctrl (Cmd on
a Mac), so a guest mashing the keyboard can't trigger them:

    Ctrl+P  prime the screen       Ctrl+E  skip to the brick house
    Ctrl+R  back to the clock      Ctrl+Q  quit
"""

import os
import sys
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PyQt5.QtCore import QRect, Qt, QTimer
from PyQt5.QtGui import (
    QCloseEvent,
    QColor,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
)
from PyQt5.QtWidgets import QApplication, QWidget

from wolf_run import camera_scene, clock
from wolf_run.camera import CameraFeed
from wolf_run.pixels import Canvas
from wolf_run.stages import Screen, Stage

PANEL_W, PANEL_H = 1024, 600
FPS = 30

Scene = Callable[[Canvas, datetime, float], None]
FeedFactory = Callable[[], CameraFeed | None]


SpriteKey = tuple[tuple[str, ...], str, str, int]
_sprites: dict[SpriteKey, QImage] = {}


def sprite_image(grid: Sequence[str], ink: str, hole: str, scale: int) -> QImage:
    """A sprite drawn once into a transparent image, then reused every frame.

    Painting pixel by pixel costs a Pi 3 about 12 microseconds a pixel, which adds
    up to a dropped frame for a big house. Stamping a cached image is one call.
    """
    key = (tuple(grid), ink, hole, scale)
    image = _sprites.get(key)
    if image is None:
        width = max((len(row) for row in grid), default=0) * scale
        image = QImage(
            max(width, 1), max(len(grid) * scale, 1), QImage.Format_ARGB32_Premultiplied
        )
        image.fill(Qt.transparent)
        painter = QPainter(image)
        colors = {"#": QColor(ink), "o": QColor(hole)}
        for r, row in enumerate(grid):
            for c, ch in enumerate(row):
                if ch in colors:
                    painter.fillRect(c * scale, r * scale, scale, scale, colors[ch])
        painter.end()
        _sprites[key] = image
    return image


NOISE_SHEETS = 8
_noise: dict[tuple[int, int, int], QImage] = {}


def noise_sheet(lo: int, hi: int, which: int) -> QImage:
    """One of a few screen-sized sheets of static, made once and cut up after.
    Fresh random numbers every frame cost a Pi 3 more than the frame budget."""
    key = (lo, hi, which % NOISE_SHEETS)
    if key not in _noise:
        grey = np.random.default_rng(key).integers(
            lo, hi + 1, (clock.H, clock.W), np.uint8
        )
        sheet = QImage(grey.data, clock.W, clock.H, clock.W, QImage.Format_Grayscale8)
        # Converted once, so drawing a band is a plain copy rather than a
        # whole-sheet conversion every time.
        _noise[key] = sheet.convertToFormat(QImage.Format_RGB32)
    return _noise[key]


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

    def sprite(
        self, grid: Sequence[str], x: int, y: int, ink: str, hole: str, scale: int = 1
    ) -> None:
        if grid:
            self._painter.drawImage(x, y, sprite_image(grid, ink, hole, scale))

    def noise(
        self, x: int, y: int, w: int, h: int, seed: int, lo: int = 0, hi: int = 255
    ) -> None:
        sheet = noise_sheet(lo, hi, seed)
        w, h = min(w, sheet.width()), min(h, sheet.height())
        top = (seed * 7) % (sheet.height() - h + 1)
        self._painter.drawImage(QRect(x, y, w, h), sheet, QRect(0, top, w, h))

    def finish(self) -> None:
        self._painter.end()


def render(scene: Scene, now: datetime, t: float, transparent: bool = False) -> QImage:
    """Draw one frame of a scene at the screen's logical size."""
    if transparent:
        image = QImage(clock.W, clock.H, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
    else:
        image = QImage(clock.W, clock.H, QImage.Format_RGB32)
    canvas = ImageCanvas(image)
    try:
        scene(canvas, now, t)
    finally:
        canvas.finish()
    return image


def frame_to_image(frame: Any) -> QImage:
    """An OpenCV frame (BGR) as a QImage that owns its own pixels."""
    rgb = np.ascontiguousarray(frame[:, :, ::-1])
    height, width = rgb.shape[:2]
    return QImage(rgb.data, width, height, 3 * width, QImage.Format_RGB888).copy()


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


def fit(outer: QRect, w: int = clock.W, h: int = clock.H, whole: bool = True) -> QRect:
    """The biggest scale of a w x h picture that fits, centred. Whole-number
    scales keep pixel art square; the camera can use any scale."""
    scale = min(outer.width() / w, outer.height() / h)
    if whole:
        scale = max(1, int(scale))
    sw, sh = round(w * scale), round(h * scale)
    return QRect(
        outer.x() + (outer.width() - sw) // 2,
        outer.y() + (outer.height() - sh) // 2,
        sw,
        sh,
    )


class ScreenWindow(QWidget):
    """Shows the screen's current stage and turns any button into a press."""

    def __init__(
        self,
        screen: Screen | None = None,
        now: Callable[[], datetime] = datetime.now,
        seconds: Callable[[], float] = time.monotonic,
        feed_factory: FeedFactory | None = None,
        windowed: bool = True,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Wolf Run")
        self.screen = screen or Screen()
        self._now, self._seconds = now, seconds
        self._feed_factory, self._windowed = feed_factory, windowed
        self.feed: CameraFeed | None = None
        self._start = seconds()
        self._image = render(self.screen.draw, now(), 0.0)
        self._camera: QImage | None = None
        self._overlay: QImage | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._timer.start(1000 // FPS)

    def elapsed(self) -> float:
        return self._seconds() - self._start

    def tick(self) -> None:
        t, now = self.elapsed(), self._now()
        self.screen.update(t)
        self._manage_feed()
        frame = self.feed.latest() if self.feed else None
        if self.screen.stage is Stage.CAMERA and frame is not None:
            self._camera = frame_to_image(frame)

            def osd(canvas: Canvas, when: datetime, at: float) -> None:
                camera_scene.draw_camera_osd(canvas, when, at, live=True)

            self._overlay = render(osd, now, t, transparent=True)
        else:
            self._camera = self._overlay = None
            self._image = render(self.screen.draw, now, t)
        self.update()

    def _manage_feed(self) -> None:
        """Connect to the camera when the ending needs it; hang up after a reset."""
        if self.screen.wants_camera and self.feed is None and self._feed_factory:
            self.feed = self._feed_factory()
            if self.feed:
                self.feed.start()
        elif not self.screen.wants_camera and self.feed is not None:
            self.feed.stop()
            self.feed = None

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt's name
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        if self._camera is not None and self._overlay is not None:
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            size = self._camera.width(), self._camera.height()
            painter.drawImage(fit(self.rect(), *size, whole=False), self._camera)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
            painter.drawImage(fit(self.rect()), self._overlay)
        else:
            painter.drawImage(fit(self.rect()), self._image)
        painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt's name
        if event.isAutoRepeat():
            return
        t = self.elapsed()
        if event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier):
            self._host_key(event.key(), t)
        elif event.key() == Qt.Key_Escape and self._windowed:
            self.close()
        else:
            self.screen.press(t)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt's name
        if not event.isAutoRepeat():
            self.screen.release(self.elapsed())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt's name
        self.screen.press(self.elapsed())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt's name
        self.screen.release(self.elapsed())

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt's name
        if self.feed is not None:
            self.feed.stop()
            self.feed = None
        super().closeEvent(event)

    def _host_key(self, key: int, t: float) -> None:
        if key == Qt.Key_P:
            self.screen.prime(t)
        elif key == Qt.Key_R:
            self.screen.reset(t)
        elif key == Qt.Key_E:
            self.screen.skip_to_ending(t)
        elif key == Qt.Key_Q:
            self.close()


def ensure_app(offscreen: bool = False) -> QApplication:
    """Reuse the running QApplication, or start one."""
    app = QApplication.instance()
    if app is None:
        if offscreen:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication([])
    return app


def warm_caches(now: datetime | None = None) -> None:
    """Rehearse every house's ending offscreen, so the sprite and static caches are
    full before anyone plays. Otherwise the first game stutters while they fill.
    Takes a couple of seconds on a Pi 3, once, at startup."""
    from wolf_run.game import LEVELS
    from wolf_run.stages import Screen

    now = now or datetime.now()
    for primed in (False, True):
        screen = Screen()
        if primed:
            screen.prime(0.0)
        for i in range(0, 90, 3):
            render(screen.draw, now, i / 30)
    for level in range(len(LEVELS)):
        screen = Screen(seed=level, demo=True)
        screen.prime(0.0)
        screen.press(0.0)
        game = screen.game
        assert game is not None
        game._start_level(level)
        game.progress, game.scroll = 1.0, 1000.0
        t = 0.0
        while (
            screen.stage is Stage.GAME and screen.game is game and game.level == level
        ):
            t += 1 / 30
            screen.update(t)
            render(screen.draw, now, t)
            if t > 60:
                break

    def camera(canvas: Canvas, when: datetime, at: float) -> None:
        camera_scene.draw_camera_osd(canvas, when, at, live=False)

    for i in range(NOISE_SHEETS):
        render(camera, now, i / 15)


def camera_feed_factory(env_path: Path = Path(".env")) -> FeedFactory:
    """Build camera feeds from .env, or none at all if it isn't set up yet."""
    from wolf_run import config

    try:
        settings = config.camera_settings(config.read_env(env_path))
    except config.ConfigError as error:
        print(f"No camera: {error}", file=sys.stderr)
        return lambda: None
    return lambda: CameraFeed(settings.rtsp_url())


def run(windowed: bool, primed: bool = False) -> int:  # pragma: no cover
    """Show the screen until the host quits it, primed from the start if asked."""
    app = ensure_app()
    warm_caches()
    window = ScreenWindow(feed_factory=camera_feed_factory(), windowed=windowed)
    if primed:
        window.screen.prime(window.elapsed())
    if windowed:
        window.resize(PANEL_W, PANEL_H)
        window.show()
    else:
        window.setCursor(Qt.BlankCursor)
        window.showFullScreen()
    return app.exec_()
