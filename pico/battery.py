# Battery level for the Inky Frame (3 x AA), shared by the launcher and apps.
#
# On a Pico W the battery is measured through a pin the Wi-Fi chip also uses,
# so the launcher calls measure() right at start-up, before Wi-Fi is switched
# on, and check_usb() after Wi-Fi is connected. Apps then call info().
#
# Battery type: fresh alkaline AAs read about 4.5-4.8 V for three, fully
# charged rechargeables (NiMH) never more than about 4.2 V. When new batteries
# go in (the voltage jumps up), the starting voltage decides the type, and it
# is remembered in battery.json until the next change.

import json

STATE_FILE = "/battery.json"
NEW_JUMP = 0.25          # volts: a rise this big means new batteries went in
ALKALINE_START = 4.35    # volts: new batteries above this are alkaline

# (volts, percent) for three cells, measured at start-up
CURVES = {
    "alkaline": ((3.10, 0), (3.30, 5), (3.60, 25), (3.90, 50), (4.20, 75), (4.50, 100)),
    "rechargeable": ((3.30, 0), (3.45, 5), (3.60, 25), (3.75, 50), (3.90, 75), (4.05, 100)),
}

volts = None             # last reading (None if it couldn't be read)
usb = False              # True when USB power is connected
detected = None          # "alkaline" or "rechargeable", from battery.json


def _read_vsys(samples=8):
    """VSYS in volts. Must run while the Wi-Fi chip is off."""
    from machine import ADC, Pin
    Pin(25, Pin.OUT, value=1)                 # Wi-Fi chip select high: GP29 is ours
    Pin(29, Pin.IN)
    adc = ADC(29)
    total = 0
    for _ in range(samples):
        total += adc.read_u16()
    v = total / samples * 3 * 3.3 / 65535     # VSYS goes through a 1/3 divider
    try:
        Pin(29, Pin.ALT, pull=Pin.PULL_DOWN, alt=7)   # give the pin back to Wi-Fi
    except Exception:
        pass
    return v


def _load():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save(st):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(st, f)
    except Exception as e:
        print("Battery: could not save state:", e)


def measure():
    """Read the battery before Wi-Fi starts. Never raises."""
    global volts, detected
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        wlan.active(False)                    # the launcher turns it on afterwards
        volts = _read_vsys()
        print("Battery: {:.2f} V".format(volts))
    except Exception as e:
        print("Battery: could not read:", e)
        volts = None
    st = _load()
    detected = st.get("type")


def check_usb():
    """After Wi-Fi is on: is USB power connected? Then update the saved
    battery state (only from battery-powered readings). Never raises."""
    global usb, detected
    try:
        from machine import Pin
        usb = bool(Pin("WL_GPIO2", Pin.IN).value())
    except Exception:
        usb = False
    if volts is None or usb:
        return
    st = _load()
    last = st.get("last")
    if last is None or st.get("type") is None or volts > last + NEW_JUMP:
        # First reading, or new batteries: decide their type from the start voltage
        st["type"] = "alkaline" if volts >= ALKALINE_START else "rechargeable"
        st["start"] = round(volts, 2)
        print("Battery: new batteries, {} ({:.2f} V)".format(st["type"], volts))
    st["last"] = round(volts, 2)
    detected = st["type"]
    _save(st)


def percent(v, kind):
    curve = CURVES.get(kind) or CURVES["alkaline"]
    if v <= curve[0][0]:
        return 0
    for (v0, p0), (v1, p1) in zip(curve, curve[1:]):
        if v <= v1:
            return int(p0 + (p1 - p0) * (v - v0) / (v1 - v0) + 0.5)
    return 100


def info(kind="auto"):
    """(percent or None, bars 0-4, volts or None, on USB, type used).
    kind: "auto", "alkaline" or "rechargeable"."""
    if usb:
        return None, 4, volts, True, None
    if volts is None:
        return None, 0, None, False, None
    if kind not in CURVES:
        kind = detected or ("alkaline" if volts >= ALKALINE_START else "rechargeable")
    p = percent(volts, kind)
    bars = 4 if p >= 75 else 3 if p >= 50 else 2 if p >= 25 else 1 if p >= 8 else 0
    return p, bars, volts, False, kind
