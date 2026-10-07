#!/usr/bin/env python3
"""One-shot: Marcador + GestorFrases back to the CPC drawing paths; phrase table cut to
Spanish + English (the other six languages stay in the file under #if 0); std::string
removed. Every anchor must match exactly once."""
import io, os, re, sys

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cpp", "vigasoco")


class F:
    def __init__(self, name):
        self.name = name
        self.s = io.open(os.path.join(D, name), encoding="utf-8").read()

    def once(self, old, new):
        c = self.s.count(old)
        assert c == 1, (self.name, c, old[:70])
        self.s = self.s.replace(old, new)

    def save(self):
        with io.open(os.path.join(D, self.name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.s)


def c_escape(txt):
    out = []
    for ch in txt:
        o = ord(ch)
        if o < 128:
            out.append(ch)
        elif o < 256:
            out.append("\\%03o" % o)          # octal: never swallows a following letter
        else:
            raise ValueError("non-Latin-1 char %r" % ch)
    return "".join(out)


# ---------------- Marcador ----------------
m = F("Marcador.cpp")
if "QL (CPC)" not in m.s:
    m.once('//para printf trazas\n#include <stdio.h>\n', '')
    # roman digit of the day: CPC body
    i = m.s.index("\t/* CPC\n\t// apunta a 8 pixels negros")
    j = m.s.index("\n}\n", i)
    body = m.s[i:j]
    k = body.index("\t*/\n\t// VGA")
    cpc = body[len("\t/* CPC\n"):k]
    vga = body[k + len("\t*/\n"):]
    m.s = m.s[:i] + "\t// QL (CPC)\n" + cpc + "#if 0 // VGA (fork)\n" + vga + "\n#endif" + m.s[j:]
    m.once("\t\t\t\t// VGA\n\t\t\t\tcpc6128->setVGAPixel(44 + i - 8, 180 + j, cpc6128->getMode1Pixel(44 + i, 180 + j));",
           "\t\t\t\tcpc6128->setMode1Pixel(44 + i - 8, 180 + j, cpc6128->getMode1Pixel(44 + i, 180 + j));")
    m.once("\t\timprimirCaracter(caracter, 84, 180, 0, 4); // VGA", "\t\timprimirCaracter(caracter, 84, 180, 3, 2);")
    m.once("\tdibujaBarra(laLogica->obsequium, 6, 240, 177); // VGA", "\tdibujaBarra(laLogica->obsequium, 2, 240, 177);")
    m.once("\tdibujaBarra(31 - laLogica->obsequium + 1, 0, 240 + laLogica->obsequium, 177); // VGA",
           "\tdibujaBarra(31 - laLogica->obsequium + 1, 3, 240 + laLogica->obsequium, 177);")
    m.once("\tcpc6128->fillMode1Rect(0, 160, 320, 40, 0); // VGA", "\tcpc6128->fillMode1Rect(0, 160, 320, 40, 3);")
    m.once("\tcpc6128->fillMode1Rect(96, 164, 128, 8, 0); // VGA ", "\tcpc6128->fillMode1Rect(96, 164, 128, 8, 3);")
    # panel graphic: CPC
    i = m.s.index("\t/* CPC\n\t// apunta a los datos gr")
    j = m.s.index("\n}\n", i)
    body = m.s[i:j]
    k = body.index("\t*/\n\t// VGA")
    cpc = body[len("\t/* CPC\n"):k]
    vga = body[k + len("\t*/\n"):]
    m.s = m.s[:i] + "\t// QL (CPC)\n" + cpc + "#if 0 // VGA (fork)\n" + vga + "\n#endif" + m.s[j:]
    # objects in the panel: CPC
    m.once("\t\t\t\t// CPC UINT8 *data = &roms[spr->despGfx];\n\t\t\t\t// VGA\n\t\t\t\tUINT8 *data = &roms[spr->despGfx + 0x24000 - 1 - 0x4000];",
           "\t\t\t\tUINT8 *data = &roms[spr->despGfx];")
    i = m.s.index("\t\t\t\t\t// CPC for (int i = 0; i < spr->ancho; i++){")
    j = m.s.index("\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t} else {", i)
    m.s = (m.s[:i] +
           "\t\t\t\t\tfor (int i = 0; i < spr->ancho; i++){\n"
           "\t\t\t\t\t\tfor (int k = 0; k < 4; k++){\n"
           "\t\t\t\t\t\t\tcpc6128->setMode1Pixel(posX + 4*i + k, posY + j, cpc6128->unpackPixelMode1(*data, k));\n"
           "\t\t\t\t\t\t}\n"
           "\t\t\t\t\t\tdata++;\n" + m.s[j:])
    # imprimeFrase / imprimirCaracter: CPC 8x8 font, Spanish+English characters only
    i = m.s.index("void Marcador::imprimeFrase(std::string frase")
    m.s = m.s[:i] + (
        "void Marcador::imprimeFrase(const char *frase, int x, int y, int colorTexto, int colorFondo)\n"
        "{\n"
        "\tfor (int i = 0; frase[i] != 0; i++){\n"
        "\t\timprimirCaracter((UINT8)frase[i], x + 8*i, y, colorTexto, colorFondo);\n"
        "\t}\n"
        "}\n\n"
        "// QL (CPC): 8x8 glyphs of the CPC font at 0xb400 (from '-' = 0x2d to 'Z'). As in the fork,\n"
        "// ',' and '.' use the glyphs in the '<' and '=' slots, the inverted question mark (0xbf)\n"
        "// the '@' slot and N-tilde (0xd1) the 'W' slot; a real W (needed by the English phrases)\n"
        "// comes from the fork's extra glyph. The fork's 8x10 accented capitals are not kept.\n"
        "void Marcador::imprimirCaracter(int caracter, int x, int y, int colorTexto, int colorFondo)\n"
        "{\n"
        "\tstatic const UINT8 glifoW[8] = { 0x00,0x66,0xe6,0xc6,0xd6,0xd6,0xfe,0x66 };\n"
        "\n"
        "\tconst UINT8 *data = &roms[0x38e7];\t// blank\n"
        "\tcaracter &= 0xff;\n"
        "\n"
        "\tswitch (caracter){\n"
        "\t\tcase ',': caracter = 0x3c; break;\n"
        "\t\tcase '.': caracter = 0x3d; break;\n"
        "\t\tcase 0xbf: caracter = 0x40; break;\n"
        "\t\tcase 0xd1: caracter = 0x57; break;\n"
        "\t\tcase 'W': caracter = 0x100; break;\n"
        "\t}\n"
        "\n"
        "\tif (caracter == 0x100){\n"
        "\t\tdata = glifoW;\n"
        "\t} else {\n"
        "\t\tcaracter &= 0x7f;\n"
        "\n"
        "\t\t// non printable\n"
        "\t\tif ((caracter != 0x20) && (caracter < 0x2d)) return;\n"
        "\n"
        "\t\tif (caracter != 0x20){\n"
        "\t\t\tdata = &roms[0xb400 + 8*(caracter - 0x2d)];\n"
        "\t\t}\n"
        "\t}\n"
        "\n"
        "\tfor (int j = 0; j < 8; j++){\n"
        "\t\tint bit = 0x80;\n"
        "\t\tint valor = *data;\n"
        "\n"
        "\t\tfor (int i = 0; i < 8; i++){\n"
        "\t\t\tcpc6128->setMode1Pixel(x + i, y + j, (valor & bit) ? colorTexto : colorFondo);\n"
        "\t\t\tbit = bit >> 1;\n"
        "\t\t}\n"
        "\t\tdata++;\n"
        "\t}\n"
        "}\n\n"
        "#if 0 // fork version (std::string, 8x10 accented glyphs, VGA colours)\n" + m.s[i:] + "\n#endif\n")
    # the chapuza line drew over the panel for the VGA 8x10 font: it lives in the VGA block now
    m.save()

h = F("Marcador.h")
if "const char *frase" not in h.s:
    h.once("#include <string>\n", "")
    h.once("\tvoid imprimeFrase(std::string frase, int x, int y, int colorTexto, int colorFondo);",
           "\tvoid imprimeFrase(const char *frase, int x, int y, int colorTexto, int colorFondo);")
    h.save()

# ---------------- GestorFrases ----------------
g = F("GestorFrases.cpp")
if "QL_NUM_IDIOMAS" not in g.s:
    start = g.s.index("\tconst char * GestorFrases::frases[8][0x38+1] = {")
    end = g.s.index("};\n", g.s.index("}, // Fin textos 7 Portugues")) + 3
    table = g.s[start:end]
    # languages 0 and 1
    a = table.index("{ // 0 Castellano")
    b = table.index("}, // Fin textos 1 ingles") + len("}, // Fin textos 1 ingles")
    two = table[a:b]
    two = "".join(c_escape(ch) if ord(ch) >= 128 and ch not in "" else ch for ch in two)
    # comments may contain accents: escaping them inside // comments is harmless
    new = ("\t// QL: Spanish (0) and English (1) only; non-ASCII as octal escapes (CPC font codes:\n"
           "\t// 0xd1 = N-tilde, 0xbf = inverted question mark). The fork's eight-language table\n"
           "\t// follows under #if 0.\n"
           "\tconst char * GestorFrases::frases[QL_NUM_IDIOMAS][0x38+1] = {\n\t\t" + two + "\n};\n\n"
           "#if 0 // fork: 8 languages\n" + table + "#endif\n")
    g.s = g.s[:start] + new + g.s[end:]
    g.once("\tfrasePergamino = frases[0][0]; // 0 castellano",
           "\tstrncpy(frasePergamino, frases[0][0], sizeof(frasePergamino) - 1); // 0 castellano\n"
           "\tfrasePergamino[sizeof(frasePergamino) - 1] = 0;")
    g.once("\t\tfrase = (char *)frasePergamino.c_str();", "\t\tfrase = frasePergamino;")
    g.once("    int caracter = *frase;", "    int caracter = (UINT8)*frase;")
    g.once("\tfor (int j = -2; j < 8; j++){", "\tfor (int j = 0; j < 8; j++){\t// QL (CPC): 8 lines")
    g.once('#include "Marcador.h"\n', '#include "Marcador.h"\n#include <string.h>\n')
    g.save()

h = F("GestorFrases.h")
if "QL_NUM_IDIOMAS" not in h.s:
    h.once("#include <string>\n", "#define QL_NUM_IDIOMAS 2\n")
    h.once("\tstd::string frasePergamino;", "\tchar frasePergamino[96];")
    h.once("\tstatic const char *frases[8][0x38+1];", "\tstatic const char *frases[QL_NUM_IDIOMAS][0x38+1];")
    h.save()

print("ok")
