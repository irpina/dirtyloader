[dirtyloader docs](../README.md) › modulation destinations

# Modulation destinations: the 16-slot limit and what moves around it

This page answers whether the M8 can get more than 16 LFO destinations per engine. It records everything found
while building [examples/lfo-sends](../examples/lfo-sends/lfo_sends.c), and where each part of the firmware puts the
limit. Addresses are headless 6.6.4A: flash `0x6xxxxxxx`, and ITCM low addresses, which are copied from flash
`0x60001680 + addr`.

Each finding is marked:
- **HW**: tested on the spare Teensy 4.1 running core 0.5, or 0.6 where the section says so.
- **static**: read from the disassembly only.

## Short answer

The limit is in the **storage**, not at run time. Each modulator keeps its destination in the low 4 bits of a
packed byte in the instrument, `type << 4 | dest`. Songs (`.m8s`) and instruments (`.m8i`) store that byte as it
is. At run time the firmware already keeps the destination as a whole byte, and core can make an engine's list
any length.

Three pieces of firmware code assume 4 bits: the DEST editor, modulator paste and the instrument randomizer. A
native extension has to handle each of them, plus a place to keep the real index. Core 0.6 does all of that; see
[Core 0.6: extended destinations](#core-06-extended-destinations-built).

## Where the destination lives

| where | layout | evidence |
|---|---|---|
| instrument data | `FW_INSTRUMENT(i) + 0x3F + 6·k`, for modulator k = 0..3: `type << 4 \| dest`, then amount and 4 type-specific bytes. Types are 0 AHD ENV, 1 ADSR ENV, 2 DRUM ENV, 3 LFO, 4 TRIG ENV, 5 TRACKING | HW |
| live modulator | each track has 4 modulator objects, `0xA8` apart, in groups `0x2B0` apart from `fw_modulators` (`0x200159E0`, a literal in the firmware). +0x18 is `dest` as a full byte, +0x19 is `type` | HW |
| group | +0x2AC points at the instrument's modulator bytes, `FW_INSTRUMENT(i) + 0x3F`. Each modulator's +0xA0 points at the first modulator of its group | HW |

Inside a modulator object, which has vtable `0x2000282C` for every type:
- +0x10 and +0x14 point at the next and previous modulator in the group.
- +0x4C is the amount, as a float from 0 to 1.
- +0x50 is "active", +0x51 is "inverted", and +0x54 is the raw output.

The methods:
- +0x04 `output()`: +0x54, negated when +0x51 is set.
- +0x08 `amount()`: returns +0x4C. Its first call after a retrigger returns +0x4C × +0x04 and clears the flag at +0x0C.
- +0x1C `dest()`: `ldrb [r0, #0x18]`.

## Every place that reads or writes the destination

| what | address | does | tested |
|---|---|---|---|
| list length and names | engine vtable +0x104 `count()` and +0xF8 `name(dest)` (RAM, `FW_ENGINE_VTABLES`). Stock getters, such as WAVSYNTH's at `0x6003CA6C`, return `table[min(dest, count − 1)]` | core 0.5 already replaces both (`mod_dest_add`); a test mod can claim any count | HW |
| **DEST editor** (INST. MODS input) | `0x600574B0..0x6005760A`, field 1 at `0x600575B6` | EDIT+LEFT/RIGHT is ±1 and EDIT+UP/DOWN is ±16; the value saturates to 0..255 (`usat`). The field descriptor's max (+0x15, at least 16) applies, then `count − 1`, and then **`and #0xF`** before `bic #0xF; orr` into the packed byte | HW |
| **DEST draw** (INST. MODS) | `0x60056AC4..0x60056B08` | reads the packed byte, `and #0xF` at `0x60056AE8`, then `name(dest)`. The name getter is never asked for more than 15 | HW |
| **modulator paste** | `0x600571FC`, reached from INST. MODS input `0x600579D6` | copies the 6 bytes, then if `dest ≥ count` sets dest to `count − 1` (`0x6005725C..0x60057296`) | HW |
| **instrument randomizer** | `0x60053664` (instrument-screen action `0xE5` at `0x60056508`). Its modulator loop is at `0x600537B4..0x60053812` | for a modulator whose dest is 0: `dest = rand() % count`, `bic #0xF; orr`, **with no mask**. It skips EXTERNAL and MIDI OUT instruments | HW |
| unpack into the modulators | `0x570` and `0xA4C` (ITCM), reached through veneers `0x600A8C08` and `0x600A8E58` from the group setups `0x60092AC8` and `0x60092C94` | `dest = byte & 0xF` → +0x18, `type = byte >> 4` → +0x19. `0x60092AC8` also stores the group's +0x2AC | static (its result is HW) |
| apply | each engine's switch in ITCM, such as WAVSYNTH `0x175D4` (core's `ev_mod_apply` sites) | `slot = voice->mod + dest`. The switch only picks how to combine; an index past the stock list goes to its default branch and does nothing | HW |

The full scan of the image found no other callers of `count()` or `name()`. So nothing else validates the
destination: loading a song or an instrument, and changing an instrument's type, keep the byte as it is (static).

## The tests

A test-only mod ([hooks/dest-probe.c](hooks/dest-probe.c)) put its own getters into WAVSYNTH's RAM vtable,
claiming 20 destinations. Entries
15..19 were named X15..X19. Results on instrument 01:

- **Editor:** stepping MOD1 DEST up one at a time went 0D, 0E, 0F (X15), then **00**: index 16 passed the count
  check and was masked back to OFF. From 05, EDIT+UP (+16) gave 21, clamped to 19, then masked to **03**. The
  type nibble never changed.
- **Draw:** MOD3, with stored `0F`, showed "0F X15". The name getter was called 140 times and never asked for
  more than 15.
- **Apply:** with MOD3 on 15, `ev_mod_apply` saw `dest` 15, the modulator's +0x18 was `0x0F`, and its group's
  +0x2AC was `0x20273146`, the address of instrument 01's modulator bytes. About 6,600 calls a second came from one
  modulator, roughly 10 per audio block.
- **Paste:** copying MOD3 (`3F`) to MOD4 copied the byte unchanged while the count was 20. With the count back at
  the stock 15, the same paste stored **`3E`**: the paste clamp turned it into MOD BINV.
- **Randomizer:** this was 12 runs on MOD1 and MOD2, with their dest reset to 0 before each.
  - With the count at 20, 8 of 24 results were `0x10..0x13`: `rand() % 20` landed on 16..19 and spilled into the
    type nibble, turning AHD ENV into ADSR ENV.
  - With the count at 15, all 24 results were `0x00..0x0E`, and the type never changed.

lfo-sends 0.1 added one destination to make 16 (15 on SAMPLER and EXTERNAL), so it never hit the mask or the
spill.

## Core 0.6: extended destinations (built)

Core 0.6 puts the plan into practice. A mod calls `mod_dest_add` as before, and from 0.6 it gets up to 16 more
entries per engine (31 in all) on firmware whose header has the modulator layout (headless 6.6.4A).

**Storage:**
- The stock destinations stay in the packed byte as they are.
- Every destination a mod added holds 15 (`DEST_MARK`) in the byte, SAMPLER's and EXTERNAL's included (their stock
  lists end at 13). Core keeps the real index in `dests.ext[128][4]`, by instrument and modulator, in its ITCM state.
- **By name, not index.** An index depends on which mods add destinations, and in what order: core-api-demo
  loading before lfo-sends moves DRY from 0F to 10. So the song data `core:dests` (in `<song>.dldata`) also
  carries a 16-bit FNV-1a hash of each added destination's name, per engine. A load maps every saved index to
  this boot's by that hash.
- A name that no loaded mod adds becomes **MISSING** (`0xFF`). It is drawn as "FF MISSING" and applied by nobody,
  and core's LOAD SONG MODS? prompt offers the mod.
- All of this costs 744 bytes of the mods' area.
- A stored 15 with nothing in the table reads as 15, the engine's first added destination. That only happens with
  data from before core 0.6, such as lfo-sends 0.1's FX SEND.

**Six `flash_mid` sites** (a new builder site kind in the bindings' `loader.mids`). Each replaces 4 bytes of flash
code with a call into core's C. The call keeps every register except the result, and s0-s15; a `keep` site runs
the replaced instructions after the call:

| site | replaces | core function | what it does |
|---|---|---|---|
| `0x60056F9A` | `and r3, r3, #0xf` (the DEST field's value) | `core_dest_cell` | the real index, so editing steps from it |
| `0x600575E4` | `and r7, r7, #0xf` (the editor's store) | `core_dest_store` | an added destination: stores the marker and keeps the value |
| `0x60056AE8` | `and r5, r5, #0xf` (the DEST drawn) | `core_dest_shown` | the real index for the number and the name |
| `0x600537F4` | `blx r3; mov fp, r0` (the randomizer's count) | `core_dest_rand_count` | caps the count at the stock list, so it picks stock destinations only |
| `0x60056D0C` | modulator copy, kept | `core_dest_copied` | remembers the copied modulator's real index |
| `0x6005724E` | modulator paste, kept | `core_dest_pasted` | gives the pasted modulator that index |

**Following the instrument.** Core subscribes to its own events at order 0:
- `ev_inst_copy` (clone src → dst) and `ev_inst_paste` copy the four entries. The instrument clipboard's source
  slot is instview + 0x10 (`0xFF`: none), set by the copy at `0x60053948`; the clipboard's data is at +0x2A8.
- `ev_inst_clear` empties them.
- `ev_inst_save` writes `<file>.m8i.dldest` when any entry is set: 12 bytes, `DLD2` and four name hashes, one per
  modulator (0: stock).
- `ev_inst_load` reads that file before the firmware loads the instrument. At the next tick, once the
  instrument's type is in, core resolves the hashes for that engine.

**API:** `DL_CORE_VERSION` is `0x600`.
- `int (*mod_dest_of)(void *modulator, int dest)` gives the real index in `ev_mod_apply`. For a modulator on 15 it
  finds the instrument through the group (+0xA0, then +0x2AC); any other modulator comes back unchanged.
- The Model:02 header has no modulator layout yet, so there core stays at 16 and `mod_dest_of` returns `dest`.

**Without core 0.6:**
- The marker shows as the engine's last stock entry (for WAVSYNTH, MOD BINV) and does nothing, because the
  switch's default branch ignores it.
- A paste or a randomize then turns it into that entry for real: the paste clamp stores `count − 1`.

**A bug found on the way:** core never reset the per-engine destination counts at boot. ITCM keeps them across a
reset, and from an older core's layout they were garbage. The first song save after flashing walked bad name
pointers and crashed in `name_hash` (pc `0x601E060E`); the crash guard caught it. Core now zeroes them in
`core_load`.

**Not covered:**
- A mod that takes (refuses) an `ev_inst_*` action still sees core's table changed.
- Paste uses the source slot's entries at paste time, not at copy time.
- Moving instruments in the pool, if the firmware does that, has no core event.

### Hardware results (core 0.6 and lfo-sends 0.2, spare Teensy)

All of these were run on the device:
- **Editor:** from 0E, EDIT+RIGHT gave 0F DRY, 10 MFX SEND, 11 DEL SEND and 12 REV SEND, and stopped at the end of
  WAVSYNTH's list. The packed byte held `0F` throughout. EDIT+UP/DOWN stepped by 16 (11 → 01 → 11).
- **Draw:** every row shows its own number and name: REV SEND on MOD1 while editing MOD3.
- **Modulator copy/paste:** MOD1 (REV SEND) → MOD2 and MOD3 (DEL SEND) → MOD4 both kept their destinations.
- **Instrument copy (SHIFT+OPT, cursor top left) and paste into an empty slot:** instrument 02 came out with REV
  SEND / DEL SEND / DEL SEND.
- **`.m8i` save and load** (through `fw_inst_save` / `fw_inst_load`, core-api-demo's LEFT): instrument 00's MFX SEND
  arrived on instrument 01. The packed byte said only `0F`, so the value came from the sidecar (DLD1, then DLD2).
- **Song:** save, restart, then load `1.M8S`: REV SEND / DEL SEND / DEL SEND came back.
- **Load order:** DEL SEND was saved at 0x12, with core-api-demo's DEMO ahead of lfo-sends. After the order was
  swapped and the song reloaded, it came back as DEL SEND at 0x11.
- **Missing mod:** with lfo-sends off, the same modulator read "FF MISSING", core asked LOAD SONG MODS? with
  lfo-sends, and playback was fine.
- **Randomizer** (first build, capped at 15): with WAVSYNTH's list at 19, 32 results were all `0x00..0x0E`, with the
  type unchanged. It is now capped at the stock list, which is the same on WAVSYNTH.
  - Without the cap, about a fifth of the results spilled into the type (see the tests above).
  - Its modulator loop also left MOD2 alone while MOD1 had a destination. With both cleared, both were randomized.
- **Sound:**
  - WAVSYNTH on two tracks: an LFO on DEL SEND swung the delay send 0.01 ↔ 0.977, and an AHD envelope on REV SEND
    decayed the reverb send with each note.
  - DRY and MFX did not move, and both sends went back to their level (40) on stop.
  - With the order swapped: an envelope on MFX SEND moved the MFX send 0.01–0.98, DRY did not move, and it went
    back to 40 on stop.
  - With an LFO on DEL SEND, the delay send swept on MACROSYNTH (0.00–0.92) and on EXTERNAL (0.00–0.98, index 0x10
    there).
  - It swept on FMSYNTH (0.00–0.98) and on HYPERSYNTH (0.00–0.98) as well.
  - SAMPLER: no sample was loaded, so it was not played.
- **Not tested:**
  - clone from the phrase (`ev_inst_copy`);
  - the pool's delete (`ev_inst_clear` without a load).

## The send levels (lfo-sends)

- **Track voices:** they are not evenly spaced. Track 1's is at `fw_audio_engine + 0x5C0` and is `0x594` long.
  Tracks 2..8 follow from `+0xB54`, `0x674` apart, and each voice's +0x3D holds its track (HW). An earlier lfo-sends
  assumed even spacing. It wrote track 2's "gains" over that voice's audio block pointers, and playback crashed in
  the block mixer, pc `0x19FC4` and `0x1AE10`.
- **Strips:** +0x3E4 is the main strip (DRY), +0x450 REVERB, +0x4BC DELAY and +0x528 MFX. Each is a gain node:
  +0x38 is the target, +0x3C the current gain (+0x54 picks the word), +0x55 ramping, +0x56 ramp on change, and
  +0x58/+0x5C/+0x60 the ramp's start, step and phase. `fw_gain_set` in `m8-headless/fw.h` does what the firmware's
  setter does.
- **When the firmware sets them:** at note start, from the instrument's levels, and it doesn't write them again
  while the note plays.
- **The curve** (HW sweep of 00..FF): gain = 0.05797 × 1.02797^(level − 0x80) for the sends, capped at 0.97705; 00
  is off. The main strip is ×0.8696 of that, capped at 1.67168.
- **The instrument a track plays:** its player, `FW_PLAYER(t) + 0x178`, points at the instrument's data. The voice's
  +0x38 is its engine voice, not the instrument.
- **WAVSYNTH's levels:** DRY, MFX, DELAY and REVERB are at instrument + 0x1D..0x20 (parameters 0x0E..0x11). Other
  engines put them at other indices, so lfo-sends reads levels back from the gains instead.
- **Instrument types:** 0 WAVSYNTH, 1 MACROSYNTH, 2 SAMPLER, 3 MIDI OUT, 4 FMSYNTH, 5 HYPERSYNTH, 6 EXTERNAL, 0xFF
  none. Only WAVSYNTH was played on hardware; the randomizer's EXTERNAL and MIDI OUT checks agree with 6 and 3.
- **Where lfo-sends 0.2's four destinations go** (HW, its page): 0F–12 on FM, HYPER, MACRO and WAV; 0E–11 on
  SAMPLER and EXTERNAL. lfo-sends 0.1 had one destination, FX SEND, with a page that picked its level per
  instrument and modulator; 0.2 needs core 0.6 and has no picker.

Hardware results for lfo-sends 0.1, the FX SEND version:
- One LFO swept the DELAY send from 0.09 to its cap and back, and the send returned to the instrument's level when
  playback stopped.
- DRY was audible on the USB recording: 6,500 RMS steady with the LFO off, 6,500 to 8,300 with it on.
- On two tracks and two instruments, each moved only its own target, for 20 s with no crash.
- The choices came back after a song save, a restart and a reload.

## On the Model:02 (6.6.2A)

Core 0.6's extended destinations and lfo-sends 0.2 run on a Model:02. The ports:

**The six editor sites** are the same instructions in 6.6.2A, found by the instruction-run aligner:

| site | headless | Model:02 |
|---|---|---|
| DEST field cell | `0x60056F9A` | `0x600585C2` |
| editor store | `0x600575E4` | `0x60058C0C` |
| draw | `0x60056AE8` | `0x60058110` |
| randomizer count | `0x600537F4` | `0x60054EC4` |
| modulator copy | `0x60056D0C` | `0x60058334` |
| modulator paste | `0x6005724E` | `0x60058876` |

**Modulators:**
- 9 groups of 4 at `0x2000D270`, `0x2B0` apart. They were found in a RAM dump by their `+0xA0` pointers, each
  pointing at its group's first; headless's `fw_modulators` is likewise the first of 9.
- The class vtable `0x20002994` matches headless's slot for slot.
- 6.6.2A's group setup (`0x6009D430`) keeps **no pointer to its instrument**: headless stores it at `+0x2AC` after
  unpacking. So `FW_MODULATOR_INST_MODS(first)` goes through the group's track instead, to the track player's
  instrument (`+0x170` on the Model:02, `+0x178` on headless).
- The unpack routines are ITCM `0x3A8` and `0x87C` (headless `0x570` and `0xA4C`).

**The send levels:**
- Each voice sends its blocks to four gain nodes, each `0x6C` long as on headless, in separate arrays: DRY
  `0x20011650`, REV `0x200119B0`, DEL `0x20011D10` and MFX `0x20012070`, each + `0x6C` × track. Walked from the
  voices' destination lists; REV reaches the reverb, DEL the delay, MFX the MFX. `fw_track_gain(t, which)` in each
  header finds them.
- The ramp is not the same. On the Model:02 (strip update, ITCM `0x203B8`), the phase `+0x60` rises 1/256 a sample,
  so a ramp takes 8 blocks of 32 frames, and only then does `+0x3C` take the target. `+0x54` is not a word selector
  there.
- headless's `fw_gain_set` restarted that ramp every block, so the gain never left its start. Heard as "no effect";
  the target was moving 0.13–1.67 while the current gain stayed at 0.078. The Model:02's `fw_gain_set` sets the gain
  at once. Updates are 0.73 ms apart.

**Hardware results:**
- lfo-sends added its four destinations to every engine: 0F–12 on FM, HYPER, MACRO and WAV; 0E–11 on SAMPLER
  and EXTERNAL.
- They show in INST. MODS > DEST.
- An LFO on DRY (HYPERSYNTH, MOD 3, AMT FF) pumped the track: the main strip's gain went 0.29–1.67 with the
  current gain following.
- DEST was still DRY after a song save, a restart and a reload.
- **Space:** lfo-sends needs 3.8 KB of ITCM. Next to CHAOS CONTROL (10.6 KB) it doesn't fit in the Model:02's
  12.5 KB, so CHAOS CONTROL was switched off for the test; perf-mon (1.7 KB) fits beside it.
