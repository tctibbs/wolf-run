from wolf_run.pixels import disc, paint, text, text_width
from wolf_run.sprites import BIG_FONT


def test_paint_uses_ink_holes_and_leaves_dots_alone(canvas):
    paint(canvas, ["#o."], 10, 20, ink="ink", hole="hole")

    assert canvas.at(10, 20) == "ink"
    assert canvas.at(11, 20) == "hole"
    assert canvas.at(12, 20) is None


def test_paint_scales_each_pixel_into_a_block(canvas):
    paint(canvas, ["#"], 0, 0, ink="ink", hole="hole", scale=3)

    assert {canvas.at(x, y) for x in range(3) for y in range(3)} == {"ink"}
    assert canvas.at(3, 0) is None


def test_text_width_counts_glyphs_and_gaps():
    assert text_width("") == 0
    assert text_width("A") == 3
    assert text_width("AB") == 7
    assert text_width("AB", scale=2) == 14


def test_text_width_handles_narrow_glyphs():
    assert text_width("9:47", 1, BIG_FONT) == 5 + 1 + 1 + 1 + 5 + 1 + 5


def test_text_draws_and_returns_where_it_ended(canvas):
    end = text(canvas, "I", 5, 5, "ink")

    assert end == 8
    assert canvas.at(5, 5) == "ink"
    assert canvas.at(6, 6) == "ink"
    assert canvas.at(5, 6) is None


def test_disc_is_round_and_filled(canvas):
    disc(canvas, 10, 10, 3, "moon")

    assert canvas.at(10, 10) == "moon"
    assert canvas.at(13, 10) == "moon"
    assert canvas.at(10, 7) == "moon"
    assert canvas.at(13, 13) is None
