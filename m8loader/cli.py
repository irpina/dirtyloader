"""
dirtyloader command-line interface.

    python -m m8loader.cli info     <stock.bin>
    python -m m8loader.cli verify   <stock.bin>
    python -m m8loader.cli build    <stock.bin> -m a.m8mod -m b.m8mod -o out.bin
    python -m m8loader.cli make-mod <stock.bin> <modified.bin> -o mod.m8mod --id my-mod

`build` never touches your device: it writes a patched .bin you flash the normal
way (M8 SD-card firmware update, or TyTools). `make-mod` is the author tool:
hand-edit a copy of the firmware, then diff it back into a shareable mod.
"""
from __future__ import annotations

import argparse
import sys

from m8loader.m8fw import M8Firmware, M8FWError
from m8loader.m8mod import Mod
from m8loader.linker import link, diff_payloads
from m8loader import registry


def _load_stock(path: str, verify: bool = True):
    with open(path, "rb") as f:
        data = f.read()
    fw = M8Firmware.parse(data, verify=verify)
    return fw, data


def cmd_info(args) -> int:
    fw, data = _load_stock(args.firmware, verify=False)
    sha = registry.sha256_bytes(data)
    ident = registry.identify(sha)
    problems = fw.check_stock(data)
    print(fw.summary())
    print(f"sha256   : {sha}")
    print(f"identity : {ident['name'] if ident else 'UNKNOWN (not in registry)'}")
    print(f"integrity: {'OK (valid stock CRCs)' if not problems else '; '.join(problems)}")
    return 0


def cmd_verify(args) -> int:
    fw, data = _load_stock(args.firmware, verify=False)
    problems = fw.check_stock(data)
    sha = registry.sha256_bytes(data)
    ident = registry.identify(sha)
    if problems:
        print("INVALID:", "; ".join(problems))
        return 1
    if ident is None:
        print(f"VALID container, but UNKNOWN build (sha256 {sha[:12]}... not in registry)")
        return 0
    print(f"VALID stock firmware: {ident['name']} (sha256 {sha[:12]}...)")
    return 0


def cmd_build(args) -> int:
    fw, data = _load_stock(args.firmware, verify=not args.no_verify)
    sha = registry.sha256_bytes(data)
    mods = [Mod.load(p) for p in args.mod]
    try:
        patched = link(fw, sha, mods)
    except M8FWError as e:
        print("build failed:", e, file=sys.stderr)
        return 1
    patched.to_file(args.output)
    print(f"built {args.output}")
    print(f"  mods applied : {', '.join(m.id for m in mods) or '(none)'}")
    print(f"  payload_crc  : 0x{patched.payload_crc32():08X}")
    print(f"  sha256       : {patched.sha256()}")
    print("flash it the usual way (M8: PROJECT > SYSTEM SETTINGS > FIRMWARE UPDATE, or TyTools).")
    return 0


def cmd_make_mod(args) -> int:
    stock, stock_data = _load_stock(args.stock, verify=True)
    modfw, _ = _load_stock(args.modified, verify=False)
    patches = diff_payloads(bytes(stock.payload), bytes(modfw.payload), gap=args.gap)
    if not patches:
        print("no differences found between the two firmwares", file=sys.stderr)
        return 1
    mod = Mod(
        id=args.id,
        name=args.name or args.id,
        author=args.author,
        version=args.modversion,
        description=args.description,
        target={"model": stock.model, "stock_sha256": registry.sha256_bytes(stock_data)},
        patches=patches,
    )
    mod.save(args.output)
    changed = sum(len(p.data) for p in patches)
    print(f"wrote {args.output}")
    print(f"  patches      : {len(patches)}")
    print(f"  bytes changed: {changed}")
    print(f"  pinned to    : model {stock.model}, stock {mod.target['stock_sha256'][:12]}...")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="m8loader",
        description="Elekloader-style mod patcher for Dirtywave M8 firmware.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="inspect a firmware .bin")
    p.add_argument("firmware")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("verify", help="check a .bin is valid, identified stock firmware")
    p.add_argument("firmware")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("build", help="apply mods to stock firmware -> patched .bin")
    p.add_argument("firmware")
    p.add_argument("-m", "--mod", action="append", default=[], required=True,
                   help="a .m8mod file (repeatable)")
    p.add_argument("-o", "--output", required=True, help="output .bin path")
    p.add_argument("--no-verify", action="store_true",
                   help="skip stock-integrity check before patching")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("make-mod", help="diff a hand-edited .bin into a .m8mod")
    p.add_argument("stock")
    p.add_argument("modified")
    p.add_argument("-o", "--output", required=True, help="output .m8mod path")
    p.add_argument("--id", required=True, help="mod id (kebab-case)")
    p.add_argument("--name", help="human-readable name")
    p.add_argument("--author", default="", help="mod author")
    p.add_argument("--modversion", default="1.0.0", help="mod version")
    p.add_argument("--description", default="", help="mod description")
    p.add_argument("--gap", type=int, default=8,
                   help="coalesce diff runs separated by fewer than N identical bytes")
    p.set_defaults(func=cmd_make_mod)

    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
