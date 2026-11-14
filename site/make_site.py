"""
Prepare the static site for GitHub Pages.

  1. zip the pure-Python `dirtyloader` package into site/engine/dirtyloader.zip
     (Pyodide unpacks it in the browser and imports it)
  2. scan site/mods/*.m8mod and write site/catalog.json (the mod list the page shows)

No firmware is needed or touched. Run from the repo root (CI does), or anywhere:

    python site/make_site.py
"""
from __future__ import annotations

import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from dirtyloader.m8mod import Mod  # noqa: E402
from dirtyloader import __version__  # noqa: E402

PKG = os.path.join(ROOT, "dirtyloader")
ENGINE_DIR = os.path.join(HERE, "engine")
MODS_DIR = os.path.join(HERE, "mods")

# Only the stdlib runtime path is shipped to the browser; RE tooling and tests are not.
SKIP_DIRS = {"re", "__pycache__", "bindings"}
SKIP_FILES = {"mkmod.py", "lint.py", "cli.py", "__main__.py", "builder.py", "build_headless.py"}
SKIP_PREFIX = ("test_",)


def _include(rel: str) -> bool:
    parts = rel.split("/")
    if any(p in SKIP_DIRS for p in parts):
        return False
    name = parts[-1]
    if name in SKIP_FILES or name.startswith(SKIP_PREFIX):
        return False
    return name.endswith(".py")


def build_engine_zip() -> int:
    os.makedirs(ENGINE_DIR, exist_ok=True)
    out = os.path.join(ENGINE_DIR, "dirtyloader.zip")
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _dirs, files in os.walk(PKG):
            for f in files:
                full = os.path.join(base, f)
                # path inside the package, e.g. "core/abi.py"
                inner = os.path.relpath(full, PKG).replace("\\", "/")
                if not _include(inner):
                    continue
                # store at "dirtyloader/<inner>" so `import dirtyloader` works
                z.write(full, f"dirtyloader/{inner}")
                n += 1
    return n


def build_catalog() -> int:
    mods = []
    for f in sorted(os.listdir(MODS_DIR)) if os.path.isdir(MODS_DIR) else []:
        if not f.endswith(".m8mod"):
            continue
        mod = Mod.load(os.path.join(MODS_DIR, f))
        mods.append({
            "id": mod.id,
            "version": mod.version,
            "title": mod.title or mod.id,
            "description": mod.description,
            "category": mod.category or ("Core" if mod.id == "core" else "Mods"),
            "author": mod.author,
            "license": mod.license,
            "file": f"mods/{f}",
            "requires": mod.requires,
            "provides": mod.events,
            "core": mod.core,
            "is_core": mod.id == "core",
            "firmware": (mod.target or {}).get("firmware", ""),
            "device": (mod.target or {}).get("device", ""),
            "sites": len(mod.sites),
            "subscriptions": len(mod.subscribe),
        })
    catalog = {"generator": f"dirtyloader {__version__}", "engine": "engine/dirtyloader.zip",
               "mods": mods}
    with open(os.path.join(HERE, "catalog.json"), "w", encoding="utf-8") as fh:
        json.dump(catalog, fh, indent=1)
        fh.write("\n")
    return len(mods)


if __name__ == "__main__":
    nz = build_engine_zip()
    nm = build_catalog()
    print(f"engine/dirtyloader.zip: {nz} module(s)")
    print(f"catalog.json: {nm} mod(s)")
