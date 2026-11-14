# dirtyloader

[![tests](https://github.com/irpina/dirtyloader/actions/workflows/tests.yml/badge.svg)](https://github.com/irpina/dirtyloader/actions/workflows/tests.yml)
[![pages](https://github.com/irpina/dirtyloader/actions/workflows/pages.yml/badge.svg)](https://github.com/irpina/dirtyloader/actions/workflows/pages.yml)

An **Elekloader-style mod patcher for Dirtywave M8 firmware.** You supply the
stock firmware `.bin` that Dirtywave publishes, pick one or more mods, and
dirtyloader builds a custom `.bin` on your machine that you flash the normal way.
It never redistributes Dirtywave's firmware — mods carry only the author's bytes
plus the stock bytes each edit expects to overwrite.

> Status: **patcher + Core dispatcher built.** The container, `.m8mod` format,
> linker, and CLI are tested against real 6.6.2A firmware, and the Core hook
> dispatcher / event-bus (`mods/core.m8mod`) is assembled and byte-verified
> against it. There's a CLI and an in-browser builder; a visible on-device
> handler is still to come, and **nothing has run on hardware yet.** See
> [Roadmap](#roadmap) and
> [docs/CORE.md](docs/CORE.md). **Read the warning before flashing.**

## Build it in your browser

The easiest path — no install. The GitHub Pages site runs the whole builder in
your browser (the engine is CPython compiled to WebAssembly via Pyodide):

**→ https://irpina.github.io/dirtyloader/**

Pick your stock `.bin` and some mods, and it hands you a patched `.bin` to flash.
Your firmware is read locally and **never uploaded** — exactly like the CLI, and
the same reason a mod only ever carries hashes of the stock bytes. The site is in
[`site/`](site/); it serves pre-built `.m8mod` files (built with `mkmod`, which
needs the firmware once) and applies them client-side.

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
→ recompute both CRCs → concatenate. `dirtyloader/m8fw.py` does exactly this and a
no-op rebuild is byte-identical to the stock file.

## Install / requirements

Pure Python standard library, **no third-party deps.** Python 3.10+.

## Usage

```bash
# inspect / verify a firmware .bin
python -m dirtyloader info   M8_V6_6_2A_MODEL02.bin
python -m dirtyloader verify M8_V6_6_2A_MODEL02.bin

# build .m8mod files from their source folders (mod.json + .s)
python -m dirtyloader mkmod mods/core        --stock M8_V6_6_2A_MODEL02.bin -o core.m8mod
python -m dirtyloader mkmod examples/hello-tick --stock M8_V6_6_2A_MODEL02.bin -o hello-tick.m8mod

# check them, and link them together against stock
python -m dirtyloader lint core.m8mod hello-tick.m8mod --stock M8_V6_6_2A_MODEL02.bin

# apply mods -> patched .bin (repeat -m for more mods; core first)
python -m dirtyloader build M8_V6_6_2A_MODEL02.bin \
    -m core.m8mod -m hello-tick.m8mod -o M8_patched.bin

# author tool: hand-edit a copy of the firmware, then diff it into a mod
python -m dirtyloader make-mod stock.bin my-edited.bin -o my-mod.m8mod --id my-mod --name "My mod"
```

Then flash the patched `.bin` the usual way: copy it to the M8 SD card and use
**PROJECT > SYSTEM SETTINGS > FIRMWARE UPDATE**, or flash with TyTools.

## The `.m8mod` format

A `.m8mod` ships only the mod author's bytes and a sha256 of the stock bytes each
change replaces — never Dirtywave's bytes — so a mod cannot apply to firmware it
wasn't built for, and mods are freely shareable. You write a mod as a **source
folder** (`mod.json` + Thumb `.s` files) and `mkmod` compiles it. The full
specification, including the source-folder layout, is **[docs/FORMAT.md](docs/FORMAT.md)**.

## Project layout

```
dirtyloader/
  m8fw.py          M8FW container: parse / verify / patch / rebuild (+ CRCs)
  m8mod.py         .m8mod format 2 (Mod, Site); loads format 1 too
  registry.py      known stock firmware (sha256 -> identity)
  linker.py        combine mods onto stock; checks; diff_payloads (make-mod)
  mkmod.py         a mod source folder -> .m8mod (assembles with keystone)
  lint.py          check / link .m8mod files
  cli.py           info / verify / build / make-mod / mkmod / lint / list
  web.py           in-browser builder glue (used by the Pages site via Pyodide)
  core/            the hook dispatcher + event bus (builder, abi, bindings)
mods/core/         the Core mod's source folder
examples/hello-tick/   the smallest handler mod (mod.json + hello.s)
site/              the GitHub Pages in-browser builder (index.html, app.js, make_site.py)
tests/             firmware-free unit tests (synthetic image; run in CI)
docs/FORMAT.md     the .m8mod specification
docs/FIRMWARE-MAP.md  the whole-firmware map (memory map, layout, threads, drivers, classes)
dirtyloader/re/    RE tools: memmap, layout, switches, vtables, params, ghidra_map, fwmap
```

Tests come in two kinds. The **firmware-free** suite uses a synthetic image and
runs in CI (no stock `.bin`):

```bash
python -m unittest discover -s tests -p "test_*.py"
```

The **against-real-firmware** scripts need your own stock `.bin` (never committed):

```bash
python -m dirtyloader.test_roundtrip  path/to/stock.bin
python -m dirtyloader.test_pipeline   path/to/stock.bin
python -m dirtyloader.test_tools      path/to/stock.bin
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
5. ~~**GUI** (pick stock + mods, build).~~ Done: the in-browser builder in [`site/`](site/).

## ⚠️ Warning & scope

- **Unofficial and unaffiliated with Dirtywave.** Flashing custom firmware is at
  your own risk and may brick the device or void support.
- The container work is proven in software, but **nothing here has been flashed to
  real hardware yet.** Whether the M8's updater enforces anything beyond the two
  CRCs is unconfirmed — validate on a spare Teensy first.
- dirtyloader **does not distribute firmware.** Supply your own stock `.bin`.
- The Teensy HalfKay bootloader is never touched; reflashing stock always recovers
  a device that still boots.
