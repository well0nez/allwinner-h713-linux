#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Forwarder: the self-test is called mkimage-selftest.py since stage 3 (doku/121).
Kept for one release because release/build-all.sh still calls this name."""

import os
import runpy
import sys

if __name__ == "__main__":
    print("mkimage-selbsttest.py is now `mkimage-selftest.py` -- forwarding", file=sys.stderr)
    sys.argv[0] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mkimage-selftest.py")
    runpy.run_path(sys.argv[0], run_name="__main__")
