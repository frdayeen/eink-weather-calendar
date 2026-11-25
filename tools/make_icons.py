"""Make Pico-ready weather icons from the original weather_jpg folder.

Run this on your computer (not the Pico), only if you change icons or screens:

    pip install pillow
    python make_icons.py path/to/weather_jpg path/to/output/icons --screen 7.3

--screen is 7.3 (default), 5.7 or 4.0. The Pico can't resize images, so each
icon is saved at the exact sizes weather.py asks for on that screen.

By default each pixel is snapped to the nearest of the panel's 7 colours
("flat"), which keeps line-art icons crisp on e-ink. Add --dither for the
speckled look the Pi's `inky` library gave (better for photo-like icons).
Files are baseline JPEGs that jpegdec can read.
"""
import argparse
import os

from PIL import Image

# Panel colours from Pimoroni's inky library: (saturated, desaturated)
PALETTES = {
    # inky_ac073tc1a.py - Inky 7.3"
    "7.3": ([(0, 0, 0), (217, 242, 255), (3, 124, 76), (27, 46, 198),
             (245, 80, 34), (255, 255, 68), (239, 121, 44)],
            [(0, 0, 0), (255, 255, 255), (0, 255, 0), (0, 0, 255),
             (255, 0, 0), (255, 255, 0), (255, 140, 0)]),
    # inky_uc8159.py - Inky 5.7" and 4.0"
    "5.7": ([(57, 48, 57), (255, 255, 255), (58, 91, 70), (61, 59, 94),
             (156, 72, 75), (208, 190, 71), (177, 106, 73)],
            [(0, 0, 0), (255, 255, 255), (0, 255, 0), (0, 0, 255),
             (255, 0, 0), (255, 255, 0), (255, 140, 0)]),
}
PALETTES["4.0"] = PALETTES["5.7"]
SATURATION = 0.9  # same value weather_new.py used

SCREEN_HEIGHT = {"7.3": 480, "5.7": 448, "4.0": 400}

# Colours PicoGraphics matches against on Inky Frame (pen index 0-6)
PICO_COLOURS = [(0, 0, 0), (255, 255, 255), (0, 255, 0), (0, 0, 255),
                (255, 0, 0), (255, 255, 0), (255, 128, 0)]


def blended_palette(screen):
    sat, desat = PALETTES[screen]
    pal = []
    for s, d in zip(sat, desat):
        pal.extend(int(a * SATURATION + b * (1 - SATURATION)) for a, b in zip(s, d))
    return pal


def flat_index(p, pal, grey=70):
    """Nearest panel colour; greyish edge shading goes to black or white."""
    i = min(range(7), key=lambda k: sum((a - c) ** 2 for a, c in zip(p, pal[k])))
    if i >= 2 and max(p) - min(p) < grey:
        r, g, b = p
        return 0 if (r * 299 + g * 587 + b * 114) / 1000 < 150 else 1
    return i


def convert(src, size, screen, dither=False, grey=70):
    im = Image.open(src).convert("RGB").resize((size, size), Image.LANCZOS)
    if not dither:
        flat = blended_palette(screen)
        pal = [tuple(flat[i:i + 3]) for i in range(0, 21, 3)]
        out = Image.new("RGB", (size, size))
        out.putdata([PICO_COLOURS[flat_index(p, pal, grey)] for p in im.getdata()])
        return out
    pal_img = Image.new("P", (1, 1))
    # PIL palettes have 256 entries; repeat our 7 so index % 7 is always valid
    pal_img.putpalette((blended_palette(screen) * 37)[:768])
    q = im.quantize(palette=pal_img, dither=Image.Dither.FLOYDSTEINBERG)
    # Swap the "how it looks" colours for the exact pen colours the Pico expects
    out = Image.new("RGB", (size, size))
    out.putdata([PICO_COLOURS[i % 7] for i in q.tobytes()])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--screen", choices=sorted(SCREEN_HEIGHT), default="7.3")
    ap.add_argument("--dither", action="store_true", help="dither instead of flat colours")
    args = ap.parse_args()

    h = SCREEN_HEIGHT[args.screen]
    # Must match icon_size() in weather.py: int(v * HEIGHT / 448)
    big, small, tiny, wind = (int(v * h / 448) for v in (120, 60, 30, 35))

    os.makedirs(args.out_dir, exist_ok=True)
    for fn in sorted(os.listdir(args.src_dir)):
        if not fn.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        name = os.path.splitext(fn)[0]
        sizes = (wind,) if name == "wind" else (big, small, tiny)
        for size in sizes:
            dst = os.path.join(args.out_dir, "{}_{}.jpg".format(name, size))
            # the tiny calendar icons need stricter grey handling to stay clean
            grey = 130 if size == tiny else 70
            convert(os.path.join(args.src_dir, fn), size, args.screen, args.dither, grey).save(
                dst, "JPEG", quality=100, subsampling=0, progressive=False, optimize=True)
            print("wrote", dst)


if __name__ == "__main__":
    main()
