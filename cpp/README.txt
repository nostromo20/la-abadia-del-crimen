cpp/ - compiled game logic for the QL hybrid build
==================================================

vigasoco/   VIGASOCO "La Abadia del Crimen" driver sources (Manuel Abadia), taken from the
            Samuel85/Abbey (VigasocoSDL) fork by tools/import_vigasoco.py and adapted for the QL.
            See ../CREDITS.txt for the licence.
port/       QL replacements and glue: Juego (no menus/VGA/SDL), cpc6128 (panel buffer, play area
            straight to the platform), system.h (input/sound hooks), Paleta (palette hook),
            ql_game.cpp (entry points + harness state block), ql_runtime.cpp (bump allocator,
            mem*/str*), ql_rand.c (glibc TYPE_3 rand), ql_port.h (the platform interface).
host/       the PC oracle (same C++ with a host platform; see tools/hdiff.py).

Build: ../build_hybrid.sh (QL image), build_oracle.sh (oracle, inside WSL).

Changes made to the fork's sources (all VGA code kept under "#if 0 // VGA (fork)")
---------------------------------------------------------------------------------
tools/patch_vigasoco_cpc.py, _blocks.py, _gen.py, _text.py, patch_fix_transp.py did these,
each asserting its anchors:

- CPC graphics addresses restored: monk faces, Guillermo/Adso animation tables, monk habit
  table, flip offset 0xc000 (Personaje, Puerta), object sprites (port/Juego.cpp).
- CPC drawing restored in Sprite::dibuja, SpriteMonje::dibuja, SpriteLuz (black = pen 3),
  Marcador (panel graphic at 0x1e328, roman day digits, CPC pens, 8x8 CPC font) and
  MezcladorSprites::combinaTile (CPC routine 0x4e49: tiles < 0x0b opaque, otherwise pen 2
  transparent for tiles 0x00-0x7f and pen 1 for 0x80-0xff; tile 0 never drawn).
- GeneradorPantallas: nivelesProfTiles = 2 (the CPC value; the fork used 4), the fork's VGA
  tile remaps and screen patches (Parchea) disabled, tiles drawn through ql_play_tile().
- MotorGrafico: background pens 0/3 as on the CPC, no VGA patching.
- Input: the fork replaced VIGASOCO's losControles queries with an SDL pad and changed some
  meanings (edge-triggered turning; Malaquias' "is Guillermo standing still" test inverted;
  the mirror's Q+R test inverted). The QL copy restores the original queries through
  ql_key_down(): cursor keys, SPACE (drop object), Q+R (mirror), S/N (Adso's question).
- GestorFrases: Spanish and English phrase tables only (the other six under #if 0), non-ASCII
  as octal escapes; frasePergamino is a char array; the phrase scroll is 8 lines (CPC).
- std::string, iostream, SDL removed from the compiled path; rand() -> ql_rand().

Known deviations from the CPC that come from VIGASOCO/the fork and are kept on purpose (the
oracle and the QL must run the same code): phrase characters advance every 2 logic steps
(the fork's choice), the end-of-investigation screen is reduced to a flag.
