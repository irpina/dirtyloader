"""The mod build command (python -m dirtyloader.cc): its targets match the shop's, info reads the shop's files, and,
where the ARM compiler is installed (not in CI), examples/hello builds for every target."""
import contextlib
import io
import json
import os
import tempfile
import unittest

from dirtyloader import cc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOP = os.path.join(ROOT, "site", "shop")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cc.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestCcCli(unittest.TestCase):
    def test_targets_match_the_shop(self):
        with open(os.path.join(SHOP, "meta.json"), encoding="utf-8") as f:
            shop = json.load(f)["targets"]
        self.assertEqual(set(shop), set(cc.TARGETS))
        for k, t in cc.TARGETS.items():
            for field in ("label", "firmware", "defines", "alias"):
                self.assertEqual(t[field], shop[k][field], f"{k}.{field}")

    def test_targets_command(self):
        code, out, _ = run("targets")
        self.assertEqual(code, 0)
        for k in cc.TARGETS:
            self.assertIn(k, out)

    def test_info_reads_a_shop_mod(self):
        path = os.path.join(SHOP, "mods", "m8-model02-664", "chaos-control.m8x")
        code, out, _ = run("info", path)
        self.assertEqual(code, 0)
        self.assertIn("chaos-control", out)
        self.assertIn("firmware 0x02060604", out)
        self.assertIn("ev_boot@50", out)
        self.assertIn("by dirtyloader: An X/Y effects pad", out)

    def test_info_is_not_a_hook(self):
        """DL_INFO's entry is read as the mod's author and description, not counted as a subscription."""
        for t in cc.TARGETS:
            with open(os.path.join(SHOP, "mods", t, "chaos-control.m8x"), "rb") as f:
                p = cc.parse_m8x(f.read())
            self.assertEqual(p["info"]["author"], "dirtyloader", t)
            self.assertTrue(p["info"]["about"].startswith("An X/Y effects pad"), t)
            self.assertNotIn(cc.EV_INFO, [s["event"] for s in p["subscribe"]], t)
        with open(os.path.join(SHOP, "catalog.json"), encoding="utf-8") as f:
            for m in json.load(f)["mods"]:
                self.assertFalse(any(h.startswith("0x") for h in m["hooks"]), m["id"])

    def test_info_refuses_a_bad_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.m8x")
            with open(p, "wb") as f:
                f.write(b"not a mod at all, not at all")
            code, _, err = run("info", p)
        self.assertEqual(code, 1)
        self.assertIn("not an .m8x", err)

    def test_build_refuses_a_missing_folder_and_one_file_for_many(self):
        self.assertEqual(run("build", os.path.join(ROOT, "no-such-mod"))[0], 1)
        code, _, err = run("build", os.path.join(ROOT, "examples", "hello"), "-o", "x.m8x")
        self.assertEqual(code, 1)
        self.assertIn("single --target", err)

    @unittest.skipUnless(cc.available(), "arm-none-eabi-gcc not installed")
    def test_hello_builds_for_every_target(self):
        with tempfile.TemporaryDirectory() as d:
            code, out, err = run("build", os.path.join(ROOT, "examples", "hello"), "-o", d)
            self.assertEqual(code, 0, err)
            fws = {"m8-headless": 0x00060604, "m8-model02": 0x02060602, "m8-model02-664": 0x02060604}
            for t, fw in fws.items():
                with open(os.path.join(d, t, "hello.m8x"), "rb") as f:
                    p = cc.parse_m8x(f.read())
                self.assertEqual((p["id"], p["fw"]), ("hello", fw), t)
                self.assertEqual(len(p["subscribe"]), 4)
                self.assertEqual(p["info"]["author"], "dirtyloader")


if __name__ == "__main__":
    unittest.main()
