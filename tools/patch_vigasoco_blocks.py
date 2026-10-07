#!/usr/bin/env python3
"""One-shot: swap the fork's VGA blocks for the commented-out CPC blocks in the imported
VIGASOCO copies. Nothing is deleted: the VGA code is kept under '#if 0 // VGA (fork)'.
Each edit asserts its anchors match exactly once."""
import io, os, sys

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cpp", "vigasoco")


def rd(f):
    return io.open(os.path.join(D, f), encoding="utf-8").read()


def wr(f, s):
    with io.open(os.path.join(D, f), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(s)


def once(s, old, new):
    c = s.count(old)
    assert c == 1, (c, old[:80])
    return s.replace(old, new)


def uncomment_block(s, start, end):
    """Text between `start` (e.g. '/* CPC' or '// CPC\\n/*') and the next `end` ('*/') becomes live."""
    i = s.index(start)
    assert s.count(start) == 1, start
    j = s.index(end, i + len(start))
    body = s[i + len(start):j]
    return s[:i] + "// CPC (restored for the QL)" + body + s[j + len(end):]


def vga_if0(s, start, end_marker):
    """Wrap from `start` up to (not including) `end_marker` in #if 0."""
    assert s.count(start) == 1, start
    i = s.index(start)
    j = s.index(end_marker, i)
    return s[:i] + "#if 0 // VGA (fork)\n" + s[i:j] + "#endif\n" + s[j:]


# ---- SpriteMonje: habit table + dibuja ----
s = rd("SpriteMonje.cpp")
if "#if 0 // VGA" in s:
    print("SpriteMonje already patched")
else:
  if True:
    s = vga_if0(s, "// VGA\nint SpriteMonje::despAnimTraje[16]", "/////////////////////////////////////////////////////////////////////////////\n// inicializ")
    s = uncomment_block(s, "// CPC\n/*\nint SpriteMonje::despAnimTraje", "*/")
    s = s.replace("// CPC (restored for the QL)", "// CPC (restored for the QL)\nint SpriteMonje::despAnimTraje", 1)
    s = vga_if0(s, "// VGA\n// dibuja la parte visible", "\x00") if False else s
    i = s.index("// VGA\n// dibuja la parte visible")
    s = s[:i] + "#if 0 // VGA (fork)\n" + s[i:] + "#endif\n"
    s = uncomment_block(s, "/* CPC\n// dibuja la parte visible", "*/")
    wr("SpriteMonje.cpp", s)

# ---- Sprite: dibuja uses the CPC body ----
s = rd("Sprite.cpp")
s = once(s, "\tdibujaVGA(spr,bufferMezclas,lgtudClipX,lgtudClipY,dist1X,dist2X,dist1Y,dist2Y);\n\n/* CPC\n",
         "/* CPC\n")
s = uncomment_block(s, "/* CPC\n", "*/")
s = vga_if0(s, "void Sprite::dibujaVGA(", "/////////////////////////////////////////////////////////////////////////////\n// m")
wr("Sprite.cpp", s)
h = io.open(os.path.join(D, "Sprite.h"), encoding="utf-8").read()
h = once(h, "private:\n\tvoid dibujaVGA(", "private:\n\t// VGA (fork) only: void dibujaVGA(")
wr("Sprite.h", h)

# ---- SpriteLuz: black is ink 3 ----
s = rd("SpriteLuz.cpp")
s = once(s, "\t\t// CPC *bufferMezclas = 3;\n\t\t*bufferMezclas = 0; // VGA\n\t\tbufferMezclas++;\n\t}\n\n\t// para 15",
         "\t\t*bufferMezclas = 3;\n\t\tbufferMezclas++;\n\t}\n\n\t// para 15")
s = once(s, "\t\t// CPC *bufferMezclas = 3;\n\t\t*bufferMezclas = 0; // VGA\n\t\tbufferMezclas++;\n\t}\n}",
         "\t\t*bufferMezclas = 3;\n\t\tbufferMezclas++;\n\t}\n}")
vga = "bufferMezclas[0] = bufferMezclas[20*4] = bufferMezclas[40*4] = bufferMezclas[60*4] = 0;"
assert s.count(vga) == 3
s = s.replace(vga, "bufferMezclas[0] = bufferMezclas[20*4] = bufferMezclas[40*4] = bufferMezclas[60*4] = 3;")
wr("SpriteLuz.cpp", s)
print("ok")
