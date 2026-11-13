"""
End-to-end proof of the mod pipeline against the real stock firmware:

  * registry identifies the supplied stock by sha256
  * the example .m8mod loads, targets, and applies cleanly
  * the built image re-validates as a well-formed container
  * make-mod (diff_payloads) round-trips: diffing stock vs built reproduces the
    example mod's exact patch
  * conflict detection and target pinning reject bad inputs

The stock firmware is only read. Pass its path as argv[1], or rely on the
default below. Run:  python -m dirtyloader.test_pipeline  [stock.bin]
"""
import os
import sys

from dirtyloader.m8fw import M8Firmware, M8FWError
from dirtyloader.m8mod import Mod, ModPatch
from dirtyloader.linker import link, diff_payloads, ConflictError
from dirtyloader import registry

STOCK = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\zacha\Downloads\M8Firmware_V6_6_2\Firmware\Model02\M8_V6_6_2A_MODEL02.bin"
MODS_DIR = os.path.join(os.path.dirname(__file__), "..", "mods")
EXAMPLE = os.path.join(MODS_DIR, "demo-rename-scale.m8mod")


def ok(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise SystemExit(1)


with open(STOCK, "rb") as f:
    stock_data = f.read()

stock = M8Firmware.parse(stock_data, verify=True)
sha = registry.sha256_bytes(stock_data)
print(stock.summary())
print("sha256:", sha, "\n")

# registry
ident = registry.identify(sha)
ok("registry identifies the stock firmware", ident is not None)

# example mod applies
mod = Mod.load(EXAMPLE)
ok("example .m8mod loads", mod.id == "demo-rename-scale")
patched = link(stock, sha, [mod])
idx = patched.payload.find(b"DIRTYWAVE MAJ ")
ok("patched payload contains the modded label", idx >= 0)
ok("original stock still untouched (no mutation)", stock.payload.find(b"DIRTYWAVE MAJ ") < 0)

# built image re-validates
built = patched.build()
M8Firmware.parse(built, verify=True)
ok("built image re-parses and both CRCs self-validate", True)
ok("built image is same size as stock", len(built) == len(stock_data))

# make-mod round trip: diff stock vs built reproduces the example patch
regen = diff_payloads(bytes(stock.payload), bytes(patched.payload))
ok("diff finds exactly one changed run", len(regen) == 1)
want = mod.patches[0]
got = regen[0]
ok("regenerated patch offset matches example", got.offset == stock.addr_to_offset(want.addr))
ok("regenerated patch data matches example", got.data == want.data)
ok("regenerated patch expect matches example", got.expect == want.expect)

# target pin rejects the wrong stock
badmod = Mod.load(EXAMPLE)
badmod.target = dict(badmod.target, stock_sha256="00" * 32)
try:
    link(stock, sha, [badmod])
    ok("wrong stock_sha256 pin is rejected", False)
except M8FWError:
    ok("wrong stock_sha256 pin is rejected", True)

# overlap between two mods is a conflict
m_a = Mod(id="a", name="A", patches=[
    ModPatch(addr=want.addr, expect=want.expect, data=want.data, note="x")])
m_b = Mod(id="b", name="B", patches=[
    ModPatch(addr=want.addr, expect=want.expect, data=want.data, note="y")])
try:
    link(stock, sha, [m_a, m_b])
    ok("two mods editing the same bytes conflict", False)
except M8FWError:
    ok("two mods editing the same bytes conflict", True)

# unmet requirement is rejected
m_need = Mod(id="needs", name="N", requires=["missing"], patches=[
    ModPatch(addr=want.addr, expect=want.expect, data=want.data)])
try:
    link(stock, sha, [m_need])
    ok("unmet 'requires' is rejected", False)
except M8FWError:
    ok("unmet 'requires' is rejected", True)

print("\nALL PIPELINE CHECKS PASSED -- mod format, linker, and make-mod round-trip work end to end.")
