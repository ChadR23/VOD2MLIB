"""Generate logo.png to the design handoff's spec.

Reproducible: re-run after editing tokens to refresh the bundled logo.

Spec (from design_handoff_vod2mlib_modal/README.md):
  - Square, rounded corners (radius 8 at 34px → 60 at 256px)
  - Background: linear-gradient(135deg, #1f2937, #0d1117)
  - Border: 1px (scale up at higher resolution) #2a323d
  - Glyph: 'V', color #2f81f7, weight 800, centred

Output: ../logo.png at 512×512 px (Dispatcharr's plugin browser scales down).
"""
from PIL import Image, ImageDraw, ImageFont
import os
import sys

# --- tokens from the design handoff ---
SIZE = 512
RADIUS = int(SIZE * 8 / 34)            # design uses radius 8 at 34px
BORDER_WIDTH = max(1, SIZE // 256)     # ~2px at 512
GRAD_TOP_LEFT = (0x1f, 0x29, 0x37)     # #1f2937
GRAD_BOTTOM_RIGHT = (0x0d, 0x11, 0x17) # #0d1117
BORDER_COLOR = (0x2a, 0x32, 0x3d)      # #2a323d
GLYPH_COLOR = (0x2f, 0x81, 0xf7)       # #2f81f7
GLYPH = "V"

# Font candidates in priority order (bold/heavy weights for design weight 800)
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def find_font(target_height: int) -> ImageFont.FreeTypeFont:
    """Return the first available font sized to fit roughly target_height."""
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            return ImageFont.truetype(path, size=target_height)
    return ImageFont.load_default()


def diagonal_gradient(size: int, top_left: tuple, bottom_right: tuple) -> Image.Image:
    """Build a 135-degree linear gradient (top-left → bottom-right)."""
    img = Image.new("RGB", (size, size), top_left)
    pixels = img.load()
    # Diagonal length (in normalised units) is along (1,1).
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            r = int(top_left[0] + (bottom_right[0] - top_left[0]) * t)
            g = int(top_left[1] + (bottom_right[1] - top_left[1]) * t)
            b = int(top_left[2] + (bottom_right[2] - top_left[2]) * t)
            pixels[x, y] = (r, g, b)
    return img


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def main():
    # Background gradient on transparent canvas
    base = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    grad = diagonal_gradient(SIZE, GRAD_TOP_LEFT, GRAD_BOTTOM_RIGHT)
    mask = rounded_mask(SIZE, RADIUS)
    base.paste(grad, (0, 0), mask)

    draw = ImageDraw.Draw(base)

    # Border (rounded rectangle, drawn with the same radius)
    draw.rounded_rectangle(
        (BORDER_WIDTH // 2, BORDER_WIDTH // 2,
         SIZE - 1 - BORDER_WIDTH // 2, SIZE - 1 - BORDER_WIDTH // 2),
        radius=RADIUS,
        outline=BORDER_COLOR,
        width=BORDER_WIDTH,
    )

    # Glyph: aim for a V that fills ~70% of the square height
    target_height = int(SIZE * 0.62)
    font = find_font(target_height)

    # Centre using font metrics
    bbox = draw.textbbox((0, 0), GLYPH, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    # Visual centring needs a small upward nudge for V (most fonts have descender room)
    x = (SIZE - text_w) // 2 - bbox[0]
    y = (SIZE - text_h) // 2 - bbox[1]
    draw.text((x, y), GLYPH, fill=GLYPH_COLOR, font=font)

    out = os.path.join(os.path.dirname(__file__), "..", "logo.png")
    base.save(out, "PNG", optimize=True)
    print(f"Wrote {os.path.abspath(out)} ({SIZE}x{SIZE})")


if __name__ == "__main__":
    main()
