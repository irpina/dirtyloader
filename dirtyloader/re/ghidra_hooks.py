"""
Locate Core hook-point candidates in the stripped M8 firmware.

The firmware has no symbols, so we find integration points structurally:

  * RENDER layer  -- which functions reference known UI-label strings
                     (a function that draws "HARMONIC MAJOR" is UI/render code)
  * main loop     -- the call graph reachable from the reset entry

Runs the same PyGhidra analysis as ghidra_export, then queries references and the
call graph. Output: <workdir>/ghidra_hooks.json

Usage:
    python -m dirtyloader.re.ghidra_hooks <stock.bin> <workdir>
"""
from __future__ import annotations

import json
import os
import sys
from collections import deque

from dirtyloader.m8fw import M8Firmware
from dirtyloader.re.ghidra_export import DEFAULT_GHIDRA, LANGUAGE, BINARY_LOADER

# (label, absolute flash address) -- unique UI strings located earlier.
ANCHORS = [
    ("HARMONIC MAJOR", 0x601D0E62),
    ("DOWNSAMPLE", 0x601CFECE),
]
ENTRY = 0x60001648  # IVT entry 0x60001649, Thumb bit cleared


def analyze_hooks(stock_path: str, workdir: str, base: int = 0x60000000) -> dict:
    os.environ.setdefault("GHIDRA_INSTALL_DIR",
                          os.environ.get("GHIDRA_INSTALL_DIR", DEFAULT_GHIDRA))
    import pyghidra
    pyghidra.start(verbose=False)
    from ghidra.util.task import TaskMonitor

    os.makedirs(workdir, exist_ok=True)
    payload_path = os.path.join(workdir, "payload.bin")
    out_json = os.path.join(workdir, "ghidra_hooks.json")
    fw = M8Firmware.from_file(stock_path, verify=True)
    with open(payload_path, "wb") as f:
        f.write(fw.payload)
    print("analyzing (this takes a few minutes)...")

    with pyghidra.open_program(
        payload_path, project_location=workdir, project_name="m8fw_hooks",
        language=LANGUAGE, loader=BINARY_LOADER, analyze=False,
    ) as api:
        prog = api.getCurrentProgram()
        space = prog.getAddressFactory().getDefaultAddressSpace()
        tx = prog.startTransaction("rebase")
        prog.setImageBase(space.getAddress(base), True)
        prog.endTransaction(tx, True)
        api.analyzeAll(prog)

        fm = prog.getFunctionManager()
        listing = prog.getListing()

        def fkey(fn):
            return "0x%08X" % fn.getEntryPoint().getOffset() if fn else None

        # --- make sure the reset entry is actually a function -----------
        tx2 = prog.startTransaction("seed-entry")
        ep = api.toAddr(ENTRY)
        try:
            api.disassemble(ep)
            root = fm.getFunctionAt(ep) or api.createFunction(ep, "reset_entry")
        except Exception as e:
            root = fm.getFunctionContaining(ep)
            print("entry seed note:", e)
        prog.endTransaction(tx2, True)

        # --- two-hop string xrefs (string -> pointer slot -> code) ------
        xrefs = []
        for label, a in ANCHORS:
            addr = api.toAddr(a)
            direct, viatable = {}, {}
            slots = []
            for r in api.getReferencesTo(addr):
                frm = r.getFromAddress()
                fn = fm.getFunctionContaining(frm)
                if fn:
                    direct[fkey(fn)] = direct.get(fkey(fn), 0) + 1
                else:
                    slots.append("0x%08X" % frm.getOffset())
                    for r2 in api.getReferencesTo(frm):  # who reads the pointer slot
                        fn2 = fm.getFunctionContaining(r2.getFromAddress())
                        if fn2:
                            viatable[fkey(fn2)] = viatable.get(fkey(fn2), 0) + 1
            xrefs.append({"label": label, "string_addr": "0x%08X" % a,
                          "pointer_slots": slots[:8],
                          "direct_code_refs": direct, "via_pointer_table": viatable})

        # --- call graph from the reset entry ----------------------------
        chain = []
        if root is not None:
            seen = set()
            q = deque([(root, 0)])
            while q and len(chain) < 150:
                fn, depth = q.popleft()
                k = fkey(fn)
                if k in seen or depth > 4:
                    continue
                seen.add(k)
                chain.append({"entry": k, "depth": depth,
                              "size": int(fn.getBody().getNumAddresses())})
                if depth < 4:
                    for callee in fn.getCalledFunctions(TaskMonitor.DUMMY):
                        q.append((callee, depth + 1))

        # --- infinite-loop functions (main-loop / idle signature) -------
        loopers = []
        for fn in fm.getFunctions(True):
            body = fn.getBody()
            size = int(body.getNumAddresses())
            if size < 24 or size > 20000 or fn.isThunk():
                continue
            it = listing.getInstructions(body, True)
            while it.hasNext():
                i = it.next()
                ft = i.getFlowType()
                if ft.isJump() and ft.isUnConditional() and not ft.isComputed():
                    hit = False
                    for t in i.getFlows():
                        if body.contains(t) and t.getOffset() <= i.getAddress().getOffset():
                            loopers.append({"entry": fkey(fn), "size": size,
                                            "branch_at": "0x%08X" % i.getAddress().getOffset()})
                            hit = True
                            break
                    if hit:
                        break
        loopers.sort(key=lambda x: x["size"], reverse=True)

        summary = {
            "entry_function": fkey(root),
            "string_xrefs": xrefs,
            "call_chain_from_entry": chain,
            "infinite_loop_functions": loopers[:25],
        }

    with open(out_json, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"wrote {out_json}")
    return summary


def _main(argv=None) -> int:
    a = argv or sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        return 2
    analyze_hooks(a[0], a[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
