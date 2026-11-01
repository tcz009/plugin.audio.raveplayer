#!/usr/bin/env python3
"""Generate the spinning-head download frames (dev-only, Pillow).

Usage: python3 scripts/make-spinner.py
Writes resources/art/spinner/head-{128,256}-XX.png (10 frames each).
The icon is alpha-masked to its circular head so rotation leaves the corners
transparent instead of spinning the yellow square.
"""
import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "icon.png")
OUT = os.path.join(ROOT, "resources", "art", "spinner")
FRAMES = 10

os.makedirs(OUT, exist_ok=True)
image = Image.open(SOURCE).convert("RGBA")
mask = Image.new("L", image.size, 0)
ImageDraw.Draw(mask).ellipse((4, 4, image.size[0] - 4, image.size[1] - 4), fill=255)
image.putalpha(mask)
for index in range(FRAMES):
    angle = -360.0 * index / FRAMES
    frame = image.rotate(angle, resample=Image.BICUBIC, expand=False)
    for size in (128, 256):
        resized = frame.resize((size, size), Image.LANCZOS)
        resized.save(os.path.join(OUT, "head-%d-%02d.png" % (size, index)))
print("wrote %d frames x2 sizes to %s" % (FRAMES, OUT))
