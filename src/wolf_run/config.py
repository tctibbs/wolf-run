"""Settings, read from the environment and a private .env file."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values

STREAM_PATHS = {"main": "h264Preview_01_main", "sub": "h264Preview_01_sub"}
REQUIRED_CAMERA_KEYS = ("CAMERA_HOST", "CAMERA_USER", "CAMERA_PASSWORD")


class ConfigError(Exception):
    """A setting is missing or doesn't make sense."""


@dataclass(frozen=True)
class CameraSettings:
    """Where the camera is and how to log in to it."""

    host: str
    user: str
    password: str
    rtsp_port: int = 554
    onvif_port: int = 8000
    stream: str = "sub"

    def rtsp_url(self) -> str:
        """The full stream URL, password included. Never print this one."""
        return self._url(quote(self.password, safe=""))

    def redacted_url(self) -> str:
        """The stream URL with the password hidden, safe to print."""
        return self._url("***")

    def _url(self, password: str) -> str:
        user = quote(self.user, safe="")
        path = STREAM_PATHS[self.stream]
        return f"rtsp://{user}:{password}@{self.host}:{self.rtsp_port}/{path}"


def read_env(path: Path = Path(".env")) -> dict[str, str]:
    """Merge the .env file with the real environment. The real environment wins."""
    values = {key: value for key, value in dotenv_values(path).items() if value}
    values.update(os.environ)
    return values


def camera_settings(env: Mapping[str, str]) -> CameraSettings:
    """Build camera settings, explaining exactly what's missing or wrong."""
    missing = [key for key in REQUIRED_CAMERA_KEYS if not env.get(key)]
    if missing:
        raise ConfigError(
            f"Missing {', '.join(missing)}. Copy .env.example to .env and fill it in."
        )
    stream = env.get("CAMERA_STREAM") or "sub"
    if stream not in STREAM_PATHS:
        raise ConfigError(f"CAMERA_STREAM should be 'sub' or 'main', not {stream!r}.")
    return CameraSettings(
        host=env["CAMERA_HOST"],
        user=env["CAMERA_USER"],
        password=env["CAMERA_PASSWORD"],
        rtsp_port=_port(env, "CAMERA_RTSP_PORT", 554),
        onvif_port=_port(env, "CAMERA_ONVIF_PORT", 8000),
        stream=stream,
    )


def _port(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if not raw:
        return default
    try:
        port = int(raw)
    except ValueError:
        raise ConfigError(f"{key} should be a number, not {raw!r}.") from None
    if not 0 < port < 65536:
        raise ConfigError(f"{key} should be between 1 and 65535, not {port}.")
    return port
