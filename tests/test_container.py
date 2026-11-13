"""M8FW container: round-trip, CRC recompute, and the apply-time guards."""
import unittest

from dirtyloader.m8fw import M8Firmware, Patch, M8FWError
from tests.synth import synth_stock, LOAD


class TestContainer(unittest.TestCase):
    def setUp(self):
        self.fw = synth_stock()
        self.raw = self.fw.build()

    def test_parse_roundtrip(self):
        fw2 = M8Firmware.parse(self.raw, verify=True)
        self.assertEqual(fw2.model, 2)
        self.assertEqual(fw2.load_addr, LOAD)
        self.assertEqual(bytes(fw2.payload), bytes(self.fw.payload))

    def test_noop_build_is_identical(self):
        self.assertEqual(M8Firmware.parse(self.raw).build(), self.raw)

    def test_patch_changes_crc_and_reverifies(self):
        before = self.fw.payload_crc32()
        self.fw.apply(Patch(offset=0x1000, new=b"\xde\xad\xbe\xef"))
        self.assertNotEqual(self.fw.payload_crc32(), before)
        patched = self.fw.build()
        self.assertEqual(len(patched), len(self.raw))
        fw2 = M8Firmware.parse(patched, verify=True)       # both CRCs self-validate
        self.assertEqual(fw2.payload[0x1000:0x1004], b"\xde\xad\xbe\xef")

    def test_expected_guard_rejects_wrong_bytes(self):
        with self.assertRaises(M8FWError):
            self.fw.apply(Patch(offset=0x1000, new=b"\x00\x00", expected=b"\xff\xff"))

    def test_sha256_guard_rejects_wrong_firmware(self):
        import hashlib
        wrong = hashlib.sha256(b"not these bytes").hexdigest()
        with self.assertRaises(M8FWError):
            self.fw.apply(Patch(offset=0x1000, new=b"\x00\x00", expected_sha256=wrong))

    def test_patch_outside_payload_rejected(self):
        with self.assertRaises(M8FWError):
            self.fw.apply(Patch(offset=len(self.fw.payload), new=b"\x00"))

    def test_bad_magic_rejected(self):
        with self.assertRaises(M8FWError):
            M8Firmware.parse(b"XXXX" + self.raw[4:])

    def test_overlap_detected(self):
        with self.assertRaises(M8FWError):
            self.fw.apply_all([Patch(0x100, b"\x00\x00\x00\x00"), Patch(0x102, b"\x11\x11")])


if __name__ == "__main__":
    unittest.main()
