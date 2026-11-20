"""
C for the M8: compile with arm-none-eabi-gcc (WSL on Windows, PATH elsewhere) and pack loadable mods.

    build_fixed(sources, base, entries)  -> (image bytes, {symbol: address})   code that runs where it is linked
    build_m8x(sources, defines)          -> (.m8x bytes, info)                 a mod core 0.3 loads from the SD card

An .m8x is linked at address 0. To find what needs relocating without parsing ELF, the image is linked twice,
at 0 and at RELOC_PROBE: every word that differs by exactly RELOC_PROBE is an absolute address into the image.
Any other difference (a movw/movt pair, say) is refused. docs/LOADER.md has the file format.
"""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from typing import Dict, List, Optional, Sequence, Tuple

SDK_INCLUDE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sdk", "include")
SDK_LIBC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sdk", "lib", "dl_libc.c")
GCC = "arm-none-eabi-gcc"
CFLAGS = ["-mcpu=cortex-m7", "-mthumb", "-mfloat-abi=hard", "-mfpu=fpv5-d16", "-Os", "-std=gnu11",
          "-ffreestanding", "-fno-common", "-ffunction-sections", "-fdata-sections", "-fno-builtin",
          "-Wall", "-Wextra", "-Wno-unused-parameter", "-Werror"]
RELOC_PROBE = 0x01000000
M8X_MAGIC = b"DLX1"
M8X_HEADER = struct.Struct("<4sIIII")          # magic, image, bss, nrel, crc32(image + relocations)
# DLX2 (core 0.7) adds where the image's writable part (.data) starts: the code and constants before it may run
# from flash (core installs a mod there when it doesn't fit in ITCM), the rest goes to RAM
M8X_MAGIC2 = b"DLX2"
M8X_HEADER2 = struct.Struct("<4sIIIII")        # magic, image, bss, nrel, crc32(image + relocations), data offset
DL_MOD_MAGIC = 0x314D4C44
EV_INFO = 0x00F0                # DL_INFO's entry in a mod's subscriptions (dl/mod.h): not an event


class CCError(RuntimeError):
    pass


def _wsl() -> bool:
    return sys.platform == "win32" and shutil.which(GCC) is None


def _path(p: str) -> str:
    """A host path as the compiler sees it."""
    p = os.path.abspath(p)
    if not _wsl():
        return p
    drive, rest = os.path.splitdrive(p)
    return "/mnt/" + drive[0].lower() + rest.replace("\\", "/")


def _run(tool: str, args: List[str]) -> str:
    cmd = (["wsl", "-e", tool] if _wsl() else [tool]) + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise CCError(f"{tool} failed:\n{r.stdout}{r.stderr}")
    return r.stdout


def available() -> bool:
    try:
        _run(GCC, ["--version"])
        return True
    except (CCError, OSError):
        return False


def _link(sources: Sequence[str], script: str, defines: Dict[str, str], work: str, tag: str,
          includes: Sequence[str], roots: Sequence[str] = ()) -> Tuple[bytes, Dict[str, int]]:
    ld = os.path.join(work, tag + ".ld")
    with open(ld, "w", newline="\n") as f:
        f.write(script)
    elf = os.path.join(work, tag + ".elf")
    args = list(CFLAGS) + ["-I" + _path(i) for i in includes] + ["-I" + _path(SDK_INCLUDE)]   # callers' first
    args += [f"-D{k}={v}" for k, v in defines.items()]
    args += ["-nostdlib", "-nostartfiles", "-Wl,--gc-sections", "-Wl,-T," + _path(ld), "-o", _path(elf)]
    args += ["-Wl,--undefined=" + r for r in roots]          # entry points --gc-sections must keep
    args += [_path(s) for s in sources] + ["-lgcc"]
    _run(GCC, args)
    binf = os.path.join(work, tag + ".bin")
    _run("arm-none-eabi-objcopy", ["-O", "binary", "--only-section=.head", "--only-section=.text",
                                   "--only-section=.data", _path(elf), _path(binf)])
    with open(binf, "rb") as f:
        image = f.read()
    syms = {}
    for line in _run("arm-none-eabi-nm", [_path(elf)]).splitlines():
        parts = line.split()
        if len(parts) == 3:
            syms[parts[2]] = int(parts[0], 16)
    return image, syms


_DISCARD = "/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) }"


def build_fixed(sources: Sequence[str], base: int, entries: Sequence[str], defines: Optional[Dict[str, str]] = None,
                includes: Sequence[str] = ()) -> Tuple[bytes, Dict[str, int]]:
    """Code linked to run at `base` (core's own C), keeping the functions named in `entries`. It may not have
    .data or .bss: there is nowhere to put it."""
    script = f"""SECTIONS {{
  . = 0x{base:08X};
  .text : {{ *(.text*) *(.rodata*) }}
  .data : {{ *(.data*) }}
  .bss  : {{ __bss_start = .; *(.bss*) *(COMMON) __bss_end = .; }}
  {_DISCARD}
}}
"""
    with tempfile.TemporaryDirectory() as work:
        image, syms = _link(sources, script, defines or {}, work, "fixed", includes, entries)
    missing = [e for e in entries if e not in syms]
    if missing:
        raise CCError("entry points not found: " + ", ".join(missing))
    if syms.get("__bss_end", 0) != syms.get("__bss_start", 0):
        raise CCError("core C has .bss; keep its state in the core RAM struct")
    return image, syms


def _mod_script(base: int) -> str:
    return f"""SECTIONS {{
  . = 0x{base:08X};
  .head : {{ KEEP(*(.dl_head)) }}
  .text : {{ *(.text*) *(.rodata*) }}
  . = ALIGN(4);
  __data_start = .;
  .data : {{ *(.data*) }}
  . = ALIGN(4);
  __image_end = .;
  .bss  : {{ *(.bss*) *(COMMON) }}
  . = ALIGN(4);
  __bss_end = .;
  {_DISCARD}
}}
"""


def build_m8x(sources: Sequence[str], defines: Optional[Dict[str, str]] = None,
              includes: Sequence[str] = ()) -> Tuple[bytes, dict]:
    with tempfile.TemporaryDirectory() as work:
        libc = os.path.join(work, "dl_libc.a")             # memcpy and friends, as a library: a mod's own win
        _run(GCC, list(CFLAGS) + ["-fno-tree-loop-distribute-patterns",   # or memcpy becomes a call to memcpy
                                  "-c", "-o", _path(libc + ".o"), _path(SDK_LIBC)])
        _run("arm-none-eabi-ar", ["rcs", _path(libc), _path(libc + ".o")])
        srcs = list(sources) + [libc]
        a, sa = _link(srcs, _mod_script(0), defines or {}, work, "a", includes)
        b, sb = _link(srcs, _mod_script(RELOC_PROBE), defines or {}, work, "b", includes)
    if len(a) != len(b):
        raise CCError("the two links differ in size")
    image_end, bss_end = sa["__image_end"], sa["__bss_end"]
    a = a.ljust(image_end, b"\0")[:image_end]
    b = b.ljust(image_end, b"\0")[:image_end]
    rel = []
    for off in range(0, image_end - image_end % 4, 4):
        x, y = struct.unpack_from("<I", a, off)[0], struct.unpack_from("<I", b, off)[0]
        if x == y:
            continue
        if (y - x) & 0xFFFFFFFF != RELOC_PROBE or x > bss_end:
            raise CCError(f"word at +0x{off:X} moves by 0x{(y - x) & 0xFFFFFFFF:X}: not a plain address "
                          "(build without movw/movt addressing)")
        rel.append(off)
    if struct.unpack_from("<I", a, 0)[0] != DL_MOD_MAGIC:
        raise CCError("the image does not start with DL_MOD(...): include dl/mod.h and declare the mod")
    relb = b"".join(struct.pack("<I", r) for r in rel)
    crc = zlib.crc32(relb, zlib.crc32(a)) & 0xFFFFFFFF
    bss = bss_end - image_end
    data = sa["__data_start"]
    blob = M8X_HEADER2.pack(M8X_MAGIC2, len(a), bss, len(rel), crc, data) + a + relb
    return blob, {"image": len(a), "bss": bss, "relocations": len(rel), "data": data, "symbols": sa}


def parse_m8x(blob: bytes) -> dict:
    """Check an .m8x the way the core does and read its dl_mod header (for tools and tests)."""
    if len(blob) < M8X_HEADER.size:
        raise CCError("too short for an .m8x")
    magic = blob[:4]
    if magic == M8X_MAGIC2 and len(blob) >= M8X_HEADER2.size:
        _m, image, bss, nrel, crc, data = M8X_HEADER2.unpack_from(blob)
        hs = M8X_HEADER2.size
        if data > image or data & 3:
            raise CCError("the writable part starts outside the image")
    elif magic == M8X_MAGIC:
        _m, image, bss, nrel, crc = M8X_HEADER.unpack_from(blob)
        hs, data = M8X_HEADER.size, 0
    else:
        raise CCError("not an .m8x")
    img = blob[hs:hs + image]
    relb = blob[hs + image:hs + image + 4 * nrel]
    if len(img) != image or len(relb) != 4 * nrel:
        raise CCError("truncated .m8x")
    if zlib.crc32(relb, zlib.crc32(img)) & 0xFFFFFFFF != crc:
        raise CCError("checksum mismatch")
    rel = [struct.unpack_from("<I", relb, 4 * i)[0] for i in range(nrel)]
    mag, abi_, nsubs, pid, pver, ptitle, psubs, fw = struct.unpack_from("<IHHIIIII", img, 0)
    if mag != DL_MOD_MAGIC:
        raise CCError("image does not start with a dl_mod")

    def cstr(p):
        return img[p:img.index(b"\0", p)].decode("ascii", "replace")

    subs, info = [], {}
    for i in range(nsubs):
        ev, order, fn = struct.unpack_from("<HHI", img, psubs + 8 * i)
        if ev == EV_INFO:                             # DL_INFO: who made it and what it does, not a hook
            author, about = struct.unpack_from("<II", img, fn)
            info = {"author": cstr(author) if author else "", "about": cstr(about) if about else ""}
        else:
            subs.append({"event": ev, "order": order, "handler": fn})
    return {"image": image, "bss": bss, "data": data, "header": hs, "relocations": rel, "abi": abi_, "id": cstr(pid),
            "version": cstr(pver), "title": cstr(ptitle), "subscribe": subs, "fw": fw, "info": info}


# ---- the command line: build a mod for one firmware or all of them -------------------------------------------------
# The targets the SDK builds for (the shop's site/shop/meta.json lists the same; tests/test_cc_cli.py checks they
# agree). A mod includes "m8-headless/fw.h" whatever it targets: for the Model:02 the build puts that firmware's header
# under that name (alias), and defines M8_MODEL02.
TARGETS = {
    "m8-headless": {"label": "M8 Headless", "firmware": "6.6.4A", "defines": {}, "alias": None},
    "m8-model02": {"label": "M8 Model:02", "firmware": "6.6.2A", "defines": {"M8_MODEL02": "1"}, "alias": "6.6.2A"},
    "m8-model02-664": {"label": "M8 Model:02", "firmware": "6.6.4A", "defines": {"M8_MODEL02": "1"},
                       "alias": "6.6.4A"},
}


def build_target(sources: Sequence[str], target: str, defines: Optional[Dict[str, str]] = None) -> Tuple[bytes, dict]:
    """build_m8x for one of TARGETS: its defines (plus yours) and its fw.h as m8-headless/fw.h."""
    if target not in TARGETS:
        raise CCError(f"unknown target {target!r}: one of {', '.join(TARGETS)}")
    t = TARGETS[target]
    includes: List[str] = []
    if t["alias"]:
        from dirtyloader.core.build_model02 import _alias_dir   # (imports this module: not at the top)
        includes.append(_alias_dir(t["alias"]))
    return build_m8x(sources, defines={**t["defines"], **(defines or {})} or None, includes=includes)


def _sources(paths: Sequence[str]) -> List[str]:
    out: List[str] = []
    for p in paths:
        if os.path.isdir(p):
            found = sorted(os.path.join(p, f) for f in os.listdir(p) if f.endswith(".c"))
            if not found:
                raise CCError(f"{p}: no .c files in it")
            out += found
        elif os.path.isfile(p):
            out.append(p)
        else:
            raise CCError(f"{p}: no such file or folder")
    return out


def _event_names() -> Dict[int, str]:
    import re
    with open(os.path.join(SDK_INCLUDE, "dl", "mod.h"), encoding="utf-8") as f:
        text = f.read()
    return {int(v, 16): n.lower() for n, v in re.findall(r"\b(EV_[A-Z0-9_]+)\s*=\s*(0x[0-9A-Fa-f]+)", text)}


def describe(blob: bytes) -> str:
    p = parse_m8x(blob)
    names = _event_names()
    hooks = ", ".join(f"{names.get(s['event'], hex(s['event']))}@{s['order']}" for s in p["subscribe"])
    where = "flash or ITCM (DLX2)" if p["data"] else "ITCM"
    out = (f"{p['id']} {p['version']} \"{p['title']}\": {len(blob)} bytes, code+data {p['image']}, bss {p['bss']}, "
           f"{len(p['relocations'])} relocations, firmware {p['fw']:#010x}, runs from {where}\n  hooks: {hooks}")
    if p["info"]:
        out += f"\n  by {p['info']['author'] or '?'}: {p['info']['about']}"
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m dirtyloader.cc",
                                 description="Build loadable mods (.m8x) for core 0.7 from C, or describe one.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="compile a mod's .c files (or its folder) into an .m8x per target")
    b.add_argument("paths", nargs="+", help="the mod's folder, or its .c files")
    b.add_argument("--target", "-t", action="append", choices=list(TARGETS) + ["all"],
                   help="firmware to build for (repeat it; default all)")
    b.add_argument("--out", "-o", default="build/mods",
                   help="folder for <target>/<id>.m8x (default build/mods), or a .m8x file for a single target")
    b.add_argument("-D", dest="defines", action="append", default=[], metavar="NAME[=VALUE]", help="a define")
    i = sub.add_parser("info", help="check an .m8x the way core does and show its header")
    i.add_argument("files", nargs="+")
    sub.add_parser("targets", help="list the firmwares mods are built for")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "targets":
            for k, t in TARGETS.items():
                print(f"{k:16} {t['label']} {t['firmware']}")
            return 0
        if args.cmd == "info":
            for f in args.files:
                with open(f, "rb") as fh:
                    print(f"{f}: " + describe(fh.read()))
            return 0
        targets = list(TARGETS) if not args.target or "all" in args.target else list(dict.fromkeys(args.target))
        if args.out.endswith(".m8x") and len(targets) != 1:
            raise CCError("--out names one file: give a single --target, or a folder")
        defines = dict(d.split("=", 1) if "=" in d else (d, "1") for d in args.defines)
        srcs = _sources(args.paths)
        for t in targets:
            blob, _info = build_target(srcs, t, defines)
            p = parse_m8x(blob)
            path = args.out if args.out.endswith(".m8x") else os.path.join(args.out, t, p["id"] + ".m8x")
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(blob)
            print(f"{t}: {path}\n  " + describe(blob))
        return 0
    except (CCError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())