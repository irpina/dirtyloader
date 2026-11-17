[dirtyloader docs](../README.md) › The Digitone mk1 core, side by side

# core-dn1 and TELOS (Digitone mk1) against dirtyloader core 0.4 (M8 Headless)

The reference is Elekloader's `mods/core-dn1` (5.3) and `mods/telos-dn1` (0.2) for the Digitone mk1, together with
the project mod lists from TELOS's later work. Each of their features is listed here with what the M8 core does
in its place.

Status:
- **done**: built and checked on hardware (a spare Teensy 4.1 running M8 Headless 6.6.4A).
- **partly**: built and checked, but covering less than the Digitone feature does.
- **not built**: could be done on the M8, but isn't yet.
- **n/a**: the M8 has nothing the feature could attach to.

## TELOS

| TELOS (Digitone mk1) | M8 core 0.4 | status |
|---|---|---|
| mods kept on the unit: a 2 MB raw store on the +Drive, 63 files | `.m8x` files in `/dirtyloader/mods` on the SD card, 16 loaded at once, 21.7 KB of ITCM | done |
| link at boot, at `ev_card_ready`, before the project loads | `core_load` inside `setup()`, after the card mounts and before the firmware uses it | done |
| transfer over USB SysEx (`F0 7D 54 4C ...`, at `ev_sysex`) | transfer over the USB serial port m8c uses (`0xD1` requests, at `ev_serial`) | done |
| `unit add` / `list` / `on` / `off` / `remove` / `clear` / `info` / `restart`, `add --off` | `python -m dirtyloader.unit add [--off]`, `ls`, `on`, `off`, `remove`, `clear`, `info`, `restart`, plus `status` and `good` | done |
| a file's CRC is checked before the directory takes it | `add` reads the file back (CHECK: size and CRC-32) before switching it on | done |
| `format` | n/a: the card is a FAT/exFAT volume the M8 formats itself | n/a |
| SETTINGS > MODS (TELOS): a row per mod, `ON` `+ON` `OFF` `-OFF` `E<n>`, APPLY & RESTART / RESTART | SYSTEM SETTINGS > MODS (TELOS) > OPEN: the same rows and states | done |
| YES toggles; RIGHT on, LEFT off; NO back | EDIT toggles; RIGHT on, LEFT off; OPT back | done |
| the store's use in the title bar | `n / 21680 BYTES IN USE` under the list | done |
| crash guard: armed for 10 s at a boot with mods, one safe boot after a crash | armed (`ARMD`) for 10 s; a boot that finds it armed, or Teensyduino's crash record, loads nothing (`SKIPPED` in the title) until RESTART on the page or `unit good` | done |
| project mod lists, LOAD PROJECT MODS? on load | song mod lists (`<song>.mods`), LOAD SONG MODS? on load | done |
| a skip key at power-on (TELOS: not yet) | not built: the hang guard covers a mod that hangs at boot | not built |
| a check before switching on (TELOS: not yet) | not built: a refusal shows as `E<n>` after the restart, as on TELOS | not built |

## core-dn1: the hook bus and the boot

| core-dn1 | M8 core 0.4 | status |
|---|---|---|
| boot copier: the RAM image, `.bss`, at the OS entry's call | the loader copies each `.m8x` into ITCM, relocates it and zeroes its `.bss` | done |
| `ev_tick`, `ev_draw`, `ev_key` | `ev_tick`, `ev_draw`, `ev_key` | done |
| `ev_enc` | the M8 has no encoders | n/a |
| `ev_render_in` / `ev_render_out` | the same, from the audio interrupt (IRQ 70) | done |
| `ev_settings` and `core_additem` (SETTINGS rows) | core adds its own MODS row; mods get pages (below) in place of rows | partly |
| `ev_voice_on` (2.1), `ev_voice_ready` (4.2) | `ev_note`, at the note-on (ITCM), once per note | partly |
| `ev_boot_ui`, `ev_idle` | `ev_boot`, `ev_tick` | done |
| `ev_view` (the view stack) | `ev_view` at `set_view` (take it to stay) | done |
| `ev_transport` (start, stop, pause) | `ev_play`, `ev_stop` | done |
| `ev_tempo` | `ev_tempo` | done |
| `ev_project_saving` / `_saved`, the loads | `ev_song_save` / `ev_song_load` | done |
| `ev_card_ready` | none: `core_load` runs at that moment, and mods run after it | n/a |
| `ev_crash` (exception handler) | the API's `last_crash`: the crash record the next boot found (Teensyduino's handler reboots) | partly |
| `ev_usb` | none | not built |

## core-dn1: MIDI

| core-dn1 | M8 core 0.4 | status |
|---|---|---|
| `ev_midi_in` (every message), `ev_midi_cc` (3.2), `ev_midi_pc` (4.0) | `ev_midi`: every USB MIDI packet `usbMIDI.read()` takes, which a handler may take; CC and PC are filtered by the handler | done |
| `ev_sysex` | SysEx comes through `ev_midi` as its USB packets (CIN 4-7) | partly |
| `ev_midi_out`, `ev_seq_midi` (5.0.1) | `ev_midi_out`: every packet `usb_midi_write_packed` sends | done |
| `core_midi_receive` (5.0.1) | `midi_receive`: a packet played into the M8 as if from the host | done |
| `fw_sysex_send` | `midi_send`: one packet (a SysEx goes as its packets) | done |
| DIN MIDI | headless has USB MIDI only | n/a |

## core-dn1: what mods get from core

| core-dn1 | M8 core 0.4 (`dl/core.h`) | status |
|---|---|---|
| the Mod Menu (2.2), icon grid (2.3), `core_menu_open` | `page_add`: a `>` on the mod's MODS row, RIGHT opens its page | partly (a list, not a grid) |
| mod pages (2.1), `core_page_open`, `core_page_shown` | `page_open` / `page_close`; the page draws with `fw_text` and takes keys | done |
| project data (2.1) | `song_data`: blocks saved as `<song>.dldata` and put back on load (the boot's AUTOSAVE included) | done |
| `core_restart` / `core_restart_now` (5.0) | `restart` | done |
| `fw_card_read` / `fw_card_write` | `file_read` / `file_write` (files, by path) | done |
| firmware locations as exports (3.0, 3.3) | `m8-headless/fw.h`: SdFat, the UI (views, grid, text), USB serial, USB MIDI, millis, the crash record | done |
| the C library and libgcc (3.3) | `memcpy`, `memmove`, `memset`, `memcmp` and `strlen` linked into each mod (`sdk/lib/dl_libc.c`), plus `-lgcc` | done |

## core-dn1: what the M8 has no counterpart for, or not yet

| core-dn1 | M8 | status |
|---|---|---|
| parameter slots, `core_param_override`, lane parameters, knobs on pages, LFO names (2.1-5.2) | the M8 has no knob pages; its equivalent is instrument and modulation parameters (`core_mod_dests`, designed for Model:02 in [CORE-EVENTS.md](CORE-EVENTS.md)) | not built |
| `ev_render_voices`, exclusive and insert audio (`core_audio`, 3.1-4.0) | the Teensy Audio graph: `ev_render_in` / `ev_render_out` only | not built |
| `ev_render_params`, `ev_render_fx`, the note queue, `ev_note_built` | the M8's sequencer and FX are ITCM code; sites not mapped | not built |
| `ev_key_leds` | headless has no key LEDs | n/a |
| `ev_voice_free`, `ev_voice_steal`, `ev_arp_step` | no voice allocator or arpeggiator in that form | n/a |
| `ev_keyboard_note`, `ev_live_note` | key-played notes reach `ev_note` (its site also serves preview) | partly |
| `ev_mute`, `ev_pattern_op`, `ev_pattern_request` / `_switch`, `ev_track_reload` | the M8's mutes, chains and songs; sites not mapped | not built |
| `ev_sound_op`, `ev_sound_load`, `ev_sound_clear`, `core_pool_load` | the M8's instrument load and save; sites not mapped | not built |
| `ev_trig_set`, `ev_step_note`, `ev_plock_*`, `ev_track_length`, `ev_param_set`, `ev_sound_live` | the M8's phrase edits; sites not mapped | not built |
| `ev_seq_tick` | the sequencer tick (ITCM); site not mapped | not built |

Everything marked done was checked on hardware. The self-test mod (`examples/core-selftest`) counts every event.
The API demo (`examples/core-api-demo`) covers four things:
- its page opens from the MODS page;
- a value survives a song save and reload;
- a note sent to the host shows up in `ev_midi_out`;
- a packet it plays in reaches the M8's own MIDI read path.
