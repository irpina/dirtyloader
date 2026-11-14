"""
Global C++ objects -> their classes.

The M8 keeps its screens, audio-graph nodes and instruments as global objects in
RAM (.bss). Their vptrs are written at boot by constructors, so nothing in the
image says "object 0x20015A8C is the SONG view". This recovers it statically.

Each function is walked linearly with a tiny register model (literal-pool loads,
movw/movt, mov, add/sub #imm; `this` = incoming r0, also when copied). Recorded,
in program order:
  * vptr stores: a known vtable address stored to [this + k] (str, strd, stm;
    pre- and post-indexed), or to a constant address (an inlined constructor);
  * constructor calls: `bl f` / tail-call `b.w f` with r0 = this + k, or with a
    constant r0 (a global object).
Constructors are resolved recursively (base vptr first, most-derived last), so a
constant `this` passed to a constructor names the object's class. Call targets
Ghidra never created as functions (tail-call-only constructors) are decoded too.

Usage:
    python -m dirtyloader.re.objects <stock.bin> <fwmap.json> [--kind view|audio|instrument|all]
"""
from __future__ import annotations

import argparse
import json
import struct
from collections import defaultdict
from typing import Dict, Tuple

from dirtyloader.m8fw import M8Firmware
from dirtyloader.re.memmap import recover
from dirtyloader.re.vtables import find_vtables

ARG0 = "ARG0"
_CLOBBER = ("r0", "r1", "r2", "r3", "ip", "r12", "lr")


def _imm(s: str):
    s = s.strip().lstrip("#").rstrip("]!")
    try:
        return int(s, 0)
    except ValueError:
        return None


def _mem(ops):
    """(base, offset, writeback) for memory operands starting at ops[0] = '[rB' or '[rB]'."""
    first = ops[0]
    b = first.lstrip("[").rstrip("]!")
    if first.endswith("]") or first.endswith("]!"):
        return b, 0, len(ops) > 1                       # [rB] or [rB], #post-index
    off = _imm(ops[1]) if len(ops) > 1 else 0
    return b, off or 0, ops[-1].endswith("!")


def scan(fw: M8Firmware, export: dict):
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
    p = bytes(fw.payload)
    base = fw.load_addr
    mm = recover(fw)
    vts = {mm.to_runtime(v.addr): v for v in find_vtables(fw)}
    funcs = {f["entry"]: f for f in export["functions"]}
    thunk = {e: f["thunk"] for e, f in funcs.items() if f.get("thunk")}
    events: Dict[int, list] = defaultdict(list)     # fn -> [("vt", off, vt) | ("call", g, off)]
    direct: list = []                               # [("vt", obj, vt, fn) | ("call", obj, g, fn)]
    seen = set()
    queue = list(funcs)
    # static initialisers are reached only through the .init_array (a table of function pointers), so
    # also walk every function a code pointer in the image points at
    # -- any Thumb code pointer, not only push-prologue ones: inline initialisers often start with ldr
    try:
        from dirtyloader.re.ghidra_map import xip_code_end
        xip_hi = xip_code_end(fw, mm)
    except Exception:
        xip_hi = base + len(p)
    itcm = mm.itcm
    xip_lo = (itcm.src + itcm.size) if itcm else base + 0x1400
    for off in range(0, len(p) - 3, 4):
        v = struct.unpack_from("<I", p, off)[0]
        a = v & ~1
        if v & 1 and ((itcm is not None and itcm.dest + 0x100 <= a < itcm.end) or xip_lo <= a < xip_hi):
            queue.append(a)

    def code_for(entry):
        f = funcs.get(entry)
        la = mm.to_load(entry)
        if la is None or not (base <= la < base + len(p)):
            return None
        size = f["size"] if f else 0x300
        return p[la - base:la - base + size], f is None, la

    def record_store(fn, regs, src, b, off):
        if not (src in regs and regs[src][0] == "C" and regs[src][1] in vts) or b not in regs:
            return
        kind, v = regs[b]
        if kind == ARG0:
            events[fn].append(("vt", v + off, regs[src][1]))
        else:
            direct.append(("vt", v + off, regs[src][1], fn))

    def record_call(fn, regs, tgt):
        tgt = thunk.get(tgt, tgt)
        r0 = regs.get("r0")
        if r0 and r0[0] == ARG0:
            events[fn].append(("call", tgt, r0[1]))
        elif r0 and r0[0] == "C" and 0x20000000 <= r0[1] < 0x20300000:
            direct.append(("call", r0[1], tgt, fn))
        else:
            return
        if tgt not in seen:
            queue.append(tgt)

    while queue:
        fn = queue.pop()
        if fn in seen:
            continue
        seen.add(fn)
        got = code_for(fn)
        if got is None:
            continue
        code, bounded, la = got
        delta = fn - la
        regs = {"r0": (ARG0, 0)}
        for i in md.disasm(code, fn):
            m = i.mnemonic.split(".")[0]
            ops = [o.strip() for o in i.op_str.split(",")]
            if bounded and ((i.mnemonic == "bx" and ops == ["lr"]) or (m == "pop" and "pc" in i.op_str)):
                break
            if m == "ldr" and "[pc" in i.op_str:
                imm = _imm(i.op_str.split("#")[-1]) if "#" in i.op_str else 0
                lo = ((i.address + 4) & ~3) + (imm or 0) - delta - base
                if 0 <= lo < len(p) - 3:
                    regs[ops[0]] = ("C", struct.unpack_from("<I", p, lo)[0])
                continue
            if m == "movw" and len(ops) == 2 and _imm(ops[1]) is not None:
                regs[ops[0]] = ("C", _imm(ops[1]))
                continue
            if m == "movt" and len(ops) == 2 and regs.get(ops[0], (None,))[0] == "C" and _imm(ops[1]) is not None:
                regs[ops[0]] = ("C", (regs[ops[0]][1] & 0xFFFF) | (_imm(ops[1]) << 16))
                continue
            if m in ("mov", "movs") and len(ops) == 2 and ops[1] in regs:
                regs[ops[0]] = regs[ops[1]]
                continue
            if m in ("add", "adds", "addw", "sub", "subs", "subw") and len(ops) == 3 and ops[1] in regs \
                    and _imm(ops[2]) is not None:
                kind, v = regs[ops[1]]
                regs[ops[0]] = (kind, v + _imm(ops[2]) * (1 if m.startswith("add") else -1))
                continue
            if m == "str" and len(ops) >= 2 and ops[1].startswith("["):
                b, off, wb = _mem(ops[1:])
                record_store(fn, regs, ops[0], b, off)
                if wb and b in regs:
                    step = _imm(ops[-1])
                    if step is not None:
                        kind, v = regs[b]
                        regs[b] = (kind, v + step)
                continue
            if m == "strd" and len(ops) >= 3 and ops[2].startswith("["):
                b, off, _wb = _mem(ops[2:])
                record_store(fn, regs, ops[0], b, off)
                record_store(fn, regs, ops[1], b, off + 4)
                continue
            if m in ("stm", "stmia", "stmea") and "{" in i.op_str:
                b = ops[0].rstrip("!")
                srcs = [r.strip() for r in i.op_str.split("{", 1)[1].split("}")[0].split(",")]
                for n, s in enumerate(srcs):
                    record_store(fn, regs, s, b, 4 * n)
                continue
            if m in ("bl", "blx") and ops and ops[0].startswith("#"):
                record_call(fn, regs, _imm(ops[0]))
                for r in _CLOBBER:
                    regs.pop(r, None)
                continue
            if i.mnemonic in ("b", "b.w") and ops and ops[0].startswith("#"):
                tgt = _imm(ops[0])
                if tgt in funcs or not (fn <= tgt < fn + len(code)):     # leaves this function: tail call
                    record_call(fn, regs, tgt)
                    if bounded:
                        break
                continue
            if ops and not m.startswith(("b", "c", "st", "it", "t", "push", "pop", "nop")):
                regs.pop(ops[0], None)

    memo: Dict[int, dict] = {}

    def resolve(fn, depth=0):
        fn = thunk.get(fn, fn)
        if fn in memo:
            return memo[fn]
        memo[fn] = {}
        out: dict = {}
        if depth < 12:
            for ev in events.get(fn, []):
                if ev[0] == "vt":
                    out[ev[1]] = ev[2]
                else:
                    for off, vt in resolve(ev[1], depth + 1).items():
                        out[ev[2] + off] = vt
        memo[fn] = out
        return out

    objects: Dict[int, Tuple[int, str]] = {}
    for ev in direct:                               # program order: later stores win (most-derived)
        if ev[0] == "vt":
            objects[ev[1]] = (ev[2], "inline in 0x%08X" % ev[3])
        else:
            for off, vt in resolve(ev[2]).items():
                objects[ev[1] + off] = (vt, "ctor 0x%08X from 0x%08X" % (ev[2], ev[3]))
    ctors = {fn: r for fn in events for r in [resolve(fn)] if r}
    return objects, ctors, vts


def kind_of(vt) -> str:
    n = len(vt)
    return "view" if n in (8, 32) else "instrument" if n >= 46 else "audio" if n <= 4 else "class"


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Map global C++ objects to their classes.")
    ap.add_argument("firmware")
    ap.add_argument("export")
    ap.add_argument("--kind", default="all")
    a = ap.parse_args(argv)
    fw = M8Firmware.from_file(a.firmware, verify=True)
    objects, ctors, vts = scan(fw, json.load(open(a.export)))
    print("constructors: %d; objects mapped: %d" % (len(ctors), len(objects)))
    for obj, (vt, how) in sorted(objects.items()):
        k = kind_of(vts[vt])
        if a.kind in ("all", k):
            print("0x%08X  %-10s vtable 0x%08X (%3d)  %s" % (obj, k, vt, len(vts[vt]), how))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
