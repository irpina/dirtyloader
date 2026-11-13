"""
Core builder: assemble the firmware-side Core (hook dispatcher + event-bus table)
into the reserved cave and emit it, plus the main-loop detour, as a `core.m8mod`.

Firmware-side layout, placed at abi.CORE_REGION_ADDR (0x60000200, the FCFB-page
cave):

    +0x000  magic "DLCORE\\0\\1"
    +0x008  u16 version, u16 max_hooks
    +0x00C  u32 reserved
    +0x010  hook table: 64 x {u16 event, u16 flags, u32 handler}   (512 B)
    +0x210  code: dispatch_handlers, tramp_tick, (bundled) demo_handler

Control flow once installed:

    main() @0x600AE052:  bl tramp_tick        (was: bl loop)
    tramp_tick:  push {lr}; r0 = TICK; bl dispatch_handlers; pop {lr}; b.w loop
    dispatch_handlers(r0=event):  for each enabled table entry matching event,
                                  blx handler(r0=event); then return
    loop() runs as before and returns into main via the preserved lr.

Handlers receive the event id in r0 and must follow AAPCS (preserve r4-r11).

Needs `pip install keystone-engine`. The core package stays importable without
it; only this builder requires it.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Tuple

from m8loader.m8fw import M8Firmware
from m8loader.m8mod import Mod, ModPatch
from m8loader.core import abi

try:
    import keystone as _ks
except ImportError:  # pragma: no cover
    _ks = None

REGION = abi.CORE_REGION_ADDR                               # 0x60000200
TABLE = REGION + 0x10                                       # 0x60000210
CODE = TABLE + abi.MAX_HOOKS * abi.HOOK_ENTRY_SIZE          # 0x60000410


def _asm(code: str, addr: int) -> bytes:
    if _ks is None:
        raise RuntimeError("keystone-engine not installed (pip install keystone-engine)")
    ks = _ks.Ks(_ks.KS_ARCH_ARM, _ks.KS_MODE_THUMB)
    enc, _ = ks.asm(code, addr)
    if enc is None:
        raise RuntimeError("keystone failed to assemble Core code")
    return bytes(enc)


@dataclass
class CoreImage:
    blob: bytes          # bytes to place at REGION
    tramp_tick: int      # address to detour the hook site to
    demo_handler: int    # address of the bundled demo handler
    dispatch: int = CODE


def assemble_code(loop_addr: int) -> Tuple[bytes, int, int]:
    """Assemble dispatch_handlers + tramp_tick + demo_handler. Returns
    (code_bytes, tramp_tick_addr, demo_handler_addr)."""
    dispatch = _asm(f"""
        push {{r4, r5, r6, r7, lr}}
        movw r4, #{TABLE & 0xFFFF}
        movt r4, #{(TABLE >> 16) & 0xFFFF}
        movs r5, #{abi.MAX_HOOKS}
    dh_loop:
        ldrh r6, [r4, #0]
        cmp  r6, #0
        beq  dh_next
        cmp  r6, r0
        bne  dh_next
        ldrh r6, [r4, #2]
        tst  r6, #{abi.FLAG_ENABLED}
        beq  dh_next
        ldr  r7, [r4, #4]
        cmp  r7, #0
        beq  dh_next
        push {{r0, r4, r5}}
        blx  r7
        pop  {{r0, r4, r5}}
    dh_next:
        adds r4, #{abi.HOOK_ENTRY_SIZE}
        subs r5, #1
        bne  dh_loop
        pop  {{r4, r5, r6, r7, pc}}
    """, CODE)

    tramp_addr = CODE + len(dispatch)
    tramp = _asm(f"""
        push {{lr}}
        movs r0, #{int(abi.Event.TICK)}
        bl   #{CODE}
        pop  {{lr}}
        b.w  #{loop_addr}
    """, tramp_addr)

    demo_addr = tramp_addr + len(tramp)
    demo = _asm("bx lr", demo_addr)  # placeholder: real handlers come from mods

    return dispatch + tramp + demo, tramp_addr, demo_addr


def build_region(loop_addr: int) -> CoreImage:
    code, tramp_addr, demo_addr = assemble_code(loop_addr)
    blob = bytearray()
    blob += abi.CORE_MAGIC                               # +0x00 (8)
    blob += struct.pack("<HH", 1, abi.MAX_HOOKS)         # +0x08 version, max
    blob += struct.pack("<I", 0)                         # +0x0C reserved
    assert len(blob) == 0x10

    table = bytearray(abi.MAX_HOOKS * abi.HOOK_ENTRY_SIZE)
    # pre-register the bundled demo handler in slot 0 (Thumb bit set for blx)
    struct.pack_into(abi.HOOK_ENTRY_FMT, table, 0,
                     int(abi.Event.TICK), abi.FLAG_ENABLED, demo_addr | 1)
    blob += table                                        # +0x10 .. +0x210
    assert len(blob) == 0x210

    blob += code
    if len(blob) > abi.CORE_REGION_SIZE:
        raise RuntimeError(f"Core blob {len(blob)} exceeds cave {abi.CORE_REGION_SIZE}")
    return CoreImage(blob=bytes(blob), tramp_tick=tramp_addr, demo_handler=demo_addr)


def build_core_mod(fw: M8Firmware, stock_sha256: str, hook_site: int, loop_addr: int) -> Mod:
    """Build the installable `core` mod: one patch writes the Core into the cave,
    one detours the main-loop call site to the trampoline."""
    img = build_region(loop_addr)

    region_off = REGION - fw.load_addr
    expect_region = bytes(fw.payload[region_off:region_off + len(img.blob)])
    if set(expect_region) not in ({0xFF}, set()):
        raise RuntimeError("Core cave is not empty (0xFF) in this firmware")

    site_off = hook_site - fw.load_addr
    orig = bytes(fw.payload[site_off:site_off + 4])
    detour = _asm(f"bl #{img.tramp_tick}", hook_site)
    if len(detour) != 4:
        raise RuntimeError(f"detour is {len(detour)} bytes, expected 4")

    patches = [
        ModPatch(addr=REGION, expect=expect_region, data=img.blob,
                 note="Core region: magic + hook table + dispatcher"),
        ModPatch(addr=hook_site, expect=orig, data=detour,
                 note=f"detour main-loop bl loop -> tramp_tick @0x{img.tramp_tick:08X}"),
    ]
    return Mod(
        id="core", name="dirtyloader Core", author="dirtyloader", version="0.1.0",
        description=("Hook dispatcher + event-bus table in the FCFB-page cave; "
                     "detours the main-loop call through a TICK trampoline. Ships "
                     "a bundled no-op demo handler pre-registered on TICK."),
        target={"model": fw.model, "stock_sha256": stock_sha256},
        patches=patches,
    )
