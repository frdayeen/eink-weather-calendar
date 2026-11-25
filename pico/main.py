import gc
import io
import sys
import time

import inky_helper as ih
from inky_frame import BLACK, BLUE, GREEN, RED, WHITE
from machine import Pin, reset
# Uncomment the line for your Inky Frame display size
# from picographics import PicoGraphics, DISPLAY_INKY_FRAME_4 as DISPLAY  # 4.0"
# from picographics import PicoGraphics, DISPLAY_INKY_FRAME as DISPLAY      # 5.7"
from picographics import PicoGraphics, DISPLAY_INKY_FRAME_7 as DISPLAY  # 7.3"
# from picographics import PicoGraphics, DISPLAY_INKY_FRAME_SPECTRA_7 as DISPLAY  # 7.3" Spectra

# Pimoroni's Inky Frame launcher, with three changes:
# - button E starts the weather app (instead of Carbon Intensity)
# - if an app hits an error, the error is shown on screen, instead of the
#   frame silently stopping with its buttons dead
# - while an app waits for its next update on USB power, pressing A-E
#   switches straight to that app (E while the weather is showing = refresh now)
#
# Hold A + E and press Reset to show this menu at any time.

# Create a secrets.py with your Wifi details to be able to get the time
#
# secrets.py should contain:
# WIFI_SSID = "Your WiFi SSID"
# WIFI_PASSWORD = "Your WiFi password"

APPS = (
    ("a", "month_calendar", "Calendar"),
    ("b", "calendar_weather", "Calendar + Weather"),
    ("c", "date_weather", "Date + Weather"),
    ("d", "headlines", "Headlines"),
    ("e", "weather", "Weather"),
)
BUTTONS = {
    "a": ih.inky_frame.button_a,
    "b": ih.inky_frame.button_b,
    "c": ih.inky_frame.button_c,
    "d": ih.inky_frame.button_d,
    "e": ih.inky_frame.button_e,
}
ERROR_RETRY_MINUTES = 30

# A short delay to give USB chance to initialise
time.sleep(0.5)

# Setup for the display.
graphics = PicoGraphics(DISPLAY)
WIDTH, HEIGHT = graphics.get_bounds()
graphics.set_font("bitmap8")


def pressed_button():
    """The letter of a button being pressed right now, or None."""
    for letter, _, _ in APPS:
        if BUTTONS[letter].read():
            return letter
    return None


def held(letter):
    """Is this button physically held down right now?"""
    b = BUTTONS[letter]
    return b.raw() if hasattr(b, "raw") else b.read()


def wait_for_release():
    """Ignore buttons that are still held down (e.g. from A + E at power-up)."""
    while any(held(letter) for letter, _, _ in APPS):
        time.sleep(0.05)


def woken_by():
    """Buttons whose press powered the frame up (on batteries). The firmware
    remembers them, because they're usually let go before this code runs.
    Each is reported once; reading them here stops anything else using them."""
    letters = []
    for letter, _, _ in APPS:
        b = BUTTONS[letter]
        if getattr(b, "startup_state", False):
            b.startup_state = False
            letters.append(letter)
    return letters


def start_app(letter):
    """Remember the app for this button and restart into it."""
    for key, name, _ in APPS:
        if key == letter:
            BUTTONS[letter].led_on()
            ih.update_state(name)
            time.sleep(0.5)
            reset()


def wait(minutes):
    """Sleep until the next update. On batteries the frame switches off and
    its clock wakes it. On USB it keeps running, so watch the buttons."""
    minutes = max(1, min(255, int(minutes)))     # the clock's timer counts to 255
    ih.rtc.clear_timer_flag()
    ih.rtc.set_timer(minutes, ttp=ih.rtc.TIMER_TICK_1_OVER_60HZ)
    ih.rtc.enable_timer_interrupt(True)
    ih.hold_vsys_en_pin.init(Pin.IN)      # on batteries, power goes off here

    wait_for_release()
    end = time.ticks_add(time.ticks_ms(), minutes * 60000)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        letter = pressed_button()
        if letter:
            start_app(letter)
        time.sleep(0.05)


def show_error(name, e):
    """Put the error on screen, so it can be seen without Thonny."""
    buf = io.StringIO()
    sys.print_exception(e, buf)
    lines = [line.strip() for line in buf.getvalue().split("\n") if line.strip()]
    print("App '{}' failed:".format(name))
    sys.print_exception(e)

    graphics.set_font("bitmap8")
    graphics.set_thickness(1)
    graphics.set_pen(WHITE)
    graphics.clear()
    graphics.set_pen(RED)
    graphics.rectangle(0, 0, WIDTH, 50)
    graphics.set_pen(WHITE)
    label = name
    for _, app, title in APPS:
        if app == name:
            label = title
    graphics.text("{} stopped with an error".format(label), 10, 12, WIDTH - 20, 3)

    graphics.set_pen(BLACK)
    y = 70
    for line in lines[-10:]:              # the end says which file, line and error
        graphics.text(line, 10, y, WIDTH - 20, 2)
        y += 20 * (1 + graphics.measure_text(line, 2) // (WIDTH - 20))
        if y > HEIGHT - 70:
            break
    graphics.set_pen(BLUE)
    graphics.text("Press A-E to start an app (E = Weather). Trying again in {} minutes."
                  .format(ERROR_RETRY_MINUTES), 10, HEIGHT - 50, WIDTH - 20, 2)
    ih.led_warn.on()
    graphics.update()
    ih.led_warn.off()


def launcher():

    # Apply an offset for the Inky Frame 5.7".
    if HEIGHT == 448:
        y_offset = 20
    # Inky Frame 7.3"
    elif HEIGHT == 480:
        y_offset = 35
    # Inky Frame 4"
    else:
        y_offset = 0

    # Draws the menu
    graphics.set_pen(WHITE)
    graphics.clear()

    graphics.set_pen(BLUE)
    graphics.rectangle(0, 0, WIDTH, 50)
    graphics.set_pen(WHITE)
    title = "Launcher"
    title_len = graphics.measure_text(title, 4) // 2
    graphics.text(title, (WIDTH // 2 - title_len), 10, WIDTH, 4)

    for i, (letter, _, label) in enumerate(APPS):
        top = HEIGHT - (340 - 60 * i + y_offset)
        width = WIDTH - 100 - 50 * i
        graphics.set_pen(GREEN if i % 2 == 0 else BLUE)
        graphics.rectangle(30, top, width, 50)
        graphics.set_pen(1)
        graphics.text("{}. {}".format(letter.upper(), label), 35, top + 15, 600, 3)
        graphics.set_pen(graphics.create_pen(220, 220, 220))
        graphics.rectangle(width, top, 70 + 50 * i, 50)

    graphics.set_pen(BLACK)
    note = "Hold A + E, then press Reset, to return to the Launcher"
    note_len = graphics.measure_text(note, 2) // 2
    graphics.text(note, (WIDTH // 2 - note_len), HEIGHT - 30, 600, 2)

    ih.led_warn.on()
    graphics.update()
    ih.led_warn.off()

    # Now we've drawn the menu to the screen, we wait here for the user to select an app.
    # Then once an app is selected, we set that as the current app and reset the device and load into it.
    wait_for_release()
    while True:
        letter = pressed_button()
        if letter:
            start_app(letter)
        time.sleep(0.05)


# Turn any LEDs off that may still be on from last run.
ih.clear_button_leds()
ih.led_warn.off()

# Which button woke the frame? (On batteries it's off between updates, and
# pressing a button is what turns it on.)
woke = woken_by()
if ("a" in woke and "e" in woke) or (held("a") and held("e")):
    launcher()

ih.clear_button_leds()

if not ih.file_exists("state.json"):
    launcher()

if len(woke) == 1:
    # Switch to that button's app (or refresh it, if it's already showing)
    for key, name, _ in APPS:
        if key == woke[0]:
            ih.load_state()
            if ih.state.get("run") != name:
                print("Woken by button", key.upper(), "- switching to", name)
                ih.update_state(name)

# Loads the JSON and launches the app
ih.load_state()
app_name = ih.state["run"]
try:
    ih.launch_app(app_name)
    # Passes the the graphics object from the launcher to the app
    ih.app.graphics = graphics
    ih.app.WIDTH = WIDTH
    ih.app.HEIGHT = HEIGHT
except Exception as e:
    # The app couldn't even start (e.g. a typo in its settings, or out of memory)
    show_error(app_name, e)
    wait(ERROR_RETRY_MINUTES)
    reset()

# Battery level: read before Wi-Fi starts (on a Pico W they share a pin)
try:
    import battery
    battery.measure()
except Exception as e:
    battery = None
    print("No battery reading:", e)

try:
    from secrets import WIFI_PASSWORD, WIFI_SSID
    ih.network_connect(WIFI_SSID, WIFI_PASSWORD)
except ImportError:
    print("Create secrets.py with your WiFi credentials")

if battery:
    battery.check_usb()       # USB power? and remember the battery type

# Get some memory back, we really need it!
gc.collect()

# The main loop executes the update and draw function from the imported app,
# and then goes to sleep ZzzzZZz
while True:
    try:
        ih.app.update()
        ih.led_warn.on()
        ih.app.draw()
        ih.led_warn.off()
        minutes = ih.app.UPDATE_INTERVAL
    except Exception as e:
        ih.led_warn.off()
        show_error(app_name, e)
        minutes = ERROR_RETRY_MINUTES
    gc.collect()
    wait(minutes)
