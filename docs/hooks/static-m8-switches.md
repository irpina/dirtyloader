# Switch census (M8 6.6.2A Model02)

Every PC-relative table branch in the image — the firmware's dispatch skeleton. Regenerate for any build:

```
python -m dirtyloader.re.switches <stock.bin> -o switches.txt [--min N]
```

`tbb [pc,Rm]` / `tbh [pc,Rm,lsl #1]` have fixed encodings (`E8DF F00m` / `E8DF F01m`), so the census is a byte
scan and does not depend on Ghidra's auto-analysis (which misses most of the M8's computed-call code). The bound
comes from the preceding `cmp Rm,#N` + `bhi`, the **bias** from a `sub Rm,Rx,#B`, and the jump table is decoded
into case targets. 6.6.2A has **140 switches**, all with recovered bounds.

Matching the case count and bias to a known enum identifies a switch without strings: `78` cases = the 78 FX
commands, bias `0x20` + 91 cases = printable ASCII, bias `0xC8` = key codes.

## Identified switches

| switch | function | cases | bias | what | conf | doc |
|---|---|---|---|---|---|---|
| 0x60028802 | 0x600287A4 | 78 | — | **FX-command executor** (row fire), cmds 0x00..0x4D | S1 | [fxcmd](static-m8-fxcmd.md) |
| 0x6005EE1E | 0x6005ED6C | 78 | — | FX-command value formatter (UI) | S1 | [SITES](SITES.md) |
| 0x60025F48 | 0x60025ED4 | 72 | — | second FX processor, cmds 0x00..0x47; RND/REP re-dispatch the stored slot cmd; per-slot state at track+0x1A4.. — likely per-tick/continuous | S3 | [fxcmd](static-m8-fxcmd.md) |
| 0x60029C08 | 0x60029BDC | 4 | 0x0C | **pitch commands** PSL/PBN/PVB/PVX (0x0C..0x0F) — *not* a sibling executor | S2 | [fxcmd](static-m8-fxcmd.md) |
| 0x6004C192 | 0x6004C13C | 30 | — | **`set_view`**: view id → view singleton | S1 | [ui](static-m8-ui.md) |
| 0x6004C29C | 0x6004C13C | 25 | — | `set_view`: view id → navigation group | S2 | [ui](static-m8-ui.md) |
| 19 × `(this, action)` | see ui doc | 21–49 | — | **per-view input handlers**, all at vtable slot `+0x08` | S1 | [ui](static-m8-ui.md) |
| 0x6002E36E | 0x6002E2A8 | 91 | 0x20 | glyph renderer (ASCII 0x20..0x7A) | S2 | [ui](static-m8-ui.md) |
| 0x6002FEE0 | 0x6002FDEC | 91 | 0x20 | second glyph renderer (second font) | S2 | [ui](static-m8-ui.md) |
| 0x60078608 | 0x600785C0 | 23 | 0x62 | value formatter: format codes `'b'..'x'` | S2 | [ui](static-m8-ui.md) |
| 0x6002F066 | (0x6002F0xx) | 38 | 0x41 | `'A'..'f'` — hex digit / letter handling | S3 | |
| 0x600A5C8E | 0x600A5C60 | 12 | 0x0D | pin/peripheral setup (cases are pin numbers 13/19/20/24; 23 MMIO refs, IOMUXC pad `0x30B0`, NVIC enable) — a PWM/timer output | S3 | |
| 0x60050B3A | (after 0x60050AB8) | 25 | 0xC8 | key codes 0xC8..0xE0 | S3 | |
| 0x60050B02 | (after 0x60050AB8) | 29 | 0x03 | same function, codes 3..0x1F | S3 | |
| 0x60099366 | 0x600992B8 | 91 | — | switch on a byte field (`[r6,#0xF]`), 0..0x5A | S3 | |
| 0x60083BF0 | 0x60083BAE | 63 | 0x1E | 0x1E..0x5C; the function calls an object's `+0x88` | S3 | |

## Unidentified, large (≥ 20 cases)

`0x6003FC5C` (26, bias 3), `0x6004B98C` (27, in the display-driver region), `0x600577AA` / `0x6006F350` (48,
bias 1), `0x600842E4` (49) + `0x60084362` (30) in `0x6008428E`, `0x60084F06` / `0x60086634` (23, bias 0x46).

The rest (~100) are small (3–18 cases) and mostly local logic.

## Notably absent

No switch is biased by `0x1C` / bounded at 37 cases, so the 37 mixer/send FX commands (`0x1C..0x40`, which the
executor sends to its default) are **not** dispatched by a second switch — most likely data-indexed (command
id → mixer slot by arithmetic), or handled per tick by `0x60025ED4`.
