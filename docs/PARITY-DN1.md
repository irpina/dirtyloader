[dirtyloader docs](../README.md) › The Digitone mk1 core, side by side

# core-dn1 and TELOS (Digitone mk1) against dirtyloader core 0.5 (M8 Headless)

The reference is Elekloader's `mods/core-dn1` (5.3) and `mods/telos-dn1` (0.2) for the Digitone mk1, together with
the project mod lists from TELOS's later work. Each of their features is listed here with what the M8 core does
in its place.

Status:
- **done**: built and checked on hardware: a spare Teensy 4.1 running M8 Headless 6.6.4A, counted by
  `examples/core-selftest`, or heard and measured. The "checked" column says how.
- **partly**: built and checked, but covering less than the Digitone feature does.
- **not built**: could be done on the M8, but isn't yet.
- **n/a**: the M8 has nothing the feature could attach to. The reason is given.

## TELOS

| TELOS (Digitone mk1) | M8 core 0.5 | status | checked |
|---|---|---|---|
| mods kept on the unit: a 2 MB raw store on the +Drive, 63 files | `.m8x` files in `/dirtyloader/mods` on the SD card; up to 16 loaded at once, in 21.6 KB of ITCM | done | loaded, `status.txt` |
| link at boot, at `ev_card_ready`, before the project loads | `core_load`, inside `setup()`, after the card mounts and before the firmware uses it | done | boot |
| transfer over USB SysEx (`F0 7D 54 4C ...`, at `ev_sysex`) | transfer over the USB serial port m8c uses (`0xD1` requests, at `ev_serial`) | done | uploads, CRC check |
| `unit add` / `list` / `on` / `off` / `remove` / `clear` / `info` / `restart`, `add --off` | `python -m dirtyloader.unit add [--off]`, `ls`, `on`, `off`, `remove`, `clear`, `info`, `restart`, plus `status`, `good` and `safe` | done | each command |
| a file's CRC is checked before the directory takes it | `add` reads the file back (CHECK: size and CRC-32) before switching it on | done | |
| `format` | n/a: the card is a FAT/exFAT volume that the M8 and any computer format | n/a | |
| SETTINGS > MODS (TELOS): a row per mod, `ON` `+ON` `OFF` `-OFF` `E<n>`, APPLY & RESTART / RESTART | SYSTEM SETTINGS > MODS (TELOS) > OPEN: the same rows and states | done | screenshots |
| YES toggles; RIGHT on, LEFT off; NO back | EDIT toggles; RIGHT on, LEFT off; OPT back | done | `active.txt` after each |
| the store's use in the title bar | `n / 21664 BYTES IN USE` under the list | done | |
| crash guard: armed for 10 s at a boot with mods; one safe boot after a crash | armed (`ARMD`) for 10 s. Either a boot that finds it armed or Teensyduino's crash record makes core load nothing (`SKIPPED` in the title) until RESTART on the page or `unit good` | done | `ARMD` → `GOOD` at 10 s; a crash → `SKIP` (twice, by accident) |
| project mod lists, LOAD PROJECT MODS? on load | song mod lists (`<song>.mods`), LOAD SONG MODS? on load | done | save and load |
| a skip key at power-on (TELOS: "not yet") | `python -m dirtyloader.unit safe`, since headless has no keys. It sends a marker over USB serial while the unit boots, and core listens for 350 ms once USB is up | done | the unit booted with `safe boot` in `status.txt` |
| a check before switching on (TELOS: "not yet") | when the MODS page switches a mod on, core reads the file and checks everything the boot would: header, size against the mods area, CRC, the `dl_mod` magic and ABI, the firmware. A refusal leaves it off and shows `E<n>!` | done | a corrupt upload showed `E5!` and stayed out of `active.txt` |

## core-dn1: the hook bus and the boot

| core-dn1 | M8 core 0.5 | status | checked |
|---|---|---|---|
| boot copier: the RAM image and `.bss`, at the OS entry's call | the loader copies each `.m8x` into ITCM, relocates it and zeroes its `.bss` | done | |
| `ev_tick`, `ev_draw`, `ev_key` | `ev_tick`, `ev_draw`, `ev_key` | done | ~380k/s, keys |
| `ev_enc` | n/a: the M8 has no encoders. Its input is 8 keys, reported as chords to `ev_key` | n/a | |
| `ev_render_in` / `ev_render_out` | the same, from the audio interrupt (IRQ 70) | done | ~740/s |
| `ev_settings`, `core_additem` (SETTINGS rows) | `setting_add`: a mod's settings rows (a byte between min and max, with names) in the Mod Menu, reached from SYSTEM SETTINGS > MODS (TELOS) > MOD MENU; LEFT / RIGHT change them, and core keeps them in `/dirtyloader/settings.txt` across boots | done | the demo's DEMO VOICE: ON → LOUD, `DEMO VOICE=2` in the file, LOUD again after a restart |
| `ev_voice_on` (2.1), `ev_voice_ready` (4.2) | `ev_note` at the note-on (`player, ...`); `ev_row` with the row's 9 bytes before it fires | done | 1 per note, 1 per row |
| `ev_boot_ui`, `ev_idle` | `ev_boot`; `ev_tick` (the M8 has one main loop and no RTOS tasks) | done | |
| `ev_card_ready` (5.0) | `ev_card_ready(mounted)`: right after core loads mods, before the firmware first uses the card | done | 1 per boot |
| `ev_usb` (5.0) | `ev_usb(configured)`, from `ev_tick` when Teensyduino's `usb_configuration` (`0x2004159F`) changes | done | 1 at boot, `1` |
| `ev_crash` (5.0) | `ev_crash(frame)`: core's handler sits in front of Teensyduino's for HardFault, MemManage, BusFault and UsageFault (RAM vector table) and runs the mods' handlers with the exception frame, then Teensyduino records the crash and resets; the next boot's `status.txt` says the handlers ran | done | a NULL read: `ev_crash: the mods' handlers ran in the fault (pc 0x601E05AE)` |
| `core_restart` / `core_restart_now` | `restart()` | done | |
| `ev_view` (the view stack) | `ev_view` at `set_view` (take it to stay) | done | |
| `ev_ui_msg` | n/a: the M8 has no UI task or message queue. Its loop calls the input router (`ev_key`) and the views directly | n/a | |
| `ev_transport` (start, stop, pause) | `ev_play`, `ev_stop` (the M8 has no pause) | done | 1 per press |
| `ev_seq_tick` | `ev_seq_tick(engine)` at the tick processor (ITCM, 192 a beat) | done | ~1,900 in a 3 s play at 120 BPM |
| `ev_tempo` | `ev_tempo` | done | |
| `ev_project_saving` / `_saved`, the loads | `ev_song_save` / `ev_song_load` | done | |
| `ev_pattern_request`, `ev_pattern_switch`, `ev_pattern_op` | the M8 has no patterns. Its song rows, chains and phrases are edited in place, with no pattern switch or pattern save. Phrase edits reach `ev_step_edit` | n/a | |
| `ev_track_reload`, `ev_sound_load`, `ev_sound_op` (pool) | `ev_inst_load` / `ev_inst_save` (`.m8i` files), `ev_inst_copy(view, src, dst)` (clone), `ev_inst_paste(view, action)` (copy and paste in the instrument view and the pool), `ev_inst_clear`. The M8's pool has no send or write-protect | done | 1 each: save, load, clone (row 0 went to instrument 01), paste (slot 02 = slot 00) |
| `ev_sound_clear`, `core_pool_load` | `ev_inst_clear(song, slot, full)` at the slot clear (the pool's delete); the API's `inst_load(path, slot)` / `inst_save(path, slot)` through the firmware's own load and save | done | pool delete → 1, slot emptied; the demo copied slot 00 into 01 through a file |
| `ev_mute` | `ev_mute(mixer, track)` at the routine every mute and solo path applies through. It fires once per track, and the masks are at `fw_mute_mask` / `fw_solo_mask` | done | 8 per toggle |
| `ev_trig_set`, `ev_step_note`, `ev_plock_store` / `_clear`, `ev_step_clear`, `ev_track_length` | `ev_step_edit(view, cell, n, column)`: a cell edited (its column), or a bulk edit (cut / clear, paste, interpolate, rotate, FILL, transposing a selection) as the steps that changed, column -1. Core wraps the phrase view's two edit slots (RAM) and compares the phrase with its last copy, so a redraw that changes nothing says nothing | done | single notes 1 each; cutting rows 0-3 and pasting them back: 1 bulk report each, 1 step |
| `ev_param_set`, `ev_sound_live` | `ev_param_set(instview, field, old)`: an instrument field changed and its value went to the playing tracks | done | 1 per edit |
| `ev_keyboard_note`, `ev_live_note` | `ev_live_note(player, instrument, note, velocity)` at the M8's live / preview trigger (ITCM run `0x23374`): notes played or auditioned from the keys, not the sequencer's (`ev_row`, `ev_note`). Take it to drop the note | done | 4 notes entered → 4 (C-4, velocity 0x64); 0 during playback |
| `ev_key_leds` | n/a: headless has no key LEDs. Its keys are m8c's, sent over USB serial | n/a | |
| `ev_voice_free`, `ev_voice_steal` | `ev_note_off(player, kill)`. The M8 has one player per track (8, `FW_PLAYER(t)`) and no voice allocator to steal from | done (release); n/a (steal) | 1 per OFF |
| `ev_arp_step` | n/a: the M8's arpeggio is an FX command (ARP), which `ev_fx_row` / `ev_fx_command` see | n/a | |

## core-dn1: MIDI

| core-dn1 | M8 core 0.5 | status | checked |
|---|---|---|---|
| `ev_midi_in`, `ev_midi_cc` (3.2), `ev_midi_pc` (4.0) | `ev_midi`: every USB MIDI packet `usbMIDI.read()` takes, which a handler may take. Handlers filter CC and PC themselves | done | 3 in, CC 7 = 99 |
| `ev_sysex` | `ev_sysex(data, len, last)`: core chains usbMIDI's SysEx handler, which the firmware sets | done | 1 per SysEx sent |
| `ev_midi_out`, `ev_seq_midi` (5.0.1) | `ev_midi_out`: every packet `usb_midi_write_packed` sends | done | the demo's note |
| `core_midi_receive` (5.0.1) | `midi_receive`: a packet played into the M8 as if from the host | done | reached the read path |
| `fw_sysex_send` | `midi_send`: one packet (a SysEx goes as its packets) | done | |
| DIN MIDI | n/a: headless is a bare Teensy board with no MIDI jacks; its MIDI is USB MIDI | n/a | |

## core-dn1: audio

| core-dn1 | M8 core 0.5 | status | checked |
|---|---|---|---|
| exclusive audio, insert audio (`core_audio`, 3.2-4.0) | `ev_audio_out(left, right, frames)`: the master output's two blocks (64 float frames, 44.1 kHz) before they go to USB and I2S. A handler processes them in place (insert) or writes them and takes the event (exclusive). Core wraps the tap's `update()` through its vtable, which lives in RAM | done | `examples/audio-tone`: 440.0 Hz recorded from the M8's USB audio |
| `ev_render_voices` (3.1) | `ev_track_audio(left, right, track)`: each track's rendered block pair, after its voice renders and before its mixer strip and its three sends read it (both port pairs while it crossfades an instrument change). Core wraps the track voice class's `update()` | done | `examples/track-silence` zeroes track 1: the recorded output went from 6,530 RMS to silence |
| `ev_render_params` (3.3) | `ev_render_params(engine)`: once per audio block, before the sequencer clock and the tracks run. The M8 has no single parameter-word stage (gains ramp inside each object), so this is the block's first moment, where a mod sets what the block will use | done | 2,497 in 3.6 s (one per block) |
| `ev_render_fx` (5.0) | `ev_fx_audio(stage, left, right)`: each send effect's input (MFX, delay, reverb) before it runs. A handler that takes MFX or the reverb replaces it: the effect does not run, and the handler's blocks go to its outputs. The delay (mono in) is observe-only | done | `examples/fx-replace` on a reverb-only sound: the reverb's smeared output (peak 32767) became its input at a quarter level (the pulse, 4,608) |
| `ev_mod_apply` (designed for the M8 in [CORE-EVENTS.md](CORE-EVENTS.md)) | `ev_mod_apply(dest, modulator, target, engine)` at the destination switch of each engine. A handler may take it, which skips the stock destination | done | FM, HYPER, MACRO, SAMPLER, WAV, EXTERNAL: each counted |
| `ev_fx_command`, `ev_fx_row` (the M8's own) | `ev_fx_row` (phrase FX applier), `ev_fx_command` (table FX executor) | done | 3 per row; per table tick |
| the note queue (4.1), `ev_note_built` (5.1) | `ev_row`: the row (note, velocity, instrument, three FX) before it fires, which a handler may rewrite | done | |

## core-dn1: what mods get from core

| core-dn1 | M8 core 0.5 (`dl/core.h`) | status | checked |
|---|---|---|---|
| the Mod Menu (2.2), icon grid (2.3), `core_menu_open` | the Mod Menu: every mod page in a grid two across, the settings rows below; opened from the MODS page's MOD MENU row, or by a mod with `menu_open()`. The M8's screen is text, so tiles are names, not icons | done | grid, EDIT opens the page, OPT back to the menu |
| mod pages (2.1), `core_page_open`, `core_page_shown` | `page_open` / `page_close`; the page draws with `fw_text` and takes keys | done | |
| project data (2.1) | `song_data`: blocks saved as `<song>.dldata` and put back on load (the boot's AUTOSAVE included) | done | value 5 back after reload |
| `fw_card_read` / `fw_card_write` | `file_read` / `file_write` (files, by path) | done | |
| firmware locations as exports (3.0, 3.3) | `m8-headless/fw.h`: SdFat, the UI, USB serial and MIDI, the song layout, mixer masks, the players, the audio engine, millis, the crash record | done | |
| the C library and libgcc (3.3) | `memcpy`, `memmove`, `memset`, `memcmp` and `strlen` linked into each mod, plus `-lgcc` | done | test |

## The Digitone's knob pages

| core-dn1 | M8 core 0.5 | status | checked |
|---|---|---|---|
| LFO destination names and groups (5.2), `core_param_override`'s names | `mod_dest_add(engine, name)`: a destination added to an engine's list, shown and picked in the instrument MODS page's DEST like a stock one, applied by the mod in `ev_mod_apply`. Core swaps the engine's two getters in its RAM vtable. A modulator keeps its destination in 4 bits, so each engine takes 16: one more for the 15-destination engines, two for SAMPLER and EXTERNAL | done | the demo's WAVSYNTH destination DEMO showed as `0F DEMO` and was applied 28,352 times in 1.5 s |
| parameter slots, lane parameters, knobs on pages (2.1-5.1) | n/a as such: the M8 has no knob pages, and its parameters are fields a view edits with EDIT + arrows. A mod's own parameters go on its page (`page_add`), kept with the song (`song_data`), and stock fields are observed with `ev_param_set` | n/a | |

## The other M8: Model:02

core 0.5 is also built for the M8 Model:02 6.6.2A, from the same C, with every site found again in that
firmware ([MODEL02-PORT.md](MODEL02-PORT.md)). `python -m dirtyloader.core.build_model02` writes a flashable
`.bin`. It is checked statically on every build (`tests/test_model02.py`), but has not been run on a Model:02 unit:
this work tested on the spare headless Teensy only, as asked.
