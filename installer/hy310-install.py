#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""hy310-install.py -- forwarder onto h713-install, for one release.

Stage 3 of doku/121: the tool is called `h713-install` and has subcommands
(`identify`, `dump`, `install`, `restore`, `restore-stock`, `extract`). The old
command line of v0.5-beta keeps working: this script maps the German switches
onto the new one, says which command it is running, and runs it. FLASHING.md,
the handoffs and everybody's shell history stay valid for one release.

    hy310-install.py --abbild out/h713-hy310-v0.5-beta.tabelle.json \\
        --authorized-key ~/.ssh/id_ed25519.pub --abzug voll
    -> h713-install install out/h713-hy310-v0.5-beta.tabelle.json \\
           --ssh-key ~/.ssh/id_ed25519.pub --full

The mapping itself lives in h713.install.translate(), the same one h713-install
uses for its hidden aliases -- so the two can never drift apart.
"""

import importlib.machinery
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from h713.install import translate                                          # noqa: E402

NEW = os.path.join(HERE, "h713-install")


def main(argv=None):
    raw = sys.argv[1:] if argv is None else list(argv)
    argv, _hints = translate(raw)
    command = argv[0] if argv and not argv[0].startswith("-") else ""
    print("hy310-install.py is now h713-install %s; running: %s"
          % (command, " ".join(["h713-install"] + argv)))
    if not os.path.isfile(NEW):
        print("h713-install is missing -- it belongs next to this script.", file=sys.stderr)
        return 5
    spec = importlib.util.spec_from_loader(
        "h713_install", importlib.machinery.SourceFileLoader("h713_install", NEW))
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return tool.main(argv)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)
