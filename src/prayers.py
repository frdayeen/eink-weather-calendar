# ---------------------------------------------------------------
#  Muslim prayer times, worked out on the Pico (no internet needed)
#
#  The sun-angle method from PrayTimes.org (the method Aladhan.com also
#  uses), plus the Moonsighting Committee's seasonal rules (as in the
#  Adhan library). Written for the Pico's single-precision floats: whole days
#  are kept as an integer counted from the year 2000, so no big date
#  numbers lose precision.
# ---------------------------------------------------------------

import math

# Fajr angle, Isha angle (or minutes after Maghrib, as a string), Maghrib angle (None = sunset)
PRAYER_METHODS = {
    "ISNA": (15, 15, None),                      # Islamic Society of North America
    "MoonsightingCommittee": (18, 18, None),     # Moonsighting Committee Worldwide (+ seasonal limits)
    "MWL": (18, 17, None),                       # Muslim World League
    "Egypt": (19.5, 17.5, None),                 # Egyptian General Authority of Survey
    "Makkah": (18.5, "90", None),                # Umm al-Qura University, Makkah
    "Karachi": (18, 18, None),                   # University of Islamic Sciences, Karachi
    "Tehran": (17.7, 14, 4.5),                   # Institute of Geophysics, University of Tehran
    "Jafari": (16, 14, 4),                       # Shia Ithna-Ashari, Leva Institute, Qum
    "Gulf": (19.5, "90", None),                  # Gulf region
    "Kuwait": (18, 17.5, None),
    "Qatar": (18, "90", None),
    "Singapore": (20, 18, None),                 # MUIS Singapore
    "Dubai": (18.2, 18.2, None),
    "France": (12, 12, None),                    # UOIF France
    "Russia": (16, 15, None),                    # Spiritual Administration of Muslims of Russia
}

SUN = (None, None)

PRAYER_NAMES = ("Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha")

_RAD = math.pi / 180


def _sin(d):
    return math.sin(d * _RAD)


def _cos(d):
    return math.cos(d * _RAD)


def _tan(d):
    return math.tan(d * _RAD)


def _fix(a, b):
    a = a - b * math.floor(a / b)
    return a + b if a < 0 else a


def _civil_days(y, m, d):
    """Days since 1970-01-01."""
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    return era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468


def _sun(d0, frac):
    """Sun's declination (degrees) and equation of time (hours).
    d0 = whole days since 2000-01-01 12:00 UT (an int), frac = extra fraction of a day."""
    g = _fix(357.529 + _fix(0.98560028 * d0, 360) + 0.98560028 * frac, 360)
    q = _fix(280.459 + _fix(0.98564736 * d0, 360) + 0.98564736 * frac, 360)
    L = _fix(q + 1.915 * _sin(g) + 0.020 * _sin(2 * g), 360)
    e = 23.439 - 0.00000036 * (d0 + frac)
    ra = math.atan2(_cos(e) * _sin(L), _cos(L)) / _RAD / 15
    eqt = q / 15 - _fix(ra, 24)
    decl = math.asin(_sin(e) * _sin(L)) / _RAD
    return decl, eqt


def _season_minutes(lat, doy, leap, evening):
    """Moonsighting Committee's seasonal twilight length in minutes."""
    a_lat = abs(lat)
    if evening:
        a = 75 + 25.60 / 55.0 * a_lat
        b = 75 + 2.050 / 55.0 * a_lat
        c = 75 - 9.210 / 55.0 * a_lat
        d = 75 + 6.140 / 55.0 * a_lat
    else:
        a = 75 + 28.65 / 55.0 * a_lat
        b = 75 + 19.44 / 55.0 * a_lat
        c = 75 + 32.74 / 55.0 * a_lat
        d = 75 + 48.10 / 55.0 * a_lat
    days_in_year = 366 if leap else 365
    if lat >= 0:
        dyy = doy + 10
        if dyy >= days_in_year:
            dyy -= days_in_year
    else:
        dyy = doy - (173 if leap else 172)
        if dyy < 0:
            dyy += days_in_year
    if dyy < 91:
        return a + (b - a) / 91.0 * dyy
    if dyy < 137:
        return b + (c - b) / 46.0 * (dyy - 91)
    if dyy < 183:
        return c + (d - c) / 46.0 * (dyy - 137)
    if dyy < 229:
        return d + (c - d) / 46.0 * (dyy - 183)
    if dyy < 275:
        return c + (b - c) / 46.0 * (dyy - 229)
    return b + (a - b) / 91.0 * (dyy - 275)


def prayer_times(y, m, d, lat, lng, tz_hours, method="ISNA", asr="standard"):
    """Prayer times for one day, as minutes after local midnight (rounded),
    in PRAYER_NAMES order. None where the sun never reaches the angle."""
    fajr_a, isha_a, magh_a = PRAYER_METHODS.get(method, PRAYER_METHODS["ISNA"])
    days = _civil_days(y, m, d)
    d0 = days - 10957                      # whole days from 2000-01-01
    base = -0.5 - lng / 360.0              # 0h UT, shifted to local mean time
    factor = 2 if asr.lower() == "hanafi" else 1

    def sun(t):
        return _sun(d0, base + t / 24.0)

    def mid_day(t):
        return _fix(12 - sun(t)[1], 24)

    def angle_time(angle, t, morning=False):
        decl = sun(t)[0]
        c = (-_sin(angle) - _sin(decl) * _sin(lat)) / (_cos(decl) * _cos(lat))
        if c < -1 or c > 1:
            return None
        h = math.acos(c) / _RAD / 15
        noon = mid_day(t)
        return noon - h if morning else noon + h

    def asr_time(t):
        decl = sun(t)[0]
        angle = -math.atan(1 / (factor + _tan(abs(lat - decl)))) / _RAD
        return angle_time(angle, t)

    # First guesses at each time, as PrayTimes does (one pass is enough)
    fajr = angle_time(fajr_a, 5, True)
    sunrise = angle_time(0.833, 6, True)
    dhuhr = mid_day(12)
    asr_t = asr_time(13)
    sunset = angle_time(0.833, 18)
    maghrib = angle_time(magh_a, 18) if magh_a else sunset
    isha = None if isinstance(isha_a, str) else angle_time(isha_a, 18)

    shift = tz_hours - lng / 15.0          # local mean time -> your clock
    t = [None if v is None else v + shift for v in (fajr, sunrise, dhuhr, asr_t, sunset, maghrib, isha)]
    fajr, sunrise, dhuhr, asr_t, sunset, maghrib, isha = t

    # Far north or south, the sky may not get dark enough in summer: limit
    # Fajr/Isha to a share of the night ("angle-based", Aladhan's default)
    if sunrise is not None and sunset is not None:
        night = _fix(sunrise - sunset, 24)
        portion = (1 / 7.0) if (method == "MoonsightingCommittee" and lat >= 55) else None

        def limit(time, base_t, angle, morning):
            part = night * (portion if portion else angle / 60.0)
            if time is None:
                return base_t - part if morning else base_t + part
            diff = _fix(base_t - time, 24) if morning else _fix(time - base_t, 24)
            if diff > part:
                return base_t - part if morning else base_t + part
            return time

        fajr = limit(fajr, sunrise, fajr_a, True)
        if not isinstance(isha_a, str):
            isha = limit(isha, sunset, isha_a, False)
        if magh_a:
            maghrib = limit(maghrib, sunset, magh_a, False)

        if method == "MoonsightingCommittee" and lat < 55:
            doy = days - _civil_days(y, 1, 1) + 1
            leap = (y % 4 == 0 and y % 100 != 0) or y % 400 == 0
            safe_fajr = sunrise - _season_minutes(lat, doy, leap, False) / 60.0
            safe_isha = sunset + _season_minutes(lat, doy, leap, True) / 60.0
            if fajr is None or fajr < safe_fajr:
                fajr = safe_fajr
            if isha is None or isha > safe_isha:
                isha = safe_isha

    if isinstance(isha_a, str) and maghrib is not None:
        isha = maghrib + int(isha_a) / 60.0

    out = []
    for v in (fajr, sunrise, dhuhr, asr_t, maghrib, isha):
        out.append(None if v is None else int(v * 60 + 0.5))
    # Plain sunrise and sunset of the last day worked out, in minutes
    global SUN
    SUN = tuple(None if v is None else int(v * 60 + 0.5) for v in (sunrise, sunset))
    return out


# ---------------------------------------------------------------
#  Hijri (Islamic) date: the Umm al-Qura calendar (Saudi Arabia's
#  official calendar, the default on Aladhan.com) from 1440 to 1500 AH,
#  and the arithmetic Islamic calendar outside that range. Local moon
#  sighting can differ by a day - use HIJRI_ADJUST in weather.py.
# ---------------------------------------------------------------

HIJRI_MONTHS = ("Muharram", "Safar", "Rabi' al-Awwal", "Rabi' al-Thani", "Jumada al-Awwal",
                "Jumada al-Thani", "Rajab", "Sha'ban", "Ramadan", "Shawwal",
                "Dhu al-Qi'dah", "Dhu al-Hijjah")

# 1 Muharram 1440 (11 Sep 2018) as days since 1970-01-01, then one bit per
# month (1 = 30 days, 0 = 29 days), from the Umm al-Qura table
_UAQ_START = 17785
_UAQ_MONTHS = 732
_UAQ_BITS = (
    "5d4ada55aaab595749764baa5b52b6a56d2ae9572a75535a95d49ba4dd26d535"
    "aaaad4b6a57527a95b4ab5536c9ae4b6a96b4ada55d25d92dc96d4ad6556d2b6"
    "93749b64d72ab54b6a5752b6956b2ad94dc95d4aea56caad5556c97")


def _arith_hijri(days):
    """Arithmetic Islamic calendar (30-year cycle)."""
    l = days + 2440588 - 1948440 + 10632
    n = (l - 1) // 10631
    l = l - 10631 * n + 354
    j = ((10985 - l) // 5316) * ((50 * l) // 17719) + (l // 5670) * ((43 * l) // 15238)
    l = l - ((30 - j) // 15) * ((17719 * j) // 50) - (j // 16) * ((15238 * j) // 43) + 29
    m = (24 * l) // 709
    return 30 * n + j - 30, m, l - (709 * m) // 24


def hijri_date(days):
    """Days since 1970-01-01 -> (year, month 1-12, day)."""
    if days >= _UAQ_START:
        start = _UAQ_START
        for i in range(_UAQ_MONTHS):
            length = 29 + ((int(_UAQ_BITS[i // 4], 16) >> (3 - i % 4)) & 1)
            if days < start + length:
                return 1440 + i // 12, i % 12 + 1, days - start + 1
            start += length
    return _arith_hijri(days)
