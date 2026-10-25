import json

import pytest

from wolf_run import card


def test_the_box_goes_around_the_card_with_some_room():
    corners = ((0.5, 0.25), (0.6, 0.25), (0.6, 0.55), (0.5, 0.55))
    left, top, width, height = card.box_around(corners, margin=0.1)
    assert (round(left, 3), round(top, 3), round(width, 3), round(height, 3)) == (
        0.49,
        0.22,
        0.12,
        0.36,
    )


def test_the_box_stays_inside_the_picture():
    assert card.box_around(((0.0, 0.0), (0.2, 0.0), (0.2, 0.3), (0.0, 0.3))) == (
        0.0,
        0.0,
        pytest.approx(0.23),
        pytest.approx(0.345),
    )


@pytest.mark.parametrize(
    "box", [[0.1, 0.2, 0.3], [0.9, 0.1, 0.2, 0.2], [0.1, 0.1, 0, 0.2], ["a", 0, 1, 1]]
)
def test_a_box_has_to_fit_the_picture(box):
    with pytest.raises(ValueError, match="box"):
        card.checked(box)


def test_a_spot_remembers_where_it_was_set(tmp_path):
    path = tmp_path / "card-spot.json"
    spot = card.CardSpot((0.4, 0.25, 0.15, 0.4), path)

    assert spot.set((0.1, 0.2, 0.3, 0.4))

    assert spot.box == (0.1, 0.2, 0.3, 0.4)
    assert json.loads(path.read_text()) == {"box": [0.1, 0.2, 0.3, 0.4]}
    assert card.CardSpot().set((0.1, 0.2, 0.3, 0.4))  # nowhere to save: still fine


def test_the_spot_comes_from_what_was_set_then_env(tmp_path, monkeypatch, capsys):
    state = tmp_path / "state"
    monkeypatch.setenv("WOLF_RUN_STATE", str(state / "place.json"))
    env = tmp_path / ".env"
    env.write_text("CARD_OUTLINE=0.4,0.25,0.15,0.4\n")
    monkeypatch.delenv("CARD_OUTLINE", raising=False)

    assert card.spot_from_env(env).box == (0.4, 0.25, 0.15, 0.4)
    card.spot_from_env(env).set((0.1, 0.2, 0.3, 0.4))
    assert card.spot_from_env(env).box == (0.1, 0.2, 0.3, 0.4)  # what the host set

    (state / "card-spot.json").write_text('{"box": [2, 2, 2, 2]}')
    assert card.spot_from_env(env).box == (
        0.4,
        0.25,
        0.15,
        0.4,
    )  # a bad file is skipped

    env.write_text("CARD_OUTLINE=0.9,0.9,0.5,0.5\n")
    assert card.spot_from_env(env).box is None
    assert "No card outline" in capsys.readouterr().err


def test_without_remembering_the_spot_is_not_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("WOLF_RUN_STATE", "off")
    spot = card.spot_from_env(tmp_path / "missing.env")
    assert spot.box is None
    assert spot.set((0.1, 0.2, 0.3, 0.4))
