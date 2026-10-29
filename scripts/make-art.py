# -*- coding: utf-8 -*-
"""Generate Rave Player's artwork: 1993/94 UK rave-flyer language.

Everything here is drawn from scratch — gradients, halftone, hazard stripes,
noise and type. No stock photography, nothing lifted off a flyer, so the
artwork is ours to ship.

    python3 scripts/make-art.py
"""

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "resources", "art")

BLACK = (7, 7, 10)
INK = (12, 12, 16)
ACID = (232, 255, 0)
MAGENTA = (255, 31, 143)
CYAN = (0, 224, 255)
ORANGE = (255, 106, 0)
PURPLE = (123, 47, 247)
WHITE = (245, 245, 240)

IMPACT = "/System/Library/Fonts/Supplemental/Impact.ttf"
DIN = "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf"
ARIAL_BLACK = "/System/Library/Fonts/Supplemental/Arial Black.ttf"


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def halftone(size, colour, spacing=14, radius=2.4, angle=0.0, alpha=255):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    width, height = size
    step = spacing
    for y in range(0, height + step, step):
        for x in range(0, width + step, step):
            ox = math.cos(angle) * (y * 0.4)
            cx = x + ox
            draw.ellipse([cx - radius, y - radius, cx + radius, y + radius],
                         fill=colour + (alpha,))
    return layer


def hazard(size, colour, spacing=46, width=16, angle=45):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    w, h = size
    span = int(math.hypot(w, h))
    for x in range(-span, span, spacing):
        draw.line([(x, -span), (x + span, span)], fill=colour + (255,), width=width)
    return layer.rotate(angle, expand=False, resample=Image.BICUBIC)


def vertical_gradient(size, top, bottom):
    base = Image.new("RGB", (1, size[1]))
    for y in range(size[1]):
        t = y / max(1, size[1] - 1)
        base.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return base.resize(size, Image.BILINEAR)


def glow(layer, radius=18):
    return layer.filter(ImageFilter.GaussianBlur(radius))


def noise(size, amount=10, seed=7):
    import numpy as np
    rng = np.random.default_rng(seed)
    shape = (size[1], size[0])
    return Image.fromarray(rng.integers(128 - amount, 128 + amount, shape, dtype=np.uint8), "L")


def text_with_offset(canvas, xy, text, fnt, fill, offset=(6, 6), offset_fill=MAGENTA, anchor="la"):
    draw = ImageDraw.Draw(canvas)
    x, y = xy
    draw.text((x + offset[0], y + offset[1]), text, font=fnt, fill=offset_fill, anchor=anchor)
    draw.text((x, y), text, font=fnt, fill=fill, anchor=anchor)


def tracked(draw, xy, text, fnt, fill, tracking=0, anchor_center=True):
    """Draw text with manual letter-spacing (PIL has no tracking)."""
    widths = [draw.textlength(ch, font=fnt) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x, y = xy
    if anchor_center:
        x -= total / 2
    for ch, width in zip(text, widths):
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += width + tracking
    return total


def vinyl(size, colour, cx, cy, r):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for ring in range(r, 8, -3):
        shade = 255 if (ring // 3) % 2 == 0 else 120
        draw.ellipse([cx - ring, cy - ring, cx + ring, cy + ring],
                     outline=colour + (max(8, shade // 8),), width=1)
    draw.ellipse([cx - r * 0.32, cy - r * 0.32, cx + r * 0.32, cy + r * 0.32],
                 outline=colour + (90,), width=2)
    return layer


def cassette(size, colour, box, alpha=255):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=14, outline=colour + (alpha,), width=7)
    inner = (x0 + 26, y0 + 26, x1 - 26, y0 + (y1 - y0) // 2 + 6)
    draw.rounded_rectangle(inner, radius=8, outline=colour + (alpha,), width=5)
    cy = y0 + (y1 - y0) * 0.72
    for cx in (x0 + (x1 - x0) * 0.34, x0 + (x1 - x0) * 0.66):
        draw.ellipse([cx - 26, cy - 26, cx + 26, cy + 26], outline=colour + (alpha,), width=6)
        draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=colour + (alpha,), width=4)
    return layer


def signal(size, colour, cx, cy, r0=40, rings=5, step=52):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for index in range(rings):
        r = r0 + index * step
        bbox = [cx - r, cy - r, cx + r, cy + r]
        draw.arc(bbox, start=-52, end=52, fill=colour + (200 - index * 30,), width=9)
        draw.arc(bbox, start=128, end=232, fill=colour + (200 - index * 30,), width=9)
    draw.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=colour + (255,))
    return layer


def chevrons(size, colour, y, width=120, height=70, count=4, alpha=200):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x = 40
    for index in range(count):
        fade = max(40, alpha - index * 40)
        draw.line([(x, y + height), (x + width // 2, y), (x + width, y + height)],
                  fill=colour + (fade,), width=14, joint="curve")
        x += width - 26
    return layer


def finish(img, add_noise=True):
    if not add_noise:
        return img
    import numpy as np
    arr = np.asarray(img).astype(np.int16)
    grain = np.asarray(noise(img.size, 9)).astype(np.int16)
    arr = np.clip(arr + (grain - 128)[:, :, None] // 2, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def base_canvas(size, colour, accent):
    canvas = vertical_gradient(size, (10, 10, 14), (4, 4, 6)).convert("RGBA")
    canvas = Image.alpha_composite(canvas, halftone(size, colour, spacing=16, radius=2.2, alpha=26))
    canvas = Image.alpha_composite(canvas, vinyl(size, accent, int(size[0] * 0.86), int(size[1] * 0.18), int(size[0] * 0.42)))
    return canvas


def make_icon(path, label, accent, glyph=None):
    size = (512, 512)
    canvas = vertical_gradient(size, (14, 14, 20), (5, 5, 8)).convert("RGBA")
    canvas = Image.alpha_composite(canvas, halftone(size, accent, spacing=13, radius=2.0, alpha=34))
    canvas = Image.alpha_composite(canvas, vinyl(size, accent, 430, 92, 210))

    if glyph:
        canvas.alpha_composite(glyph.resize((296, 296), Image.LANCZOS), (108, 30))

    # dark scrim so the label always sits on black, whatever the glyph does
    scrim = Image.new("L", (1, size[1]))
    for y in range(size[1]):
        value = 0 if y < 250 else int(232 * (y - 250) / (size[1] - 250))
        scrim.putpixel((0, y), value)
    scrim = scrim.resize(size)
    canvas = Image.composite(Image.new("RGBA", size, (5, 5, 8, 255)), canvas, scrim)

    draw = ImageDraw.Draw(canvas)
    for (x, y, dx, dy) in ((26, 26, 1, 1), (486, 26, -1, 1), (26, 486, 1, -1), (486, 486, -1, -1)):
        draw.line([(x, y), (x + 54 * dx, y)], fill=WHITE + (200,), width=5)
        draw.line([(x, y), (x, y + 54 * dy)], fill=WHITE + (200,), width=5)

    size_px = 138
    while size_px > 56 and draw.textlength(label.upper(), font=font(IMPACT, size_px)) > 398:
        size_px -= 4
    big = font(IMPACT, size_px)
    text_with_offset(canvas, (250, 368), label.upper(), big, WHITE, offset=(7, 7),
                     offset_fill=accent, anchor="mm")
    tracked(draw, (256, 440), "RAVE PLAYER", font(DIN, 32), accent + (235,), tracking=5)

    finish(canvas.convert("RGB")).save(path, "PNG", optimize=True)


def make_main_icon(path):
    size = (512, 512)
    canvas = vertical_gradient(size, (16, 16, 22), (4, 4, 6)).convert("RGBA")
    canvas = Image.alpha_composite(canvas, halftone(size, ACID, spacing=12, radius=2.1, alpha=40))
    canvas = Image.alpha_composite(canvas, vinyl(size, MAGENTA, 430, 90, 220))
    canvas = Image.alpha_composite(canvas, chevrons(size, ACID, 44, width=86, height=50, count=4, alpha=120))

    draw = ImageDraw.Draw(canvas)
    word_size = 128
    while word_size > 64 and max(draw.textlength("RAVE", font=font(IMPACT, word_size)),
                                 draw.textlength("PLAYER", font=font(IMPACT, word_size))) > 430:
        word_size -= 4
    big = font(IMPACT, word_size)
    text_with_offset(canvas, (34, 128), "RAVE", big, ACID, offset=(8, 8), offset_fill=MAGENTA)
    text_with_offset(canvas, (34, 128 + int(word_size * 0.92)), "PLAYER", big, WHITE,
                     offset=(8, 8), offset_fill=CYAN)

    tag_size = 26
    while tag_size > 14 and draw.textlength("OLDSKOOL · JUNGLE · HARDCORE", font=font(DIN, tag_size)) > 430:
        tag_size -= 2
    tracked(draw, (36, 396), "OLDSKOOL · JUNGLE · HARDCORE", font(DIN, tag_size), WHITE + (235,),
            tracking=2, anchor_center=False)

    draw.rounded_rectangle([36, 434, 206, 478], radius=8, outline=ACID + (255,), width=4)
    tracked(draw, (121, 450), "93 / 94", font(DIN, 28), ACID + (255,), tracking=4)

    finish(canvas.convert("RGB")).save(path, "PNG", optimize=True)


def make_fanart(path):
    size = (1920, 1080)
    canvas = vertical_gradient(size, (16, 16, 24), (3, 3, 5)).convert("RGBA")
    canvas = Image.alpha_composite(canvas, halftone(size, CYAN, spacing=15, radius=2.4, alpha=28))
    canvas = Image.alpha_composite(canvas, vinyl(size, MAGENTA, 1520, 300, 430))
    canvas = Image.alpha_composite(canvas, vinyl(size, ACID, 150, 940, 300))

    band = Image.new("RGBA", size, (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(band)
    for x in range(-50, size[0] + 50, 56):
        bdraw.polygon([(x, 0), (x + 28, 0), (x + 6, 26), (x - 22, 26)], fill=ACID + (235,))
    canvas = Image.alpha_composite(canvas, band)

    big = font(IMPACT, 240)
    text_with_offset(canvas, (90, 96), "RAVE", big, ACID, offset=(14, 14), offset_fill=MAGENTA)
    text_with_offset(canvas, (90, 330), "PLAYER", big, WHITE, offset=(14, 14), offset_fill=CYAN)

    draw = ImageDraw.Draw(canvas)
    tracked(draw, (96, 640), "OLDSKOOL · JUNGLE · DRUM & BASS · HARDCORE", font(DIN, 46),
            WHITE + (240,), tracking=3, anchor_center=False)
    tracked(draw, (96, 706), "TAPE PACKS · PIRATE RADIO · LIVE STREAMS", font(DIN, 36),
            MAGENTA + (245,), tracking=3, anchor_center=False)

    draw.rounded_rectangle([96, 800, 640, 876], radius=12, outline=ACID + (255,), width=6)
    tracked(draw, (368, 838), "EST. 2014 · REBUILT 2026", font(DIN, 32), ACID + (255,), tracking=4)

    for index, colour in enumerate((ACID, MAGENTA, CYAN, ORANGE)):
        x = 1460 + index * 96
        draw.rectangle([x, 900, x + 72, 972], fill=colour + (235,))

    finish(canvas.convert("RGB")).save(path, "JPEG", quality=90, optimize=True)


def make_preview(icon_paths, path):
    cols, cell = 5, 300
    rows = math.ceil(len(icon_paths) / cols)
    sheet = Image.new("RGB", (cols * cell, rows * cell + 60), (12, 12, 16))
    draw = ImageDraw.Draw(sheet)
    for index, icon_path in enumerate(icon_paths):
        icon = Image.open(icon_path).convert("RGB").resize((cell - 24, cell - 24), Image.LANCZOS)
        x = (index % cols) * cell + 12
        y = (index // cols) * cell + 12
        sheet.paste(icon, (x, y))
    draw.text((16, rows * cell + 16), "RAVE PLAYER · 2026 ARTWORK", font=font(DIN, 28), fill=(230, 255, 0))
    sheet.save(path, "JPEG", quality=88)


def main():
    os.makedirs(ART, exist_ok=True)

    def bolt(size_colour):
        def draw_glyph():
            layer = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            d.polygon([(300, 70), (180, 280), (256, 280), (212, 440), (352, 220), (272, 220)],
                      fill=size_colour + (235,))
            return layer
        return draw_glyph()

    def tower(colour):
        layer = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.line([(256, 330), (256, 110)], fill=colour + (255,), width=10)
        for y, r in ((150, 46), (212, 76), (274, 106)):
            d.arc([256 - r, y - r, 256 + r, y + r], start=-60, end=60, fill=colour + (200,), width=8)
            d.arc([256 - r, y - r, 256 + r, y + r], start=120, end=240, fill=colour + (200,), width=8)
        d.ellipse([244, 320, 268, 344], fill=colour + (255,))
        d.rectangle([180, 340, 332, 356], fill=colour + (255,))
        return layer

    def magnifier(colour):
        layer = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.ellipse([150, 120, 350, 320], outline=colour + (240,), width=16)
        d.line([(330, 300), (410, 390)], fill=colour + (240,), width=22)
        return layer

    def house(colour):
        layer = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.polygon([(256, 110), (400, 250), (112, 250)], fill=colour + (230,))
        d.rectangle([150, 250, 362, 400], outline=colour + (235,), width=12)
        d.rectangle([226, 316, 286, 400], outline=colour + (235,), width=8)
        return layer

    def info(colour):
        layer = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.ellipse([150, 110, 362, 322], outline=colour + (240,), width=14)
        d.ellipse([248, 150, 264, 166], fill=colour + (255,))
        d.rectangle([246, 196, 266, 300], fill=colour + (255,))
        return layer

    make_main_icon(os.path.join(ROOT, "icon.png"))
    make_fanart(os.path.join(ROOT, "fanart.jpg"))

    icons = [
        ("radio", "LIVE", CYAN, signal((512, 512), CYAN, 256, 200, r0=30, rings=4, step=46)),
        ("rave", "RAVE", ACID, None),
        ("jungle", "JUNGLE", MAGENTA, None),
        ("hardcore", "HARDCORE", ORANGE, bolt(ORANGE)),
        ("house", "HOUSE", PURPLE, house(PURPLE)),
        ("pirate", "PIRATE", ACID, tower(ACID)),
        ("tapepacks", "TAPES", CYAN, cassette((512, 512), CYAN, (110, 170, 402, 342))),
        ("search", "SEARCH", WHITE, magnifier(WHITE)),
        ("about", "ABOUT", CYAN, info(CYAN)),
    ]

    paths = []
    for slug, label, colour, glyph in icons:
        path = os.path.join(ART, slug + ".png")
        make_icon(path, label, colour, glyph)
        paths.append(path)

    make_preview(paths, os.path.join(ART, "preview.jpg"))
    print("artwork written to resources/art and add-on root")


if __name__ == "__main__":
    main()
