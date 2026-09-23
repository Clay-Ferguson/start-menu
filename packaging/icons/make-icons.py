#!/usr/bin/env python3
"""Regenerate the installable PNG icon set from source.png beside it.

Only needed when the source artwork changes; the PNGs it writes are checked
in, so build-deb.sh never has to convert anything (and never needs Pillow).

    uv run --with pillow packaging/icons/make-icons.py

The source is 128x110, not square, and an icon theme's sizes are squares: it
is centered on a transparent square canvas first, so nothing is stretched.
Sizes stop at the source's own width — anything larger would only be the
same picture blurred. The largest is also copied into the package as the
window icon (start_menu/data/start-menu.png), which a checkout run needs
because no desktop entry is installed to supply one.
"""
from pathlib import Path

from PIL import Image

SIZES = (16, 22, 24, 32, 48, 64, 128)

root = Path(__file__).resolve().parent
art = Image.open(root / "source.png").convert("RGBA")
side = max(art.size)
square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
square.paste(art, ((side - art.width) // 2, (side - art.height) // 2))

for size in SIZES:
    out = root / "hicolor" / f"{size}x{size}" / "apps" / "start-menu.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    square.resize((size, size), Image.LANCZOS).save(out, optimize=True)
    print(out.relative_to(root.parents[1]))

window_icon = root.parents[1] / "start_menu" / "data" / "start-menu.png"
square.resize((max(SIZES), max(SIZES)), Image.LANCZOS).save(window_icon, optimize=True)
print(window_icon.relative_to(root.parents[1]))
