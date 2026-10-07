# Loading-screen candidates (QL Mode 8)

These are candidates only. Nothing here is wired into the game or the loader yet.
To regenerate everything, run `python tools/loadscreen.py`. Each run also checks every `_scr`
with an independent decoder against its preview, pixel for pixel, and asserts that no FLASH
bits are set.

## Sources

| file | what it is |
|---|---|
| `src_cpc.png` | **CPC title, `data/ABADIA0.BIN`**. This is the 0xC000–0xFFFF screen dump; it is identical to `build/roms.bin` 0x0000. **MODE 0** (160×200, 16 pens): `pista0.asm` 0x0108 writes gate-array 0x8C, which selects mode 0. **Palette** from `pista0.asm` 0x010D (call 0x0182 with 17 inline hardware-colour bytes: border, then pens 15..0): pen0 pink, 1 black, 2 white, 3 pastel yellow, 4 dark cyan, 5 red, 6 dark blue, 7 blue, 8 magenta, 9 purple, 10 orange, 11 mauve, 12 grey, 13 dark red, 14 pastel blue, 15 pastel cyan. The border is black. |
| `src_dos.png` | **DOS `ABADIA.PIC`**. CGA 320×200×4, with even/odd banks at 0 and 0x2000. `ABADIA.EXE` copies it raw to B800:0 after INT 10h mode 4, then INT 10h AX=0B00h with BX=[0x67B]. BX is 0100h for F1 "MONITOR COLOR", which gives **palette 0, high intensity** (black, light green, light red, yellow), and 0000h for F2 "MONITOR MONOCROMO" (palette 1, cyan/magenta/white). |
| `src_zx.png` | **Spectrum**: `Abadia_Intro_English_snap0.z80`, RAM bank 5 (page 8). This is the SCREEN$ of the **2002 English Spectrum conversion** ("The abbey of crime"). It is *different artwork* from the CPC/DOS title. No FLASH is used; BRIGHT is used on about 21k pixels. The Spanish `abadiadelcrimen_snap0` and the Part1–4 snapshots hold gameplay or blank screens. |

## Candidates

The picture sits at lines 28–227 (layout A); the Spectrum picture sits at lines 32–223.

| id | mode | description | pros / cons |
|---|---|---|---|
| A1 | 8 | CPC 160→256, area-average, nearest colour | + no dither noise; − the 50% CPC tones all round up, so the robe turns bright cyan and the skin turns white: garish |
| A2 | 8 | CPC 160→256, area-average, 4×4 Bayer | + faithful tones, stable pattern; − the title outlines break up at the scaled pixel boundaries |
| A3 | 8 | CPC 160→256, area-average, Floyd–Steinberg | + the best tonal fidelity; − noisy "worms" on the 2:1-wide Mode 8 pixels, and the lettering is fuzzy |
| **A4** | 8 | CPC 160→256 best-fit, **hand-tuned pen → colour or 50% checker** | + every pen keeps one consistent look (skin = red/white, robe = cyan/black, dark red = red/black); clean lettering; − the 1.6× column widths are uneven (2,2,1,2,1…), and the grey "soft" is faint |
| A5 | 8 | CPC 160→256 best-fit, hand-tuned solid colours only | + crispest, no dither; − with only 8 pure colours it looks garish (magenta skin and title fill) |
| A6 | 8 | A4, but thin strokes forced to solid colours | + the "OPERA soft" logo reads better; − the title gets harsh vertical stripes |
| B1 | 8 | CPC with doubled pixels (320 wide), centre-cropped to 256, with A4's mapping | + uniform 2-px columns, so nothing is resampled; − it cuts 16 CPC px (32 QL px) per side: the left steps of the chair, "OPE" of the OPERA logo, the final "n" of "crimen" and most of the book on the right |
| C1 | 8 | DOS 320→256 best-fit columns | + CGA palette 0 maps **exactly** to QL black/green/red/yellow, with no colour loss; − it drops every 5th column, and the CGA art is a weaker, 4-colour version |
| C2 | 8 | DOS 320→256 area-average + Bayer, within the same 4 colours | + smoother diagonals; − some dither fuzz on the lettering |
| D1 | 8 | Spectrum SCREEN$ at 1:1, ZX colour n → QL colour n | + a perfect 1:1 fit (same width, same 8-colour order; only BRIGHT is lost); − it is the 2002 English remake art, not the original title |
| M4 | **4** | Mode 4 comparison: CPC 160→512, blue folded into R and G, Floyd–Steinberg | for comparison only: twice the horizontal resolution, but only black/red/green/white, so the skin and robe go green and red |

**Recommendation: A4.** It is the closest to the CPC original that the 8 QL colours allow, and
its lettering stays legible. If the author prefers zero dithering, use C1 (the DOS art at exact
colours). D1 is the cleanest technical fit, but it is a different picture.

## Files and viewing

- `<id>_scr` is a 32,768-byte raw screen. Load it with `LBYTES ...,131072` after `MODE 8`, or after
  `MODE 4` for M4.
- `<id>_preview.png` is 1024×512: 2× of the 512×256 display, with each Mode 8 pixel 4×2.
- `loadscreen_sheet.png` shows every source and candidate, labelled.
- `view_bas`: copy it and the `*_scr` files to `win1_`, then `LRUN win1_view_bas`. Each key shows
  the next screen. If the files live elsewhere, edit `dev$` on line 110 (e.g.
  `"win1_loadscreen_"`).

## Stretched set (`<id>S`): whole screen, no border

The same candidates, stretched to fill the full 256×256 Mode 8 screen (M4S fills 512×256 in
Mode 4). The centred originals above are unchanged.

- CPC 160×200 becomes 256×256 (×1.6 wide, ×1.28 tall).
- DOS 320×200 becomes 256×256.
- Spectrum 256×192 becomes 256×256 (×1.333 tall, 1:1 across).

| id | vertical method |
|---|---|
| A1S, A2S, A3S | Area-average on both axes, then the same colour step (nearest / Bayer / Floyd–Steinberg) |
| A4S, A5S, A6S | Best-fit rows and columns on the pen indices; 56 of every 200 rows are doubled, evenly spread. Then the same pen→colour/checker map. The checker phase follows the screen pixels, so doubled rows never double the checker |
| B1S | The same 2×-wide centre crop, with rows best-fit from 200 to 256 |
| C1S | Best-fit rows and columns, exact CGA→QL colours |
| C2S | Area-average on both axes, then Bayer within the 4 CGA colours |
| D1S | Best-fit rows: every 3rd Spectrum row is doubled |
| M4S | Area-average to 512×256, then Floyd–Steinberg (Mode 4) |

- **Gains from the stretch:** A4S, A6S, C1S and C2S. The taller lettering reads better and the
  picture fills the screen. The checker patterns are unaffected.
- **Hurt by the stretch:** D1S. The Spectrum's 8-px font gets uneven row heights (2,1,1) in its
  tiny credit text; it is still legible, but lumpy. A1S/A5S stay garish. Everything is about 28%
  taller than the source art, so faces look elongated.
- **Recommendation: A4S if you want the full screen**; otherwise keep A4.

Files:
- `<id>S_scr` and `<id>S_preview.png` for each candidate;
- `loadscreen_sheet_stretch.png`: the stretched set;
- `compare_sheet.png`: each original next to its stretched version;
- `view_stretch_bas`: `LRUN win1_view_stretch_bas`.
