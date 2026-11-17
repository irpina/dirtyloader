"""
Screenshot an M8 over USB, as m8c would show it: ask for the display stream, draw the frames, save a PNG.

    python -m dirtyloader.m8screen shot.png [--port COM11] [--scale 3] [--keys "SHIFT+UP,DOWN"]

--keys presses buttons first (comma-separated chords of LEFT UP DOWN SHIFT PLAY RIGHT OPT EDIT). Close m8c
first. Needs Pillow. Text is drawn with Pillow's built-in font, not the M8's, so letters look a little different.

The stream (m8c protocol): SLIP frames; 0xFE rectangle (x, y[, w, h][, r, g, b], u16 LE, colour sticky),
0xFD character (c, x, y, fg rgb, bg rgb; bg == fg means no background), 0xFC oscilloscope (rgb, then samples),
0xFF system info (hardware: 0 headless 320x240, else 480x320).
"""
from __future__ import annotations

import argparse
import struct
import sys
import time

from dirtyloader.serialport import open_m8
from dirtyloader.unit import slip_frames

KEYS = {"LEFT": 0x80, "UP": 0x40, "DOWN": 0x20, "SHIFT": 0x10, "PLAY": 0x08, "RIGHT": 0x04, "OPT": 0x02,
        "EDIT": 0x01}


def capture(port, seconds: float = 1.2, keys: str = "") -> list:
    port.write(b"E")
    time.sleep(0.3)
    for chord in [c for c in keys.split(",") if c.strip()]:
        mask = 0
        for k in chord.split("+"):
            mask |= KEYS[k.strip().upper()]
            port.write(bytes([0x43, mask]))
            time.sleep(0.06)
        time.sleep(0.12)
        port.write(bytes([0x43, 0]))
        time.sleep(0.25)
    port.read(65536, 0.2)                     # drop what came before the redraw
    port.write(b"R")
    buf, frames = bytearray(), []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        buf += port.read(65536, 0.05)
        frames += slip_frames(buf)
    port.write(b"D")
    return frames


def render(frames: list, scale: int = 3):
    from PIL import Image, ImageDraw, ImageFont
    w, h = 320, 240
    for f in frames:
        if f[0] == 0xFF and len(f) >= 2 and f[1] != 0:
            w, h = 480, 320
    img = Image.new("RGB", (w, h), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    colour = (0, 0, 0)
    for f in frames:
        t, n = f[0], len(f)
        if t == 0xFE and n in (5, 8, 9, 12):
            x, y = struct.unpack_from("<HH", f, 1)
            rw = rh = 1
            if n in (9, 12):
                rw, rh = struct.unpack_from("<HH", f, 5)
            if n in (8, 12):
                colour = tuple(f[n - 3:n])
            draw.rectangle([x, y, x + rw - 1, y + rh - 1], fill=colour)
        elif t == 0xFD and n >= 12:
            c, (x, y), fg, bg = f[1], struct.unpack_from("<HH", f, 2), tuple(f[6:9]), tuple(f[9:12])
            if bg != fg:
                draw.rectangle([x, y, x + 7, y + 9], fill=bg)
            if 32 < c < 127:
                draw.text((x, y - 1), chr(c), fill=fg, font=font)
        elif t == 0xFC and n > 4:
            col = tuple(f[1:4])
            for i, v in enumerate(f[4:]):
                draw.point((w - (n - 4) + i, min(v, 20)), fill=col)
    return img.resize((w * scale, h * scale), Image.NEAREST) if scale > 1 else img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m dirtyloader.m8screen", description=__doc__.split("\n\n")[0])
    ap.add_argument("out")
    ap.add_argument("--port")
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--keys", default="")
    args = ap.parse_args(argv)
    port = open_m8(args.port)
    try:
        frames = capture(port, keys=args.keys)
    finally:
        port.close()
    if not frames:
        print("error: no display frames (is m8c closed?)", file=sys.stderr)
        return 1
    render(frames, args.scale).save(args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
