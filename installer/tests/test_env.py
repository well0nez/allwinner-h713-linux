"""env_lesen / env_schreiben: the U-Boot environment round trip."""

import hashlib
import unittest

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

# frozen 2026-09-14 from hy310-install.py 0.1, on the release environment
# fixtures/device/hy310-uboot-env-20260913-release.bin
ENTRIES = 77
DIGEST = "4570b2e0f9b3150454215b5c8f283d7d50aae1253b79ce8d4b1cacc1d5609def"
INTENT = {"h713_gate": "1", "h713_boot": "emmc"}


class EnvRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.need([fakedisk.V3_ENV])
        cls.inst = support.tool("install")
        with open(fakedisk.V3_ENV, "rb") as fh:
            cls.raw = fh.read()

    def test_reads_the_release_environment_and_writes_it_back(self):
        env = self.inst.env_lesen(self.raw)
        self.assertEqual(len(env), ENTRIES)
        joined = "\n".join("%s=%s" % (k, env[k]) for k in sorted(env))
        self.assertEqual(hashlib.sha256(joined.encode("utf-8")).hexdigest(), DIGEST)
        self.assertEqual(dict((k, env[k]) for k in INTENT), INTENT)
        self.assertEqual(self.inst.env_schreiben(env), self.raw)

    def test_a_written_environment_reads_back(self):
        blob = self.inst.env_schreiben({"a": "1", "b": "2"})
        self.assertEqual(len(blob), self.inst.ENV_BYTES)
        self.assertEqual(self.inst.env_lesen(blob), {"a": "1", "b": "2"})
        with self.assertRaises(RuntimeError):
            self.inst.env_schreiben({"x": "y" * self.inst.ENV_BYTES})

    def test_broken_crc_gives_none(self):
        broken = bytearray(self.raw)
        broken[0] ^= 0xFF
        self.assertIsNone(self.inst.env_lesen(bytes(broken)))
        self.assertIsNone(self.inst.env_lesen(b"\0" * self.inst.ENV_BYTES))
        self.assertIsNone(self.inst.env_lesen(b"ab"))

    def test_the_stock_android_environment_is_not_one_of_ours(self):
        # why abzug_klein() reads LBA 14336 only on our own layout
        support.need([fakedisk.STOCK_ENV_A])
        with open(fakedisk.STOCK_ENV_A, "rb") as fh:
            self.assertIsNone(self.inst.env_lesen(fh.read(self.inst.ENV_BYTES)))
