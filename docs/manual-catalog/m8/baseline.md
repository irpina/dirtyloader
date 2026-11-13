# Baseline: what dirtyloader core 0.1.0 gives a mod on the M8 (Model:02, firmware 6.6.2A)

The one sheet every reader rates against. Written by hand from `docs/CORE.md`, `m8loader/core/abi.py` and
`m8loader/core/bindings/m8_6.6.2A_model02.json` on branch core-ghidra. Software-verified only; nothing has run
on hardware yet.

## Events (code a mod's handler runs)

- **TICK**: fires once per main-loop iteration, just before the firmware's `loop()` (the whole application
  frame). Observer only: the handler receives the event id and nothing else, cannot stop or change `loop()`,
  and has no way to read firmware state (no located state addresses and no calls back into the firmware).
  Several mods may each register a TICK handler; the linker gives each its own slot.

Not offered (event ids exist in the ABI but no firmware site is installed): BOOT, RENDER, AUDIO_BLOCK, INPUT.
There is no draw event, no key or input event, no parameter-change event, no note or row event, no FX-command
event, no MIDI event, no audio event.

## Calls (firmware functions a mod can call)

None. A mod cannot read or set a parameter, play a note, change a view, draw, send MIDI or touch the mixer.

## Tables (firmware data a mod can extend or rewrite through the loader)

None exposed as tables.

## Static patching (byte patches in a .m8mod)

A mod can rewrite bytes the author has located, guarded by the stock bytes it expects (same-size edits only).
This is coverage only where the site is already located. Located today:

- UI label strings in the parameter-label region, including the modulation destination short names
  (`CUTOFF`, `RES`, `AMP`, `PAN`, `CCA`..`CCD`, `VOL`, `PITCH`, ...), the send parameter names
  (`DRY`, `SEND MODFX`, `SEND DELAY`, `SEND REVERB`), modulator type names and filter type names.
- Scale name strings (for example `HARMONIC MAJOR`).
- The input/track routing name list (`L&R`, `MIC`, `USB`, `INL`, `INR`, ..., `T1`..`T4`).

So renaming one of those labels is `partial (static patch: rename only)`; the behaviour behind it is not
reachable. Not located: the destination list itself (which entries each engine offers, and its count), how a
destination is applied, any parameter range or default, any limit or count, any key handler, any FX command.

## Not offered, by area

- UI input and screen: no key events, no draw, no view changes.
- Parameters: no edit path, no ranges, no defaults, no enum lists (only some of their label strings).
- Sequencer: no row, phrase, chain, song, groove, table or transport events.
- FX commands: no dispatch hook, no command table.
- Modulation and voices: no modulator or destination hook; destination labels only.
- Mixer, effects, master: nothing.
- MIDI, USB, storage, settings, sampling: nothing.
