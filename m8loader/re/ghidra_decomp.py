"""
Decompile chosen functions and walk their callers, for code-only site hunts
(the dirtyloader counterpart of the Elekloader hunt-kit's ghidra/decomp/).

Writes <workdir>/decomp/<entry>.c per function and <workdir>/decomp/callers.txt:
each function's callers, and the caller chains up to `loop()`/`setup()` (or an
uncalled root such as an interrupt handler) within a few levels.

Usage:
    python -m m8loader.re.ghidra_decomp <stock.bin> <workdir> 0x6005ED66 0x60025718 ...
"""
from __future__ import annotations

import os
import sys

from m8loader.m8fw import M8Firmware
from m8loader.re.ghidra_export import DEFAULT_GHIDRA, LANGUAGE, BINARY_LOADER

KNOWN = {0x60081BD4: "loop", 0x60082374: "setup", 0x600AE04C: "main", 0x600B4DC0: "yield"}


def run(stock_path: str, workdir: str, entries, base: int = 0x60000000) -> None:
    os.environ.setdefault("GHIDRA_INSTALL_DIR", os.environ.get("GHIDRA_INSTALL_DIR", DEFAULT_GHIDRA))
    import pyghidra
    pyghidra.start(verbose=False)
    from ghidra.app.decompiler import DecompInterface
    from ghidra.util.task import TaskMonitor

    out = os.path.join(workdir, "decomp")
    os.makedirs(out, exist_ok=True)
    payload_path = os.path.join(workdir, "payload.bin")
    fw = M8Firmware.from_file(stock_path, verify=True)
    with open(payload_path, "wb") as f:
        f.write(fw.payload)

    with pyghidra.open_program(payload_path, project_location=workdir, project_name="m8fw_decomp",
                               language=LANGUAGE, loader=BINARY_LOADER, analyze=False) as api:
        prog = api.getCurrentProgram()
        space = prog.getAddressFactory().getDefaultAddressSpace()
        tx = prog.startTransaction("rebase")
        prog.setImageBase(space.getAddress(base), True)
        prog.endTransaction(tx, True)
        api.analyzeAll(prog)
        fm = prog.getFunctionManager()
        dec = DecompInterface()
        dec.openProgram(prog)
        mon = TaskMonitor.DUMMY

        def name(fn):
            e = fn.getEntryPoint().getOffset()
            return KNOWN.get(e, "0x%08X" % e)

        lines = []
        for e in entries:
            fn = fm.getFunctionAt(api.toAddr(e))
            if fn is None:
                # Ghidra's auto-analysis missed much of the track-player region:
                # create the function at the exact entry we were given.
                t = prog.startTransaction("create")
                try:
                    api.disassemble(api.toAddr(e))
                    fn = api.createFunction(api.toAddr(e), None)
                finally:
                    prog.endTransaction(t, True)
            if fn is None:
                fn = fm.getFunctionContaining(api.toAddr(e))
            if fn is None:
                lines.append("0x%08X: no function" % e)
                continue
            res = dec.decompileFunction(fn, 120, mon)
            code = res.getDecompiledFunction().getC() if res.decompileCompleted() else "// decompile failed"
            with open(os.path.join(out, "%08X.c" % fn.getEntryPoint().getOffset()), "w") as f:
                f.write(code)
            callers = sorted(name(c) for c in fn.getCallingFunctions(mon))
            lines.append("%s size %d callers: %s" % (name(fn), int(fn.getBody().getNumAddresses()),
                                                     ", ".join(callers) or "(none: root or indirect)"))
            # caller chains up to a known function or a root, depth <= 6
            chains, frontier = [], [[fn]]
            for _ in range(6):
                nxt = []
                for path in frontier:
                    cs = list(path[-1].getCallingFunctions(mon))
                    if not cs or path[-1].getEntryPoint().getOffset() in KNOWN:
                        chains.append(path)
                        continue
                    for c in cs[:4]:
                        if c not in path:
                            nxt.append(path + [c])
                frontier = nxt[:40]
            chains += frontier
            for path in chains[:8]:
                lines.append("    " + " <- ".join(name(x) for x in path))
        with open(os.path.join(out, "callers.txt"), "w") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 3:
        sys.exit(__doc__)
    run(a[0], a[1], [int(x, 16) for x in a[2:]])
