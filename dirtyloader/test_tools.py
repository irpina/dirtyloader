"""
Prove the mod-authoring tools (mkmod, lint) against the real firmware and the
repo's own source folders (mods/core, examples/hello-tick):

  * mkmod builds the core and hello-tick from their mod.json + .s sources
  * lint passes them and they ship no stock bytes
  * they link together and hello-tick's handler lands in a Core table slot

Run:  python -m dirtyloader.test_tools [stock.bin]
"""
import os
import struct
import sys

from dirtyloader.m8fw import M8Firmware
from dirtyloader.mkmod import build_from_source
from dirtyloader.lint import check_mod
from dirtyloader.linker import link
from dirtyloader import registry
from dirtyloader.core import abi

ROOT = os.path.dirname(os.path.dirname(__file__))
STOCK = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\zacha\Downloads\M8Firmware_V6_6_2\Firmware\Model02\M8_V6_6_2A_MODEL02.bin"


def ok(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise SystemExit(1)


data = open(STOCK, "rb").read()
fw = M8Firmware.parse(data, verify=True)
sha = registry.sha256_bytes(data)

core = build_from_source(os.path.join(ROOT, "mods", "core"), STOCK)
ok("mkmod builds the core from source", core.id == "core" and len(core.sites) == 2)
ok("core provides TICK", core.events == ["TICK"])
ok("lint passes the core", check_mod(core) == [])

hello = build_from_source(os.path.join(ROOT, "examples", "hello-tick"), STOCK)
ok("mkmod builds hello-tick from source", hello.id == "hello-tick")
ok("hello-tick has one site and one subscription",
   len(hello.sites) == 1 and len(hello.subscribe) == 1)
ok("hello-tick requires core and targets this firmware",
   "core" in hello.requires and hello.target["bin_sha256"] == sha)
ok("lint passes hello-tick", check_mod(hello) == [])

# no stock bytes are shipped: every site part is author hex, guarded by a hash
shipped = [p for s in hello.sites for p in s.new if p[0] == "hex"]
ok("hello-tick ships only author hex (no stock bytes)", len(shipped) == len(hello.sites))
ok("hello-tick site is guarded by a stock hash", all(len(s.stock_sha256) == 64 for s in hello.sites))

built = link(fw, sha, [core, hello])
M8Firmware.parse(built.build(), verify=True)
ok("core + hello-tick link into a CRC-valid image", True)

# hello-tick's handler is registered on TICK in a free slot (slot 0 is the core's demo)
table_off = (abi.CORE_REGION_ADDR - fw.load_addr) + 0x10
hero = hello.subscribe[0]["handler"]
found = any(
    struct.unpack_from(abi.HOOK_ENTRY_FMT, bytes(built.payload), table_off + i * abi.HOOK_ENTRY_SIZE)
    == (int(abi.Event.TICK), abi.FLAG_ENABLED, hero)
    for i in range(abi.MAX_HOOKS)
)
ok("hello-tick's handler is in the Core hook table on TICK", found)

print("\nALL TOOL CHECKS PASSED -- mkmod and lint build and validate mods from source.")
