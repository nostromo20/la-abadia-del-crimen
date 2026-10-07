#!/usr/bin/env python3
"""The game's colour rules (CHARCOL, src/colour.s), in Python: which QL colour a pixel of CPC pen
`pen`, drawn by source `cls`, shows at QL screen position (x, y) under palette `pal`, for a
mapping from data/colour_mapping.json. tools/colour_mapper.html's "Game" view follows the same
rules; tools/hdiff.py and tools/colourcheck.py compare the QL image against them.

Sources (the scene recorder's classes): 0 terrain, 1 characters, 2 lamp, 3 panel.
  - palettes 0 and 1 (black, parchment): the terrain row for everything (no sprites or panel
    are drawn under them);
  - characters: their own row (the game builds the sprite-mask path when it differs);
  - panel: its own row;
  - lamp: the terrain row (SpriteLuz only writes pen 3; mkpalette warns if lamp pen 3 differs);
  - a colour pair [a, b] is a 2x2 checker: a where x + y is even, b where odd.
Colour indices are the QL's G*4 + R*2 + B: black 0, blue 1, red 2, magenta 3, green 4, cyan 5,
yellow 6, white 7 (pngout.ql_mode8_to_indices).
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
NAMES = ["black", "blue", "red", "magenta", "green", "cyan", "yellow", "white"]
INDEX = {n: i for i, n in enumerate(NAMES)}


def load(path=None):
    return json.load(open(path or os.path.join(QL, "data", "colour_mapping.json")))


def row_for(mapping, pal, cls):
    e = mapping["palettes"][str(pal)]
    t = e["terrain"]
    if pal in (0, 1) or cls in (0, 2):
        return t
    if cls == 1:
        return e.get("characters", t)
    return e.get("panel", t)


def colour(mapping, pal, cls, pen, x, y):
    c = row_for(mapping, pal, cls)[pen]
    if isinstance(c, list):
        c = c[(x + y) & 1]
    return INDEX[c]
