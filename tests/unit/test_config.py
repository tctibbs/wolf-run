import pytest

from wolf_run.config import CameraSettings, ConfigError, camera_settings, read_env

BASE_ENV = {
    "CAMERA_HOST": "192.168.1.50",
    "CAMERA_USER": "viewer",
    "CAMERA_PASSWORD": "change-me",
}


def test_camera_settings_uses_defaults_for_ports_and_stream():
    settings = camera_settings(BASE_ENV)

    assert settings == CameraSettings("192.168.1.50", "viewer", "change-me")
    assert (settings.rtsp_port, settings.onvif_port, settings.stream) == (
        554,
        8000,
        "sub",
    )


def test_camera_settings_reads_ports_and_stream():
    env = {
        **BASE_ENV,
        "CAMERA_RTSP_PORT": "8554",
        "CAMERA_ONVIF_PORT": "8080",
        "CAMERA_STREAM": "main",
    }

    settings = camera_settings(env)

    assert (settings.rtsp_port, settings.onvif_port, settings.stream) == (
        8554,
        8080,
        "main",
    )


def test_missing_settings_are_all_named():
    with pytest.raises(ConfigError, match="CAMERA_USER, CAMERA_PASSWORD"):
        camera_settings({"CAMERA_HOST": "192.168.1.50", "CAMERA_USER": ""})


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("CAMERA_STREAM", "huge", "'sub' or 'main'"),
        ("CAMERA_RTSP_PORT", "five", "should be a number"),
        ("CAMERA_ONVIF_PORT", "70000", "between 1 and 65535"),
    ],
)
def test_bad_values_are_explained(key, value, message):
    with pytest.raises(ConfigError, match=message):
        camera_settings({**BASE_ENV, key: value})


def test_rtsp_url_escapes_awkward_passwords():
    settings = CameraSettings("192.168.1.50", "viewer", "p@ss:w/rd")

    assert settings.rtsp_url() == (
        "rtsp://viewer:p%40ss%3Aw%2Frd@192.168.1.50:554/h264Preview_01_sub"
    )


def test_redacted_url_hides_the_password():
    settings = CameraSettings("192.168.1.50", "viewer", "secret", stream="main")

    url = settings.redacted_url()

    assert "secret" not in url
    assert url == "rtsp://viewer:***@192.168.1.50:554/h264Preview_01_main"


def test_read_env_merges_file_with_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("CAMERA_HOST=from-file\nCAMERA_USER=viewer\nCAMERA_PASSWORD=\n")
    monkeypatch.setenv("CAMERA_HOST", "from-environment")

    values = read_env(env_file)

    assert values["CAMERA_HOST"] == "from-environment"
    assert values["CAMERA_USER"] == "viewer"
    assert "CAMERA_PASSWORD" not in values


def test_read_env_without_a_file_uses_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("CAMERA_USER", "viewer")

    values = read_env(tmp_path / "missing.env")

    assert values["CAMERA_USER"] == "viewer"
