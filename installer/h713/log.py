# SPDX-License-Identifier: GPL-2.0
"""Log and console output.

`Log` collects the lines of a run (the extractor's report), `Console` prints
them the way the installer does, and `Quiet` stands in for `console` where the
success lines are noise.

Stage 1: moved from h713-extract (X:280-306) and hy310-install.py (I:118-166).
Every printed string is unchanged.
"""

from __future__ import annotations

import os
import sys


class Log:
    def __init__(self, quiet: bool = False):
        self.lines: list[str] = []
        self.warnings: list[str] = []
        self.quiet = quiet

    def _p(self, s: str):
        self.lines.append(s)
        if not self.quiet:
            print(s, flush=True)

    def info(self, s: str):
        self._p("  " + s)

    def heading(self, s: str):
        self._p("")
        self._p("== " + s)

    def warn(self, s: str):
        self.warnings.append(s)
        self._p("  WARNUNG: " + s)

    def error(self, s: str):
        self._p("  FEHLER: " + s)


class Abort(Exception):
    pass


class Console:
    """Output that stays readable in a Windows command prompt as well."""

    def __init__(self, color=None, style="install"):
        """`style`: "install" is hy310-install's look ("OK", "!", "FEHLER:"), "mkimage"
        is hy310-mkimage's old class K ("OK  ", "HM  ", "FEHL", deeper info indent).
        Both keep their exact old output (stage 1, doku/121)."""
        if color is None:
            color = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
        self.color = color
        if style not in ("install", "mkimage"):
            raise ValueError("unknown console style %r" % (style,))
        self.style = style

    def _c(self, code, text):
        return "\033[%sm%s\033[0m" % (code, text) if self.color else text

    def step(self, n, text):
        if self.style == "mkimage":
            print("\n%s %s" % (self._c("1;36", "[%s]" % n), text))
        else:
            print("\n%s %s" % (self._c("1;34", "[%s]" % n), self._c("1", text)))

    def ok(self, text):
        if self.style == "mkimage":
            print("  %s %s" % (self._c("32", "OK  "), text))
        else:
            print("  %s %s" % (self._c("32", "OK"), text))

    def warn(self, text):
        if self.style == "mkimage":
            print("  %s %s" % (self._c("33", "HM  "), text))
        else:
            print("  %s %s" % (self._c("33", "!"), text))

    def info(self, text):
        if self.style == "mkimage":
            print("       %s" % text)
        else:
            print("  %s" % text)

    def error(self, text):
        if self.style == "mkimage":
            print("  %s %s" % (self._c("1;31", "FEHL"), text), file=sys.stderr)
        else:
            print("\n%s %s" % (self._c("31", "FEHLER:"), text), file=sys.stderr)


console = Console()


class Quiet:
    """Like `console`, but without the 30 success lines while the placeholders
    are filled -- there only "all of them are right" counts. Warnings do come
    through."""

    @staticmethod
    def ok(_t):
        pass

    @staticmethod
    def info(_t):
        pass

    @staticmethod
    def warn(t):
        console.warn(t)
