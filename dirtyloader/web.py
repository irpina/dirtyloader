"""
In-browser builder glue, used by the GitHub Pages site through Pyodide.

The site loads the `dirtyloader` package into Pyodide (a WebAssembly CPython) and
calls these two functions. Everything runs in the visitor's browser: the stock
firmware they pick is read locally and never uploaded, exactly like the CLI.

Stdlib only, like the rest of the runtime path -- no keystone here, because the
site only *applies* pre-built `.m8mod` files; mods are assembled ahead of time by
`mkmod`.
"""
from __future__ import annotations

import json
from typing import List

from dirtyloader.m8fw import M8Firmware
from dirtyloader.m8mod import Mod
from dirtyloader.linker import link
from dirtyloader import registry


def inspect_stock(stock: bytes) -> dict:
    """Identify a picked .bin without requiring it to be known/valid."""
    fw = M8Firmware.parse(stock, verify=False)
    sha = registry.sha256_bytes(stock)
    ident = registry.identify(sha)
    problems = fw.check_stock(stock)
    return {
        "model": fw.model,
        "payload_len": len(fw.payload),
        "sha256": sha,
        "identity": ident["name"] if ident else None,
        "known": ident is not None,
        "valid": not problems,
        "problems": problems,
    }


def _out_name(sha: str, mods: List[Mod]) -> str:
    ident = registry.identify(sha)
    base = "M8_" + (ident["version"].replace(".", "_") if ident else sha[:8])
    ids = "-".join(m.id for m in mods if m.id != "core") or "core"
    return f"{base}__{ids}.bin"


def build_patched(stock: bytes, mod_jsons) -> dict:
    """Apply the selected mods (as JSON text or dicts) to `stock`, returning the
    flashable image bytes and a short report. Raises M8FWError on any problem."""
    fw = M8Firmware.parse(stock, verify=True)
    sha = registry.sha256_bytes(stock)
    mods = [Mod.from_dict(json.loads(j) if isinstance(j, (str, bytes)) else j) for j in mod_jsons]
    out = link(fw, sha, mods)
    data = out.build()
    return {
        "name": _out_name(sha, mods),
        "bytes": data,
        "size": len(data),
        "payload_crc": f"0x{out.payload_crc32():08X}",
        "sha256": out.sha256(),
        "mods": [f"{m.id} {m.version}" for m in mods],
    }
