# The .m8mod format

A `.m8mod` is a JSON file: one mod for the Dirtywave M8. It follows Elekloader's `.elemod` wherever the M8
has the same thing, so the rules carry over:

- **Nothing from Dirtywave is distributed.** A mod carries only its author's bytes and a sha256 of the stock
  bytes each change replaces, never the stock bytes. Where its bytes repeat the firmware it says
  `["stock", addr, n]`, and the loader copies them from the user's own, hash-checked firmware.
- **Every mod names its target** (the stock firmware it was made for, by hash). dirtyloader refuses a mod whose
  target it does not know, or a set of mods made for different firmware.
- **Mods are checked against each other before anything is built.** Two mods may not touch the same bytes or
  claim the same named resource, and every `requires` and every subscribed event must be met.

## Example

```json
{
 "m8mod": 2,
 "id": "hello-tick", "version": "1.0",
 "title": "Hello tick", "category": "Examples", "author": "you", "license": "GPL-2.0-or-later",
 "description": "Registers a handler on TICK: the smallest mod that runs code each frame.",
 "target": {"device": "m8-model02", "product": "M8 Model:02", "firmware": "6.6.2A",
            "bin_sha256": "fbc15296...", "payload_sha256": "...", "payload_len": 2011136},
 "requires": ["core"], "conflicts": [], "core": "0.1",
 "sites": [
  {"addr": "0x60000460", "len": 2, "kind": "code", "stock_sha256": "...", "new": "7047"}
 ],
 "subscribe": [{"event": "TICK", "handler": "0x60000461", "order": 50}],
 "resources": {"names": []},
 "signature": null
}
```

## Fields

| field | |
|---|---|
| `m8mod` | the format: `2`. (Format-1 files say `"m8mod_format": 1`; they still load, below.) |
| `id`, `version` | the mod's name (kebab-case) and version; `requires`/`conflicts` name other ids |
| `title`, `description`, `category`, `author` | for people |
| `license` | an SPDX identifier for the mod's own bytes, e.g. `GPL-2.0-or-later` |
| `target` | the stock firmware: `device` (`m8-model02` or `m8-model01`), `product`, `firmware` (the version as the unit shows it), `bin_sha256` (the whole stock `.bin` as Dirtywave publishes it), and optionally `payload_sha256` and `payload_len` (the flash image inside the M8FW container) |
| `sites` | changes to the stock flash image (below) |
| `events` | the core only: the events it installs, e.g. `["TICK"]`; a mod may only subscribe to an event some selected mod provides |
| `subscribe` | handlers this mod registers: `[{"event", "handler", "order"}]` (below) |
| `core` | for a mod that requires the core: the oldest core version it works with, e.g. `"0.1"` |
| `resources` | `names`: named resources it claims exclusively, such as `fx:cmd:0x4e` or `settings:MY ROW`; two selected mods may not claim the same name |
| `requires`, `conflicts` | lists of mod ids |
| `signature` | reserved; `null` |

## Sites

A **site** is a same-size change to the stock flash image (addresses as in the image at `0x60000000`):

```json
{"addr": "0x600ae052", "len": 4, "kind": "code", "stock_sha256": "...", "new": "f752f9f9"}
```

- `stock_sha256` is the sha256 of the `len` stock bytes at `addr`; the build refuses a site whose stock bytes
  do not match, so a mod can only apply to the firmware it was made for.
- `new` is a hex string, or a list of parts: `["hex", "..."]` and `["stock", "0x...", n]` (n stock bytes
  copied from the user's image). The parts must add up to `len`.
- `kind` is `code` (whole Thumb instructions) or `data`.
- Sites are same-size: nothing moves. New code goes in free space (the code caves listed in `docs/CORE.md`).
- No two sites, from any selected mods, may overlap.

## Events and subscribe

The core installs a hook dispatcher and a table of handlers in its cave (`docs/CORE.md`). A mod adds a
handler by subscribing:

```json
"subscribe": [{"event": "TICK", "handler": "0x60000461", "order": 50}]
```

- `event` is a name from `dirtyloader/core/abi.py` (`TICK` today; `BOOT`, `RENDER`, `AUDIO_BLOCK` and `INPUT`
  have ids but no installed site yet).
- `handler` is the Thumb address of the mod's handler (bit 0 set), usually code the mod's own sites place in a
  cave. It is called with the event id in `r0` and must follow the AAPCS (preserve r4-r11).
- `order` (0-255, default 50) sorts handlers on the same event, lower first; ties go by mod id. The linker gives
  each subscription its own table slot, so several mods share one event instead of fighting over a call site.

## Building

`python -m dirtyloader build <stock.bin> -m a.m8mod -m b.m8mod -o out.bin` checks the stock file's hash,
every mod's target, `requires`, `conflicts`, `core`, resources and site overlaps, applies the sites, installs
the subscriptions, recomputes both M8FW CRCs and re-reads the result before writing it. Flash the output as
any firmware update: copy it to the SD card and use PROJECT > SYSTEM SETTINGS > FIRMWARE UPDATE.

## Source folders

You don't write a `.m8mod` by hand. A mod is a folder with a `mod.json` and its assembly sources, and
`mkmod` compiles it against your stock firmware:

```
python -m dirtyloader mkmod examples/hello-tick --stock stock.bin -o hello-tick.m8mod
```

`examples/hello-tick/` and `mods/core/` are the worked examples. A `mod.json`:

```json
{
 "m8mod_source": 1,
 "id": "hello-tick", "version": "1.0.0", "title": "Hello tick",
 "category": "Examples", "license": "GPL-2.0-or-later", "author": "you",
 "description": "...",
 "device": "m8-model02", "firmware": "6.6.2A",
 "requires": ["core"], "core": "0.1",
 "cave": "0x60000460",
 "handlers": [{"event": "TICK", "source": "hello.s", "order": 60}]
}
```

- `cave` is the base of this mod's code in a free code cave (`docs/CORE.md` lists them).
- Each `handlers[]` entry names a Thumb assembly file (keystone syntax; `//`, `@` and `/* */` comments are
  stripped). `mkmod` assembles it at the next free spot in the cave, makes a hash-guarded `code` site for it,
  and adds a `subscribe` entry whose `handler` is that address. A handler gets the event id in `r0` and must
  preserve r4-r11.
- The core's folder sets `"build": "core"` instead of `cave`/`handlers`: it is built by
  `dirtyloader.core.builder` from the firmware's bindings file.

`lint` checks a built `.m8mod` (and, with `--stock`, links it with the core):

```
python -m dirtyloader lint hello-tick.m8mod --stock stock.bin --with core.m8mod
```

Built `.m8mod` files are artifacts and are not committed; the sources are. Regenerate with `mkmod`.

## Format 1

The first format (`"m8mod_format": 1`) stored the stock bytes themselves in each patch's `expect`. It still
loads: each patch becomes a format-2 site whose `stock_sha256` is the hash of `expect`, and `hooks` become
`subscribe` entries. `save` always writes format 2. Do not publish format-1 files: they carry stock bytes.
