#!/usr/bin/env bash
#
# Copy Wolf Run to the Pi and get it ready, without touching anything else there.
#
# Everything lands in ~/wolf-run with its own venv. The venv borrows the system
# PyQt5 from apt (building it on a Pi 3 isn't worth an afternoon). The camera's
# .env is copied only if the Pi doesn't already have one, and never printed.
# The service is installed but not started: it takes over the screen, so
# starting it is your call.
#
# Usage: scripts/deploy-pi.sh [user@host]    (default: WOLF_RUN_PI from .env)

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [ -f .env ]; then
  WOLF_RUN_PI="${WOLF_RUN_PI:-$(sed -n 's/^WOLF_RUN_PI=//p' .env)}"
fi
TARGET="${1:-${WOLF_RUN_PI:-raspberrypi.local}}"
ssh() { command ssh -o SetEnv=LC_ALL=C "$@"; }
say() { printf '\n== %s\n' "$1"; }

say "Copying the code to ${TARGET}:~/wolf-run"
COPYFILE_DISABLE=1 tar czf - --no-xattrs src deploy pyproject.toml README.md LICENSE 2>/dev/null \
  | ssh "$TARGET" 'mkdir -p ~/wolf-run && cd ~/wolf-run && tar xzf - 2>/dev/null; find . -name "._*" -delete'

if [ -f .env ] && ! ssh "$TARGET" 'test -f ~/wolf-run/.env'; then
  say "Copying the camera settings (first deploy only)"
  scp -q -o SetEnv=LC_ALL=C .env "$TARGET":wolf-run/.env
  ssh "$TARGET" 'chmod 600 ~/wolf-run/.env'
fi

say "Making sure the venv is ready"
ssh "$TARGET" 'set -e; cd ~/wolf-run
  if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
    /usr/bin/python3 -c "import PyQt5, pathlib; print(pathlib.Path(PyQt5.__file__).resolve().parent.parent)" \
      > "$(echo .venv/lib/python3.*/site-packages)/zz-system-site.pth"
    .venv/bin/python -m pip install -q --disable-pip-version-check -e .
  fi
  .venv/bin/python -c "import PyQt5.QtWidgets, cv2, wolf_run; print(\"imports ok\")"'

say "Installing the service (not starting it)"
ssh "$TARGET" 'mkdir -p ~/.config/systemd/user
  cp ~/wolf-run/deploy/wolf-run.service ~/.config/systemd/user/
  systemctl --user daemon-reload
  if systemctl --user is-active --quiet wolf-run; then
    systemctl --user restart wolf-run && echo "restarted the running screen"
  else
    echo "installed; start it with: systemctl --user start wolf-run"
  fi'
