import random
from datetime import datetime

import pytest

from conftest import FakeCanvas
from wolf_run import game_scene, sprites
from wolf_run.game import LEVELS, Game, Obstacle, Phase
from wolf_run.palette import NIGHT

HALLOWEEN_EVENING = datetime(2026, 10, 31, 21, 47)


def at(phase: Phase, level: int = 0, steps: int = 40, phase_steps: int = 8) -> Game:
    game = Game(rng=random.Random(1))
    game.level, game.phase = level, phase
    game.steps, game.phase_steps = steps, phase_steps
    game.house_x = 150
    game.scroll = 0 if phase is Phase.INTRO else 1000  # the village is long gone
    return game


def drawn(game: Game) -> FakeCanvas:
    canvas = FakeCanvas()
    game_scene.draw_game(canvas, game, HALLOWEEN_EVENING, 3.0)
    return canvas


@pytest.mark.parametrize("phase", list(Phase))
@pytest.mark.parametrize("level", range(len(LEVELS)))
def test_every_moment_of_the_game_draws(phase, level):
    canvas = drawn(at(phase, level))

    assert canvas.pixels


def test_static_fills_the_screen():
    canvas = drawn(at(Phase.STATIC))

    assert canvas.at(0, 0) == canvas.at(255, 149) == "noise"


def test_clock_slides_up_as_the_run_begins():
    first = drawn(at(Phase.INTRO, steps=1, phase_steps=1))
    later = drawn(at(Phase.INTRO, steps=40, phase_steps=40))

    digit_band = [(x, y) for x in range(40, 200) for y in range(30, 60)]
    assert any(first.at(x, y) == NIGHT.ink for x, y in digit_band)
    assert not any(later.at(x, y) == NIGHT.ink for x, y in digit_band)


def test_obstacles_are_drawn_where_they_are():
    game = at(Phase.RUN)
    game.obstacles = [Obstacle("straw", 100)]

    canvas = drawn(game)

    assert canvas.at(100, 120 - 2) == NIGHT.ink


def test_running_wolf_alternates_legs_and_tucks_them_to_jump():
    game = at(Phase.RUN)
    frames = set()
    for steps in range(8):
        game.steps = steps
        frames.add(tuple(game_scene.wolf_frame(game)))
    game.wolf_y = -10

    assert len(frames) == 2
    assert game_scene.wolf_frame(game) == sprites.WOLF_JUMP


def test_debris_flies_off_and_falls_away():
    early = game_scene.debris(0, 150, 2)
    later = game_scene.debris(0, 150, 30)

    assert len(later) < len(early)
    assert min(x for _, x, _ in later) > min(x for _, x, _ in early)


def test_the_house_shakes_while_he_eats_inside():
    positions = set()
    for p in range(4):
        canvas = drawn(at(Phase.INSIDE, level=2, phase_steps=p))
        left = min(
            x
            for (x, y), color in canvas.pixels.items()
            if color == NIGHT.ink and y == 98  # the chimney cap, the top row
        )
        positions.add(left)

    assert len(positions) == 2


def test_the_wolf_vanishes_into_the_chimney():
    game = at(Phase.CLIMB, level=2, phase_steps=39)
    game.wolf_x, game.wolf_y = 155, 0

    canvas = drawn(game)
    above_roof = [
        (x, y)
        for (x, y), color in canvas.pixels.items()
        if color == NIGHT.ink and 150 <= x <= 190 and 60 < y < 120 - 22
    ]

    assert not above_roof


def test_crash_says_ouch_and_how_to_try_again():
    canvas = drawn(at(Phase.CRASH, phase_steps=31))

    assert any(
        color == NIGHT.ink for (x, y), color in canvas.pixels.items() if 40 <= y < 55
    )
    assert any(
        color == NIGHT.ink for (x, y), color in canvas.pixels.items() if 66 <= y < 71
    )


def test_hud_shows_houses_done_and_tries():
    game = at(Phase.RUN, level=2, steps=100)
    game.tries = 3

    canvas = drawn(game)

    assert canvas.at(158, 6) == canvas.at(166, 6) == NIGHT.ink  # two houses down
    assert canvas.at(176, 8) is None or canvas.at(176, 8) != NIGHT.ink


def test_grandma_runs_in_the_intro_and_from_each_house():
    for phase in (Phase.INTRO, Phase.FLEE):
        game = at(phase, phase_steps=30)
        game.granny_x = 120

        canvas = drawn(game)

        assert canvas.at(120 + 8, 120 - 12) is not None


def test_rummaging_throws_junk_out_of_the_chimney_that_lands_nearby():
    flying = game_scene.junk(150, 20)
    landed = game_scene.junk(150, 90)

    assert len(flying) < len(landed) == len(game_scene.JUNK)
    for grid, x, y in landed:
        assert y == 120 - len(grid)
        assert 100 < x < 230


def test_rummage_shows_soot_words_then_aha():
    early = drawn(at(Phase.RUMMAGE, level=2, phase_steps=20))
    found = drawn(at(Phase.RUMMAGE, level=2, phase_steps=80))

    assert NIGHT.soft in early.pixels.values()
    assert any(
        color == NIGHT.ink and 120 - 52 <= y < 120 - 52 + 15
        for (x, y), color in found.pixels.items()
    )


def test_try_again_draws_button_in_red():
    canvas = drawn(at(Phase.CRASH, phase_steps=31))

    assert NIGHT.red in canvas.pixels.values()
