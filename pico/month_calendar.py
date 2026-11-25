# Simple month calendar for the Inky Frame launcher (button A).
#
# It uses your settings in weather.py (location, time zone, Hijri date) and
# the weather app's fonts, so the two screens look alike. Today's date comes
# from the same weather service the weather app uses, so it is always the
# local date for your time zone.

# ---- Settings ----
# First day of the week: "Sunday", "Monday" or "Saturday"
WEEK_START = "Sunday"
# ------------------

import gc
import time

graphics = None
WIDTH = None
HEIGHT = None
UPDATE_INTERVAL = 60 * 24

import weather as _w        # your settings, and the weather app's drawing code
_app = _w._app

_today = None               # (year, month, day, hijri text or None)


def _setup():
    _w.graphics = graphics
    _w.WIDTH = WIDTH
    _w.HEIGHT = HEIGHT
    _w._share()


def _fetch_now():
    """Local date and time ('YYYY-MM-DDTHH:MM') and the UTC offset in seconds."""
    a = _app
    url = ("https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}"
           "&current=weather_code&forecast_days=1&timezone={}").format(
               a.LATITUDE, a.LONGITUDE, a.TIMEZONE.replace("/", "%2F"))
    last = None
    for attempt in range(4):
        gc.collect()
        try:
            a.ensure_wifi()                   # wait for Wi-Fi (up to 30 s) like the weather app
            r = a.requests.get(url, timeout=30)
            try:
                if r.status_code != 200:
                    raise RuntimeError("HTTP {}".format(r.status_code))
                a._remember_date(r)       # the server's exact clock
                data = r.json()
            finally:
                r.close()
            offset = data.get("utc_offset_seconds", 0)
            return a.local_now(data["current"]["time"], offset), offset
        except Exception as e:
            last = e
            print("Date attempt {} failed: {}".format(attempt + 1, e))
            time.sleep(5 * (attempt + 1))     # give the network a little longer each time
    raise RuntimeError("Could not get today's date: {}".format(last))


def update():
    global _today, UPDATE_INTERVAL
    _setup()
    now, offset = _fetch_now()
    y, m, d = int(now[0:4]), int(now[5:7]), int(now[8:10])
    minute = int(now[11:13]) * 60 + int(now[14:16])
    wait = 1440 - minute + 1                  # just after midnight
    hijri = None
    try:
        p = _app.prayer_info(now, offset)     # same Hijri date as the weather screen
        hijri = p.get("hijri")
        maghrib = p["times"][4]
        if _app.HIJRI_FROM_MAGHRIB and not p["tomorrow"] and maghrib is not None and maghrib > minute:
            wait = min(wait, maghrib - minute + 1)   # the Hijri date changes at Maghrib
    except Exception as e:
        print("No Hijri date:", e)
    _today = (y, m, d, hijri)
    # The frame's wake-up timer counts to 255 minutes at most, so check in
    # every 4 hours anyway; the last wait of the day lands just after midnight
    UPDATE_INTERVAL = max(1, min(wait, 240))
    print("Calendar: {} - next update in {} min".format(now, UPDATE_INTERVAL))


def _draw_month():
    a = _app
    MX, MY, MF, text = a.MX, a.MY, a.MF, a.draw_text
    y, m, d, hijri = _today

    graphics.set_pen(a.WHITE)
    graphics.clear()

    # Header: month and year on the left, today (and its Hijri date) on the right
    graphics.set_pen(a.BLACK)
    graphics.rectangle(0, 0, WIDTH, MY(54))
    text("{} {}".format(a.MONTHS_FULL[m - 1], y), MX(20), MY(4), MF(34), a.WHITE, bold=True, bg=a.BLACK)
    first = a._days_from_civil(y, m, 1)                    # days since 1 Jan 1970 (a Thursday)
    weekday = (first + d - 1 + 4) % 7                      # 0 = Sunday
    today = "{}, {} {}".format(a.DAYS[weekday], d, a.MONTHS_FULL[m - 1])
    if hijri:
        text(today, WIDTH - MX(20), MY(5), MF(17), a.WHITE, right=True, bg=a.BLACK)
        text(hijri, WIDTH - MX(20), MY(27), MF(17), a.GREEN, right=True, bg=a.BLACK)
        right_w = max(a.text_width(today, MF(17)), a.text_width(hijri, MF(17)))
    else:
        right_w = text(today, WIDTH - MX(20), MY(14), MF(20), a.WHITE, right=True, bg=a.BLACK)
    a.draw_battery(WIDTH - MX(20) - right_w - MX(12), MY(27))

    # Weekday names
    start = {"Monday": 1, "Saturday": 6}.get(WEEK_START, 0)
    col = (WIDTH - MX(40)) // 7
    x0 = (WIDTH - col * 7) // 2
    for i in range(7):
        text(a.DAYS[(start + i) % 7][:3], x0 + i * col + col // 2, MY(64), MF(22),
             a.BLACK, bold=True, center=True)
    graphics.set_pen(a.BLACK)
    graphics.rectangle(MX(20), MY(96), WIDTH - MX(40), 2)

    # The days, with today in a red circle
    nm, ny = (m + 1, y) if m < 12 else (1, y + 1)
    days_in = a._days_from_civil(ny, nm, 1) - first
    lead = ((first + 4) % 7 - start) % 7                   # blank boxes before the 1st
    rows = (lead + days_in + 6) // 7
    top = MY(102)
    rh = (HEIGHT - MY(6) - top) // rows
    size = MF(34) if rows <= 5 else MF(30)
    for n in range(1, days_in + 1):
        cell = lead + n - 1
        cx = x0 + (cell % 7) * col + col // 2
        cy = top + (cell // 7) * rh + rh // 2
        fg, bg = a.BLACK, a.WHITE
        if n == d:
            graphics.set_pen(a.RED)
            graphics.circle(cx, cy, int(min(col, rh) * 0.42))
            fg, bg = a.WHITE, a.RED
        text(str(n), cx, cy - int(size * 0.62), size, fg, bold=True, center=True, bg=bg)


def draw():
    a = _app
    _setup()
    gc.collect()
    if a._vector is None:
        a._vector = a._has_vector_font(a._vfont())
    try:
        _draw_month()
    except MemoryError:
        if a.FONT != "original" or a._bmp_failed:
            raise
        # Not enough memory for the pre-rendered font: redraw with the built-in one
        a._bmp_failed = True
        a._bmp_close()
        gc.collect()
        _draw_month()
    a._bmp_close()
    gc.collect()
    graphics.update()
