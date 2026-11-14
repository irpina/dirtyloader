# The song in RAM, transport and the sequencer (static, M8 6.6.2A Model02)

The data every mod touches: where the song lives, how code reaches each part of it, how playback is driven.
Addresses are run-time unless marked "load".

## The song object — OCRAM `0x2025A570`

The whole song is one 109 KB object in OCRAM at **`0x2025A570`** — the most-shared constant in the firmware
(413 literal uses). Its layout is the `.m8s` file image: **RAM offset = file offset − `0x82`**. The file layout
comes from the community parser (`m8-file-parser`, firmware 4.0–6.x) and is confirmed by the firmware's own
accessors:

| section | RAM | song + | file offset | shape | accessor (load) |
|---|---|---|---|---|---|
| header (tempo, quantize, name, MIDI settings, key, mixer settings) | `0x2025A570` | `0x0000` | `0x0082` | | `0x600A6118` (`song + 0x0C + n`) |
| grooves | `0x2025A5DC` | `0x006C` | `0x00EE` | 32 × 16 | |
| song rows | `0x2025A7DC` | `0x026C` | `0x02EE` | 256 rows × 8 tracks (chain numbers) | |
| **phrases** | `0x2025AFDC` | `0x0A6C` | `0x0AEE` | 255 × 16 steps × 9 B: note, vel, instr, 3 × (cmd, val) | `0x600A6142(song, p, step, field)` |
| chains | `0x20263F4C` | `0x99DC` | `0x9A5E` | 255 × 16 × 2 B: phrase, transpose | `0x600A6130(song, c, step, field)` |
| tables | `0x20265F2C` | `0xB9BC` | `0xBA3E` | 256 × 16 × 8 B: transpose, vel, 3 × (cmd, val) | |
| **instruments** | `0x2026DF2C` | `0x139BC` | `0x13A3E` | 128 × **215 B** (`0xD7`, returned by `0x600A6214`) | `0x600A617E(song, i, byte)` |
| effects settings | `0x20274AAC` | `0x1A53C` | `0x1A5BE` | MODFX / delay / reverb (field table in [FIRMWARE-MAP.md](../FIRMWARE-MAP.md) §9) | `0x600A6124(song, field)` |
| MIDI mappings | `0x20274AEC` | `0x1A57C` | `0x1A5FE` | 128 | |
| scales | `0x20274F6C` | `0x1A9FC` | `0x1AA7E` | 16 | |
| EQs | `0x2027524C` | `0x1ACDC` | `0x1AD5E` | 128 × 18 B (3 bands × 6 B) | `0x600A6190(song, n, band, field)` |

Confirmation beyond the accessors: row fire (`0x24DE0`) reads a phrase step as `phrase + step*9` and the three FX
columns at `+3/+4`, `+5/+6`, `+7/+8`; the instrument parameter interface reads values as `data[index]` with the
modulators at `data[0x30..0x47]` ([static-m8-params.md](static-m8-params.md)).

**Instrument record (215 B):** byte `index` of a parameter = its descriptor's index (engine parameters from 0,
the four 6-byte modulator slots at `0x30`). The engine type selects which singleton interprets it.

File I/O: the `M8VERSION`-headed loaders/savers per file type sit at `0x6007D300..0x6007F978` (song, instrument
`.m8i`, scale `.m8n`, theme `.m8t`, settings, bundles); `0x6007D68C` is the song-version check
(`SONG WAS CREATED IN A NEWER VERSION`). SdFat file reads: exFAT `0x600AA764`, FAT `0x600A8D68`.

## Transport — the sequencer clock object `0x2000D218`

The clock is an `AudioStream` node (`update()` = ITCM `0x22720`) and the transport API is a handful of methods,
each bracketed by `AudioNoInterrupts()` (IRQ 70 lock):

| function (load) | role | field |
|---|---|---|
| `0x6009A6C0` | **`setTempo(bpm)`** | `+0x30` = bpm (float); `+0x40` = bpm × K (double increment) |
| `0x6009A528` | **`setPlaying(b)`** | `+0x29` = !b |
| `0x6009A55C` | **`stop()`** — clears running, resets the tracks | `+0x28` |
| `0x6009A47C` | phase nudge / external sync | `+0x38` (double phase) |
| `0x6009A51C` | **`getTicks()`** | `+0x2C` |

**Resolution:** K = `7.256235827664399e-05` = **192 / (60 × 44100)** exactly — the phase advances per sample at
44.1 kHz with **192 sub-ticks per beat** (8 × the 24 PPQN of 6-tick steps). `update()` steps 32 times per call,
which suggests **32-sample audio blocks** (~0.73 ms) — S3.

## Track players — `0x2000D270`, 8 × `0x2B0`

Eight 688-byte per-track sequencer objects follow the clock (`0x2000D270..0x2000E7F0`), initialised by
`0x6003BA2C`. Row fire (`0x24DE0`) runs on one of them: it sets the note / instrument / volume and applies the
row's three FX columns via `0x24854`; the per-tick slot scan (`0x28424`) runs the 78-case executor
([static-m8-fxcmd.md](static-m8-fxcmd.md)).

## Hooks this enables

- **Read or edit the song** from a mod: everything is at fixed offsets from `0x2025A570` (pin per firmware).
- **Transport events**: detour `setTempo` / `setPlaying` / `stop` (flash code — the plain `bl` Core detour works).
- **Per-tick / per-row**: inside ITCM (audio thread) — see the ITCM constraints in [../CORE.md](../CORE.md).
