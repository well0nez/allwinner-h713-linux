#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hy310-mkimage.py -- forwarder. The tool is called `h713-mkimage` since stage 3 (doku/121).

Kept for one release because release/build-all.sh still calls this name. It prints one line
and hands every argument to h713-mkimage, which still accepts the old switches
(--out, --pruefen, --baum-boot, --baum-rootfs).
"""

import importlib.machinery
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NEW = os.path.join(HERE, "h713-mkimage")


def tool():
    """Load h713-mkimage (no .py suffix) as a module, without running it."""
    loader = importlib.machinery.SourceFileLoader("h713_mkimage", NEW)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def main(argv=None):
    print("hy310-mkimage.py is now `h713-mkimage` -- forwarding", file=sys.stderr)
    return tool().main(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
