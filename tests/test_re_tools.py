"""
The byte-level RE tools on a synthetic image (no firmware needed):

  * re.vtables finds a {0,0}-headed run of Thumb code pointers and locates a
    function's slot, tolerating a heuristic start a few bytes past the entry
  * re.switches finds a `cmp; bhi; tbb [pc, r1]` switch, recovers its case count
    and `sub` bias, and decodes the jump table (needs capstone)
"""
import struct
import unittest

from dirtyloader.m8fw import M8Firmware
from dirtyloader.re import vtables

LOAD = 0x60000000

try:
    import capstone  # noqa: F401
    HAVE_CAPSTONE = True
except Exception:
    HAVE_CAPSTONE = False


def _image(size=0x4000):
    return M8Firmware(version=0x00020001, load_addr=LOAD, payload=bytearray(size))


class TestVtables(unittest.TestCase):
    def setUp(self):
        self.fw = _image()
        p = self.fw.payload
        # vtable at +0x2000: header {0, 0}, then 8 Thumb code pointers into the image
        self.vt = LOAD + 0x2008
        self.funcs = [LOAD + 0x1000 + 0x40 * k for k in range(8)]
        struct.pack_into("<II", p, 0x2000, 0, 0)
        for k, f in enumerate(self.funcs):
            struct.pack_into("<I", p, 0x2008 + 4 * k, f | 1)

    def test_finds_vtable(self):
        vts = vtables.find_vtables(self.fw)
        self.assertEqual([(v.addr, len(v)) for v in vts], [(self.vt, 8)])

    def test_locates_slot_and_true_entry(self):
        vts = vtables.find_vtables(self.fw)
        hits = vtables.locate(vts, self.funcs[2] + 2)        # a guess 2 bytes past the real entry
        self.assertEqual(len(hits), 1)
        vt, off, entry = hits[0]
        self.assertEqual((vt.addr, off, entry), (self.vt, 0x08, self.funcs[2]))

    def test_needs_zero_header(self):
        struct.pack_into("<I", self.fw.payload, 0x2004, 0x12345678)   # break the {0,0} header
        self.assertEqual(vtables.find_vtables(self.fw), [])


@unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
class TestSwitches(unittest.TestCase):
    def test_tbb_census(self):
        from dirtyloader.re import switches
        fw = _image()
        code = bytes.fromhex(
            "10b5"      # push {r4, lr}
            "a1f10501"  # sub.w r1, r1, #5     (bias 5)
            "0329"      # cmp r1, #3           (4 cases)
            "00d8"      # bhi (default)
            "dfe801f0"  # tbb [pc, r1]
            "02030405"  # jump table: 4 byte entries
        )
        fw.payload[0x100:0x100 + len(code)] = code
        rows = switches.census(fw)
        self.assertEqual(len(rows), 1)
        s = rows[0]
        self.assertEqual((s.addr, s.kind, s.reg, s.cases, s.bias, s.function),
                         (LOAD + 0x10A, "tbb", 1, 4, 5, LOAD + 0x100))
        table = LOAD + 0x10A + 4
        self.assertEqual(s.targets, [table + 2 * v for v in (2, 3, 4, 5)])


if __name__ == "__main__":
    unittest.main()
