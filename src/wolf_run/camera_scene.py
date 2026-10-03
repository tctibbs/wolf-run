"""Stage three's on-screen display: the security-camera look over the live feed.

With a live picture the overlay is drawn on a transparent layer. Without one
(still connecting, or the stream dropped) it draws static and NO SIGNAL instead.
"""

from datetime import datetime

from wolf_run.clock import H, W
from wolf_run.palette import NIGHT
from wolf_run.pixels import Canvas, text, text_width

OSD = "#e6e6e6"
REC = NIGHT.red
LABEL = "CAM 1  BASEMENT"


def draw_camera_osd(canvas: Canvas, now: datetime, t: float, live: bool) -> None:
    if not live:
        canvas.noise(0, 0, W, H, seed=int(t * 15), lo=16, hi=46)
        message = "NO SIGNAL"
        text(canvas, message, (W - text_width(message, 2)) // 2, 68, OSD, 2)
    text(canvas, LABEL, 8, 8, OSD)
    if int(t * 2) % 2 == 0:
        canvas.fill(222, 8, 5, 5, REC)
    text(canvas, "REC", 230, 8, OSD)
    text(canvas, f"{now:%m-%d-%Y %H:%M:%S}", 8, H - 13, OSD)
