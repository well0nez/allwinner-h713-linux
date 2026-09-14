"""Stage 2 C9: what the board declares and our layout no longer carries as a partition goes
into the image's U-Boot environment -- h713_project from Reserve0's panel_config.ini."""

import importlib.machinery
import importlib.util
import os
import struct
import sys
import unittest

import support                 # imported first: it puts the tests directory on sys.path
import fakedisk

sys.path.insert(0, support.TOOLS)
from h713.env import ENV_BYTES, env_read, env_write        # noqa: E402
from h713.install import write_env_keys                    # noqa: E402
from h713.source import FileSource                         # noqa: E402

SECT = 512


class _Silent:
    """The installer's console shape (ok/info/warn/error), swallowing everything."""
    def ok(self, _t): pass
    def info(self, _t): pass
    def warn(self, _t): pass
    def error(self, _t): pass


# Stage 3: the tool is h713-install (hy310-install.py is only the forwarder now); it has no
# .py suffix, so it is loaded by path just as before.
TOOL = os.path.join(support.TOOLS, "h713-install")


def _installer_script():
    """The thin h713-install as a module (for _declared_project)."""
    support.need([TOOL])
    spec = importlib.util.spec_from_loader(
        "h713_install_script", importlib.machinery.SourceFileLoader("h713_install_script", TOOL))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class WriteEnvKeys(unittest.TestCase):
    """write_env_keys() sets keys in the environment block of a working copy of part B."""

    def _part(self, env):
        tmp = support.workdir(self)
        work = os.path.join(tmp, "part-b.img")
        with open(work, "wb") as f:
            f.write(b"\xaa" * (4 * SECT))          # 4 sectors of something, then the env
            f.write(env_write(env))
            f.write(b"\x55" * (4 * SECT))
        # part B starts at LBA 14336 (layout v3); the env block is 4 sectors into it
        tab = {"bausteine": {"env": {"lba": 14336 + 4}}, "teile": [{"datei": "b.img", "lba": 14336}]}
        return work, tab

    def test_sets_the_key_and_keeps_the_rest(self):
        work, tab = self._part({"bootcmd": "run boot_emmc", "h713_gate": "1"})
        rc = write_env_keys(tab, work, "b.img", {"h713_project": "0x34"}, _Silent())
        self.assertEqual(rc, 0)
        with open(work, "rb") as f:
            f.seek(4 * SECT)
            env = env_read(f.read(ENV_BYTES))
        self.assertEqual(env["h713_project"], "0x34")
        self.assertEqual(env["h713_gate"], "1")
        self.assertEqual(env["bootcmd"], "run boot_emmc")

    def test_nothing_to_do_when_already_set(self):
        work, tab = self._part({"h713_project": "0x30"})
        before = open(work, "rb").read()
        self.assertEqual(write_env_keys(tab, work, "b.img", {"h713_project": "0x30"}, _Silent()), 0)
        self.assertEqual(open(work, "rb").read(), before)

    def test_no_env_block_is_a_note_not_an_error(self):
        work, tab = self._part({})
        tab = {"bausteine": {}, "teile": tab["teile"]}
        self.assertEqual(write_env_keys(tab, work, "b.img", {"h713_project": "0x34"}, _Silent()), 0)

    def test_broken_crc_is_exit_code_11(self):
        work, tab = self._part({"a": "b"})
        with open(work, "r+b") as f:
            f.seek(4 * SECT + 8)
            f.write(b"\xff")
        self.assertEqual(write_env_keys(tab, work, "b.img", {"h713_project": "0x34"}, _Silent()), 11)


class DeclaredProject(unittest.TestCase):
    """The installer takes the declared project id from the identification of the vendor image."""

    def test_hy310_image_declares_0x30(self):
        support.need([fakedisk.IMAGES["hy310"]])
        import h713.identify
        m = _installer_script()
        ident = h713.identify.identify(FileSource(__import__("pathlib").Path(fakedisk.IMAGES["hy310"])))
        self.assertEqual(m._declared_project(ident), "0x30")

    def test_t08_image_declares_0x34(self):
        support.need([fakedisk.IMAGES["hy300-t08"]])
        import h713.identify
        m = _installer_script()
        ident = h713.identify.identify(FileSource(__import__("pathlib").Path(fakedisk.IMAGES["hy300-t08"])))
        self.assertEqual(m._declared_project(ident), "0x34")

    def test_nothing_declared_is_none(self):
        m = _installer_script()
        self.assertIsNone(m._declared_project({"facts": {}}))
