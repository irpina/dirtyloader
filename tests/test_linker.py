"""The linker: a good link, the refusals, and diff_payloads -- all firmware-free."""
import struct
import unittest

from dirtyloader.m8fw import M8Firmware, M8FWError
from dirtyloader.m8mod import Mod, Site, make_target
from dirtyloader.linker import link, diff_payloads, ConflictError
from dirtyloader.core import abi
from tests.synth import synth_stock, stock_sha, synth_core, synth_handler, LOAD, CAVE


def _handler_in_table(fw: M8Firmware, handler: int) -> bool:
    table_off = (abi.CORE_REGION_ADDR - fw.load_addr) + 0x10
    return any(
        struct.unpack_from(abi.HOOK_ENTRY_FMT, bytes(fw.payload),
                           table_off + i * abi.HOOK_ENTRY_SIZE)
        == (int(abi.Event.TICK), abi.FLAG_ENABLED, handler)
        for i in range(abi.MAX_HOOKS)
    )


class TestLink(unittest.TestCase):
    def setUp(self):
        self.fw = synth_stock()
        self.sha = stock_sha(self.fw)
        self.core = synth_core(self.fw, self.sha)
        self.handler = synth_handler(self.fw, self.sha)

    def test_good_link(self):
        out = link(self.fw, self.sha, [self.core, self.handler])
        M8Firmware.parse(out.build(), verify=True)          # CRCs valid
        region_off = abi.CORE_REGION_ADDR - LOAD
        self.assertEqual(bytes(out.payload[region_off:region_off + len(abi.CORE_MAGIC)]),
                         abi.CORE_MAGIC)
        self.assertTrue(_handler_in_table(out, CAVE | 1))
        # the input firmware is not mutated
        self.assertNotEqual(bytes(self.fw.payload[region_off:region_off + 8]), abi.CORE_MAGIC)

    def test_two_handlers_get_distinct_slots(self):
        h2 = synth_handler(self.fw, self.sha, cave=CAVE + 0x10, mod_id="demo2")
        out = link(self.fw, self.sha, [self.core, self.handler, h2])
        self.assertTrue(_handler_in_table(out, CAVE | 1))
        self.assertTrue(_handler_in_table(out, (CAVE + 0x10) | 1))

    def test_duplicate_id(self):
        with self.assertRaises(ConflictError):
            link(self.fw, self.sha, [self.core, self.handler, self.handler])

    def test_subscribe_without_core(self):
        with self.assertRaises(M8FWError):
            link(self.fw, self.sha, [self.handler])

    def test_requires_missing(self):
        lonely = synth_handler(self.fw, self.sha)
        lonely.subscribe = []                               # so the failure is 'requires', not 'provides'
        with self.assertRaises(M8FWError):
            link(self.fw, self.sha, [lonely])

    def test_conflicts(self):
        self.handler.conflicts = ["core"]
        with self.assertRaises(ConflictError):
            link(self.fw, self.sha, [self.core, self.handler])

    def test_resource_clash(self):
        a = synth_handler(self.fw, self.sha, cave=CAVE, mod_id="a")
        b = synth_handler(self.fw, self.sha, cave=CAVE + 0x10, mod_id="b")
        a.resources = b.resources = {"names": ["fx:cmd:0x4e"]}
        with self.assertRaises(ConflictError):
            link(self.fw, self.sha, [self.core, a, b])

    def test_wrong_target(self):
        self.handler.target["bin_sha256"] = "f" * 64
        with self.assertRaises(M8FWError):
            link(self.fw, self.sha, [self.core, self.handler])

    def test_core_too_old(self):
        self.handler.core = "9.0"
        with self.assertRaises(M8FWError):
            link(self.fw, self.sha, [self.core, self.handler])

    def test_overlapping_sites(self):
        clash = synth_handler(self.fw, self.sha, cave=CAVE, mod_id="clash")
        # same cave as self.handler -> overlapping sites
        with self.assertRaises(M8FWError):
            link(self.fw, self.sha, [self.core, self.handler, clash])


class TestDiff(unittest.TestCase):
    def test_diff_roundtrip(self):
        fw = synth_stock()
        stock = bytes(fw.payload)
        modified = bytearray(stock)
        modified[0x1000:0x1004] = b"\xaa\xbb\xcc\xdd"
        modified[0x2000:0x2002] = b"\xee\xff"
        sites = diff_payloads(stock, bytes(modified), gap=8, load_addr=LOAD)
        self.assertEqual(len(sites), 2)
        # applying the sites back onto stock reproduces `modified`
        fw2 = synth_stock()
        for s in sites:
            fw2.apply(s.resolve(fw2))
        self.assertEqual(bytes(fw2.payload), bytes(modified))

    def test_diff_size_mismatch(self):
        with self.assertRaises(M8FWError):
            diff_payloads(b"\x00" * 4, b"\x00" * 8)


if __name__ == "__main__":
    unittest.main()
