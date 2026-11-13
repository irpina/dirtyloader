"""
End-to-end proof of the .m8mod pipeline (format 2, docs/FORMAT.md) against the real stock firmware:

  * format 2 round-trips through save/load, and ships no stock bytes (only their sha256)
  * the format-1 example still loads (converted to hash-guarded sites) and builds
  * make-mod (diff_payloads) reproduces a mod's sites from a hand-edited image
  * ["stock", addr, n] parts are filled from the user's own firmware
  * the linker refuses: a wrong target, a stock-hash mismatch, overlapping sites, an unmet requires,
    a shared resource name, a subscription with no provider, and a core that is too old

The stock firmware is only read. Run:  python -m dirtyloader.test_pipeline [stock.bin]
"""
import json
import os
import sys
import tempfile

from dirtyloader.m8fw import M8Firmware, M8FWError
from dirtyloader.m8mod import Mod, Site, make_target, sha256
from dirtyloader.linker import link, diff_payloads
from dirtyloader import registry

STOCK = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\zacha\Downloads\M8Firmware_V6_6_2\Firmware\Model02\M8_V6_6_2A_MODEL02.bin"
V1_EXAMPLE = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "demo-rename-scale.v1.m8mod")
LABEL = 0x601D0E62          # "HARMONIC MAJOR", 14 bytes
NEW = b"DIRTYWAVE MAJ "


def ok(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        raise SystemExit(1)


def refuses(label, fn):
    try:
        fn()
    except M8FWError:
        ok(label, True)
        return
    ok(label, False)


data = open(STOCK, "rb").read()
stock = M8Firmware.parse(data, verify=True)
sha = registry.sha256_bytes(data)
ok("registry identifies the stock firmware", registry.identify(sha) is not None)
target = make_target(stock, sha, "6.6.2A")
off = LABEL - stock.load_addr
stock_label = bytes(stock.payload[off:off + len(NEW)])

# -- a format-2 mod, saved and loaded ---------------------------------
mod = Mod(id="rename-scale", version="1.0", title="Rename a scale", license="GPL-2.0-or-later",
          target=target, sites=[Site.from_bytes(LABEL, stock_label, NEW, "data", "scale label")])
tmp = os.path.join(tempfile.mkdtemp(), "rename-scale.m8mod")
mod.save(tmp)
raw = open(tmp, encoding="utf-8").read()
ok("saved as format 2", json.loads(raw)["m8mod"] == 2)
ok("ships no stock bytes (only their hash)", stock_label.hex() not in raw and sha256(stock_label) in raw)
again = Mod.load(tmp)
ok("format 2 round-trips", again.to_dict() == mod.to_dict())

built = link(stock, sha, [again])
ok("patched payload carries the new label", NEW in bytes(built.payload))
ok("stock image untouched", NEW not in bytes(stock.payload))
M8Firmware.parse(built.build(), verify=True)
ok("built image re-parses; both CRCs valid", True)

# -- the format-1 example still loads ---------------------------------
v1 = Mod.load(V1_EXAMPLE)
ok("format-1 example loads (converted)", v1.loaded_format == 1 and len(v1.sites) == 1)
ok("format-1 conversion hashes the stock bytes", v1.sites[0].stock_sha256 == sha256(stock_label))
ok("format-1 example builds", NEW in bytes(link(stock, sha, [v1]).payload))

# -- make-mod round trip ----------------------------------------------
regen = diff_payloads(bytes(stock.payload), bytes(built.payload), load_addr=stock.load_addr)
ok("diff finds one site", len(regen) == 1)
ok("regenerated site matches", regen[0].addr == LABEL and regen[0].stock_sha256 == sha256(stock_label)
   and regen[0].data(stock) == NEW)

# -- stock parts --------------------------------------------------------
parts_site = Site(addr=LABEL, len=len(NEW), stock_sha256=sha256(stock_label),
                  new=[["stock", hex(LABEL), 9], ["hex", NEW[9:].hex()]], kind="data")
ok("stock parts filled from the user's firmware", parts_site.data(stock) == stock_label[:9] + NEW[9:])

# -- refusals -------------------------------------------------------------
bad_target = Mod(id="x", target=dict(target, bin_sha256="00" * 32), sites=mod.sites)
refuses("wrong bin_sha256 is refused", lambda: link(stock, sha, [bad_target]))
bad_dev = Mod(id="x", target=dict(target, device="m8-model01"), sites=mod.sites)
refuses("wrong device is refused", lambda: link(stock, sha, [bad_dev]))
bad_hash = Mod(id="x", target=target, sites=[Site(addr=LABEL, len=len(NEW), stock_sha256="11" * 32,
                                                   new=[["hex", NEW.hex()]])])
refuses("stock-hash mismatch is refused", lambda: link(stock, sha, [bad_hash]))
a = Mod(id="a", target=target, sites=mod.sites)
b = Mod(id="b", target=target, sites=mod.sites)
refuses("overlapping sites are refused", lambda: link(stock, sha, [a, b]))
refuses("unmet requires is refused", lambda: link(stock, sha, [Mod(id="n", target=target, requires=["gone"])]))
r1 = Mod(id="r1", target=target, resources={"names": ["fx:cmd:0x4e"]})
r2 = Mod(id="r2", target=target, resources={"names": ["fx:cmd:0x4e"]})
refuses("a shared resource name is refused", lambda: link(stock, sha, [r1, r2]))
sub = Mod(id="s", target=target, subscribe=[{"event": "TICK", "handler": 0x60000461, "order": 50}])
refuses("a subscription with no provider is refused", lambda: link(stock, sha, [sub]))
old_core = Mod(id="core", version="0.1.0", target=target, events=["TICK"])
needy = Mod(id="needy", target=target, requires=["core"], core="0.9")
refuses("a core older than a mod needs is refused", lambda: link(stock, sha, [old_core, needy]))

print("\nALL PIPELINE CHECKS PASSED -- format 2, format-1 loading, make-mod and the linker's checks.")
