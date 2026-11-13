"""
Drive Ghidra in-process via the PyGhidra (CPython) bridge and export the
discovered function map to JSON.

Ghidra 12 dropped bundled Jython, so .py scripts only run under PyGhidra. Rather
than launch analyzeHeadless, we start Ghidra inside CPython, import the flat flash
image at 0x60000000 as ARM Cortex (Thumb), rebase, auto-analyze, and dump the
functions / a string sample. Needs `pip install pyghidra` and a Ghidra install
(via $GHIDRA_INSTALL_DIR).

Usage:
    python -m dirtyloader.re.ghidra_export <stock.bin> <workdir> [base_hex]
"""
from __future__ import annotations

import json
import os
import sys

from dirtyloader.m8fw import M8Firmware

DEFAULT_GHIDRA = r"C:\Users\zacha\Documents\smbd-recompilation\build\deps\ghidra_12.1.4_PUBLIC"
LANGUAGE = "ARM:LE:32:Cortex"
BINARY_LOADER = "ghidra.app.util.opinion.BinaryLoader"


def export(stock_path: str, workdir: str, base: int = 0x60000000) -> dict:
    os.environ.setdefault("GHIDRA_INSTALL_DIR",
                          os.environ.get("GHIDRA_INSTALL_DIR", DEFAULT_GHIDRA))
    import pyghidra
    pyghidra.start(verbose=False)

    os.makedirs(workdir, exist_ok=True)
    payload_path = os.path.join(workdir, "payload.bin")
    out_json = os.path.join(workdir, "ghidra_functions.json")
    fw = M8Firmware.from_file(stock_path, verify=True)
    with open(payload_path, "wb") as f:
        f.write(fw.payload)
    print(f"extracted payload 0x{len(fw.payload):X} bytes; starting Ghidra analysis...")

    with pyghidra.open_program(
        payload_path,
        project_location=workdir,
        project_name="m8fw",
        language=LANGUAGE,
        loader=BINARY_LOADER,
        analyze=False,
    ) as api:
        prog = api.getCurrentProgram()
        space = prog.getAddressFactory().getDefaultAddressSpace()
        tx = prog.startTransaction("rebase")
        prog.setImageBase(space.getAddress(base), True)
        prog.endTransaction(tx, True)
        api.analyzeAll(prog)

        fm = prog.getFunctionManager()
        funcs = []
        it = fm.getFunctions(True)
        while it.hasNext():
            f = it.next()
            ep = f.getEntryPoint()
            funcs.append({
                "name": f.getName(),
                "entry": "0x%08X" % ep.getOffset(),
                "size": int(f.getBody().getNumAddresses()),
                "thunk": bool(f.isThunk()),
                "called_by": int(f.getSymbol().getReferenceCount()) if f.getSymbol() else 0,
            })

        strings = []
        di = prog.getListing().getDefinedData(True)
        while di.hasNext() and len(strings) < 200:
            d = di.next()
            try:
                if d.hasStringValue():
                    s = str(d.getValue())
                    if s and len(s) >= 4:
                        strings.append({"addr": "0x%08X" % d.getAddress().getOffset(),
                                        "text": s[:60]})
            except Exception:
                pass

        summary = {
            "language": str(prog.getLanguageID()),
            "image_base": "0x%08X" % prog.getImageBase().getOffset(),
            "function_count": len(funcs),
            "string_sample_count": len(strings),
            "functions": funcs,
            "strings": strings,
        }

    with open(out_json, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"exported {len(funcs)} functions, {len(strings)} strings -> {out_json}")
    return summary


def _main(argv=None) -> int:
    a = argv or sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        return 2
    base = int(a[2], 16) if len(a) > 2 else 0x60000000
    export(a[0], a[1], base)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
