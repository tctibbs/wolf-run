# Wolf Run

A little party screen for a Halloween escape room, built for a Raspberry Pi with a
touchscreen.

Most of the night it's just a clock in the corner of the living room. Then something
in the game sets it off, and the clock turns into a retro runner, the kind you play
when the internet goes down. You're the Big Bad Wolf. Jump the straw, the sticks and
the bricks, make it all the way to Grandma's house, and... well, he eats her. Then
the screen crackles into static and cuts to a live feed from the basement camera.

## The three stages

| Stage | What's on screen | Status |
|---|---|---|
| 1. Clock | The time, minding its own business | Not built yet |
| 2. Wolf Run | The runner game, ending with Grandma as dinner | Sprites done, game next |
| 3. The basement | A live camera feed | Camera check works |

## Getting started

You'll need [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env    # then fill in your camera's address and login
uv run wolf-run camera-check
```

`camera-check` grabs one frame from the camera and saves it to
`snapshots/camera-check.jpg`, so you can see it's really working.

## Private stuff stays private

The camera's address and login live in `.env`, which git ignores. The repo only has
`.env.example`, with made-up values. Snapshots are ignored too.

## Hardware

- Raspberry Pi 3 with a 1024x600 touchscreen
- Reolink E1 Zoom camera, read over RTSP (the small "sub" stream is plenty for a Pi 3)
- Home Assistant to kick things off and to override anything that gets stuck

## Development

```bash
uv run pytest
uv run ruff check
uv run ruff format
```
