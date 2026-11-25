# Date + Weather, for the Inky Frame launcher (button C).
#
#   Left:  today's day name, a big date, the month and year, the Hijri date,
#          and a small calendar of this month with today circled
#   Right: the weather now with sunrise and sunset, details, today's prayer
#          times, and a 4-day forecast
#
# It uses your settings in weather.py and the weather app's data, fonts and
# icons, so it matches the other screens.

# ---- Settings ----
# First day of the week in the small calendar: "Sunday", "Monday" or "Saturday"
WEEK_START = "Sunday"
# ------------------

import gc

graphics = None
WIDTH = None
HEIGHT = None
UPDATE_INTERVAL = 60

import weather as _w        # your settings, and the weather app's code
_app = _w._app


def _setup():
    _w.graphics = graphics
    _w.WIDTH = WIDTH
    _w.HEIGHT = HEIGHT
    _w._share()


def update():
    global UPDATE_INTERVAL
    _setup()
    a = _app
    a.update()                       # weather, alerts, prayer times (for the Hijri date)
    w = a.weather
    if w is not None and w.get("prayer") is None:
        try:                         # the Hijri date comes with the prayer times
            w["prayer"] = a.prayer_info(a.local_now(w["now"], w["utc_offset"]), w["utc_offset"])
        except Exception as e:
            print("No Hijri date:", e)
    UPDATE_INTERVAL = a.UPDATE_INTERVAL


# ---------------------------------------------------------------------------

def _date_panel(w, now, x0, x1):
    """Day name, big date, month and year, Hijri date, small calendar."""
    a = _app
    MX, MY, MF, text = a.MX, a.MY, a.MF, a.draw_text
    cx = (x0 + x1) // 2
    y, m, d = int(now[0:4]), int(now[5:7]), int(now[8:10])
    first = a._days_from_civil(y, m, 1)                     # days since 1 Jan 1970 (a Thursday)
    weekday = (first + d - 1 + 4) % 7                       # 0 = Sunday

    text(a.DAYS[weekday], cx, MY(6), MF(36), a.BLACK, center=True)
    text("%02d" % d, cx, MY(40), MF(96), a.BLACK, bold=True, center=True)
    text("{} {}".format(a.MONTHS_FULL[m - 1], y), cx, MY(140), MF(30), a.BLACK, center=True)
    hijri = (w.get("prayer") or {}).get("hijri")
    if hijri:
        text(hijri, cx, MY(178), a.fit(hijri, MF(20), x1 - x0, bold=True, smallest=MF(17)),
             a.GREEN, bold=True, center=True)

    # Small calendar
    start = {"Monday": 1, "Saturday": 6}.get(WEEK_START, 0)
    col = (x1 - x0) // 7
    gx = x0 + (x1 - x0 - col * 7) // 2
    top = MY(212)
    for i in range(7):
        text(a.DAYS[(start + i) % 7][:2], gx + i * col + col // 2, top, MF(18),
             a.BLACK, bold=True, center=True)
    graphics.set_pen(a.BLACK)
    graphics.rectangle(gx, top + MY(24), col * 7, 1)

    nm, ny = (m + 1, y) if m < 12 else (1, y + 1)
    days_in = a._days_from_civil(ny, nm, 1) - first
    lead = ((first + 4) % 7 - start) % 7
    rows = (lead + days_in + 6) // 7
    gtop = top + MY(30)
    rh = min(MY(40), (HEIGHT - MY(8) - gtop) // rows)
    size = MF(20)
    for n in range(1, days_in + 1):
        cell = lead + n - 1
        ncx = gx + (cell % 7) * col + col // 2
        ny_ = gtop + (cell // 7) * rh + (rh - int(size * 1.2)) // 2
        fg, bg = a.BLACK, a.WHITE
        if n == d:
            graphics.set_pen(a.RED)
            graphics.circle(ncx, ny_ + int(size * 0.62), int(size * 0.78))
            fg, bg = a.WHITE, a.RED
        text(str(n), ncx, ny_, size, fg, bold=(n == d), center=True, bg=bg)


def _weather_panel(w, now, x0, x1):
    a = _app
    MX, MY, MF, text = a.MX, a.MY, a.MF, a.draw_text
    room = x1 - x0

    # Top line: place on the left; battery, moon, and the moon's name over
    # the update time on the right
    updated = "Updated " + a.clock(now)
    right = x1
    if a.SHOW_MOON:
        phase = a.moon_phase(now, w["utc_offset"])
        name = a.moon_name(phase)
        tw = max(a.text_width(name, MF(17)), a.text_width(updated, MF(17)))
        text(name, x1, MY(1), MF(17), a.BLACK, right=True)
        text(updated, x1, MY(21), MF(17), a.BLACK, right=True)
        r = MY(16)
        mcx = x1 - tw - MX(10) - r
        graphics.set_pen(a.BLACK)                    # outline, so the white moon shows on white
        graphics.circle(mcx, MY(20), r + 1)
        a.draw_moon(mcx, MY(20), r, phase, a.WHITE, a.BLACK, a.WHITE, a.BLACK if a.MOON_SPOTS else None)
        right = mcx - r - MX(12)
        uw = x1 - right
        bw = a.draw_battery(right, MY(20), dark=False)
    else:
        uw = text(updated, x1, MY(14), MF(17), a.BLACK, right=True)
        bw = a.draw_battery(x1 - uw - MX(12), MY(14) + int(MF(17) * 0.62), dark=False)
    if a.LOCATION_NAME:
        lroom = room - uw - bw - MX(30)
        text(a.LOCATION_NAME, x0, MY(6), a.fit(a.LOCATION_NAME, MF(30), lroom, bold=True, smallest=MF(18)),
             a.BLACK, bold=True)

    # Now: big icon, temperature (both units), conditions, feels like
    isz = a.icon_size(120)
    a.draw_icon(a.icon_for(w["code"]), isz, x0, MY(50))
    tx = x0 + isz + MX(14)

    # Sunrise and sunset at the top right, beside the temperature
    p = w.get("prayer")
    rise = sset = None
    if p and p.get("sun"):
        rise, sset = p["sun"]
    sun = (("Sunrise", a.time_parts(rise)[0] if rise is not None else a.clock(w["sunrise"])),
           ("Sunset", a.time_parts(sset)[0] if sset is not None else a.clock(w["sunset"])))
    lw = a.text_width("Sunrise", MF(17))
    tsz = MF(22)                                 # same size as the prayer times
    sun_w = lw + MX(6) + max(a.text_width(t, tsz, True) for _, t in sun)

    big = a.deg(w["temp"], show_unit=True)
    small = a.deg(w["temp"], a.other_unit(), show_unit=True)
    sw = a.text_width(small, MF(34))
    bsize = a.fit(big, MF(86), x1 - tx - sw - MX(12) - sun_w - MX(12), bold=True, smallest=MF(52))
    by = MY(42) + int((MF(86) - bsize) * 0.7)
    bwid = text(big, tx, by, bsize, a.temp_colour(w["temp"]), bold=True)
    # Sunrise and sunset lines centred on the temperature's digits
    mid = by + int(bsize * 0.56)
    for k, (label, t) in enumerate(sun):
        ty = mid - MY(25) + k * MY(26)
        text(label, x1 - sun_w, ty + int((tsz - MF(17)) * 1.04), MF(17), a.BLACK)
        text(t, x1, ty, tsz, a.ORANGE, bold=True, right=True)
    sx = tx + bwid + MX(12)
    ssz = a.fit(small, MF(34), x1 - sun_w - MX(10) - sx, smallest=MF(20))   # stay clear of sunrise/sunset
    text(small, sx, MY(80) + int((MF(34) - ssz) * 0.9), ssz, a.BLACK)
    desc = a.describe(w["code"]).replace("\n", " ")
    text(desc, tx, MY(134), a.fit(desc, MF(28), x1 - tx, bold=True, smallest=MF(17)), a.GREEN, bold=True)
    # Feels like, then the chance of rain over the next 12 hours
    feels = "Feels like " + a.both(w["feels"])
    rain = w["rain_12h"] + "%"
    rain_w = MX(16) + a.text_width(rain, MF(22), True)
    fw = text(feels, tx, MY(168), a.fit(feels, MF(22), x1 - tx - rain_w - MX(14), smallest=MF(17)), a.BLACK)
    rx = tx + fw + MX(14)
    a.draw_drop(rx, MY(173), MY(16))
    text(rain, rx + MX(16), MY(168), MF(22), a.BLUE, bold=True)

    # Details grid: 3 columns x 2 rows
    graphics.set_pen(a.BLACK)
    graphics.rectangle(x0, MY(200), room, 2)
    # Column widths: High / Low has the shortest value, the wind the longest
    xa, xb, xc = x0, x0 + MX(140), x0 + MX(300)
    wa, wb, wc = xb - xa - MX(10), xc - xb - MX(10), x1 - xc
    cw = wa
    y0, y1 = MY(206), MY(290)
    # The three values share one size (the one the tightest needs), and the
    # second-unit text beneath / beside them shares the small size
    cu, ou = a.UNITS, a.other_unit()
    hl = a.deg(w["hi_c"], cu, True) + " / " + a.deg(w["lo_c"], cu, True)
    vsize = a.fit(hl, MF(26), wa, bold=True, smallest=MF(17))
    vsize = min(vsize, a.draw_uv_humidity(w, 0, 0, wb, top=MF(26), measure=True))
    if a.SHOW_BOTH_UNITS:
        vsize = min(vsize, a.draw_wind(w, 0, 0, wc, top=MF(26), measure=True))
    else:
        vsize = min(vsize, a.fit(a.wind_text(w), MF(26), wc, bold=True, smallest=MF(17)))
    small = max(MF(17), int(vsize * 0.72))

    text("High / Low", x0, y0, MF(17), a.BLACK)
    text(hl, x0, y0 + MY(18), vsize, a.unit_colour(cu), bold=True)
    if a.SHOW_BOTH_UNITS:
        ho = a.deg(w["hi_c"], ou, True) + " / " + a.deg(w["lo_c"], ou, True)
        text(ho, x0, y0 + MY(20) + int(vsize * 1.12), a.fit(ho, small, wa, smallest=MF(17)), a.unit_colour(ou))
    text("UV / Humidity", xb, y0, MF(17), a.BLACK)
    a.draw_uv_humidity(w, xb, y0 + MY(18), wb, top=vsize)
    text("Wind (" + w["wind_dir"] + ")", xc, y0, MF(17), a.BLACK)
    if a.SHOW_BOTH_UNITS:
        a.draw_wind(w, xc, y0 + MY(18), wc, top=vsize)
    else:
        text(a.wind_text(w), xc, y0 + MY(18), vsize, a.BLACK, bold=True)

    # Second row: the five prayers, the next one in a green box
    p = w.get("prayer")
    if p:
        cols = a.PRAYER_COLUMNS
        pcol = room // len(cols)
        ph = MY(48)
        nxt = cols.index(p["next"]) if p["next"] in cols else -1
        # am/pm only if every time in the row has room for it
        suffix = True
        for i in cols:
            big, small = a.time_parts(p["times"][i])
            if small and a.text_width(big, MF(22), True) + MX(2) + a.text_width(small, MF(17)) > pcol - MX(8):
                suffix = False
        for j, i in enumerate(cols):
            x = x0 + j * pcol
            cx = x + pcol // 2
            is_next = j == nxt
            fg, bg = (a.WHITE, a.GREEN) if is_next else (a.BLACK, a.WHITE)
            if is_next:
                graphics.set_pen(a.GREEN)
                graphics.rectangle(x + MX(2), y1 - MY(2), pcol - MX(4), ph)
            elif j and nxt != j - 1:
                graphics.set_pen(a.BLACK)
                graphics.rectangle(x, y1 + MY(6), 1, ph - MY(14))
            text(p["names"][i], cx, y1, MF(17), fg, bold=True, center=True, bg=bg)
            big, small = a.time_parts(p["times"][i])
            if not suffix:
                small = ""                  # no room for am/pm: the order makes it clear
            bwd = a.text_width(big, MF(22), True)
            swd = a.text_width(small, MF(17)) if small else 0
            gap = MX(2) if small else 0
            sx = cx - (bwd + gap + swd) // 2
            text(big, sx, y1 + MY(20), MF(22), fg, bold=True, bg=bg)
            if small:
                text(small, sx + bwd + gap, y1 + MY(20) + int((MF(22) - MF(17)) * 1.04), MF(17), fg, bg=bg)

    # A weather warning, if there is one, in a red bar above the forecast
    fy = MY(344)
    if w["alerts"]:
        a.draw_alert_banner(w["alerts"], x0, x1, MY(341), MY(26))
        fy = MY(371)
    graphics.set_pen(a.BLACK)
    graphics.rectangle(x0, fy - MY(4), room, 2)

    # Forecast: 4 days. Name and rain chance, icon, °C and °F high / low
    days = w["days"][:4]
    dcol = room // max(1, len(days))
    fisz = a.icon_size(60)
    small_icons = fy > MY(344)        # a warning takes some room: smaller icons
    if small_icons:
        fisz = a.icon_size(30)
    tsize = MF(16) if a.FONT == "original" and not a._bmp_failed else MF(17)
    for i, d in enumerate(days):
        x = x0 + i * dcol
        if i:
            graphics.set_pen(a.BLACK)
            graphics.rectangle(x - MX(4), fy + MY(4), 1, HEIGHT - fy - MY(10))
        text(d["name"][:3], x, fy, MF(20), a.BLACK, bold=True)
        rain = d["rain"] + "%"
        rw = a.text_width(rain, MF(17))
        text(rain, x + dcol - MX(10), fy + MY(2), MF(17), a.BLUE, right=True)
        a.draw_drop(x + dcol - MX(10) - rw - MX(14), fy + MY(5), MY(14))
        iy = fy + MY(21)
        if small_icons:
            a.draw_icon(a.icon_for(d["code"]), fisz, x + (dcol - MX(10) - fisz) // 2, iy)
        else:
            a.draw_icon(a.icon_for(d["code"]), fisz, x + (dcol - MX(10) - fisz) // 2, iy)
        ty = iy + fisz - MY(1)
        units = ("C", "F") if a.SHOW_BOTH_UNITS else (a.UNITS,)
        for k, u in enumerate(units):
            hi, lo = a.deg(d["hi_c"], u, True), a.deg(d["lo_c"], u, True)
            t = hi + "/" + lo
            if a.text_width(t, tsize, True) > dcol - MX(12):
                t = hi.rstrip(u).rstrip(a.DEG) + "/" + lo
            text(t, x + (dcol - MX(10)) // 2, ty + k * MY(17), tsize, a.unit_colour(u), bold=True, center=True)


def _draw_screen(w):
    a = _app
    MX, MY = a.MX, a.MY
    graphics.set_pen(a.WHITE)
    graphics.clear()
    now = a.local_now(w["now"], w["utc_offset"])
    split = MX(300)
    _date_panel(w, now, MX(10), split - MX(10))
    graphics.set_pen(a.BLACK)
    graphics.rectangle(split, MY(10), 2, HEIGHT - MY(20))
    _weather_panel(w, now, split + MX(16), WIDTH - MX(12))


def draw():
    a = _app
    _setup()
    if a.weather is None:
        a.draw()        # keeps the last screen after a one-off failure, or shows the error
        return
    gc.collect()
    if a._jpeg is None:
        try:            # the icon decoder needs one big block of memory: take it while it's free
            a._jpeg = a.jpegdec.JPEG(graphics)
        except MemoryError:
            gc.collect()
    if a._vector is None:
        a._vector = a._has_vector_font(a._vfont())
    a._write_fails(0)
    try:
        _draw_screen(a.weather)
    except MemoryError:
        if a.FONT != "original" or a._bmp_failed:
            raise
        a._bmp_failed = True        # not enough memory for the pre-rendered font
        a._bmp_close()
        gc.collect()
        _draw_screen(a.weather)
    a._jpeg = None
    a._bmp_close()
    gc.collect()
    graphics.update()
