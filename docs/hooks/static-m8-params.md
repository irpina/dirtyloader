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
3. the **apply** step (below) needs the new indices: it is a switch, so they land in its default branch.

## The apply step — per-engine `switch(dest)` in ITCM (Path B)

Each engine applies modulation in the audio thread with `apply_mod(voice, modulator)`:

```
if (!mod->active()) return;            // vt +0x18
mod->update();                          // vt +0x14
out = mod->output(); amt = mod->amount();   // vt +0x04, +0x08 (floats); type = vt +0x0C
float *slot = &voice->mod[ mod->dest() ];   // voice +0x8C: one float per destination; dest = vt +0x1C
switch (dest) { case 1 /*VOLUME*/: *slot *= f(out, amt); ...  case 2 /*PITCH*/: *slot += ...; ... }
```

The destination index selects the slot directly; the switch only picks the combining rule (VOLUME
multiplicative, PITCH additive with an LFO special case, the rest additive with a per-destination scale). The
switches are `subs rX,#1; cmp rX,#N; tbb` — case 1 upward, OFF = 0 skipped — and their case counts equal the
destination counts minus one:

| engine | apply switch (run) | cases |
|---|---|---|
| FMSYNTH | `0x0C9D0` | 14 |
| HYPERSYNTH | `0x0E552` | 14 |
| MACROSYNTH | `0x1185A` | 14 |
| SAMPLER | `0x1439E` (fn `0x14350`) and its specialised copy fn `0x12800` | 13 |
| WAVSYNTH | `0x171BA` (fn `0x17160`, confirmed by decompile) | 14 |
| EXTERNAL | fn `0x0B324` (switch at `0x0B384`; reached through a function pointer at `0x600B4F04`) | 13 |

Both remaining switches were settled by decompiling them:

- **EXTERNAL is `0x0B324`.** Its cases follow EXTERNAL's destination list exactly, and it has no PITCH:
  - 1 VOLUME, multiplicative
  - 2 CUTOFF and 3 RES, additive
  - 4 AMP, ×16
  - 5 PAN, bipolar
  - 6–9 CC A–D, which re-read the modulator unless `this+0x90` is set
  - 10–13 MOD AMT / RATE / BOTH / BINV, which call the target modulator's `+0x28` (amount) and `+0x2C` (rate)
    methods; BINV passes `1 − x` to rate
- **`0x12800` is SAMPLER, not EXTERNAL.** The SAMPLER voice (its update `0x15144`, and `0x1473C`/`0x149F0`)
  applies modulator 0 through `0x12800`, then modulators 1–3 through `0x14350`, with `r1 = mods + 0xA8·k`. The
  modulator objects are 0xA8 bytes apart. The compiler specialised the first call: it guards each virtual call
  with a direct-call fast path. The cases are the same: VOLUME, PITCH (quantised through a table), LOOP ST
  (raises a reload flag and stores a u16 position at `+0x1F4`), LENGTH (clamped 0–1), DEGRADE/CUTOFF/RES, AMP
  ×16, PAN, MOD ×4. The SAMPLER writes its per-destination values to `voice+0x100 + 4·slot`; EXTERNAL keeps a
  pointer to its float array at `+0x8C`.

**For the mod:** a destination index past the original count takes the switch's `bhi` (default) branch. A Core
hook on that branch (an ITCM detour — [../CORE.md](../CORE.md)) can handle the new destinations. The sends are
applied in the per-track send mixers (32 nodes, 8 tracks × 4 buses), not in the voice, so the handler writes
the modulated level into that track's send-mixer gain rather than into `voice->mod[]`.
