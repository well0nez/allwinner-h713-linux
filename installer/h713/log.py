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

    def __init__(self, color=None):
        if color is None:
            color = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
        self.color = color

    def _c(self, code, text):
        return "\033[%sm%s\033[0m" % (code, text) if self.color else text

    def step(self, n, text):
        print("\n%s %s" % (self._c("1;34", "[%s]" % n), self._c("1", text)))

    def ok(self, text):
        print("  %s %s" % (self._c("32", "OK"), text))

    def warn(self, text):
        print("  %s %s" % (self._c("33", "!"), text))

    def info(self, text):
        print("  %s" % text)

    def error(self, text):
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
