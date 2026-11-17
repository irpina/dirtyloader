"""
Build core 0.5 for the M8 Model:02 (6.6.2A) and link it into a flashable .bin.

    python -m dirtyloader.core.build_model02 <stock M8_V6_6_2A_MODEL02.bin> <out dir>

Writes <out>/M8_V6_6_2A_MODEL02_core05.bin, <out>/core.m8mod and <out>/sd/ (as build_headless does: the heartbeat
example, rebuilt for this firmware, in sd/dirtyloader/mods with active.txt and guard). The core is the headless
core's C (core03.c) built against m8-model02/fw.h, with the sites of bindings/m8_6.6.2A_model02.json: every one was
found again in 6.6.2A from the headless one (docs/MODEL02-PORT.md). It has been built and checked byte for byte
against the stock image, but not yet run on a Model:02 unit: flash it on a unit you can restore with the stock
.bin (M8 Launcher / the Teensy Loader).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

from dirtyloader.core import builder
from dirtyloader.core.build_headless import write_sd
from dirtyloader.linker import link
from dirtyloader.m8fw import M8Firmware

BINDINGS = os.path.join(os.path.dirname(__file__), "bindings", "m8_6.6.2A_model02.json")
HEARTBEAT = os.path.join(os.path.dirname(__file__), "..", "..", "examples", "sd-heartbeat", "heartbeat.c")
FW_HEADER_DIR = os.path.join(os.path.dirname(__file__), "..", "sdk", "include", "m8-model02")


def build(stock_bin: str, out: str) -> dict:
    from dirtyloader import cc
    with open(stock_bin, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    with open(BINDINGS) as f:
        b = json.load(f)
    if sha != b["stock_sha256"]:
        raise SystemExit(f"{stock_bin} is not {b['firmware']} (sha256 {sha[:12]}...)")
    fw = M8Firmware.parse(raw)
    core = builder.build_core03_mod(fw, sha, b)
    patched = link(fw, sha, [core])
    # mods include "m8-headless/fw.h" by name: give them this firmware's header under that name
    beat, info = cc.build_m8x([HEARTBEAT], defines={"M8_MODEL02": "1"}, includes=[_alias_dir()])
    os.makedirs(out, exist_ok=True)
    core.save(os.path.join(out, "core.m8mod"))
    sd = write_sd(out, {"sd-heartbeat.m8x": beat})
    path = os.path.join(out, "M8_V6_6_2A_MODEL02_core05.bin")
    M8Firmware(version=fw.version, load_addr=fw.load_addr, payload=patched.payload).to_file(path)
    n = len(fw.payload)
    changed = sum(1 for x, y in zip(fw.payload, patched.payload[:n]) if x != y) + len(patched.payload) - n
    return {"bin": path, "sd": sd, "changed_bytes": changed, "core_events": core.events,
            "heartbeat": {k: v for k, v in info.items() if k != "symbols"}}


def _alias_dir() -> str:
    """An include directory where "m8-headless/fw.h" is the Model:02 header, for the shipped examples."""
    import tempfile
    d = os.path.join(tempfile.gettempdir(), "dirtyloader-model02-include")
    os.makedirs(os.path.join(d, "m8-headless"), exist_ok=True)
    with open(os.path.join(FW_HEADER_DIR, "fw.h"), encoding="utf-8") as f:
        text = f.read()
    with open(os.path.join(d, "m8-headless", "fw.h"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return d


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        raise SystemExit(__doc__)
    print(json.dumps(build(args[0], args[1]), indent=1))
