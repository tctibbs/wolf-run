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


def started(seed=3):
    screen = Screen(seed=seed)
    screen.prime(0.0)
    screen.press(1.0)
    return screen


def test_pressing_while_asleep_does_nothing():
    screen = Screen()

    assert screen.press(1.0) == []
    assert screen.stage is Stage.CLOCK


def test_any_button_starts_the_game_once_primed():
    screen = started()

    assert screen.stage is Stage.GAME
    assert screen.game is not None


def test_release_reaches_the_game():
    screen = started()
    screen.game._start_level(0)

    assert screen.press(2.0) == ["jump"]
    screen.release(2.0)

    assert not screen.game.holding


def test_update_steps_the_game_thirty_times_a_second():
    screen = started()

    for frame in range(1, 31):
        screen.update(1.0 + frame / 30)

    assert screen.game.steps == 30


def test_a_long_stall_skips_ahead_instead_of_fast_forwarding():
    screen = started()

    screen.update(60.0)

    assert screen.game.steps == 10


def test_the_game_hands_over_to_the_camera_when_it_ends():
    screen = started()
    screen.skip_to_ending(1.0)
    t = 1.0
    while screen.stage is Stage.GAME and t < 120:
        t += 0.1
        screen.update(t)

    assert screen.stage is Stage.CAMERA
    assert screen.wants_camera


def test_camera_stage_draws_no_signal_until_the_picture_arrives():
    screen = Screen(stage=Stage.CAMERA)
    canvas = FakeCanvas()

    screen.draw(canvas, HALLOWEEN_EVENING, 3.0)

    assert canvas.at(128, 20) == "noise"


def test_skip_from_the_clock_goes_straight_to_the_brick_house():
    screen = Screen()

    screen.skip_to_ending(1.0)

    assert screen.stage is Stage.GAME
    assert screen.game.last_level


def test_reset_drops_the_game():
    screen = started()

    screen.reset(5.0)

    assert (screen.stage, screen.game) == (Stage.CLOCK, None)
    assert screen.update(6.0) == []
    assert not screen.wants_camera
