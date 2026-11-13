# The dirtyloader Core

The **Core** is injected firmware infrastructure that lets several mods hook the
same piece of M8 firmware without fighting over the bytes. It is the direct
analogue of Elekloader's *core mod + event bus*: instead of each mod overwriting
a call site (and the last one winning), mods **register handlers** against named
**events**, and the Core's **dispatcher** runs every registered handler at each
hooked site.

In dirtyloader terms the Core ships as a special mod with `id: "core"`; other
mods set `requires: ["core"]` (the linker already enforces that).

```
   stock call site                 Core dispatcher (in a code cave)
   ───────────────                 ────────────────────────────────
   ... bl original  ──patched──►   save context
                                   for each entry in hook table where
                                       entry.event == THIS_EVENT and enabled:
                                       call entry.handler
                                   run the relocated original instruction(s)
                                   restore context, return
```

## What we already know (6.6.2A Model02)

Established by the RE pass (`m8loader.re.boot`, `m8loader.re.caves`):

| Fact | Value | Why it matters for the Core |
|---|---|---|
| Integrity | two zlib **CRC-32s only**, no signature | the loader recomputes them, so a Core-patched image boots |
| Image | flat FlexSPI image @ `0x60000000`, Thumb | standard Cortex-M7; capstone/Ghidra analyze it cleanly |
| Entry | `0x60001649` (ResetHandler) | the `BOOT` event hooks late in startup, after init |
| HAB `csf` | points at `0x601EA400`, which is **all zeros** | no real signature present; unsigned image (confirm on HW) |
| Biggest cave | `0x60000200`, **3584 B** of `0xFF` (FCFB page tail) | home for the dispatcher + handler table |
| Spare caves | `0x6000102C` (980 B), `0x601EA400` (3072 B) | overflow / per-mod trampolines |
| Total free | ~12 KB across 12 caves ≥256 B | **tight** — code budget is the main constraint |

The provisional memory layout and event ids are in
[`m8loader/core/abi.py`](../m8loader/core/abi.py).

## Design

### 1. Reserved region & table
The Core occupies `CORE_REGION_ADDR` (`0x60000200`). Layout:

```
+0x000  CORE_MAGIC  "DLCORE\0\1"      (detect + version)
+0x008  table_count : u16
+0x00A  dispatcher_addr : u32         (so mods can call it / verify)
+0x010  hook table: MAX_HOOKS × { event_id:u16, flags:u16, handler:u32 }
...     dispatcher code (Thumb)
```

### 2. Hooking mechanism (detour + trampoline)
At a chosen site we overwrite one 32-bit Thumb instruction (typically a `BL`/
`B.W`) with a branch to a per-site **trampoline** in a cave. The trampoline:
1. branches into the shared dispatcher with the event id,
2. the dispatcher calls each registered handler,
3. executes the **relocated** original instruction (fixed up for its new PC),
4. returns to just after the patched site.

Thumb specifics the Core builder must handle: 2- vs 4-byte instruction
boundaries, PC-relative operands in the relocated instruction, and preserving
`lr` across the detour. `B.W`/`BL` reach ±16 MB — easily enough to reach the
caves from anywhere in the 2 MB image.

### 3. Events & registration
`abi.Event` fixes the numeric event ids (stable ABI). The *addresses* each event
hooks are **bound per firmware** after Ghidra identifies the functions (main
loop, display render, audio block, input) and recorded in the Core mod's own
manifest — not hard-coded in the library. A mod registers by adding a hook-table
entry (event id + its handler address); the Core mod installs the dispatcher and
the empty table.

### 4. Loader integration
- The Core is a normal `.m8mod` (`id: "core"`) pinned to a stock sha256.
- Mods depend on it via `requires: ["core"]`.
- The linker's overlap/conflict/expect checks already prevent two mods from
  corrupting the table or the same trampoline slot.
- A future `core`-aware step assigns handler-table slots so mods don't collide.

## Build order

1. **Function map** — Ghidra headless (`m8loader.re.ghidra_run`) → candidate
   hook targets: main loop, display render, audio block, input handler. *(running)*
2. **Pick the first hook** — simplest useful event (likely `RENDER` or `TICK`)
   and a trivial demo handler (e.g. draw a marker / toggle a byte).
3. **Assemble the dispatcher** in Thumb (keystone) into `0x60000200`; patch one
   call site to detour through it; recompute CRCs via `m8fw`.
4. **Validate on a spare Teensy 4.1 + M8 Headless firmware** — never on a real M8
   until proven. The HalfKay bootloader is untouched, so stock always recovers.
5. **Generalise** — multi-handler table, slot allocation, the `requires: ["core"]`
   wiring, and a mod-author macro for "register handler for event X".

## Open risks
- **Code budget.** ~12 KB of caves total; the dispatcher must be compact and
  per-mod code has to fit. Resizable images (growing the payload) are a possible
  future escape hatch but change the container length field.
- **Hook-point stability.** Addresses move every firmware release; the Core mod
  is pinned per build and must be re-derived each version.
- **Thumb relocation correctness** of the displaced original instruction.
- **Hardware enforcement** of HAB/csf — believed inert on open Teensy; must be
  confirmed by actually flashing.
