from datetime import datetime

from conftest import FakeCanvas
from wolf_run import clock
from wolf_run.stages import Screen, Stage

HALLOWEEN_EVENING = datetime(2026, 10, 31, 21, 47)


def test_screen_starts_as_a_sleeping_clock():
    assert Screen().stage is Stage.CLOCK


def test_priming_remembers_when_it_happened():
    screen = Screen()

    assert screen.prime(12.5)
    assert (screen.stage, screen.since) == (Stage.PRIMED, 12.5)


def test_priming_twice_keeps_the_first_time():
    screen = Screen()
    screen.prime(12.5)

    assert not screen.prime(20.0)
    assert screen.since == 12.5


def test_reset_puts_the_wolf_back_to_sleep():
    screen = Screen()
    screen.prime(12.5)

    screen.reset(30.0)

    assert (screen.stage, screen.since) == (Stage.CLOCK, 30.0)


def test_draw_matches_the_clock_for_its_stage():
    screen, drawn, expected = Screen(), FakeCanvas(), FakeCanvas()
    screen.prime(10.0)

    screen.draw(drawn, HALLOWEEN_EVENING, 12.0)
    clock.draw_clock(expected, HALLOWEEN_EVENING, 12.0, primed_at=10.0)

    assert drawn.pixels == expected.pixels
