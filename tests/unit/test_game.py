import random
from itertools import pairwise

import pytest

from wolf_run import game as g
from wolf_run.game import LEVELS, Game, Obstacle, Phase


def run_steps(game: Game, steps: int) -> list[str]:
    sounds: list[str] = []
    for _ in range(steps):
        sounds += game.step()
    return sounds


def until(game: Game, phase: Phase, limit: int = 20_000) -> list[str]:
    sounds: list[str] = []
    for _ in range(limit):
        if game.phase is phase:
            return sounds
        sounds += game.step()
    raise AssertionError(f"never reached {phase}, stuck in {game.phase}")


def running(level: int = 0, **kwargs) -> Game:
    game = Game(rng=random.Random(1), **kwargs)
    game._start_level(level)
    return game


def test_game_opens_with_grandma_running_for_it():
    game = Game(rng=random.Random(1))

    sounds = run_steps(game, 1)
    still = game.granny_x
    run_steps(game, g.INTRO_NOTICE + 5)

    assert game.phase is Phase.INTRO
    assert "alert" in sounds
    assert game.granny_x > still
    until(game, Phase.RUN)
    assert game.level == 0


def test_a_tap_is_a_hop_and_holding_jumps_higher():
    def peak(hold_steps: int) -> float:
        game = running()
        game.press()
        highest = 0.0
        for step in range(60):
            if step == hold_steps:
                game.release()
            game._fall()
            highest = min(highest, game.wolf_y)
        return -highest

    tap, held = peak(1), peak(g.MAX_HOLD_STEPS)

    assert 15 < tap < 30
    assert held > tap + 12


def test_jumping_only_works_from_the_ground():
    game = running()

    assert game.press() == ["jump"]
    game._fall()
    assert game.press() == []


def test_hitting_an_obstacle_crashes():
    game = running()
    game.obstacles = [Obstacle("bricks", game.wolf_x + 10)]

    sounds = game.step()

    assert game.phase is Phase.CRASH
    assert "crash" in sounds


def test_a_crash_sends_you_back_to_the_start_of_the_level_not_the_game():
    game = running(level=1)
    game.progress = 0.8
    game._enter(Phase.CRASH)

    game.press()
    assert game.phase is Phase.CRASH  # too soon, so a mashed button doesn't skip it

    run_steps(game, g.CRASH_PAUSE + 1)
    game.press()

    assert (game.phase, game.level, game.progress, game.tries) == (Phase.RUN, 1, 0, 2)


def test_levels_get_faster_and_trickier():
    starts = [level.speeds[0] for level in LEVELS]
    doubles = [level.doubles for level in LEVELS]

    assert starts == sorted(starts)
    assert doubles == sorted(doubles)
    assert [level.name for level in LEVELS] == [
        "STRAW HUT",
        "STICK HOUSE",
        "BRICK HOUSE",
    ]


def test_speed_ramps_up_through_a_level():
    game = running()
    slow = game.speed
    game.progress = 1.0

    assert game.speed > slow


def test_obstacles_sometimes_come_in_pairs_on_later_levels():
    game = running(level=2)
    pairs = 0
    for _ in range(200):
        game.obstacles.clear()
        game.gap = 0
        game._spawn(game.current)
        pairs += len(game.obstacles) == 2

    assert pairs > 20


def test_first_level_never_doubles_up():
    game = running(level=0)
    for _ in range(100):
        game.obstacles.clear()
        game.gap = 0
        game._spawn(game.current)
        assert len(game.obstacles) == 1


@pytest.mark.parametrize("level", range(len(LEVELS)))
def test_autopilot_can_clear_every_level(level):
    """The obstacles are always beatable, pairs included."""
    game = running(level=level, demo=True)

    sounds = until(game, Phase.ARRIVE)

    assert "crash" not in sounds


def test_straw_and_sticks_blow_down_and_grandma_runs_on():
    game = running(level=0)
    game.progress = 1.0

    sounds = until(game, Phase.FLEE)
    sounds += until(game, Phase.RUN)

    assert game.level == 1
    for beat in ("huff", "puff", "crumble", "alert"):
        assert beat in sounds


def test_the_brick_house_wont_blow_down_so_down_the_chimney_he_goes():
    game = running(level=2)
    game.progress = 1.0

    sounds = until(game, Phase.DONE)

    for beat in ("huff", "puff", "sad", "climb", "chomp", "burp", "lick", "static"):
        assert beat in sounds
    assert "crumble" not in sounds
    assert game.finished


def test_he_lands_on_the_chimney_before_dropping_in():
    game = running(level=2)
    game.house_x = g.HOUSE_STOPS_AT
    game._enter(Phase.CLIMB)

    for step in range(1, g.CLIMB_ARC + 1):
        game._climb(step)

    assert game.wolf_y == pytest.approx(-(len(LEVELS[2].house) - 1))
    assert game.house_x < game.wolf_x + 16 < game.house_x + len(LEVELS[2].house[0])


def test_camera_warms_up_once_he_heads_for_the_chimney():
    game = running(level=2)
    game.progress = 1.0

    until(game, Phase.FAIL)
    assert not game.wants_camera
    until(game, Phase.CLIMB)
    assert game.wants_camera


def test_host_can_skip_straight_to_the_brick_house():
    game = Game(rng=random.Random(1))

    game.skip_to_ending()
    until(game, Phase.ARRIVE)

    assert game.last_level


def test_banner_names_the_next_house_then_fades():
    game = running(level=1)

    assert game.banner_steps > 0
    run_steps(game, 61)
    assert game.banner_steps == 0


def test_banners_cheer_you_on_without_naming_the_next_house():
    from wolf_run.game_scene import banner

    lines = [banner(running(level=level)) for level in range(len(LEVELS))]

    assert lines[0] == "CATCH GRANDMA!"
    for line in lines:
        assert "HOUSE" not in line
        assert "HUT" not in line


def test_a_retry_skips_the_banner():
    game = running(level=1)
    game._enter(Phase.CRASH)
    run_steps(game, g.CRASH_PAUSE + 1)

    game.press()

    assert game.banner_steps == 0


def test_each_level_is_faster_than_the_last_one_ended():
    for easier, harder in pairwise(LEVELS):
        assert harder.speeds[0] > easier.speeds[1]
        assert harder.gaps[1] < easier.gaps[1]


def test_after_a_pair_the_next_obstacle_leaves_room_to_land():
    game = running(level=2)
    game.rng = random.Random(0)
    for _ in range(300):
        game.obstacles.clear()
        game.gap = 0
        game._spawn(game.current)
        if len(game.obstacles) == 2:
            pair_end = game.obstacles[1].x + game.obstacles[1].width
            next_at = game.obstacles[0].x + game.gap
            assert next_at - pair_end >= game.current.gaps[0]
