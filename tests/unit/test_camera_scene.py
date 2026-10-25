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


def test_the_camera_picture_sits_on_the_canvas_like_the_window_fits_it():
    # A 16:9 picture on the 1024x600 panel: full width, a band above and below.
    assert camera_scene.picture_box(1024, 600, 1280, 720) == (0.0, 3.0, 256.0, 144.0)
    # A wider window: the canvas stays at x4, the picture grows past its sides.
    x, y, w, h = camera_scene.picture_box(1100, 600, 1280, 720)
    assert (round(x, 2), round(y, 2), round(w, 2), round(h, 2)) == (
        -5.5,
        0.0,
        266.75,
        150.0,
    )
    assert camera_scene.on_picture((0, 0, 200, 100), (0.5, 0.25)) == (100, 25)


def test_the_card_outline_shows_where_to_hold_it():
    canvas = FakeCanvas()
    card = camera_scene.CardView(outline=(100, 40, 40, 60))

    camera_scene.draw_camera_osd(canvas, NIGHT_OF, 0.2, live=True, card=card)

    assert canvas.at(100, 40) == camera_scene.OSD  # a dash at the top left
    assert canvas.at(97, 37) == camera_scene.OSD  # the corner bracket
    colors = set(canvas.pixels.values())
    assert camera_scene.FOUND not in colors
    label_row = [canvas.at(x, 32) for x in range(80, 160)]
    assert camera_scene.OSD in label_row  # HOLD HIS CARD HERE, above the box


def test_the_outline_lights_and_traces_the_card_while_it_reads():
    canvas = FakeCanvas()
    seen = ((105.0, 45.0), (130.0, 47.0), (128.0, 90.0), (103.0, 88.0))
    card = camera_scene.CardView(outline=(100, 40, 40, 60), seen=seen)

    camera_scene.draw_camera_osd(canvas, NIGHT_OF, 0.2, live=True, card=card)

    assert canvas.at(100, 40) == camera_scene.FOUND
    assert canvas.at(105, 45) == camera_scene.FOUND  # the card's own corner
    assert canvas.at(117, 46) == camera_scene.FOUND  # along its top edge


def test_a_box_near_the_top_puts_its_words_underneath():
    canvas = FakeCanvas()
    card = camera_scene.CardView(outline=(100, 4, 40, 60))

    camera_scene.draw_camera_osd(canvas, NIGHT_OF, 0.2, live=True, card=card)

    assert camera_scene.OSD in [canvas.at(x, 69) for x in range(80, 160)]


def test_no_card_outline_without_a_picture():
    canvas = FakeCanvas()
    card = camera_scene.CardView(outline=(100, 40, 40, 60))

    camera_scene.draw_camera_osd(canvas, NIGHT_OF, 0.7, live=False, card=card)

    assert canvas.at(100, 40) == "noise"
