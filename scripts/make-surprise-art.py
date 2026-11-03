#!/usr/bin/env python3
"""Generate the Surprise Me burst background (stdlib only; dev helper).

The 2026 sticker style is black ink, pink spot colour and a halftone dot grid;
this draws a radial burst with transparent-looking dark wedges into a 1280x720
PNG.  No external image library is needed.
"""
import math
import os
import struct
import zlib

W, H = 1280, 720
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "resources", "art", "surprise-burst.png")


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def _pixel(x, y):
    cx, cy = W * 0.55, H * 0.48
    dx, dy = x - cx, y - cy
    dist = math.sqrt(dx * dx + dy * dy)
    angle = (math.atan2(dy, dx) + math.pi) / (math.pi * 2)
    # 18 bursts: alternating pink beams over near-black ink.
    if (angle * 18) % 1.0 < 0.52 and dist < 860:
        fade = max(0.0, 1.0 - dist / 900.0)
        return (18 + int(72 * fade), 3 + int(10 * fade), 16 + int(34 * fade))
    # Halftone dots, sparse and warm.
    if int(x / 18) % 2 == 0 and int(y / 18) % 2 == 0 and (x * 7 + y * 11) % 29 < 3:
        return (65, 24, 50)
    return (12, 12, 16)


def main():
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        for x in range(W):
            raw.extend(_pixel(x, y))
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += _chunk(b"IEND", b"")
    with open(OUT, "wb") as handle:
        handle.write(png)
    jpg = OUT[:-4] + ".jpg"
    import subprocess
    subprocess.run(["sips", "-s", "format", "jpeg", OUT, "--out", jpg],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.remove(OUT)
    print("wrote %s" % jpg)


if __name__ == "__main__":
    main()
