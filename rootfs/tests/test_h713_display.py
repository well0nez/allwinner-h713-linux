"""Tests for h713-display (rootfs/overlay): the display stack per boot, against a made-up /proc, /sys, /lib, /etc and
a made-up U-Boot environment behind fw_printenv/fw_setenv. Run: python3 -m unittest rootfs/tests/test_h713_display.py"""
import importlib.machinery
import importlib.util
import io
import lzma
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "overlay", "usr", "local", "sbin", "h713-display")
CONF = os.path.join(HERE, "..", "overlay", "etc", "modprobe.d", "h713-drm.conf")
RELEASE = "6.18.38"
BENCH = "7.3.1-rustbench"
FLAGS = " SMP preempt mod_unload aarch64"
BOOTCMD = ('if test "${h713_display}" = clean; then h713_disp init ${h713_project} noboot logo; setenv h713_display_args '
           '"h713.display=clean module_blacklist=hy310_cpu_comm,sun50i_h713_hdmirx,sun50i_h713_mips,sun50i_h713_msp,'
           'sun50i_h713_afbd"; else h713_disp init ${h713_project} logo; setenv h713_display_args '
           '"module_blacklist=h713_drm"; fi; run boot_${h713_boot}; run boot_net')
BOOT_EMMC = ('if ext4load mmc 1:5 0x60000000 h713-kernel.fit; then setenv bootargs "${bootargs_base} loglevel=4 '
             'root=PARTLABEL=hy310-rootfs rw ${h713_display_args}"; bootm 0x60000000; fi')
CLEAN_CMDLINE = ("console=ttyS0,115200 rootwait loglevel=4 root=PARTLABEL=hy310-rootfs rw h713.display=clean "
                 "module_blacklist=hy310_cpu_comm,sun50i_h713_hdmirx,sun50i_h713_mips,sun50i_h713_msp,sun50i_h713_afbd")
VENDOR_CMDLINE = "console=ttyS0,115200 rootwait loglevel=4 root=PARTLABEL=hy310-rootfs rw module_blacklist=h713_drm"


def load():
    loader = importlib.machinery.SourceFileLoader("h713_display", TOOL)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("h713_display", loader))
    loader.exec_module(mod)
    return mod


def ko(vermagic, name):
    return b"\x7fELF\0\0junk\0" + ("name=%s\0vermagic=%s\0license=GPL\0" % (name, vermagic)).encode()


class Device:
    """A root with a kernel's module tree, the firmware files, the command line and an environment."""

    def __init__(self, kernel=RELEASE, drm_for=None, cmdline=VENDOR_CMDLINE, env=None, firmware=True, dt_node=False,
                 xz=False):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.kernel = kernel
        self.put("proc/cmdline", cmdline + "\n")
        with open(CONF) as f:
            self.put("etc/modprobe.d/h713-drm.conf", f.read())
        dep = ["kernel/drivers/soc/sunxi/sun50i-h713-arisc.ko:",
               "kernel/drivers/gpu/drm/sun50i/sun50i-h713-afbd.ko:"]
        self.put_bytes("lib/modules/%s/kernel/drivers/soc/sunxi/sun50i-h713-arisc.ko" % kernel,
                       ko(kernel + FLAGS, "sun50i_h713_arisc"))
        if drm_for:
            data = ko(drm_for + FLAGS, "h713_drm")
            name = "extra/h713_drm.ko" + (".xz" if xz else "")
            self.put_bytes("lib/modules/%s/%s" % (kernel, name), lzma.compress(data) if xz else data)
            dep.append(name + ": kernel/drivers/soc/sunxi/sun50i-h713-arisc.ko")
        self.put("lib/modules/%s/modules.dep" % kernel, "\n".join(dep) + "\n")
        if firmware:
            for n in ("h713-mips/database.TSE", "h713-mips/pq_custom.TSE", "h713-mips/ProjectID_0x0030.TSE",
                      "hy310-edid.bin"):
                self.put("lib/firmware/" + n, "x")
        if dt_node:
            self.put_bytes("sys/firmware/devicetree/base/soc/display-engine@5600000/compatible",
                           b"allwinner,sun50i-h713-display-engine\0")
        else:
            self.put_bytes("sys/firmware/devicetree/base/soc/afbd@5600000/compatible", b"allwinner,sun50i-h713-afbd\0")
        self.env = {"bootcmd": BOOTCMD, "boot_emmc": BOOT_EMMC, "h713_boot": "emmc", "h713_display": "vendor"} \
            if env is None else env
        self.calls = []
        self.modprobe_rc = {}

    def put(self, rel, text):
        self.put_bytes(rel, text.encode())

    def put_bytes(self, rel, data):
        p = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)

    def run(self, argv):
        self.calls.append(list(argv))
        if argv[0] == "fw_printenv":
            return (0, self.env[argv[2]] + "\n", "") if argv[2] in self.env else \
                (1, "", "## Error: \"%s\" not defined\n" % argv[2])
        if argv[0] == "fw_setenv":
            self.env[argv[1]] = argv[2]
            return 0, "", ""
        if argv[0] == "modprobe":
            rc = self.modprobe_rc.get(argv[1], 0)
            return rc, "", "modprobe: ERROR: could not insert '%s'\n" % argv[1] if rc else ""
        raise AssertionError("unexpected tool %r" % argv)

    def setenvs(self):
        return [c for c in self.calls if c[0] == "fw_setenv"]

    def modprobes(self):
        return [c[1:] for c in self.calls if c[0] == "modprobe"]


class Display(unittest.TestCase):
    def tool(self, d, *args):
        if not getattr(d, "cleanup_set", False):
            self.addCleanup(d.tmp.cleanup)
            d.cleanup_set = True
        m = load()
        m.ROOT = d.dir
        m.run = d.run
        os.environ["H713_UNAME_R"] = getattr(d, "running", d.kernel)
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                rc = m.main(list(args))
        finally:
            del os.environ["H713_UNAME_R"]
        return rc, out.getvalue(), err.getvalue()

    # --- status

    def test_status_on_the_release_kernel_names_what_is_missing(self):
        d = Device()
        rc, out, _ = self.tool(d, "status")
        self.assertEqual(rc, 0)
        self.assertIn("running: the vendor stack (display.bin on the MIPS)", out)
        self.assertIn("next boot: the vendor stack (h713_display=vendor)", out)
        self.assertIn("h713_drm on this kernel (6.18.38): no - the kernel 6.18.38 has no h713_drm", out)
        self.assertIn("CONFIG_RUST", out)
        self.assertIn("h713-mips/database.TSE ok", out)
        self.assertNotIn("a reboot switches", out)
        self.assertEqual(d.setenvs(), [])

    def test_status_on_a_clean_boot_going_back_to_vendor(self):
        d = Device(kernel=BENCH, drm_for=BENCH, cmdline=CLEAN_CMDLINE)
        d.put("sys/module/h713_drm/refcnt", "0")
        rc, out, _ = self.tool(d, "status")
        self.assertEqual(rc, 0)
        self.assertIn("running: the clean stack (h713.display=clean on the command line), h713_drm loaded", out)
        self.assertIn("h713_drm on this kernel (7.3.1-rustbench): loadable", out)
        self.assertIn("a reboot switches to the vendor stack", out)

    def test_status_says_when_the_saved_bootcmd_ignores_the_key(self):
        d = Device(kernel=BENCH, drm_for=BENCH, env={"bootcmd": "h713_disp init ${h713_project} logo; run boot_emmc",
                                                      "h713_display": "clean"})
        _, out, _ = self.tool(d, "status")
        self.assertIn("next boot: the vendor stack - h713_display=clean is set, but the saved bootcmd does not read", out)

    # --- set

    def test_set_clean_refuses_the_release_kernel_without_the_module(self):
        d = Device()
        rc, _, err = self.tool(d, "set", "clean")
        self.assertEqual(rc, 1)
        self.assertIn("not clean: the kernel 6.18.38 has no h713_drm", err)
        self.assertEqual(d.setenvs(), [])
        self.assertEqual(d.env["h713_display"], "vendor")

    def test_set_clean_refuses_a_module_of_another_kernel(self):
        # the clean repository's 7.3.1-rustbench module copied into the release kernel's tree
        d = Device(drm_for=BENCH)
        rc, _, err = self.tool(d, "set", "clean")
        self.assertEqual(rc, 1)
        self.assertIn("h713_drm was built for the kernel 7.3.1-rustbench, this one is 6.18.38 (vermagic mismatch)", err)
        self.assertEqual(d.setenvs(), [])

    def test_set_clean_refuses_other_flags_than_the_kernels(self):
        d = Device(kernel=BENCH, drm_for=BENCH)
        d.put_bytes("lib/modules/%s/extra/h713_drm.ko" % BENCH, ko(BENCH + " SMP mod_unload aarch64", "h713_drm"))
        rc, _, err = self.tool(d, "set", "clean")
        self.assertEqual(rc, 1)
        self.assertIn("(vermagic mismatch)", err)

    def test_set_clean_refuses_an_environment_whose_bootcmd_ignores_the_key(self):
        d = Device(kernel=BENCH, drm_for=BENCH,
                   env={"bootcmd": "h713_disp init ${h713_project} logo; h713_conlog 0x45000000; run boot_${h713_boot}",
                        "boot_emmc": BOOT_EMMC, "h713_boot": "emmc"})
        rc, _, err = self.tool(d, "set", "clean")
        self.assertEqual(rc, 1)
        self.assertIn("the saved bootcmd does not read h713_display", err)
        self.assertEqual(d.setenvs(), [])

    def test_set_clean_refuses_a_boot_path_without_the_display_words(self):
        # boot_rust of docs/kernel-rust.md as it was: h713_boot=rust would boot the vendor drivers without display.bin
        env = {"bootcmd": BOOTCMD, "h713_boot": "rust", "boot_emmc": BOOT_EMMC,
               "boot_rust": 'setenv h713_boot emmc; saveenv; if ext4load mmc 1:5 0x60000000 h713-kernel-rust.fit; then '
                            'setenv bootargs "${bootargs_base} loglevel=4 root=PARTLABEL=hy310-rootfs rw"; bootm; fi'}
        d = Device(kernel=BENCH, drm_for=BENCH, env=env)
        rc, _, err = self.tool(d, "set", "clean")
        self.assertEqual(rc, 1)
        self.assertIn("boot_rust (h713_boot=rust) does not append ${h713_display_args}", err)

    def test_set_clean_refuses_without_database_tse(self):
        d = Device(kernel=BENCH, drm_for=BENCH, firmware=False)
        rc, _, err = self.tool(d, "set", "clean")
        self.assertEqual(rc, 1)
        self.assertIn("/lib/firmware/h713-mips/database.TSE is missing: no picture", err)

    def test_set_clean_on_the_bench_kernel_writes_the_key(self):
        d = Device(kernel=BENCH, drm_for=BENCH, xz=True)
        rc, out, err = self.tool(d, "set", "clean")
        self.assertEqual(rc, 0, err)
        self.assertEqual(d.setenvs(), [["fw_setenv", "h713_display", "clean"]])
        self.assertEqual(d.env["h713_display"], "clean")
        self.assertIn("h713_display = clean, from the next boot on", out)
        self.assertIn("reboot to switch: the vendor stack runs until then", out)
        self.assertIn("no HDCP", out)

    def test_set_clean_for_a_one_shot_boot_into_the_bench_kernel(self):
        # running the release kernel; boot_rust73 boots 7.3.1-rustbench once, with the display words, and goes back
        boot_rust73 = ('setenv h713_boot emmc; setenv h713_display vendor; saveenv; if ext4load mmc 1:5 0x60000000 '
                       'h713-kernel-rustbench73.fit; then setenv bootargs "${bootargs_base} loglevel=4 '
                       'root=PARTLABEL=hy310-rootfs rw ${h713_display_args}"; bootm 0x60000000; fi')
        d = Device(kernel=BENCH, drm_for=BENCH, env={"bootcmd": BOOTCMD, "h713_boot": "rust73",
                                                      "boot_rust73": boot_rust73, "h713_display": "vendor"})
        d.running = RELEASE
        rc, _, err = self.tool(d, "set", "clean")
        self.assertEqual(rc, 1)
        self.assertIn("the kernel 6.18.38 has no h713_drm", err)
        rc, out, err = self.tool(d, "set", "clean", "--kernel", BENCH)
        self.assertEqual(rc, 0, err)
        self.assertEqual(d.env["h713_display"], "clean")

    def test_set_vendor_needs_no_module_and_says_already(self):
        d = Device(env={"bootcmd": BOOTCMD, "boot_emmc": BOOT_EMMC, "h713_display": "clean"})
        rc, out, _ = self.tool(d, "set", "vendor")
        self.assertEqual(rc, 0)
        self.assertEqual(d.env["h713_display"], "vendor")
        rc, out, _ = self.tool(d, "set", "vendor")
        self.assertEqual(rc, 0)
        self.assertIn("h713_display = vendor already", out)
        self.assertEqual(len(d.setenvs()), 1)

    def test_set_refuses_an_environment_fw_printenv_cannot_read(self):
        # fw_setenv on a bad CRC would write an environment of this key alone: no bootcmd, U-Boot at its prompt
        d = Device(env={})
        rc, _, err = self.tool(d, "set", "vendor")
        self.assertEqual(rc, 1)
        self.assertIn("no bootcmd fw_printenv can read", err)
        self.assertEqual(d.setenvs(), [])

    # --- load (h713-display.service)

    def test_load_on_the_vendor_stack_does_nothing(self):
        d = Device(kernel=BENCH, drm_for=BENCH)
        rc, out, _ = self.tool(d, "load")
        self.assertEqual(rc, 0)
        self.assertIn("nothing to load", out)
        self.assertEqual(d.modprobes(), [])

    def test_load_on_a_clean_boot_loads_the_provider_first_and_bench_without_a_node(self):
        d = Device(kernel=BENCH, drm_for=BENCH, cmdline=CLEAN_CMDLINE, env={"h713_display": "clean"})
        rc, out, err = self.tool(d, "load")
        self.assertEqual(rc, 0, err)
        self.assertEqual(d.modprobes(), [["sun50i-h713-arisc"], ["h713_drm", "bench=1"]])
        self.assertIn("h713_drm loaded after sun50i-h713-arisc (bench=1", out)
        self.assertEqual(d.setenvs(), [])

    def test_load_with_a_device_tree_node_passes_no_bench(self):
        d = Device(kernel=BENCH, drm_for=BENCH, cmdline=CLEAN_CMDLINE, dt_node=True)
        self.assertEqual(self.tool(d, "load")[0], 0)
        self.assertEqual(d.modprobes(), [["sun50i-h713-arisc"], ["h713_drm"]])

    def test_load_on_a_kernel_without_the_module_goes_back_to_vendor(self):
        # h713_display=clean carried over by a reinstall onto the release kernel
        d = Device(cmdline=CLEAN_CMDLINE, env={"bootcmd": BOOTCMD, "h713_display": "clean"})
        rc, _, err = self.tool(d, "load")
        self.assertEqual(rc, 1)
        self.assertEqual(d.modprobes(), [])
        self.assertEqual(d.env["h713_display"], "vendor")
        self.assertIn("the clean stack cannot run on 6.18.38", err)
        self.assertIn("h713_display set back to vendor: the next boot runs the vendor stack", err)

    def test_load_whose_modprobe_fails_goes_back_to_vendor(self):
        d = Device(kernel=BENCH, drm_for=BENCH, cmdline=CLEAN_CMDLINE, env={"h713_display": "clean"})
        d.modprobe_rc["h713_drm"] = 1
        rc, _, err = self.tool(d, "load")
        self.assertEqual(rc, 1)
        self.assertIn("modprobe h713_drm bench=1: exit 1", err)
        self.assertEqual(d.env["h713_display"], "vendor")

    def test_the_conf_names_what_the_module_requests(self):
        m = load()
        with open(CONF) as f:
            text = f.read()
        self.assertIn("edid_fw=hy310-edid.bin", text)
        for param, default, _ in m.FIRMWARE[:3]:
            self.assertIn("%s=h713-mips/%s" % (param, os.path.basename(default)), text)


if __name__ == "__main__":
    unittest.main()
