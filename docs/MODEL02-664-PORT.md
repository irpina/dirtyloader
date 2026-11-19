[dirtyloader docs](../README.md) › core on the Model:02 6.6.4A

# core 0.7 for the M8 Model:02 (6.6.4A)

Dirtywave's current Model:02 firmware (`M8Firmware.zip`, `Firmware/Model02/M8_V6_6_4A_MODEL02.bin`, sha256
`7bca8f34…b2b0e0`). The same core as headless and 6.6.2A: the same C (`core03.c`), the same events, API, MODS page,
Mod Menu and song lists. It is built against `sdk/include/m8-model02-6.6.4A/fw.h` with the sites in
`core/bindings/m8_6.6.4A_model02.json`.

    python -m dirtyloader.core.build_model02 M8_V6_6_4A_MODEL02.bin out

The `.bin`'s sha256 picks the firmware (6.6.2A or 6.6.4A). This writes `out/M8_V6_6_4A_MODEL02_core.bin` and an
`sd/` folder with the heartbeat mod built for 6.6.4A. Mods for it carry the firmware id `0x02060604`: core refuses a
6.6.2A build (`0x02060602`) and the other way round. The shop builds every mod for both (`m8-model02` and
`m8-model02-664`), and its Get started page builds core into this file in the browser (`firmware/m8-model02-664.json`).

**Status (2026-11-18):** built and checked against the stock image only. It hasn't run on a unit yet. Flash it only on
a unit you can put back to stock (the shop's Recover tab, or Dirtywave's `.bin`).

`tests/test_model02_664.py` checks every build, when the stock `.bin` is in `~/Downloads/M8Firmware_V6_6_4` or
`DIRTYLOADER_MODEL02_664_BIN` names it. It checks:
- the container's CRCs and the loader past the image;
- each call site's stock `bl` target and that it now goes to core;
- the extended-destination, visualizer and side-column sites;
- the view table, the vtable slots, the frame gate, the theme routines, the palette literal and the settings template;
- that no 6.6.2A or headless RAM address is left in core's code.

The builder checks each site's relocated instructions and each `mids` site's expected instruction as it builds.

## How each address was found

6.6.4A Model:02 is not a small step from 6.6.2A Model:02. Between them Dirtywave rebuilt the Model:02 from the same
source as Headless 6.6.4A. The audio engine became one object reached through a pointer, `set_view` reads a view table,
and the players are 0x248 long. So every address was looked for **from both** 6.6.2A Model:02 and Headless 6.6.4A
with `dirtyloader/re/portmap.py`, and every one was then checked by hand, mostly by disassembly:

    python -m dirtyloader.re.portmap <old .bin/.hex> M8_V6_6_4A_MODEL02.bin 0x6004C13C 0x20015458 ...

- **Code and flash data** are matched by windows of 24 bytes around the address. Both images are normalised first:
  branch, literal-load and `adr` offsets, and literal words holding an address, are zeroed. Each window found exactly
  once in the new image votes for a shift. A result only counts when the bytes at the address itself also match.
  Where they didn't (the function before it moved too), the address was found by its callers instead.
- **RAM** is matched through the literals that name it in code mapped as above.
- **Things only an instruction names** (engine member offsets, block sizes) are matched by finding each instruction
  that uses the headless value and reading the immediate at the matching instruction in 6.6.4A.

Where both sources gave the same address (most of the SdFat, USB, MIDI, theme, mod-apply and ITCM entries), that is
the evidence. The rest:

| what | 6.6.4A | how |
|---|---|---|
| `main`, `setup`, `loop`, `yield` | `0x600B42F0`, `0x6008595C`, `0x60085368`, `0x600BAF30` | `main`'s three `bl`s. `loop` is now a `b.w` veneer (to `0x6008646C`, which runs the touch engine and then the loop body at `0x60086294`), as on headless. `yield` is the `ldr.w pc` veneer to ITCM `0x2BACD`. Windows can't place veneers: they all look alike. |
| DRAW, KEY | `bl` at `0x600862EE`, `0x600863F2` | the loop body's `bl frame_refresh(0x2001A084)` and `bl router(ui, action)` after reading the input. The router is `0x6004F620`: it stores millis at ui+8 and toggles the visualizer on 0xE4, like 6.6.2A's. (The window vote said `0x6004F324`, the function before it, so it was found by its caller.) |
| VIEW, PLAY, STOP, SONG_LOAD, SONG_SAVE, SEQ_TICK | `0x6004EEA4`, `0x600A1010`, `0x600A119C`, `0x60066854`, `0x600812FC`, ITCM `0x238B4` | the same instructions as headless's. VIEW came out the same from both sources. For the other five, 6.6.2A Model:02's code differs and the 6.6.2A route gave a wrong address (PLAY, STOP) or one a few bytes off. |
| TOUCH | `bl` at `0x60086030` → `0x6007F180` | the touch engine moved into the loop (`0x60086008`, `bl` at `0x600862BE`). It still polls (`0x6007ED14`) and then asks the touch object `0x2001C9E0` for activity. Both routines are the same code as 6.6.2A's. |
| load_at | `bl` at `0x60085A4E` | the call right after the card is mounted (`bl fw_sd_ready` at `0x60085A3E`). Its callee `0x600A07AC` is headless's load_at callee: its first call builds the audio engine. |
| `fw_sd_ready` | `0x60080605` | 6.6.2A's code (the Model:02's own). Headless's version is different. |
| `fw_sys_save` | `0x600AD5BF` | headless's answer. The bytes are `70b50546 0024c822`, as on 6.6.2A. The 6.6.2A route was 6 bytes short. |
| SysEx handler | `0x2004093C`, stock `0x600ACCF1` | the store at `0x6008D314` (6.6.2A's `0x60089650`) |
| view table | `0x20000BD8`, 30 slots | `set_view` loads it (literal `0x6004F030`) and checks `id <= 0x1D`. Slot 7 is 0 and slot 0x1C is SYSTEM SETTINGS (`0x2001C87C`), so `FW_HAS_VIEW_TABLE 1` and no `view_switch`. |
| the audio engine | `0x2000C780` | a function-local static: built by `0x6009D9D4` behind a guard at `0x600A0428`, its address stored at `0x2002068C`. Headless's `0x2000BE80` maps here (2/2 literals). |
| engine members | soft clip (tap) +0x88D8, USB branch +0x8538, MFX +0x34B0, delay +0x3234, reverb +0x75F8, I2S branch +0x8920/+0x8984/+0x8AA8/+0x8AF0; the sequencer block 0x28 further in than headless's: clock +0x3B8, playing +0x3E0, bpm +0x3E8, mixer +0x408 | instruction by instruction from headless's (`movw #0x9750` → `#0x88D8` at 4 sites, none disagreeing; `#0x9308` → `#0x8538` 2; `#0x3D08` → `#0x34B0` 5; `#0x3A0C` → `#0x3234` 17; `#0x7E50` → `#0x75F8` 19). Headless's large offsets never appear in this build. The sequencer block: `play` (`0x600A1010`) tests and sets `[engine, #0x3E0]`, `set_tempo` stores `[engine, #0x3E8]`; the code adds `#0x3B8` 5 times and `#0x408` 4 times, headless `#0x390` 5 and `#0x3E0` 2 (none of those here). On the unit, +0x3B8 holds the clock's vtable `0x20002060`, +0x3E8 reads 120.0, +0x408 starts `01000000` like headless's mixer, and every other member starts with its class's vtable. (The first version of this port kept headless's +0x390/+0x3B8/+0x3C0/+0x3E0: the `ldr/str [#0x3B8]` matches it counted use another base.) |
| track voices | track 1 +0x5E8, tracks 2..8 +0xA7C + 0x574 × (t−1) | the engine constructor calls the voice constructor `0x6009D6F0` (it stores the track class's vtable) with these `r0`s. Headless: +0x5C0 and +0xB54, 0x674 apart. |
| track strips | main +0x2E4, then reverb, delay, MFX 0x6C apart (+0x350, +0x3BC, +0x428) | voice 3's nodes in the constructor (`r6` = engine + 0x1000): +0x54/+0x56 field stores at voice+0x2E4 and +0x3BC, and voice 4's at +0x2E4, +0x350, +0x3BC. Their class (vtable slot `0x20002F60`) has 6.6.2A's strip update (ITCM `0x207A8` = 6.6.2A `0x203B8`), so `fw_gain_set` is the Model:02 one. The voice tail is 0x100 shorter than headless's (+0x594/+0x5CC/+0x604 → +0x494/+0x4CC/+0x504). The order (main, reverb, delay, MFX) is headless's, not seen on a unit. |
| class slots | track `0x20002514`, MFX `0x20002D50`, delay `0x20002F48`, reverb `0x200029F0`, clock `0x20002060` | the `.data` word holding each update(), the headless update found again in ITCM |
| engine vtables (`FW_ENGINE_VTABLES`) | `0x200019DC 0x200020AC 0x20002274 0x20002840 0x20001E78 0x20002A68 0x20001C1C` | the one `.data` place where both +0xF8 (name) and +0x104 (count) hold headless's two methods, found again |
| players, modulators | `0x2001A980` + 0x248 × t (instrument +0x178); `0x20015570`, group +0x2AC the instrument's bytes | headless's layout: `mov.w #0x248` appears 86 times in both 6.6.4A builds (6.6.2A Model:02: `#0x240`, 62), and `ldrsb.w [#0x2AC]` 8 times in both |
| audio blocks | 32 frames | the pool's blocks are 0x94 apart (`mvn #0x93` in `AudioStream::allocate`), as on 6.6.2A. Headless's are 0x114 (64 frames). |
| `FW_ATTR_PAL_LIT` | ITCM `0x18FEC` | the attribute draw loop's `ldr.w fp, =FW_PALETTE` (`0x2000BD08`): the first of the two ITCM literals that hold the palette, as on both other builds. The loop decodes as headless's does (`sub.w r4, r0, #0x2e; cmp #0x24; cmp #0x80`). |
| frame gate | `fw_frame_last 0x200206F0`, 16 ms | the frame refresh `0x6004E218`: `cmp r6, #15` (headless: 31), literals `0x6004E420` (millis) and `0x6004E424` |
| side column | `bl`s at `0x6004E376 0x6004E3B0 0x6004E3C6 0x6004E408`, `0x6004F4BC 0x6004F4C8 0x6004F4D4 0x6004F4DE` | the frame refresh's normal branch and the view-draw dispatcher `0x6004F4A4` (`bl` at `0x6004E3BA`): the same calls in the same order as 6.6.2A. The meters are `0x6004DFF8`, not the window vote's `0x6004E020`. |
| visualizer | scope call `0x6004E312` → `0x6004D31A`; VIS_DRAW `0x6004E32C` (`strh.w r8, [r4, #0x2ea]`); entry sets remote+0x19 at `0x6004DE36` | the same code as 6.6.2A |
| SYSTEM SETTINGS | template `0x601D871C`, literals `0x60078150/58` (template), `0x60078934` (colours) | the same 24 rows as 6.6.2A Model:02 (BATT.CHARGING row 20, FIRMWARE UPDATE row 21): MODS in row 22, field 14 |
| `.bss` end, spare RAM | `0x200418E0`; `FW_SPARE_RAM 0x20041A00` | the reset handler's literal at `0x6000142C` (the same place in all three builds). 6.6.2A's `0x20041800` would now be inside `.bss`. |
| loader | C at `0x601F8000` (the image ends `0x601F1400`), ITCM tail `0x2BFB0..0x2FF80` (16.3 KB) | the ITCM copy now ends at `0x2BFB0` (the startup's copy; GPR17 unchanged) |

## What is different from 6.6.2A, and how core handles it

| | Model:02 6.6.2A | Model:02 6.6.4A | in core |
|---|---|---|---|
| screens | `set_view` is a switch; core switches to its page itself (`view_switch`) | a 30-slot view table, slot 7 empty | `FW_HAS_VIEW_TABLE 1`: core puts the MODS page in slot 7, as on headless |
| audio graph | globals (soft clip `0x2001DA34`, clock `0x2000D218`, ...) | one engine object `0x2000C780` with members at offsets (not headless's) | `FW_AUDIO_TAP_OBJ`, `FW_CLOCK_OBJ`, `FW_TRACK_VOICE` from the engine, as headless |
| track strips | arrays (`0x20011650 + 0x6C × track`) | inside each voice (+0x2E4) | `FW_TRACK_STRIP(voice)` |
| players | `0x200140E4 + 0x240 × t` | `0x2001A980 + 0x248 × t`, instrument at +0x178 | `FW_PLAYER(t)`, `FW_PLAYER_INST` |
| a modulator group's instrument | not kept: core used the track's player | kept at +0x2AC, as headless | `FW_MODULATOR_INST` |
| ITCM tail for mods | ~17.4 KB | 16.3 KB | bindings |
| mods' firmware id | `0x02060602` | `0x02060604` | `DL_FW` |

## On a unit (2026-11-18)

Run on a real Model:02. The spare Teensy 4.1 can't take this build: tycmd refuses it, because the Model:02 is a
Teensy MicroMod with 16 MB of flash.

- The flash read back over PEEK matches the build byte for byte (sha256 of the 2,092,437-byte payload).
- core 0.7 boots and reports firmware 0x02060604 with the card mounted. USB info, ls, add, status, restart and
  PEEK all work.
- The screen, keys, song view, mixer and the full-screen MOD LOADER (side column held off) all work. The song
  plays, with the scope, meters and play markers drawn and audio on USB.
- CHAOS CONTROL (code in flash at 0x60600000), PERF-MON and LFO-SENDS load and run, one at a time and together.
  Restarts were clean in 6/6 runs with all three, and 6/6 runs with a flash rewrite on every boot.
- On the unit, the engine members start with their classes' vtables, which confirms those offsets. The same check
  found the sequencer block's offsets (clock, playing, bpm, mixer) wrong in the first version of this port; they
  are fixed (see the table above).
- **sd-heartbeat must not run on a Model:02.** Its LED code turns pad GPIO_B0_03 (Teensy pin 13) into a GPIO.
  The Model:02 uses that pin, so the unit hangs or resets within 10 s (4/4 boots, and a probe that only sets the
  pad does the same). The crash guard catches it on the next boot. This is not specific to 6.6.4A. Fixed in
  sd-heartbeat 0.1.1: Model:02 builds (M8_MODEL02) leave the pin alone and only count ticks. They ran 8/8 boots
  clean, alone and with the three mods above, and the Model:02 tests check that the IOMUXC base isn't in them.
- Seen once and not reproduced in 26 later restarts: a crash at ITCM 0x1B0E0 (`arm_biquad_cascade_df1_f32`, read
  of a null coefficient pointer). It is in the update of the I2S branch's stereo filter (engine+0x8984, class slot
  0x20003084). `setup()` builds the engine at `load_at` and gives that filter its coefficients two calls later
  (0x60080150 -> 0x60039CF4). An audio interrupt in between would hit exactly this.

## Not checked yet

- The audio graph's routing to the speaker and headphones, and the strip order (main, reverb, delay, MFX) inside
  each voice. USB audio plays, but no mod that taps a strip has been heard on this firmware yet.
- `FW_SPARE_RAM`: the gap below the stack was measured on headless, not here.
- Touch and CHAOS's touch pad (they need a person at the unit).
