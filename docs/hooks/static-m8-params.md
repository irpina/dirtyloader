# Parameter descriptor tables (static, M8 6.6.2A Model02)

Primitive 2 of the catalog ("parameter descriptor table") and the key to primitive 5 (LFO destinations). These
tables were long filed as "blocked behind computed indirection"; the real reason they looked unreachable is
that their **strings live in `.data` (DTCM)** and are referenced only by run-time `0x2000xxxx` addresses
([../FIRMWARE-MAP.md](../FIRMWARE-MAP.md) §1). Translated, they are plain data. List them with:

```
python -m dirtyloader.re.params <stock.bin> [--names]
```

## Record layout (28 bytes, in flash)

| offset | field | example: SEND DELAY (WAVSYNTH) |
|---|---|---|
| `+0x00` | id (u32; `0xFF` for modulator fields) | `0x0F` |
| `+0x04` | long name → DTCM | `"DELAY VOL"` |
| `+0x08` | 4-char UI label → DTCM | `"DEL "` |
| `+0x0C` | 3-char code → DTCM (also the FX/modulation short code) | `"SDL"` |
| `+0x10` | help text → DTCM | `"SEND DELAY"` |
| `+0x14` | flags (u32) | `0x00000001`; PAN `0x80000102` (relative), AMOUNT `0x80000102`/`0xFF000101` |
| `+0x18` | `min, max, field offset, ?` (u8 each) | `0x00, 0xFF, 0x0C, 0x00` — `0xFF` offset = not a stored field (e.g. ADD NOTE, CHORD) |

Re-labelling (`+0x04..+0x10`) and re-ranging (`+0x18` min/max) are pure data patches to flash. The string
pointers can be repointed at new strings in a cave as long as the new strings are reachable at run time (put
them in `.data`, or point at flash — the UI reads through the pointer either way; to be confirmed on hardware).

## The tables

| table | engine | params | notable |
|---|---|---|---|
| `0x600B5E68` | **modulators** | 47 | 6 types × (TYPE, **DEST**, AMOUNT, …): AHD (ATTACK/HOLD/DECAY), LFO (OSC/TRG/FREQ), DRUM (PEAK/BODY/DECAY), ADSR (ATTACK/DECAY/SUSTAIN/REL), TRIG (ATTACK/HOLD/DECAY), TRACKING (SOURCE/LOW/HIGH) |
| `0x601C2FBC` | WAVSYNTH | 19 | SHAPE, SIZE, MULT, WARP, SCAN |
| `0x600CBF60` | MACROSYNTH | 20 | SHAPE, TIMBRE, COLOR, DEGRADE, REDUX, TRIGGER/STRIKE |
| `0x600CDBCC` | SAMPLER (+ sample settings) | 34 | BPM, STEPS, PLAY MODE, SLICE, START/LOOP OFFSET, LENGTH, DEGRADE (three groups) |
| `0x600CC5AC` | MIDI OUT | 28 | CHANNEL, BANK, PG, PB, ADD NOTE, CHORD, CCA..CCJ NUM/VAL |
| `0x600BC478` | FMSYNTH | 48 | FM ALGORITHM, per-operator fields (labels in a second region), FM MOD1..4 |
| `0x600BD55C` | HYPERSYNTH | 30 | CHORD, 6 × chord note, KEY+SCALE, SWARM, WIDTH, SUBOSC, SHAPE |
| `0x600BB9E0` | EXTERNAL | 28 | INPUT, PORT, CHANNEL, BANK, PG, CCA..CCD |

## The modulator DEST field — the LFO mod's target

Every modulator slot has `MOD~ DEST` at **field offset `0x02`** (help text `"LFO DESTINATION"` for the LFO
type, `"ENV DESTINATION"` / `"TRACKING DESTINATION"` for the others) and `MOD~ AMOUNT` at `0x04`. The
descriptor's range is `0..255`; the selectable destinations are limited elsewhere, by each engine's
destination list (names at DTCM `0x200061F4` = flash `0x601E4214`, which now has 12 code references — the next
thing to follow, see [../MODULATION.md](../MODULATION.md)).

## The shared send block

Every sound-producing engine ends with the same parameters. Their stored field offsets:

| engine | CUTOFF | RES | AMP | PAN | DRY | MODFX | DELAY | REVERB |
|---|---|---|---|---|---|---|---|---|
| WAVSYNTH | 0x0B | 0x0D | 0x02 | 0x06 | 0x08 | 0x0A | 0x0C | 0x0E |
| MACROSYNTH | 0x0B | 0x0D | 0x02 | 0x06 | 0x08 | 0x0A | 0x0C | 0x0E |
| SAMPLER | 0x10 | 0x11 | 0x02 | 0x06 | 0x08 | 0x0A | 0x0C | 0x0E |
| FMSYNTH | 0x27 | 0x29 | 0x1E | 0x22 | 0x24 | 0x26 | 0x28 | 0x2A |
| HYPERSYNTH | 0x13 | 0x15 | 0x0A | 0x0E | 0x10 | 0x12 | 0x14 | 0x16 |
| EXTERNAL | 0x13 | 0x15 | 0x07 | 0x0D | 0x10 | 0x12 | 0x14 | 0x16 |

The sends step by 2 in every engine; the filter fields can coincide numerically with the sends (WAVSYNTH
CUTOFF `0x0B` vs MODFX `0x0A`), so the offset byte is probably relative to more than one sub-structure (filter
block vs. mixer block) or encodes a doubled index. Settle on hardware before writing a mod that depends on it.

**For the extended-LFO-destinations mod** this is enough to proceed: the sends are ordinary per-engine
parameters with descriptors, and the DEST field is a known byte; what remains is the destination list and the
apply step that maps a DEST value to one of these fields.
