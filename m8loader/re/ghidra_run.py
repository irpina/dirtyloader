"""
Drive Ghidra headless over an M8 firmware payload.

Extracts the flat flash image from a stock .bin, imports it into a throwaway
Ghidra project at base 0x60000000 as ARM Cortex (Thumb), runs auto-analysis, and
exports the discovered functions/strings to JSON via export_functions.py.

The Ghidra install is found via $GHIDRA_INSTALL_DIR, else a machine default.

Usage:
    python -m m8loader.re.ghidra_run <stock.bin> <workdir> [base_hex]
"""
from __future__ import annotations

import os
import subprocess
import sys

from m8loader.m8fw import M8Firmware

DEFAULT_GHIDRA = r"C:\Users\zacha\Documents\smbd-recompilation\build\deps\ghidra_12.1.4_PUBLIC"
PROCESSOR = "ARM:LE:32:Cortex"
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "ghidra_scripts")


def ghidra_home() -> str:
    return os.environ.get("GHIDRA_INSTALL_DIR", DEFAULT_GHIDRA)


def analyze_headless_path() -> str:
    home = ghidra_home()
    bat = os.path.join(home, "support", "analyzeHeadless.bat")
    sh = os.path.join(home, "support", "analyzeHeadless")
    return bat if os.name == "nt" and os.path.exists(bat) else sh


def extract_payload(stock_path: str, out_path: str) -> M8Firmware:
    fw = M8Firmware.from_file(stock_path, verify=True)
    with open(out_path, "wb") as f:
        f.write(fw.payload)
    return fw


def run(stock_path: str, workdir: str, base: int = 0x60000000,
        process_only: bool = False) -> int:
    os.makedirs(workdir, exist_ok=True)
    payload = os.path.join(workdir, "payload.bin")
    out_json = os.path.join(workdir, "ghidra_functions.json")
    if not process_only:
        fw = extract_payload(stock_path, payload)
        print(f"extracted payload: 0x{len(fw.payload):X} bytes -> {payload}")

    headless = analyze_headless_path()
    if not os.path.exists(headless):
        print(f"ERROR: analyzeHeadless not found at {headless}", file=sys.stderr)
        print("set GHIDRA_INSTALL_DIR to your Ghidra install", file=sys.stderr)
        return 2

    # Ghidra 12 runs .py scripts via PyGhidra, enabled in headless with -pyghidra.
    # We keep the project (no -deleteProject) so the script can be re-run with
    # -process against the already-analyzed program (process_only=True) -- fast.
    if process_only:
        action = ["-process", "payload.bin"]
    else:
        action = ["-import", payload, "-processor", PROCESSOR,
                  "-loader", "BinaryLoader", "-loader-baseAddr", f"0x{base:08X}"]
    args = [
        headless, workdir, "m8fw", "-pyghidra",
        *action,
        "-scriptPath", SCRIPTS_DIR,
        "-postScript", "export_functions.py", out_json,
    ]
    # On Windows, a .bat must be launched through the command interpreter.
    cmd = (["cmd", "/c"] + args) if headless.lower().endswith(".bat") else args
    print("running:", " ".join(f'"{a}"' if " " in a else a for a in args))
    proc = subprocess.run(cmd)
    print(f"analyzeHeadless exit code: {proc.returncode}")
    if os.path.exists(out_json):
        print(f"OK -> {out_json}")
    return proc.returncode


def _main(argv=None) -> int:
    a = list(argv or sys.argv[1:])
    process_only = "--process-only" in a
    a = [x for x in a if x != "--process-only"]
    if len(a) < 2:
        print(__doc__)
        return 2
    base = int(a[2], 16) if len(a) > 2 else 0x60000000
    return run(a[0], a[1], base, process_only=process_only)


if __name__ == "__main__":
    raise SystemExit(_main())
