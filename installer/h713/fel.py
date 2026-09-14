# SPDX-License-Identifier: GPL-2.0
"""FEL mode: finding sunxi-fel, asking whether a device answers, and telling
the user how to get the projector there.

Stage 1: moved from hy310-install.py (I:46, 420-461). Every printed string is
unchanged.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess

from .log import console

FEL_VID_PID = "1f3a:efe8"


def fel_tool(given=None, search_dir=None):
    """Find sunxi-fel: shipped with us (next to the calling script, `search_dir`),
    in the PATH, or named by the caller."""
    if given:
        if not os.path.isfile(given):
            raise SystemExit("--sunxi-fel %s nicht gefunden" % given)
        return given
    name = "sunxi-fel.exe" if platform.system() == "Windows" else "sunxi-fel"
    here = os.path.join(search_dir or os.path.dirname(os.path.abspath(__file__)), name)
    if os.path.isfile(here):
        return here
    found = shutil.which(name)
    if found:
        return found
    raise SystemExit(
        "sunxi-fel nicht gefunden. Es gehoert neben dieses Skript oder in den PATH.")


def fel_present(fel):
    try:
        p = subprocess.run([fel, "version"], capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    text = p.stdout.decode("latin1", "replace").strip()
    return text if "AWUSBFEX" in text else None


def fel_instructions():
    console.info("")
    console.info("So kommt das Geraet in den FEL-Modus:")
    console.info("  1. Strom abziehen.")
    console.info("  2. Die Reset-Taste gedrueckt halten.")
    console.info("  3. Strom einstecken, Taste noch zwei Sekunden halten, loslassen.")
    console.info("")
    console.info("Das Geraet bleibt dabei dunkel -- das ist richtig so.")
    console.info("Es braucht ein USB-A-auf-A-Kabel, dessen Stromader getrennt ist.")
    console.info("Kein Gehaeuse oeffnen, kein Pad, kein Loeten.")
