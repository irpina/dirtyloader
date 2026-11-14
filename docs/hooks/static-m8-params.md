# Parameters, modulators and LFO destinations (static, M8 6.6.2A Model02)

Primitive 2 of the catalog (parameter descriptors) and primitive 5 (modulation destinations — the
extended-LFO-destinations mod). These were long filed as "blocked behind computed indirection"; the real
reasons were (1) the strings live in `.data` (DTCM) and are referenced only by run-time `0x2000xxxx`
addresses ([../FIRMWARE-MAP.md](../FIRMWARE-MAP.md) §1), and (2) the tables are reached through *virtual
methods* that form addresses arithmetically, so no pointer to them is stored anywhere. List them with:

```
python -m dirtyloader.re.params <stock.bin> [--names]
```

> **Correction (supersedes the first version of this file):** the record layout below starts four bytes
> earlier than first published. The old framing read the previous record's index as an "id", dropped each
> table's first entry (VOLUME), and misread byte 2 of the range word as a "field offset" — it is a **UI grid
> slot**. The "DEST is byte `+0x02`" and "send block offsets" claims built on it are withdrawn.

## The descriptor record (28 bytes, in flash)

Verified against the code: WAVSYNTH's `getParamDescriptor` returns `0x601C2FA4 + idx * 0x1C`.

| offset | field | WAVSYNTH idx 0 | idx 3 |
|---|---|---|---|
| `+0x00` | long name → DTCM | `"VOLUME"` | `"SHAPE"` |
| `+0x04` | UI label → DTCM | `"VOLUME"` | `"SHAPE"` |
| `+0x08` | 3-char code → DTCM — **the instrument FX-command mnemonic** | `"VOL"` | `"OSC"` |
| `+0x0C` | help text → DTCM | `"VOLUME (RELATIVE)"` | `"OSCILLATOR SHAPE"` |
| `+0x10..+0x12` | flags (meaning not yet pinned; "RELATIVE" params tend to have `+0x10 = 01/02`) | `00 01 01` | `00 00 00` |
| `+0x13` | **default value** (returned by `vt+0x108`) | `0x00` | `0x00` |
| `+0x14` | min | `0x00` | `0x00` |
| `+0x15` | max | `0xFF` | `0x45` (69 shapes) |
| `+0x16` | **UI grid slot** (`row = b>>1`, `col = b&1`; `0xFF` = not in the grid) | `0xFF` | `0x00` |
| `+0x17` | **UI page** (0 instrument, 1 modulators) | `0` | `0` |
| `+0x18` | **parameter index** = byte offset in the instrument data = instrument FX command `0x80|idx` (`0xFF` = none) | `0x00` | `0x03` |

Defaults seen: CUTOFF `0xFF` (open), DRY `0xC0`, PAN/FINETUNE `0x80` (centre), WAVSYNTH SIZE `0x20`.

## The tables

| table | engine | params | notable |
|---|---|---|---|
| `0x601C2FA4` | WAVSYNTH | 20 | SHAPE, SIZE, MULT, WARP, SCAN |
| `0x600CBF64` | MACROSYNTH | 20 | SHAPE, TIMBRE, COLOR, DEGRADE, REDUX, TRIGGER/STRIKE |
| `0x600CDBD0` | SAMPLER (+ sample settings) | 34 | BPM, STEPS, PLAY MODE, SLICE, START/LOOP OFFSET, LENGTH, DEGRADE |
| `0x600CC594` | MIDI OUT | 29 | PORT, CHANNEL, BANK, PG, PB, ADD NOTE, CHORD, CCA..CCJ |
| `0x600BC47C` | FMSYNTH | 48 | FM ALGORITHM, per-operator fields, FM MOD1..4 |
| `0x600BD560` | HYPERSYNTH | 30 | CHORD, 6 × chord note, KEY+SCALE, SWARM, WIDTH, SUBOSC, SHAPE |
| `0x600BB9E4` | EXTERNAL | 28 | INPUT, PORT, CHANNEL, BANK, PG, CCA..CCD |
| `0x600B5E6C` | **modulators** | 47 | 6 types × (TYPE, DEST, AMOUNT, …): AHD, LFO, DRUM, ADSR, TRIG, TRACKING |

Every sound engine ends with FILTER TYPE/CUTOFF/RES, AMP, LIMIT, PAN, **DRY / MODFX / DELAY / REVERB**
(WAVSYNTH indices `0x08..0x11`) — the sends are ordinary per-engine parameters.

## The instrument parameter interface (virtual, per engine)

Each instrument class (one global singleton per engine, [../FIRMWARE-MAP.md](../FIRMWARE-MAP.md) §8) exposes:

| slot | role | evidence |
|---|---|---|
| `+0xBC` | `getParamDescriptor(idx)`: `idx < N` → `table + idx*28`; `0x30..0x47` → `+0xC4(idx-0x30)` | WAVSYNTH `0x6004713C` |
| `+0xC4` | modulator-field descriptor (shared `0x6003AA20`) | |
| `+0xC8` | FX-command value text (per engine) | `SITES.md` |
| `+0xD8` | screen row → parameter index | used by `+0xE8` |
| `+0xDC` | parameter count | used by `+0x108` |
| `+0xE8` | **draw a parameter row** of the INSTRUMENT screen (name via descriptor, value via `0x600784F8`) | WAVSYNTH `0x60047194` |
| `+0x0F8` | **`getModDestName(dest)`** → `table[min(dest, count-1)]` | WAVSYNTH `0x60047168` |
| `+0x104` | **`getModDestCount()`** — `movs r0,#N; bx lr` | per engine, below |
| `+0x108` | `getParamDefault(idx)` → descriptor `+0x13` | shared `0x6003AC14` |
| `+0x10C` | `getParamValue(idx)` → `data[idx]` (`data` = `this+0x10`) | shared `0x6009BAD2` |

Instrument data: engine parameters at `data[0x00..]`, the **four modulator slots at `data[0x30..0x47]`**
(6 bytes each).

## LFO destinations — the per-engine lists

| engine | count (`+0x104`) | name table (run / flash) | getName (`+0x0F8`) | destinations |
|---|---|---|---|---|
| WAVSYNTH | 15 @ `0x600A3990` | `0x20003F3C` / `0x601E1F5C` | `0x60047168` (literal `0x60047190`) | OFF, VOLUME, PITCH, SIZE, MULT, WARP, SCAN, CUTOFF, RES, AMP, PAN, MOD AMT, MOD RATE, MOD BOTH, MOD BINV |
| MACROSYNTH | 15 @ `0x600A133C` | `0x2000422C` / `0x601E224C` | `0x60044DEC` | OFF, VOLUME, PITCH, TIMBRE, COLOR, DEGRADE, REDUX, CUTOFF, RES, AMP, PAN, MOD ×4 |
| SAMPLER | 14 @ `0x600A30A0` | `0x20004B88` / `0x601E2BA8` | `0x60046BB0` | OFF, VOLUME, PITCH, LOOP ST, LENGTH, DEGRADE, CUTOFF, RES, AMP, PAN, MOD ×4 |
| FMSYNTH | 15 @ `0x6009DE20` | `0x20003DC0` / `0x601E1DE0` | `0x6003F2AC` | OFF, VOLUME, PITCH, MOD 1..4, CUTOFF, RES, AMP, PAN, MOD ×4 |
| HYPERSYNTH | 15 @ `0x6009F824` | `0x2000407C` / `0x601E209C` | `0x6003FC14` | OFF, VOLUME, PITCH, SHIFT, SWARM, WIDTH, SUBOSC, CUTOFF, RES, AMP, PAN, MOD ×4 |
| EXTERNAL | 14 @ `0x6009CE9C` | `0x20004C7C` / `0x601E2C9C` | `0x6003E2AC` | OFF, VOLUME, CUTOFF, RES, AMP, PAN, CCA..CCD, MOD ×4 |
| MIDI OUT | 15 @ `0x600A20B4` | `0x20003E0C` / `0x601E1E2C` | `0x60045558` | OFF, CCA..CCJ, MOD ×4 |

**No engine offers DRY, MODFX, DELAY or REVERB.** For the extended-LFO-destinations mod the UI half is now
data-level:

1. raise the count immediate in `+0x104` (2-byte `movs r0,#N` patch per engine);
2. repoint the name-table literal of `+0x0F8` at an extended copy of the table in a cave (the label strings
   `"DRY"`, `"MFX"`, `"DEL"`, `"REV"` already exist in DTCM; a flash pointer works too — `getModDestName` only
   loads and returns it);
3. the **apply** step — where the audio thread turns a DEST index into a modulated parameter — is the one
   piece still to locate (in or under the engine voice nodes, ITCM). New indices need handling there (a Core
   hook in ITCM, see [../CORE.md](../CORE.md)), or an existing entry's slot can be repurposed.
