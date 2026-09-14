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


def tool(which):
    """The unchanged tool of today, as a module."""
    if which not in _loaded:
        name, path = _PATHS[which]
        spec = importlib.util.spec_from_loader(
            name, importlib.machinery.SourceFileLoader(name, path))
        _loaded[which] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_loaded[which])
    return _loaded[which]


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
