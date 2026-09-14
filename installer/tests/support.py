"""Shared plumbing: load today's tools BY PATH (never copy them), find fixtures,
catch the German console output.  Stage 1 only has to change the paths below."""

import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest
import warnings

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import fakedisk                                            # noqa: E402

# The tools under test: by default the ones next to this directory (installer/), or the
# directory H713_TOOLS_DIR names -- e.g. the old stand-alone scripts, to re-freeze a golden
# value. H713_EXTRACT_PATH overrides the extractor alone (it used to live elsewhere).
TOOLS = os.environ.get("H713_TOOLS_DIR", os.path.dirname(_HERE))
INSTALL_PY = os.path.join(TOOLS, "hy310-install.py")
MKIMAGE_PY = os.path.join(TOOLS, "hy310-mkimage.py")
SELFTEST_PY = os.path.join(TOOLS, "mkimage-selbsttest.py")
EXTRACT_PY = os.environ.get("H713_EXTRACT_PATH", os.path.join(TOOLS, "h713-extract"))
BUILD_OUT = os.environ.get("H713_BUILD_OUT", os.path.join(TOOLS, "out"))
VENDOR_OUT = os.environ.get("H713_VENDOR_OUT", os.path.join(TOOLS, "out", "vendor"))

_PATHS = {"install": ("hy310_install", INSTALL_PY), "extract": ("h713_extract", EXTRACT_PY),
          "mkimage": ("hy310_mkimage", MKIMAGE_PY)}
_loaded = {}


_MARKER = {"install": "abzug_klein", "extract": "Lauf", "mkimage": "gpt_bauen"}


def tool(which):
    """The tool under test, as a module -- or, when the script in H713_TOOLS_DIR is one of
    the thin stage-1 scripts over the h713 package, an adapter that serves the old names
    from the package (see _PackageAdapter)."""
    if which not in _loaded:
        name, path = _PATHS[which]
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _loaded[which] = mod if hasattr(mod, _MARKER[which]) else _PackageAdapter(which)
    return _loaded[which]


class _PackageAdapter:
    """The old names the golden tests were written against, served by the h713 package.

    Stage 1 of doku/121 moved the functions and gave them English names; the frozen values in
    these tests must not change with that move, so the tests keep calling the old names and
    this adapter maps them (argument order is unchanged by design; only keyword names differ).
    Stage 3 rewrites the tests against the package directly and deletes this class."""

    def __init__(self, which):
        self.which = which
        sys.path.insert(0, TOOLS)
        import h713.blockdev, h713.env, h713.fex, h713.gpt, h713.imagewty, h713.layout  # noqa: E401
        import h713.log, h713.source, h713.fs.sparse                                     # noqa: E401
        self.h = h713

    def _disk(self):
        """Disk with the old method names the tests call."""
        Disk = self.h.blockdev.Disk

        class Platte(Disk):
            lies, schreib = Disk.read, Disk.write

            @property
            def sektoren(self):
                return self.sectors
        return Platte

    def _gpt(self):
        Gpt = self.h.gpt.Gpt

        class OldGpt(Gpt):
            ist_gpt = staticmethod(Gpt.is_gpt)

            @property
            def tabelle_ok(self):
                return self.table_ok
        return OldGpt

    def __getattr__(self, name):
        h = self.h
        if self.which == "install":
            table = {
                "env_lesen": h.env.env_read, "env_schreiben": h.env.env_write,
                "ENV_BYTES": h.env.ENV_BYTES, "ENV_LBA": h.env.ENV_LBA,
                "SPERRE_ERSTER": h.blockdev.LOCK_FIRST, "SPERRE_LETZTER": h.blockdev.LOCK_LAST,
                "SECTORS_EXPECTED": h.blockdev.SECTORS_EXPECTED,
                "Platte": lambda pfad, schreiben=False, exklusiv=None:
                    self._disk()(pfad, writable=schreiben, exclusive=exklusiv),
                "ist_sparse": h.fs.sparse.is_sparse,
                "sparse_schreiben": lambda platte, d, plba, trocken=False:
                    h.fs.sparse.write_sparse(platte, d, plba, trocken),
                "stock_plan": self._stock_plan,
                "stock_gpt_bauen": h.gpt.build_stock_gpt,
            }
            if name in table:
                return table[name]
            if name == "abzug_klein":
                import h713.dump
                return lambda platte, ziel, log=h.log.console, unser_layout=False: \
                    h713.dump.dump_small(platte, ziel, log, unser_layout)
            if name == "stock_zurueck":
                import h713.stock
                return lambda platte, image_datei, extraktor=None, log=h.log.console, trocken=False: \
                    h713.stock.restore_stock(platte, image_datei, extraktor, log, trocken,
                                             data_dir=TOOLS)   # the shipped ext4 blob lives next to the scripts
        elif self.which == "extract":
            table = {"DateiQuelle": h.source.FileSource, "Gpt": self._gpt(), "Log": h.log.Log}
            if name in table:
                return table[name]
        elif self.which == "mkimage":
            table = {"gpt_bauen": h.gpt.build_layout_gpt, "gpt_pruefen": h.gpt.check_gpt,
                     "ARR_SEKT": h.layout.GPT_ARRAY_SECTORS}
            if name in table:
                return table[name]
        raise AttributeError("%s adapter: no %r" % (self.which, name))

    def _stock_plan(self, ex, image_q):
        """Old shape (img, partitions, raw) of hy310-install.stock_plan()."""
        h = self.h
        img = h.imagewty.Imagewty(image_q, h.log.Log())
        partitions, raw = h.fex.stock_plan(img)
        return img, partitions, raw


def need(paths):
    """Skip -- naming the file -- when a fixture is not on this machine."""
    gone = fakedisk.missing(paths)
    if gone:
        raise unittest.SkipTest("fixture missing: %s" % ", ".join(gone))


def slow_or_skip():
    if os.environ.get("H713_SLOW_TESTS") != "1":
        raise unittest.SkipTest("slow: set H713_SLOW_TESTS=1 to run it")


def workdir(case):
    """A temp directory that goes away with the test."""
    path = tempfile.mkdtemp(prefix="a4a6-")
    case.addCleanup(shutil.rmtree, path, True)
    return path


class Recorder(object):
    """Stands in for the tools' Konsole: keeps what would go on screen."""

    def __init__(self):
        self.lines = []

    def ok(self, t):
        self.lines.append("OK " + t)

    def info(self, t):
        self.lines.append("INFO " + t)

    def warn(self, t):
        self.lines.append("WARN " + t)

    @property
    def text(self):
        return "\n".join(self.lines)


@contextlib.contextmanager
def quiet():
    """Catch what the extractor prints, and mute the handles it leaks on the way:
    stock_plan()/stock_zurueck() open a DateiQuelle per call and never close it."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            yield buf


@contextlib.contextmanager
def image_source(path):
    """An extractor DateiQuelle that gets closed again -- it has no close()."""
    import pathlib
    source = tool("extract").DateiQuelle(pathlib.Path(path))
    try:
        yield source
    finally:
        source.fh.close()


def digest(obj):
    """A stable fingerprint of a plan, a list of lines, or a text."""
    text = obj if isinstance(obj, str) else repr(obj)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
