import pytest

from wolf_run import sprites


def test_every_sprite_and_glyph_is_well_formed():
    sprites.validate()


@pytest.mark.parametrize(
    "name", ["wolfA", "wolfB", "wolfJump", "wolfOpen", "wolfChomp", "wolfFat"]
)
def test_wolf_frames_share_one_size_so_they_swap_cleanly(name):
    grid = sprites.SPRITES[name]

    assert (len(grid[0]), len(grid)) == (32, 22)


def test_validate_catches_a_ragged_sprite(monkeypatch):
    monkeypatch.setitem(sprites.SPRITES, "broken", ["##", "###"])

    with pytest.raises(ValueError, match="ragged"):
        sprites.validate()


def test_validate_catches_a_stray_character(monkeypatch):
    monkeypatch.setitem(sprites.SPRITES, "broken", ["#x"])

    with pytest.raises(ValueError, match="unexpected"):
        sprites.validate()
