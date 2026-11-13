# SPDX-License-Identifier: GPL-2.0-or-later
"""Check .m8mod files and say what is wrong (docs/FORMAT.md).

    python -m dirtyloader lint MY.m8mod [MORE.m8mod ...]
    python -m dirtyloader lint MY.m8mod --stock stock.bin --with core.m8mod

Without --stock, each file is checked on its own: the format, its fields, a target with a device and a stock
hash, and that every site is well formed. With --stock it also runs the full link with any --with mods (the
core a mod requires), so targets, requires, conflicts, resources, site overlaps and subscriptions are checked
together. One "OK" or "PROBLEM:" line per finding; exit status 0 means everything passed.
"""
from __future__ import annotations

import os

from dirtyloader.m8fw import M8Firmware, M8FWError
from dirtyloader.m8mod import Mod, KINDS, DEVICES
from dirtyloader.linker import link
from dirtyloader import registry
from dirtyloader.core.abi import Event


def check_mod(mod: Mod) -> list:
    p = []
    if not mod.id:
        p.append("missing id")
    t = mod.target or {}
    if t.get("device") and t["device"] not in DEVICES:
        p.append(f"target device {t['device']!r} is unknown")
    if not t.get("device"):
        p.append("target has no device")
    if not t.get("bin_sha256"):
        p.append("target has no bin_sha256 (cannot be pinned to stock firmware)")
    for s in mod.sites:
        if s.len <= 0:
            p.append(f"site 0x{s.addr:08X}: len is {s.len}")
        if s.kind not in KINDS:
            p.append(f"site 0x{s.addr:08X}: kind {s.kind!r} is not one of {KINDS}")
        if len(s.stock_sha256 or "") != 64:
            p.append(f"site 0x{s.addr:08X}: stock_sha256 is not a sha256")
    known = {e.name for e in Event}
    for s in mod.subscribe:
        if s["event"] not in known:
            p.append(f"subscribe: unknown event {s['event']!r}")
    if mod.subscribe and "core" not in mod.requires and mod.id != "core":
        p.append("subscribes to events but does not require 'core'")
    return p


def _main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="dirtyloader lint", description=__doc__.splitlines()[1])
    ap.add_argument("files", nargs="+", help=".m8mod files")
    ap.add_argument("--stock", help="stock .bin: also run the full link")
    ap.add_argument("--with", dest="with_", action="append", default=[], help="another .m8mod to link with")
    args = ap.parse_args(argv)

    bad = False
    mods = []
    for f in args.files:
        try:
            m = Mod.load(f)
        except (M8FWError, ValueError, KeyError) as e:
            print(f"PROBLEM: {f}: {e}")
            bad = True
            continue
        mods.append(m)
        probs = check_mod(m)
        if probs:
            bad = True
            for pr in probs:
                print(f"PROBLEM: {f}: {pr}")
        else:
            fmt = m.loaded_format
            print(f"OK: {f}: {m.id} {m.version} (format {fmt}), {len(m.sites)} site(s), "
                  f"{len(m.subscribe)} subscription(s)")

    if args.stock and not bad:
        data = open(args.stock, "rb").read()
        fw = M8Firmware.parse(data, verify=True)
        sha = registry.sha256_bytes(data)
        extra = [Mod.load(w) for w in args.with_]
        try:
            link(fw, sha, mods + extra)
            print(f"OK: links against {os.path.basename(args.stock)}")
        except M8FWError as e:
            print(f"PROBLEM: link: {e}")
            bad = True

    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(_main())
