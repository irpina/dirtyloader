# Modulation system & the "extended LFO destinations" mod

Reverse-engineered from the 6.6.2A parameter-label region (`dirtyloader.re` + string
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
(`dirtyloader.core.test_hooks`): the linker auto-allocates a Core table slot per
mod, so several mods share one event. In Path B, we define `MOD_APPLY` and the
extended-LFO-destinations mod registers a handler on it; a second modulation mod
can register on the same event with zero coordination — exactly the mechanism
proven today on `TICK`.

## Update: the wall was a relocation — resolved

The four failed passes below were all looking in the wrong address space. On Teensy 4, `.rodata` is copied
into DTCM with `.data` at boot, so every label in `0x601DE020..0x601EA2E0` is referenced by its **run-time**
address `0x20000000 + (flash − 0x601DE020)` and never by its flash address
([FIRMWARE-MAP.md](FIRMWARE-MAP.md) §1). Translated:

| label | flash | run time | code/data references |
|---|---|---|---|
| destination-name table | `0x601E4214` | `0x200061F4` | **12** |
| DEST enum label | `0x601E3D24` | `0x20005D04` | 6 |
| LFO DESTINATION | `0x601E3E2C` | `0x20005E0C` | 1 |
| SEND DELAY / REVERB / MODFX | `0x601E4558` / `457C` / `4534` | `0x20006538` / `655C` / `6514` | 6 each |

The SEND references are **parameter descriptor records** — 28-byte entries in plain flash (id, name, label,
code, help, flags, min/max/field offset), one table per engine plus a modulator table. They are mapped in
[hooks/static-m8-params.md](hooks/static-m8-params.md): the modulator `DEST` field is byte `+0x02` of each
modulator slot, and every engine's MODFX/DELAY/REVERB send has a descriptor and a field offset.

**What is left for the LFO mod:** follow the 12 references to the destination-name table (`0x200061F4`) to the
per-engine destination lists and their counts, then the code that maps a DEST value to a field (the apply
step, which runs in the audio thread). Both are now ordinary static work.

## RE findings (historical): static analysis hits a wall here

Four passes tried to locate the modulation-apply / parameter code by anchoring on
the destination and send name strings:

1. 4-byte pointer scan of the whole image → **no** reference to any dest/send
   string (so they aren't stored as pointers, and aren't fixed-width table rows).
2. Ghidra `getReferencesTo` on each interior string (resolves Thumb `movw/movt`
   address loads) → **none**.
3. Ghidra region scan: every referenced address in `0x601E3C00..0x601E5E00`
   (`dirtyloader.re.ghidra_xref`) → **zero referenced addresses in the region.**

Conclusion: the parameter/label tables are reached through **computed or
RAM-indirected addressing** — a base pointer held in a global (likely copied
flash→RAM at boot) plus a runtime offset — which neither byte scanning nor
Ghidra's static reference analysis bridges. Pinning the exact apply function and
the dest→parameter mapping needs **interactive Ghidra decompiler work** (define
the base global, follow the DEST byte through the voice/audio path), not more
one-shot scripts.

## Verdict & recommended path

- **Feasibility: high.** `SEND DELAY/REVERB/MODFX` are ordinary instrument
  parameters with known byte offsets; the only thing stock lacks is their
  presence in the destination enum. The M8 almost certainly applies modulation
  through a per-engine **destination→parameter descriptor table** (Path A) rather
  than a giant hardcoded switch — too many engine×destination combinations to
  hand-code — but this is **inference, not yet confirmed.**
- **Either path is covered.** If Path A: add the send offsets to the per-engine
  destination table + bump its count (pure data `.m8mod`, no Core). If Path B:
  the Core `MOD_APPLY` hook + handler we already have the machinery for.
- **Best next step is hardware-in-the-loop, not more static RE.** Once the Teensy
  is flashing (tomorrow), confirming Path A is fast and empirical: extend a
  destination count by one, flash, and see whether a new selectable destination
  appears and what it modulates. That closes the question in minutes versus hours
  of decompiler spelunking, and the Ghidra project
  (`re.ghidra_export`/`ghidra_xref` regenerate it) is there for the GUI if needed.

## Status

- Modulation data model: **mapped.**
- Sends confirmed as parameters outside the destination enum: **done.**
- Parameter descriptor tables (incl. the modulator DEST field, the sends): **mapped** (static-m8-params.md).
- Apply function / dest→param table: **unblocked** — the destination-name table has 12 references once
  translated to DTCM; next static pass. (Superseded: "blocked on interactive RE or hardware".)
- Mod itself: **design ready**, path (A vs B) pending that pass.
