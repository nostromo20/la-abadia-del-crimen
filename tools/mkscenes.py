#!/usr/bin/env python3
"""Scene data for tools/colour_mapper.html: real game frames from the HOST-ONLY scene recorder
(cpp/build_oracle_scenes.sh -> build/host/oracle_scenes, the PC oracle built with
QL_HOST_CLASSES), each pixel = CPC pen (0-3) + the source that drew it (0 terrain/tiles,
1 characters/sprites, 2 lamp light (SpriteLuz), 3 panel/HUD).

  mkscenes.py [--capture]     --capture re-runs the recorder (WSL) first

Writes tools/colour_scenes.js (var COLOUR_SCENES = {...}): pen|class<<2 per pixel (4 bits), 256 x 200
(CPC x 32..287; play area rows 0..159, panel 160..199), two pixels a byte (first in the high
nibble), zlib-deflated, base64 ("z"; the page inflates it with DecompressionStream("deflate")).
Nothing here touches the QL image.
"""
import base64, json, os, subprocess, sys, zlib
import qlpaths  # local tool paths (tools/qlpaths.py)

HERE = os.path.dirname(os.path.abspath(__file__))
QL = os.path.dirname(HERE)
SC = os.path.join(QL, "build", "scenes")
OUT = os.path.join(HERE, "colour_scenes.js")
WSL_QL = qlpaths.WSL_QL

# CPC hardware colours (the game's Paleta.h lists hardware ink numbers, in decimal)
CPC_HW = [(128, 128, 128), (128, 128, 128), (0, 255, 128), (255, 255, 128), (0, 0, 128), (255, 0, 128),
          (0, 128, 128), (255, 128, 128), (255, 0, 128), (255, 255, 128), (255, 255, 0), (255, 255, 255),
          (255, 0, 0), (255, 0, 255), (255, 128, 0), (255, 128, 255), (0, 0, 128), (0, 255, 128),
          (0, 255, 0), (0, 255, 255), (0, 0, 0), (0, 0, 255), (0, 128, 0), (0, 128, 255),
          (128, 0, 128), (128, 255, 128), (128, 255, 0), (128, 255, 255), (128, 0, 0), (128, 0, 255),
          (128, 128, 0), (128, 128, 255)]
PALETTES = [
    {"id": 0, "name": "black", "cpc_inks": [20, 20, 20, 20], "ql_now": ["black", "black", "black", "black"],
     "used": "Pergamino: while the parchment is being drawn (before its own palette is set)"},
    {"id": 1, "name": "parchment", "cpc_inks": [7, 28, 20, 12], "ql_now": ["white", "magenta", "black", "red"],
     "used": "intro and ending parchments (Pergamino); QL mapping provisional"},
    {"id": 2, "name": "day", "cpc_inks": [6, 14, 3, 20], "ql_now": ["cyan", "yellow", "red", "black"],
     "used": "the game by day (Marcador::muestraDiaYMomentoDia: every moment but night/compline), "
             "after the intro, after loading, the day-6 spiral (AccionesDia)"},
    {"id": 3, "name": "night", "cpc_inks": [4, 29, 0, 20], "ql_now": ["blue", "magenta", "white", "black"],
     "used": "night and compline (Marcador::muestraDiaYMomentoDia), after the day-6 spiral (AccionesDia)"},
]
NOTE_LAMP = ("Dark rooms (the library) do NOT switch palette: the room is drawn in pen 3 (fill) and "
             "Adso's lamp (SpriteLuz, an 80x80 sprite) leaves the lit shape; the colours are the day or "
             "night palette in force.")


def capture():
    cmds = [
        "cd %s" % WSL_QL,
        "mkdir -p build/scenes/day build/scenes/enter build/scenes/enter_night build/scenes/intro",
        "./build/host/oracle_scenes build/roms.bin tests/walk1.txt 2000 build/scenes/day/state.bin build/scenes/day $(seq 20 40 1999)",
        "./build/host/oracle_scenes build/roms.bin tests/enter.txt 900 build/scenes/enter/state.bin build/scenes/enter $(seq 20 25 899)",
        "FORCE_NIGHT=1 ./build/host/oracle_scenes build/roms.bin tests/enter.txt 900 build/scenes/enter_night/state.bin "
        "build/scenes/enter_night $(seq 20 25 899)",
        "printf '# idle\\n' > build/tmp/idle.txt",
        "INTRO=1 ./build/host/oracle_scenes build/roms.bin build/tmp/idle.txt 400 build/scenes/intro/state.bin build/scenes/intro $(seq 10 10 399)",
    ]
    subprocess.run(["wsl", "-e", "bash", "-c", " && ".join(cmds)], check=True,
                   env=dict(os.environ, MSYS_NO_PATHCONV="1"))


def frame(d, t):
    s = open(os.path.join(SC, d, "screen_%05d.bin" % t), "rb").read()
    c = open(os.path.join(SC, d, "cls_%05d.bin" % t), "rb").read()
    pal = int(open(os.path.join(SC, d, "pal_%05d.txt" % t)).read())
    st = open(os.path.join(SC, d, "state.bin"), "rb").read()
    room = st[t * 256 + 16]
    px = [[(s[y * 320 + x] & 3) | ((c[y * 320 + x] & 3) << 2) for x in range(32, 288)] for y in range(200)]
    return px, pal, room


def lamp_scene(panel_from):
    """the dark library: a real library screen (oracle --tour) seen through SpriteLuz's own fill
    pattern (rellenoLuz) with the lamp at the centre; outside the light sprite the room is the
    pen-3 fill (terrain), the light sprite's dark pixels are class lamp"""
    tour = os.path.join(QL, "build", "roomcmp", "tour_%03d.bin" % 0x67)
    s = open(tour, "rb").read()
    px = [[s[y * 320 + x] & 3 for x in range(32, 288)] for y in range(160)]
    patt = [0x00e0, 0x03f8, 0x07fc, 0x07fc, 0x0ffe, 0x0ffe, 0x1fff, 0x1fff,
            0x1fff, 0x1fff, 0x0ffe, 0x0ffe, 0x07fc, 0x07fc, 0x03f8, 0x00e0]
    # SpriteLuz::dibuja on an 80x80 pixel sprite, as the C++ walks it (p = pixel index)
    dark = set()
    izq, der, arriba, abajo = 0, 16, 0xa0 * 4, 0xf0 * 4      # character at x&3 == 0, y&7 < 4
    p = 0
    for _ in range(arriba):
        dark.add(p); p += 1
    for j in range(15):
        pos = p
        pat = patt[j]
        for _ in range(izq):
            for r in (0, 80, 160, 240): dark.add(p + r)
            p += 1
        for _ in range(16):
            if (pat & 0x8000) == 0:
                for _ in range(4):
                    for r in (0, 80, 160, 240): dark.add(p + r)
                    p += 1
            else:
                p += 4
            pat <<= 1
        for _ in range(der):
            for r in (0, 80, 160, 240): dark.add(p + r)
            p += 1
        p = pos + 80 * 4
    for _ in range(abajo):
        dark.add(p); p += 1
    x0, y0 = 88, 40                     # the light sprite's top-left in the play area
    out = []
    for y in range(160):
        row = []
        for x in range(256):
            lx, ly = x - x0, y - y0
            if 0 <= lx < 80 and 0 <= ly < 80:
                v = 3 | (2 << 2) if (ly * 80 + lx) in dark else px[y][x]
            else:
                v = 3                    # the dark room's pen-3 fill
            row.append(v)
        out.append(row)
    return out + panel_from[160:]


def pack(px):
    flat = [v for row in px for v in row]
    b = bytes((flat[i] << 4) | flat[i + 1] for i in range(0, len(flat), 2))
    return base64.b64encode(zlib.compress(b, 9)).decode()


def rle(px):
    flat = [v for row in px for v in row]
    out = bytearray()
    i = 0
    while i < len(flat):
        v = flat[i]
        n = 1
        while i + n < len(flat) and flat[i + n] == v and n < 256:
            n += 1
        out += bytes([n - 1, v])
        i += n
    return base64.b64encode(bytes(out)).decode()


def main():
    if "--capture" in sys.argv:
        capture()
    scenes = []

    def add(sid, title, d, t, note=""):
        px, pal, room = frame(d, t)
        title = title.replace("ROOM", "room 0x%02x" % room)
        scenes.append({"id": sid, "title": title, "palette": pal, "room": "0x%02x" % room,
                       "source": "oracle_scenes %s tick %d%s" % (d, t, (", " + note) if note else ""), "px": px})
        return px

    base = add("day_entrance", "Day: the abbey entrance, Guillermo and the abbot", "day", 100)
    add("day_hall_monks", "Day: ROOM, four monks", "enter", 320)
    add("day_b", "Day: ROOM", "enter", 495)
    add("day_c", "Day: ROOM", "enter", 545)
    add("day_d_monks", "Day: ROOM, several monks", "enter", 820)
    add("night_a", "Night: ROOM", "enter_night", 320, "FORCE_NIGHT (time of day set to NOCHE at tick 2)")
    add("night_b", "Night: ROOM", "enter_night", 820, "FORCE_NIGHT")
    add("night_entrance", "Night: ROOM (entrance)", "enter_night", 20, "FORCE_NIGHT")
    lp = lamp_scene(base)
    scenes.append({"id": "dark_library_lamp", "title": "Dark library with Adso's lamp (synthetic)", "palette": 3,
                   "room": "0x67", "source": "SYNTHETIC: oracle --tour screen 0x67 seen through SpriteLuz's fill "
                   "pattern (rellenoLuz) at the centre, panel from day_entrance; shown here at night, the game "
                   "uses whichever of day/night is in force", "px": lp})
    add("parchment", "The intro parchment", "intro", 300)
    out = {"version": 1, "layout": {"name": "A", "play_y": 28, "panel_y": 188, "w": 256, "h": 256},
           "classes": ["terrain", "characters", "lamp", "panel"],
           "cpc_hw_rgb": CPC_HW, "palettes": PALETTES, "note_lamp": NOTE_LAMP,
           "scenes": [{k: v for k, v in s.items() if k != "px"} | {"w": 256, "h": 200, "z": pack(s["px"])}
                      for s in scenes]}
    stats = {}
    for s in scenes:
        cnt = [0, 0, 0, 0]
        for row in s["px"]:
            for v in row:
                cnt[v >> 2] += 1
        stats[s["id"]] = cnt
    js = "// GENERATED by tools/mkscenes.py from the host-only scene recorder. Do not edit.\nvar COLOUR_SCENES = " + \
         json.dumps(out, separators=(",", ":")) + ";\n"
    open(OUT, "w", newline="\n").write(js)
    print("wrote %s (%d KB)" % (OUT, len(js) // 1024))
    for k, v in stats.items():
        print("  %-20s terrain %6d  characters %5d  lamp %5d  panel %5d" % (k, *v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
