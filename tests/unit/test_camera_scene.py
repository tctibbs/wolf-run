from datetime import datetime

from conftest import FakeCanvas
from wolf_run import camera_scene

NIGHT_OF = datetime(2026, 10, 31, 23, 47, 12)


def test_live_overlay_leaves_the_picture_showing():
    canvas = FakeCanvas()

    camera_scene.draw_camera_osd(canvas, NIGHT_OF, 0.2, live=True)

    assert canvas.at(128, 75) is None
    assert canvas.at(222, 8) == camera_scene.REC


def test_no_signal_fills_with_static():
    canvas = FakeCanvas()

    camera_scene.draw_camera_osd(canvas, NIGHT_OF, 0.7, live=False)

    assert canvas.at(10, 140) in ("noise", camera_scene.OSD)
    assert canvas.at(222, 8) == "noise"  # REC light blinks off
