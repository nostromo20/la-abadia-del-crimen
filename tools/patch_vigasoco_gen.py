#!/usr/bin/env python3
"""One-shot: GeneradorPantallas / MotorGrafico / MezcladorSprites CPC + QL adaptation.
VGA code is kept under #if 0; every anchor must match exactly once."""
import io, os, sys

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cpp", "vigasoco")


class F:
    def __init__(self, name):
        self.name = name
        self.s = io.open(os.path.join(D, name), encoding="utf-8").read()

    def once(self, old, new):
        c = self.s.count(old)
        assert c == 1, (self.name, c, old[:70])
        self.s = self.s.replace(old, new)

    def wrap_if0(self, start, end, tag="VGA (fork)"):
        assert self.s.count(start) == 1, (self.name, start[:60])
        i = self.s.index(start)
        j = self.s.index(end, i)
        self.s = self.s[:i] + "#if 0 // " + tag + "\n" + self.s[i:j] + "\n#endif\n" + self.s[j:]

    def save(self):
        with io.open(os.path.join(D, self.name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.s)


# ---------------- GeneradorPantallas ----------------
g = F("GeneradorPantallas.cpp")
if "ql_play_tile" not in g.s:
    g.once('#include <SDL2/SDL.h>\n#include "system.h"\n', '// QL: SDL and system.h not needed\n')
    g.once('#include "IDrawPlugin.h"\n', '')
    g.wrap_if0("void GeneradorPantallas::Parchea(UINT8 numPantalla)",
               "\n/////////////////////////////////////////////////////////////////////////////\n// m",
               "VGA (fork): tile patches for the VGA graphics set")
    g.once("\tif (tile==57) tile=201;\n\tif (tile==58) tile=225;\n",
           "#if 0 // VGA (fork)\n\tif (tile==57) tile=201;\n\tif (tile==58) tile=225;\n")
    g.once("\tif (tile==105) tile=237;\n", "\tif (tile==105) tile=237;\n#endif\n")
    old_draw = ("\t// Draw all the tiles from the current scene.\n"
                "\tfor (int m=0;m<20;m++){\n"
                "\t\tfor (int n=0;n<16;n++){\n"
                "\t\t\t// Layers in the current scene.\n"
                "\t\t\tfor (int k = 0; k < nivelesProfTiles; k++){\t\t\t\t\n"
                "\t\t\t\tdibujaTile(32+n*16, m*8,bufferTiles[m][n].tile[k]);\n"
                "\t\t\t}\n\t\t}\n\t}\n")
    g.once(old_draw,
           "\t// QL: draws every cell (the CPC goes from the centre outwards in strips; the cells do\n"
           "\t// not overlap, so the result is the same). Tile 0 is not drawn, as on the CPC.\n"
           "\tfor (int m=0;m<20;m++){\n"
           "\t\tfor (int n=0;n<16;n++){\n"
           "\t\t\tfor (int k = 0; k < nivelesProfTiles; k++){\n"
           "\t\t\t\tint tile = bufferTiles[m][n].tile[k];\n"
           "\t\t\t\tif (tile != 0){\n"
           "\t\t\t\t\tdibujaTile(32+n*16, m*8, tile);\n"
           "\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n")
    a = "\tUINT8 *tileData =  &roms[0x24000-1 - 0x4000 + 0x1400 + num*8*16];"
    assert g.s.count(a) == 1
    i = g.s.index(a)
    j = g.s.index("\n}\n", i)
    g.s = (g.s[:i] + "\t// QL: the platform draws the 16x8 tile (CPC tile graphics, AND/OR masks by bit 7)\n"
           "\tql_play_tile(x, y, num);\n#if 0 // VGA (fork)\n" + g.s[i:j] + "\n#endif" + g.s[j:])
    g.save()

h = F("GeneradorPantallas.h")
if "QL: 2 = the CPC" not in h.s:
    h.once("static const int nivelesProfTiles = 4;",
           "static const int nivelesProfTiles = 2; // QL: 2 = the CPC original (the fork used 4)")
    h.once("#include <iostream>\n", "")
    h.save()

# ---------------- MotorGrafico ----------------
m = F("MotorGrafico.cpp")
if "QL: CPC inks" not in m.s:
    m.once("\t\tint colorFondo = (pantallaIluminada) ? 12 : 0; // VGA ",
           "\t\t// QL: CPC inks (0 = paper, 3 = black)\n\t\tint colorFondo = (pantallaIluminada) ? 0 : 3;")
    m.once("\t\tif (elJuego->GraficosCPC==false)\n", "\t\tif (false) // QL: the VGA tile patches are not used\n")
    m.once("\t\t\tgenPant->Parchea(numPantalla);", "\t\t\t; // genPant->Parchea(numPantalla) (VGA only)")
    m.save()

# ---------------- MezcladorSprites ----------------
x = F("MezcladorSprites.cpp")
if "QL (CPC)" not in x.s:
    # CPC: only non-zero tiles are combined
    x.once("\t\t\t\t\t//CPC\n\t\t\t\t\t//if (ti->tile[k] != 0){\n",
           "\t\t\t\t\t// QL (CPC): tile 0 is never drawn\n\t\t\t\t\tif (ti->tile[k] != 0){\n")
    x.once("\t\t\t\t\tif (ultimaPasada){\n\t\t\t\t\t\t// limpia la marca de dibujado\n",
           "\t\t\t\t\t}\n\n\t\t\t\t\tif (ultimaPasada){\n\t\t\t\t\t\t// limpia la marca de dibujado\n")
    # combinaTile: CPC body
    a = "\t// halla el desplazamiento del tile (cada tile ocupa 32 bytes)\n\tUINT8 *tileData = &roms[0x8300 + tile*32];"
    assert x.s.count(a) == 1
    i = x.s.index(a)
    j = x.s.index("\n}\n", i)
    cpc = (
        "\t// QL (CPC): restored from the CPC routine at 0x4e49. Tiles < 0x0b are copied as they are;\n"
        "\t// the others go through the AND/OR tables chosen by bit 7 of the tile number, which on the\n"
        "\t// CPC make ink 1 transparent for tiles 0x00-0x7f and ink 2 for tiles 0x80-0xff (the fork's\n"
        "\t// generaMascaras() has the two ink bits swapped, so it is not used here).\n"
        "\tUINT8 *tileData = &roms[0x8300 + tile*32];\n"
        "\tUINT8 *dest = &bufferMezclas[despBufSprites];\n"
        "\tint despSgteLinea = spr->anchoFinal*4 - 16;\n"
        "\tint transparente = (tile < 0x0b) ? -1 : ((tile & 0x80) ? 2 : 1);\n"
        "\n"
        "\tfor (int j = 0; j < 8; j++){\n"
        "\t\tfor (int i = 0; i < 4; i++){\n"
        "\t\t\tint data = *tileData++;\n"
        "\t\t\tfor (int k = 0; k < 4; k++){\n"
        "\t\t\t\tint color = cpc6128->unpackPixelMode1(data, k);\n"
        "\t\t\t\tif (color != transparente){\n"
        "\t\t\t\t\t*dest = color;\n"
        "\t\t\t\t}\n"
        "\t\t\t\tdest++;\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t\tdest += despSgteLinea;\n"
        "\t}\n"
        "#if 0 // VGA (fork)\n")
    x.s = x.s[:i] + cpc + x.s[i:j] + "\n#endif" + x.s[j:]
    # vuelcaBufferAPantalla: hand the visible rectangle to the platform
    old = ("\t// dibuja la parte visible del sprite\n"
           "\tfor (int j = 0; j < alto; j++){\n"
           "\t\tfor (int i = 0; i < ancho*4; i++){\n"
           "\t\t\t// CPC cpc6128->setMode1Pixel(posX + i, posY + j, *src);\n"
           "\t\t\tcpc6128->setVGAPixel(posX + i, posY + j, *src);\n"
           "\t\t\tsrc++;\n"
           "\t\t}\n\n"
           "\t\t// salta los pixels recortados en x\n"
           "\t\tsrc += distXSgteLinea;\n"
           "\t}\n")
    x.once(old, "\t// QL: the platform copies the visible part to the play area\n"
                "\tql_play_blit(posX, posY, ancho*4, alto, src, ancho*4 + distXSgteLinea);\n")
    x.save()

print("ok")
