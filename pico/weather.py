"""
Weather app for the Inky Frame launcher (button E): YOUR SETTINGS.

Edit the settings below and save (Cmd+S in Thonny). The app itself is in
weather_app.mpy, pre-compiled so the Pico doesn't run out of memory.
Wi-Fi comes from secrets.py, like the other launcher apps.
"""

# ---------------------------------------------------------------
#  Settings - edit these
# ---------------------------------------------------------------

# Your location. 41.88, -87.63 is downtown Chicago. For your exact spot,
# right-click your home in Google Maps (west longitudes are negative).
LATITUDE = 41.88
LONGITUDE = -87.63
TIMEZONE = "America/Chicago"   # IANA name, e.g. "Europe/London"
TIMEZONE_LABEL = None          # None = Open-Meteo's abbreviation, or e.g. "CST"

# Place name for the header bar. "" leaves it out.
LOCATION_NAME = "Chicago"

# Screen design: "modern" (made for the 7.3" screen) or "classic" (the Pi layout)
LAYOUT = "modern"

# Main units: "F" (degF, mph) or "C" (degC, km/h)
UNITS = "C"

# Times as "9:15 PM" (False) or "21:15" (True)
CLOCK_24H = True

# Show the moon phase (worked out on the Pico, no internet needed)
SHOW_MOON = True

# Show every temperature in both units: °F beside °C (or °C beside °F)
SHOW_BOTH_UNITS = True

# How many days the forecast at the bottom shows: 4 or 3
FORECAST_DAYS = 4

# Grey "seas" on the white moon (False for a plain white moon)
MOON_SPOTS = True

# Battery icon in the top band (3 x AA). BATTERY_TYPE "auto" tells alkaline
# from rechargeable by the voltage of new batteries; or set "alkaline" or
# "rechargeable". SHOW_BATTERY_VOLTS shows the voltage beside the icon.
SHOW_BATTERY = True
BATTERY_TYPE = "auto"
SHOW_BATTERY_VOLTS = True

# Severe weather alerts from the US National Weather Service (US only)
SHOW_ALERTS = True

# Muslim prayer times, shown in place of the 12-hour chart. They're worked
# out on the Pico, so they need no internet.
SHOW_PRAYER_TIMES = True

# Calculation method: "ISNA", "MoonsightingCommittee", "MWL" (Muslim World
# League), "Egypt", "Makkah" (Umm al-Qura), "Karachi", "Tehran", "Jafari",
# "Gulf", "Kuwait", "Qatar", "Singapore", "Dubai", "France", "Russia"
PRAYER_METHOD = "ISNA"

# Asr: "hanafi", or "standard" (Shafi'i, Maliki, Hanbali)
ASR_METHOD = "hanafi"

# Minutes to add (or take away, with -) to match your mosque's timetable
PRAYER_ADJUST = {"Fajr": 0, "Sunrise": 0, "Dhuhr": 0, "Asr": 0, "Maghrib": 0, "Isha": 0}

# Hijri date (shown at the right of the prayer times). It follows the Umm
# al-Qura calendar, like Aladhan.com. If your community's moon sighting puts
# the month a day later, set HIJRI_ADJUST = 1 (or -1 for a day earlier).
HIJRI_ADJUST = 0

# True: the Hijri date moves on at Maghrib, when the Islamic day begins.
# False: it moves on at midnight, like most phone apps.
HIJRI_FROM_MAGHRIB = True

# Font: "original" (your Pi's PT Serif, from the /fonts folder), the built-in
# "serif", "sans", "serif_italic", "gothic", "cursive", or "bitmap"
FONT = "original"

# Minutes between updates (60 = hourly), and how soon to retry if a
# download fails. Both must be 255 or less.
UPDATE_MINUTES = 60
RETRY_MINUTES = 10

# ---------------------------------------------------------------
#  Nothing to edit below here
# ---------------------------------------------------------------

graphics = None   # set by the launcher
WIDTH = None
HEIGHT = None
UPDATE_INTERVAL = UPDATE_MINUTES

import weather_app as _app


def _share():
    """Pass the settings above, and the launcher's screen, to the app code."""
    g = globals()
    for name in g:
        if name[0] != "_" and (name.isupper() or name == "graphics"):
            setattr(_app, name, g[name])


def update():
    global UPDATE_INTERVAL
    _share()
    _app.update()
    UPDATE_INTERVAL = _app.UPDATE_INTERVAL


def draw():
    _share()
    _app.draw()
