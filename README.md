# Wolf Run

[![Tests](https://github.com/tctibbs/wolf-run/actions/workflows/ci.yml/badge.svg)](https://github.com/tctibbs/wolf-run/actions/workflows/ci.yml)

I made Wolf Run for a Halloween escape room I hosted. It runs on a Raspberry Pi with
a small touchscreen that sits in the living room.

Most of the night it's a clock, with the Big Bad Wolf asleep in the corner. When it's
time, he wakes up and the screen asks for a button. Press it and you're the wolf,
chasing Grandma as she runs to the straw house, then the stick house, then the brick
house. It plays a lot like the Chrome dinosaur game: tap to hop, hold to jump higher,
and each house is faster than the last. Catch her and the screen cuts to a live
camera.

![The wolf wakes up](docs/images/wake-up.gif)

![Running and jumping](docs/images/run.gif)

![Huffing and puffing](docs/images/huff-and-puff.gif)

![Down the chimney](docs/images/brick-house.gif)

## Running it

```bash
uv sync
uv run wolf-run screen --windowed
```

Ctrl+P (Cmd+P on a Mac) wakes the wolf, then any key plays. Ctrl+E skips to the brick
house, Ctrl+R resets, and Ctrl+Q quits. `--primed` (or `WOLF_RUN_PRIMED=1`) starts with
the wolf already awake.

For the camera at the end, copy `.env.example` to `.env` and fill in your RTSP
camera. `uv run wolf-run camera-check` tells you if it's working.

## Power cuts

The screen remembers where it was: the clock, the wolf awake, the house the chase
reached, or the camera. After a power cut it starts right back there. If the chase was
on, the wolf is awake again and the next press picks up at the house they'd reached.
Ctrl+R puts it back to the clock. It keeps its place in
`~/.local/state/wolf-run/place.json` (or wherever `WOLF_RUN_STATE` says;
`WOLF_RUN_STATE=off` starts at the clock every time).

## On the Pi

`scripts/deploy-pi.sh` copies it to the Pi and installs two user services without
starting anything. `systemctl --user start wolf-run` puts it on the screen now, and
`systemctl --user enable wolf-run-boot` puts it there at every boot, even if another
app starts first. The Pi starts user services at boot only with lingering on
(`loginctl enable-linger`).

## Controlling it from another computer

The screen can also take the host's commands over the network, so a phone, a laptop,
or a Home Assistant button can wake the wolf without anyone touching the keyboard.
Turn it on with a port:

```bash
uv run wolf-run screen --control 8034
```

(or `WOLF_RUN_CONTROL_PORT=8034`). It listens on every network the Pi is on and
prints its address when it starts. Then:

- `GET /state` says where the screen is, like `{"stage": "game", "house": 2}`. The
  stage is `clock`, `primed`, `game`, or `camera`, and `house` (1 to 3) is only there
  during the game.
- `POST /prime` wakes the wolf, `POST /skip` skips to the brick house, and
  `POST /reset` goes back to the clock. They do the same as Ctrl+P, Ctrl+E, and
  Ctrl+R.

```bash
curl -X POST http://raspberrypi.local:8034/prime
```

There's no password, so only turn it on for a network your guests aren't on.

## Sprites

![All the sprites](docs/images/cast.png)

## Hardware

A Raspberry Pi 3, a 1024x600 touchscreen, a Reolink E1 Zoom camera, and a big red USB
button.
