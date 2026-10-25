import json

from wolf_run import memory


def test_the_place_comes_back_as_it_was_saved(tmp_path):
    path = tmp_path / "state" / "place.json"

    assert memory.save(path, {"stage": "game", "house": 2})
    assert memory.load(path) == {"stage": "game", "house": 2}
    assert not (tmp_path / "state" / "place.json.part").exists()


def test_a_missing_or_broken_place_is_nothing(tmp_path):
    path = tmp_path / "place.json"
    assert memory.load(path) == {}

    path.write_text("{half a fil")
    assert memory.load(path) == {}

    path.write_text(json.dumps(["camera"]))
    assert memory.load(path) == {}


def test_a_place_that_cant_be_written_doesnt_stop_the_screen(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("not a folder")

    assert not memory.save(blocked / "place.json", {"stage": "clock"})


def test_where_the_place_lives(tmp_path):
    home = memory.path_from_env({})
    assert home is not None and home.name == "place.json" and "~" not in str(home)
    elsewhere = tmp_path / "here.json"
    assert memory.path_from_env({memory.ENV: str(elsewhere)}) == elsewhere
    assert memory.path_from_env({memory.ENV: " Off "}) is None
