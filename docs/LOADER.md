# Loading mods on the unit (core 0.3 and 0.4)

Core 0.3 is dirtyloader's answer to Elekloader's TELOS: the firmware is patched once, and from then on mods
are files on the M8's SD card. Core 0.4 adds what Elekloader's Digitone mk1 core gives mods beyond the hook bus
(an API, MIDI, pages, song data); [PARITY-DN1.md](PARITY-DN1.md) compares the two feature by feature. You put them there over USB, switch them on or off, and the next boot loads
them. No more rebuilding and reflashing the firmware for every change of mods.

First build: **M8 Headless 6.6.4A** on a Teensy 4.1. Everything below has run on hardware (a spare Teensy 4.1
with an SD card): upload over USB, loading at boot, the MODS page, per-song mod lists, the crash guard, and
every implemented event, counted by `examples/core-selftest`.

| TELOS (Digitone mk1) | core 0.3 (M8 headless) |
|---|---|
| mods are files on the +Drive, loaded at boot | `.m8x` files on the SD card, loaded into free ITCM at boot |
| transfer over USB (SysEx) | transfer over the m8c USB serial port (`ev_serial`) |
| Mod Menu: list, on/off | SYSTEM SETTINGS > MODS (TELOS): list, on/off, apply and restart |
| projects remember their mods | songs remember their mods (`<song>.mods`); LOAD SONG MODS? on load |
| crash guard: skip mods after a crash | the same, from Teensyduino's crash record, and a 10 s hang guard |
| core-dn1's Mod Menu, mod pages, project data, MIDI hooks | `dl/core.h` (core 0.4): pages, song data, files, MIDI in and out |

## What is where

| | where | what |
|---|---|---|
| hook bus | flash `0x60000200` | core 0.2's dispatcher, table and site stubs (layout 3) |
| loader | flash `0x601E0000` | `core03.c`, compiled with arm-none-eabi-gcc, in free flash past the image (`0x601DD400`) |
| core state | ITCM `0x29B40` | magic, hook table (64), the API pointer (`+0x208`), loaded mods, the MODS page, pages, song state; ITCM is MPU read-only until `core_early` opens it |
| mods | ITCM `0x2A4D0..0x2F980` | 21,680 bytes; mods run from ITCM, so they are fast and safe on the audio thread |
| scratch | ITCM `0x2F980..0x2FF80` | status text (1 KB) and a list buffer (512 B): `active.txt`, song lists, USB requests |
| veneers | ITCM `0x2FF80..0x30000` | up to 16 long branches from ITCM hook sites to their flash stubs |
| files | SD `/dirtyloader/` | `mods/*.m8x`, `active.txt`, `guard`, `status.txt`; each saved song gets a `<song>.mods` (and `<song>.dldata` when mods keep data) beside it |

The ITCM tail is free because the firmware's ITCM code ends at `0x29B40` and the FlexRAM gives ITCM six
banks (192 KB). The firmware never touches it (checked on hardware by filling it before `setup()`).

## Boot

1. `core_early`, first in `main()`: make ITCM writable (MPU region 1, RASR AP bits), write the ITCM veneers,
   retire the old table.
2. `core_load`, inside `setup()` at its call to `0x6008FDA8`: the card is mounted, and the firmware has not
   used it yet (no autosave, no samples, no audio). Core reads `guard` and `active.txt`, loads each listed
   `.m8x` into ITCM, relocates it, zeroes its `.bss`, adds its hooks in `order`, and writes `status.txt`.
3. `core_boot`, after `setup()`: put the MODS page in the free view slot (7), wrap the audio interrupt's
   vector for `ev_render_in` / `ev_render_out`, and set the magic so the dispatcher uses the new table; then
   `ev_boot` runs, loaded mods included.

Core uses the card in step 2, in answer to a USB request, from the MODS page, and after a song save or load
(below); never while the firmware has a file open.

`status.txt` after a boot with the heartbeat mod:

    dirtyloader core 0.4
    mods area 21680 bytes at 0x0002A4D0
    core-selftest.m8x: loaded core-selftest 0.1.0 at 0x0002A4D0, 624 bytes, 16 hooks
    core-api-demo.m8x: loaded core-api-demo 0.1.0 at 0x0002A740, 1120 bytes, 3 hooks
    hooks 24

Load errors are `E1` cannot open, `E2` not an .m8x, `E3` no room, `E4` read failed, `E5` checksum,
`E6` not a dl_mod, `E7` built for other firmware, `E8` id already loaded, `E9` hook table full, `E10` too many
mods (16).

## Crash guard

When a boot with mods crashes, Teensyduino's fault handler saves a crash record at `0x2027FF80` and reboots;
the record and ITCM survive that reset (not a power cycle). The next `core_load` sees a crash after a boot with
mods, writes `SKIP` to `guard`, loads nothing, and says so in `status.txt` with the crash pc. Nothing loads
while `guard` says `SKIP`; `python -m dirtyloader.unit good` (or any change of mods) writes `GOOD`.

**Hangs** (core 0.4), as TELOS does it: a boot that loads mods writes `ARMD` to `guard` first, and `ev_tick`
writes `GOOD` once the boot has run 10 s. A boot that finds `ARMD` (the last one hung, or lost power within
10 s) writes `SKIP` and loads nothing. A restart asked for (USB RESTART, the API's `restart`, the MODS page)
writes `GOOD` first: it is not a hang.

The MODS page's title says `SKIPPED: A CRASH`, `SKIPPED: NO 10 S RUN` or `SKIPPED` while the guard is set; its
RESTART row writes `GOOD` and restarts, so the set gets another try. `core->last_crash` gives mods the crash
record the boot found.

## The MODS page

SYSTEM SETTINGS gets a row, **MODS (TELOS) OPEN** (core patches the settings screen's text and colour
templates, using a copy past the image). EDIT on it opens the MODS page, a screen of the firmware's own kind in
its free view slot: one row per `.m8x` on the card, then APPLY & RESTART.

| state | meaning |
|---|---|
| `ON` | loaded and running |
| `+ON` | switched on; loads at the next boot |
| `OFF` | not loaded |
| `-OFF` | running now; switched off from the next boot |
| `E<n>` | listed in `active.txt`, but the boot refused it (load error n) |

UP / DOWN move, EDIT switches the mod under the cursor (written to `active.txt` at once), RIGHT switches it on
and LEFT off (as TELOS), EDIT on the last row restarts, OPT goes back to SYSTEM SETTINGS. The last row reads
RESTART when nothing has changed. A running mod that added a page shows `>` after its state, and RIGHT opens
the page (OPT comes back). The firmware draws its track list from column 34, so core's text and pages keep to
columns 0-33.

## Songs keep their mods

TELOS projects remember their mods; on the M8 it is songs. Core subscribes to two events at the firmware's song
routines:

- **`ev_song_save`**: after a save, core writes `<song path>.mods`, the mods running then, one per line as
  `file id version` under a `#` comment.
- **`ev_song_load`**: after a load (not the AUTOSAVE load during boot), core reads the song's `.mods`. If it
  names a different set from the one running, the MODS page opens as **LOAD SONG MODS?**, with rows marked `+`
  (the song wants it, not running), `-` (running, the song does not want it) or `?` (the song names a file that
  is not on the card). YES writes the song's set to `active.txt` and restarts; NO keeps the running set.

The firmware keeps the card busy for a while after its save or load routine is entered, so core does this from
`ev_tick`, 300 ms later, retrying up to ten times. Mods' song data (below) is saved and loaded at the same
moments, into `<song>.dldata`.

## The core API (core 0.4)

What core does for a mod beyond calling its handlers: the M8 counterpart of core-dn1's exports. A pointer to
`struct dl_core` sits after core's hook table (`DL_CORE_PTR`, ITCM `0x29D48`); `dl_core()` in `dl/core.h`
checks it and returns 0 under an older core. Take it at `ev_boot`.

| member | does | core-dn1 |
|---|---|---|
| `restart()` | reboot now (clears the hang guard first) | `core_restart` |
| `page_add(page)`, `page_open(page)`, `page_close()` | a screen of the mod's own: `{mod id, title, open, draw, key}`. Opened from the MODS page (RIGHT on the mod's `>` row) or by the mod; core clears it, then `draw()` runs every frame and `key(action)` gets each chord (return nonzero to keep it; OPT closes) | the Mod Menu, mod pages |
| `song_data(block)` | `{id, data, size, loaded(n)}`: saved with each song as `<song>.dldata`, put back on load (the boot's AUTOSAVE included); `loaded(0)` when the song has none | project data |
| `file_read(path, off, buf, n)`, `file_write(path, buf, n)` | files on the card by absolute path, from the UI thread | `fw_card_read` / `_write` |
| `midi_receive(packet)` | a USB MIDI packet played into the M8 as if from the host (ev_midi sees it first) | `core_midi_receive` |
| `midi_send(packet)` | a USB MIDI packet to the host (ev_midi_out sees it) | `fw_sysex_send` |
| `last_crash` | Teensyduino's crash record as the boot found it (`[0]` 0: none, `[6]` the pc) | `ev_crash` |
| `song` | the path of the song last loaded or saved | |

`examples/core-api-demo` uses all of it: a page (song value, MIDI counts), a value kept with the song, a note
sent out on EDIT, a note played in on RIGHT.

## MIDI (core 0.4)

Headless has USB MIDI only. Each packet is a word: byte 0 is cable << 4 | CIN, bytes 1-3 the MIDI bytes
(`DL_MIDI_PACKET`, `DL_MIDI_STATUS` in `dl/core.h`).

- **`ev_midi`** `int f(uint32_t packet)`: every packet `usbMIDI.read()` takes. `usb_midi_read`'s call of
  `usb_midi_read_message` (`0x600A376A`) goes to core's C (`core_midi_read`), which reads the packet (or one a
  mod played in), raises the event, and hands it on; a handler that returns nonzero drops it.
- **`ev_midi_out`** `int f(uint32_t packet)`: every packet `usb_midi_write_packed` (`0x600A3238`) sends; take
  it to drop it.

Checked on hardware: three messages sent from the computer arrived as three `ev_midi` calls, the last one
`0x6307B00B` (CC 7 = 99); the demo's note out arrived at `ev_midi_out` as `0x033C9009`; and its played-in note
reached the M8's read path.

## The .m8x format

A mod is C built with the SDK (`dirtyloader/sdk/include/dl/mod.h`) and linked at address 0:

    #include "dl/mod.h"
    #include "m8-headless/fw.h"
    static void on_tick(void) { ... }
    DL_MOD("my-mod", "0.1.0", "My mod", DL_ON(EV_TICK, 50, on_tick));

`dirtyloader.cc.build_m8x([sources])` compiles it and writes:

| offset | size | |
|---|---|---|
| 0 | 4 | `DLX1` |
| 4 | 4 | image bytes |
| 8 | 4 | .bss bytes |
| 12 | 4 | relocation count |
| 16 | 4 | crc32 of image, then relocations |
| 20 | image | code and data; it starts with the `dl_mod` header |
| | 4 × n | offsets of the words to add the load address to |

Relocations are found without parsing ELF: the mod is linked at 0 and at `0x01000000`, and every word that
differs by exactly that amount is an address into the image. Anything else that differs is refused.
`dl_mod.fw` names the firmware the mod was built for (the device header sets `DL_FW`); core refuses others.

## Transfer (USB)

Headless has no USB drive mode (no `USB_DRIVE` entry and no mass-storage interface in its USB descriptors),
and the shop needs to put mods on a unit anyway, so core takes files over the USB serial port m8c uses.

A new event, `ev_serial`, sits at the entry of the m8c command parser (`0x6007846C`), which drains every
waiting byte. Core's handler runs first, peeks the receive queue, and takes the call when the next byte is
`0xD1`, which never starts an m8c command (those are ASCII). m8c works as before.

**Request** (host to unit): `D1` cmd seq len(u16 LE) payload sum8, where sum8 is the low byte of the sum of
cmd through payload. **Reply**: a SLIP frame (`C0` ends it, `DB DC` / `DB DD` escape) `F1` cmd seq status
data, alongside any display frames.

| cmd | payload | reply data |
|---|---|---|
| 1 INFO | | text: core, firmware, card, mods area, loaded ids |
| 2 LIST | directory | names, one per line |
| 3 PUT | offset u32, name len u8, name, data (≤ 1 KB) | bytes written u32; offset 0 creates or truncates |
| 4 CHECK | name | size u32, crc32 u32 |
| 5 GET | offset u32, max u16 (≤ 512), name len u8, name | data |
| 6 MKDIRS | | creates `/dirtyloader/mods` |
| 7 RESTART | | (reply, then reset) |
| 8 PEEK | address u32, count u16 (≤ 512) | memory, for development. Nothing guards the read: stay in RAM, and away from address 0 and the stack guard at `0x200415E0`, which fault |
| 9 DELETE | name (under `/dirtyloader` only) | (core 0.4; SdFat's `FatFile::remove` `0x6009FF4C` / `ExFatFile::remove` `0x6009DADC`) |

Status: 0 ok, 1 bad request, 2 checksum, 3 bad path or no file, 4 SD error, 5 no card, 6 timeout, 7 unknown.
Names are `[A-Za-z0-9._-/]`, no `..`, under 64 bytes. PUT writes only under `/dirtyloader/` (names are
relative to it); LIST, CHECK and GET also take an absolute path (`/Songs/x.m8s.mods`).

The host side is `dirtyloader.unit` (Python, no dependencies; `dirtyloader.serialport` opens the port):

    python -m dirtyloader.unit info
    python -m dirtyloader.unit add sd-heartbeat.m8x     upload, verify by crc, switch on (--off: leave it off)
    python -m dirtyloader.unit remove sd-heartbeat.m8x  delete it from the card (clear: all of them)
    python -m dirtyloader.unit ls
    python -m dirtyloader.unit off sd-heartbeat.m8x
    python -m dirtyloader.unit restart
    python -m dirtyloader.unit status

Close m8c first; the port can only be open once. A web shop can speak the same protocol over Web Serial.

## Bring-up notes

- **Write every byte a mod places, 0xFF included.** The HEX writer used to leave out 0xFF bytes past the stock
  image, trusting the bootloader to have erased them. It had not: a `bl` encoded `FF F7 ..` kept a byte from
  an earlier build and the M8 crashed, at different places from build to build. `ihex.write(..., cover=)` now
  takes every site's range. Most of a day of "SD access breaks the firmware" was this.
- Check the firmware's mounted flag (`fw_storage + 4`) before any SdFat call, as the firmware does.
- The M8 screen can be read without m8c: send `E`, then decode the SLIP frames; `0xFD` frames are characters
  (char, x u16, y u16, colours). Keys go in as `C` plus a bitmask (LEFT 80, UP 40, DOWN 20, SHIFT 10, PLAY 08,
  RIGHT 04, OPT 02, EDIT 01). `python -m dirtyloader.m8screen` does both and writes a PNG.
- Reading address 0 (the NULL trap) or the stack guard (`0x200415E0`) faults the unit; the first such PEEK
  tested the crash guard by accident.
- Teensyduino's crash record in this build has a length of 11 words, not 44; core accepts both.
- The settings screen's enter code reaches its templates through a literal that points at the colour template
  (`0x60074018`), not the text one; core patches all three literals.
- Terminate every path core builds: core 0.3 built `<song>.mods` without its NUL, so the name ran on into the
  stack; opens failed until the stack happened to hold a 0, and one write left a stray `1.m8s.mods#`.

## Testing on hardware

`examples/core-selftest` subscribes to every implemented event and counts each call into `selftest_counts`;
PEEK reads the counters (the load address is in `status.txt`, the offset in the build's symbols). On the spare
Teensy: boot 1; tick and draw about 380k a second; render in and out about 740 a second each; one note per
played note; play and stop once per PLAY press; one midi per packet in, one midi_out per packet out; key,
view, tempo, song load and save, and serial as used.

Mods are compiled freestanding; `sdk/lib/dl_libc.c` (memcpy, memmove, memset, memcmp, strlen) and libgcc are
linked into each, so a struct copy links. A mod's own definitions win.

## Next

- A skip key at power-on; a check before switching a mod on.
- The rest of [PARITY-DN1.md](PARITY-DN1.md)'s "not built": instrument and modulation hooks, the sequencer's
  edits and tick, audio ownership.
- The Model:02 build: its own bindings, and the `.bin` container instead of HEX.
