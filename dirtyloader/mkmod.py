# SPDX-License-Identifier: GPL-2.0-or-later
"""A mod source folder (mod.json + .s sources) -> a format-2 .m8mod (docs/FORMAT.md, "Source folders").

    python -m dirtyloader mkmod mods/hello-tick --stock stock.bin -o hello-tick.m8mod

mod.json:
  id, version, title, category, license, author, description
  device, firmware                target (the hashes come from --stock)
  requires, conflicts, core, resources
  build: "core"                   core only: built by dirtyloader.core.builder from the firmware's bindings
  cave: "0x60000460"              base of this mod's code in a free code cave (see docs/CORE.md)
  handlers: [{event, source, order}]   each .s is assembled at the next slot; its entry is subscribed

Stock bytes are read from --stock to fill each site's guard hash; they are never written into the .m8mod.
Assembly uses keystone (a Thumb handler receives the event id in r0 and must preserve r4-r11).
"""
from __future__ import annotations

import json
import os
import re

from dirtyloader.m8fw import M8Firmware, M8FWError
from dirtyloader.m8mod import Mod, Site, make_target, event_name
from dirtyloader import registry
from dirtyloader.core import abi

try:
    import keystone as _ks
except ImportError:  # pragma: no cover
    _ks = None

_COMMENTS = re.compile(r"/\*.*?\*/", re.DOTALL)


def assemble(source: str, addr: int) -> bytes:
    """Assemble Thumb `source` placed at `addr`. Comments (/* */, //, @) are stripped first."""
    if _ks is None:
        raise M8FWError("keystone-engine is not installed (pip install keystone-engine)")
    text = _COMMENTS.sub("", source)
    text = "\n".join(ln.split("//")[0].split("@")[0] for ln in text.splitlines())
    ks = _ks.Ks(_ks.KS_ARCH_ARM, _ks.KS_MODE_THUMB)
    enc, _count = ks.asm(text, addr)
    if enc is None:
        raise M8FWError("assembly failed (keystone)")
    return bytes(enc)


def bindings_for(sha256: str) -> dict:
    bdir = os.path.join(os.path.dirname(abi.__file__), "bindings")
    for n in sorted(os.listdir(bdir)):
        if n.endswith(".json"):
            b = json.load(open(os.path.join(bdir, n), encoding="utf-8"))
            if (b.get("stock_sha256") or "").lower() == sha256:
                return b
    raise M8FWError(f"no Core bindings for stock {sha256[:12]}... (dirtyloader/core/bindings/)")


def build_from_source(src_dir: str, stock_path: str) -> Mod:
    mj = json.load(open(os.path.join(src_dir, "mod.json"), encoding="utf-8"))
    data = open(stock_path, "rb").read()
    fw = M8Firmware.parse(data, verify=True)
    sha = registry.sha256_bytes(data)
    ident = registry.identify(sha)
    firmware = mj.get("firmware") or (ident["version"] if ident else "")

    if mj.get("build") == "core":
        from dirtyloader.core import builder
        b = bindings_for(sha)
        mod = builder.build_core_mod(fw, sha, int(b["hook_sites"]["TICK"]["patch_at"], 16),
                                     int(b["symbols"]["loop"], 16))
        for f in ("version", "title", "description", "license", "author", "category"):
            if mj.get(f):
                setattr(mod, f, mj[f])
        mod.target["firmware"] = firmware
        return mod

    base = int(mj["cave"], 0)
    sites, subs = [], []
    for h in mj.get("handlers", []):
        code = assemble(open(os.path.join(src_dir, h["source"]), encoding="utf-8").read(), base)
        off = base - fw.load_addr
        stock = bytes(fw.payload[off:off + len(code)])
        if set(stock) not in ({0xFF}, set()):
            raise M8FWError(f"{mj['id']}: cave 0x{base:08X} is not free (0xFF) in this firmware")
        sites.append(Site.from_bytes(base, stock, code, "code", f"{event_name(h['event'])} handler"))
        subs.append({"event": event_name(h["event"]), "handler": base | 1,
                     "order": int(h.get("order", 50))})
        base += (len(code) + 1) & ~1

    return Mod(
        id=mj["id"], version=str(mj.get("version", "0.0.0")), title=mj.get("title", ""),
        description=mj.get("description", ""), category=mj.get("category", ""),
        author=mj.get("author", ""), license=mj.get("license", ""),
        target=make_target(fw, sha, firmware), sites=sites, subscribe=subs,
        requires=list(mj.get("requires", [])), conflicts=list(mj.get("conflicts", [])),
        core=mj.get("core"), resources=dict(mj.get("resources") or {}),
    )
