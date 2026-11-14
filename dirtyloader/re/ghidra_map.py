"""
One-pass whole-program analysis: load the image into Ghidra with its *runtime*
memory map, seed every function entry the byte-level tools can find, analyze
once, save the project, and export the whole program to JSON for offline work.

Why each piece matters (learned the hard way on 6.6.2A):
  * ITCM code runs at 0x00000000, not at its flash load address -- calls into it
    from flash code are absolute veneers that resolve to nothing otherwise.
  * .data/.rodata runs in DTCM at 0x20000000 -- the parameter tables, labels and
    vtables are referenced there and nowhere else.
  * Ghidra's auto-analysis misses code reached only through vtables, function
    pointers or computed calls; vtable slots, code pointers in data and
    post-return `push` prologues recover it.
  * Analyzing once and saving the project avoids re-importing per question.

Output JSON: {"memmap": {...}, "functions": [{entry, load, size, insns, fp,
callees, mmio, drefs, thunk}], ...}. Feed it to dirtyloader.re.fwmap.

Usage:
    python -m dirtyloader.re.ghidra_map <stock.bin> <workdir>
"""
from __future__ import annotations

import json
import os
import struct
import sys
import time

from dirtyloader.m8fw import M8Firmware
from dirtyloader.re.memmap import recover
from dirtyloader.re.vtables import find_vtables
from dirtyloader.re.ghidra_export import DEFAULT_GHIDRA, LANGUAGE, BINARY_LOADER

PROJECT = "m8fw_full"
PERIPH = (0x40000000, 0x42200000)
PPB = (0xE0000000, 0xE0100000)
OCRAM = (0x20200000, 0x20280000)


def xip_code_end(fw, mm, window: int = 64, min_frac: float = 0.15) -> int:
    """End of the main flash-resident code span: the first point after which a 16 KB window is
    under 15% code chunks. (Small-integer tables decode as plausible Thumb -- lsls/movs -- so the
    data region has scattered false "code" chunks; a density cliff is the robust boundary.)"""
    from dirtyloader.re.layout import classify
    kinds = classify(fw, 256)
    start = (mm.itcm.src + mm.itcm.size) if mm.itcm else fw.load_addr + 0x2000
    k0 = (start - fw.load_addr) // 256
    end = fw.load_addr + len(fw.payload)
    for k in range(k0, len(kinds)):
        w = kinds[k:k + window]
        if w and w.count("code") < min_frac * len(w) and kinds[k] != "code":
            # back off to just after the last code chunk before k
            j = k
            while j > k0 and kinds[j - 1] != "code":
                j -= 1
            end = fw.load_addr + j * 256
            break
    # the linker's long-branch veneer island sits right after .text; include it
    vs = [a for a, _t in veneers(fw) if a < end + 0x4000]
    return max(end, max(vs) + 8) if vs else end


VENEER = b"\x5f\xf8\x00\xf0"     # ldr.w pc, [pc, #-0] ; .word target


def veneers(fw):
    """(stub load address, target) for every linker long-branch veneer."""
    p = bytes(fw.payload)
    out, k = [], p.find(VENEER)
    while k != -1:
        if k % 2 == 0 and k + 8 <= len(p):
            out.append((fw.load_addr + k, struct.unpack_from("<I", p, k + 4)[0]))
        k = p.find(VENEER, k + 1)
    return out


def find_seeds(fw: M8Firmware, mm, xip_end: int):
    p = bytes(fw.payload)
    base = fw.load_addr
    itcm = mm.itcm
    xip_lo = (itcm.src + itcm.size) if itcm else base + 0x1400

    def code_runtime(v):
        return (itcm is not None and itcm.dest + 0x100 <= v < itcm.end) or xip_lo <= v < xip_end

    def hw_at_runtime(v, k=0):
        la = mm.to_load(v)
        if la is None:
            return None
        o = la - base + k
        return struct.unpack_from("<H", p, o)[0] if 0 <= o < len(p) - 1 else None

    def is_push(v):
        h = hw_at_runtime(v)
        if h is None:
            return False
        if (h & 0xFF00) == 0xB500:
            return True
        return h == 0xE92D and (hw_at_runtime(v, 2) or 0) & 0x4000

    seeds = {"veneer": set(), "vtable": set(), "pointer": set(), "prologue": set()}
    for stub, tgt in veneers(fw):
        seeds["veneer"].add(mm.to_runtime(stub))
        if code_runtime(tgt & ~1):
            seeds["veneer"].add(tgt & ~1)
    for vt in find_vtables(fw):
        for s in vt.slots:
            if code_runtime(s & ~1):
                seeds["vtable"].add(s & ~1)
    for off in range(0, len(p) - 3, 4):
        v = struct.unpack_from("<I", p, off)[0]
        if v & 1 and code_runtime(v & ~1) and is_push(v & ~1):
            seeds["pointer"].add(v & ~1)
    # post-terminator push prologues, in load space, then translated
    spans = [(xip_lo, xip_end)]
    if itcm:
        spans.append((itcm.src, itcm.src + itcm.size))
    for lo, hi in spans:
        for a in range(lo + 2, hi - 2, 2):
            h = struct.unpack_from("<H", p, a - base)[0]
            if not ((h & 0xFF00) == 0xB500 or (h == 0xE92D and struct.unpack_from("<H", p, a + 2 - base)[0] & 0x4000)):
                continue
            prev = struct.unpack_from("<H", p, a - 2 - base)[0]
            prev2 = struct.unpack_from("<H", p, a - 4 - base)[0] if a - 4 >= base else 0
            if (prev == 0x4770 or (prev & 0xFF00) == 0xBD00 or (prev & 0xF800) == 0xE000 or prev in (0x0000, 0xBF00)
                    or (prev2 == 0xE8BD and prev & 0x8000)):
                seeds["prologue"].add(mm.to_runtime(a))
    return seeds


def run(stock_path: str, workdir: str) -> str:
    t0 = time.time()
    fw = M8Firmware.from_file(stock_path, verify=True)
    mm = recover(fw)
    xip_end = xip_code_end(fw, mm)
    seeds = find_seeds(fw, mm, xip_end)
    allseeds = sorted(set().union(*seeds.values()))
    print("memmap: ITCM %s  .data %s  xip code end 0x%08X" % (
        mm.itcm and hex(mm.itcm.src), mm.data and hex(mm.data.src), xip_end))
    print("seeds: " + ", ".join("%s %d" % (k, len(v)) for k, v in seeds.items()) + "  (unique %d)" % len(allseeds))

    os.environ.setdefault("GHIDRA_INSTALL_DIR", DEFAULT_GHIDRA)
    import pyghidra
    pyghidra.start(verbose=False)
    import jpype
    from java.io import ByteArrayInputStream
    from ghidra.util.task import TaskMonitor
    mon = TaskMonitor.DUMMY

    os.makedirs(workdir, exist_ok=True)
    img = os.path.join(workdir, "m8full.bin")
    open(img, "wb").write(fw.payload)
    p = bytes(fw.payload)

    with pyghidra.open_program(img, project_location=workdir, project_name=PROJECT,
                               language=LANGUAGE, loader=BINARY_LOADER, analyze=False) as api:
        prog = api.getCurrentProgram()
        mem = prog.getMemory()
        space = prog.getAddressFactory().getDefaultAddressSpace()
        A = space.getAddress
        tx = prog.startTransaction("memory map")
        try:
            prog.setImageBase(A(fw.load_addr), True)
            # split the flash block so the ITCM / .data *load* images are not analysed as code twice
            for c in (mm.itcm, mm.data):
                if c is None:
                    continue
                for cut in (c.src, c.src + c.size):
                    blk = mem.getBlock(A(cut))
                    if blk is not None and blk.getStart().getOffset() != cut:
                        mem.split(blk, A(cut))
                lb = mem.getBlock(A(c.src))
                lb.setExecute(False)
                lb.setName("itcm_load" if c is mm.itcm else "data_load")

            def init_block(name, start, data, execute, write):
                arr = jpype.JArray(jpype.JByte)(data)
                b = mem.createInitializedBlock(name, A(start), ByteArrayInputStream(arr), len(data), mon, False)
                b.setRead(True)
                b.setWrite(write)
                b.setExecute(execute)

            if mm.itcm:
                c = mm.itcm
                init_block("ITCM", c.dest, p[c.src - fw.load_addr:c.src - fw.load_addr + c.size], True, False)
            if mm.data:
                c = mm.data
                init_block("DTCM_data", c.dest, p[c.src - fw.load_addr:c.src - fw.load_addr + c.size], False, True)
                top = mm.stack_top or 0x20050000
                mem.createUninitializedBlock("DTCM_bss", A(c.end), top - c.end, False)
            for name, (lo, hi) in (("OCRAM", OCRAM), ("PERIPH", PERIPH), ("PPB", PPB)):
                mem.createUninitializedBlock(name, A(lo), hi - lo, False)
        finally:
            prog.endTransaction(tx, True)
        print("memory set up (%.0fs); seeding %d functions..." % (time.time() - t0, len(allseeds)))

        listing = prog.getListing()
        fm = prog.getFunctionManager()
        tx = prog.startTransaction("seed")
        made = 0
        try:
            for s in allseeds:
                a = A(s)
                if fm.getFunctionAt(a) is not None:
                    continue
                try:
                    api.disassemble(a)
                    if api.createFunction(a, None) is not None:
                        made += 1
                except Exception:
                    pass
        finally:
            prog.endTransaction(tx, True)
        print("seeded %d new functions (%.0fs); analysing..." % (made, time.time() - t0))
        api.analyzeAll(prog)
        print("analysis done (%.0fs); exporting..." % (time.time() - t0))

        funcs = []
        for fn in fm.getFunctions(True):
            e = fn.getEntryPoint().getOffset()
            body = fn.getBody()
            callees, mmio, drefs = set(), set(), set()
            n = fp = 0
            for ins in listing.getInstructions(body, True):
                n += 1
                if ins.getMnemonicString().lower().startswith("v"):
                    fp += 1
                for r in ins.getReferencesFrom():
                    to = r.getToAddress().getOffset()
                    rt = r.getReferenceType()
                    if rt.isCall():
                        callees.add(to)
                    elif PERIPH[0] <= to < PERIPH[1] or to >= PPB[0]:
                        mmio.add(to)
                    elif not rt.isFlow():
                        drefs.add(to)
            thunk = None
            if fn.isThunk():
                t = fn.getThunkedFunction(True)
                if t is not None:
                    thunk = t.getEntryPoint().getOffset()
            funcs.append({"entry": e, "load": mm.to_load(e), "size": int(body.getNumAddresses()),
                          "insns": n, "fp": fp, "callees": sorted(callees), "mmio": sorted(mmio),
                          "drefs": sorted(drefs), "thunk": thunk})
        # no explicit save: open_program holds a transaction for the whole session and saves the
        # analysed program into the project on close -- `decompile()` reopens it without re-analysis

    out = os.path.join(workdir, "fwmap.json")
    json.dump({"firmware": os.path.basename(stock_path), "load_addr": fw.load_addr,
               "memmap": {"itcm": mm.itcm and vars(mm.itcm), "data": mm.data and vars(mm.data),
                          "stack_top": mm.stack_top, "vectors_ram": mm.vectors_ram,
                          "flexram": mm.flexram_config, "xip_code_end": xip_end},
               "seeds": {k: len(v) for k, v in seeds.items()},
               "functions": funcs}, open(out, "w"))
    print("exported %d functions -> %s (%.0fs total)" % (len(funcs), out, time.time() - t0))
    return out


def decompile(workdir: str, addrs, outdir: str = None) -> list:
    """Reopen the saved, already-analysed project (no re-import, no re-analysis) and decompile
    the given runtime addresses (functions are created where missing). Returns (entry, size, path)."""
    os.environ.setdefault("GHIDRA_INSTALL_DIR", DEFAULT_GHIDRA)
    import pyghidra
    pyghidra.start(verbose=False)
    from ghidra.app.decompiler import DecompInterface
    from ghidra.util.task import TaskMonitor
    outdir = outdir or os.path.join(workdir, "decomp")
    os.makedirs(outdir, exist_ok=True)
    img = os.path.join(workdir, "m8full.bin")
    out = []
    with pyghidra.open_program(img, project_location=workdir, project_name=PROJECT,
                               language=LANGUAGE, loader=BINARY_LOADER, analyze=False) as api:
        prog = api.getCurrentProgram()
        fm = prog.getFunctionManager()
        print("reopened project: %d functions" % fm.getFunctionCount())
        dec = DecompInterface()
        dec.openProgram(prog)
        for a in addrs:
            ad = api.toAddr(a)
            fn = fm.getFunctionAt(ad) or fm.getFunctionContaining(ad)
            if fn is None:
                api.disassemble(ad)
                fn = api.createFunction(ad, None)
            if fn is None:
                out.append((a, 0, None))
                continue
            res = dec.decompileFunction(fn, 180, TaskMonitor.DUMMY)
            code = res.getDecompiledFunction().getC() if res.decompileCompleted() else "// decompile failed"
            e = fn.getEntryPoint().getOffset()
            path = os.path.join(outdir, "%08X.c" % e)
            open(path, "w").write(code)
            out.append((e, int(fn.getBody().getNumAddresses()), path))
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 3 and a[0] == "decompile":
        for e, size, path in decompile(a[1], [int(x, 16) for x in a[2:]]):
            print("0x%08X  %5d B  %s" % (e, size, path))
    elif len(a) >= 2:
        run(a[0], a[1])
    else:
        sys.exit(__doc__ + "\n    python -m dirtyloader.re.ghidra_map decompile <workdir> <hex>...")
