import numpy as np
import pytest

from wolf_run import camera, cli

ENV_FILE = "CAMERA_HOST=192.168.1.50\nCAMERA_USER=viewer\nCAMERA_PASSWORD=secret\n"


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    for key in ("CAMERA_HOST", "CAMERA_USER", "CAMERA_PASSWORD", "CAMERA_STREAM"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text(ENV_FILE)
    return path


def a_good_check():
    return camera.StreamCheck(
        width=640,
        height=480,
        fps=15.0,
        seconds_to_first_frame=1.25,
        frame=np.zeros((480, 640, 3), dtype=np.uint8),
    )


def test_camera_check_saves_a_snapshot_and_never_prints_the_password(
    env_file, tmp_path, mocker, capsys
):
    check = mocker.patch(
        "wolf_run.cli.camera.check_stream", return_value=a_good_check()
    )
    snapshot = tmp_path / "check.jpg"

    code = cli.main(
        ["camera-check", "--env", str(env_file), "--snapshot", str(snapshot)]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert snapshot.exists()
    assert "640x480 picture after 1.2s at 15 fps" in out
    assert "secret" not in out
    assert check.call_args.args[0].endswith("/h264Preview_01_sub")


def test_camera_check_can_switch_to_the_main_stream(env_file, tmp_path, mocker):
    check = mocker.patch(
        "wolf_run.cli.camera.check_stream", return_value=a_good_check()
    )

    cli.main(
        [
            "camera-check",
            "--env",
            str(env_file),
            "--stream",
            "main",
            "--snapshot",
            str(tmp_path / "check.jpg"),
        ]
    )

    assert check.call_args.args[0].endswith("/h264Preview_01_main")


def test_camera_check_explains_missing_settings(tmp_path, monkeypatch, capsys):
    for key in ("CAMERA_HOST", "CAMERA_USER", "CAMERA_PASSWORD"):
        monkeypatch.delenv(key, raising=False)

    code = cli.main(["camera-check", "--env", str(tmp_path / "none.env")])

    assert code == 1
    assert "Copy .env.example to .env" in capsys.readouterr().err


def test_camera_check_explains_an_unreachable_camera(env_file, mocker, capsys):
    mocker.patch(
        "wolf_run.cli.camera.check_stream",
        side_effect=camera.StreamError("Couldn't open the stream."),
    )

    code = cli.main(["camera-check", "--env", str(env_file)])

    assert code == 1
    assert "RTSP is on in the Reolink app" in capsys.readouterr().err


def test_camera_check_explains_a_failed_snapshot(env_file, mocker, capsys):
    mocker.patch("wolf_run.cli.camera.check_stream", return_value=a_good_check())
    mocker.patch(
        "wolf_run.cli.camera.save_snapshot", side_effect=OSError("Couldn't save.")
    )

    code = cli.main(["camera-check", "--env", str(env_file)])

    assert code == 1
    assert "Couldn't save." in capsys.readouterr().err


@pytest.mark.parametrize(
    ("fps", "shown"), [(15.0, " at 15 fps"), (0.0, ""), (90000.0, "")]
)
def test_only_sensible_frame_rates_are_shown(fps, shown):
    assert cli._fps(fps) == shown


def test_screenshot_renders_the_requested_moment(tmp_path, mocker, capsys):
    save = mocker.patch("wolf_run.ui.save_snapshot", return_value=tmp_path / "s.png")

    code = cli.main(
        ["screenshot", "--at", "2026-10-31 21:47", "--seconds", "2.5", "--out", "s.png"]
    )

    assert code == 0
    out_path, when, seconds, _scene = save.call_args.args
    assert (str(out_path), when.hour, when.minute, seconds) == ("s.png", 21, 47, 2.5)
    assert "Saved" in capsys.readouterr().out


def test_screenshot_explains_a_failed_save(mocker, capsys):
    mocker.patch("wolf_run.ui.save_snapshot", side_effect=OSError("Couldn't save."))

    assert cli.main(["screenshot"]) == 1
    assert "Couldn't save." in capsys.readouterr().err


def test_screen_opens_the_window(mocker):
    run = mocker.patch("wolf_run.ui.run", return_value=0)

    assert cli.main(["screen", "--windowed"]) == 0
    run.assert_called_once_with(True)


def test_screenshot_can_show_the_screen_primed(mocker):
    save = mocker.patch("wolf_run.ui.save_snapshot")

    cli.main(["screenshot", "--seconds", "6", "--primed", "2.5"])

    scene = save.call_args.args[3]
    assert scene.__self__.since == 3.5
