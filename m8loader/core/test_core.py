"""
Verify the Core builder end to end against real firmware:

  * build the `core` mod (dispatcher + table + main-loop detour)
  * apply it through the linker and rebuild a valid .bin (CRCs recomputed)
  * disassemble the installed cave and the patched call site to confirm the
    machine code is correct (assemble -> install -> disassemble round trip)

Software-only: it proves the bytes are right, not that they run (that needs a
Teensy). The stock firmware is read-only. Run:
    python -m m8loader.core.test_core [stock.bin]
"""
import json
import os
import sys

from m8loader.m8fw import M8Firmware
from m8loader.linker import link
from m8loader import registry
from m8loader.core import abi, builder

import capstone

STOCK = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\zacha\Downloads\M8Firmware_V6_6_2\Firmware\Model02\M8_V6_6_2A_MODEL02.bin"
BINDINGS = os.path.join(os.path.dirname(__file__), "bindings", "m8_6.6.2A_model02.json")

md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB + capstone.CS_MODE_MCLASS)


def ok(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise SystemExit(1)


def dis(payload, addr, n):
    off = (addr & ~1) - 0x60000000
    out = []
    for i in md.disasm(bytes(payload[off:off + n * 4]), addr & ~1):
        out.append((i.address, i.mnemonic, i.op_str))
        if len(out) >= n:
            break
    return out


with open(STOCK, "rb") as f:
    data = f.read()
sha = registry.sha256_bytes(data)
fw = M8Firmware.parse(data, verify=True)

b = json.load(open(BINDINGS))
hook_site = int(b["hook_sites"]["TICK"]["patch_at"], 16)     # 0x600AE052
loop_addr = int(b["symbols"]["loop"], 16)                    # 0x60081BD4

print(f"stock: {b['firmware']}  hook_site=0x{hook_site:08X} loop=0x{loop_addr:08X}\n")

mod = builder.build_core_mod(fw, sha, hook_site, loop_addr)
ok("core mod built with 2 patches", len(mod.patches) == 2)

patched = link(fw, sha, [mod])
built = patched.build()
M8Firmware.parse(built, verify=True)
ok("patched image re-parses; both CRCs valid", True)
ok("size unchanged", len(built) == len(data))

pay = patched.payload

# 1. magic installed at region start
ok("Core magic at 0x60000200",
   bytes(pay[0x200:0x208]) == abi.CORE_MAGIC)

# 2. hook-site now detours to the trampoline
site = dis(pay, hook_site, 1)[0]
img = builder.build_region(loop_addr)
print(f"  hook site: 0x{site[0]:08X}: {site[1]} {site[2]}")
ok("hook site is a bl", site[1] == "bl")
ok("hook site targets tramp_tick",
   int(site[2].lstrip("#"), 16) == img.tramp_tick)

# 3. dispatcher disassembles correctly
print("\n  dispatcher @0x%08X:" % builder.CODE)
dh = dis(pay, builder.CODE, 8)
for a, m, o in dh:
    print(f"    0x{a:08X}: {m:<7} {o}")
ok("dispatcher starts with push {r4,r5,r6,r7,lr}",
   dh[0][1] == "push" and "lr" in dh[0][2])

# 4. trampoline: push lr; movs r0,#TICK; bl dispatch; pop lr; b.w loop
print("\n  tramp_tick @0x%08X:" % img.tramp_tick)
tt = dis(pay, img.tramp_tick, 5)
for a, m, o in tt:
    print(f"    0x{a:08X}: {m:<7} {o}")
ok("tramp sets r0 = TICK",
   any(m == "movs" and o == "r0, #0x10" for a, m, o in tt))
ok("tramp calls dispatch_handlers",
   any(m == "bl" and int(o.lstrip('#'), 16) == builder.CODE for a, m, o in tt))
ok("tramp tail-calls loop()",
   any(m in ("b", "b.w") and int(o.lstrip('#'), 16) == loop_addr for a, m, o in tt))

# 5. demo handler is bx lr, and registered in table slot 0
demo = dis(pay, img.demo_handler, 1)[0]
ok("demo handler is bx lr", demo[1] == "bx" and demo[2] == "lr")
import struct
ev, fl, hnd = struct.unpack_from(abi.HOOK_ENTRY_FMT, bytes(pay), 0x210)
ok("table slot0 event = TICK", ev == int(abi.Event.TICK))
ok("table slot0 enabled", fl & abi.FLAG_ENABLED)
ok("table slot0 handler = demo|thumb", hnd == (img.demo_handler | 1))

print("\nALL CORE CHECKS PASSED -- dispatcher/trampoline/table assemble and install correctly.")
