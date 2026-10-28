#!/usr/bin/env python3
"""Color the Iconify SVGs in research/figures/assets/icons and convert them to PDF for the report layout.

Usage: python3 latex/make_icons.py   (from paper/; needs rsvg-convert). Output: figures/icons/<name>.pdf
"""
import os, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "..", "figures", "assets", "icons")
OUT = os.path.join(HERE, "..", "figures", "icons")
ACCENT, MUTED = "#1A73E8", "#4B5563"  # accent = Gemma blue
ICONS = {  # output name: (Iconify file, color)
    "stamp": ("lucide--stamp", ACCENT), "school": ("lucide--graduation-cap", MUTED),
    "supplement": ("lucide--file-text", MUTED), "github": ("simple-icons--github", MUTED),
    "kaggle": ("simple-icons--kaggle", MUTED),
}
os.makedirs(OUT, exist_ok=True)
for name, (src, color) in ICONS.items():
    svg = open(os.path.join(SRC, src + ".svg")).read()
    if color:
        svg = svg.replace("currentColor", color)
    svg = svg.replace('width="1em" height="1em"', 'width="96" height="96"')
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(svg)
    subprocess.run(["rsvg-convert", "-f", "pdf", "-o", os.path.join(OUT, name + ".pdf"), f.name], check=True)
    os.unlink(f.name)
print(f"{len(ICONS)} icons in {OUT}")
