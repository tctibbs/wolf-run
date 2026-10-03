from datetime import datetime

import pytest

from wolf_run import clock
from wolf_run.palette import NIGHT

HALLOWEEN_EVENING = datetime(2026, 10, 31, 21, 47)


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (0, 5, ("12:05", "AM")),
        (9, 7, ("9:07", "AM")),
        (12, 0, ("12:00", "PM")),
        (21, 47, ("9:47", "PM")),
    ],
)
def test_time_reads_like_a_wall_clock(hour, minute, expected):
    assert clock.time_parts(datetime(2026, 10, 31, hour, minute)) == expected


def test_date_line_spells_out_the_day():
    assert clock.date_line(HALLOWEEN_EVENING) == "SATURDAY OCTOBER 31"


def test_colon_blinks_every_second():
    assert clock.colon_visible(4.2)
    assert not clock.colon_visible(4.7)


def test_wolf_eyes_peek_out_then_hide():
    assert not clock.eyes_open(1.0)
    assert clock.eyes_open(4.0)
    assert not clock.eyes_open(4.7)
    assert not clock.eyes_open(12.0)
    assert clock.eyes_open(24.0)


def test_bats_fly_right_to_left_then_leave():
    early, later = clock.bats(1.5), clock.bats(5.0)

    assert len(early) == 2
    assert later[0].x < early[0].x
    assert clock.bats(15.0) == []


def test_drips_grow_then_let_go():
    assert clock.drip(0.0, 0) == (1, None)
    length, fallen = clock.drip(clock.DRIP_CYCLE * 0.7, 0)
    assert length > 5
    assert fallen is None
    assert clock.drip(clock.DRIP_CYCLE * 0.9, 0)[1] is not None


def test_stars_stay_out_of_the_way_of_the_time():
    left, top, right, bottom = clock.CLEAR

    for x, y, _ in clock.STARS:
        assert not (left <= x <= right and top <= y <= bottom)


def test_draw_clock_paints_the_time_and_the_ground(canvas):
    clock.draw_clock(canvas, HALLOWEEN_EVENING, t=4.0)

    inked = {xy for xy, color in canvas.pixels.items() if color == NIGHT.ink}
    in_digits = [
        (x, y)
        for x, y in inked
        if clock.DIGIT_TOP <= y < clock.DIGIT_TOP + 7 * clock.DIGIT_SCALE
    ]
    assert len(in_digits) > 500
    assert canvas.at(0, clock.GROUND_Y) == NIGHT.ink
    assert canvas.at(0, 0) == NIGHT.bg


def test_wolf_eyes_glow_only_while_open(canvas):
    eye_x = clock.BUSH_X + clock.EYES[0][0]
    eye_y = clock.GROUND_Y - len(clock.sprites.BUSH) + clock.EYES[0][1]

    clock.draw_clock(canvas, HALLOWEEN_EVENING, t=4.0)
    assert canvas.at(eye_x, eye_y) == NIGHT.glow

    clock.draw_clock(canvas, HALLOWEEN_EVENING, t=12.0)
    assert canvas.at(eye_x, eye_y) == NIGHT.soft


def test_same_moment_draws_the_same_picture():
    first, second = clock_pixels(4.0), clock_pixels(4.0)

    assert first == second
    assert first != clock_pixels(4.6)


def clock_pixels(t):
    from conftest import FakeCanvas

    canvas = FakeCanvas()
    clock.draw_clock(canvas, HALLOWEEN_EVENING, t)
    return canvas.pixels
