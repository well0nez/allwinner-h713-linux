"""Tests for release/check-display.py: the board environment (the U-Boot fork's hy310.env) run through its hush model,
and rootfs tars made of the overlay's own files. Run: python3 -m unittest release/tests/test_check_display.py"""
import importlib.machinery
import importlib.util
import io
import os
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CHECK = os.path.join(REPO, "release", "check-display.py")
ENV = os.path.join(REPO, "mainline", "external", "u-boot", "board", "sunxi", "hy310.env")
OVERLAY = os.path.join(REPO, "rootfs", "overlay")
POWER = os.path.join(REPO, "userspace", "h713-power")
# boot_emmc's kernel command line before h713_display existed (U-Boot fork 26f974b8d6a, hy310.env)
BEFORE = ("console=ttyS0,115200 rootwait clk_ignore_unused pd_ignore_unused cma=128M net.ifnames=0 panic=10 loglevel=4 "
          "root=PARTLABEL=hy310-rootfs rw")
VENDOR_MODULES = ("hy310_cpu_comm", "sun50i-h713-hdmirx", "sun50i-h713-mips", "sun50i-h713-msp", "sun50i-h713-afbd",
                  "sun50i-h713-arisc")


def load():
    loader = importlib.machinery.SourceFileLoader("check_display", CHECK)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("check_display", loader))
    loader.exec_module(mod)
    return mod


def ko(vermagic):
    return ("\0vermagic=%s\0" % vermagic).encode()


def slurp(p):
    with open(p, "rb") as f:
        return f.read()


class Tar:
    def __init__(self, kernel="6.18.38", drm=None, modules=VENDOR_MODULES, skip=()):
        self.files, self.links = {}, {}
        for rel in ("usr/local/sbin/h713-display", "etc/systemd/system/h713-display.service",
                    "etc/systemd/system/h713-hdcp-key.service", "etc/modprobe.d/h713-drm.conf",
                    "etc/modprobe.d/h713-hdcp-key.conf"):
            self.files[rel] = slurp(os.path.join(OVERLAY, rel))
        for u in ("h713-tv-rescue.service", "h713-sleep-pre.service", "h713-sleep-post.service"):
            self.files["etc/systemd/system/" + u] = slurp(os.path.join(POWER, u))
        for rel in skip:
            del self.files[rel]
        self.links["etc/systemd/system/sysinit.target.wants/h713-display.service"] = \
            "/etc/systemd/system/h713-display.service"
        self.links["usr/lib/firmware/h713-mips"] = os.readlink(os.path.join(OVERLAY, "usr/lib/firmware/h713-mips"))
        dep = []
        for m in modules:
            dep.append("kernel/drivers/x/%s.ko:" % m)
            self.files["usr/lib/modules/%s/kernel/drivers/x/%s.ko" % (kernel, m)] = ko(kernel + " SMP preempt mod_unload aarch64")
        if drm:
            dep.append("extra/h713_drm.ko: kernel/drivers/x/sun50i-h713-arisc.ko")
            self.files["usr/lib/modules/%s/extra/h713_drm.ko" % kernel] = ko(drm + " SMP preempt mod_unload aarch64")
        self.files["usr/lib/modules/%s/modules.dep" % kernel] = ("\n".join(dep) + "\n").encode()

    def write(self, d):
        p = os.path.join(d, "rootfs.tar")
        with tarfile.open(p, "w") as t:
            for rel, data in self.files.items():
                i = tarfile.TarInfo("./" + rel)
                i.size = len(data)
                t.addfile(i, io.BytesIO(data))
            for rel, target in self.links.items():
                i = tarfile.TarInfo("./" + rel)
                i.type, i.linkname = tarfile.SYMTYPE, target
                t.addfile(i)
        return p


class CheckDisplay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def gate(self, *args):
        m = load()
        out = io.StringIO()
        with redirect_stdout(out):
            rc = m.main(list(args))
        return rc, out.getvalue()

    def env_file(self, text):
        p = os.path.join(self.tmp.name, "u-boot-initial-env")
        with open(p, "w") as f:
            f.write(text)
        return p

    def test_the_board_environment_and_the_overlay_are_green(self):
        rc, out = self.gate("--env", ENV, "--rootfs", Tar().write(self.tmp.name))
        self.assertEqual(rc, 0, out)
        self.assertIn("display gate: green", out)
        self.assertIn("6.18.38 carries no h713_drm", out)
        self.assertNotIn("FAIL", out)

    def test_the_vendor_command_line_is_the_one_before_plus_one_word(self):
        m = load()
        env = m.env_load(ENV)
        for display in (None, "vendor"):
            disp, args = m.boot(env, display, "emmc")
            self.assertEqual(disp, [["init", "0x30", "logo"]])
            self.assertEqual(args, BEFORE + " module_blacklist=h713_drm")
        disp, args = m.boot(env, "clean", "emmc")
        self.assertEqual(disp, [["init", "0x30", "noboot", "logo"]])
        self.assertEqual(args, BEFORE + " h713.display=clean module_blacklist=hy310_cpu_comm,sun50i_h713_hdmirx,"
                                        "sun50i_h713_mips,sun50i_h713_msp,sun50i_h713_afbd")

    def test_the_mkenvimage_form_reads_the_same(self):
        m = load()
        env = m.env_load(ENV)
        blob = os.path.join(self.tmp.name, "env.bin")
        payload = b"".join(("%s=%s" % (k, env[k])).encode() + b"\0" for k in sorted(env)) + b"\0"
        payload = payload.ljust(0x10000 - 4, b"\0")
        import struct
        import zlib
        with open(blob, "wb") as f:
            f.write(struct.pack("<I", zlib.crc32(payload) & 0xffffffff) + payload)
        self.assertEqual(m.env_load(blob), env)

    def test_a_boot_path_that_drops_the_words_fails(self):
        m = load()
        env = m.env_load(ENV)
        env["boot_net"] = env["boot_net"].replace(" ${h713_display_args}", "")
        rc, out = self.gate("--env", self.env_file("".join("%s=%s\n" % kv for kv in env.items())))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  h713_display=clean, boot_net", out)
        self.assertIn("ok    h713_display=clean, boot_emmc", out)

    def test_the_old_environment_fails(self):
        m = load()
        env = m.env_load(ENV)
        env["bootcmd"] = "h713_disp init ${h713_project} logo; run boot_${h713_boot}; run boot_net"
        rc, out = self.gate("--env", self.env_file("".join("%s=%s\n" % kv for kv in env.items())))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  h713_display=clean, boot_emmc: h713_disp [['init', '0x30', 'logo']]", out)

    def test_a_unit_that_would_reach_for_the_mips_fails(self):
        t = Tar()
        t.files["etc/systemd/system/h713-hdcp-key.service"] = t.files["etc/systemd/system/h713-hdcp-key.service"] \
            .replace(b"ConditionKernelCommandLine=!h713.display=clean\n", b"")
        rc, out = self.gate("--env", ENV, "--rootfs", t.write(self.tmp.name))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL  h713-hdcp-key.service has no ConditionKernelCommandLine=!h713.display=clean", out)

    def test_an_unlinked_load_unit_fails(self):
        t = Tar()
        del t.links["etc/systemd/system/sysinit.target.wants/h713-display.service"]
        rc, out = self.gate("--env", ENV, "--rootfs", t.write(self.tmp.name))
        self.assertEqual(rc, 1)
        self.assertIn("is not linked into sysinit.target.wants", out)

    def test_a_renamed_vendor_driver_fails(self):
        t = Tar(modules=tuple(m for m in VENDOR_MODULES if m != "sun50i-h713-msp") + ("sun50i-h713-msp2",))
        rc, out = self.gate("--env", ENV, "--rootfs", t.write(self.tmp.name))
        self.assertEqual(rc, 1)
        self.assertIn("the clean stack refuses sun50i_h713_msp, which this kernel has no module of", out)

    def test_an_h713_drm_of_another_kernel_fails_and_its_own_passes(self):
        rc, out = self.gate("--env", ENV, "--rootfs", Tar(drm="7.3.1-rustbench").write(self.tmp.name))
        self.assertEqual(rc, 1)
        self.assertIn("h713_drm vermagic '7.3.1-rustbench SMP preempt mod_unload aarch64'", out)
        rc, out = self.gate("--env", ENV, "--rootfs", Tar(kernel="7.3.1-rustbench", drm="7.3.1-rustbench")
                            .write(self.tmp.name))
        self.assertEqual(rc, 0, out)
        self.assertIn("ok    7.3.1-rustbench: h713_drm built for this kernel", out)


if __name__ == "__main__":
    unittest.main()
