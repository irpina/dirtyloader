"""
The published catalog (site/mods/*.m8mod) must be shareable: format 2, well-formed,
and carrying no Dirtywave bytes -- every site part is the author's own hex, guarded
by a sha256 of the stock bytes. This runs without any firmware.
"""
import glob
import os
import unittest

from dirtyloader.m8mod import Mod

SITE_MODS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "site", "mods")


class TestCatalog(unittest.TestCase):
    def setUp(self):
        self.files = sorted(glob.glob(os.path.join(SITE_MODS, "*.m8mod")))
        if not self.files:
            self.skipTest("no published mods in site/mods")

    def test_all_load_as_format2(self):
        for path in self.files:
            mod = Mod.load(path)
            self.assertEqual(mod.loaded_format, 2, path)
            self.assertTrue(mod.id, path)
            self.assertTrue(mod.target.get("bin_sha256"), f"{path} has no target pin")

    def test_no_stock_bytes_are_shipped(self):
        for path in self.files:
            mod = Mod.load(path)
            for s in mod.sites:
                self.assertEqual(len(s.stock_sha256), 64, f"{path}: site not hash-guarded")
                for part in s.new:
                    self.assertEqual(part[0], "hex",
                                     f"{path}: site ships a non-author part {part[0]!r}")


if __name__ == "__main__":
    unittest.main()
