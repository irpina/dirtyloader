"""
"2 mods, 1 hook" -- prove the event bus lets several mods hook one event.

Installs the Core plus two independent demo mods, each registering its own
handler on TICK. The linker must auto-allocate a distinct Core table slot per
mod so all three handlers (Core's bundled demo + the two mods) coexist and run
each frame, instead of the last mod winning a single call site.

Software-only (no hardware). Run:
    python -m m8loader.core.test_hooks [stock.bin]
"""
import json
import os
import struct
import sys

from m8loader.m8fw import M8Firmware, M8FWError
from m8loader.linker import link
from m8loader import registry
from m8loader.core import abi, builder

STOCK = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\zacha\Downloads\M8Firmware_V6_6_2\Firmware\Model02\M8_V6_6_2A_MODEL02.bin"
BINDINGS = os.path.join(os.path.dirname(__file__), "bindings", "m8_6.6.2A_model02.json")


def ok(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise SystemExit(1)


with open(STOCK, "rb") as f:
    data = f.read()
sha = registry.sha256_bytes(data)
fw = M8Firmware.parse(data, verify=True)
b = json.load(open(BINDINGS))
hook_site = int(b["hook_sites"]["TICK"]["patch_at"], 16)
loop_addr = int(b["symbols"]["loop"], 16)

core = builder.build_core_mod(fw, sha, hook_site, loop_addr)
# two independent mods, each with its own handler in its own cave slot
mod_a = builder.build_handler_mod(fw, sha, "demo-a", "Demo A", 0x60000460, int(abi.Event.TICK))
mod_b = builder.build_handler_mod(fw, sha, "demo-b", "Demo B", 0x60000470, int(abi.Event.TICK))

patched = link(fw, sha, [core, mod_a, mod_b])
M8Firmware.parse(patched.build(), verify=True)
ok("core + 2 mods link into a CRC-valid image", True)

# read back the hook table
table_off = (abi.CORE_REGION_ADDR - fw.load_addr) + 0x10
entries = []
for i in range(6):
    ev, fl, hn = struct.unpack_from(abi.HOOK_ENTRY_FMT, bytes(patched.payload),
                                    table_off + i * abi.HOOK_ENTRY_SIZE)
    entries.append((ev, fl, hn))
    if ev or hn:
        print(f"  slot{i}: event=0x{ev:04X} flags=0x{fl:04X} handler=0x{hn:08X}")

tick = [(ev, fl, hn) for ev, fl, hn in entries if ev == int(abi.Event.TICK) and hn]
ok("three handlers registered on TICK", len(tick) == 3)
ok("all three are enabled", all(fl & abi.FLAG_ENABLED for _ev, fl, _hn in tick))
handlers = {hn for _ev, _fl, hn in tick}
ok("handlers are distinct (no mod clobbered another)", len(handlers) == 3)
ok("demo-a handler present", (0x60000460 | 1) in handlers)
ok("demo-b handler present", (0x60000470 | 1) in handlers)

# a handler mod without the Core must be rejected
try:
    link(fw, sha, [mod_a])
    ok("handler mod without Core is rejected", False)
except M8FWError:
    ok("handler mod without Core is rejected", True)

print("\nALL HOOK CHECKS PASSED -- multiple mods share one event via auto-allocated slots.")
