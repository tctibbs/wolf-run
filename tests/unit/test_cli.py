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
    run.assert_called_once_with(True, False)


def test_screen_can_start_primed(mocker, monkeypatch):
    monkeypatch.delenv("WOLF_RUN_PRIMED", raising=False)
    run = mocker.patch("wolf_run.ui.run", return_value=0)

    cli.main(["screen", "--primed"])

    run.assert_called_once_with(False, True)


def test_the_service_can_prime_it_with_an_environment_variable(mocker, monkeypatch):
    run = mocker.patch("wolf_run.ui.run", return_value=0)

    monkeypatch.setenv("WOLF_RUN_PRIMED", "1")
    cli.main(["screen"])
    monkeypatch.setenv("WOLF_RUN_PRIMED", "0")
    cli.main(["screen"])

    assert [c.args for c in run.call_args_list] == [(False, True), (False, False)]


def test_screenshot_can_show_the_screen_primed(mocker):
    save = mocker.patch("wolf_run.ui.save_snapshot")

    cli.main(["screenshot", "--seconds", "6", "--primed", "2.5"])

    scene = save.call_args.args[3]
    assert scene.__self__.since == 3.5


@pytest.fixture
def local_control(mocker, monkeypatch):
    """Run --control on a free port on this computer only, and keep the servers."""
    from wolf_run import control

    monkeypatch.delenv("WOLF_RUN_CONTROL_PORT", raising=False)
    monkeypatch.delenv("WOLF_RUN_PRIMED", raising=False)
    real_start = control.start
    servers = []

    def start(port, commands, status):
        servers.append(real_start(0, commands, status, host="127.0.0.1"))
        return servers[-1]

    mocker.patch("wolf_run.control.start", side_effect=start)
    mocker.patch("wolf_run.control.lan_address", return_value="192.168.1.23")
    return servers


def test_control_listens_while_the_screen_runs_and_stops_after(
    local_control, mocker, capsys
):
    import json
    import urllib.request

    seen = {}

    def run(windowed, primed, commands, status):
        port = local_control[0].server_port
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/state") as reply:
            seen["state"] = json.loads(reply.read())
        urllib.request.urlopen(
            urllib.request.Request(f"http://127.0.0.1:{port}/skip", method="POST")
        ).close()
        seen["command"] = commands.get_nowait()
        return 0

    mocker.patch("wolf_run.ui.run", side_effect=run)

    assert cli.main(["screen", "--primed", "--control", "8034"]) == 0

    server = local_control[0]
    assert seen == {"state": {"stage": "primed"}, "command": "skip"}
    assert f"http://192.168.1.23:{server.server_port}" in capsys.readouterr().out
    assert server.socket.fileno() == -1  # closed once the screen quits


def test_control_port_can_come_from_the_environment(local_control, mocker, monkeypatch):
    run = mocker.patch("wolf_run.ui.run", return_value=0)
    monkeypatch.setenv("WOLF_RUN_CONTROL_PORT", "8034")

    cli.main(["screen"])

    assert len(local_control) == 1
    assert run.call_args.kwargs["status"] == {"stage": "clock"}


def test_the_flag_beats_the_environment(mocker, monkeypatch):
    run = mocker.patch("wolf_run.ui.run", return_value=0)
    monkeypatch.setenv("WOLF_RUN_CONTROL_PORT", "8034")
    monkeypatch.delenv("WOLF_RUN_PRIMED", raising=False)

    cli.main(["screen", "--control", "0"])

    run.assert_called_once_with(False, False)


def test_a_bad_control_port_in_the_environment_is_explained(
    mocker, monkeypatch, capsys
):
    run = mocker.patch("wolf_run.ui.run", return_value=0)
    monkeypatch.setenv("WOLF_RUN_CONTROL_PORT", "wolf")

    assert cli.main(["screen"]) == 1
    assert (
        "WOLF_RUN_CONTROL_PORT: 'wolf' isn't a port number" in capsys.readouterr().err
    )
    run.assert_not_called()


@pytest.mark.parametrize("port", ["-1", "70000", "eighty"])
def test_a_bad_control_flag_is_refused(port, capsys):
    with pytest.raises(SystemExit):
        cli.main(["screen", "--control", port])

    assert "isn't a port number" in capsys.readouterr().err


def test_a_busy_control_port_stops_before_the_screen_opens(mocker, capsys):
    run = mocker.patch("wolf_run.ui.run", return_value=0)
    mocker.patch(
        "wolf_run.control.start", side_effect=RuntimeError("Port 8034 is busy.")
    )

    assert cli.main(["screen", "--control", "8034"]) == 1
    assert "Port 8034 is busy." in capsys.readouterr().err
    run.assert_not_called()


def test_the_control_answers_with_the_remembered_place_from_the_start(
    tmp_path, monkeypatch
):
    from wolf_run import memory

    path = tmp_path / "place.json"
    monkeypatch.setenv("WOLF_RUN_STATE", str(path))
    memory.save(path, {"stage": "camera"})
    assert cli.first_status(False) == {"stage": "camera"}

    memory.save(path, {"stage": "game", "house": 3})
    assert cli.first_status(False) == {"stage": "primed"}

    monkeypatch.setenv("WOLF_RUN_STATE", "off")
    assert cli.first_status(True) == {"stage": "primed"}
    assert cli.first_status(False) == {"stage": "clock"}
