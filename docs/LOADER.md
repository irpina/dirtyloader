# Loading mods on the unit (core 0.3)

Core 0.3 is dirtyloader's answer to Elekloader's TELOS: the firmware is patched once, and from then on mods
are files on the M8's SD card. You put them there over USB, switch them on or off, and the next boot loads
them. No more rebuilding and reflashing the firmware for every change of mods.

First build: **M8 Headless 6.6.4A** on a Teensy 4.1. It has run on hardware: a mod uploaded over USB,
loaded at boot, and the M8 ran normally with it.

## What is where

| | where | what |
|---|---|---|
| hook bus | flash `0x60000200` | core 0.2's dispatcher, table and site stubs (layout 3) |
| loader | flash `0x601E0000` | `core03.c`, compiled with arm-none-eabi-gcc, in free flash past the image (`0x601DD400`) |
| core state | ITCM `0x29B40` | magic, hook table (64), loaded mods; ITCM is MPU read-only until `core_early` opens it |
| mods | ITCM `0x29D98..0x2FA00` | 23,656 bytes; mods run from ITCM, so they are fast and safe on the audio thread |
| scratch | ITCM `0x2FA00..0x30000` | status text and `active.txt` at boot, USB requests after |
| files | SD `/dirtyloader/` | `mods/*.m8x`, `active.txt`, `guard`, `status.txt` |

The ITCM tail is free because the firmware's ITCM code ends at `0x29B40` and the FlexRAM gives ITCM six
banks (192 KB). The firmware never touches it (checked on hardware by filling it before `setup()`).

## Boot

1. `core_early`, first in `main()`: make ITCM writable (MPU region 1, RASR AP bits), retire the old table.
2. `core_load`, inside `setup()` at its call to `0x6008FDA8`: the card is mounted, and the firmware has not
   used it yet (no autosave, no samples, no audio). Core reads `guard` and `active.txt`, loads each listed
   `.m8x` into ITCM, relocates it, zeroes its `.bss`, adds its hooks in `order`, and writes `status.txt`.
3. `core_boot`, after `setup()`: set the magic, so the dispatcher uses the new table, then `ev_boot` runs,
   loaded mods included.

All of core's SD access happens in step 2 or in answer to a USB request; the firmware has no file open then.

`status.txt` after a boot with the heartbeat mod:

    dirtyloader core 0.3
    mods area 23656 bytes at 0x00029D98
    sd-heartbeat.m8x: loaded sd-heartbeat 0.1.0 at 0x00029D98, 264 bytes, 3 hooks
    hooks 4

Load errors are `E1` cannot open, `E2` not an .m8x, `E3` no room, `E4` read failed, `E5` checksum,
`E6` not a dl_mod, `E7` built for other firmware, `E8` id already loaded, `E9` hook table full, `E10` too many
mods (16).

## Crash guard

When a boot with mods crashes, Teensyduino's fault handler saves a crash record at `0x2027FF80` and reboots;
the record and ITCM survive that reset (not a power cycle). The next `core_load` sees a crash after a boot with
mods, writes `SKIP` to `guard`, loads nothing, and says so in `status.txt` with the crash pc. Nothing loads
while `guard` says `SKIP`; `python -m dirtyloader.unit good` (or any change of mods) writes `GOOD`.

Not covered yet: a mod that hangs without faulting. Power-cycle and switch it off over USB.

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
| 2 LIST | dir under `/dirtyloader` | names, one per line |
| 3 PUT | offset u32, name len u8, name, data (≤ 1 KB) | bytes written u32; offset 0 creates or truncates |
| 4 CHECK | name | size u32, crc32 u32 |
| 5 GET | offset u32, max u16 (≤ 512), name len u8, name | data |
| 6 MKDIRS | | creates `/dirtyloader/mods` |
| 7 RESTART | | (reply, then reset) |

Status: 0 ok, 1 bad request, 2 checksum, 3 bad path or no file, 4 SD error, 5 no card, 6 timeout, 7 unknown.
Names are relative to `/dirtyloader/`, `[A-Za-z0-9._-/]`, no `..`, under 64 bytes.

The host side is `dirtyloader.unit` (Python, no dependencies; `dirtyloader.serialport` opens the port):

    python -m dirtyloader.unit info
    python -m dirtyloader.unit add sd-heartbeat.m8x     upload, verify by crc, switch on
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
  RIGHT 04, OPT 02, EDIT 01).

## Next

- A MODS page in SYSTEM SETTINGS: list, on/off, apply and restart.
- Per-song mod lists: a file next to the song, and a prompt on load when its mods differ.
- Delete over USB (needs SdFat's remove), and a skip key at boot for mods that hang.
- The Model:02 build: its own bindings, and the `.bin` container instead of HEX.
