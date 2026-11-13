"""
Find which functions reference a set of anchor addresses, using Ghidra's
constant-reference analysis (resolves Thumb movw/movt address loads that byte
scans miss). Used to locate the parameter-descriptor / modulation-apply code by
anchoring on the destination and send name strings.

Usage:
    python -m dirtyloader.re.ghidra_xref <stock.bin> <workdir>
"""
from __future__ import annotations

import json
import os
import sys

from dirtyloader.m8fw import M8Firmware
from dirtyloader.re.ghidra_export import DEFAULT_GHIDRA, LANGUAGE, BINARY_LOADER

# label -> absolute address (from the 6.6.2A parameter-label region)
ANCHORS = {
    "CUTOFF": 0x601E4214, "RES": 0x601E421C, "AMP": 0x601E4220, "PAN": 0x601E4224,
    "VOL": 0x601E4264, "PITCH": 0x601E427C, "FINETUNE": 0x601E4780,
    "SEND MODFX": 0x601E4534, "SEND DELAY": 0x601E4558, "SEND REVERB": 0x601E457C,
    "MFX": 0x601E4528, "DEL": 0x601E454C, "REV": 0x601E4570, "DRY": 0x601E4510,
    "DEST": 0x601E3D24, "LFO DESTINATION": 0x601E3E2C,
}


def run(stock_path: str, workdir: str, base: int = 0x60000000) -> dict:
    os.environ.setdefault("GHIDRA_INSTALL_DIR",
                          os.environ.get("GHIDRA_INSTALL_DIR", DEFAULT_GHIDRA))
    import pyghidra
    pyghidra.start(verbose=False)

    os.makedirs(workdir, exist_ok=True)
    payload_path = os.path.join(workdir, "payload.bin")
    out_json = os.path.join(workdir, "ghidra_xref.json")
    fw = M8Firmware.from_file(stock_path, verify=True)
    with open(payload_path, "wb") as f:
        f.write(fw.payload)
    print("analyzing...")

    with pyghidra.open_program(payload_path, project_location=workdir,
                               project_name="m8fw_xref", language=LANGUAGE,
                               loader=BINARY_LOADER, analyze=False) as api:
        prog = api.getCurrentProgram()
        space = prog.getAddressFactory().getDefaultAddressSpace()
        tx = prog.startTransaction("rebase")
        prog.setImageBase(space.getAddress(base), True)
        prog.endTransaction(tx, True)
        api.analyzeAll(prog)
        fm = prog.getFunctionManager()

        def fkey(fn):
            return "0x%08X" % fn.getEntryPoint().getOffset() if fn else None

        listing = prog.getListing()

        def str_at(addr):
            try:
                d = listing.getDataContaining(addr)
                b = []
                a2 = addr
                for _ in range(24):
                    code = api.getByte(a2) & 0xFF
                    if 32 <= code < 127:
                        b.append(chr(code))
                        a2 = a2.add(1)
                    else:
                        break
                return "".join(b)
            except Exception:
                return ""

        # Enumerate every referenced address in the label region and who refs it.
        from ghidra.program.model.address import AddressSet
        LO, HI = 0x601E3C00, 0x601E5E00
        aset = AddressSet(api.toAddr(LO), api.toAddr(HI - 1))
        rm = prog.getReferenceManager()
        it = rm.getReferenceDestinationIterator(aset, True)
        by_func = {}   # func -> {dest_addr: string}
        dests = []
        while it.hasNext():
            dest = it.next()
            da = "0x%08X" % dest.getOffset()
            s = str_at(dest)
            dests.append({"dest": da, "str": s})
            for r in rm.getReferencesTo(dest):
                fn = fm.getFunctionContaining(r.getFromAddress())
                k = fkey(fn) or ("data:0x%08X" % r.getFromAddress().getOffset())
                by_func.setdefault(k, {})[da] = s

        ranked = sorted(by_func.items(), key=lambda kv: len(kv[1]), reverse=True)
        summary = {
            "referenced_dests": dests[:80],
            "referencing_functions": [
                {"func": k, "count": len(v),
                 "targets": [{"addr": a, "str": s} for a, s in sorted(v.items())][:20]}
                for k, v in ranked[:20]
            ],
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
    run(a[0], a[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
