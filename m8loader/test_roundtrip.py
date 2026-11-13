"""
Proves the m8fw foundation against the real stock firmware:

  1. parse + verify stock (both CRCs must validate)
  2. rebuild with no changes  -> must be byte-identical to the original file
  3. apply a real byte patch   -> payload CRC changes, header stays valid,
                                  re-parse of the rebuilt image succeeds

The original firmware file is only ever read. All output goes to the scratchpad.
Pass the stock .bin path as argv[1].
"""
import sys
import hashlib

from m8loader.m8fw import M8Firmware, Patch, crc32, HEADER_SIZE

SRC = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\zacha\Downloads\M8Firmware_V6_6_2\Firmware\Model02\M8_V6_6_2A_MODEL02.bin"

with open(SRC, "rb") as f:
    original = f.read()

def ok(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise SystemExit(1)

print(f"source: {SRC}")
print(f"sha256: {hashlib.sha256(original).hexdigest()}\n")

# 1. parse + verify
fw = M8Firmware.parse(original, verify=True)
print(fw.summary(), "\n")
ok("magic + both CRCs verify as valid stock", True)  # parse(verify=True) would have raised
ok("model is 02", fw.model == 2)
ok("load address is 0x60000000", fw.load_addr == 0x60000000)

# 2. lossless round trip
rebuilt = fw.build()
ok("no-op rebuild is byte-identical to original", rebuilt == original)

# 3. live patch with CRC recompute
# find a plaintext UI string and overwrite it with same-length bytes
needle = b"HARMONIC MAJOR"
idx = fw.payload.find(needle)
ok(f"located demo string {needle!r} in payload", idx >= 0)

before_crc = fw.payload_crc32()
replacement = b"MODDED  MAJOR"[: len(needle)].ljust(len(needle), b" ")
fw.apply(Patch(offset=idx, new=replacement, expected=needle, note="demo string swap"))
after_crc = fw.payload_crc32()

ok("payload CRC changed after patch", before_crc != after_crc)

patched = fw.build()
ok("patched image size unchanged", len(patched) == len(original))
ok("patched differs from original", patched != original)

# the rebuilt image must itself be a valid stock-shaped container
fw2 = M8Firmware.parse(patched, verify=True)
ok("patched image re-parses and both CRCs self-validate", True)
ok("patched header stores the new payload CRC", fw2.stored_payload_crc == after_crc)
ok("re-reading the patched string returns the modded bytes",
   fw2.payload[idx:idx+len(needle)] == replacement)

# guard works: wrong 'expected' is rejected
try:
    fw2.apply(Patch(offset=idx, new=b"X"*len(needle), expected=needle))
    ok("stale-expected guard rejects mismatched stock bytes", False)
except Exception:
    ok("stale-expected guard rejects mismatched stock bytes", True)

print("\nALL CHECKS PASSED -- container is losslessly repackable and patchable.")
