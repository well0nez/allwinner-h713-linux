"""release/check-crust.py, the crust gate of build-all step 10, against made-up artefacts.

Every input here is written by the test: a FIT with external data the way binman lays it out, a device
tree with an arisc node, crust and U-Boot .config files, a rootfs tar, BL31 bytes with or without the
TF-A strings the gate looks for. A green set first, then each gate against one wrong input.
"""
import io
import os
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest

GATE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "release", "check-crust.py")
CRUST = b"\x00crust" * 2000
DRAM = {"CLK": "792", "ZQ": "0x007b7bfb", "ODT_EN": "0x1", "PARA1": "0x000010f4", "PARA2": "0x04000000",
        "MR0": "0x1c70", "MR1": "0x40", "MR2": "0x18", "MR3": "0x0", "TPR5": "0x48484848", "TPR6": "0x48",
        "TPR9": "0x0", "TPR13": "0xb4016103"}
# What TF-A's sunxi_standby.c prints (built only with SUNXI_SYSTEM_SUSPEND=1), and the T1 reset's text.
STANDBY_TEXTS = b"".join(b"\n" + t + b"\n" for t in (
    b"PSCI: system suspend refused (0x%x): magic 0x%x version %u", b"PSCI: warm entry 0x%lx not usable by the ARISC",
    b"PSCI: msgbox port 3 keeps the request, no ARISC firmware is reading it", b"PSCI: system suspend, cpu op req sent, entry",
    b"PSCI: msgbox port 3 stays full, the ARISC main loop is not draining it",
    b"PSCI: system counter restored, %lu ms asleep added", b"PSCI: back from system suspend"))
T1_TEXT = b"\nPSCI: SoC watchdog fed and armed, no reset after 1 s\n"


def fdt(tree, tail=b""):
    """A flattened device tree from {name: {prop: bytes} or nested dict}, with tail after it."""
    struct_, strings, names = bytearray(), bytearray(), {}

    def node(name, body):
        struct_.extend(struct.pack(">I", 1) + name.encode() + b"\0")
        struct_.extend(b"\0" * (-len(struct_) % 4))
        for k, v in body.items():
            if isinstance(v, dict):
                continue
            if k not in names:
                names[k] = len(strings)
                strings.extend(k.encode() + b"\0")
            struct_.extend(struct.pack(">III", 3, len(v), names[k]) + v + b"\0" * (-len(v) % 4))
        for k, v in body.items():
            if isinstance(v, dict):
                node(k, v)
        struct_.extend(struct.pack(">I", 2))
    node("", tree)
    struct_.extend(struct.pack(">I", 9))
    total = 40 + 16 + len(struct_) + len(strings)
    head = struct.pack(">10I", 0xd00dfeed, total, 56, 56 + len(struct_), 40, 17, 16, 0, len(strings), len(struct_))
    return head + b"\0" * 16 + bytes(struct_) + bytes(strings) + b"\0" * (-total % 4) + tail


def fit(scp):
    """A FIT with external data: an uboot image and, unless scp is None, an scp image."""
    images = {"uboot": {"data-offset": struct.pack(">I", 0), "data-size": struct.pack(">I", 4)}}
    if scp is not None:
        images["scp"] = {"data-offset": struct.pack(">I", 4), "data-size": struct.pack(">I", len(scp))}
    return fdt({"images": images}, b"UBOO" + (scp or b""))


class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.put("scp.bin", CRUST)
        self.put("uboot-proper-release.bin", fit(CRUST))
        self.put("u-boot-installer.bin", b"\xff" * 0x8000 + fit(b""))
        self.put("u-boot-h713-probe.bin", b"\xff" * 0x8000 + fit(None))
        self.crust_config()
        self.put("uboot.config", "".join("CONFIG_%s=%s\n" % (("DRAM_CLK" if k == "CLK" else "DRAM_SUNXI_" + k), v)
                                         for k, v in DRAM.items()) + "CONFIG_SUNXI_DRAM_H713_DDR3_STOCK=y\n")
        self.dtb("hy310-crust.bin")
        self.rootfs(crust=CRUST, standby=True)
        self.put("bl31.bin", STANDBY_TEXTS + T1_TEXT)
        self.put("versions.env", 'CRUST_RELEASE_ALLOW=""\n')

    def put(self, name, data):
        with open(os.path.join(self.tmp.name, name), "wb") as f:
            f.write(data.encode() if isinstance(data, str) else data)

    def crust_config(self, *extra):
        self.put("crust.config", "CONFIG_H713_DRAM_SELF_REFRESH=y\nCONFIG_H713_IR_WAKE_NECX=y\nCONFIG_H713_DRAM_TYPE=3\n" +
                 "".join("CONFIG_H713_DRAM_%s=%s\n" % kv for kv in DRAM.items()) + "".join(extra))

    def dtb(self, firmware, wdt=b"allwinner,sun50i-h6-wdt\0allwinner,sun6i-a31-wdt\0"):
        arisc = {"compatible": b"allwinner,sun50i-h713-arisc\0", "firmware-name": firmware.encode() + b"\0hy310-edid.bin\0"}
        self.put("board.dtb", fdt({"soc": {"watchdog@2051000": {"compatible": wdt}, "arisc@100000": arisc}}))

    def rootfs(self, crust=None, standby=False, watchdog=False, extra=None):
        files = {"./etc/systemd/sleep.conf.d/10-h713.conf":
                 b"[Sleep]\nAllowSuspend=yes\nSuspendState=mem\nMemorySleepMode=deep\n" if standby else b"[Sleep]\nAllowSuspend=no\n"}
        if crust is not None:
            files["./usr/lib/firmware/hy310-crust.bin"] = crust
        if watchdog:
            files["./etc/systemd/system.conf.d/h713-watchdog.conf"] = b"[Manager]\nRuntimeWatchdogSec=16s\n"
        files.update(extra or {})
        with tarfile.open(os.path.join(self.tmp.name, "rootfs.tar"), "w") as t:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
            if standby:
                info = tarfile.TarInfo("./etc/systemd/system/multi-user.target.wants/h713-power.service")
                info.type, info.linkname = tarfile.SYMTYPE, "../h713-power.service"
                t.addfile(info)

    def run_gate(self, crust=True, standby=True, version="v0.6.35"):
        p = lambda n: os.path.join(self.tmp.name, n)
        argv = [sys.executable, GATE, "--board", "hy310", "--release-fit", p("uboot-proper-release.bin"),
                "--empty-fit", p("u-boot-installer.bin"), "--empty-fit", p("u-boot-h713-probe.bin"),
                "--uboot-config", p("uboot.config"), "--dtb", p("board.dtb"), "--rootfs", p("rootfs.tar"),
                "--bl31", p("bl31.bin"), "--versions", p("versions.env")]
        if crust:
            argv += ["--crust", p("scp.bin"), "--crust-config", p("crust.config"), "--crust-version", version]
        if standby:
            argv.append("--standby")
        r = subprocess.run(argv, capture_output=True, text=True)
        return r.returncode, r.stdout

    def assert_refused(self, why, **kw):
        rc, out = self.run_gate(**kw)
        self.assertEqual(rc, 1, out)
        self.assertIn(why, out)

    def test_the_green_set_passes_and_names_the_build_word(self):
        rc, out = self.run_gate()
        self.assertEqual(rc, 0, out)
        self.assertIn("build word 0x%08x" % (len(CRUST) | 1 << 24 | 1 << 26), out)

    def test_a_crust_that_is_not_the_one_in_the_fit(self):
        self.put("scp.bin", CRUST[:-1] + b"!")
        self.assert_refused("release FIT scp is")

    def test_an_scp_in_the_installer_fit(self):
        self.put("u-boot-installer.bin", b"\xff" * 0x8000 + fit(CRUST))
        self.assert_refused("u-boot-installer.bin carries an scp")

    def test_a_rootfs_crust_of_another_build(self):
        self.rootfs(crust=CRUST + b"x", standby=True)
        self.assert_refused("rootfs crust")

    def test_a_device_tree_that_names_the_vendor_blob(self):
        self.dtb("h713-arisc.bin")
        self.assert_refused("device tree names 'h713-arisc.bin'")

    def test_refused_options_and_the_sleep_net_before_its_release(self):
        for option in ("H713_DEEP_SLEEP", "H713_DEEP_VDD_SYS", "H713_DEEP_PLL_LDO", "H713_TEST", "H713_SLEEP_NET"):
            self.crust_config("CONFIG_%s=y\n" % option)
            self.assert_refused("CONFIG_%s=y" % option)
        self.put("versions.env", 'CRUST_RELEASE_ALLOW="H713_SLEEP_NET"\n')
        self.assertEqual(self.run_gate()[0], 0)
        self.put("versions.env", 'CRUST_RELEASE_ALLOW="H713_DEEP_VDD_SYS"\n')
        self.assert_refused("which no release may carry")

    def test_dram_values_that_differ_from_u_boot(self):
        self.crust_config("CONFIG_H713_DRAM_CLK=720\n")
        self.assert_refused("DRAM differ: CLK 720/792")

    def test_a_dirty_version_text(self):
        self.assert_refused("a dirty tree or one without tags", version="v0.6.10035")

    def test_standby_against_bl31_and_rootfs(self):
        self.assert_refused("BL31 offers SYSTEM_SUSPEND, the build has no --standby", standby=False)
        self.rootfs(crust=CRUST, standby=False)
        self.assert_refused("do not fit --standby")

    def test_a_watchdog_rootfs_needs_the_feeding_reset(self):
        self.rootfs(crust=CRUST, standby=True, watchdog=True)
        self.assertEqual(self.run_gate()[0], 0)
        self.put("bl31.bin", STANDBY_TEXTS)
        self.assert_refused("every reboot would hang")

    def test_the_watchdog_settings_as_systemd_reads_them(self):
        self.put("bl31.bin", STANDBY_TEXTS)                                    # no feeding reset
        conf = "./%s/systemd/system.conf.d/%s"
        for files in ({conf % ("usr/lib", "50-wd.conf"): b"[Manager]\nRuntimeWatchdogSec=16s\n"},
                      {conf % ("usr/local/lib", "50-wd.conf"): b"[Manager]\nRebootWatchdogSec=default\n"},
                      {"./usr/lib/systemd/system.conf": b"[Manager]\nRuntimeWatchdogSec=1min\n"},
                      {conf % ("etc", "10-off.conf"): b"RuntimeWatchdogSec=0\n", conf % ("lib", "50-wd.conf"): b"RuntimeWatchdogSec=16s\n"}):
            self.rootfs(crust=CRUST, standby=True, extra=files)
            self.assert_refused("every reboot would hang")
        for files in ({conf % ("etc", "wd.conf"): b"[Manager]\nRuntimeWatchdogSec=0s\nRebootWatchdogSec=off\n"},
                      {"./etc/systemd/system.conf": b"[Manager]\n#RuntimeWatchdogSec=off\n#RebootWatchdogSec=10min\n"},
                      {conf % ("usr/lib", "50-wd.conf"): b"RuntimeWatchdogSec=16s\n", conf % ("etc", "50-wd.conf"): b""},
                      {conf % ("usr/lib", "50-wd.conf"): b"RuntimeWatchdogSec=16s\n", conf % ("etc", "90-off.conf"): b"RuntimeWatchdogSec=\n"},
                      {"./run/systemd/system.conf.d/wd.conf": b"RuntimeWatchdogSec=16s\n"}):
            self.rootfs(crust=CRUST, standby=True, extra=files)
            rc, out = self.run_gate()
            self.assertEqual(rc, 0, (files, out))

    def test_a_bl31_with_some_of_the_standby_texts(self):
        self.put("bl31.bin", STANDBY_TEXTS.replace(b"back from system suspend", b"back from the standby") + T1_TEXT)
        self.assert_refused("6 of the 7 texts of TF-A's standby code")
        self.put("bl31.bin", T1_TEXT)
        self.assert_refused("BL31 lacks SYSTEM_SUSPEND, the build has --standby")

    def test_a_test_bench_bl31(self):
        self.put("bl31.bin", STANDBY_TEXTS + T1_TEXT + b"\nPSCI: test bench BL31: system suspend takes unmeasured\n")
        self.assert_refused("BL31 is a test bench build")

    def test_a_watchdog_bound_with_its_layout_needs_the_feeding_reset(self):
        self.dtb("hy310-crust.bin", wdt=b"allwinner,sun50i-h713-wdt\0allwinner,sun55i-a523-wdt\0")
        self.assertEqual(self.run_gate()[0], 0)
        self.put("bl31.bin", STANDBY_TEXTS)
        self.assert_refused("binds the SoC watchdog with its real layout")

    def test_a_board_without_crust(self):
        self.put("uboot-proper-release.bin", fit(b""))
        self.dtb("h713-arisc.bin")
        self.rootfs()
        self.put("bl31.bin", T1_TEXT)
        self.assertEqual(self.run_gate(crust=False, standby=False)[0], 0)
        self.rootfs(crust=CRUST)
        self.assert_refused("rootfs carries", crust=False, standby=False)


if __name__ == "__main__":
    unittest.main()
