from datetime import datetime

import numpy as np
import pytest
from PyQt5.QtCore import QEvent, QPointF, QRect, Qt
from PyQt5.QtGui import QColor, QImage, QKeyEvent, QMouseEvent

from wolf_run import clock, ui
from wolf_run.palette import NIGHT
from wolf_run.stages import Stage

HALLOWEEN_EVENING = datetime(2026, 10, 31, 21, 47)


@pytest.fixture(autouse=True)
def app():
    return ui.ensure_app(offscreen=True)


def test_render_draws_at_the_logical_size():
    image = ui.render(clock.draw_clock, HALLOWEEN_EVENING, 4.0)

    assert (image.width(), image.height()) == (clock.W, clock.H)
    assert image.pixelColor(0, 0) == QColor(NIGHT.bg)


def test_snapshot_is_panel_sized_with_square_pixels(tmp_path):
    path = ui.save_snapshot(tmp_path / "shots" / "clock.png", HALLOWEEN_EVENING, 4.0)

    image = QImage(str(path))
    assert (image.width(), image.height()) == (ui.PANEL_W, ui.PANEL_H)
    ground = clock.GROUND_Y * 4
    assert image.pixelColor(0, ground) == QColor(NIGHT.ink)
    assert image.pixelColor(3, ground + 3) == QColor(NIGHT.ink)


def test_snapshot_reports_a_failed_save(tmp_path, mocker):
    mocker.patch.object(QImage, "save", return_value=False)

    with pytest.raises(OSError, match="Couldn't save"):
        ui.save_snapshot(tmp_path / "clock.png", HALLOWEEN_EVENING, 4.0)


@pytest.mark.parametrize(
    ("outer", "expected"),
    [
        (QRect(0, 0, 1024, 600), QRect(0, 0, 1024, 600)),
        (QRect(0, 0, 1100, 700), QRect(38, 50, 1024, 600)),
        (QRect(0, 0, 100, 100), QRect(-78, -25, 256, 150)),
    ],
)
def test_fit_uses_whole_number_scales(outer, expected):
    assert ui.fit(outer) == expected


def test_image_canvas_reuses_colours():
    image = QImage(4, 4, QImage.Format_RGB32)
    canvas = ui.ImageCanvas(image)

    canvas.fill(0, 0, 2, 2, "#ff0000")
    canvas.fill(2, 2, 2, 2, "#ff0000")
    canvas.finish()

    assert len(canvas._colors) == 1
    assert image.pixelColor(3, 3) == QColor("#ff0000")


class Ticker:
    """A clock the test moves by hand."""

    def __init__(self, t: float = 100.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def key(code, modifiers=Qt.NoModifier, kind=QEvent.KeyPress):
    return QKeyEvent(kind, code, modifiers)


def window_at(ticker, **kwargs):
    return ui.ScreenWindow(now=lambda: HALLOWEEN_EVENING, seconds=ticker, **kwargs)


def test_host_keys_need_ctrl_so_guests_cant_hit_them():
    ticker = Ticker()
    window = window_at(ticker)

    window.keyPressEvent(key(Qt.Key_P))
    assert window.screen.stage is Stage.CLOCK

    ticker.t = 103.0
    window.keyPressEvent(key(Qt.Key_P, Qt.ControlModifier))
    assert (window.screen.stage, window.screen.since) == (Stage.PRIMED, 3.0)

    window.keyPressEvent(key(Qt.Key_R, Qt.ControlModifier))
    assert window.screen.stage is Stage.CLOCK


def test_any_key_starts_the_game_once_primed_and_jumps_after():
    ticker = Ticker()
    window = window_at(ticker)
    window.keyPressEvent(key(Qt.Key_P, Qt.ControlModifier))

    window.keyPressEvent(key(Qt.Key_Z))
    assert window.screen.stage is Stage.GAME

    window.screen.game._start_level(0)
    window.keyPressEvent(key(Qt.Key_Space))
    assert window.screen.game.holding
    window.keyReleaseEvent(key(Qt.Key_Space, kind=QEvent.KeyRelease))
    assert not window.screen.game.holding


def test_held_keys_repeating_are_not_extra_presses():
    window = window_at(Ticker())
    window.screen.prime(0.0)

    window.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier, "", True))

    assert window.screen.stage is Stage.PRIMED


def test_a_click_or_tap_is_a_button_too():
    window = window_at(Ticker())
    window.screen.prime(0.0)
    click = QMouseEvent(
        QEvent.MouseButtonPress,
        QPointF(5, 5),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )

    window.mousePressEvent(click)
    assert window.screen.stage is Stage.GAME
    window.mouseReleaseEvent(click)
    assert not window.screen.game.holding


def test_ctrl_e_skips_to_the_brick_house():
    window = window_at(Ticker())

    window.keyPressEvent(key(Qt.Key_E, Qt.ControlModifier))

    assert window.screen.game.last_level


def test_escape_closes_only_a_windowed_screen():
    full = window_at(Ticker(), windowed=False)
    full.show()
    full.keyPressEvent(key(Qt.Key_Escape))
    assert full.isVisible()

    windowed = window_at(Ticker())
    windowed.show()
    windowed.keyPressEvent(key(Qt.Key_Escape))
    assert not windowed.isVisible()
    full.keyPressEvent(key(Qt.Key_Q, Qt.ControlModifier))
    assert not full.isVisible()


def test_window_redraws_on_tick():
    ticker = Ticker()
    window = window_at(ticker)
    window.resize(ui.PANEL_W, ui.PANEL_H)
    window.show()

    ticker.t = 104.0
    window.tick()
    frame = window.grab().toImage()

    assert frame.pixelColor(0, clock.GROUND_Y * 4) == QColor(NIGHT.ink)


class FakeFeed:
    def __init__(self, frame=None):
        self.frame, self.started, self.stopped = frame, False, False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def latest(self):
        return self.frame


def test_camera_connects_for_the_ending_and_shows_the_picture():
    ticker = Ticker()
    feed = FakeFeed(np.full((360, 640, 3), (0, 0, 255), dtype=np.uint8))
    window = window_at(ticker, feed_factory=lambda: feed)
    window.resize(ui.PANEL_W, ui.PANEL_H)
    window.show()
    window.screen.stage = Stage.CAMERA

    window.tick()
    frame = window.grab().toImage()

    assert feed.started
    assert frame.pixelColor(ui.PANEL_W // 2, ui.PANEL_H // 2) == QColor("#ff0000")

    window.screen.reset(1.0)
    window.tick()
    assert feed.stopped
    assert window.feed is None


def test_closing_the_window_hangs_up_the_camera():
    feed = FakeFeed()
    window = window_at(Ticker(), feed_factory=lambda: feed)
    window.screen.stage = Stage.CAMERA
    window.tick()

    window.close()

    assert feed.stopped


def test_no_camera_settings_means_no_feed(tmp_path, monkeypatch, capsys):
    for name in ("CAMERA_HOST", "CAMERA_USER", "CAMERA_PASSWORD"):
        monkeypatch.delenv(name, raising=False)

    factory = ui.camera_feed_factory(tmp_path / "missing.env")

    assert factory() is None
    assert "No camera" in capsys.readouterr().err


def test_camera_feed_factory_builds_feeds_from_env(tmp_path, monkeypatch):
    for name in ("CAMERA_HOST", "CAMERA_USER", "CAMERA_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("CAMERA_HOST=192.168.1.50\nCAMERA_USER=viewer\nCAMERA_PASSWORD=x\n")

    assert isinstance(ui.camera_feed_factory(env)(), ui.CameraFeed)


def test_noise_paints_grey_static():
    image = QImage(8, 8, QImage.Format_RGB32)
    canvas = ui.ImageCanvas(image)

    canvas.noise(0, 0, 8, 8, seed=1, lo=100, hi=100)
    canvas.finish()

    assert image.pixelColor(4, 4) == QColor(100, 100, 100)


def test_frame_to_image_turns_opencv_blue_green_red_into_red():
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    frame[:, :, 2] = 255

    image = ui.frame_to_image(frame)

    assert image.pixelColor(0, 0) == QColor("#ff0000")
