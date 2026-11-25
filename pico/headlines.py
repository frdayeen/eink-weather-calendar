# Headlines front page, for the Inky Frame launcher (button D).
#
#   A lead story (headline, summary and QR code), then four more headlines in
#   two columns, each with its section, source, age and a QR code to open it
#   on your phone.
#
# It uses your settings in weather.py (time zone, Hijri date, clock, font)
# and the weather app's fonts, so it matches the other screens.

# ---- Settings ----
# (section, source, feed address). The first one is the lead story.
# Any RSS feed works; keep the sections short.
FEEDS = (
    ("World", "CBS News", "https://www.cbsnews.com/latest/rss/world"),
    ("US", "CBS News", "https://www.cbsnews.com/latest/rss/us"),
    ("Chicago", "CBS Chicago", "https://www.cbsnews.com/chicago/latest/rss/main"),
    ("Bangladesh", "Prothom Alo", "https://en.prothomalo.com/feed/"),
    ("Tech", "CBS News", "https://www.cbsnews.com/latest/rss/technology"),
)
SHOW_QR = True            # QR codes to open each story on your phone
UPDATE_MINUTES = 60
# ------------------

import gc
import time

graphics = None
WIDTH = None
HEIGHT = None
UPDATE_INTERVAL = UPDATE_MINUTES

import weather as _w        # your settings, and the weather app's code
_app = _w._app

stories = []                # one dict per feed
_now = None                 # local time 'YYYY-MM-DDTHH:MM'
_offset = 0
_hijri = None

SECTION_COLOURS = ("RED", "BLUE", "GREEN", "ORANGE", "BLACK")
WANTED = (b"title", b"link", b"pubDate", b"description")
MAX_FIELD = 1200            # bytes kept per field
AGENT = "InkyFrame/1.0 (Pimoroni Inky Frame headlines)"


def _setup():
    _w.graphics = graphics
    _w.WIDTH = WIDTH
    _w.HEIGHT = HEIGHT
    _w._share()


# ---------------------------------------------------------------------------
# Reading the feeds

def _read_items(raw, n):
    """Stream an RSS feed and return the first n <item>s as dicts of raw
    bytes. Only the wanted fields are kept, so memory use stays small even
    for big feeds."""
    items, cur, buf = [], None, b""
    skip = None             # closing tag of an element being skipped
    field = None            # [name, closing tag, collected bytes]
    while True:
        chunk = raw.read(512)
        if not chunk:
            break
        buf += chunk
        while True:
            if skip:
                i = buf.find(skip)
                if i < 0:
                    buf = buf[-(len(skip) - 1):]
                    break
                buf = buf[i + len(skip):]
                skip = None
                continue
            if field:
                i = buf.find(field[1])
                if i < 0:
                    keep = len(field[1]) - 1
                    if len(buf) > keep:
                        if len(field[2]) < MAX_FIELD:
                            field[2] += buf[:-keep]
                        buf = buf[-keep:]
                    break
                if len(field[2]) < MAX_FIELD:
                    field[2] += buf[:i]
                cur[field[0]] = field[2][:MAX_FIELD]
                buf = buf[i + len(field[1]):]
                field = None
                continue
            if cur is None:
                i = buf.find(b"<item")
                if i < 0:
                    buf = buf[-5:]
                    break
                j = buf.find(b">", i)
                if j < 0:
                    buf = buf[i:]
                    break
                buf = buf[j + 1:]
                cur = {}
                continue
            i = buf.find(b"<")
            if i < 0:
                buf = b""
                break
            j = buf.find(b">", i)
            if j < 0:
                buf = buf[i:]
                break
            tag = buf[i + 1:j]
            buf = buf[j + 1:]
            if tag.startswith(b"/item"):
                items.append(cur)
                cur = None
                if len(items) >= n:
                    return items
                continue
            if tag[:1] in (b"/", b"!", b"?") or tag.endswith(b"/"):
                continue
            name = tag.split(b" ")[0]
            if name in WANTED and name not in cur:
                field = [name, b"</" + name + b">", b""]
            else:
                skip = b"</" + name + b">"
    return items


ENTITIES = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": " ",
            "rsquo": "'", "lsquo": "'", "ldquo": '"', "rdquo": '"', "ndash": "-",
            "mdash": "-", "hellip": "...", "deg": "°"}
UNICODE = {"‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"',
           "–": "-", "—": "-", "…": "...", " ": " ", "•": "-",
           "«": '"', "»": '"', "′": "'"}
ACCENTED = "àáâãäåèéêëìíîïòóôõöùúûüñçýÀÁÂÃÄÅÈÉÊËÌÍÎÏÒÓÔÕÖÙÚÛÜÑÇÝ"
PLAIN = "aaaaaaeeeeiiiiooooouuuuncyAAAAAAEEEEIIIIOOOOOUUUUNCY"


def _clean(b):
    """Raw field bytes -> plain text the frame's font can show."""
    try:
        s = b.decode("utf-8")
    except Exception:
        s = "".join(chr(c) for c in b if c < 128)
    s = s.replace("<![CDATA[", "").replace("]]>", "")
    # strip HTML tags (descriptions can contain them)
    out, i = [], 0
    while True:
        j = s.find("<", i)
        if j < 0:
            out.append(s[i:])
            break
        out.append(s[i:j])
        k = s.find(">", j)
        if k < 0:
            break
        out.append(" ")
        i = k + 1
    s = "".join(out)
    # entities, twice for double-escaped feeds ('&amp;#039;')
    for _ in range(2):
        out, i = [], 0
        while True:
            j = s.find("&", i)
            if j < 0:
                out.append(s[i:])
                break
            k = s.find(";", j, j + 10)
            if k < 0:
                out.append(s[i:j + 1])
                i = j + 1
                continue
            out.append(s[i:j])
            name = s[j + 1:k]
            if name.startswith("#"):
                try:
                    out.append(chr(int(name[2:], 16) if name[1:2] in ("x", "X") else int(name[1:])))
                except ValueError:
                    out.append(s[j:k + 1])
            else:
                out.append(ENTITIES.get(name, s[j:k + 1]))
            i = k + 1
        s = "".join(out)
    # characters outside the font
    out = []
    for ch in s:
        if " " <= ch <= "~" or ch == "°":
            out.append(ch)
        elif ch in UNICODE:
            out.append(UNICODE[ch])
        elif ch in ACCENTED:
            out.append(PLAIN[ACCENTED.index(ch)])
        elif ch in "\t\n\r":
            out.append(" ")
    return " ".join("".join(out).split())


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
ZONES = {"GMT": 0, "UTC": 0, "UT": 0, "Z": 0, "EST": -300, "EDT": -240, "CST": -360,
         "CDT": -300, "MST": -420, "MDT": -360, "PST": -480, "PDT": -420}


def _pub_minutes(s):
    """'Tue, 24 Nov 2026 19:01:06 -0600' -> minutes since 1970 (UTC), or None."""
    try:
        p = s.replace(",", " ").split()
        if p[0][:1].isalpha():
            p = p[1:]
        d, mon, y = int(p[0]), MONTHS.index(p[1][:3]) + 1, int(p[2])
        hh, mm = p[3].split(":")[:2]
        tz = p[4] if len(p) > 4 else "GMT"
        if tz[:1] in "+-" and len(tz) == 5:
            off = int(tz[1:3]) * 60 + int(tz[3:5])
            off = -off if tz[0] == "-" else off
        else:
            off = ZONES.get(tz.upper(), 0)
        return _app._days_from_civil(y, mon, d) * 1440 + int(hh) * 60 + int(mm) - off
    except Exception:
        return None


def _ago(pub):
    if pub is None or _now is None:
        return ""
    now = (_app._days_from_civil(int(_now[0:4]), int(_now[5:7]), int(_now[8:10])) * 1440
           + int(_now[11:13]) * 60 + int(_now[14:16]) - _offset // 60)
    m = now - pub
    if m < 1:
        return "just now"
    if m < 60:
        return "{} min ago".format(m)
    if m < 48 * 60:
        return "{} h ago".format(m // 60)
    return "{} d ago".format(m // 1440)


def _fetch_story(url):
    a = _app
    a.ensure_wifi()
    r = a.requests.get(url, headers={"User-Agent": AGENT}, timeout=30)
    try:
        if r.status_code != 200:
            raise RuntimeError("HTTP {}".format(r.status_code))
        items = _read_items(r.raw, 1)
    finally:
        r.close()
    if not items:
        raise RuntimeError("no stories in the feed")
    it = items[0]
    title = _clean(it.get(b"title", b""))
    if len(title) > 220:
        title = title[:217] + "..."
    return {
        "title": title or "(no headline)",
        "link": _clean(it.get(b"link", b"")),
        "pub": _pub_minutes(_clean(it.get(b"pubDate", b""))),
        "desc": _clean(it.get(b"description", b""))[:400],
    }


def _fetch_now():
    """Local date and time, and the UTC offset, from the weather service."""
    a = _app
    url = ("https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}"
           "&current=weather_code&forecast_days=1&timezone={}").format(
               a.LATITUDE, a.LONGITUDE, a.TIMEZONE.replace("/", "%2F"))
    a.ensure_wifi()
    r = a.requests.get(url, timeout=30)
    try:
        a._remember_date(r)
        data = r.json()
    finally:
        r.close()
    offset = data.get("utc_offset_seconds", 0)
    return a.local_now(data["current"]["time"], offset), offset


def update():
    global stories, _now, _offset, _hijri, UPDATE_INTERVAL
    _setup()
    UPDATE_INTERVAL = UPDATE_MINUTES
    try:
        _now, _offset = _fetch_now()
        _hijri = _app.prayer_info(_now, _offset).get("hijri")
    except Exception as e:
        print("No date / Hijri date:", e)
    new, errors = [], []
    for k, (section, source, url) in enumerate(FEEDS[:5]):
        gc.collect()
        st = {"section": section, "source": source, "colour": SECTION_COLOURS[k % 5]}
        for attempt in range(2):
            try:
                st.update(_fetch_story(url))
                st.pop("error", None)
                break
            except Exception as e:
                st["error"] = str(e)
                print("Feed {} failed: {}".format(section, e))
                time.sleep(2)
        if "error" in st:
            errors.append(section)
        new.append(st)
    if len(errors) == len(new):
        raise RuntimeError("Couldn't load any news feed - check Wi-Fi")
    # If the lead feed failed, the first section that worked takes its place
    if "error" in new[0]:
        k = next(i for i, st in enumerate(new) if "error" not in st)
        new.insert(0, new.pop(k))
    stories = new


# ---------------------------------------------------------------------------
# Drawing

def _wrap(txt, size, width, bold=False, max_lines=3):
    a = _app
    lines, cur = [], ""
    for wd in txt.split(" "):
        t = (cur + " " + wd).strip()
        if a.text_width(t, size, bold) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while " " in last and a.text_width(last + "...", size, bold) > width:
            last = last.rsplit(" ", 1)[0]
        lines[-1] = last + "..."
    return lines


def _qr_size(link, room):
    """(module count, pixels per module) for a QR code no wider than room,
    or None if it would be too small to scan (under 2 px per module)."""
    if not SHOW_QR or not link:
        return None
    try:
        import qrcode
        code = qrcode.QRCode()
        code.set_text(link)
        n = code.get_size()[0]
    except Exception as e:
        print("QR failed:", e)
        return None
    scale = room // (n + 4)                 # with a 2-module white border
    if scale < 2:
        return None
    return code, n, scale


def _draw_qr(q, x, y):
    code, n, scale = q
    full = (n + 4) * scale
    graphics.set_pen(_app.WHITE)
    graphics.rectangle(x, y, full, full)
    graphics.set_pen(_app.BLACK)
    ox, oy = x + 2 * scale, y + 2 * scale
    for yy in range(n):
        for xx in range(n):
            if code.get_module(xx, yy):
                graphics.rectangle(ox + xx * scale, oy + yy * scale, scale, scale)
    return full


def _header_line(st, x, x1, y):
    """Section label (in its colour) on the left, source and age on the right."""
    a = _app
    MF, text = a.MF, a.draw_text
    text(st["section"].upper(), x, y, MF(17), getattr(a, st["colour"]), bold=True)
    info = st["source"]
    ago = _ago(st.get("pub"))
    if ago:
        info += " - " + ago
    text(info, x1, y, MF(17), a.BLACK, right=True)


def _masthead():
    a = _app
    MX, MY, MF, text = a.MX, a.MY, a.MF, a.draw_text
    graphics.set_pen(a.BLACK)
    graphics.rectangle(0, 0, WIDTH, MY(54))
    tw = text("Headlines", MX(20), MY(4), MF(34), a.WHITE, bold=True, bg=a.BLACK)
    updated = "Updated " + (a.clock(_now) if _now else "--")
    rw = a.text_width(updated, MF(17))
    if _hijri:
        rw = max(rw, a.text_width(_hijri, MF(17)))
        text(_hijri, WIDTH - MX(20), MY(5), MF(17), a.GREEN, right=True, bg=a.BLACK)
        text(updated, WIDTH - MX(20), MY(27), MF(17), a.WHITE, right=True, bg=a.BLACK)
    else:
        text(updated, WIDTH - MX(20), MY(16), MF(17), a.WHITE, right=True, bg=a.BLACK)
    right = WIDTH - MX(20) - rw - MX(12)
    right -= a.draw_battery(right, MY(27))
    if _now:
        date = "{}, {} {}".format(a.day_name(_now[:10]), int(_now[8:10]), a.MONTHS_FULL[int(_now[5:7]) - 1])
        x = MX(20) + tw + MX(16)
        room = right - MX(12) - x
        if room > MX(60):
            text(date, x, MY(12), a.fit(date, MF(24), room, smallest=MF(17)), a.WHITE, bg=a.BLACK)


def _draw_screen():
    a = _app
    MX, MY, MF, text = a.MX, a.MY, a.MF, a.draw_text
    graphics.set_pen(a.WHITE)
    graphics.clear()
    _masthead()
    x0, x1 = MX(20), WIDTH - MX(20)

    # Lead story: headline, summary, QR code
    lead = stories[0]
    y = MY(64)
    _header_line(lead, x0, x1, y)
    q = _qr_size(lead.get("link"), MY(110))
    qw = (q[1] + 4) * q[2] if q else 0
    tw = x1 - x0 - (qw + MX(14) if q else 0)
    yy = y + MY(22)
    if "error" in lead:
        text("Couldn't load the " + lead["section"] + " news", x0, yy, MF(22), a.BLACK)
    else:
        for ln in _wrap(lead["title"], MF(30), tw, True, 2):
            text(ln, x0, yy, MF(30), a.BLACK, bold=True)
            yy += MY(34)
        if lead.get("desc"):
            for ln in _wrap(lead["desc"], MF(19), tw, False, 2):
                text(ln, x0, yy + MY(2), MF(19), a.BLACK)
                yy += MY(23)
        if q:
            _draw_qr(q, x1 - qw, y + MY(20))

    # Four more stories in two columns
    top = MY(230)
    graphics.set_pen(a.BLACK)
    graphics.rectangle(x0, top - MY(8), x1 - x0, 2)
    gap = MX(24)
    cw = (x1 - x0 - gap) // 2
    rh = (HEIGHT - MY(6) - top) // 2
    for i, st in enumerate(stories[1:5]):
        cx = x0 + (i % 2) * (cw + gap)
        cy = top + (i // 2) * rh
        if i % 2:
            graphics.set_pen(a.BLACK)
            graphics.rectangle(cx - gap // 2, cy, 1, rh - MY(10))
        if i == 2 or i == 3:
            graphics.set_pen(a.BLACK)
            for xx in range(cx, cx + cw, 3):
                graphics.pixel(xx, cy - MY(6))
        _header_line(st, cx, cx + cw, cy)
        if "error" in st:
            text("Couldn't load this feed", cx, cy + MY(24), MF(19), a.BLACK)
            continue
        q = _qr_size(st.get("link"), rh - MY(30))
        qw = (q[1] + 4) * q[2] if q else 0
        tw = cw - (qw + MX(10) if q else 0)
        yy = cy + MY(22)
        for ln in _wrap(st["title"], MF(21), tw, True, 3):
            text(ln, cx, yy, MF(21), a.BLACK, bold=True)
            yy += MY(25)
        if q:
            _draw_qr(q, cx + cw - qw, cy + MY(20))


def draw():
    a = _app
    _setup()
    gc.collect()
    if a._vector is None:
        a._vector = a._has_vector_font(a._vfont())
    try:
        _draw_screen()
    except MemoryError:
        if a.FONT != "original" or a._bmp_failed:
            raise
        a._bmp_failed = True        # not enough memory for the pre-rendered font
        a._bmp_close()
        gc.collect()
        _draw_screen()
    a._bmp_close()
    gc.collect()
    graphics.update()
