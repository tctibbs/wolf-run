import json
from datetime import datetime
from pathlib import Path

import pytest

from conftest import FakeCanvas
from wolf_run import clock, control, pigs
from wolf_run.palette import NIGHT
from wolf_run.stages import Screen

HALLOWEEN_EVENING = datetime(2026, 10, 31, 21, 47)


def board(*pigs_on: str | None, owners=("olive", "teddy", "meatball")) -> dict:
    return {
        "houses": [
            {"pig": pig, "owner": owner}
            for pig, owner in zip(pigs_on, owners, strict=True)
        ]
    }


def test_a_house_counts_only_with_its_own_pig_on_it():
    state = board("olive", "meatball", None)

    assert pigs.pigs_home(state) == (True, False, False)
    assert pigs.pigs_home(board("unknown", "teddy", "meatball")) == (False, True, True)


@pytest.mark.parametrize("state", [None, {}, {"houses": []}, {"houses": "three"}])
def test_an_answer_that_isnt_three_houses_is_refused(state):
    with pytest.raises(ValueError):
        pigs.pigs_home(state)


def test_the_watch_keeps_its_last_good_answer():
    answers = [json.dumps(board("olive", None, "meatball")).encode(), b"not json"]

    def fetch(url: str) -> bytes:
        assert url == "http://pigs.local/state"
        return answers.pop(0)

    watch = pigs.PigWatch("http://pigs.local/", fetch=fetch)
    assert watch.home() == (False, False, False)
    assert watch.check()
    assert not watch.check()  # bad JSON
    assert watch.home() == (True, False, True)


def test_the_watch_survives_the_board_being_off():
    def fetch(url: str) -> bytes:
        raise OSError("Host is down")

    watch = pigs.PigWatch("http://pigs.local", fetch=fetch)
    assert not watch.check()
    assert watch.home() == (False, False, False)


def test_the_watch_asks_in_the_background_until_stopped():
    asked = []

    def fetch(url: str) -> bytes:
        asked.append(url)
        return json.dumps(board("olive", "teddy", "meatball")).encode()

    watch = pigs.PigWatch("http://pigs.local", fetch=fetch)
    watch.start()
    for _ in range(200):
        if watch.home() == pigs.ALL_UP:
            break
        import time

        time.sleep(0.01)
    watch.stop()
    assert watch.home() == pigs.ALL_UP
    assert asked


def test_the_watch_comes_from_pig_houses_url(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PIG_HOUSES_URL", raising=False)
    env = tmp_path / ".env"
    env.write_text("")
    assert pigs.watch_from_env(env) is None
    env.write_text("PIG_HOUSES_URL=http://192.168.1.60\n")
    watch = pigs.watch_from_env(env)
    assert watch is not None
    assert watch.url == "http://192.168.1.60/state"


def test_a_house_goes_up_from_the_ground_and_comes_back_down():
    building = pigs.Building()
    assert building.height(0, 0.0) == 0

    building.follow((True, False, False), 1.0)
    assert building.height(0, 1.0 + pigs.BUILD_SECONDS / 2) == pytest.approx(0.5)
    assert building.height(0, 1.0 + pigs.BUILD_SECONDS) == 1
    assert building.height(1, 5.0) == 0

    building.follow((False, False, False), 5.0)
    assert building.height(0, 5.0 + pigs.BUILD_SECONDS / 4) == pytest.approx(0.75)
    assert building.height(0, 10.0) == 0


def test_a_house_caught_halfway_turns_around_where_it_is():
    building = pigs.Building()
    building.follow((True, True, True), 0.0)
    halfway = pigs.BUILD_SECONDS / 2
    building.follow((False, True, True), halfway)

    assert building.height(0, halfway) == pytest.approx(0.5)
    assert building.height(0, halfway + pigs.BUILD_SECONDS / 4) == pytest.approx(0.25)


def ink_in_house(canvas: FakeCanvas, house: int) -> list[int]:
    """The rows inked where a house stands, above the ground's specks."""
    grid, x = clock.HOUSES[house]
    top = clock.GROUND_Y - len(grid)
    return [
        py
        for (px, py), color in canvas.pixels.items()
        if x <= px < x + len(grid[0])
        and top <= py < clock.GROUND_Y - 1
        and color == NIGHT.ink
    ]


def test_the_clock_builds_only_the_houses_whose_pigs_are_home():
    building = pigs.Building()
    building.follow((True, False, False), 0.0)
    built, bare = FakeCanvas(), FakeCanvas()

    clock.draw_clock(built, HALLOWEEN_EVENING, 10.0)
    clock.draw_clock(bare, HALLOWEEN_EVENING, 10.0, building=building)

    assert sorted(ink_in_house(bare, 0)) == sorted(ink_in_house(built, 0))
    assert ink_in_house(bare, 1) == []
    _, x = clock.HOUSES[1]
    assert bare.at(x, clock.GROUND_Y - 1) == NIGHT.dim  # the plot's corner stake


def test_a_half_built_house_shows_its_bottom_half():
    building = pigs.Building()
    building.follow(pigs.ALL_UP, 0.0)
    canvas = FakeCanvas()

    clock.draw_clock(
        canvas, HALLOWEEN_EVENING, pigs.BUILD_SECONDS / 2, building=building
    )

    grid, _ = clock.HOUSES[2]
    roof = clock.GROUND_Y - len(grid)
    assert min(ink_in_house(canvas, 2)) >= roof + len(grid) // 2 - 1


def test_the_screen_builds_while_asleep_and_shows_every_house_once_awake():
    screen = Screen(building=pigs.Building())
    asleep, awake = FakeCanvas(), FakeCanvas()

    screen.draw(asleep, HALLOWEEN_EVENING, 5.0)
    screen.prime(5.0)
    screen.draw(awake, HALLOWEEN_EVENING, 5.0)

    assert ink_in_house(asleep, 0) == []
    assert ink_in_house(awake, 0)


def test_the_state_says_which_pigs_are_home():
    screen = Screen()
    assert "pigs_home" not in control.state_of(screen)
    screen.building = pigs.Building()
    screen.building.follow((True, False, True), 0.0)

    assert control.state_of(screen)["pigs_home"] == [True, False, True]
