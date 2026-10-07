#!/usr/bin/env python3
"""One-shot: restore the CPC code paths in the imported VIGASOCO copies (cpp/vigasoco).

The Samuel85/Abbey fork switched graphics to a 256-colour VGA set and changed several input
tests. Each patch below puts back the CPC path that the fork left commented out. Every
pattern must match exactly once or the script aborts without writing anything.
"""
import io, os, sys

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cpp", "vigasoco")

P = []
def p(f, old, new, count=1):
    P.append((f, old, new, count))

# ---- monk faces (CPC offsets) ----
for f, cpc, vga in [("Abad.cpp", "0xb167", "67308"), ("Malaquias.cpp", "0xb1cb", "67708"),
                    ("Severino.cpp", "0xb103", "66908"), ("Jorge.cpp", "0xb2f7", "68908"),
                    ("Bernardo.cpp", "0xb293", "68508")]:
    p(f, "datosCara[0] = %s;" % vga, "datosCara[0] = %s;" % cpc)
    p(f, "datosCara[1] = %s+0x32*4;" % vga, "datosCara[1] = %s + 0x32;" % cpc)
p("Berengario.cpp", "datosCara[0] = 68108;", "datosCara[0] = 0xb22f;")
p("Berengario.cpp", "datosCara[1] = 68108+0x32*4;", "datosCara[1] = 0xb22f + 0x32;")
p("Berengario.cpp", "datosCara[0] = 69308;", "datosCara[0] = 0xb35b;")
p("Berengario.cpp", "datosCara[1] = 69308+0x32*4;", "datosCara[1] = 0xb35b + 0x32;")

# ---- animation tables (CPC graphics addresses) ----
for a, b in [("54480, 0x05, 0x22", "0xa3b4, 0x05, 0x22"), ("53760, 0x05, 0x24", "0xa300, 0x05, 0x24"),
             ("55180, 0x05, 0x22", "0xa45e, 0x05, 0x22"), ("57240, 0x04, 0x21", "0xa666, 0x04, 0x21"),
             ("55880, 0x05, 0x23", "0xa508, 0x05, 0x23"), ("56580, 0x05, 0x21", "0xa5b7, 0x05, 0x21")]:
    n = 2 if a.startswith(("54480", "57240")) else 1
    p("Guillermo.cpp", "{ %s }" % a, "{ %s }" % b, n)
for a, b in [("58408, 0x05, 0x20", "0xa78a, 0x05, 0x20"), ("57768, 0x05, 0x20", "0xa6ea, 0x05, 0x20"),
             ("59048, 0x05, 0x1f", "0xa82a, 0x05, 0x1f"), ("59668, 0x04, 0x1e", "0xa8c5, 0x04, 0x1e"),
             ("60148, 0x04, 0x1e", "0xa93d, 0x04, 0x1e"), ("60628, 0x04, 0x1e", "0xa9b5, 0x04, 0x1e")]:
    n = 2 if a.startswith(("58408", "59668")) else 1
    p("Adso.cpp", "{ %s }" % a, "{ %s }" % b, n)

# ---- flipped graphics live 0xc000 above the originals on the CPC ----
p("Personaje.cpp", "sprite->despGfx += 120305;", "sprite->despGfx += despFlipX;")
p("Puerta.cpp", "sprite->despGfx = 69708 + 120305*despOrientacion[oriPuerta][7]; // VGA",
  "sprite->despGfx = 0x0aa49 + 0xc000*despOrientacion[oriPuerta][7];")

# ---- monk habits (CPC table) ----
vga_tab = """	61628, // 0x0ab59 + 0x0082,
	61108, // 0x0ab59 + 0x0000,
	61628, // 0x0ab59 + 0x0082,
	62108, // 0x0ab59 + 0x00fa,
	63548, // 0x0ab59 + 0x0262,
	62588, // 0x0ab59 + 0x0172,
	63548, // 0x0ab59 + 0x0262,
	63088, // 0x0ab59 + 0x01ef,
	63548+120305, // 0x16b59 + 0x0262,
	62588+120305, // 0x16b59 + 0x0172,
	63548+120305, // 0x16b59 + 0x0262,
	63088+120305, // 0x16b59 + 0x01ef,
	61628+120305, // 0x16b59 + 0x0082,
	61108+120305, // 0x16b59 + 0x0000,
	61628+120305, // 0x16b59 + 0x0082,
	62108+120305, // 0x16b59 + 0x00fa
"""
cpc_tab = """	0x0ab59 + 0x0082,
	0x0ab59 + 0x0000,
	0x0ab59 + 0x0082,
	0x0ab59 + 0x00fa,
	0x0ab59 + 0x0262,
	0x0ab59 + 0x0172,
	0x0ab59 + 0x0262,
	0x0ab59 + 0x01ef,
	0x16b59 + 0x0262,
	0x16b59 + 0x0172,
	0x16b59 + 0x0262,
	0x16b59 + 0x01ef,
	0x16b59 + 0x0082,
	0x16b59 + 0x0000,
	0x16b59 + 0x0082,
	0x16b59 + 0x00fa
"""
# SpriteMonje.cpp table: patched by hand (trailing whitespace in the original)

# ---- black is ink 3 on the CPC (the fork used VGA colour 0) ----
p("Adso.cpp", "elMotorGrafico->genPant->limpiaPantalla(0); // VGA", "elMotorGrafico->genPant->limpiaPantalla(3);")
p("Adso.cpp", 'elMarcador->imprimeFrase("S:N", 148, 164, 4, 0); // VGA', 'elMarcador->imprimeFrase("S:N", 148, 164, 2, 3);')
p("Adso.cpp", 'elMarcador->imprimeFrase("   ", 148, 164, 4, 0); // VGA', 'elMarcador->imprimeFrase("   ", 148, 164, 2, 3);')
p("Jorge.cpp", "elJuego->limpiaAreaJuego(0); // VGA", "elJuego->limpiaAreaJuego(3);")
p("GestorFrases.cpp", "elJuego->marcador->imprimirCaracter(caracter, 216, 164, 4, 0);",
  "elJuego->marcador->imprimirCaracter(caracter, 216, 164, 2, 3);")
p("GestorFrases.cpp", "elJuego->marcador->imprimirCaracter(0x20, 216, 164, 4, 0); // VGA",
  "elJuego->marcador->imprimirCaracter(0x20, 216, 164, 2, 3);")

# ---- input: original VIGASOCO losControles semantics ----
p("Guillermo.cpp", """		if (sys->pad.left){
			gira(1);
			sys->pad.left = false;""", """		if (ql_key_down(QK_LEFT)){
			gira(1);""")
p("Guillermo.cpp", """		} else if (sys->pad.right){
			gira(-1);
			sys->pad.right = false;""", """		} else if (ql_key_down(QK_RIGHT)){
			gira(-1);""")
p("Guillermo.cpp", "} else if (sys->pad.up){", "} else if (ql_key_down(QK_UP)){")
p("Adso.cpp", "if (sys->pad.up){", "if (ql_key_down(QK_UP)){")
p("Adso.cpp", "if (sys->pad.down){", "if (ql_key_down(QK_DOWN)){")
p("Adso.cpp", "if (sys->pad.button3){", "if (ql_key_down(QK_S)){")
p("Adso.cpp", "if (sys->pad.button4){", "if (ql_key_down(QK_N)){")
p("Malaquias.cpp", "if (sys->pad.up){", "if (!ql_key_down(QK_UP)){")
p("Logica.cpp", "if (sys->pad.up || sys->pad.left || sys->pad.right){",
  "if (ql_key_down(QK_UP) || ql_key_down(QK_LEFT) || ql_key_down(QK_RIGHT)){")
p("Logica.cpp", "if (sys->pad.button1){", "if (ql_key_down(QK_SPACE)){")
p("Logica.cpp", "if (sys->pad.button1 || sys->pad.button2){", "if (!ql_key_down(QK_Q) || !ql_key_down(QK_R)){")

# ---- deterministic rand ----
p("Logica.cpp", "srand(1);", "ql_srand(1);")
p("Logica.cpp", "numeroRomano = rand() & 0x03;", "numeroRomano = ql_rand() & 0x03;")


def main():
    files = {}
    for f, old, new, count in P:
        if f not in files:
            files[f] = io.open(os.path.join(D, f), encoding="utf-8").read()
        s = files[f]
        c = s.count(old)
        if c != count:
            print("PATCH FAILED (%d matches, want %d) in %s:\n%s" % (c, count, f, old))
            return 1
        files[f] = s.replace(old, new)
    for f, s in files.items():
        for f2, old, new, count in P:
            if f2 == f:
                assert new in s, (f, new)
        with io.open(os.path.join(D, f), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(s)
    print("applied %d patches to %d files" % (len(P), len(files)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
