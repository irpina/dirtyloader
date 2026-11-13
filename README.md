# dirtyloader

An **Elekloader-style mod patcher for Dirtywave M8 firmware.** You supply the
stock firmware `.bin` that Dirtywave publishes, pick one or more mods, and
dirtyloader builds a custom `.bin` on your machine that you flash the normal way.
It never redistributes Dirtywave's firmware — mods carry only the author's bytes
plus the stock bytes each edit expects to overwrite.

> Status: **working foundation.** Container read/write, the `.m8mod` format, the
> linker, and a CLI are built and tested against real 6.6.2 firmware. Code-cave
> injection, a hook/event-bus core mod, and a GUI are not built yet. See
> [Roadmap](#roadmap). **Untested on real hardware — read the warning.**

## Why this is possible

The M8 `.bin` is a Dirtywave container (`M8FW`) wrapping a flat Teensy 4.1 flash
image. It is **unencrypted, unsigned ARM-GCC code**, protected only by two
ordinary CRC-32s. There is no cryptographic signature, so a patched payload with
recomputed CRCs passes the M8's own integrity check — which is exactly what makes
recompile-free binary modding viable.

### M8FW container format (reverse-engineered from 6.6.2 / Model02)

| Offset | Size | Field | Notes |
|-------:|-----:|-------|-------|
| `0x00` | 4 | magic | `"M8FW"` |
| `0x04` | 4 | version | u32 LE; high word = model (`0x0002` → Model02) |
| `0x08` | 4 | payload_len | u32 LE, == `len(payload)` |
| `0x0C` | 4 | payload_crc32 | `zlib.crc32(payload)` |
| `0x10` | 4 | load_addr | `0x60000000` (Teensy 4.1 FlexSPI flash base) |
| `0x14` | 4 | header_crc32 | `zlib.crc32(header[0x00:0x14])` |
| `0x18`..`0x1FF` | — | zero padding | |
| `0x200` | N | payload | flat IMXRT1062 flash image mapped at load_addr |

Both CRCs are standard zlib CRC-32 (poly `0xEDB88320`). Repacking = patch payload
→ recompute both CRCs → concatenate. `m8loader/m8fw.py` does exactly this and a
no-op rebuild is byte-identical to the stock file.

## Install / requirements

Pure Python standard library, **no third-party deps.** Python 3.10+.

## Usage

```bash
# inspect a firmware .bin
python -m m8loader.cli info   M8_V6_6_2A_MODEL02.bin

# confirm it is valid, recognised stock firmware
python -m m8loader.cli verify M8_V6_6_2A_MODEL02.bin

# apply mods -> patched .bin (repeat -m for more mods)
python -m m8loader.cli build  M8_V6_6_2A_MODEL02.bin \
    -m mods/demo-rename-scale.m8mod -o M8_patched.bin

# author tool: hand-edit a copy of the firmware, then diff it into a mod
python -m m8loader.cli make-mod stock.bin my-edited.bin \
    -o mods/my-mod.m8mod --id my-mod --name "My mod" --author you
```

Then flash the patched `.bin` the usual way: copy it to the M8 SD card and use
**PROJECT > SYSTEM SETTINGS > FIRMWARE UPDATE**, or flash with TyTools.

## The `.m8mod` format

A `.m8mod` is a small JSON document. Each patch is guarded by the stock bytes it
`expect`s, so a mod physically cannot apply to firmware it wasn't built for.

```json
{
  "m8mod_format": 1,
  "id": "demo-rename-scale",
  "name": "Rename Harmonic Major scale",
  "target": { "model": 2, "stock_sha256": "fbc152..." },
  "requires": [], "conflicts": [],
  "patches": [
    { "note": "scale name label", "addr": "0x601D0E62",
      "expect": "4841524d4f4e4943204d414a4f52",
      "data":   "444952545957415645204d414a20" }
  ]
}
```

- Each patch sets exactly one of `addr` (absolute flash address, as seen in a
  disassembler) or `offset` (payload-relative).
- `expect` and `data` must be equal length — **v1 is same-size replacement only**
  (no code relocation yet).
- The linker rejects unmet `requires`, declared `conflicts`, overlapping edits
  between mods, a wrong `stock_sha256`/`model`, and any `expect` mismatch.

## Project layout

```
m8loader/
  m8fw.py          M8FW container: parse / verify / patch / rebuild (+ CRCs)
  m8mod.py         .m8mod mod package format
  registry.py      known stock firmware (sha256 -> identity)
  linker.py        combine mods onto stock + diff_payloads (make-mod)
  cli.py           info / verify / build / make-mod
  test_roundtrip.py   container proof vs real firmware
  test_pipeline.py    end-to-end mod pipeline proof
mods/
  demo-rename-scale.m8mod   worked example (cosmetic, reversible)
```

Run the tests (point them at your stock `.bin`):

```bash
python -m m8loader.test_roundtrip  path/to/stock.bin
python -m m8loader.test_pipeline   path/to/stock.bin
```

## Roadmap

1. **Hardware validation** — confirm the on-device updater accepts a CRC-correct
   custom image and enforces no further check. Test on a **spare Teensy 4.1 +
   free M8 Headless firmware**, not a real M8.
2. **Ghidra project** — load the payload at `0x60000000` (Cortex-M7) and start
   mapping functions, so mods can target code, not just strings.
3. **Code-cave injection + hook core mod** — find free flash, inject Thumb code
   (keystone), and an event-bus "core mod" so several mods can hook one function.
4. **Resizable patches** and a mod repository format.
5. **GUI** (pick stock + mods, build).

## ⚠️ Warning & scope

- **Unofficial and unaffiliated with Dirtywave.** Flashing custom firmware is at
  your own risk and may brick the device or void support.
- The container work is proven in software, but **nothing here has been flashed to
  real hardware yet.** Whether the M8's updater enforces anything beyond the two
  CRCs is unconfirmed — validate on a spare Teensy first.
- dirtyloader **does not distribute firmware.** Supply your own stock `.bin`.
- The Teensy HalfKay bootloader is never touched; reflashing stock always recovers
  a device that still boots.
