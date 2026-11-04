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
# the image's kernel defconfig: CONFIG_RUST=y and CONFIG_DRM_H713=m since 7.3.1 (05.11.2026)
DEFCONFIG = os.path.join(REPO, "mainline", "patches", "kernel", "board", "hy200_qz713df_a1_defconfig")


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

    def test_the_hy320_environment_logs_the_console_after_either_init(self):
        # hy320_defconfig sets CONFIG_CONSOLE_RECORD: its bootcmd carries h713_conlog, the others' do not
        m = load()
        plain, hy320 = m.env_load(ENV), m.env_load(ENV, ["CONFIG_CONSOLE_RECORD"])
        self.assertNotIn("h713_conlog", plain["bootcmd"])
        self.assertIn('fi; h713_conlog 0x45000000; mmc dev 1; mmc write 0x45000000 0x2800 0x400; run boot_${h713_boot}',
                      hy320["bootcmd"])
        self.assertIn("h713_display", hy320["bootcmd"])           # h713-display set clean takes it
        for display in ("vendor", "clean"):
            h = m.run_boot(hy320, display, "emmc")
            self.assertEqual((h.conlog, h.bootargs), ([1], m.boot(plain, display, "emmc")[1]))
        rc, out = self.gate("--env", ENV, "--define", "CONFIG_CONSOLE_RECORD")
        self.assertEqual(rc, 0, out)
        self.assertIn("ok    h713_display=clean, boot_emmc: h713_conlog after the display init", out)

    def test_a_console_log_before_the_display_init_fails(self):
        m = load()
        env = m.env_load(ENV)
        env["bootcmd"] = "h713_conlog 0x45000000; " + env["bootcmd"]
        rc, out = self.gate("--env", self.env_file("".join("%s=%s\n" % kv for kv in env.items())))
        self.assertEqual(rc, 1)
        self.assertIn("h713_conlog ran after 0 h713_disp - wanted once, after the display init", out)

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

    def config(self, name, *lines):
        p = os.path.join(self.tmp.name, name)
        with open(p, "w") as f:
            f.write("".join(l + "\n" for l in lines))
        return p

    def test_a_kernel_that_lost_rust_fails(self):
        # the release defconfig asks for both; kconfig without the Rust toolchain leaves CONFIG_RUST out and DRM_H713 with it
        built = self.config(".config", "CONFIG_DRM=y", "# CONFIG_RUST is not set")
        rc, out = self.gate("--env", ENV, "--rootfs", Tar(kernel="7.3.1").write(self.tmp.name),
                            "--defconfig", DEFCONFIG, "--kernel-config", built)
        self.assertEqual(rc, 1)
        self.assertIn("the kernel's .config lacks CONFIG_RUST=y, CONFIG_DRM_H713=m", out)
        self.assertIn("7.3.1 carries no h713_drm, but the kernel's defconfig builds it", out)

    def test_an_image_without_h713_drm_fails_where_the_kernel_builds_it(self):
        built = self.config(".config", "CONFIG_RUST=y", "CONFIG_DRM_H713=m")
        rc, out = self.gate("--env", ENV, "--rootfs", Tar(kernel="7.3.1").write(self.tmp.name),
                            "--defconfig", DEFCONFIG, "--kernel-config", built)
        self.assertEqual(rc, 1)
        self.assertIn("ok    the kernel's .config carries CONFIG_RUST=y, CONFIG_DRM_H713=m", out)
        self.assertIn("FAIL  7.3.1 carries no h713_drm, but the kernel's defconfig builds it", out)
        rc, out = self.gate("--env", ENV, "--rootfs", Tar(kernel="7.3.1", drm="7.3.1").write(self.tmp.name),
                            "--defconfig", DEFCONFIG, "--kernel-config", built)
        self.assertEqual(rc, 0, out)
        self.assertIn("ok    7.3.1: h713_drm built for this kernel", out)

    def test_a_defconfig_without_the_clean_stack_asks_nothing(self):
        plain = self.config("defconfig", "CONFIG_DRM=y")
        rc, out = self.gate("--env", ENV, "--rootfs", Tar().write(self.tmp.name), "--defconfig", plain)
        self.assertEqual(rc, 0, out)
        self.assertIn("asks for none of CONFIG_RUST=y, CONFIG_DRM_H713=m", out)
        self.assertIn("6.18.38 carries no h713_drm", out)

    def test_a_defconfig_that_asks_needs_the_kernel_config(self):
        rc, out = self.gate("--env", ENV, "--defconfig", DEFCONFIG)
        self.assertEqual(rc, 1)
        self.assertIn("but no --kernel-config to hold the built kernel against", out)


if __name__ == "__main__":
    unittest.main()
