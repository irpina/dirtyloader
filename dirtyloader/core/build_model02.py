"""
Build core for the M8 Model:02 and link it into a flashable .bin.

    python -m dirtyloader.core.build_model02 <stock M8_V6_6_xA_MODEL02.bin> <out dir>

The stock .bin picks the firmware by its sha256: 6.6.2A (bindings/m8_6.6.2A_model02.json, m8-model02/fw.h) or 6.6.4A
(bindings/m8_6.6.4A_model02.json, m8-model02-6.6.4A/fw.h). Writes <out>/M8_V6_6_xA_MODEL02_core.bin, <out>/core.m8mod
and <out>/sd/ (as build_headless does: the heartbeat example, rebuilt for this firmware, in sd/dirtyloader/mods with
active.txt and guard). The core is the headless core's C (core03.c) built against the firmware's header, with the
sites of its bindings: every one was found again from the other builds (docs/MODEL02-PORT.md,
docs/MODEL02-664-PORT.md). Flash it on a unit you can restore with the stock .bin.
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

HERE = os.path.dirname(__file__)
HEARTBEAT = os.path.join(HERE, "..", "..", "examples", "sd-heartbeat", "heartbeat.c")
INCLUDE = os.path.join(HERE, "..", "sdk", "include")
# the Model:02 firmwares core is built for: version -> (bindings, device header dir, mods' firmware id)
FIRMWARES = {
    "6.6.2A": ("m8_6.6.2A_model02.json", "m8-model02", 0x02060602),
    "6.6.4A": ("m8_6.6.4A_model02.json", "m8-model02-6.6.4A", 0x02060604),
}
BINDINGS = os.path.join(HERE, "bindings", FIRMWARES["6.6.2A"][0])          # the first port's, as before
FW_HEADER_DIR = os.path.join(INCLUDE, FIRMWARES["6.6.2A"][1])


def bindings_path(version: str) -> str:
    return os.path.join(HERE, "bindings", FIRMWARES[version][0])


def identify(raw: bytes):
    """(version, bindings) for a stock Model:02 .bin, by its sha256; SystemExit if it is none core supports."""
    sha = hashlib.sha256(raw).hexdigest()
    for version in FIRMWARES:
        with open(bindings_path(version)) as f:
            b = json.load(f)
        if b["stock_sha256"] == sha:
            return version, b
    raise SystemExit(f"not a Model:02 firmware core supports (sha256 {sha[:12]}...): "
                     + ", ".join(f"M8_V{v.replace('.', '_')}_MODEL02.bin" for v in FIRMWARES))


def build(stock_bin: str, out: str) -> dict:
    from dirtyloader import cc
    with open(stock_bin, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    version, b = identify(raw)
    fw = M8Firmware.parse(raw)
    core = builder.build_core03_mod(fw, sha, b)
    patched = link(fw, sha, [core])
    # mods include "m8-headless/fw.h" by name: give them this firmware's header under that name
    beat, info = cc.build_m8x([HEARTBEAT], defines={"M8_MODEL02": "1"}, includes=[_alias_dir(version)])
    os.makedirs(out, exist_ok=True)
    core.save(os.path.join(out, "core.m8mod"))
    sd = write_sd(out, {"sd-heartbeat.m8x": beat})
    path = os.path.join(out, f"M8_V{version.replace('.', '_')}_MODEL02_core.bin")
    M8Firmware(version=fw.version, load_addr=fw.load_addr, payload=patched.payload).to_file(path)
    n = len(fw.payload)
    changed = sum(1 for x, y in zip(fw.payload, patched.payload[:n]) if x != y) + len(patched.payload) - n
    return {"firmware": version, "bin": path, "sd": sd, "changed_bytes": changed, "core_events": core.events,
            "heartbeat": {k: v for k, v in info.items() if k != "symbols"}}


def _alias_dir(version: str = "6.6.2A") -> str:
    """An include directory where "m8-headless/fw.h" is this Model:02 firmware's header, for the shipped examples."""
    import tempfile
    d = os.path.join(tempfile.gettempdir(), f"dirtyloader-model02-{version}-include")
    os.makedirs(os.path.join(d, "m8-headless"), exist_ok=True)
    with open(os.path.join(INCLUDE, FIRMWARES[version][1], "fw.h"), encoding="utf-8") as f:
        text = f.read()
    with open(os.path.join(d, "m8-headless", "fw.h"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return d


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        raise SystemExit(__doc__)
    print(json.dumps(build(args[0], args[1]), indent=1))
