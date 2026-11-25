"""Turn TrueType fonts into small bitmap font files the Pico can draw.

Run this on your computer (not the Pico) if you want a different font:

    pip install pillow
    python make_font.py Regular.ttf Bold.ttf path/to/output/fonts

It renders every letter at the sizes weather.py uses, with no anti-aliasing
(the panel can't show grey) and exactly the spacing PIL gave on the Pi.
All sizes go into two files, original_r.bin (regular) and original_b.bin
(bold), so they take little space on the Pico. Very large sizes only contain
the characters a temperature needs.

File format (little-endian):
    b"FNP1", u8 number of sizes, then per size: u8 size, u32 offset, u32 length
    Each size is a block:
    b"FNT1", u8 size, u8 glyph count
    per glyph: u16 char code, u16 advance x16, i8 x offset, u8 y offset,
               u8 width, u8 height, u16 data offset
    then the glyph bitmaps, 1 bit per pixel, rows padded to whole bytes.
    Offsets are measured from the top of the line (PIL's "la" anchor).
"""
import os
import struct
import sys

from PIL import Image, ImageDraw, ImageFont

TEXT = "".join(chr(c) for c in range(32, 127)) + "\xb0"
DIGITS = " -0123456789\xb0CF/."

REGULAR_SIZES = (15, 17, 18, 20, 21, 22, 24, 25, 28, 30, 34, 36, 40, 45, 52, 57)
BOLD_SIZES = (16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 32, 34, 40, 46, 57)
BOLD_DIGIT_SIZES = (60, 66, 72, 80, 86, 92, 96)


def render(font_path, size, chars):
    font = ImageFont.truetype(font_path, size)
    glyphs = []
    data = bytearray()
    for ch in chars:
        adv = font.getlength(ch)
        x0, y0, x1, y1 = font.getbbox(ch, anchor="la")
        w, h = max(0, x1 - x0), max(0, y1 - y0)
        bits = bytearray()
        if w and h:
            im = Image.new("1", (w, h), 0)
            d = ImageDraw.Draw(im)
            d.fontmode = "1"                       # crisp, no grey edges
            d.text((-x0, -y0), ch, font=font, fill=1, anchor="la")
            px = im.load()
            # trim empty rows/columns left by hinting
            rows = [y for y in range(h) if any(px[x, y] for x in range(w))]
            cols = [x for x in range(w) if any(px[x, y] for y in range(h))]
            if rows and cols:
                cx0, cx1, cy0, cy1 = cols[0], cols[-1] + 1, rows[0], rows[-1] + 1
                x0, y0, w, h = x0 + cx0, y0 + cy0, cx1 - cx0, cy1 - cy0
                for y in range(cy0, cy1):
                    row = 0
                    for x in range(cx0, cx1):
                        row = (row << 1) | (1 if px[x, y] else 0)
                    row <<= (-w) % 8
                    bits += row.to_bytes((w + 7) // 8, "big")
            else:
                w = h = 0
        assert -128 <= x0 < 128 and 0 <= y0 < 256 and w < 256 and h < 256, (ch, size)
        glyphs.append((ord(ch), int(round(adv * 16)), x0, y0, w, h, len(data)))
        data += bits
    assert len(data) < 65536
    out = bytearray(b"FNT1") + bytes((size, len(glyphs)))
    for g in glyphs:
        out += struct.pack("<HHbBBBH", *g)
    return bytes(out + data)


def pack(blocks):
    head = bytearray(b"FNP1") + bytes((len(blocks),))
    offset = 5 + 9 * len(blocks)
    body = bytearray()
    for size, blob in blocks:
        head += struct.pack("<BII", size, offset + len(body), len(blob))
        body += blob
    return bytes(head + body)


def main(regular, bold, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    regular_blocks = [(s, render(regular, s, TEXT)) for s in REGULAR_SIZES]
    bold_blocks = [(s, render(bold, s, TEXT)) for s in BOLD_SIZES]
    bold_blocks += [(s, render(bold, s, DIGITS)) for s in BOLD_DIGIT_SIZES]
    for style, blocks in (("r", regular_blocks), ("b", bold_blocks)):
        data = pack(blocks)
        with open(os.path.join(out_dir, "original_{}.bin".format(style)), "wb") as f:
            f.write(data)
        print("wrote original_{}.bin: {} sizes, {:.0f} KB".format(style, len(blocks), len(data) / 1024))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
