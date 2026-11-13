# Modulation system & the "extended LFO destinations" mod

Reverse-engineered from the 6.6.2A parameter-label region (`m8loader.re` + string
analysis). This is the groundwork for mod #1 (extended LFO destinations) and
feeds mod #2 (KAOSS master-track mode).

## The modulation data model

Each M8 instrument has a few **modulator slots**. Every modulator has a **type**
and, whatever the type, the same set of per-slot fields — notably a shared
**DEST** (destination) selector:

- **Modulator types** (`MOD~ TYPE`, labels at ~`0x601E4070`):
  `AHD ENV`, `ADSR ENV`, `DRUM ENV`, `LFO`, `TRIG ENV`, `TRACKING`.
- **Shared destination field**: both `LFO DESTINATION` (`0x601E3E2C`) and
  `ENV DESTINATION` (`0x601E3F14`) select from one **DEST** enum (`0x601E3D24`).
  So extending "LFO destinations" extends destinations for *every* modulator type.

## The destination name table (`0x601E4214`)

The destination short-names are packed here, per synth engine:

```
CUTOFF RES AMP PAN  CCA CCB CCC CCD  MOD AMT  MOD RATE  MOD BOTH  MOD BINV
VOL PITCH FINETUNE ...  DRY  (SEND)MODFX/DELAY/REVERB  ...  1>LEV..4>FBK  MOD1..MOD4
```

Destinations are **per-engine** (WAVSYNTH/MACRO/FM/SAMPLE/MIDI each expose their
own set — e.g. `1>LEV…4>FBK` and `MOD1..4` are FM-only; `CUTOFF/RES` are the
filter). The full parameter/label tables span roughly `0x601E3C00..0x601E5E00`:
each parameter has a long name, a 4-char UI label, a 3-char code, and a help
string.

Also noted for later: a routing/track table at `0x601CFDD4`
(`L&R MIC USB INL INR U.L U.R ALL T1 T2 T3 T4`) — the master/track targets the
**KAOSS** mod (mod #2) will reuse.

## How "extended destinations" works — and the one open question

A destination has two parts: a **name** (UI) and an **effect** (the modulation
engine adds the modulator's value to some parameter). Adding a destination means
adding both. The implementation path depends entirely on **how the apply code
consumes the DEST value**, which is the next RE task:

- **Path A — table-indexed (data-only mod).** If the engine does
  `target = param_base + dest_offset_table[dest]; *target += mod_value`, then a
  new destination is pure data: append an entry to the per-engine destination
  array (name + target offset) and bump its count. **No Core needed.** Cleanest
  possible mod; just `.m8mod` byte patches.
- **Path B — hardcoded switch (needs the Core).** If it's
  `switch (dest) { case CUTOFF: ...; case RES: ...; }`, a new value has no case.
  Then: extend the name table + count for the UI, **and** hook the apply function
  with a new Core event (`MOD_APPLY`) whose handler applies modulation for the
  new DEST values.

Open RE questions for tomorrow (need the Teensy-independent Ghidra pass):
1. The **per-engine destination arrays** + their **counts** (so the UI offers the
   new entry) — find via xrefs to `0x601E4214`.
2. The **modulation-apply function** and whether it is table-indexed or switched
   — find by xref from the modulator processing in the voice/audio path.
3. The **DEST field's max** in the editor (so you can select the new value).

## Tie-in to "2 mods, 1 hook"

The multi-handler event bus is already built and verified
(`m8loader.core.test_hooks`): the linker auto-allocates a Core table slot per
mod, so several mods share one event. In Path B, we define `MOD_APPLY` and the
extended-LFO-destinations mod registers a handler on it; a second modulation mod
can register on the same event with zero coordination — exactly the mechanism
proven today on `TICK`.

## Status

- Modulation data model: **mapped.**
- Apply function + dest arrays/counts: **next RE pass.**
- Mod itself: **design only** until that pass decides Path A vs B.
