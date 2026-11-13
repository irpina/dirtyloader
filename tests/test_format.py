"""The .m8mod format: Site/Mod round-trips, format-1 loading, make_target."""
import os
import unittest

from dirtyloader.m8mod import Mod, Site, make_target, event_id, event_name, FORMAT
from dirtyloader.m8fw import M8FWError
from tests.synth import synth_stock, stock_sha, synth_core, synth_handler, LOAD

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestSite(unittest.TestCase):
    def test_from_bytes_roundtrip(self):
        s = Site.from_bytes(0x60000500, b"\x01\x02", b"\x03\x04", "code", "x")
        d = s.to_dict()
        self.assertEqual(d["new"], "0304")                  # single hex part collapses to a string
        s2 = Site.from_dict(d)
        self.assertEqual((s2.addr, s2.len, s2.kind), (0x60000500, 2, "code"))
        self.assertEqual(s2.stock_sha256, s.stock_sha256)

    def test_stock_part_copies_from_firmware(self):
        fw = synth_stock()
        off = 0x1000
        orig = bytes(fw.payload[off:off + 4])
        s = Site(addr=LOAD + 0x2000, len=4, stock_sha256="0" * 64,
                 new=[["stock", hex(LOAD + off), 4]])
        self.assertEqual(s.data(fw), orig)

    def test_parts_must_sum_to_len(self):
        with self.assertRaises(M8FWError):
            Site(addr=0x60000500, len=4, stock_sha256="0" * 64, new=[["hex", "0304"]])

    def test_bad_stock_hash_rejected(self):
        with self.assertRaises(M8FWError):
            Site(addr=0x60000500, len=2, stock_sha256="tooshort", new=[["hex", "0304"]])


class TestMod(unittest.TestCase):
    def test_v2_roundtrip(self):
        fw = synth_stock()
        sha = stock_sha(fw)
        mod = synth_handler(fw, sha)
        mod2 = Mod.from_dict(mod.to_dict())
        self.assertEqual(mod2.to_dict()["m8mod"], FORMAT)
        self.assertEqual(mod2.id, "demo")
        self.assertEqual(mod2.requires, ["core"])
        self.assertEqual(mod2.subscribe[0]["event"], "TICK")
        self.assertEqual(len(mod2.sites), 1)

    def test_make_target_fields(self):
        fw = synth_stock()
        t = make_target(fw, stock_sha(fw), "synthetic")
        self.assertEqual(t["device"], "m8-model02")
        self.assertEqual(t["payload_len"], len(fw.payload))
        self.assertEqual(len(t["bin_sha256"]), 64)

    def test_events(self):
        self.assertEqual(event_name(event_id("TICK")), "TICK")
        with self.assertRaises(M8FWError):
            event_id("NO_SUCH_EVENT")

    def test_format1_loads_and_converts(self):
        v1 = {
            "m8mod_format": 1, "id": "old", "version": "1.0", "name": "old mod",
            "target": {"model": 2, "firmware_version": "6.6.2A", "stock_sha256": "a" * 64},
            "patches": [{"addr": "0x60000500", "data": "0304", "expect": "0102", "note": "x"}],
            "hooks": [{"event": "TICK", "handler": "0x60000501"}],
        }
        mod = Mod.from_dict(v1)
        self.assertEqual(mod.loaded_format, 1)
        self.assertEqual(len(mod.sites), 1)
        self.assertEqual(mod.sites[0].addr, 0x60000500)
        self.assertEqual(mod.subscribe[0]["event"], "TICK")
        # re-saving writes format 2 (stock bytes become a hash, never shipped)
        self.assertEqual(mod.to_dict()["m8mod"], FORMAT)
        self.assertTrue(all(p[0] == "hex" for s in mod.sites for p in s.new))

    def test_fixture_v1_loads(self):
        path = os.path.join(FIXTURES, "demo-rename-scale.v1.m8mod")
        if not os.path.exists(path):
            self.skipTest("fixture missing")
        mod = Mod.load(path)
        self.assertTrue(mod.id)
        self.assertTrue(mod.sites)


if __name__ == "__main__":
    unittest.main()
