import cv2
import numpy as np
import pytest

from wolf_run import camera


class FakeCapture:
    def __init__(self, opened=True, frame=None, fps=15.0):
        self.opened = opened
        self.frame = frame
        self.fps = fps
        self.released = False

    def isOpened(self):  # noqa: N802 - mirrors OpenCV
        return self.opened

    def read(self):
        return (self.frame is not None, self.frame)

    def get(self, prop_id):
        assert prop_id == cv2.CAP_PROP_FPS
        return self.fps

    def release(self):
        self.released = True


def ticking_clock(*times):
    values = iter(times)
    return lambda: next(values)


def test_check_stream_reports_the_first_frame():
    capture = FakeCapture(frame=np.zeros((480, 640, 3), dtype=np.uint8))

    result = camera.check_stream(
        "rtsp://example", open_fn=lambda url: capture, clock=ticking_clock(10.0, 11.5)
    )

    assert (result.width, result.height, result.fps) == (640, 480, 15.0)
    assert result.seconds_to_first_frame == pytest.approx(1.5)
    assert capture.released


def test_check_stream_explains_a_stream_that_will_not_open():
    capture = FakeCapture(opened=False)

    with pytest.raises(camera.StreamError, match="Couldn't open"):
        camera.check_stream("rtsp://example", open_fn=lambda url: capture)
    assert capture.released


def test_check_stream_explains_a_stream_with_no_picture():
    capture = FakeCapture(frame=None)

    with pytest.raises(camera.StreamError, match="no picture"):
        camera.check_stream("rtsp://example", open_fn=lambda url: capture)
    assert capture.released


def test_open_capture_asks_for_tcp_video_with_timeouts(mocker, monkeypatch):
    monkeypatch.delenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", raising=False)
    video_capture = mocker.patch("wolf_run.camera.cv2.VideoCapture")

    camera.open_capture("rtsp://example")

    url, backend, params = video_capture.call_args.args
    options = camera.os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"]
    assert (url, backend) == ("rtsp://example", cv2.CAP_FFMPEG)
    assert cv2.CAP_PROP_OPEN_TIMEOUT_MSEC in params
    assert cv2.CAP_PROP_READ_TIMEOUT_MSEC in params
    assert "rtsp_transport;tcp" in options
    assert "allowed_media_types;video" in options


def test_open_capture_respects_options_already_set(mocker, monkeypatch):
    monkeypatch.setenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;udp")
    mocker.patch("wolf_run.camera.cv2.VideoCapture")

    camera.open_capture("rtsp://example")

    assert camera.os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] == "rtsp_transport;udp"


def test_save_snapshot_writes_an_image(tmp_path):
    frame = np.zeros((48, 64, 3), dtype=np.uint8)

    saved = camera.save_snapshot(frame, tmp_path / "shots" / "check.jpg")

    assert saved.exists()
    assert cv2.imread(str(saved)).shape == (48, 64, 3)


def test_save_snapshot_reports_a_failed_write(tmp_path, mocker):
    mocker.patch("wolf_run.camera.cv2.imwrite", return_value=False)

    with pytest.raises(OSError, match="Couldn't save"):
        camera.save_snapshot(np.zeros((4, 4, 3), dtype=np.uint8), tmp_path / "x.jpg")
