"""
Weather app code for the Inky Frame launcher. Your settings are in weather.py,
which passes them in here before every update. Icons and fonts are read from
the SD card (/sd/icons, /sd/fonts) if it has them, otherwise from the Pico.

This file goes on the Pico pre-compiled, as weather_app.mpy, so the Pico doesn't
run out of memory compiling it. To change it, edit this source and rebuild with
mpy-cross 1.29 (the firmware's MicroPython version):
    pip install mpy-cross==1.29.0
    mpy-cross weather_app.py
The defaults below are only used if weather.py doesn't set something.
"""

import gc
import math
import os
import struct
import time

import jpegdec
import network
try:
    import requests
except ImportError:  # older firmware
    import urequests as requests

# ---------------------------------------------------------------
#  Settings - edit these
# ---------------------------------------------------------------

LATITUDE = 55.55
LONGITUDE = -45.45
TIMEZONE = "America/Chicago"   # IANA name, e.g. "Europe/London"
TIMEZONE_LABEL = None          # None = use Open-Meteo's abbreviation, or e.g. "CST"

# Screen design: "modern" (made for the 7.3" screen) or "classic" (the Pi layout)
LAYOUT = "modern"

# Main units for the modern layout: "F" (degF, mph) or "C" (degC, km/h).
# The other temperature unit is still shown next to the big reading.
UNITS = "F"

# Times as "9:15 PM" (False) or "21:15" (True)
CLOCK_24H = False

# Place name for the header bar, e.g. "Chicago". "" leaves it out.
LOCATION_NAME = ""

# Show the moon phase (worked out on the Pico, no internet needed)
SHOW_MOON = True

# Show every temperature in both units: °F beside °C (or °C beside °F)
SHOW_BOTH_UNITS = True

# How many days the forecast at the bottom shows: 4 or 3
FORECAST_DAYS = 4

# Grey "seas" on the moon's lit part (black dots on the white moon)
MOON_SPOTS = True

# Battery icon in the top band: "auto" works out alkaline or rechargeable
# from the voltage of new batteries; or set "alkaline" / "rechargeable"
SHOW_BATTERY = True
BATTERY_TYPE = "auto"
SHOW_BATTERY_VOLTS = True    # the voltage beside the icon (handy for checking)

# Severe weather alerts from the US National Weather Service (US locations only)
SHOW_ALERTS = True

# Muslim prayer times in place of the 12-hour chart (modern layout)
SHOW_PRAYER_TIMES = True
PRAYER_METHOD = "ISNA"         # see prayers.py for the list
ASR_METHOD = "hanafi"          # "hanafi" or "standard"
PRAYER_ADJUST = {}             # e.g. {"Fajr": 2, "Isha": -1} minutes, to match your mosque
HIJRI_ADJUST = 0               # days to shift the Hijri date, to match local moon sighting
HIJRI_FROM_MAGHRIB = True      # the Islamic day (and Hijri date) begins at Maghrib

# Font for all text:
#   "original"  - your Pi's PT Serif, pre-rendered into the /fonts folder
#   "serif", "sans", "serif_italic", "gothic", "cursive" - built-in vector fonts
#   "bitmap"    - built-in pixel font
FONT = "original"

# Minutes between updates (60 = hourly, like the old cron job), and how
# soon to try again if the download fails. Both must be 255 or less.
UPDATE_MINUTES = 60
RETRY_MINUTES = 10

# ---------------------------------------------------------------
#  Set by the launcher
# ---------------------------------------------------------------

graphics = None
WIDTH = None
HEIGHT = None

# The launcher reads this after each draw() to decide how long to sleep
UPDATE_INTERVAL = UPDATE_MINUTES

# The seven colours the panel can show natively (same as inky_frame.BLACK etc.)
BLACK = 0
WHITE = 1
GREEN = 2
BLUE = 3
RED = 4
YELLOW = 5
ORANGE = 6

# icons/ and fonts/ can be on the SD card (best: plenty of room, and you can
# copy them with your computer) or on the Pico itself. The SD card wins.
_dirs = {}
_sd_tried = False


def _mount_sd():
    """Mount the Inky Frame's SD card at /sd (pins from Pimoroni's examples).
    Done when drawing, after the downloads: mounting it before an HTTPS
    request can run the Pico out of memory."""
    global _sd_tried
    if _sd_tried:
        return
    _sd_tried = True
    try:
        os.stat("/sd")
        return                              # already mounted
    except OSError:
        pass
    try:
        import sdcard
        from machine import SPI, Pin
        spi = SPI(0, sck=Pin(18, Pin.OUT), mosi=Pin(19, Pin.OUT), miso=Pin(16, Pin.OUT))
        os.mount(sdcard.SDCard(spi, Pin(22)), "/sd")
        print("SD card mounted")
    except Exception as e:
        print("No SD card:", e)


def asset_dir(name):
    """'/sd/icons' if the SD card has that folder, otherwise '/icons'."""
    d = _dirs.get(name)
    if d is None:
        _mount_sd()
        d = "/" + name
        try:
            os.stat("/sd/" + name)
            d = "/sd/" + name
        except OSError:
            pass
        print("Using", d)
        _dirs[name] = d
    return d

FAIL_FILE = "/weather_fails.txt"
DEG = "\xb0"  # the degree sign - drawn as a small circle, the fonts don't have one

# ---------------------------------------------------------------
#  Weather codes (same as the Pi version)
# ---------------------------------------------------------------

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Cloudy",
    45: "Fog and depositing rime",
    48: "Fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with\nslight hail",
    99: "Thunderstorm with\nheavy hail",
}

WEATHER_ICONS = {
    0: "clear",
    1: "mostlyclear",
    2: "mostlyclear",
    3: "cloudy",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    56: "drizzle",
    57: "drizzle",
    61: "rain",
    63: "rain",
    65: "rain",
    66: "snow",
    67: "snow",
    71: "snow",
    73: "snow",
    75: "snow",
    77: "snow",
    80: "rain",
    81: "rain",
    82: "rain",
    85: "snow",
    86: "snow",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm",
}

DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTHS_FULL = ("January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December")
COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")

# Filled in by update(), used by draw()
weather = None
error = None

# ---------------------------------------------------------------
#  Small helpers (MicroPython has no datetime module)
# ---------------------------------------------------------------


def day_name(date_str):
    """'2026-11-21' -> 'Saturday' (Sakamoto's day-of-week method)."""
    y = int(date_str[0:4])
    m = int(date_str[5:7])
    d = int(date_str[8:10])
    t = (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)
    if m < 3:
        y -= 1
    return DAYS[(y + y // 4 - y // 100 + y // 400 + t[m - 1] + d) % 7]


def cardinal_direction(deg):
    return COMPASS[int(deg / 22.5 + 0.5) % 16]


def to_int(value):
    return None if value is None else int(round(value))


def to_text(value, default="--"):
    return default if value is None else str(value)


def c_to_f(c):
    return int(round(c * 1.8 + 32))


def describe(code):
    return WEATHER_CODES.get(code, "Unknown")


def icon_for(code):
    return WEATHER_ICONS.get(code, "cloudy")


def _read_fails():
    """Failed updates in a row; -1 if the weather has never shown yet."""
    try:
        with open(FAIL_FILE) as f:
            return int(f.read())
    except Exception:
        return -1


def _write_fails(n):
    try:
        with open(FAIL_FILE, "w") as f:
            f.write(str(n))
    except Exception:
        pass


# ---------------------------------------------------------------
#  Network + Open-Meteo
# ---------------------------------------------------------------

def ensure_wifi(timeout_s=30):
    """The launcher connects first; this retries for longer if that failed."""
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        return
    from secrets import WIFI_SSID, WIFI_PASSWORD
    print("Wi-Fi not connected yet, trying again...")
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    start = time.ticks_ms()
    while not wlan.isconnected():
        if wlan.status() < 0:
            raise RuntimeError("Wi-Fi failed (status {}) - check secrets.py".format(wlan.status()))
        if time.ticks_diff(time.ticks_ms(), start) > timeout_s * 1000:
            raise RuntimeError("Wi-Fi timed out - check secrets.py")
        time.sleep(0.25)


def build_url():
    # Kept small on purpose: the Pico W has very little RAM to parse JSON with.
    return ("https://api.open-meteo.com/v1/forecast"
            "?latitude={}&longitude={}"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
            "weather_code,wind_speed_10m,wind_direction_10m"
            "&hourly=temperature_2m,precipitation_probability"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max,sunrise,sunset,uv_index_max"
            "&timezone={}&forecast_days=6").format(
                LATITUDE, LONGITUDE, TIMEZONE.replace("/", "%2F"))


_server_date = None   # the "Date" the weather server sent, e.g. "Sun, 22 Nov 2026 15:52:10 GMT"


def _remember_date(r):
    global _server_date
    _server_date = None
    try:
        for k, v in r.headers.items():
            if k.lower() == "date":
                _server_date = v
    except Exception:
        pass


def fetch_weather(attempts=3):
    url = build_url()
    last_error = None
    for attempt in range(attempts):
        gc.collect()
        try:
            r = requests.get(url, timeout=30)
            try:
                if r.status_code != 200:
                    raise RuntimeError("HTTP {}".format(r.status_code))
                _remember_date(r)
                data = r.json()
            finally:
                r.close()
            return data
        except Exception as e:
            last_error = e
            print("Download attempt {} failed: {}".format(attempt + 1, e))
            time.sleep(3)
    raise RuntimeError("Could not download weather: {}".format(last_error))


def parse_weather(data):
    """Pull out only what the screen needs, so the big JSON can be freed."""
    cur = data["current"]
    hourly = data["hourly"]
    daily = data["daily"]

    now = cur["time"]                      # e.g. "2026-11-21T21:15"
    temp_c = to_int(cur["temperature_2m"])
    feels_c = to_int(cur["apparent_temperature"])
    wind_kph = cur["wind_speed_10m"] or 0

    # Highest chance of rain over the next 12 hours
    hour_key = now[:13]                    # "2026-11-21T21"
    times = hourly["time"]
    start = 0
    for i in range(len(times)):
        if times[i].startswith(hour_key):
            start = i
            break
    rain_12h = None
    for v in hourly["precipitation_probability"][start:start + 12]:
        if v is not None and (rain_12h is None or v > rain_12h):
            rain_12h = v

    days = []
    for i in range(1, min(6, len(daily["time"]))):
        days.append({
            "name": day_name(daily["time"][i]),
            "code": daily["weather_code"][i],
            "hi": to_text(to_int(daily["temperature_2m_max"][i])),
            "lo": to_text(to_int(daily["temperature_2m_min"][i])),
            "hi_c": daily["temperature_2m_max"][i],
            "lo_c": daily["temperature_2m_min"][i],
            "rain": to_text(daily["precipitation_probability_max"][i]),
        })

    # The next 12 hours, for the chart: (hour 0-23, temp degC, rain %)
    hours = []
    for i in range(start, min(start + 12, len(times))):
        hours.append((int(times[i][11:13]), hourly["temperature_2m"][i],
                      hourly["precipitation_probability"][i]))

    tz = TIMEZONE_LABEL
    if tz is None:
        tz = data.get("timezone_abbreviation", "")

    return {
        "day": day_name(now[:10]),
        "date": now[8:10],
        "month": MONTHS[int(now[5:7]) - 1],
        "updated": now[11:16],
        "tz": tz,
        "code": cur["weather_code"],
        "temp_c": to_text(temp_c),
        "temp_f": "--" if temp_c is None else str(c_to_f(cur["temperature_2m"])),
        "feels_c": to_text(feels_c),
        "feels_f": "--" if feels_c is None else str(c_to_f(cur["apparent_temperature"])),
        "wind_kph": str(int(round(wind_kph))),
        "wind_mph": str(int(round(wind_kph / 1.609344))),
        "wind_dir": cardinal_direction(cur["wind_direction_10m"] or 0),
        "rain_12h": to_text(rain_12h),
        "days": days,
        "now": now,
        "temp": cur["temperature_2m"],
        "feels": cur["apparent_temperature"],
        "humidity": cur.get("relative_humidity_2m"),
        "wind": wind_kph,
        "hi_c": daily["temperature_2m_max"][0],
        "lo_c": daily["temperature_2m_min"][0],
        "sunrise": daily["sunrise"][0],
        "sunset": daily["sunset"][0],
        "uv": daily["uv_index_max"][0] if "uv_index_max" in daily else None,
        "utc_offset": data.get("utc_offset_seconds", 0),
        "rain_12h_n": rain_12h,
        "hours": hours,
        "alerts": [],
        "prayer": None,
    }


# ---------------------------------------------------------------
#  Severe weather alerts (US National Weather Service)
#
#  Alert texts can be several KB each, too much to parse as JSON on a
#  Pico W, so the reply is read in small pieces and only the few fields
#  we need are picked out.
# ---------------------------------------------------------------

_ALERT_KEYS = (b'"@type":', b'"severity":', b'"ends":', b'"expires":', b'"event":')
_SEVERITY = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3}


def _scan_alerts(stream):
    """Pick event, severity and end time out of each alert.

    Each NWS alert starts with "@type": "wx:Alert", so the fields are grouped
    by that marker whatever order they come in. (If the marker is ever missing,
    an alert ends at its "event" field, which comes after the times in NWS replies.)"""
    alerts = []
    cur = {}
    marked = False
    buf = b""
    while True:
        chunk = stream.read(512)
        if not chunk:
            break
        buf += chunk
        while True:
            best = -1
            key = None
            for k in _ALERT_KEYS:
                i = buf.find(k)
                if i >= 0 and (best < 0 or i < best):
                    best, key = i, k
            if key is None:
                break
            j = best + len(key)
            while j < len(buf) and buf[j] in (32, 9, 10, 13):   # skip spaces
                j += 1
            if j >= len(buf):
                break                          # value not arrived yet
            if buf[j] == 34:                   # a "string" value
                end = buf.find(b'"', j + 1)
                if end < 0:
                    break
                name = key[1:-2].decode()
                value = buf[j + 1:end].decode()
                buf = buf[end + 1:]
                if name == "@type":
                    if value == "wx:Alert":    # a new alert starts here
                        marked = True
                        if "event" in cur:
                            alerts.append(cur)
                        cur = {}
                    continue
                cur[name] = value
                if name == "event" and not marked:
                    alerts.append(cur)
                    cur = {}
            else:                              # null etc.
                buf = buf[j:]
        if len(buf) > 300:
            buf = buf[-300:]                   # keep a tail in case a key was cut in half
    if "event" in cur:
        alerts.append(cur)
    alerts.sort(key=lambda a: _SEVERITY.get(a.get("severity"), 9))
    return alerts


def fetch_alerts():
    url = "https://api.weather.gov/alerts/active?point={:.4f},{:.4f}".format(LATITUDE, LONGITUDE)
    r = requests.get(url, headers={"User-Agent": "InkyFrameWeather/1.0 (Raspberry Pi Pico W)",
                                   "Accept": "application/geo+json"}, timeout=20)
    try:
        if r.status_code != 200:
            raise RuntimeError("HTTP {}".format(r.status_code))
        return _scan_alerts(r.raw)
    finally:
        r.close()


# ---------------------------------------------------------------
#  Moon phase - a simple average-lunar-month calculation, good to
#  within about half a day
# ---------------------------------------------------------------

MOON_NAMES = ("New moon", "Waxing crescent", "First quarter", "Waxing gibbous",
              "Full moon", "Waning gibbous", "Last quarter", "Waning crescent")


def moon_name(phase):
    """New/first quarter/full/last quarter only within a day of the exact moment;
    crescent or gibbous in between."""
    days = phase * 29.530588853
    for target, name in ((0, "New moon"), (7.38, "First quarter"), (14.77, "Full moon"),
                         (22.15, "Last quarter"), (29.53, "New moon")):
        if abs(days - target) <= 1.0:
            return name
    if days < 7.38:
        return "Waxing crescent"
    if days < 14.77:
        return "Waxing gibbous"
    if days < 22.15:
        return "Waning gibbous"
    return "Waning crescent"


def _days_from_civil(y, m, d):
    """Days since 1970-01-01."""
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def moon_phase(now, utc_offset):
    """0 = new, 0.25 = first quarter, 0.5 = full, 0.75 = last quarter."""
    days = (_days_from_civil(int(now[0:4]), int(now[5:7]), int(now[8:10]))
            + (int(now[11:13]) * 60 + int(now[14:16])) / 1440 - utc_offset / 86400)
    # A known new moon: 6 Jan 2000, 18:14 UTC
    return ((days - 10962.7597) % 29.530588853) / 29.530588853


# The moon's near-side seas (maria): centre x, y, half-width, half-height,
# as fractions of the radius (x to the right, y down), as seen from the
# northern hemisphere.
MARIA = (
    (-0.30, -0.45, 0.30, 0.24),   # Sea of Showers (Imbrium)
    (0.20, -0.36, 0.18, 0.16),    # Sea of Serenity
    (0.36, -0.06, 0.22, 0.18),    # Sea of Tranquility
    (0.70, -0.28, 0.11, 0.13),    # Sea of Crises
    (0.56, 0.18, 0.12, 0.16),     # Sea of Fertility
    (0.38, 0.36, 0.09, 0.09),     # Sea of Nectar
    (-0.62, -0.10, 0.22, 0.38),   # Ocean of Storms, north
    (-0.46, 0.26, 0.18, 0.18),    # Ocean of Storms, south
    (-0.16, 0.36, 0.15, 0.12),    # Sea of Clouds
    (-0.48, 0.48, 0.09, 0.08),    # Sea of Moisture
    (0.00, -0.20, 0.09, 0.08),    # Sea of Vapours
    (-0.10, -0.74, 0.30, 0.06),   # Sea of Cold
)


def draw_moon(cx, cy, r, phase, lit, dark, shade, spot=None):
    """Moon as seen from the northern hemisphere. The shadowed side is a
    sparse dot pattern of `shade` on `dark`, which looks grey on e-ink.
    With `spot`, the seas on the lit part are dotted in that colour."""
    k = math.cos(2 * math.pi * phase)
    for dy in range(-r, r + 1):
        hw = math.sqrt(r * r - dy * dy)
        left, right = int(cx - hw + 0.5), int(cx + hw + 0.5)
        if phase < 0.5:
            a, b = hw * k, hw                  # waxing: right side lit
        else:
            a, b = -hw, -hw * k                # waning: left side lit
        x0, x1 = int(cx + a + 0.5), int(cx + b + 0.5)
        y = cy + dy
        graphics.set_pen(dark)
        graphics.rectangle(left, y, right - left + 1, 1)
        graphics.set_pen(shade)
        if y % 2 == 0:
            for x in range(left + (y // 2) % 2, right + 1, 2):
                if not x0 <= x < x1:
                    graphics.pixel(x, y)
        if x1 > x0:
            graphics.set_pen(lit)
            graphics.rectangle(x0, y, x1 - x0, 1)
            if spot is not None:
                graphics.set_pen(spot)
                fy = dy / r
                for sx, sy, rx, ry in MARIA:
                    t = (fy - sy) / ry
                    if -1 < t < 1:
                        h = rx * math.sqrt(1 - t * t) * r
                        s0 = max(x0, int(cx + sx * r - h + 0.5))
                        s1 = min(x1, int(cx + sx * r + h + 0.5))
                        for x in range(s0 + (y + s0) % 2, s1, 2):
                            graphics.pixel(x, y)


# ---------------------------------------------------------------
#  Prayer times (calculated by prayers.py on the Pico)
# ---------------------------------------------------------------

PRAYER_LABELS = {
    "ISNA": "ISNA", "MoonsightingCommittee": "Moonsighting Committee", "MWL": "Muslim World League",
    "Egypt": "Egyptian Authority", "Makkah": "Umm al-Qura", "Karachi": "Karachi", "Tehran": "Tehran",
    "Jafari": "Jafari", "Gulf": "Gulf", "Kuwait": "Kuwait", "Qatar": "Qatar", "Singapore": "Singapore",
    "Dubai": "Dubai", "France": "UOIF France", "Russia": "Russia",
}
_MONTH_ABBR = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _civil_from_days(z):
    """Days since 1970-01-01 -> (year, month, day)."""
    z += 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    return yoe + era * 400 + (m <= 2), m, d


def local_now(fallback, utc_offset):
    """Local time now as 'YYYY-MM-DDTHH:MM', from the weather server's clock
    (exact), or Open-Meteo's 15-minute 'current' time if that's missing."""
    try:
        p = _server_date.split()            # Sun, 22 Nov 2026 15:52:10 GMT
        days = _days_from_civil(int(p[3]), _MONTH_ABBR.index(p[2]) + 1, int(p[1]))
        total = days * 1440 + int(p[4][0:2]) * 60 + int(p[4][3:5]) + utc_offset // 60
        y, m, d = _civil_from_days(total // 1440)
        minute = total % 1440
        return "%04d-%02d-%02dT%02d:%02d" % (y, m, d, minute // 60, minute % 60)
    except Exception:
        return fallback


def prayer_info(now, utc_offset):
    """Today's times (or tomorrow's, once Isha has begun) and which comes next."""
    import prayers
    y, m, d = int(now[0:4]), int(now[5:7]), int(now[8:10])
    minute_now = int(now[11:13]) * 60 + int(now[14:16])
    tz = utc_offset / 3600.0

    def day_times(y, m, d):
        out = []
        times = prayers.prayer_times(y, m, d, LATITUDE, LONGITUDE, tz, PRAYER_METHOD, ASR_METHOD)
        for name, v in zip(prayers.PRAYER_NAMES, times):
            if v is not None:
                v += int(PRAYER_ADJUST.get(name, 0))
            out.append(v)
        return out

    times = day_times(y, m, d)
    # Today's sunrise (as in the prayer row) and sunset, for the details grid
    sun = (times[1], prayers.SUN[1])

    # Hijri date: moves on at Maghrib, when the Islamic day begins
    hdays = _days_from_civil(y, m, d) + int(HIJRI_ADJUST)
    if HIJRI_FROM_MAGHRIB and times[4] is not None and minute_now >= times[4]:
        hdays += 1
    hy, hm, hd = prayers.hijri_date(hdays)
    hijri = "{} {} {} AH".format(hd, prayers.HIJRI_MONTHS[hm - 1], hy)

    tomorrow = times[5] is not None and minute_now >= times[5]
    if tomorrow:
        y, m, d = _civil_from_days(_days_from_civil(y, m, d) + 1)
        times = day_times(y, m, d)
    nxt = until = None
    for i in (0, 2, 3, 4, 5):                # the five prayers (sunrise isn't one)
        v = times[i]
        if v is not None and (tomorrow or v > minute_now):
            nxt, until = i, v - minute_now + (1440 if tomorrow else 0)
            break
    return {"times": times, "names": prayers.PRAYER_NAMES, "next": nxt, "until": until,
            "tomorrow": tomorrow, "hijri": hijri, "sun": sun}


def time_parts(minutes):
    """510 -> ('8:30', 'am'), or ('08:30', '') with the 24-hour clock."""
    if minutes is None:
        return "--:--", ""
    minutes %= 1440
    h, m = minutes // 60, minutes % 60
    if CLOCK_24H:
        return "%02d:%02d" % (h, m), ""
    return "%d:%02d" % (h % 12 or 12, m), ("am" if h < 12 else "pm")


# ---------------------------------------------------------------
#  Text drawing
#
#  The Pi used PT Serif TrueType fonts through PIL. The Pico can't load
#  TTF files, so this uses one of the firmware's built-in vector fonts,
#  sized so the Pi layout's (x, y, font size) numbers still line up.
# ---------------------------------------------------------------

# Built-in vector fonts, and how much to shrink each one so its text is
# about as wide as PT Serif was (they're all wider than PT Serif).
VECTOR_FONTS = {
    "serif": 36,
    "serif_italic": 37,
    "sans": 34,
    "gothic": 33,
    "cursive": 34,
}

_vector = None   # True/False once checked (needs the graphics object)


def _vfont():
    """Vector font to use (falls back to serif if FONT isn't a vector font)."""
    return FONT if FONT in VECTOR_FONTS else "serif"


# ---- "original" font: pre-rendered bitmaps made by tools/make_font.py ----

_bmp_sizes = None   # {"r": {size: (offset, length)}, "b": {...}}
_bmp_cache = {}     # (style, size) -> (index bytes, glyph count, data start, style)
_bmp_files = {}     # style -> open font file, kept open while drawing
_bmp_buf = bytearray(512)   # one letter's bitmap (the biggest is under 500 bytes)
_bmp_failed = False         # out of memory once -> use the built-in font


def _bmp_list():
    """Sizes in fonts/original_r.bin and original_b.bin (made by tools/make_font.py)."""
    global _bmp_sizes
    if _bmp_sizes is None:
        _bmp_sizes = {"r": {}, "b": {}}
        for style in ("r", "b"):
            try:
                with open("{}/original_{}.bin".format(asset_dir("fonts"), style), "rb") as fh:
                    head = fh.read(5)
                    if head[:4] == b"FNP1":
                        table = fh.read(9 * head[4])
                        for i in range(head[4]):
                            size, off, length = struct.unpack_from("<BII", table, i * 9)
                            _bmp_sizes[style][size] = (off, length)
            except OSError:
                pass
    return _bmp_sizes


def _bmp_file(style):
    fh = _bmp_files.get(style)
    if fh is None:
        fh = open("{}/original_{}.bin".format(asset_dir("fonts"), style), "rb")
        _bmp_files[style] = fh
    return fh


def _bmp_close():
    for fh in _bmp_files.values():
        try:
            fh.close()
        except Exception:
            pass
    _bmp_files.clear()
    _bmp_cache.clear()


def _bmp_load(style, size):
    """Only the index (under 1 KB) is kept in memory; letters are read from
    the file as they're drawn. (Loading whole sizes ran a Pico W out of RAM.)"""
    key = (style, size)
    f = _bmp_cache.get(key)
    if f is None:
        if len(_bmp_cache) >= 16:
            _bmp_cache.clear()
        off, length = _bmp_list()[style][size]
        fh = _bmp_file(style)
        fh.seek(off)
        head = fh.read(6)
        count = head[5]
        f = (fh.read(count * 10), count, off + 6 + count * 10, style)
        _bmp_cache[key] = f
    return f


def _glyph(f, cp):
    """(code, advance x16, x offset, y offset, width, height, data offset) or None."""
    index, count = f[0], f[1]
    if count == 96:                     # full set: characters 32-126, then the degree sign
        i = cp - 32 if 32 <= cp <= 126 else (95 if cp == 176 else -1)
        if i >= 0:
            g = struct.unpack_from("<HHbBBBH", index, i * 10)
            if g[0] == cp:
                return g
    for i in range(count):              # small sets (big digits), or anything unusual
        g = struct.unpack_from("<HHbBBBH", index, i * 10)
        if g[0] == cp:
            return g
    return None


def _bmp_font(size, bold, txt):
    """Largest pre-rendered size <= size that has every character in txt."""
    if FONT != "original" or _bmp_failed:
        return None
    style = "b" if bold else "r"
    sizes = sorted(_bmp_list()[style])
    if not sizes:
        return None
    for s in reversed(sizes):
        if s <= size + 0.01 or s == sizes[0]:
            f = _bmp_load(style, s)
            ok = True
            for ch in txt:
                if _glyph(f, ord(ch)) is None:
                    ok = False
                    break
            if ok:
                return f
    return None


def _bmp_width(f, txt):
    w = 0
    for ch in txt:
        g = _glyph(f, ord(ch))
        if g:
            w += g[1]
    return (w + 8) // 16


def _bmp_draw(f, txt, x, y):
    global _bmp_buf
    fh = _bmp_file(f[3])
    base = f[2]
    pen = x * 16
    for ch in txt:
        g = _glyph(f, ord(ch))
        if not g:
            continue
        _, adv, xo, yo, w, h, off = g
        rb = (w + 7) >> 3
        n = rb * h
        if n:
            if n > len(_bmp_buf):
                _bmp_buf = bytearray(n)
            buf = _bmp_buf
            fh.seek(base + off)
            fh.readinto(memoryview(buf)[:n])
            gx = (pen + 8) // 16 + xo
            gy = y + yo
            p = 0
            for r in range(h):
                run = -1
                for c in range(w):
                    if buf[p + (c >> 3)] & (0x80 >> (c & 7)):
                        if run < 0:
                            run = c
                    elif run >= 0:
                        graphics.rectangle(gx + run, gy + r, c - run, 1)
                        run = -1
                if run >= 0:
                    graphics.rectangle(gx + run, gy + r, w - run, 1)
                p += rb
        pen += adv


def _has_vector_font(name):
    if name not in VECTOR_FONTS:
        return False
    try:
        graphics.set_font("bitmap8")
        bitmap_w = graphics.measure_text("W", scale=1)
        graphics.set_font(name)
        return graphics.measure_text("W", scale=1) != bitmap_w
    except Exception:  # newer firmware raises ValueError for vector fonts
        return False


def _use_font(size, bold):
    """Select a font to stand in for PT Serif at `size` (as used with PIL).

    Returns (scale, y_offset, cap_top, cap_height): y_offset is where to put
    the font's own origin and cap_top where its capitals start, both measured
    down from the PIL-style top-of-line y.
    """
    # Below ~20px the vector fonts get blotchy ("a" looks like "o"), so small
    # text uses the crisp built-in pixel font instead
    if _vector and size >= 20:
        graphics.set_font(_vfont())
        weight = 0.085 if bold else 0.05
        graphics.set_thickness(max(1, int(size * weight + 0.5)))
        # Drawn a bit smaller than PT Serif (keeps the layout from
        # overlapping) and centred on where PT Serif's capitals were
        # (0.34-1.04 x size below the top of the line).
        scale = size / VECTOR_FONTS[_vfont()]
        cap_h = 21 * scale                      # glyphs span -12..+9 units
        cap_top = size * 0.34 + (size * 0.70 - cap_h) / 2
        return scale, int(cap_top + 12 * scale + 0.5), int(cap_top + 0.5), cap_h
    graphics.set_font("bitmap8")
    graphics.set_thickness(1)
    scale = max(1, int(size / 11 + 0.5))
    cap_top = int(size * 0.34 + 0.5)
    return scale, cap_top, cap_top, 7 * scale


def _deg_size(cap_h):
    r = max(2, int(cap_h * 0.2 + 0.5))
    gap = max(1, int(cap_h * 0.06 + 0.5))
    return r, gap


def text_width(txt, size, bold=False):
    f = _bmp_font(size, bold, txt)
    if f:
        return _bmp_width(f, txt)
    scale, _, _, cap_h = _use_font(size, bold)
    r, gap = _deg_size(cap_h)
    width = 0
    parts = txt.split(DEG)
    for i in range(len(parts)):
        if i:
            width += 2 * r + 2 * gap
        if parts[i]:
            width += graphics.measure_text(parts[i], scale=scale)
    return width


def _draw_degree(x, y, size, bold, colour, bg=WHITE):
    _, _, cap_top, cap_h = _use_font(size, bold)
    r, gap = _deg_size(cap_h)
    ring = max(1, int(cap_h * (0.13 if bold else 0.08) + 0.5))
    cx = x + gap + r
    cy = y + cap_top + r                        # sits at the top of the capitals
    graphics.set_pen(colour)
    graphics.circle(cx, cy, r)
    graphics.set_pen(bg)
    graphics.circle(cx, cy, max(0, r - ring))
    graphics.set_pen(colour)
    return 2 * r + 2 * gap


def _wrap(txt, size, bold, max_width):
    """Break a line at a space if it's too wide for its column."""
    if max_width is None or text_width(txt, size, bold) <= max_width:
        return [txt]
    line = ""
    lines = []
    for w in txt.split(" "):
        trial = w if not line else line + " " + w
        if line and text_width(trial, size, bold) > max_width:
            lines.append(line)
            line = w
        else:
            line = trial
    lines.append(line)
    return lines


def draw_text(txt, x, y, size, colour, bold=False, right=False, max_width=None, center=False, bg=WHITE):
    """Like PIL's draw.text((x, y), txt, font=PT Serif at `size`).

    right=True behaves like anchor="ra" (x is the right-hand edge).
    Returns the width of the (last) line drawn.
    """
    lines = []
    for part in txt.split("\n"):
        lines.extend(_wrap(part, size, bold, max_width))

    w = 0
    for line in lines:
        w = text_width(line, size, bold)
        lx = x - w if right else (x - w // 2 if center else x)
        f = _bmp_font(size, bold, line)
        if f:
            graphics.set_pen(colour)
            _bmp_draw(f, line, int(lx), int(y))
            y += int(size * 1.2)
            continue
        scale, y_off, _, _ = _use_font(size, bold)
        graphics.set_pen(colour)
        parts = line.split(DEG)
        for i in range(len(parts)):
            if i:
                lx += _draw_degree(lx, y, size, bold, colour, bg)
            if parts[i]:
                graphics.text(parts[i], int(lx), int(y + y_off), scale=scale)
                lx += graphics.measure_text(parts[i], scale=scale)
        y += int(size * 1.2)
    return w


_jpeg = None


def draw_icon(name, size, x, y):
    global _jpeg
    if _jpeg is None:
        _jpeg = jpegdec.JPEG(graphics)
    try:
        _jpeg.open_file("{}/{}_{}.jpg".format(asset_dir("icons"), name, size))
        # Icons are pre-dithered to the panel's 7 colours, so no dithering here
        _jpeg.decode(x, y, jpegdec.JPEG_SCALE_FULL, dither=False)
    except Exception as e:
        print("Icon {} ({}px) failed: {}".format(name, size, e))


# ---------------------------------------------------------------
#  Screen layout
#
#  Same design as the Pi's 600x448 screen. Positions are written in
#  those coordinates and stretched to fit: X() across the screen,
#  Y() down it, and F() for font and icon sizes.
# ---------------------------------------------------------------

def X(v):
    return int(v * WIDTH / 600 + 0.5)


def Y(v):
    # On the 7.3" spread the rows a little further apart to use the extra height
    return int(v * HEIGHT / 448 * (1.07 if HEIGHT >= 480 else 1.0) + 0.5)


def F(size):
    # Grow text with the screen height, plus a little extra on wider screens
    return size * HEIGHT / 448 * (1.08 if WIDTH >= 800 else 1.0)


def icon_size(v):
    return int(v * HEIGHT / 448)   # 7.3": 128 / 64 / 37 px


def draw_weather(w):
    graphics.set_pen(WHITE)
    graphics.clear()

    # Date
    draw_text(w["day"], X(15), Y(5), F(50), BLACK)
    draw_text(w["month"], WIDTH - X(75), Y(5), F(50), BLUE, bold=True, right=True)
    draw_text(w["date"], WIDTH - X(10), Y(5), F(50), ORANGE, bold=True, right=True)
    draw_text("As of: " + w["updated"] + " " + w["tz"], WIDTH - X(10), Y(78), F(15), BLACK, right=True)

    # Current conditions
    draw_text(describe(w["code"]), X(15), Y(65), F(28), GREEN, bold=True)
    big_w = draw_text(w["temp_c"] + DEG + "C", X(15), Y(118), F(83), RED, bold=True)
    draw_text("/" + w["temp_f"] + DEG + "F", X(15) + big_w + X(10), Y(155), F(45), BLACK)
    draw_icon(icon_for(w["code"]), icon_size(120), X(415), Y(105))

    # Feels like
    draw_text("Feels like", X(15), Y(220), F(25), BLACK, bold=True)
    feels_w = draw_text(w["feels_c"] + DEG + "C", X(15), Y(245), F(30), RED)
    draw_text("/" + w["feels_f"] + DEG + "F", X(15) + feels_w, Y(245), F(30), BLACK)

    # Chance of rain over the next 12 hours
    draw_text("Precipitation", WIDTH - X(20), Y(220), F(25), BLACK, bold=True, right=True)
    draw_text("chance", WIDTH - X(20), Y(250), F(25), BLACK, right=True)
    draw_text(w["rain_12h"] + "%", WIDTH - X(105), Y(245), F(30), GREEN, right=True)

    # Wind
    label_w = draw_text("Wind", X(220), Y(220), F(25), BLACK, bold=True)
    icon_x = X(220) + label_w + 5
    draw_icon("wind", icon_size(35), icon_x, Y(218))
    draw_text("(" + w["wind_dir"] + ")", icon_x + icon_size(35) + 2, Y(218), F(25), GREEN, bold=True)
    kph_w = draw_text(w["wind_kph"] + "Kph", X(220), Y(245), F(30), RED)
    draw_text("/" + w["wind_mph"] + "Mph", X(220) + kph_w, Y(245), F(30), BLACK)

    # Next three days
    for i, x in enumerate((15, 220, 420)):
        d = w["days"][i]
        x = X(x)
        draw_text(d["name"], x, Y(290), F(25), BLACK, bold=True)
        draw_icon(icon_for(d["code"]), icon_size(60), x - 5, Y(320))
        draw_text(d["hi"] + DEG + "C/" + d["lo"] + DEG + "C", x + icon_size(60), Y(320), F(20), RED, bold=True)
        draw_text(d["rain"] + "% chance", x + icon_size(60), Y(340), F(20), BLACK)
        draw_text(describe(d["code"]), x, Y(370), F(18), BLACK, max_width=min(X(190), WIDTH - x - X(8)))


# ---------------------------------------------------------------
#  Modern layout - designed for the 7.3" 800x480 screen
#
#  +--------------------------------------------------------------+
#  | Saturday, November 21                      Updated 9:15 PM   |  header band
#  | [icon]  26°F  -3°C        High / Low    Rain, next 12 h      |
#  |         Moderate rain     Wind          Humidity             |  now
#  |         Feels like 15°    Sunrise       Sunset               |
#  |--------------------------------------------------------------|
#  | Next 12 hours: temperature line + rain chance bars           |  chart
#  |--------------------------------------------------------------|
#  |  Sun   |   Mon   |   Tue   |   Wed   |   Thu                 |  5 days
#  +--------------------------------------------------------------+
# ---------------------------------------------------------------

def MX(v):
    return int(v * WIDTH / 800 + 0.5)


def MY(v):
    return int(v * HEIGHT / 480 + 0.5)


def MF(size):
    return size * HEIGHT / 480


def temp_in(c, unit):
    return c if unit == "C" else c * 1.8 + 32


def deg(c, unit=None, show_unit=False):
    """-3.4 (degC) -> '26°' in the chosen units."""
    if c is None:
        return "--"
    u = unit or UNITS
    return str(int(round(temp_in(c, u)))) + DEG + (u if show_unit else "")


def other_unit():
    return "C" if UNITS == "F" else "F"


def unit_colour(u):
    """High/low temperatures: °C in red, °F in blue."""
    return RED if u == "C" else BLUE


def both(c):
    """-10.2 (degC) -> '-10°C (14°F)' when SHOW_BOTH_UNITS, else '-10°C'."""
    if SHOW_BOTH_UNITS and c is not None:
        return deg(c, show_unit=True) + " (" + deg(c, other_unit(), True) + ")"
    return deg(c, show_unit=True)


def hi_lo_other(hi_c, lo_c, spaced=True):
    """'48 / 36°F': the high and low in the other unit."""
    u = other_unit()
    sep = " / " if spaced else "/"
    return deg(hi_c, u).rstrip(DEG) + sep + deg(lo_c, u, True)


def temp_colour(c):
    if c is None:
        return BLACK
    if c <= 0:
        return BLUE       # freezing
    if c < 16:
        return GREEN      # cool
    if c < 27:
        return ORANGE     # warm
    return RED            # hot


def clock(t):
    """'2026-11-21T06:48' -> '6:48 AM' (or '06:48')."""
    if CLOCK_24H:
        return t[11:16]
    h = int(t[11:13])
    return "{}:{} {}".format(h % 12 or 12, t[14:16], "AM" if h < 12 else "PM")


def clock_minutes(m):
    """406 (minutes after midnight) -> '6:46 AM' (or '06:46')."""
    h, mm = (m // 60) % 24, m % 60
    if CLOCK_24H:
        return "%02d:%02d" % (h, mm)
    return "%d:%02d %s" % (h % 12 or 12, mm, "AM" if h < 12 else "PM")


def hour_label(h):
    if CLOCK_24H:
        return "%02d:00" % h
    return "{}{}".format(h % 12 or 12, "am" if h < 12 else "pm")


def wind_text(w):
    kph = w["wind"]
    speed = int(round(kph / 1.609344)) if UNITS == "F" else int(round(kph))
    return "{} {} {}".format(speed, "mph" if UNITS == "F" else "km/h", w["wind_dir"])


def draw_wind(w, x, y, width, top=None, measure=False):
    """'21 km/h (13 mph)': the speed in the chosen units in bold, then the
    other unit in brackets a little smaller, shrunk together to fit. `top` is
    the largest size to try; with measure=True it only returns the size."""
    kph = w["wind"]
    km = "{} km/h".format(int(round(kph)))
    mi = "{} mph".format(int(round(kph / 1.609344)))
    main, extra = (mi, km) if UNITS == "F" else (km, mi)
    extra = " (" + extra + ")"
    size = top or MF(27)
    for _ in range(4):
        small = max(MF(17), size * 0.72)
        total = text_width(main, size, True) + text_width(extra, small)
        if total <= width or size <= MF(17):
            break
        size = max(MF(17), min(size - 1, size * width / total))
    if measure:
        return size
    x += draw_text(main, x, y, size, BLACK, bold=True)
    draw_text(extra, x, y + int((size - small) * 1.04), small, BLACK)


def fit(txt, size, max_width, bold=False, smallest=16):
    """Largest font size <= size at which txt fits in max_width (usually 1-2 tries)."""
    w = text_width(txt, size, bold)
    while size > smallest and w > max_width:
        size = max(smallest, min(size - 1, size * max_width / w))
        w = text_width(txt, size, bold)
    return size


def uv_word(u):
    if u is None:
        return ""
    u = int(round(u))
    for limit, word in ((2, "Low"), (5, "Moderate"), (7, "High"), (10, "Very high")):
        if u <= limit:
            return word
    return "Extreme"


def uv_text(u):
    if u is None:
        return "--"
    return "{} {}".format(int(round(u)), uv_word(u))


UV_SHORT = {"Moderate": "Mod.", "Very high": "V. high", "Extreme": "Ext."}


def draw_uv_humidity(w, x, y, width, top=None, measure=False):
    """'1 (Low) / 88%': the UV number and its level in the UV colour (the
    level a little smaller), a black '/', then the humidity in its own colour. Shrinks to fit, and only
    shortens the level ('Mod.') if it still doesn't fit. `top` is the largest
    size to try; with measure=True it only returns the size it would use."""
    u = w["uv"]
    num = "--" if u is None else str(int(round(u)))
    word = uv_word(u)
    hum = to_text(w["humidity"]) + "%"
    col = uv_colour(u)
    for short in (False, True):
        cat = ""
        if word:
            cat = " (" + (UV_SHORT.get(word, word) if short else word) + ")"
        size = top or MF(27)
        for _ in range(4):
            small = max(MF(17), size * 0.72)
            total = text_width(num, size, True) + text_width(cat, small) + text_width(" / " + hum, size, True)
            if total <= width or size <= MF(17):
                break
            size = max(MF(17), min(size - 1, size * width / total))
        if total <= width:
            break
    if measure:
        return size
    x += draw_text(num, x, y, size, col, bold=True)
    if cat:
        x += draw_text(cat, x, y + int((size - small) * 1.04), small, col)
    x += draw_text(" / ", x, y, size, BLACK, bold=True)
    draw_text(hum, x, y, size, humidity_colour(w["humidity"]), bold=True)


def humidity_colour(h):
    """Orange when dry (under 30%), green when comfortable (30-60%), blue when
    humid (over 60%)."""
    if h is None:
        return BLACK
    if h < 30:
        return ORANGE
    return GREEN if h <= 60 else BLUE


def uv_colour(u):
    """Green for Low (0-2), orange for Moderate and High (3-7), red for Very
    high and Extreme (8+), going by the same rounded number that is shown."""
    if u is None:
        return GREEN
    u = int(round(u))
    if u <= 2:
        return GREEN
    return ORANGE if u <= 7 else RED


def alert_text(alerts, with_time=True):
    a = alerts[0]
    t = a.get("ends") or a.get("expires") or ""
    txt = a.get("event", "Weather alert")
    if with_time and len(t) >= 16:
        txt += " until " + day_name(t[:10])[:3] + " " + clock(t)
    if len(alerts) > 1:
        txt += "  (+{} more)".format(len(alerts) - 1)
    return txt


def draw_alert_banner(alerts, x0, x1, y, h):
    graphics.set_pen(RED)
    graphics.rectangle(x0, y, x1 - x0, h)
    # Warning triangle with "!"
    t = h - MY(6)
    tx, ty = x0 + MX(10), y + MY(3)
    graphics.set_pen(WHITE)
    graphics.triangle(tx + t // 2, ty, tx, ty + t, tx + t, ty + t)
    graphics.set_pen(RED)
    graphics.rectangle(tx + t // 2 - 1, ty + t // 3, 3, t // 3 + 1)
    graphics.rectangle(tx + t // 2 - 1, ty + t - t // 6 - 2, 3, 3)
    txt = alert_text(alerts)
    x = tx + t + MX(12)
    room = x1 - x - MX(10)
    if text_width(txt, MF(17), True) > room:
        # Narrow banner: leave out the end time, then words, until it fits
        txt = alert_text(alerts, False)
        while " " in txt and text_width(txt, MF(17), True) > room:
            txt = txt.rsplit(" ", 1)[0]
    draw_text(txt, x, y + (h - MF(21) * 1.25) // 2, fit(txt, MF(21), room, bold=True, smallest=MF(17)),
              WHITE, bold=True, bg=RED)


def draw_hourly(hours, x0, x1, line_top, line_bottom, bar_bottom, bar_height):
    n = len(hours)
    if n == 0:
        return
    slot = (x1 - x0) / n
    bar_w = max(4, int(slot * 0.45))
    temps = [temp_in(t, UNITS) for _, t, _ in hours if t is not None]
    t_lo = min(temps) if temps else 0
    t_hi = max(temps) if temps else 1
    if t_hi - t_lo < 4:                 # keep a nearly flat day looking flat
        mid = (t_hi + t_lo) / 2
        t_lo, t_hi = mid - 2, mid + 2

    # Rain chance bars, with a baseline
    for i in range(n):
        p = hours[i][2]
        if p:
            cx = int(x0 + slot * (i + 0.5))
            bh = max(2, int(bar_height * p / 100))
            graphics.set_pen(BLUE)
            graphics.rectangle(cx - bar_w // 2, bar_bottom - bh, bar_w, bh)
    graphics.set_pen(BLACK)
    graphics.rectangle(x0, bar_bottom, x1 - x0, 2)

    # Temperature line
    points = []
    for i in range(n):
        t = hours[i][1]
        if t is None:
            continue
        v = temp_in(t, UNITS)
        y = int(line_bottom - (v - t_lo) / (t_hi - t_lo) * (line_bottom - line_top))
        points.append((int(x0 + slot * (i + 0.5)), y, i, t))
    graphics.set_pen(RED)
    for a, b in zip(points, points[1:]):
        graphics.line(a[0], a[1], b[0], b[1], 3)
    for x, y, i, t in points:
        graphics.set_pen(RED)
        graphics.circle(x, y, 5)
        graphics.set_pen(WHITE)
        graphics.circle(x, y, 2)
        if i % 2 == 0:
            draw_text(deg(t, show_unit=True), x, y - MY(30), MF(18), BLACK, bold=True, center=True)

    # Hour labels under the bars
    for i in range(0, n, 2):
        cx = int(x0 + slot * (i + 0.5))
        draw_text(hour_label(hours[i][0]), cx, bar_bottom + MY(2), MF(17), BLACK, center=True)


def draw_modern(w):
    graphics.set_pen(WHITE)
    graphics.clear()

    # Header band
    graphics.set_pen(BLACK)
    graphics.rectangle(0, 0, WIDTH, MY(54))
    now = w["now"]
    date = "{}, {} {}".format(day_name(now[:10]), MONTHS_FULL[int(now[5:7]) - 1], int(now[8:10]))
    updated = "Updated " + clock(now)
    if SHOW_MOON:
        # Right side: the moon, with its phase name above the update time
        phase = moon_phase(now, w["utc_offset"])
        name = moon_name(phase)
        tw = max(text_width(name, MF(17)), text_width(updated, MF(17)))
        draw_text(name, WIDTH - MX(20), MY(5), MF(17), WHITE, right=True, bg=BLACK)
        draw_text(updated, WIDTH - MX(20), MY(27), MF(17), WHITE, right=True, bg=BLACK)
        right_edge = WIDTH - MX(20) - tw - MX(14) - MY(36)
        # White moon; the seas are black dots on white, so they look grey
        draw_moon(right_edge + MY(18), MY(27), MY(19), phase, WHITE, BLACK, WHITE,
                  BLACK if MOON_SPOTS else None)
    else:
        draw_text(updated, WIDTH - MX(20), MY(12), MF(21), WHITE, right=True, bg=BLACK)
        right_edge = WIDTH - MX(20) - text_width(updated, MF(21))
    used = draw_battery(right_edge - MX(12), MY(27))
    if used:
        right_edge -= used + MX(12)
    if LOCATION_NAME:
        loc_size = fit(LOCATION_NAME, MF(34), MX(260), bold=True, smallest=MF(20))
        lw = draw_text(LOCATION_NAME, MX(20), MY(4), loc_size, WHITE, bold=True, bg=BLACK)
        x = MX(20) + lw + MX(16)
        draw_text(date, x, MY(4) + int((loc_size - MF(24)) * 1.04),
                  fit(date, MF(24), right_edge - x - MX(10), smallest=MF(17)), WHITE, bg=BLACK)
    else:
        draw_text(date, MX(20), MY(4), fit(date, MF(34), right_edge - MX(30), bold=True, smallest=MF(20)),
                  WHITE, bold=True, bg=BLACK)

    # With prayer times and both units, the details grid is taller (High / Low
    # gets a line in the other unit) and the prayer row is a little shorter
    prayer = w.get("prayer") if SHOW_PRAYER_TIMES else None
    tall = bool(prayer) and SHOW_BOTH_UNITS
    extra = MY(22) if tall else 0           # added to the details grid
    dy = MY(10) if tall else 0              # current conditions move down to stay centred

    # Now: icon, big temperature, conditions
    draw_icon(icon_for(w["code"]), icon_size(120), MX(18), MY(70) + dy)
    # Big reading plus the other unit, shrunk if needed to stay clear of the details grid
    big = deg(w["temp"], show_unit=True)
    small = deg(w["temp"], other_unit(), show_unit=True)
    room = MX(466) - MX(162)
    small_w = text_width(small, MF(36))
    size = fit(big, MF(92), room - small_w - MX(14), bold=True, smallest=MF(60))
    big_w = draw_text(big, MX(162), MY(52) + dy + int((MF(92) - size) * 0.7), size,
                      temp_colour(w["temp"]), bold=True)
    draw_text(small, MX(162) + big_w + MX(14), MY(96) + dy, MF(36), BLACK)

    desc = describe(w["code"]).replace("\n", " ")
    draw_text(desc, MX(166), MY(146) + dy, fit(desc, MF(30), room, bold=True, smallest=MF(18)), GREEN, bold=True)
    draw_text("Feels like " + both(w["feels"]), MX(166), MY(182) + dy, MF(24), BLACK)

    # Details grid (with prayer times showing, sunrise is in their row, so
    # the rain chance from the chart takes its place)
    hi_lo_label = "High / Low"
    if SHOW_BOTH_UNITS and not tall:
        # 'Hi / Lo (48 / 36°F)', tighter if the font is wide, plain if neither fits
        for label in ("Hi / Lo (" + hi_lo_other(w["hi_c"], w["lo_c"]) + ")",
                      "Hi/Lo (" + hi_lo_other(w["hi_c"], w["lo_c"], False) + ")"):
            if text_width(label, MF(17)) <= MX(156):
                hi_lo_label = label
                break
    hi_lo = (hi_lo_label, deg(w["hi_c"], show_unit=True) + " / " + deg(w["lo_c"], show_unit=True),
             unit_colour(UNITS))
    if SHOW_BOTH_UNITS:
        # Direction in the label, both speeds below: 'Wind (NW)' / '21 km/h (13 mph)'
        wind = ("Wind (" + w["wind_dir"] + ")", draw_wind, None)
    else:
        wind = ("Wind", wind_text(w), BLACK)
    if prayer:
        # Left: High / Low, Wind, Precipitation (highest chance over the next
        # 12 hours, worded like the original Pi screen).
        # Right: UV index (coloured by level) and humidity in one box, then
        # sunrise and sunset, worked out with the prayer times so they match.
        rise, set_ = prayer["sun"]
        cells = (
            hi_lo,
            ("UV / Humidity", draw_uv_humidity, None),
            wind,
            ("Sunrise", clock_minutes(rise) if rise is not None else clock(w["sunrise"]), ORANGE),
            ("Precipitation", w["rain_12h"] + "% chance", BLUE),
            ("Sunset", clock_minutes(set_) if set_ is not None else clock(w["sunset"]), ORANGE),
        )
    else:
        cells = (
            hi_lo,
            ("UV index today", uv_text(w["uv"]), uv_colour(w["uv"])),
            wind,
            ("Humidity", to_text(w["humidity"]) + "%", humidity_colour(w["humidity"])),
            ("Sunrise", clock(w["sunrise"]), ORANGE),
            ("Sunset", clock(w["sunset"]), ORANGE),
        )
    # All the values share one size: the largest that every box fits at
    vsize = MF(27)
    for i, (label, value, colour) in enumerate(cells):
        x = MX(474) + (i % 2) * MX(180)
        width = MX(170) if i % 2 == 0 else WIDTH - MX(8) - x
        if callable(value):
            vsize = min(vsize, value(w, 0, 0, width, top=MF(27), measure=True))
        else:
            vsize = min(vsize, fit(value, MF(27), width, bold=True, smallest=MF(18)))
    small = max(MF(17), int(vsize * 0.72))           # the second-unit text, '(13 mph)' etc.
    for i, (label, value, colour) in enumerate(cells):
        x = MX(474) + (i % 2) * MX(180)
        y = MY(58) + (i // 2) * MY(52) + (extra if i >= 2 else 0)
        width = MX(170) if i % 2 == 0 else WIDTH - MX(8) - x
        draw_text(label, x, y, MF(17), BLACK)
        if callable(value):
            value(w, x, y + MY(18), width, top=vsize)
        else:
            draw_text(value, x, y + MY(18), vsize, colour, bold=True)
        if i == 0 and tall:
            # High / Low in the other unit, on its own line: '48°F / 36°F'
            other = deg(w["hi_c"], other_unit(), True) + " / " + deg(w["lo_c"], other_unit(), True)
            draw_text(other, x, y + MY(20) + int(vsize * 1.12), fit(other, small, width, smallest=MF(17)),
                      unit_colour(other_unit()))

    graphics.set_pen(BLACK)
    graphics.rectangle(MX(20), MY(220) + extra, WIDTH - MX(40), 2)

    # Prayer times, or the next 12 hours
    if w["alerts"]:
        draw_alert_banner(w["alerts"], MX(20), WIDTH - MX(20), MY(222) + extra, MY(28))
    elif prayer:
        draw_prayer_title(prayer, MY(220) + extra)
    else:
        draw_chart_title(w)
    if prayer:
        row_top = MY(254) + extra - (MY(6) if tall else 0)
        draw_prayers(prayer, MX(20), WIDTH - MX(20), row_top, MY(346) - row_top)
    else:
        draw_hourly(w["hours"], MX(20), WIDTH - MX(20), MY(272), MY(292), MY(330), MY(34))
    _after_chart(w)


def draw_prayer_title(p, y=None):
    """'Prayer times (Hanafi)' on the left, the Hijri date on the right."""
    if y is None:
        y = MY(220)
    title = "Prayer times tomorrow" if p["tomorrow"] else "Prayer times"
    tw = draw_text(title, MX(20), y, MF(22), BLACK, bold=True)
    asr = "(Hanafi)" if ASR_METHOD.lower() == "hanafi" else "(Standard Asr)"
    # same baseline as the title
    draw_text(asr, MX(20) + tw + MX(10), y + int((MF(22) - MF(18)) * 1.04), MF(18), BLACK)
    hijri = p.get("hijri")
    if hijri:
        draw_text(hijri, WIDTH - MX(20), y + int((MF(22) - MF(20)) * 1.04), MF(20), GREEN,
                  bold=True, right=True)


# Fajr, Dhuhr, Asr, Maghrib, Isha (sunrise is already in the details above)
PRAYER_COLUMNS = (0, 2, 3, 4, 5)


def draw_prayers(p, x0, x1, top, height):
    """Five columns, one per prayer, lined up with the five forecast days
    below. The next prayer is in a green box."""
    cols = PRAYER_COLUMNS
    col = (x1 - x0) // len(cols)
    compact = height < MY(85)          # shorter row: everything sits closer
    time_y = top + (MY(24) if compact else MY(32))
    next_y = top + height - (MY(22) if compact else MY(24))
    nxt = cols.index(p["next"]) if p["next"] in cols else -1
    for j, i in enumerate(cols):
        x = x0 + j * col
        cx = x + col // 2
        is_next = j == nxt
        fg, bg = (WHITE, GREEN) if is_next else (BLACK, WHITE)
        if is_next:
            graphics.set_pen(GREEN)
            graphics.rectangle(x + MX(3), top, col - MX(6), height)
        elif j and nxt != j - 1:
            graphics.set_pen(BLACK)                    # thin divider between columns
            graphics.rectangle(x, top + MY(10), 1, height - MY(20))
        draw_text(p["names"][i], cx, top + (MY(2) if compact else MY(4)), MF(21), fg, bold=True, center=True, bg=bg)
        big, small = time_parts(p["times"][i])
        bw = text_width(big, MF(30), True)
        sw = text_width(small, MF(17)) if small else 0
        gap = MX(3) if small else 0
        sx = cx - (bw + gap + sw) // 2
        draw_text(big, sx, time_y, MF(30), fg, bold=True, bg=bg)
        if small:
            # same baseline as the big digits
            draw_text(small, sx + bw + gap, time_y + int((MF(30) - MF(17)) * 1.04), MF(17), fg, bg=bg)
        if is_next:
            draw_text("next", cx, next_y, MF(17), WHITE, center=True, bg=GREEN)


def draw_chart_title(w):
    tw = draw_text("Next 12 hours", MX(20), MY(220), MF(22), BLACK, bold=True)
    draw_text("rain up to " + w["rain_12h"] + "%", MX(20) + tw + MX(12), MY(224), MF(17), BLUE)
    # Key, right-aligned: [red line] Temperature   [blue box] Rain chance
    x = WIDTH - MX(20) - text_width("Rain chance", MF(17))
    draw_text("Rain chance", x, MY(224), MF(17), BLACK)
    graphics.set_pen(BLUE)
    graphics.rectangle(x - MX(20), MY(229), MX(13), MY(14))
    x -= MX(40) + text_width("Temperature", MF(17))
    draw_text("Temperature", x, MY(224), MF(17), BLACK)
    graphics.set_pen(RED)
    graphics.line(x - MX(34), MY(236), x - MX(8), MY(236), 3)


# Shorter names for the longest conditions, so they fit a forecast column
SHORT_CONDITIONS = {45: "Rime fog", 96: "Storm, slight hail", 99: "Storm, heavy hail"}


def draw_pair(a, b, x, y, size, ca, cb, bold=False):
    """'7°C/1°C' with each half in its own colour; returns the width."""
    w1 = draw_text(a + "/", x, y, size, ca, bold=bold)
    return w1 + draw_text(b, x + w1, y, size, cb, bold=bold)


def _after_chart(w):
    graphics.set_pen(BLACK)
    graphics.rectangle(MX(20), MY(352), WIDTH - MX(40), 2)

    # The next few days, laid out like the original Pi screen: the day and its
    # conditions on top, then the icon with the high/low and rain chance beside it
    n = min(max(int(FORECAST_DAYS), 3), 4)
    days = w["days"][:n]
    col = (WIDTH - MX(40)) // max(1, len(days))
    isz = icon_size(60)
    # One size for every day's °C and °F lines: the largest they all fit at
    tsz = MF(21)
    u2 = other_unit()
    for i, d in enumerate(days):
        sroom = col - (MX(10) if i else 0) - isz - MX(8) - MX(6)
        for u in ((UNITS, u2) if SHOW_BOTH_UNITS else (UNITS,)):
            t = deg(d["hi_c"], u, True) + "/" + deg(d["lo_c"], u, True)
            tsz = min(tsz, fit(t, MF(21), sroom, bold=True, smallest=MF(17)))
    for i, d in enumerate(days):
        x = MX(20) + i * col
        pad = MX(10) if i else 0
        if i:
            graphics.set_pen(BLACK)
            graphics.rectangle(x, MY(362), 1, MY(108))
        tx = x + pad
        room = x + col - MX(8) - tx
        name = d["name"]
        draw_text(name, tx, MY(354), fit(name, MF(22), room, bold=True, smallest=MF(17)), BLACK, bold=True)
        desc = SHORT_CONDITIONS.get(d["code"]) or describe(d["code"]).replace("\n", " ")
        while " " in desc and text_width(desc, MF(17)) > room:
            desc = desc.rsplit(" ", 1)[0]      # drop words that will not fit
        draw_text(desc, tx, MY(379), fit(desc, MF(18), room, smallest=MF(17)), BLACK)

        draw_icon(icon_for(d["code"]), isz, tx, MY(404))
        sx = tx + isz + MX(8)
        sroom = x + col - MX(6) - sx
        hi = deg(d["hi_c"], show_unit=True)
        lo = deg(d["lo_c"], show_unit=True)
        if SHOW_BOTH_UNITS:
            y_c, y_o, y_r = MY(404), MY(427), MY(448)
        else:
            y_c, y_o, y_r = MY(410), None, MY(438)
        cu = unit_colour(UNITS)
        draw_pair(hi, lo, sx, y_c, tsz, cu, cu, bold=True)
        if y_o:
            u = other_unit()
            hi_o = deg(d["hi_c"], u, True)
            lo_o = deg(d["lo_c"], u, True)
            co = unit_colour(u)
            draw_pair(hi_o, lo_o, sx, y_o, tsz, co, co, bold=True)
        chance = d["rain"] + "% chance"
        draw_text(chance, sx, y_r, fit(chance, MF(18), sroom, smallest=MF(17)), BLACK)


def draw_battery(right, cy, dark=True):
    """Battery icon, its right edge at `right`, centred on `cy`: on the black
    band (dark=True) or on white. Returns the width used (0 if nothing shown)."""
    if not SHOW_BATTERY:
        return 0
    try:
        import battery
        pct, bars, volts, on_usb, kind = battery.info(BATTERY_TYPE)
    except Exception:
        return 0
    if volts is None and not on_usb:
        return 0
    bw, bh = MX(26), MY(14)
    x, y = right - bw - MX(3), cy - bh // 2
    fg, bg = (WHITE, BLACK) if dark else (BLACK, WHITE)
    graphics.set_pen(fg)                          # outline and the + nub
    graphics.rectangle(x, y, bw, bh)
    graphics.rectangle(x + bw, y + bh // 4, MX(3), bh - 2 * (bh // 4))
    graphics.set_pen(bg)
    graphics.rectangle(x + 2, y + 2, bw - 4, bh - 4)
    if on_usb:
        # Plugged in: a yellow lightning bolt
        graphics.set_pen(YELLOW if dark else ORANGE)
        mx = x + bw // 2
        graphics.triangle(mx + MX(3), y + 2, mx - MX(5), y + bh // 2 + 1, mx + MX(1), y + bh // 2 + 1)
        graphics.triangle(mx - MX(3), y + bh - 2, mx + MX(5), y + bh // 2 - 1, mx - MX(1), y + bh // 2 - 1)
    else:
        colour = GREEN if bars >= 3 else ORANGE if bars == 2 else RED
        seg = (bw - 4 - 5) // 4                   # four bars with 1 px gaps
        for i in range(bars):
            graphics.set_pen(colour)
            graphics.rectangle(x + 3 + i * (seg + 1), y + 3, seg, bh - 6)
        if bars == 0:                             # empty: red outline
            graphics.set_pen(RED)
            graphics.rectangle(x, y, bw, 2)
            graphics.rectangle(x, y + bh - 2, bw, 2)
    used = bw + MX(3)
    if SHOW_BATTERY_VOLTS and volts is not None and not on_usb:
        t = "{:.2f}V".format(volts)
        used += draw_text(t, x - MX(5), cy - int(MF(17) * 0.62), MF(17), fg, right=True, bg=bg) + MX(5)
    return used


def draw_drop(x, y, h):
    """A small filled raindrop, h pixels tall, top-left corner at x, y."""
    r = max(2, int(h * 0.34))
    cx = x + r
    cy = y + h - r
    graphics.set_pen(BLUE)
    graphics.circle(cx, cy, r)
    graphics.triangle(cx, y, cx - r, cy, cx + r, cy)


def draw_error(message):
    graphics.set_pen(WHITE)
    graphics.clear()
    draw_text("Weather update failed", X(15), Y(20), F(40), RED, bold=True)
    draw_text(message, X(15), Y(110), F(22), BLACK, max_width=WIDTH - X(30))
    draw_text("Trying again every {} minutes.".format(RETRY_MINUTES), X(15), Y(200), F(22), BLACK)
    draw_text("Check secrets.py (Wi-Fi) and the settings in weather.py.", X(15), Y(240), F(18), BLACK,
              max_width=WIDTH - X(30))


# ---------------------------------------------------------------
#  Called by the launcher (main.py)
# ---------------------------------------------------------------

def update():
    global weather, error, UPDATE_INTERVAL
    try:
        ensure_wifi()
        data = fetch_weather()
        weather = parse_weather(data)
        del data
        gc.collect()
        if SHOW_ALERTS and LAYOUT == "modern":
            try:
                weather["alerts"] = fetch_alerts()
                print("Alerts:", [a.get("event") for a in weather["alerts"]])
            except Exception as e:
                print("Alerts unavailable:", e)   # not worth failing the update for
        error = None
        UPDATE_INTERVAL = UPDATE_MINUTES
        if SHOW_PRAYER_TIMES and LAYOUT == "modern":
            try:
                p = prayer_info(local_now(weather["now"], weather["utc_offset"]), weather["utc_offset"])
                weather["prayer"] = p
                print("Prayer times:", [time_parts(t)[0] for t in p["times"]])
                # Refresh a minute after the next prayer begins, so the highlight moves on
                if p["until"] is not None and p["until"] + 1 < UPDATE_INTERVAL:
                    UPDATE_INTERVAL = max(1, p["until"] + 1)
            except Exception as e:
                print("Prayer times unavailable:", e)   # not worth failing the update for
        print("Weather:", weather["temp_c"], "C,", describe(weather["code"]))
    except Exception as e:
        # Never let an error escape: it would stop the launcher's loop
        weather = None
        error = str(e)
        UPDATE_INTERVAL = RETRY_MINUTES
        print("Update failed:", error)
    gc.collect()


def draw_screen(w):
    if LAYOUT == "modern":
        draw_modern(w)
    else:
        draw_weather(w)


def draw():
    global _vector, _jpeg, _bmp_failed
    gc.collect()
    if _jpeg is None:
        # The picture decoder needs one big block of memory: take it while it's free
        try:
            _jpeg = jpegdec.JPEG(graphics)
        except MemoryError:
            gc.collect()
    if _vector is None:
        _vector = _has_vector_font(_vfont())
        if FONT == "original" and _bmp_list()["r"]:
            print("Font: original (pre-rendered)")
        else:
            print("Font:", _vfont() if _vector else "bitmap8")

    if weather is not None:
        _write_fails(0)
        try:
            draw_screen(weather)
        except MemoryError:
            if FONT != "original" or _bmp_failed:
                raise
            # Not enough memory for the pre-rendered font: redraw with the built-in one
            print("Out of memory with the original font - using the built-in serif")
            _bmp_failed = True
            _bmp_close()
            gc.collect()
            draw_screen(weather)
    else:
        fails = _read_fails()
        _write_fails(max(fails, 0) + 1)
        # Keep the last forecast on screen after a one-off failure. Show the
        # error if the weather has never been shown, or it has failed 3 times.
        if fails >= 0 and fails + 1 < 3:
            print("Keeping the last forecast on screen")
            return
        draw_error(error or "Unknown error")

    _jpeg = None
    _bmp_close()
    gc.collect()
    print("Refreshing display (takes ~40 seconds)...")
    graphics.update()
