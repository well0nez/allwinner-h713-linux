"""h713-install driven as a subprocess, the way a user drives it.

A regular file IS accepted as --device: the tool takes any existing path given with
--device, Disk opens it with os.open(), and the size comes from lseek(SEEK_END).
So the command lines below are the real ones.

Stage 3 (doku/121 §3) turned the switches into subcommands and every text English,
so both golden values below are re-frozen once -- reason "stage 3 texts" -- with the
old value in the comment above them. The runs themselves are the same: the same
steps in the same order, the same exit code, and the disk untouched.
"""

import os
import platform
import re
import shutil
import subprocess
import sys
import types
import unittest

import support                 # imported first: it puts the work dir on sys.path
import fakedisk

TOOL = os.path.join(support.TOOLS, "h713-install")
FORWARDER = support.INSTALL_PY                      # hy310-install.py, now a forwarder


def _tool_module():
    """h713-install as a module -- it has no .py suffix, so it is loaded by path."""
    import importlib.machinery, importlib.util
    support.need([TOOL])
    spec = importlib.util.spec_from_loader(
        "h713_install_tool", importlib.machinery.SourceFileLoader("h713_install_tool", TOOL))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# frozen 2026-09-14 from hy310-install.py 0.1: (exit code, lines, digest of the
# normalised stdout).  Normalisation replaces the temp directory, the device and
# the image path, and the platform name; nothing else in these runs varies.
# C-B froze (0, 36, "f75069a5c52094e4e29b3700f67b827576ef643d55915d8784c16794fc1dc5e2"); stage 2 C1 wired identify() into the installer (Fable);
# was (0, 39, "2df06dfc7fa639b2a0f086108f209783cfeded689e02f0bdeaaac321b311dd54") until stage 3 texts (D1):
# was (0, 39, "d1a21c7154f202072e2fbd350434093b27acbf104500ce734b8cda4008bfa823") until G1 put the
# boot logo into the small dump: three lines of step 3 changed, "bootloader_a/_b 19 files 1.9 MiB"
# -> "20 files 7.8 MiB" and "the same 19 files" -> "20 files". Exit code and 39 lines unchanged;
# the identify line above still says "19 files" -- that one counts mips/ only (h713/facts.py).
DUMP_ONLY = (0, 39, "e9b79974591406ce990b9d17b1dda4ed81bef3bdee0b8a843c236766a78e70b6")
# was b6e41cd4… (D1): re-frozen once more for the stage 3 texts of D2 (h713/fs/ext4.py: the
# "media_data not readable" line is English now); exit code and 39 lines unchanged (Fable, 14.09.).
# was (0, 50, "da0ecc92e5649f29597bd72ca1da1fabe6954f0c756d1d068c9c5d13189f305c") until
# stage 2 C-C: still 50 lines, but UDISK's line turned from "genullt" into the new
# English "left untouched", private/Reserve0_b say who keeps them, and the two
# boot-resource.fex lines note the second copy in the container.
# C-C froze "3f61d6c1…" with UDISK in the default preserve list; UDISK is zeroed again (Fable, C-C review);
# was (0, 53, "09b955f14db23015d0e929180cdc5152f1e76062685ff3ef84955aafabfaee34") until stage 3 texts (D1):
# was (0, 53, "f066a21a87d82f33d297a2727079816bdd49fb6820fb11ed418b8f069298e4e4") until R1 item 2b:
# `restore-stock` now compares the GPT it builds out of sys_partition.fex with the sunxi_gpt.fex
# of the same container before it writes (doku/60 point 12). Six lines more -- one warning and
# the five-row table of the four partitions the HY310 image's two tables spell differently
# (media_data, Reserve0_a, Reserve0_b, UDISK). Exit code, the writes and their order unchanged.
RESTORE_STOCK = (0, 59, "403480294280340d8fabbb04110ed5b06177cda6c04cf28d78c2ea9f2691c662")
# was dd1faf56… (D1): re-frozen once more for the stage 3 texts of D2 (h713/imagewty.py: the five
# IMAGEWTY reader lines are English now); exit code and 53 lines unchanged (Fable, 14.09.).
#
# Layout v4 (P2, 16.09.2026) did NOT re-freeze either of them, and that is the finding, not an
# oversight: both runs are `dump` and `restore-stock`, and neither goes anywhere near the
# install path that was rewritten (write_package, the file set, the mount). Checked by running
# the two tests before and after the rewrite -- same exit code, same line count, same digest.
# What layout v4 does change in this file is further down: `identify` on a release table now
# counts files instead of placeholders, and says so when the table is a v3 one.


class InstallerDryRun(unittest.TestCase):
    def setUp(self):
        support.need(fakedisk.NEEDS_STOCK + (TOOL, support.EXTRACT_PY))
        self.tmp = support.workdir(self)
        self.disk = fakedisk.make_stock_disk(os.path.join(self.tmp, "emmc.img"))
        self.before = fakedisk.journal(self.disk)

    def run_tool(self, *args, **kw):
        proc = subprocess.Popen(
            [sys.executable, kw.get("tool", TOOL)] + list(args),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=self.tmp,
            env=dict(os.environ, TERM="dumb", LC_ALL="C.UTF-8"))
        text = proc.communicate()[0].decode("utf-8", "replace")
        for needle, name in ((self.disk, "<DEV>"), (self.tmp, "<TMP>"),
                             (fakedisk.IMAGES["hy310"], "<IMG>"),
                             (platform.system(), "<PLATFORM>")):
            text = text.replace(needle, name)
        return proc.returncode, re.sub(r"[ \t]+$", "", text, flags=re.M)

    def check(self, frozen, got):
        code, lines, want = frozen
        self.assertEqual(got[0], code, got[1])
        self.assertEqual(len(got[1].splitlines()), lines, got[1])
        self.assertEqual(support.digest(got[1]), want, got[1])
        self.assertEqual(fakedisk.journal(self.disk), self.before, got[1])

    def test_backup_only(self):
        # no --small/--full, exactly as the old --nur-abzug run: the size question is
        # printed and, without a terminal, answered with its default (39 lines, as before).
        got = self.run_tool("dump", "--device", self.disk, "-o", "backup", "--no-write")
        self.check(DUMP_ONLY, got)
        self.assertIn("stock layout, 26 partitions", got[1])
        for name in ("secure-storage", "private", "reserve0-a", "reserve0-b"):
            self.assertTrue(os.path.isfile(
                os.path.join(self.tmp, "backup", "%s.bin" % name)), name)

    def test_restore_stock(self):
        support.need([fakedisk.IMAGES["hy310"]])
        got = self.run_tool("restore-stock", fakedisk.IMAGES["hy310"],
                            "--device", self.disk, "--no-write")
        self.check(RESTORE_STOCK, got)
        self.assertIn("No-write run -- nothing written.", got[1])

    def test_no_write_is_the_old_dry_run(self):
        """--no-write replaces --dry-run and --nur-abzug: the old command line through the
        hidden aliases and the new one produce the same run, modulo the hint lines."""
        old = self.run_tool("--device", self.disk, "--nur-abzug", "--sicherung", "backup",
                            "--abzug", "klein", "--dry-run")
        new = self.run_tool("dump", "--device", self.disk, "-o", "backup",
                            "--small", "--no-write")
        hints = [line for line in old[1].splitlines() if " is now " in line]
        self.assertEqual(len(hints), 4, old[1])            # one line per alias used
        self.assertEqual(old[0], new[0])
        self.assertEqual([line for line in old[1].splitlines() if " is now " not in line],
                         new[1].splitlines())

    def test_the_forwarder_runs_the_new_tool(self):
        support.need([FORWARDER])
        got = self.run_tool("--device", self.disk, "--nur-abzug", "--sicherung", "backup",
                            "--abzug", "klein", "--dry-run", tool=FORWARDER)
        self.assertEqual(got[0], 0, got[1])
        self.assertIn("hy310-install.py is now h713-install dump; running: "
                      "h713-install dump --device <DEV> -o backup --small --no-write",
                      got[1])
        self.assertEqual(fakedisk.journal(self.disk), self.before, got[1])


class AliasHints(unittest.TestCase):
    """Every German switch is still accepted and says in one line what it is now."""

    def test_each_alias_prints_one_hint_line(self):
        sys.path.insert(0, support.TOOLS)
        from h713.install import ALIASES, HINTS, translate
        for old in sorted(ALIASES):
            argv, hints = translate([old, "x"] if ALIASES[old][2] else [old])
            self.assertEqual(len(hints), 1, old)
            self.assertEqual(hints[0], "%s is now %s" % (old, HINTS[old]), old)
            self.assertNotIn(old, argv, old)

    def test_the_aliases_map_onto_the_documented_command_lines(self):
        sys.path.insert(0, support.TOOLS)
        from h713.install import translate
        for argv, want in (
                (["--abbild", "t.json"], ["install", "t.json"]),
                (["--restore", "d.img"], ["restore", "d.img"]),
                (["--restore-stock", "u.img"], ["restore-stock", "u.img"]),
                (["--nur-abzug"], ["dump"]),
                (["--abzug", "voll"], ["dump", "--full"]),
                (["--abzug", "klein"], ["dump", "--small"]),
                (["--nur-abzug", "--sicherung", "b"], ["dump", "-o", "b"]),
                (["--abbild", "t.json", "--sicherung", "b"], ["install", "t.json", "--dump", "b"]),
                (["--abbild", "t.json", "--authorized-key", "k.pub"],
                 ["install", "t.json", "--ssh-key", "k.pub"]),
                (["--abbild", "t.json", "--arbeitskopie", "w.img"],
                 ["install", "t.json", "--work-copy", "w.img"]),
                (["--abbild", "t.json", "--tabelle", "t.json"],
                 ["install", "t.json", "--table", "t.json"]),
                (["--abbild", "t.json", "--env-neu"], ["install", "t.json", "--fresh-env"]),
                (["--abbild", "t.json", "--ohne-erkennung"],
                 ["install", "t.json", "--skip-identify"]),
                (["--abbild", "t.json", "--dry-run"], ["install", "t.json", "--no-write"]),
                (["--extraktor", "/tmp/e", "--nur-abzug"], ["dump"]),
                (["--device", "/dev/sdb", "--nur-abzug"], ["dump", "--device", "/dev/sdb"])):
            self.assertEqual(translate(argv)[0], want, argv)

    def test_a_new_command_line_is_left_alone(self):
        sys.path.insert(0, support.TOOLS)
        from h713.install import translate
        for argv in (["dump", "--full", "-o", "b"], ["install", "DIR", "--ssh-key", "k"],
                     ["identify", "x.img", "--json"], ["extract", "x.img", "-o", "out"],
                     ["--help"], ["--version"]):
            self.assertEqual(translate(argv), (argv, []), argv)


class NoMandatoryDumpOnOurLayout(unittest.TestCase):
    """Stage 2 C5: on our own layout the restore paths take no mandatory small dump."""

    # N2 (Marco, 15.09.): `--dump DIR` now means "take one anyway" -- so this run may not
    # name a directory any more, or it would ask for the very dump it is testing the absence
    # of. Everything else about the test is unchanged; the directory it checks for is the
    # default one, which would appear in the working directory of the run.
    def test_no_mandatory_dump_on_our_layout(self):
        support.need(fakedisk.NEEDS_V3 + (TOOL,))
        tmp = support.workdir(self)
        disk = fakedisk.make_v3_disk(os.path.join(tmp, "emmc-v3.img"))
        proc = subprocess.run(
            [sys.executable, TOOL, "restore-stock", fakedisk.IMAGES["hy310"], "--device", disk,
             "--skip-identify"],
            input="no\n", capture_output=True, text=True, cwd=tmp)
        out = proc.stdout + proc.stderr
        self.assertNotIn("Small dump (mandatory", out)
        self.assertIn("no mandatory dump before the restore", out)
        self.assertFalse(os.path.exists(os.path.join(tmp, "h713-dump")))
        self.assertEqual(proc.returncode, 1, out)          # refused at the YES prompt, nothing written


class ReleaseFolder(unittest.TestCase):
    """`install RELEASE-DIR` finds the table, the parts, u-boot-installer.bin and sunxi-fel
    by itself (api-stufe3.md). The folder here is the real release table of v0.5-beta with
    empty part files next to it -- the discovery is what is under test, not the writing."""

    TABLE = "h713-hy310-v0.5-beta.tabelle.json"

    def setUp(self):
        sys.path.insert(0, support.TOOLS)
        self.release = os.path.join(support.workdir(self), "release")
        os.makedirs(self.release)
        source = os.path.join(fakedisk.FIXTURES, "release", self.TABLE)
        support.need([source])
        shutil.copyfile(source, os.path.join(self.release, self.TABLE))
        from h713.install import image_package
        _dir, self.table = image_package(self.release)
        for part in self.table["teile"]:
            open(os.path.join(self.release, part["datei"]), "wb").close()
        for name in ("u-boot-installer.bin", "sunxi-fel"):
            with open(os.path.join(self.release, name), "wb") as fh:
                fh.write(b"\x7fELF" + b"\0" * 60)

    def test_the_table_is_found_in_the_folder(self):
        from h713.install import image_package
        directory, table = image_package(self.release)
        self.assertEqual(directory, os.path.abspath(self.release))
        self.assertEqual(table["abbild"], "h713-hy310-v0.5-beta")
        self.assertEqual(len(table["teile"]), 3)

    def test_uboot_and_sunxi_fel_are_found_next_to_it(self):
        from h713.install import release_files
        self.assertEqual(release_files(self.release),
                         {"uboot": os.path.join(self.release, "u-boot-installer.bin"),
                          "fel": os.path.join(self.release, "sunxi-fel")})

    def test_a_folder_without_them_simply_has_nothing_to_offer(self):
        from h713.install import release_files
        self.assertEqual(release_files(os.path.dirname(self.release)), {})

    def test_an_old_dump_is_still_read_under_its_v05_names(self):
        """in_dump(): the English name when it exists, else the v0.5-beta spelling (a dump
        made by the old tool stays a way back), else the English path for writing."""
        from h713.install import DUMP_FULL, EXTRACT_DIR, in_dump
        old = os.path.join(support.workdir(self), "hy310-sicherung")
        os.makedirs(os.path.join(old, "extrakt"))
        open(os.path.join(old, "emmc-voll.img"), "wb").close()
        log = support.Recorder()
        self.assertEqual(in_dump(old, DUMP_FULL, log), os.path.join(old, "emmc-voll.img"))
        self.assertEqual(in_dump(old, EXTRACT_DIR, log), os.path.join(old, "extrakt"))
        self.assertEqual(len(log.lines), 2, log.text)
        self.assertIn("v0.5-beta name emmc-voll.img", log.text)
        new = os.path.join(support.workdir(self), "h713-dump")
        os.makedirs(new)
        open(os.path.join(new, "emmc-full.img"), "wb").close()
        self.assertEqual(in_dump(new, DUMP_FULL, log), os.path.join(new, "emmc-full.img"))
        self.assertEqual(in_dump(new, EXTRACT_DIR, log), os.path.join(new, "extract"))
        self.assertEqual(len(log.lines), 2, log.text)      # nothing said for the new names

    def _identify(self, path):
        import contextlib
        import io
        tool = _tool_module()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = tool.main(["identify", path])
        return code, buf.getvalue()

    def test_identify_reads_the_table_itself(self):
        """`identify TABLE.json` lists the pieces and what lies next to the table; exit 0,
        nothing written (the device-test plan's "Vorher 2" check, stage 4)."""
        code, text = self._identify(os.path.join(self.release, self.TABLE))
        self.assertEqual(code, 0, text)
        self.assertIn("release table  h713-hy310-v0.5-beta", text)
        for part in self.table["teile"]:
            self.assertIn(part["datei"], text)
        self.assertIn("truncated?", text)          # the fixture's parts are empty files
        self.assertIn("u-boot-installer.bin                     present", text)

    def test_identify_says_when_a_table_is_a_layout_v3_one(self):
        """The v0.5-beta table above is a placeholder table. `identify` never writes, so it
        reports rather than refuses -- but it says the installer will not take it (v4)."""
        code, text = self._identify(os.path.join(self.release, self.TABLE))
        self.assertEqual(code, 0, text)
        self.assertIn("this image was built for the placeholder layout v3", text)
        self.assertNotIn("files: ", text)

    def test_identify_counts_the_files_of_a_v4_table(self):
        v4 = os.path.join(fakedisk.FIXTURES, "release", "h713-hy310-v4-example.tabelle.json")
        support.need([v4])
        code, text = self._identify(v4)
        self.assertEqual(code, 0, text)
        self.assertIn("release table  h713-hy310-v4-example", text)
        self.assertIn("files: 44 from your own device, 1 of your own", text)
        self.assertNotIn("placeholder layout v3", text)

    def test_the_tool_takes_uboot_and_fel_out_of_the_release_folder(self):
        """main() fills --uboot/--sunxi-fel from the folder before it goes looking for the
        device; expose_drive() is stood in for, so no FEL and no drive are needed here."""
        tool = _tool_module()
        seen = {}

        def instead(args, here):
            seen["args"] = args
            return None, 0
        tool.expose_drive = instead
        self.assertEqual(tool.main(["install", self.release, "--no-write"]), 0)
        self.assertEqual(seen["args"].uboot, os.path.join(self.release, "u-boot-installer.bin"))
        self.assertEqual(seen["args"].fel, os.path.join(self.release, "sunxi-fel"))
        self.assertEqual(seen["args"].dump_dir, "h713-dump")

    def test_the_given_paths_beat_the_folder(self):
        tool = _tool_module()
        seen = {}

        def instead(args, here):
            seen["args"] = args
            return None, 0
        tool.expose_drive = instead
        tool.main(["install", self.release, "--uboot", "/tmp/mine.bin", "--no-write"])
        self.assertEqual(seen["args"].uboot, "/tmp/mine.bin")
        self.assertEqual(seen["args"].fel, os.path.join(self.release, "sunxi-fel"))

    def _pack(self, name):
        """Replace one part by its .img.zst -- that is how the release ships them."""
        path = os.path.join(self.release, name)
        with open(path, "wb") as fh:
            fh.write(b"h713" * 1024)
        subprocess.run(["zstd", "-q", "-f", path, "-o", path + ".zst"], check=True)
        os.remove(path)
        return path

    def test_a_packed_part_is_unpacked_with_zstd(self):
        if not shutil.which("zstd"):
            raise unittest.SkipTest("no zstd binary on this machine")
        from h713.install import unpack_parts
        path = self._pack(self.table["teile"][0]["datei"])
        unpack_parts(self.release, self.table, support.Recorder())
        self.assertTrue(os.path.isfile(path))
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), b"h713" * 1024)

    def test_without_the_zstd_binary_it_says_so_and_names_the_file(self):
        from h713 import install as module
        from h713.install import unpack_parts
        name = self.table["teile"][0]["datei"]
        self._pack(name)
        keep = module.shutil
        module.shutil = types.SimpleNamespace(which=lambda _n: None)
        try:
            with self.assertRaises(RuntimeError) as caught:
                unpack_parts(self.release, self.table, support.Recorder())
        finally:
            module.shutil = keep
        self.assertIn(name + ".zst", str(caught.exception))
        self.assertIn("zstd", str(caught.exception))

    def test_nothing_to_unpack_is_no_work(self):
        from h713.install import unpack_parts
        log = support.Recorder()
        unpack_parts(self.release, self.table, log)
        self.assertEqual(log.lines, [])


class RestoreNoWrite(unittest.TestCase):
    """`restore --no-write` rehearses instead of asking for the YES and then dying in
    Disk.write() -- the one deliberate behaviour change of stage 3 (REPORT.txt)."""

    def test_a_rehearsed_restore_writes_nothing_and_says_so(self):
        support.need(fakedisk.NEEDS_V3 + (TOOL,))
        tmp = support.workdir(self)
        disk = fakedisk.make_v3_disk(os.path.join(tmp, "emmc-v3.img"))
        before = fakedisk.journal(disk)
        dump = os.path.join(tmp, "emmc-full.img")
        with open(dump, "wb") as fh:
            fh.write(b"\xa5" * (1 << 20))
        proc = subprocess.run(
            [sys.executable, TOOL, "restore", dump, "--device", disk, "--skip-identify",
             "--no-write"], stdin=subprocess.DEVNULL, capture_output=True, text=True, cwd=tmp)
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, out)
        self.assertIn("No-write run -- nothing written.", out)
        self.assertNotIn("Type YES to continue", out)
        self.assertNotIn("Traceback", out)
        self.assertEqual(fakedisk.journal(disk), before, out)
        os.remove(dump)
