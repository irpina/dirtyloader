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

import hashlib
import os
import struct
from dataclasses import dataclass
from typing import Tuple

from dirtyloader.m8fw import M8Firmware
from dirtyloader.m8mod import Mod, Site, make_target
from dirtyloader.core import abi

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

    sites = [
        Site.from_bytes(REGION, expect_region, img.blob, "code",
                        "Core region: magic + hook table + dispatcher"),
        Site.from_bytes(hook_site, orig, detour, "code",
                        f"detour main-loop bl loop -> tramp_tick @0x{img.tramp_tick:08X}"),
    ]
    return Mod(
        id="core", version=CORE_VERSION, title="dirtyloader Core", author="dirtyloader",
        category="Core", license="GPL-2.0-or-later",
        description=("Hook dispatcher + event-bus table in the FCFB-page cave; "
                     "detours the main-loop call through a TICK trampoline. Ships "
                     "a bundled no-op demo handler pre-registered on TICK."),
        target=make_target(fw, stock_sha256), events=["TICK"], sites=sites,
        resources={"names": ["core:hook-table", "core:region"]},
    )


CORE_VERSION = "0.1.0"
CORE02_VERSION = "0.2.0"


# ================================================================ core 0.2
# The hook bus proper (docs/CORE-EVENTS.md): one dispatcher that passes the site's arguments to every handler
# in table order (the linker fills the table sorted by `order`, then mod id), "take" semantics for int events,
# and three kinds of site, each bound per firmware in bindings/<fw>.json under "core":
#
#   call_pre   a `bl target` whose callee gets the event first:  handlers(r0-r3) -> taken? return 0 : target()
#   call_post  a `bl target` followed by the event:               target(); handlers()
#   entry      a function's first instruction(s) become `b.w stub`:  handlers(r0-r3, s0) -> taken? return 0 :
#              the relocated prologue, then the rest of the function
#
# Dispatcher contract: ip = event id | TAKE (bit 16); r0-r3 and s0 are the handlers' arguments; returns r0 =
# the taking handler's nonzero result, else 0; r1-r3 are clobbered, s0 is preserved. Every frame it pushes is
# a multiple of 8 bytes, so handlers see an AAPCS-aligned stack whenever the hooked site had one.

TAKE = 0x10000
KINDS02 = ("call_pre", "call_post", "entry", "itcm_entry")


RAM_MAGIC = 0x33524C44          # "DLR3": core 0.3's table in ITCM is live (core03.c sets it after loading)


def _dispatch02_asm(table: int, slots: int, ram: int = 0) -> str:
    """With `ram` (core 0.3), the dispatcher walks the table core03.c builds in ITCM once its magic is set,
    and the flash table until then."""
    pick = f"""
        movw  r9, #{ram & 0xFFFF}
        movt  r9, #{ram >> 16}
        ldr   r10, [r9]
        movw  r0, #{RAM_MAGIC & 0xFFFF}
        movt  r0, #{RAM_MAGIC >> 16}
        cmp   r10, r0
        bne   d_flash
        ldr   r10, [r9, #4]
        add.w r9, r9, #8
        cmp   r10, #0
        beq   d_none
        b     d_loop
    d_flash:""" if ram else ""
    return f"""
        push.w {{r3, r4, r5, r6, r7, r8, r9, r10, r11, lr}}
        mov   r8, ip
        mov   r4, r0
        mov   r5, r1
        mov   r6, r2
        mov   r7, r3
        vmov  r11, s0{pick}
        movw  r9, #{table & 0xFFFF}
        movt  r9, #{table >> 16}
        mov.w r10, #{slots}
    d_loop:
        ldrh  ip, [r9]
        uxth  r0, r8
        cmp   ip, r0
        bne   d_next
        ldrh  ip, [r9, #2]
        tst   ip, #{abi.FLAG_ENABLED}
        beq   d_next
        ldr   ip, [r9, #4]
        cmp   ip, #0
        beq   d_next
        mov   r0, r4
        mov   r1, r5
        mov   r2, r6
        mov   r3, r7
        vmov  s0, r11
        blx   ip
        tst   r8, #{TAKE}
        beq   d_next
        cmp   r0, #0
        bne   d_done
    d_next:
        add.w r9, r9, #{abi.HOOK_ENTRY_SIZE}
        subs  r10, #1
        bne   d_loop
    d_none:
        movs  r0, #0
    d_done:
        vmov  s0, r11
        pop.w {{r3, r4, r5, r6, r7, r8, r9, r10, r11, pc}}
    """


def _ev_word(event: int, takeable: bool) -> int:
    return int(event) | (TAKE if takeable else 0)


def _set_ip(word: int) -> str:
    return f"movw ip, #{word & 0xFFFF}\n" + (f"movt ip, #{word >> 16}\n" if word >> 16 else "")


def _md():
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
    md.detail = True
    return md


def _decode_bl(fw: M8Firmware, at: int) -> int:
    off = fw.addr_to_offset(at)
    ins = next(_md().disasm(bytes(fw.payload[off:off + 4]), at), None)
    if ins is None or ins.mnemonic != "bl" or ins.size != 4:
        raise RuntimeError(f"0x{at:08X} is not a 4-byte bl in this firmware")
    return int(ins.op_str.lstrip("#"), 16)


def relocate_prologue(fw: M8Firmware, fn: int, need: int = 4, before: int = 0) -> Tuple[str, int]:
    """Assembly that does what the first >= `need` bytes of `fn` do, from anywhere, and how many bytes it covers.
    Plain instructions are copied; `ldr rX, [pc, #imm]` becomes a movw/movt of the literal's value. Anything
    else that reads the pc, any branch, or a branch elsewhere in the function back into the replaced bytes,
    is refused."""
    off = fw.addr_to_offset(fn)
    md = _md()
    lines, n = [], 0
    for ins in md.disasm(bytes(fw.payload[off:off + 16]), fn):
        if n >= need:
            break
        m, ops = ins.mnemonic, ins.op_str
        if m.startswith(("b", "cb", "tb", "it", "adr")) or "pc" in ops and not (m.startswith("ldr") and "[pc" in ops):
            raise RuntimeError(f"0x{ins.address:08X} {m} {ops}: cannot relocate")
        if m in ("ldr", "ldr.w") and "[pc" in ops:
            reg = ops.split(",")[0].strip()
            imm = int(ops.split("#")[-1].rstrip("]"), 16)
            lit = ((ins.address + 4) & ~3) + imm
            val = struct.unpack_from("<I", fw.payload, fw.addr_to_offset(lit))[0]
            lines += [f"movw {reg}, #{val & 0xFFFF}", f"movt {reg}, #{val >> 16}"]
        else:
            lines.append(f"{m} {ops}")
        n += ins.size
    if n < need:
        raise RuntimeError(f"0x{fn:08X}: could not decode {need} bytes")
    # nothing in the next 1 KB may branch into the bytes we replace (except to the entry itself); for a site inside
    # a function (`before`), nothing in the `before` bytes ahead of it either
    if before:
        for ins in md.disasm(bytes(fw.payload[off - before:off]), fn - before):
            if ins.mnemonic.startswith(("b", "cb")) and ins.op_str.startswith("#"):
                t = int(ins.op_str.lstrip("#"), 16)
                if fn < t < fn + n:
                    raise RuntimeError(f"0x{ins.address:08X} branches into the relocated bytes at 0x{fn:08X}")
    for ins in md.disasm(bytes(fw.payload[off:off + 0x400]), fn):
        if ins.mnemonic.startswith(("b", "cb")) and ins.op_str.startswith("#"):
            t = int(ins.op_str.lstrip("#"), 16)
            if fn < t < fn + n:
                raise RuntimeError(f"0x{ins.address:08X} branches into the relocated prologue of 0x{fn:08X}")
        if ins.mnemonic in ("bx", "pop", "pop.w") and ("lr" in ins.op_str or "pc" in ins.op_str):
            break
    return "\n".join(lines), n


@dataclass
class Core02:
    blob: bytes                     # the whole region (header + table + code)
    sites: list                     # [(addr, new_bytes, note)]
    stubs: dict                     # event name -> stub address
    dispatch: int


VENEER_TABLE = REGION + abi.CORE_REGION_SIZE - 0x84          # core 0.3: count, then (itcm address, target) x 16
MAX_VENEERS = 16


def build_core02(fw: M8Firmware, bindings: dict, ram: int = 0, early: int = 0, boot: int = 0,
                 layout: int = 2, calls_before: dict = None, itcm_load: int = 0, veneers_at: int = 0) -> Core02:
    """Assemble core 0.2 for one firmware from its bindings' "core" sites. core 0.3 passes the address of its
    ITCM table (`ram`) and of core03.c's `early` (before setup) and `boot` (after setup, before ev_boot). `calls_before`
    maps the address of a `bl` to a function to call first (core 0.3's loader, inside setup())."""
    from dirtyloader.core.abi import EVENTS, by_name
    code = bytearray()
    pc = CODE

    def emit(asm: str) -> int:
        nonlocal pc
        at = pc
        b = _asm(asm, at)
        code.extend(b)
        pc += len(b)
        if pc & 3:                                   # keep stubs word-aligned
            code.extend(b"\x00\xbf")
            pc += 2
        return at

    dispatch = emit(_dispatch02_asm(TABLE, abi.MAX_HOOKS, ram))
    sites, stubs, veneers = [], {}, []
    for name, s in bindings["core"].items():
        ev = by_name(name.split("@")[0])                 # "MOD_APPLY@FM": one event, several sites
        take = EVENTS[ev].takeable
        word = _ev_word(ev, take)
        at = int(s["patch_at"], 16)
        kind = s["kind"]
        if kind == "call_pre":
            target = _decode_bl(fw, at)
            if "target" in s and int(s["target"], 16) != target:
                raise RuntimeError(f"{name}: bl at 0x{at:08X} calls 0x{target:08X}, bindings say {s['target']}")
            stub = emit(f"""
                push {{r0, r1, r2, r3, r4, lr}}
                sub  sp, #8
                {_set_ip(word)}
                bl   #{dispatch}
                add  sp, #8
                cmp  r0, #0
                bne  taken
                pop  {{r0, r1, r2, r3, r4, lr}}
                b.w  #{target}
            taken:
                movs r0, #0
                add  sp, #16
                pop  {{r4, pc}}
            """)
            new = _asm(f"bl #{stub}", at)
        elif kind == "call_post":
            target = _decode_bl(fw, at)
            if "target" in s and int(s["target"], 16) != target:
                raise RuntimeError(f"{name}: bl at 0x{at:08X} calls 0x{target:08X}, bindings say {s['target']}")
            pre = f"bl #{early}" if early and ev == by_name("BOOT") else ""
            post = f"bl #{boot}" if boot and ev == by_name("BOOT") else ""
            stub = emit(f"""
                push {{r4, lr}}
                {pre}
                bl   #{target}
                {post}
                {_set_ip(word)}
                bl   #{dispatch}
                pop  {{r4, pc}}
            """)
            new = _asm(f"bl #{stub}", at)
        elif kind == "entry":
            prologue, n = relocate_prologue(fw, at)
            stub = emit(f"""
                push {{r0, r1, r2, r3, r4, lr}}
                sub  sp, #8
                {_set_ip(word)}
                bl   #{dispatch}
                add  sp, #8
                cmp  r0, #0
                bne  taken
                pop  {{r0, r1, r2, r3, r4, lr}}
                {prologue}
                b.w  #{at + n}
            taken:
                movs r0, #0
                add  sp, #16
                pop  {{r4, pc}}
            """)
            new = _asm(f"b.w #{stub}", at)
            new += b"\x00\xbf" * ((n - len(new)) // 2)        # pad a longer relocation with nops
        elif kind == "itcm_entry":
            # ITCM code (the audio thread and the sequencer) runs at 0x0000xxxx, out of reach of flash: the site
            # branches to a veneer in the ITCM tail (core_early writes it), the veneer to the flash stub, and the
            # stub back into ITCM with bx. `patch_at` is the run address; the bytes are patched in the load image.
            if not (itcm_load and veneers_at):
                raise RuntimeError(f"{name}: an itcm_entry site needs the ITCM load base and a veneer area")
            if len(veneers) >= MAX_VENEERS:
                raise RuntimeError("too many ITCM sites for the veneer table")
            run = at
            load = itcm_load + run
            prologue, n = relocate_prologue(fw, load)
            back = (run + n) | 1
            stub = emit(f"""
                push {{r0, r1, r2, r3, r4, lr}}
                sub  sp, #8
                {_set_ip(word)}
                bl   #{dispatch}
                add  sp, #8
                cmp  r0, #0
                bne  taken
                pop  {{r0, r1, r2, r3, r4, lr}}
                {prologue}
                movw ip, #{back & 0xFFFF}
                movt ip, #{back >> 16}
                bx   ip
            taken:
                movs r0, #0
                add  sp, #16
                pop  {{r4, pc}}
            """)
            ven = veneers_at + 8 * len(veneers)
            veneers.append((ven, stub | 1))
            new = _asm(f"b.w #{ven}", run)
            new += b"\x00\xbf" * ((n - len(new)) // 2)
            at = load
        elif kind == "itcm_mid":
            # ITCM code, inside a function: registers, flags and s0-s15 are live, so the stub keeps them all and
            # returns through a stack slot. "args" says where the handler's r0-r3 come from (a register or
            # "#n"); "taken_to" (takeable events) is where a taken event goes: the function's own epilogue,
            # which the stock reaches from the site with the stack as it is (checked: the replaced bytes are
            # followed by a conditional branch there).
            if not (itcm_load and veneers_at):
                raise RuntimeError(f"{name}: an itcm_mid site needs the ITCM load base and a veneer area")
            if len(veneers) >= MAX_VENEERS:
                raise RuntimeError("too many ITCM sites for the veneer table")
            run = at
            load = itcm_load + run
            prologue, n = relocate_prologue(fw, load, before=0x400)
            back = (run + n) | 1
            slot = {f"r{i}": 64 + 8 + 4 * i for i in range(4)}           # r0-r3 as pushed, past s0-s15 and sub sp
            moves = []
            for i, src in enumerate(s.get("args", ["r0", "r1", "r2", "r3"])):
                if src.startswith("#"):
                    moves.append(f"movw r{i}, #{int(src[1:], 0)}")
                elif src in slot:
                    moves.append(f"ldr r{i}, [sp, #{slot[src]}]")
                else:
                    moves.append(f"mov r{i}, {src}")
            def leave(to: int) -> str:
                return f"""
                    sub  sp, #8
                    str  r0, [sp]
                    movw r0, #{to & 0xFFFF}
                    movt r0, #{to >> 16}
                    str  r0, [sp, #4]
                    pop  {{r0, pc}}"""
            taken_to = int(s["taken_to"], 16) if "taken_to" in s else 0
            if take and not taken_to:
                raise RuntimeError(f"{name}: a takeable event inside a function needs taken_to")
            if taken_to:
                nxt = next(_md().disasm(bytes(fw.payload[fw.addr_to_offset(load + n):][:4]), run + n), None)
                if nxt is None or not nxt.mnemonic.startswith("b") or int(nxt.op_str.lstrip("#"), 16) != taken_to:
                    raise RuntimeError(f"{name}: the instruction after the site does not branch to {s['taken_to']}")
            stub = emit(f"""
                push  {{r0, r1, r2, r3, ip, lr}}
                vpush {{s0-s15}}
                sub   sp, #8
                {chr(10).join(moves)}
                {_set_ip(word)}
                bl    #{dispatch}
                add   sp, #8
                {"cmp r0, #0" if taken_to else ""}
                {"bne taken" if taken_to else ""}
                vpop  {{s0-s15}}
                pop   {{r0, r1, r2, r3, ip, lr}}
                {prologue}
                {leave(back)}
            {"taken:" if taken_to else ""}
                {"vpop {s0-s15}" if taken_to else ""}
                {"pop {r0, r1, r2, r3, ip, lr}" if taken_to else ""}
                {leave(taken_to | 1) if taken_to else ""}
            """)
            ven = veneers_at + 8 * len(veneers)
            veneers.append((ven, stub | 1))
            new = _asm(f"b.w #{ven}", run)
            new += b"\x00\xbf" * ((n - len(new)) // 2)
            at = load
        else:
            raise RuntimeError(f"{name}: unknown site kind {kind!r} (one of {KINDS02})")
        stubs[name] = stub
        sites.append((at, new, f"{ev.name} ({kind}) -> stub 0x{stub:08X}"))

    for at, fn in (calls_before or {}).items():
        target = _decode_bl(fw, at)
        stub = emit(f"""
            push {{r0, r1, r2, r3, r4, lr}}
            bl   #{fn}
            pop  {{r0, r1, r2, r3, r4, lr}}
            b.w  #{target}
        """)
        sites.append((at, _asm(f"bl #{stub}", at), f"loader call before 0x{target:08X} -> stub 0x{stub:08X}"))

    blob = bytearray(abi.CORE_MAGIC)
    blob += struct.pack("<HH", layout, abi.MAX_HOOKS)              # +0x08 core layout (2, 3), slots
    blob += struct.pack("<I", dispatch | 1)                        # +0x0C the dispatcher (Thumb)
    blob += bytes(abi.MAX_HOOKS * abi.HOOK_ENTRY_SIZE)             # empty table: the linker fills it in order
    blob += code
    if veneers:
        end = VENEER_TABLE - REGION
        if len(blob) > end:
            raise RuntimeError(f"core is {len(blob)} B; with ITCM veneers the region holds {end}")
        blob += bytes([0xFF]) * (end - len(blob))
        blob += struct.pack("<I", len(veneers)) + b"".join(struct.pack("<II", v, t) for v, t in veneers)
    if len(blob) > abi.CORE_REGION_SIZE:
        raise RuntimeError(f"core 0.2 is {len(blob)} B; the cave holds {abi.CORE_REGION_SIZE}")
    return Core02(blob=bytes(blob), sites=sites, stubs=stubs, dispatch=dispatch)


def build_core02_mod(fw: M8Firmware, stock_sha256: str, bindings: dict) -> Mod:
    img = build_core02(fw, bindings)
    region_off = fw.addr_to_offset(REGION)
    stock_region = bytes(fw.payload[region_off:region_off + len(img.blob)])
    if set(stock_region) - {0xFF}:
        raise RuntimeError("the core cave is not empty (0xFF) in this firmware")
    sites = [Site.from_bytes(REGION, stock_region, img.blob, "code", "core 0.2: magic, hook table, dispatcher, stubs")]
    for at, new, note in img.sites:
        o = fw.addr_to_offset(at)
        sites.append(Site.from_bytes(at, bytes(fw.payload[o:o + len(new)]), new, "code", note))
    events = list(dict.fromkeys(n.split("@")[0] for n in img.stubs))
    return Mod(
        id="core", version=CORE02_VERSION, title="dirtyloader core", author="dirtyloader", category="Core",
        license="GPL-2.0-or-later",
        description=("The hook bus: a dispatcher and a 64-slot handler table in the FCFB-page cave, with "
                     "sites for " + ", ".join(events) + ". Handlers get the site's arguments; int events can "
                     "be taken."),
        target=make_target(fw, stock_sha256, bindings.get("firmware", "")), events=events, sites=sites,
        resources={"names": ["core:hook-table", "core:region"]},
    )


def build_handler_mod(fw: M8Firmware, stock_sha256: str, mod_id: str, name: str,
                      cave_addr: int, event, handler_asm: str = "bx lr", order: int = 50) -> Mod:
    """A minimal mod that drops a handler into a free cave slot and subscribes it to `event`. The linker
    gives each subscription its own Core table slot, so several of these coexist on one event -- the whole
    point of the Core."""
    from dirtyloader.m8mod import event_name
    code = _asm(handler_asm, cave_addr)
    off = cave_addr - fw.load_addr
    stock = bytes(fw.payload[off:off + len(code)])
    if set(stock) not in ({0xFF}, set()):
        raise RuntimeError(f"{mod_id}: cave 0x{cave_addr:08X} is not empty (0xFF)")
    return Mod(
        id=mod_id, version="0.1.0", title=name, author="dirtyloader", category="Examples",
        license="GPL-2.0-or-later", description=f"Demo handler on {event_name(event)}.",
        target=make_target(fw, stock_sha256), requires=["core"], core="0.1",
        sites=[Site.from_bytes(cave_addr, stock, code, "code", f"{mod_id} handler")],
        subscribe=[{"event": event_name(event), "handler": cave_addr | 1, "order": order}],
    )


def build_asm_mod(fw: M8Firmware, stock_sha256: str, mod_id: str, title: str, cave: int, handlers,
                  description: str = "", core: str = "0.2", firmware: str = "") -> Mod:
    """A mod whose handlers are Thumb assembly placed one after another in a free (0xFF) cave.
    `handlers` is [(event, asm, order)]; each is subscribed with its own order."""
    from dirtyloader.m8mod import event_name
    code = bytearray()
    subs = []
    for event, asm, order in handlers:
        at = cave + len(code)
        code += _asm(asm, at)
        if len(code) & 3:
            code += b"\x00\xbf"
        subs.append({"event": event_name(event), "handler": at | 1, "order": order})
    off = fw.addr_to_offset(cave)
    stock = bytes(fw.payload[off:off + len(code)])
    if set(stock) - {0xFF}:
        raise RuntimeError(f"{mod_id}: cave 0x{cave:08X} is not empty (0xFF)")
    return Mod(
        id=mod_id, version="0.1.0", title=title, author="dirtyloader", category="Examples",
        license="GPL-2.0-or-later", description=description, target=make_target(fw, stock_sha256, firmware),
        requires=["core"], core=core, subscribe=subs,
        sites=[Site.from_bytes(cave, stock, bytes(code), "code", f"{mod_id} handlers")],
    )


# ================================================================ core 0.3
# core 0.2's hook bus plus the SD-card loader in dirtyloader/core/c/core03.c (docs/LOADER.md). The C is
# compiled with arm-none-eabi-gcc (dirtyloader.cc) and placed in free flash past the stock image; its state
# and the mods it loads live in the free ITCM tail. Bound per firmware by the bindings' "loader" block.
CORE03_VERSION = "0.5.0"
CORE03_SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "c", "core03.c")


def build_core03_mod(fw: M8Firmware, stock_sha256: str, bindings: dict) -> Mod:
    """core 0.3 for one firmware. Its loader lies past the stock image; dirtyloader.linker pads a headless
    image to fit."""
    stock = fw
    from dirtyloader import cc
    ld = bindings["loader"]
    c_at, ram, ram_end = (int(ld[k], 16) for k in ("c_at", "ram", "ram_end"))
    defines = {"CORE_FW_H": '"%s"' % ld["fw_header"], "CORE_RAM": f"0x{ram:08X}u",
               "CORE_RAM_END": f"0x{ram_end:08X}u", "CORE_FLASH_TABLE": f"0x{TABLE:08X}u",
               "CORE_FLASH_SLOTS": str(abi.MAX_HOOKS), "CORE_DISPATCH": f"0x{CODE | 1:08X}u",
               "CORE_VENEERS": f"0x{VENEER_TABLE:08X}u"}
    row = ld.get("settings_row")
    if row:
        defines["SETTINGS_MODS_Y"] = str(int(row["field_y"]))
    calls = {int(a, 16): c for a, c in ld.get("calls", {}).items()}   # a bl that calls core's C instead
    entries = ["core_early", "core_load", "core_boot", "core_serial", "core_key", "core_tick", "core_song_load",
               "core_song_save"] + [c["fn"] for c in calls.values()]
    c_img, syms = cc.build_fixed([CORE03_SOURCE], c_at, entries, defines)
    if c_at < fw.load_addr + len(fw.payload):
        raise RuntimeError(f"loader address 0x{c_at:08X} is inside the stock image")
    # SYSTEM SETTINGS gets a MODS row: a copy of its layout template with the row added, after the loader. The
    # copy names the stock rows by address (["stock", ...]), so no Dirtywave bytes are in the mod.
    t_at = t_len = 0
    if row:
        t_at = (c_at + len(c_img) + 15) & ~15
        t_len = int(row["attrs"], 16) + 24 * 40 + 1           # text template, gap, attribute template
    end = max(c_at + len(c_img), t_at + t_len)
    # past the image the flash is erased (0xFF): that is what the loader's sites hash-check against
    fw = M8Firmware(version=fw.version, load_addr=fw.load_addr,
                    payload=bytearray(fw.payload) + bytes([0xFF]) * (end - fw.load_addr - len(fw.payload)))
    load_at = int(ld["load_at"], 16)
    img = build_core02(fw, bindings, ram=ram, early=syms["core_early"], boot=syms["core_boot"], layout=3,
                       calls_before={load_at: syms["core_load"]}, itcm_load=int(ld.get("itcm_load", "0"), 16),
                       veneers_at=int(ld.get("veneers", "0"), 16))
    region_off = fw.addr_to_offset(REGION)
    stock_region = bytes(fw.payload[region_off:region_off + len(img.blob)])
    if set(stock_region) - {0xFF}:
        raise RuntimeError("the core cave is not empty (0xFF) in this firmware")
    sites = [Site.from_bytes(REGION, stock_region, img.blob, "code", "core 0.3: magic, hook table, dispatcher, stubs")]
    for at, new, note in img.sites:
        o = fw.addr_to_offset(at)
        sites.append(Site.from_bytes(at, bytes(fw.payload[o:o + len(new)]), new, "code", note))
    for at, c in calls.items():
        # the C function makes the call itself (its address is in the device header) and raises the event
        o = fw.addr_to_offset(at)
        new_bl = _asm(f"bl #{syms[c['fn']]}", at)
        if bytes(fw.payload[o:o + 2])[1] & 0xF8 != 0xF0:
            raise RuntimeError(f"0x{at:08X} is not a bl")
        sites.append(Site.from_bytes(at, bytes(fw.payload[o:o + 4]), new_bl, "code",
                                     f"{c['event']}: bl -> {c['fn']} (core's C)"))
    o = fw.addr_to_offset(c_at)
    sites.append(Site.from_bytes(c_at, bytes(fw.payload[o:o + len(c_img)]), c_img, "code",
                                 f"core 0.3 loader ({len(c_img)} B, core03.c)"))
    if row:
        # The screen's text template is 24 rows of 40 characters; its attribute (colour) template follows at
        # +attrs. The copy is the stock one with row r replaced, its colours those of row `attr_like`.
        tpl, r, at_off = int(row["template"], 16), int(row["row"]), int(row["attrs"], 16)
        like = int(row["attr_like"])
        attr = tpl + at_off
        text = row["text"].ljust(40)[:40].encode("ascii")
        new = [["stock", f"0x{tpl:08x}", r * 40], ["hex", text.hex()],
               ["stock", f"0x{tpl + (r + 1) * 40:08x}", at_off - (r + 1) * 40],
               ["stock", f"0x{attr:08x}", r * 40],
               ["stock", f"0x{attr + like * 40:08x}", 40],
               ["stock", f"0x{attr + (r + 1) * 40:08x}", (24 - r - 1) * 40 + 1]]
        o = fw.addr_to_offset(t_at)
        sites.append(Site(addr=t_at, len=t_len, stock_sha256=hashlib.sha256(bytes(fw.payload[o:o + t_len])).hexdigest(),
                          new=new, kind="data", note="SYSTEM SETTINGS layout and colours with the MODS row"))
        # every literal that names the stock templates (the text's address, or the colours' at +attrs) now names
        # core's copy
        for lit_s in row["literals"]:
            lit = int(lit_s, 16)
            o = fw.addr_to_offset(lit)
            v = struct.unpack_from("<I", fw.payload, o)[0]
            if v not in (tpl, attr):
                raise RuntimeError(f"0x{lit:08X} names neither of the settings templates")
            sites.append(Site.from_bytes(lit, bytes(fw.payload[o:o + 4]), struct.pack("<I", t_at + v - tpl), "data",
                                         "SYSTEM SETTINGS: the templates are core's copy"))
    events = list(dict.fromkeys([n.split("@")[0] for n in img.stubs] + [c["event"] for c in calls.values()]))
    mod = Mod(
        id="core", version=CORE03_VERSION, title="dirtyloader core", author="dirtyloader", category="Core",
        license="GPL-2.0-or-later",
        description=("The hook bus (" + ", ".join(events) + ") and the SD-card loader: during setup() it loads "
                     "the mods listed in /dirtyloader/active.txt into free ITCM, with a crash guard; with a SERIAL site "
                     "it also takes mod uploads over USB (dirtyloader.unit)."),
        target=make_target(stock, stock_sha256, bindings.get("firmware", "")), events=events, sites=sites,
        subscribe=([{"event": "SERIAL", "handler": syms["core_serial"] | 1, "order": 0}]
                   if "SERIAL" in events else [])
                  + [{"event": ev, "handler": syms[fn] | 1, "order": 0}
                     for ev, fn in (("KEY", "core_key"), ("TICK", "core_tick"), ("SONG_LOAD", "core_song_load"),
                                    ("SONG_SAVE", "core_song_save")) if ev in events],
        resources={"names": ["core:hook-table", "core:region", "core:loader", "core:itcm-tail"]},
    )
    return mod
