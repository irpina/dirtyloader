# The UI framework: views, input, touch, text (static hunt, M8 6.6.2A Model02)

How the M8's screens are structured, switched, fed input and drawn. Found with the whole-image switch census
([static-m8-switches.md](static-m8-switches.md)), the vtable finder (`python -m dirtyloader.re.vtables`) and
targeted Ghidra decompiles. Addresses are flash addresses (base `0x60000000`); "true entry" addresses come from
vtable pointers and are exact. Nothing here has run on hardware.

## The UI context object

One global UI object (held in literal pools such as `_DAT_60081d48`, `DAT_6004c358`) carries the view state:

| field | meaning | evidence |
|---|---|---|
| `+0x04` | **current view object** (pointer) | `set_view` stores the new view here, then calls through its vtable |
| `+0x15` | **current view id** (`0x00..0x1D`) | `set_view` writes it; the input router, touch engine and display driver all switch on it |
| `+0x17` | previous view id | `set_view` copies `+0x15` here first |
| `+0x2D` | navigation group (`0..4`) | second switch in `set_view` (below) |

## `set_view(ui, id)` — the view manager — `0x6004C13C` (S1)

1. calls the **old** view's vtable `+0x14` (leave);
2. `prev = cur; cur = id` (`ui+0x17 ← ui+0x15`, `ui+0x15 ← id`);
3. a 30-way `switch(id)` (ids `0x00..0x1D`; **`7` is unused**) picks the view **singleton** for that id and
   stores it at `ui+4` (`9` additionally resets 8 per-track objects);
4. calls the **new** view's `+0x1C`, `+0x18`, then `+0x00` (enter);
5. maps the id to a navigation group `ui+0x2D`.

Navigation groups (S3 interpretation — the five columns of the SONG → CHAIN → PHRASE → INSTRUMENT → TABLE
row): `0 ← {0, 6}`, `1 ← {2, 6*}`, `2 ← {1, 3, 0x13}`, `3 ← {5, 0x18, 0x16*}`, `4 ← {4, 0x16*}` (`*` depends
on a mode byte in that view). So plausibly **`0` Song, `2` Chain, `4` Table, `5` Instrument**; the others are
unnamed until confirmed on hardware.

Callers seen: `0x60050AB8` (picks an item, then `set_view(ui, 0x19)`) and `0x6004F7DC` (a view's input
handler navigating).

**Hook:** `ev_view_change` at `set_view` — observe navigation, veto it, or route a **new id** (e.g. `0x1E`) to a
mod-supplied view object. This is how a mod adds a whole screen (the KAOSS mode).

## The `View` interface — 8 virtual slots (S1 for `+0x08`, S2 otherwise)

C++ without RTTI: each vtable in flash is a `{0, 0}` header plus code pointers. 26 classes have exactly 8 slots
(the base `View`); 5 list-style views extend it to 32.

| slot | role | evidence |
|---|---|---|
| `+0x00` | enter / activate | view-specific; called last by `set_view` |
| `+0x04` | base default | `0x600A4358` in nearly every view (rarely overridden) |
| **`+0x08`** | **handle input action** `(this, action)` | **19 of 19** census input handlers sit here (below) |
| `+0x0C`, `+0x10` | view-specific | the draw/update candidates (not yet confirmed which) |
| `+0x14` | leave | called on the old view by `set_view` |
| `+0x18`, `+0x1C` | boolean queries | base defaults `0x600A4350/54`; tested by `set_view` and the display driver |

### Per-view input handlers (`+0x08`)

Each is `switch (action)` on an input-action code; the bound is the highest action that view handles.

| true entry | vtable | slots | actions |
|---|---|---|---|
| 0x6004F7DC | 0x601DF4B4 | 32 | 0..0x22 |
| 0x6005478C | 0x601DF6AC | 32 | 0..0x22 |
| 0x600619A8 | 0x601DF874 | 32 | 0..0x22 |
| 0x6007390A | 0x601E1290 | 32 | 0..0x22 |
| 0x600768AC | 0x601DF5F0 | 32 | 0..0x22 |
| 0x600539F4 | 0x601DFDC8 | 8 | 0..0x22 |
| 0x60071868 | 0x601DF57C | 8 | 0..0x22 |
| 0x600511A4 | 0x601E0BE8 | 8 | 0..0x21 |
| 0x6005BCD8 | 0x601E0564 | 8 | 0..0x21 |
| 0x6005DD14 | 0x601DF554 | 8 | 0..0x21 |
| 0x60063D58 | 0x601DFD78 | 8 | 0..0x21 |
| 0x6004EA1C | 0x601DF93C | 8 | 0..0x18 |
| 0x60064958 | 0x601E0FD8 | 8 | 0..0x18 |
| 0x60075450 | 0x601E0CB8 | 8 | 0..0x18 |
| 0x60058F48 | 0x601E0C40 | 8 | 0..0x30 |
| 0x6005A47C | 0x601E0C68 | 8 | 0..0x30 |
| 0x60066BBC | 0x601E0654 | 8 | 0..0x14 |
| 0x600749E2 | 0x601DF5A4 | 8 | 1..0x18 |
| 0x60077BFC | 0x601E067C | 8 | 1..0x18 |

The 32-slot handlers call their own `+0x5C`, `+0x64`, `+0x74` (list behaviour: cursor, row edit, …).

**Hook:** `ev_input` per view by wrapping slot `+0x08` of a view's vtable (copy the vtable to RAM/cave, swap
the pointer in the view singleton), or globally upstream at the router `0x6004C6C8`
([static-m8-loop.md](static-m8-loop.md)), which runs just before the display flush and special-cases action
`0xE4` except in views `{0x05, 0x0C, 0x11, 0x14, 0x16, 0x1B, 0x1D}`.

## The touch / gesture engine — `0x600A5E60` (S2)

Called unconditionally every `loop()` (this is **not** a sequencer engine — corrected). It polls the touch
state (`0x600A6B34`, `0x6007B6B4`), returns early unless `0x6007BB20` reports activity, then dispatches **by
current view** with float coordinates from a touch-state object:

| field | meaning |
|---|---|
| `+0x30`, `+0x34` | dx, dy (float) — `|dx|` vs `|dy|` picks the **dominant axis** |
| `+0x40`, `+0x44` | x, y (float) |
| `+0x50` | axis flag (`0` X, `1` Y); `0xFF` passed when below the motion threshold |
| `+0x53` | mode flag; `+0x5C` timestamp |

| view | handler | input |
|---|---|---|
| `0x05` | 0x600557B8 | x (scaled, 1-D) |
| `0x16` | 0x60058E64 | x (scaled, 1-D) |
| `0x19` | 0x60052470 | x, y |
| `0x12` | 0x60067744 | x, y, dominant axis |
| `{0x06, 0x0B, 0x0D, 0x16, 0x19, 0x1A}` (and 5) | 0x600898E0 | gesture with axis |
| other views | 0x600898E0 ×2, or 0x6008A178 / 0x60089C80 | — |

**Hook:** `ev_touch` at `0x600A5E60` (or per-view at a handler above) — the KAOSS mod's XY input. The
per-view handlers call the instrument / receiver event interface `+0x88/+0x90/+0x94` (next section).

## Text and value drawing

| function | what | conf |
|---|---|---|
| `0x6002E2A8` | glyph renderer: 91-case switch on ASCII `0x20..0x7A` (6.6 KB, 61 calls) | S2 |
| `0x6002FDEC` | second glyph renderer (same switch shape — a second font) | S2 |
| `0x60030ECC` | text-draw wrapper → `0x6002E2A8`; used by `loop()`'s tail and the formatter | S2 |
| `0x600785C0` | printf-style **value formatter**: walks a format string of codes `'b'..'x'` (`b` bool → one of two strings, `c` char, …) and draws each via `0x60030ECC` | S2 |

**Hook (draw):** wrap `0x60030ECC` for a text overlay, or `0x600785C0` to re-format parameter values (a
re-range mod showing new units).

## Instrument classes (confirmed)

Large vtables share **the same base methods at `+0x88`, `+0x90`, `+0x94`** (`0x6009B994`, `0x6009B99C`,
`0x6009B9A0`) and each overrides `+0xA0`. Each of the seven big ones has a method returning its engine name, which
names it (S1):

| vtable | slots | engine |
|---|---|---|
| `0x601DFE18` | 104 | WAVSYNTH |
| `0x601E0220` | 102 | MACROSYNTH |
| `0x601E07EC` | 103 | SAMPLER |
| `0x601DFBBC` | 109 | MIDI OUT |
| `0x601DF97C` | 102 | FMSYNTH |
| `0x601E0058` | 102 | HYPERSYNTH |
| `0x601E0A14` | 109 | EXTERNAL |
| `0x601E0E34` | 46 | NONE (empty instrument) |

The other 46-slot classes share the same base and are **MIDI / controller receivers**: Launchpad Pro
(`0x601E0D20`, `LAUNCHPAD CONNECTED`), and three MIDI-input/record modes (`0x601E0F18`, `0x601E103C`,
`0x601E10FC`; `OUT OF EMPTY PHRASES!`, `TRANSPOSE`). So `+0x88/+0x90/+0x94` belong to that shared **event
interface** (*corrected*: first read as a parameter interface). The real parameter interface is
`+0xBC`/`+0x0F8`/`+0x104`/`+0x108`/`+0x10C`, documented with the descriptor tables in
[static-m8-params.md](static-m8-params.md). Screen ids are named in [../FIRMWARE-MAP.md](../FIRMWARE-MAP.md) §8.

The instruments are the parameter/data model; the sound comes from separate `AudioStream` voice nodes whose
`update()` runs in ITCM from the audio interrupt ([../FIRMWARE-MAP.md](../FIRMWARE-MAP.md) §3–4) — which is
also why the sequencer is never reached from `loop()`: it is an audio-graph node too.

*Correction:* a 128-entry table at `0x601E9A38` (every entry `0x600ADF45`) was first logged as the IRQ vector
template. It is not: the RAM vector table is at **`0x2000C000`** (zero in the `.data` image, filled at boot).
`0x601E9A38` is some 128-entry default-callback table (128 = MIDI note/CC count — unconfirmed).
