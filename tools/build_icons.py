"""Render original SVG sources with resvg-py. No Blender dependency.

python tools/build_icons.py [--contact-sheet path.png]
Build dependencies: resvg-py==0.5.0, Pillow (only for the contact sheet).
SPDX-License-Identifier: GPL-3.0-or-later
"""

import argparse
from pathlib import Path

import resvg_py

DIRECTORY = Path(__file__).resolve().parents[1] / "notuodesk_3ds_maxxed" / "icons"


def build(contact_sheet=None):
    sources = sorted((DIRECTORY / "src").glob("*.svg"))
    for index, source in enumerate(sources, 1):
        print(f"[{index}/{len(sources)}] {source.stem}", flush=True)
        for size, suffix in ((32, ""), (64, "@2x")):
            png = resvg_py.svg_to_bytes(svg_path=str(source), width=size, height=size,
                                        skip_system_fonts=True)
            (DIRECTORY / (source.stem + suffix + ".png")).write_bytes(png)
    if contact_sheet:
        from PIL import Image, ImageDraw, ImageFont
        columns, cell_w, cell_h = 6, 210, 100
        rows = (len(sources) + columns - 1) // columns
        sheet = Image.new("RGB", (columns * cell_w, rows * cell_h + 72), "#343434")
        draw = ImageDraw.Draw(sheet)
        font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 13)
        draw.text((18, 12), "NotuoDesk original Max-style icons | GPL-3.0-or-later", font=font, fill="#ededed")
        draw.text((18, 34), "Actual 16px / 32px / 64px sizes. Authored SVG paths, no Autodesk artwork.",
                  font=font, fill="#bcbcbc")
        for i, source in enumerate(sources):
            x, y = (i % columns) * cell_w, (i // columns) * cell_h + 72
            draw.rectangle((x, y, x + cell_w - 1, y + cell_h - 1), outline="#484848")
            original = Image.open(DIRECTORY / (source.stem + "@2x.png")).convert("RGBA")
            for size, dx in ((16, 12), (32, 42), (64, 94)):
                tile = original.resize((size, size), Image.Resampling.LANCZOS)
                sheet.paste(tile, (x + dx, y + 4 + (64 - size) // 2), tile)
            draw.text((x + 10, y + 78), source.stem, font=font, fill="#ededed")
        target = Path(contact_sheet)
        target.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(target)
        print(f"Contact sheet: {target}", flush=True)
    print(f"Built {len(sources)} SVGs at 32px and 64px", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contact-sheet")
    build(parser.parse_args().contact_sheet)
