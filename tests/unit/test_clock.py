from datetime import datetime

import pytest

from conftest import FakeCanvas
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


def test_wolf_sleeps_and_breathes_until_primed():
    breaths = {tuple(clock.wolf_pose(t, None).grid) for t in (0.5, 2.0)}

    assert breaths == {
        tuple(clock.sprites.WOLF_SLEEP_A),
        tuple(clock.sprites.WOLF_SLEEP_B),
    }


def test_wolf_wakes_with_a_start_then_hops_up_and_wags():
    startled = clock.wolf_pose(10.3, primed_at=10.0)
    hopping = clock.wolf_pose(11.0, primed_at=10.0)
    wags = {tuple(clock.wolf_pose(10.0 + s, 10.0).grid) for s in (1.35, 1.55)}

    assert startled.startled
    assert startled.grid == clock.sprites.WOLF_STARTLED
    assert hopping.lift > 0
    assert wags == {tuple(clock.sprites.WOLF_B), tuple(clock.sprites.WOLF_WAG)}


def test_snores_rise_and_grow():
    low, high = sorted(clock.snores(1.0), key=lambda z: -z.y)[::2]

    assert high.y < low.y
    assert high.scale >= low.scale


def test_prompt_waits_for_him_to_stand_then_blinks():
    assert not clock.prompt_visible(5.0, None)
    assert not clock.prompt_visible(10.5, primed_at=10.0)
    assert clock.prompt_visible(11.4, primed_at=10.0)
    assert not clock.prompt_visible(12.1, primed_at=10.0)


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


def test_primed_swaps_the_date_for_the_prompt(canvas):
    def ink_in_date_band(primed_at):
        drawn = FakeCanvas()
        clock.draw_clock(drawn, HALLOWEEN_EVENING, 11.5, primed_at)
        band = range(clock.DATE_Y - 2, clock.DATE_Y + 9)
        return {
            color
            for (x, y), color in drawn.pixels.items()
            if y in band and 40 < x < 220
        }

    asleep, primed = ink_in_date_band(None), ink_in_date_band(10.0)

    assert NIGHT.dim in asleep
    assert NIGHT.ink not in asleep
    assert NIGHT.ink in primed


def test_startled_wolf_gets_a_glowing_exclamation_mark(canvas):
    clock.draw_clock(canvas, HALLOWEEN_EVENING, 10.2, primed_at=10.0)

    assert NIGHT.glow in {
        canvas.at(x, y) for x in range(20, 40) for y in range(80, 110)
    }


def test_same_moment_draws_the_same_picture():
    first, second = clock_pixels(4.0), clock_pixels(4.0)

    assert first == second
    assert first != clock_pixels(4.6)


def clock_pixels(t):
    canvas = FakeCanvas()
    clock.draw_clock(canvas, HALLOWEEN_EVENING, t)
    return canvas.pixels


def test_standing_wolf_stays_clear_of_the_prompt():
    standing = clock.wolf_pose(12.0, primed_at=10.0)
    head_right = clock.WOLF_X + standing.shift + len(standing.grid[0])
    prompt_left = (clock.W - clock.text_width(clock.PROMPT, clock.PROMPT_SCALE)) // 2

    ear_and_head_right = head_right - 6  # the snout is below the prompt's baseline
    assert ear_and_head_right < prompt_left
