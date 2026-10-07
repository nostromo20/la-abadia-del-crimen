#!/usr/bin/env python3
"""One-shot import of the VIGASOCO (Samuel85/Abbey) logic sources into QL/cpp/vigasoco.

The Abbey clone (ABBEY_SRC, tools/qlpaths.py) is treated as read-only. This copies the files the
QL build compiles, normalising text to UTF-8 + LF (the originals mix Latin-1 and UTF-8
comments). After import the copies in cpp/vigasoco are the source of truth and are
hand-patched (CPC graphics paths restored, SDL/VGA code removed) -- see cpp/README.txt.

Refuses to overwrite an existing file unless --force is given (hand edits would be lost).
"""
import argparse, os, sys
import qlpaths  # local tool paths (tools/qlpaths.py)

SRC = qlpaths.ABBEY_VIGASOCO
DST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cpp", "vigasoco")

FILES = """
Logica AccionesDia Abad Adso Malaquias Berengario Severino Jorge Bernardo Guillermo Monje
Personaje PersonajeConIA BuscadorRutas GestorFrases Puerta Objeto RejillaPantalla
FijarOrientacion EntidadJuego TransformacionesCamara MotorGrafico GeneradorPantallas Comandos
Sprite SpriteMonje SpriteLuz MezcladorSprites Marcador Serializar
""".split()
HEADERS_ONLY = ["Singleton", "Types", "Comando", "sonidos"]


def decode(b):
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("latin-1")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(DST, exist_ok=True)
    names = []
    for f in FILES:
        names += [f + ".cpp", f + ".h"]
    names += [h + ".h" for h in HEADERS_ONLY]
    n = 0
    for name in names:
        sp = os.path.join(SRC, name)
        if not os.path.exists(sp):
            continue
        dp = os.path.join(DST, name)
        if os.path.exists(dp) and not a.force:
            print("exists, skipped:", name)
            continue
        txt = decode(open(sp, "rb").read()).replace("\r\n", "\n").replace("\r", "\n")
        with open(dp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(txt)
        n += 1
    print("imported", n, "files to", DST)


if __name__ == "__main__":
    sys.exit(main())
