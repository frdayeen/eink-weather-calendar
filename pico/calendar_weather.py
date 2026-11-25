# Calendar with the weather and prayer times, for the Inky Frame launcher (button B).
#
#   Left:  the weather now, then today's prayer times with the next one in green
#   Right: this month, today circled in red, weather on today and the coming days
#
# It uses your settings in weather.py and the weather app's data, fonts and
# icons, so everything matches the weather screen. The small calendar icons
# (*_32.jpg) go in the icons folder on the SD card with the others.

# ---- Settings ----
# First day of the week: "Sunday", "Monday" or "Saturday"
WEEK_START = "Sunday"
# ------------------

import gc
import os

graphics = None
WIDTH = None
HEIGHT = None
UPDATE_INTERVAL = 60

import weather as _w        # your settings, and the weather app's code
_app = _w._app


def _small_icon(name, x, y):
    """32 px icon for a calendar box. If the small icon files (*_32.jpg) aren't
    on the card, the normal 64 px icon is drawn at half size instead."""
    a = _app
    d = a.asset_dir("icons")
    path = "{}/{}_{}.jpg".format(d, name, a.icon_size(30))
    scale = a.jpegdec.JPEG_SCALE_FULL
    try:
        os.stat(path)
    except OSError:
        path = "{}/{}_{}.jpg".format(d, name, a.icon_size(60))
        scale = a.jpegdec.JPEG_SCALE_HALF
    try:
        if a._jpeg is None:
            a._jpeg = a.jpegdec.JPEG(graphics)
        a._jpeg.open_file(path)
        a._jpeg.decode(x, y, scale, dither=False)
    except Exception as e:
        print("Icon {} failed: {}".format(path, e))


def _setup():
    _w.graphics = graphics
    _w.WIDTH = WIDTH
    _w.HEIGHT = HEIGHT
    _w._share()


def update():
    global UPDATE_INTERVAL
    _setup()
    a = _app
    a.update()                       # weather, alerts and prayer times
    w = a.weather
    if w is not None and w.get("prayer") is None:
        try:                         # prayer times even if they're off on the weather screen
            w["prayer"] = a.prayer_info(a.local_now(w["now"], w["utc_offset"]), w["utc_offset"])
            until = w["prayer"]["until"]
            if until is not None and until + 1 < a.UPDATE_INTERVAL:
                a.UPDATE_INTERVAL = max(1, until + 1)
        except Exception as e:
            print("Prayer times unavailable:", e)
    UPDATE_INTERVAL = a.UPDATE_INTERVAL


# ---------------------------------------------------------------------------

def _header(w, now):
    a = _app
    MX, MY, MF, text = a.MX, a.MY, a.MF, a.draw_text
    graphics.set_pen(a.BLACK)
    graphics.rectangle(0, 0, WIDTH, MY(54))
    date = "{}, {} {} {}".format(a.day_name(now[:10]), int(now[8:10]), a.MONTHS_FULL[int(now[5:7]) - 1], now[:4])
    updated = "Updated " + a.clock(now)
    hijri = (w.get("prayer") or {}).get("hijri")
    if hijri:
        right_w = max(a.text_width(hijri, MF(17)), a.text_width(updated, MF(17)))
        text(hijri, WIDTH - MX(20), MY(5), MF(17), a.GREEN, right=True, bg=a.BLACK)
        text(updated, WIDTH - MX(20), MY(27), MF(17), a.WHITE, right=True, bg=a.BLACK)
    else:
        right_w = a.text_width(updated, MF(21))
        text(updated, WIDTH - MX(20), MY(12), MF(21), a.WHITE, right=True, bg=a.BLACK)
    right_edge = WIDTH - MX(20) - right_w
    used = a.draw_battery(right_edge - MX(12), MY(27))
    if used:
        right_edge -= used + MX(12)
    x = MX(20)
    if a.LOCATION_NAME:
        size = a.fit(a.LOCATION_NAME, MF(34), MX(230), bold=True, smallest=MF(20))
        x += text(a.LOCATION_NAME, x, MY(4), size, a.WHITE, bold=True, bg=a.BLACK) + MX(16)
        text(date, x, MY(4) + int((size - MF(24)) * 1.04),
             a.fit(date, MF(24), right_edge - x - MX(10), smallest=MF(17)), a.WHITE, bg=a.BLACK)
    else:
        text(date, x, MY(4), a.fit(date, MF(34), right_edge - x - MX(10), bold=True, smallest=MF(20)),
             a.WHITE, bold=True, bg=a.BLACK)


def _calendar(w, now, x0, x1, top, bottom):
    """The month, today in a red circle, and the weather (icon and high / low)
    on today and the coming days."""
    a = _app
    MX, MY, MF, text = a.MX, a.MY, a.MF, a.draw_text
    y, m, d = int(now[0:4]), int(now[5:7]), int(now[8:10])    # (the month and year are in the header)

    start = {"Monday": 1, "Saturday": 6}.get(WEEK_START, 0)
    col = (x1 - x0) // 7
    for i in range(7):
        text(a.DAYS[(start + i) % 7][:3], x0 + i * col + col // 2, top, MF(18),
             a.BLACK, bold=True, center=True)
    graphics.set_pen(a.BLACK)
    graphics.rectangle(x0, top + MY(25), col * 7, 1)

    first = a._days_from_civil(y, m, 1)                     # days since 1 Jan 1970 (a Thursday)
    nm, ny = (m + 1, y) if m < 12 else (1, y + 1)
    days_in = a._days_from_civil(ny, nm, 1) - first
    lead = ((first + 4) % 7 - start) % 7                    # blank boxes before the 1st
    rows = (lead + days_in + 6) // 7
    gtop = top + MY(28)
    rh = (bottom - gtop) // rows

    # Weather for each day we have: today, then the forecast days
    fc = {d: (w["code"], w["hi_c"], w["lo_c"])}
    for k, day in enumerate(w["days"]):
        if d + 1 + k <= days_in:
            fc[d + 1 + k] = (day["code"], day["hi_c"], day["lo_c"])

    isz = a.icon_size(30)                                    # 32 px on the 7.3" screen
    size = MF(20)
    # Room for a °C line and a °F line under the icon? (six-week months are tighter)
    # Forecast temperatures: bold 16 px with the PT Serif font from the SD card;
    # the built-in fallback font has nothing that small that is still readable
    tsize = MF(16) if a.FONT == "original" and not a._bmp_failed else MF(17)
    roomy = rh >= MY(2) + isz + MY(1) + MY(17) + MY(18)
    line_h = MY(17) if roomy else MY(14)
    icon_dy = MY(2) if roomy else MY(1)
    text_dy = icon_dy + isz + (MY(1) if roomy else -MY(1))
    two_lines = rh >= text_dy + line_h + MY(14)

    # Light dotted lines between the boxes
    graphics.set_pen(a.BLACK)
    for r_ in range(1, rows):
        yy = gtop + r_ * rh
        for xx in range(x0, x0 + col * 7, 3):
            graphics.pixel(xx, yy)
    for c_ in range(1, 7):
        xx = x0 + c_ * col
        for yy in range(gtop, gtop + rows * rh, 3):
            graphics.pixel(xx, yy)
    for n in range(1, days_in + 1):
        cell = lead + n - 1
        cx0 = x0 + (cell % 7) * col
        ctop = gtop + (cell // 7) * rh
        num = str(n)
        nx, ny_ = cx0 + MX(4), ctop + MY(3)                  # date in the top-left corner
        if n in fc:
            # Icon in the top-right corner, high / low underneath: '4°/-2°C'
            code, hi_c, lo_c = fc[n]
            _small_icon(a.icon_for(code), cx0 + col - isz - MX(1), ctop + icon_dy)
            if hi_c is not None and lo_c is not None:
                # High / low side by side: °C on top in its colour, °F below in its own
                ty = ctop + text_dy
                units = ("C", "F") if a.SHOW_BOTH_UNITS else (a.UNITS,)
                if not two_lines:
                    units = units[:1]
                for k, u in enumerate(units):
                    # Every value with its unit: '13°C/3°C', '55°F/38°F'. Only if that
                    # can't fit (very cold or hot days) is the unit written once.
                    hi, lo = a.deg(hi_c, u, True), a.deg(lo_c, u, True)
                    for t in (hi + "/" + lo, hi.rstrip(u).rstrip(a.DEG) + "/" + lo,
                              hi.rstrip(u).rstrip(a.DEG) + "/" + lo.rstrip(u).rstrip(a.DEG)):
                        if a.text_width(t, tsize, True) <= col - MX(6):
                            break
                    text(t, cx0 + col // 2, ty + k * line_h, tsize, a.unit_colour(u), bold=True, center=True)
        fg, bg = a.BLACK, a.WHITE
        if n == d:
            nw = a.text_width(num, size, True)
            graphics.set_pen(a.RED)
            graphics.circle(nx + nw // 2, ny_ + int(size * 0.62), int(size * 0.7))
            fg, bg = a.WHITE, a.RED
        text(num, nx, ny_, size, fg, bold=True, bg=bg)


def _now_panel(w, x0, x1, top):
    """The weather now, in a narrow column: icon and temperature, then the
    conditions, feels like, high / low, rain chance and wind."""
    a = _app
    MX, MY, MF, text = a.MX, a.MY, a.MF, a.draw_text
    room = x1 - x0
    isz = a.icon_size(60)
    a.draw_icon(a.icon_for(w["code"]), isz, x0, top + MY(2))
    tx = x0 + isz + MX(8)
    big = a.deg(w["temp"], show_unit=True)
    bsize = a.fit(big, MF(52), x1 - tx, bold=True, smallest=MF(28))
    text(big, tx, top + int((MF(52) - bsize) * 0.7), bsize, a.temp_colour(w["temp"]), bold=True)
    text(a.deg(w["temp"], a.other_unit(), show_unit=True), tx, top + MY(48), MF(22), a.BLACK)

    y = top + MY(74)
    desc = a.SHORT_CONDITIONS.get(w["code"]) or a.describe(w["code"]).replace("\n", " ")
    while " " in desc and a.text_width(desc, MF(17), True) > room:
        desc = desc.rsplit(" ", 1)[0]
    text(desc, x0, y, a.fit(desc, MF(22), room, bold=True, smallest=MF(17)), a.GREEN, bold=True)
    y += MY(26)
    # Four detail lines, all at one size: the largest that every line fits at
    feels = "Feels like " + a.both(w["feels"])
    cu, ou = a.UNITS, a.other_unit()
    hl = a.deg(w["hi_c"], cu, True) + "/" + a.deg(w["lo_c"], cu, True)
    ho = (a.deg(w["hi_c"], ou, True) + "/" + a.deg(w["lo_c"], ou, True)) if a.SHOW_BOTH_UNITS else ""
    rain = w["rain_12h"] + "% chance"
    kph = w["wind"]
    km = "{} km/h".format(int(round(kph)))
    mi = "{} mph".format(int(round(kph / 1.609344)))
    main, other = (mi, km) if a.UNITS == "F" else (km, mi)
    wind = main + (" (" + other + ")" if a.SHOW_BOTH_UNITS else "") + " " + w["wind_dir"]

    def widths(sz):
        return (a.text_width(feels, sz),
                a.text_width(hl, sz, True) + (MX(8) + a.text_width(ho, sz) if ho else 0),
                MX(16) + a.text_width(rain, sz),
                a.text_width(wind, sz))
    lsize = MF(18)
    if max(widths(lsize)) > room:
        lsize = MF(17)
    if ho and widths(lsize)[1] > room:
        ho = ""                                    # very cold/hot: leave out the second unit
    if a.text_width("Wind " + wind, lsize) <= room:
        wind = "Wind " + wind
    step = MY(21)

    text(feels, x0, y, a.fit(feels, lsize, room, smallest=MF(17)), a.BLACK)
    y += step
    # High / low: chosen unit in its colour, the other unit beside it
    hw = text(hl, x0, y, lsize, a.unit_colour(cu), bold=True)
    if ho:
        text(ho, x0 + hw + MX(8), y, lsize, a.unit_colour(ou))
    y += step
    # Chance of rain over the next 12 hours, then the wind
    a.draw_drop(x0 + MX(1), y + MY(4), MY(15))
    text(rain, x0 + MX(16), y, lsize, a.BLUE)
    y += step
    text(wind, x0, y, a.fit(wind, lsize, room, smallest=MF(17)), a.BLACK)


def _prayer_list(p, x0, x1, top, bottom, title=True):
    """Five rows, one per prayer, the next one in a green bar."""
    a = _app
    MX, MY, MF, text = a.MX, a.MY, a.MF, a.draw_text
    rtop = top
    if title:
        t = "Prayer times tomorrow" if p["tomorrow"] else "Prayer times"
        asr = "(Hanafi)" if a.ASR_METHOD.lower() == "hanafi" else "(Standard Asr)"
        # Keep '(Hanafi)' beside the heading if a slightly smaller heading makes room
        tsize = None
        for sz in (MF(20), MF(18)):
            if a.text_width(t, sz, True) + MX(6) + a.text_width(asr, MF(17)) <= x1 - x0:
                tsize = sz
                break
        if tsize is None:
            asr = ""                         # no room: leave out '(Hanafi)'
            tsize = a.fit(t, MF(20), x1 - x0, bold=True, smallest=MF(17))
        tw = text(t, x0, top + int((MF(20) - tsize) * 1.04), tsize, a.BLACK, bold=True)
        if asr:
            text(asr, x0 + tw + MX(6), top + int((MF(20) - MF(17)) * 1.04), MF(17), a.BLACK)
        rtop = top + MY(28)

    cols = a.PRAYER_COLUMNS
    rh = (bottom - rtop) // len(cols)
    for j, i in enumerate(cols):
        y = rtop + j * rh
        is_next = i == p["next"]
        fg, bg = (a.WHITE, a.GREEN) if is_next else (a.BLACK, a.WHITE)
        if is_next:
            graphics.set_pen(a.GREEN)
            graphics.rectangle(x0 - MX(6), y + 1, x1 - x0 + MX(12), rh - 2)
        elif j:
            graphics.set_pen(a.BLACK)
            graphics.rectangle(x0, y, x1 - x0, 1)
        ty = y + (rh - int(MF(22) * 1.15)) // 2
        nw = text(p["names"][i], x0, ty + int((MF(22) - MF(20)) * 1.04), MF(20), fg, bold=True, bg=bg)
        if is_next:
            text("next", x0 + nw + MX(8), ty + int((MF(22) - MF(17)) * 1.04), MF(17), a.WHITE, bg=a.GREEN)
        big, small = a.time_parts(p["times"][i])
        sx = x1
        if small:
            sx -= a.text_width(small, MF(17))
            text(small, sx, ty + int((MF(22) - MF(17)) * 1.04), MF(17), fg, bg=bg)
            sx -= MX(3)
        text(big, sx, ty, MF(22), fg, bold=True, right=True, bg=bg)


def _alert_banner(alerts, x0, x1, y):
    """Red banner with the full alert name (on two lines if it's long).
    Returns its height."""
    a = _app
    MX, MY, MF, text = a.MX, a.MY, a.MF, a.draw_text
    txt = a.alert_text(alerts, False)            # e.g. 'Winter Storm Warning'
    room = x1 - x0 - MX(12)
    lines = [txt]
    size = a.fit(txt, MF(20), room, bold=True, smallest=MF(17))
    if a.text_width(txt, size, True) > room and " " in txt:
        # Two lines, split near the middle at a space
        words = txt.split(" ")
        best = 1
        for k in range(1, len(words)):
            l1, l2 = " ".join(words[:k]), " ".join(words[k:])
            if max(len(l1), len(l2)) < max(len(" ".join(words[:best])), len(" ".join(words[best:]))):
                best = k
        lines = [" ".join(words[:best]), " ".join(words[best:])]
        size = min(a.fit(l, MF(20), room, bold=True, smallest=MF(17)) for l in lines)
    line_h = int(size * 1.15)
    h = line_h * len(lines) + MY(8)
    graphics.set_pen(a.RED)
    graphics.rectangle(x0, y, x1 - x0, h)
    for k, l in enumerate(lines):
        text(l, (x0 + x1) // 2, y + MY(3) + k * line_h, size, a.WHITE, bold=True, center=True, bg=a.RED)
    return h


def _draw_screen(w):
    a = _app
    MX, MY = a.MX, a.MY
    graphics.set_pen(a.WHITE)
    graphics.clear()
    now = a.local_now(w["now"], w["utc_offset"])
    _header(w, now)

    # The weather and prayer times in a narrow column on the left, the
    # calendar on the right (boxes 80 px wide, so the temperatures have room)
    cal_x1 = WIDTH - MX(8)
    cal_x0 = cal_x1 - 7 * MX(80)
    split = cal_x0 - MX(6)
    _calendar(w, now, cal_x0, cal_x1, MY(64), HEIGHT - MY(4))
    graphics.set_pen(a.BLACK)
    graphics.rectangle(split, MY(66), 1, HEIGHT - MY(78))

    x0, x1 = MX(12), split - MX(10)
    _now_panel(w, x0, x1, MY(62))
    graphics.set_pen(a.BLACK)
    graphics.rectangle(x0, MY(254), x1 - x0, 2)
    p = w.get("prayer")
    if w["alerts"]:
        # A weather warning takes the place of the prayer heading
        h = _alert_banner(w["alerts"], x0 - MX(4), x1 + MX(4), MY(259))
        if p:
            _prayer_list(p, x0, x1, MY(259) + h + MY(4), HEIGHT - MY(8), title=False)
    elif p:
        _prayer_list(p, x0, x1, MY(260), HEIGHT - MY(8))


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
