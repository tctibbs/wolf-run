from datetime import datetime

import numpy as np
import pytest
from PyQt5.QtCore import QEvent, QPoint, QRect, Qt
from PyQt5.QtGui import QColor, QImage, QKeyEvent, QTouchEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from wolf_run import camera_scene, card, clock, control, ui
from wolf_run.game import CRASH_PAUSE, JUMP_SPEED, LEVELS, Phase
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


def test_enter_from_the_red_button_starts_the_game_and_jumps():
    window = window_at(Ticker())
    window.screen.prime(0.0)

    window.keyPressEvent(key(Qt.Key_Return))
    window.keyReleaseEvent(key(Qt.Key_Return, kind=QEvent.KeyRelease))
    assert window.screen.stage is Stage.GAME

    window.screen.game._start_level(0)
    window.keyPressEvent(key(Qt.Key_Enter))
    window.keyPressEvent(
        QKeyEvent(QEvent.KeyPress, Qt.Key_Enter, Qt.NoModifier, "", True)
    )
    assert (window.screen.game.holding, window.screen.game.vy) == (True, JUMP_SPEED)
    window.keyReleaseEvent(key(Qt.Key_Enter, kind=QEvent.KeyRelease))
    assert not window.screen.game.holding


def running(window):
    window.screen.prime(0.0)
    window.screen.press(0.0)
    window.screen.release(0.0)
    window.screen.game._start_level(0)


def crashed(window):
    running(window)
    window.screen.game._enter(Phase.CRASH)
    window.screen.game.phase_steps = CRASH_PAUSE + 1


def ending(window):
    running(window)
    window.screen.game._start_level(len(LEVELS) - 1)
    window.screen.game._enter(Phase.RUMMAGE)


def watching(window):
    window.screen.stage = Stage.CAMERA


STATES = {
    "clock": lambda window: None,
    "primed": lambda window: window.screen.prime(0.0),
    "game": running,
    "crash": crashed,
    "ending": ending,
    "camera": watching,
}


def touch(window, kind, state):
    """A touch event straight to the window (PyQt5 can't make the points)."""
    QApplication.sendEvent(window, QTouchEvent(kind, None, Qt.NoModifier, state, []))


@pytest.mark.parametrize("enter", STATES.values(), ids=STATES.keys())
def test_touches_and_clicks_never_count_as_the_button(enter):
    window = window_at(Ticker())
    window.resize(ui.PANEL_W, ui.PANEL_H)
    window.show()
    enter(window)
    before = repr(window.screen)
    # Qt turns a touch it isn't asked to handle into these mouse events, sent
    # through the same window as the Pi's touchscreen.
    glass = window.windowHandle()
    middle = QPoint(ui.PANEL_W // 2, ui.PANEL_H // 2)

    QTest.mousePress(glass, Qt.LeftButton, Qt.NoModifier, middle)
    assert repr(window.screen) == before  # held down: a long press
    QTest.mouseRelease(glass, Qt.LeftButton, Qt.NoModifier, middle)
    QTest.mouseDClick(glass, Qt.LeftButton, Qt.NoModifier, middle)
    QTest.mouseClick(glass, Qt.RightButton, Qt.NoModifier, middle)
    touch(window, QEvent.TouchBegin, Qt.TouchPointPressed)
    touch(window, QEvent.TouchEnd, Qt.TouchPointReleased)

    assert repr(window.screen) == before


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


def test_sprites_are_drawn_once_then_reused():
    ui._sprites.clear()
    image = QImage(6, 2, QImage.Format_RGB32)
    image.fill(QColor("#000000"))
    canvas = ui.ImageCanvas(image)

    canvas.sprite(["#o."], 0, 0, "#ffffff", "#ff0000")
    canvas.sprite(["#o."], 3, 0, "#ffffff", "#ff0000")
    canvas.finish()

    assert len(ui._sprites) == 1
    assert image.pixelColor(0, 0) == QColor("#ffffff")
    assert image.pixelColor(1, 0) == QColor("#ff0000")
    assert image.pixelColor(2, 0) == QColor("#000000")  # '.' stays see-through
    assert image.pixelColor(3, 0) == QColor("#ffffff")


def test_scaled_sprites_and_empty_ones():
    image = QImage(4, 4, QImage.Format_RGB32)
    image.fill(QColor("#000000"))
    canvas = ui.ImageCanvas(image)

    canvas.sprite(["#"], 0, 0, "#00ff00", "#000000", scale=2)
    canvas.sprite([], 0, 0, "#00ff00", "#000000")
    canvas.finish()

    assert image.pixelColor(1, 1) == QColor("#00ff00")
    assert image.pixelColor(2, 2) == QColor("#000000")


def test_cached_drawing_matches_pixel_by_pixel():
    """The fast path must draw exactly what the slow one does."""
    from conftest import FakeCanvas
    from wolf_run.pixels import paint

    image = QImage(clock.W, clock.H, QImage.Format_RGB32)
    image.fill(QColor(NIGHT.bg))
    canvas = ui.ImageCanvas(image)
    paint(canvas, clock.sprites.BRICK_HOUSE_BIG, 10, 10, NIGHT.ink, NIGHT.glow)
    canvas.finish()
    fake = FakeCanvas()
    paint(fake, clock.sprites.BRICK_HOUSE_BIG, 10, 10, NIGHT.ink, NIGHT.glow)

    for (x, y), color in fake.pixels.items():
        assert image.pixelColor(x, y) == QColor(color)


def test_static_is_cut_from_a_few_reused_sheets():
    ui._noise.clear()
    image = QImage(clock.W, clock.H, QImage.Format_RGB32)
    canvas = ui.ImageCanvas(image)

    for seed in range(40):
        canvas.noise(0, seed % 140, clock.W, 6, seed=seed)
    canvas.noise(0, 0, clock.W, clock.H, seed=3)
    canvas.finish()

    assert len(ui._noise) == ui.NOISE_SHEETS


def test_warming_up_fills_the_caches_before_anyone_plays():
    ui._sprites.clear()
    ui._noise.clear()

    ui.warm_caches(HALLOWEEN_EVENING)

    keys = {key[0] for key in ui._sprites}
    assert tuple(clock.sprites.BRICK_HOUSE_BIG) in keys
    assert tuple(clock.sprites.WOLF_FAT) in keys
    assert tuple(clock.sprites.WOLF_SLEEP_A) in keys
    assert ui._noise


def test_the_window_picks_up_where_it_was_and_remembers_changes(tmp_path):
    from wolf_run import memory

    path = tmp_path / "place.json"
    memory.save(path, {"stage": "game", "house": 2})
    ticker = Ticker()
    window = window_at(ticker, place_file=path)
    assert window.screen.stage is Stage.PRIMED
    assert window.screen.resume_level == 1

    ticker.t = 101.0
    window.keyPressEvent(key(Qt.Key_R, Qt.ControlModifier))
    window.tick()

    assert memory.load(path) == {"stage": "clock"}


def test_a_window_without_a_place_file_remembers_nothing(tmp_path):
    ticker = Ticker()
    window = window_at(ticker)
    window.keyPressEvent(key(Qt.Key_P, Qt.ControlModifier))
    window.tick()

    assert window.screen.stage is Stage.PRIMED
    assert list(tmp_path.iterdir()) == []


def test_the_card_outline_lands_on_the_camera_picture():
    sightings = control.Sightings(lambda: 10.0)
    window = window_at(
        Ticker(), card_spot=card.CardSpot((0.5, 0.25, 0.25, 0.5)), sightings=sightings
    )
    window.resize(ui.PANEL_W, ui.PANEL_H)

    view = window.card_view(1280, 720)

    assert view is not None and view.seen is None
    assert view.outline == (128.0, 39.0, 64.0, 72.0)
    sightings.report(((0.5, 0.25), (0.75, 0.25), (0.75, 0.75), (0.5, 0.75)))
    view = window.card_view(1280, 720)
    assert view.seen == ((128.0, 39.0), (192.0, 39.0), (192.0, 111.0), (128.0, 111.0))
    assert window_at(Ticker()).card_view(1280, 720) is None


def test_the_camera_view_draws_the_card_outline():
    feed = FakeFeed(np.zeros((720, 1280, 3), dtype=np.uint8))
    window = window_at(
        Ticker(),
        feed_factory=lambda: feed,
        card_spot=card.CardSpot((0.5, 0.25, 0.25, 0.5)),
    )
    window.resize(ui.PANEL_W, ui.PANEL_H)
    window.show()
    window.screen.stage = Stage.CAMERA

    window.tick()

    assert window._overlay is not None
    # The outline's top-left dash, at canvas (128, 39), drawn into the overlay.
    assert window._overlay.pixelColor(128, 39) == QColor(camera_scene.OSD)
