import errno
import http.client
import json
import queue
import urllib.error
import urllib.request
from datetime import datetime

import pytest

from wolf_run import card, control, ui
from wolf_run.stages import Screen, Stage

HALLOWEEN_EVENING = datetime(2026, 10, 31, 21, 47)


def call(url, method="GET", body=None):
    """Send a request and return the status code and the JSON that came back."""
    request = urllib.request.Request(url, data=body, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


@pytest.fixture
def served():
    """The real server on a free port, with a status the test can change."""
    commands = queue.Queue()
    status = {"stage": "game", "house": 2}
    server = control.start(0, commands, lambda: dict(status), host="127.0.0.1")
    yield f"http://127.0.0.1:{server.server_port}", commands, status
    server.shutdown()
    server.server_close()


def drained(commands):
    names = []
    while not commands.empty():
        names.append(commands.get_nowait())
    return names


def test_state_reports_the_status_it_is_given(served):
    url, _, status = served

    assert call(f"{url}/state") == (200, {"stage": "game", "house": 2})

    status.pop("house")
    status["stage"] = "camera"
    assert call(f"{url}/state") == (200, {"stage": "camera"})


def test_state_is_json(served):
    url, _, _ = served

    with urllib.request.urlopen(f"{url}/state", timeout=5) as response:
        assert response.headers["Content-Type"] == "application/json"


def test_state_ignores_a_trailing_slash_and_a_query(served):
    url, _, _ = served

    assert call(f"{url}/state/?from=phone")[0] == 200


@pytest.mark.parametrize("name", control.COMMANDS)
def test_each_command_is_queued_for_the_window(served, name):
    url, commands, _ = served

    assert call(f"{url}/{name}", "POST") == (200, {"ok": name})
    assert drained(commands) == [name]


def test_a_command_with_a_body_still_works(served):
    url, commands, _ = served

    assert call(f"{url}/skip", "POST", b'{"by": "host"}') == (200, {"ok": "skip"})
    assert drained(commands) == ["skip"]


def test_a_nonsense_body_length_is_ignored(served):
    url, commands, _ = served
    connection = http.client.HTTPConnection(url.removeprefix("http://"), timeout=5)
    connection.putrequest("POST", "/reset")
    connection.putheader("Content-Length", "lots")
    connection.endheaders()

    response = connection.getresponse()

    assert (response.status, json.loads(response.read())) == (200, {"ok": "reset"})
    connection.close()
    assert drained(commands) == ["reset"]


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/"), ("GET", "/prime"), ("POST", "/state"), ("POST", "/quit")],
)
def test_unknown_paths_are_a_json_404(served, method, path):
    url, commands, _ = served

    code, body = call(f"{url}{path}", method, b"" if method == "POST" else None)

    assert code == 404
    assert "/state" in body["error"]
    assert drained(commands) == []


def test_requests_are_not_logged(served, capsys):
    url, _, _ = served

    call(f"{url}/state")
    call(f"{url}/nope")

    out, err = capsys.readouterr()
    assert (out, err) == ("", "")


def test_a_busy_port_says_so(served):
    url, commands, _ = served
    port = int(url.rsplit(":", 1)[1])

    with pytest.raises(RuntimeError, match=f"Port {port} is busy"):
        control.start(port, commands, dict, host="127.0.0.1")


def test_other_listening_problems_are_explained(mocker):
    mocker.patch.object(
        control,
        "ThreadingHTTPServer",
        side_effect=OSError(errno.EACCES, "Permission denied"),
    )

    with pytest.raises(RuntimeError, match="Couldn't listen on port 80: Permission"):
        control.start(80, queue.Queue(), dict)


def test_prime_wakes_the_wolf():
    screen = Screen()

    control.apply_command(screen, "prime", 12.5)

    assert (screen.stage, screen.since) == (Stage.PRIMED, 12.5)


def test_skip_goes_to_the_brick_house():
    screen = Screen()

    control.apply_command(screen, "skip", 3.0)

    assert screen.stage is Stage.GAME
    assert screen.game.last_level


def test_reset_goes_back_to_the_clock():
    screen = Screen()
    control.apply_command(screen, "skip", 3.0)

    control.apply_command(screen, "reset", 9.0)

    assert (screen.stage, screen.since, screen.game) == (Stage.CLOCK, 9.0, None)


def test_an_unknown_command_does_nothing():
    screen = Screen()

    control.apply_command(screen, "explode", 1.0)

    assert screen == Screen()


def test_state_names_the_stage_and_the_house_only_while_playing():
    screen = Screen(seed=1)
    assert control.state_of(screen) == {"stage": "clock"}

    screen.prime(0.0)
    assert control.state_of(screen) == {"stage": "primed"}

    screen.press(1.0)
    assert control.state_of(screen) == {"stage": "game", "house": 1}

    screen.skip_to_ending(2.0)
    assert control.state_of(screen) == {"stage": "game", "house": 3}

    screen.stage = Stage.CAMERA
    assert control.state_of(screen) == {"stage": "camera"}


def test_publish_updates_the_shared_dict_in_place():
    status = {"stage": "game", "house": 3}
    shared = status

    control.publish(status, Screen(stage=Stage.CAMERA))

    assert shared is status
    assert status == {"stage": "camera"}


def test_lan_address_falls_back_to_this_computer(mocker):
    probe = mocker.patch("wolf_run.control.socket.socket").return_value
    probe.connect.side_effect = OSError("no network")

    assert control.lan_address() == "127.0.0.1"
    probe.close.assert_called_once()


def test_lan_address_is_the_route_out(mocker):
    probe = mocker.patch("wolf_run.control.socket.socket").return_value
    probe.getsockname.return_value = ("192.168.1.23", 50000)

    assert control.lan_address() == "192.168.1.23"


@pytest.fixture
def app():
    return ui.ensure_app(offscreen=True)


def window_with(commands, status=None):
    return ui.ScreenWindow(
        now=lambda: HALLOWEEN_EVENING,
        seconds=lambda: 100.0,
        commands=commands,
        status=status,
    )


def test_window_drains_queued_commands_on_its_next_frame(app):
    commands = queue.Queue()
    window = window_with(commands)

    commands.put("prime")
    assert window.screen.stage is Stage.CLOCK
    window.tick()
    assert window.screen.stage is Stage.PRIMED
    assert window.status == {"stage": "primed"}

    commands.put("skip")
    window.tick()
    assert window.status == {"stage": "game", "house": 3}

    commands.put("reset")
    commands.put("explode")
    window.tick()
    assert window.status == {"stage": "clock"}
    assert commands.empty()


def test_window_fills_in_the_status_it_is_handed(app):
    status = {"stage": "primed"}

    window = window_with(queue.Queue(), status)

    assert window.status is status
    assert status == {"stage": "clock"}


def test_a_host_key_shows_up_in_the_status_too(app):
    from PyQt5.QtCore import QEvent, Qt
    from PyQt5.QtGui import QKeyEvent

    window = window_with(None)

    window.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_E, Qt.ControlModifier))
    window.tick()

    assert window.status == {"stage": "game", "house": 3}


def test_a_post_reaches_the_screen_and_shows_up_in_state(app):
    commands = queue.Queue()
    window = window_with(commands)
    server = control.start(0, commands, lambda: dict(window.status), host="127.0.0.1")
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert call(f"{url}/state") == (200, {"stage": "clock"})

        call(f"{url}/prime", "POST")
        window.tick()

        assert call(f"{url}/state") == (200, {"stage": "primed"})
    finally:
        server.shutdown()
        server.server_close()


class Clock:
    def __init__(self) -> None:
        self.t = 50.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def sighted():
    """The server with card sightings, on a clock the test moves."""
    clock = Clock()
    sightings = control.Sightings(clock)
    server = control.start(
        0, queue.Queue(), dict, host="127.0.0.1", sightings=sightings
    )
    yield f"http://127.0.0.1:{server.server_port}", sightings, clock
    server.shutdown()
    server.server_close()


CARD = {
    "found": True,
    "corners": [[640, 180], [768, 180], [768, 372], [640, 372]],
    "frame": [1280, 720],
}


def test_a_card_report_says_where_the_card_is(sighted):
    url, sightings, clock = sighted
    assert sightings.seen() is None

    code, body = call(f"{url}/card", "POST", json.dumps(CARD).encode())

    assert (code, body) == (200, {"ok": "card"})
    seen = [tuple(round(v, 4) for v in corner) for corner in sightings.seen()]
    assert seen == [(0.5, 0.25), (0.6, 0.25), (0.6, 0.5167), (0.5, 0.5167)]
    clock.t += control.STALE_SECONDS + 0.1
    assert sightings.seen() is None  # no word for a while: it's gone


def test_a_lost_card_report_clears_it(sighted):
    url, sightings, _ = sighted
    call(f"{url}/card", "POST", json.dumps(CARD).encode())

    call(f"{url}/card", "POST", b'{"found": false}')

    assert sightings.seen() is None


@pytest.mark.parametrize(
    ("body", "says"),
    [
        (b"not json", "Send JSON"),
        (b"[]", "whether the card was found"),
        (b'{"found": "yes"}', "whether the card was found"),
        (b'{"found": true, "corners": [[1, 2]] , "frame": [10, 10]}', "four corners"),
        (
            b'{"found": true, "corners": [[1, 2], [1, 2], [1, 2], [1]], '
            b'"frame": [10, 10]}',
            "[x, y]",
        ),
        (b'{"found": true, "corners": [], "frame": [0, 10]}', "frame's size"),
        (b'{"found": true, "corners": [], "frame": [true, 10]}', "frame's size"),
    ],
)
def test_a_bad_card_report_says_why(sighted, body, says):
    url, sightings, _ = sighted
    code, answer = call(f"{url}/card", "POST", body)
    assert code == 400 and says in answer["error"]
    assert sightings.seen() is None


def test_no_sightings_means_no_card_route(served):
    url, commands, _ = served
    code, _ = call(f"{url}/card", "POST", json.dumps(CARD).encode())
    assert code == 404
    assert commands.empty()


@pytest.fixture
def spotted():
    """The server with card sightings and a card spot."""
    clock = Clock()
    sightings = control.Sightings(clock)
    spot = card.CardSpot((0.4, 0.25, 0.15, 0.4))
    server = control.start(
        0, queue.Queue(), dict, host="127.0.0.1", sightings=sightings, spot=spot
    )
    yield f"http://127.0.0.1:{server.server_port}", sightings, spot
    server.shutdown()
    server.server_close()


def test_the_card_spot_moves_to_where_the_card_is(spotted):
    url, sightings, spot = spotted
    code, answer = call(f"{url}/card-spot", "POST", b"")
    assert code == 409 and "can't see the card" in answer["error"]
    assert spot.box == (0.4, 0.25, 0.15, 0.4)

    sightings.report(((0.5, 0.25), (0.6, 0.25), (0.6, 0.55), (0.5, 0.55)))
    code, answer = call(f"{url}/card-spot", "POST", b"")

    assert code == 200 and answer["ok"] == "card-spot"
    assert spot.box == card.box_around(sightings.seen())
    assert answer["box"] == [round(v, 4) for v in spot.box]


def test_the_card_spot_can_be_set_outright(spotted):
    url, _, spot = spotted
    code, _ = call(f"{url}/card-spot", "POST", b'{"box": [0.1, 0.2, 0.3, 0.4]}')
    assert code == 200 and spot.box == (0.1, 0.2, 0.3, 0.4)
    for bad in (b'{"box": [2, 2, 2, 2]}', b"[1]", b"nope"):
        code, _ = call(f"{url}/card-spot", "POST", bad)
        assert code == 400, bad
    assert spot.box == (0.1, 0.2, 0.3, 0.4)


def test_state_says_whether_the_card_reads(spotted):
    url, sightings, _ = spotted
    assert call(f"{url}/state")[1]["card"] == "waiting"
    sightings.report(((0.5, 0.25), (0.6, 0.25), (0.6, 0.55), (0.5, 0.55)))
    assert call(f"{url}/state")[1]["card"] == "reading"
