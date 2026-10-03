from datetime import datetime

import pytest
from PyQt5.QtCore import QEvent, QRect, Qt
from PyQt5.QtGui import QColor, QImage, QKeyEvent

from wolf_run import clock, ui
from wolf_run.palette import NIGHT

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


def test_window_redraws_on_tick_and_closes_on_escape():
    seconds = iter([100.0, 104.0])
    window = ui.ScreenWindow(
        now=lambda: HALLOWEEN_EVENING, seconds=lambda: next(seconds)
    )
    window.resize(ui.PANEL_W, ui.PANEL_H)
    window.show()

    window.tick()
    frame = window.grab().toImage()

    assert frame.pixelColor(0, clock.GROUND_Y * 4) == QColor(NIGHT.ink)
    window.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    assert not window.isVisible()
