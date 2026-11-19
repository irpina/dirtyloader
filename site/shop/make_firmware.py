"""
Build the shop's firmware patches: for each M8 firmware core supports, build core against Dirtywave's stock file
(as dirtyloader.core.build_headless / build_model02 do) and write site/shop/firmware/<target>.json, a patch the
page's "Get started" applies in the browser to the user's own copy of that file.

    python site/shop/make_firmware.py [--headless <stock .hex>] [--model02 <6.6.2A .bin>] [--model02-664 <6.6.4A .bin>]

Needs the ARM compiler and Dirtywave's stock files (default: where they unzip in ~/Downloads). The patch holds no
Dirtywave firmware: it is the difference between the stock image and the built one, and any run of 4 or more bytes
of that difference which also occurs in the stock image is written as "copy from the stock image at x" rather than
as bytes, so only bytes that come from dirtyloader are in the file. Each patch names the stock file by its sha256 and
the image it makes by its sha256, and the page checks both. Commit the .json files: CI has no ARM compiler.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from dirtyloader import ihex  # noqa: E402
from dirtyloader.core import builder  # noqa: E402
from dirtyloader.linker import link  # noqa: E402
from dirtyloader.m8fw import M8Firmware  # noqa: E402

DL = os.path.expanduser("~/Downloads")
TARGETS = {
    "m8-model02": {
        "label": "M8 Model:02", "firmware": "6.6.2A", "kind": "bin",
        "stock": os.path.join(DL, "M8Firmware_V6_6_2", "Firmware", "Model02", "M8_V6_6_2A_MODEL02.bin"),
        "bindings": "m8_6.6.2A_model02.json", "out": "M8_V6_6_2A_MODEL02_dirtyloader",
        "get": "https://github.com/Dirtywave/M8Firmware/raw/main/Releases/M8Firmware_V6_6_2.zip",
        "get_note": "M8Firmware_V6_6_2.zip, from Dirtywave's firmware archive (Releases)",
    },
    "m8-model02-664": {
        "label": "M8 Model:02", "firmware": "6.6.4A", "kind": "bin",
        "stock": os.path.join(DL, "M8Firmware_V6_6_4", "Firmware", "Model02", "M8_V6_6_4A_MODEL02.bin"),
        "bindings": "m8_6.6.4A_model02.json", "out": "M8_V6_6_4A_MODEL02_dirtyloader",
        "get": "https://github.com/Dirtywave/M8Firmware/raw/main/M8Firmware.zip",
        "get_note": "M8Firmware.zip, Dirtywave's current download (6.6.4A)",
    },
    "m8-headless": {
        "label": "M8 Headless", "firmware": "6.6.4A", "kind": "hex",
        "stock": os.path.join(DL, "M8Headless_6_6_4A", "M8_V6_6_4A_HEADLESS.hex"),
        "bindings": "m8_6.6.4A_headless.json", "out": "M8_V6_6_4A_HEADLESS_dirtyloader",
        "get": "https://github.com/Dirtywave/M8HeadlessFirmware/tree/main/Releases",
        "get_note": "M8_V6_6_4A_HEADLESS.hex, from Dirtywave's Headless firmware releases",
    },
}
MIN_COPY = 4          # a run this long that is in the stock image is copied from it, never shipped


def core_version() -> str:
    src = open(os.path.join(ROOT, "dirtyloader", "core", "c", "core03.c"), encoding="utf-8").read()
    i = src.index('"dirtyloader core ') + len('"dirtyloader core ')
    return src[i:src.index("\\n", i)]


def build(target: str, path: str):
    """(stock file bytes, stock payload, built payload, M8Firmware header fields) for one target."""
    t = TARGETS[target]
    raw = open(path, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    b = json.load(open(os.path.join(ROOT, "dirtyloader", "core", "bindings", t["bindings"])))
    if sha != b["stock_sha256"]:
        raise SystemExit(f"{path} is not {b['firmware']} (sha256 {sha[:12]}...)")
    fw = ihex.to_firmware(ihex.read(raw.decode("ascii"))) if t["kind"] == "hex" else M8Firmware.parse(raw)
    core = builder.build_core03_mod(fw, sha, b)
    patched = link(fw, sha, [core])
    return raw, bytes(fw.payload), bytes(patched.payload), fw


def diff_regions(stock: bytes, out: bytes, gap: int = 8):
    base = stock + b"\xFF" * (len(out) - len(stock))
    regions, start, last = [], None, None
    for k in range(len(out)):
        if out[k] != base[k]:
            if start is None:
                start = k
            elif k - last > gap:
                regions.append((start, last + 1))
                start = k
            last = k
    if start is not None:
        regions.append((start, last + 1))
    return regions


def encode(stock: bytes, out: bytes):
    """The ops that turn `stock` (padded with 0xFF to len(out)) into `out`: [at, base64] puts the bytes, and
    [at, src, n] copies n bytes from the stock image at src."""
    regions = diff_regions(stock, out)
    want = {out[k:k + MIN_COPY] for a, b in regions for k in range(a, b - MIN_COPY + 1)}
    where = {}
    for k in range(len(stock) - MIN_COPY + 1):
        g = stock[k:k + MIN_COPY]
        if g in want:
            lst = where.setdefault(g, [])
            if len(lst) < 48:
                lst.append(k)
    ops = []
    for a, b in regions:
        p, lit = a, bytearray()
        lit_at = a

        def flush():
            if lit:
                ops.append([lit_at, base64.b64encode(bytes(lit)).decode("ascii")])
                lit.clear()
        while p < b:
            best, src = 0, 0
            for s in where.get(out[p:p + MIN_COPY], ()) if p + MIN_COPY <= b else ():
                n = 0
                while p + n < b and s + n < len(stock) and stock[s + n] == out[p + n]:
                    n += 1
                if n > best:
                    best, src = n, s
            if best >= MIN_COPY:
                flush()
                ops.append([p, src, best])
                p += best
                lit_at = p
            else:
                if not lit:
                    lit_at = p
                lit.append(out[p])
                p += 1
        flush()
    return ops


def apply(stock: bytes, n: int, ops) -> bytes:
    """What the page does (firmware.js applyPatch), for checking the patch here."""
    img = bytearray(stock[:n] + b"\xFF" * (n - len(stock)))
    for op in ops:
        if len(op) == 2:
            d = base64.b64decode(op[1])
            img[op[0]:op[0] + len(d)] = d
        else:
            img[op[0]:op[0] + op[2]] = stock[op[1]:op[1] + op[2]]
    return bytes(img)


def literal_runs_in_stock(stock: bytes, ops) -> int:
    """How many MIN_COPY-byte windows of shipped bytes also occur in the stock image (must be 0)."""
    grams = {stock[k:k + MIN_COPY] for k in range(len(stock) - MIN_COPY + 1)}
    n = 0
    for op in ops:
        if len(op) == 2:
            d = base64.b64decode(op[1])
            n += sum(1 for k in range(len(d) - MIN_COPY + 1) if d[k:k + MIN_COPY] in grams)
    return n


def main(argv) -> int:
    paths = {t: v["stock"] for t, v in TARGETS.items()}
    for flag, t in (("--headless", "m8-headless"), ("--model02", "m8-model02"), ("--model02-664", "m8-model02-664")):
        if flag in argv:
            paths[t] = argv[argv.index(flag) + 1]
    os.makedirs(os.path.join(HERE, "firmware"), exist_ok=True)
    ver = core_version()
    index = []
    for target, path in paths.items():
        if not os.path.exists(path):
            print(f"{target}: no stock file at {path}, skipped")
            continue
        t = TARGETS[target]
        raw, stock, out, fw = build(target, path)
        if len(out) < len(stock):
            raise SystemExit(f"{target}: the built image is shorter than the stock one")
        ops = encode(stock, out)
        if apply(stock, len(out), ops) != out:
            raise SystemExit(f"{target}: the patch does not rebuild the image")
        leaks = literal_runs_in_stock(stock, ops)
        if leaks:
            raise SystemExit(f"{target}: {leaks} shipped runs also occur in the stock image")
        patch = {
            "format": 1, "target": target, "label": t["label"], "firmware": t["firmware"], "core": ver,
            "stock": {"kind": t["kind"], "name": os.path.basename(path), "size": len(raw),
                      "sha256": hashlib.sha256(raw).hexdigest(), "payload": len(stock),
                      "get": t["get"], "get_note": t["get_note"]},
            "out": {"name": f"{t['out']}-core{ver}", "payload": len(out), "load_addr": fw.load_addr,
                    "version": fw.version, "sha256": hashlib.sha256(out).hexdigest()},
            "ops": ops,
        }
        if t["kind"] == "bin":
            built = M8Firmware(version=fw.version, load_addr=fw.load_addr, payload=bytearray(out)).build()
            patch["out"]["bin_sha256"] = hashlib.sha256(built).hexdigest()
        dest = os.path.join(HERE, "firmware", target + ".json")
        with open(dest, "w", encoding="utf-8", newline="\n") as f:
            json.dump(patch, f, separators=(",", ":"))
            f.write("\n")
        shipped = sum(len(base64.b64decode(o[1])) for o in ops if len(o) == 2)
        copied = sum(o[2] for o in ops if len(o) == 3)
        print(f"{target}: core {ver}, {len(ops)} ops, {shipped} bytes shipped, {copied} copied from the stock image,"
              f" {os.path.getsize(dest)} bytes -> {os.path.relpath(dest, ROOT)}")
        index.append({k: patch[k] for k in ("target", "label", "firmware", "core")} | {
            "stock_sha256": patch["stock"]["sha256"], "stock_name": patch["stock"]["name"], "kind": t["kind"],
            "get": t["get"], "get_note": t["get_note"], "file": f"firmware/{target}.json"})
    if index:
        old = []
        ipath = os.path.join(HERE, "firmware", "index.json")
        if os.path.exists(ipath):
            old = [e for e in json.load(open(ipath)) if e["target"] not in {e2["target"] for e2 in index}]
        with open(ipath, "w", encoding="utf-8", newline="\n") as f:
            json.dump(sorted(old + index, key=lambda e: e["target"]), f, indent=1)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
