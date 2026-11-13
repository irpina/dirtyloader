"""
mkmod's Thumb assembler, exercised when keystone is installed (it is in CI's test
job). This needs no firmware: it only assembles author code at an address.
Building a full mod from a source folder needs the stock firmware and is covered
by dirtyloader/test_tools.py, which runs locally against the real .bin.
"""
import unittest

try:
    import keystone  # noqa: F401
    HAVE_KEYSTONE = True
except Exception:
    HAVE_KEYSTONE = False


@unittest.skipUnless(HAVE_KEYSTONE, "keystone-engine not installed")
class TestAssemble(unittest.TestCase):
    def test_bx_lr(self):
        from dirtyloader.mkmod import assemble
        self.assertEqual(assemble("bx lr", 0x60000460), b"\x70\x47")

    def test_comments_stripped(self):
        from dirtyloader.mkmod import assemble
        src = "// a line comment\n@ another\nbx lr /* trailing */"
        self.assertEqual(assemble(src, 0x60000460), b"\x70\x47")

    def test_movs_then_return(self):
        from dirtyloader.mkmod import assemble
        code = assemble("movs r0, #0\nbx lr", 0x60000460)
        self.assertEqual(len(code), 4)       # two 16-bit Thumb instructions


if __name__ == "__main__":
    unittest.main()
