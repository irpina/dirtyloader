[dirtyloader docs](../README.md) › core 0.5 on the Model:02

# core 0.5 for the M8 Model:02 (6.6.2A)

The same core as headless: the same C (`core03.c`), the same events, API, MODS page, Mod Menu and song lists.
It is built against `sdk/include/m8-model02/fw.h` with the sites in `core/bindings/m8_6.6.2A_model02.json`.

    python -m dirtyloader.core.build_model02 M8_V6_6_2A_MODEL02.bin out

This writes `out/M8_V6_6_2A_MODEL02_core.bin`, plus an `sd/` folder with the heartbeat mod built for this
firmware. The same command builds for Dirtywave's current Model:02 firmware, 6.6.4A, when given that `.bin` (the
file's sha256 picks the bindings): [MODEL02-664-PORT.md](MODEL02-664-PORT.md).

**Status:** runs on a Model:02 (2026-11-17): core 0.6 boots, mods load over USB (`unit add / restart / status`),
and CHAOS CONTROL plays from the touch screen in the visualizer ([CHAOS-CONTROL.md](CHAOS-CONTROL.md)). The
other events and the MODS page have not been exercised there yet.

Core 0.6's extended destinations run there too: the six editor sites are ported, and lfo-sends 0.2 works
([MOD-DESTS.md](MOD-DESTS.md#on-the-model02-662a)).

The Model:02 has one event headless doesn't: `ev_vis_draw`, a `flash_mid` at `0x6004B620` in the visualizer's frame
path ([CORE-EVENTS.md](CORE-EVENTS.md)). With it, `fw_rect` (the firmware's fill-rect, `0x60078C34`) draws over the
visualizer.

To flash with TyTools, make a `.hex` from the built `.bin`. Dirtywave's own `M8_V6_6_2A_MODEL02 (TyUploader).hex`
carries exactly the `.bin`'s payload at `0x60000000`, leaving out only runs of `0xFF`. So the patched payload,
written the same way, flashes with `tycmd upload` and boots. The SD card's FIRMWARE UPDATE takes the `.bin` as it
is.

These checks pass on every build:
- the container's CRCs;
- every site's stock bytes, its `bl` target and its relocated instructions;
- each `ev_mod_apply` site's branch to the epilogue;
- no headless-only RAM address appears in core's compiled code.

`tests/test_model02.py` runs those checks when the stock `.bin` is present. Flash the build only on a unit you
can restore with the stock `.bin`.

## How each address was found

Every address the headless core and SDK use was found again in 6.6.2A. The full map, with the evidence for each
of its 162 entries, is [hooks/model02-map.json](hooks/model02-map.json):
- **Code:** matched by unique runs of 10 normalised instructions across both images, then checked against
  callers, the literals the matched code loads, strings, and [FIRMWARE-MAP.md](FIRMWARE-MAP.md).
- **RAM data:** found through the literals the matched code loads.
- **RAM vtable slots:** the `.data` word that holds the matched `update()`.

151 entries are S1 (two independent lines of evidence) and 8 are S2. All 34 core sites have a Model:02
address. 27 of them are the same instructions as headless. 7 have a different prologue that still relocates
(VIEW, PLAY, STOP, TEMPO, SEQ_TICK, MUTE, PARAM_SET). ROW differs only in a register.

## What is different, and how core handles it

| | headless 6.6.4A | Model:02 6.6.2A | in core |
|---|---|---|---|
| screens | `set_view` reads a 30-slot table; slot 7 is empty and core puts the MODS page there | `set_view` is a switch on the id, and case 7 does nothing | `FW_HAS_VIEW_TABLE 0`: core subscribes `core_view` to `ev_view` and switches to its screen itself (leave, current view, id, enter) |
| audio graph | one engine object, `0x2000BE80`, with the objects at offsets | the objects are globals (soft clip `0x2001DA34`, USB branch `0x2001D854`, clock `0x2000D218`, MFX, delay, reverb) | `FW_AUDIO_TAP_OBJ`, `FW_CLOCK_OBJ` are absolute in both headers. Both graphs were walked on hardware: the soft clip feeds USB and the I2S branch, so `ev_audio_out` wraps it |
| audio blocks | 64 frames | 32 frames | `FW_AUDIO_FRAMES` |
| track strips | inside each track voice (`+0x3E4`) | an array, `0x20011650 + 0x6C × track` | `FW_TRACK_STRIP(voice)` |
| players | `0x2001ADF0 + 0x248 × track` | `0x200140E4 + 0x240 × track` | `FW_PLAYER(t)` |
| sequencer playing flag | `0x2000BE80 + 0x3B8` | `0x2000D218 + 0x28` | `FW_SEQ_PLAYING` |
| SYSTEM SETTINGS | MODS row at row 21, field 12 | two more rows (BATT.CHARGING, FIRMWARE UPDATE): MODS row at row 22, field 14 | bindings |
| loader | at `0x601E0000`, after the image (ends `0x601DD400`) | at `0x601F0000`, after the image (ends `0x601EB000`). The `.bin` grows, and its header records the length | the linker lets core's loader grow a `.bin` |
| ITCM tail | `0x29B40..0x2FF80` (21.6 KB of mods) | `0x2B8D0..0x2FF80` (~17.4 KB of mods) | bindings |
| mods' firmware id | `0x00060604` | `0x02060602` | `DL_FW`: a mod built for one does not load on the other |
| RAM vector table (VTOR) | `0x2000B800` | `0x2000C000` (startup's store at `0x600014C4`) | `FW_VECTORS` in each header. Until 2026-11-17 core hard-coded headless's: on the Model:02 that overwrote 5 words of the firmware's data and left `ev_render_*` and `ev_crash` unhooked |

The Model:02's touch screen and its own keys are not hooked; the KEY event sees their actions as it does m8c's.
