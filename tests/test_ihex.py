"""Intel HEX read/write: round-trips, coverage, and patches that land in bytes the stock file skipped."""
import unittest

from dirtyloader import ihex


def _hex(records):
    return "\n".join(ihex._rec(t, a, b) for t, a, b in records) + "\n"


STOCK = _hex([
    (0x04, 0, b"\x60\x00"),
    (0x00, 0x0000, bytes(range(16))),
    (0x00, 0x0010, b"\xFF" * 16),                 # covered erased bytes (a cave the file does list)
    (0x00, 0x0040, bytes(range(16, 32))),         # 0x20..0x3F is a gap the file skips
    (0x05, 0, b"\x60\x00\x10\x00"),
    (0x01, 0, b""),
])


class TestIHex(unittest.TestCase):
    def test_read(self):
        img = ihex.read(STOCK)
        self.assertEqual(img.base, 0x60000000)
        self.assertEqual(len(img.data), 0x50)
        self.assertEqual(img.start, 0x60001000)
        self.assertEqual(bytes(img.data[0x20:0x40]), b"\xFF" * 0x20)
        self.assertEqual(img.covered.count(0), 0x20)

    def test_roundtrip(self):
        img = ihex.read(STOCK)
        self.assertEqual(ihex.write(img).split(), STOCK.split())

    def test_ff_bytes_in_new_code_are_written(self):
        """0xFF inside code a mod placed must be in the file: flash the bootloader did not erase keeps old bytes
        (hardware, core 0.3: a `bl` encoded FF F7 .. lost its first byte)."""
        img = ihex.read(STOCK)
        data = bytearray(img.data)
        code = bytes.fromhex("7047fff7e2bf")
        data[0x22:0x28] = code                                     # in the gap the stock file skips
        tail = bytes.fromhex("fff7e2bf7047")                       # past the stock end, starting with 0xFF
        again = ihex.read(ihex.write(img, bytes(data) + bytes.fromhex("ff" * 8) + tail,
                                     cover=[(0x60000058, len(tail))]))
        self.assertEqual(bytes(again.data[0x22:0x28]), code)
        self.assertEqual(bytes(again.data[0x58:0x5E]), tail)
        self.assertEqual(again.covered[0x24], 1)                  # the 0xFF byte is in a record
        self.assertEqual(again.covered[0x58], 1)

    def test_patch_in_gap_is_written(self):
        img = ihex.read(STOCK)
        data = bytearray(img.data)
        data[0x24:0x26] = b"\x70\x47"             # code in the skipped gap
        data[0x12] = 0x00                         # code in a covered cave
        again = ihex.read(ihex.write(img, bytes(data)))
        self.assertEqual(bytes(again.data[0x24:0x26]), b"\x70\x47")
        self.assertEqual(again.data[0x12], 0x00)
        self.assertEqual(bytes(again.data[:0x10]), bytes(range(16)))

    def test_checksum_is_checked(self):
        bad = STOCK.replace(":10000000", ":10000001", 1)
        with self.assertRaises(ihex.IHexError):
            ihex.read(bad)

    def test_to_firmware(self):
        fw = ihex.to_firmware(ihex.read(STOCK))
        self.assertEqual(fw.model, ihex.HEADLESS_MODEL)
        self.assertEqual(fw.load_addr, 0x60000000)
        from dirtyloader.m8mod import make_target
        self.assertEqual(make_target(fw, "0" * 64)["device"], "m8-headless")


if __name__ == "__main__":
    unittest.main()
