# SPDX-License-Identifier: GPL-2.0
"""FEL mode: finding sunxi-fel, asking whether a device answers, telling the user
how to get the projector there -- and getting the eMMC exposed as a drive.

Stage 1: moved from hy310-install.py (I:46, 420-461).
Stage 3 (doku/121 §3, "thin CLIs"): `expose_drive()` holds steps 0 to 2 of the old
main() -- drive already there, else FEL, else expose it. Same steps, same order,
same exit codes; only the language changed.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time

from .blockdev import device_kind, find_drive
from .install import ask
from .log import console

FEL_VID_PID = "1f3a:efe8"


def fel_tool(given=None, search_dir=None):
    """Find sunxi-fel: shipped with us (next to the calling script, `search_dir`),
    in the PATH, or named by the caller."""
    if given:
        if not os.path.isfile(given):
            raise SystemExit("--sunxi-fel %s not found" % given)
        return given
    name = "sunxi-fel.exe" if platform.system() == "Windows" else "sunxi-fel"
    here = os.path.join(search_dir or os.path.dirname(os.path.abspath(__file__)), name)
    if os.path.isfile(here):
        return here
    found = shutil.which(name)
    if found:
        return found
    raise SystemExit(
        "sunxi-fel not found. It belongs next to this script or in the PATH.")


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
    console.info("This is how the device gets into FEL mode:")
    console.info("  1. Unplug the power.")
    console.info("  2. Hold the reset button down.")
    console.info("  3. Plug the power in, keep the button down two more seconds, let go.")
    console.info("")
    console.info("The device stays dark while it does -- that is how it should be.")
    console.info("It takes a USB A-to-A cable whose power wire is cut.")
    console.info("No opening the case, no pad, no soldering.")


def expose_drive(args, here):
    """Steps 0 to 2 of the old main(): the exposed drive, else FEL, else the exposure.
    Returns (path, None) or (None, exit code) -- exactly one of the two is set."""
    # --- 0. Is the eMMC already hanging there as a drive? Then FEL is done. (The only way
    #        out of the exposure is a power cycle; whoever starts the tool twice should not
    #        have to begin again.)
    there = find_drive()
    if args.device and not there and os.path.exists(args.device):
        # Whoever names the path expressly means it -- for instance when the identification
        # does not like the device. This case used to fall into the FEL branch and failed
        # there, because the device was long running U-Boot.
        there = [(args.device, 0, "--device")]
    if there:
        if args.device:
            path = args.device
        elif len(there) > 1:
            console.error("Several drives match: %s. Please give --device."
                          % ", ".join(t[0] for t in there))
            return None, 3
        else:
            path = there[0][0]
        console.step(1, "the eMMC is already exposed as a drive")
        try:
            kind = device_kind(path)
        except PermissionError:
            console.error("No read permission on %s. The tool needs elevated rights "
                          "(sudo on Linux, as Administrator on Windows)." % path)
            return None, 3
        if not kind:
            console.error("%s has the right size, but does not look like the projector "
                          "(neither our nor the stock layout)." % path)
            console.info("  With --device it can be forced -- but look first at what kind")
            console.info("  of drive that is.")
            return None, 3
        sectors = next((t[1] for t in there if t[0] == path), 0)
        console.ok("%s, %s sectors, %s -- FEL and exposure skipped" % (path, sectors or "?", kind))
        return path, None

    # --- 1. FEL
    console.step(1, "Look for the device in FEL mode")
    fel = fel_tool(args.fel, search_dir=here)
    banner = fel_present(fel)
    if not banner:
        console.warn("No device found in FEL mode.")
        fel_instructions()
        if ask("\n  Try again? [Y/n] ", "y").startswith("n"):
            return None, 1
        banner = fel_present(fel)
        if not banner:
            console.error("Still nothing. Is the A-to-A cable plugged in?")
            return None, 1
    console.ok(banner.split("\n")[0])
    # Check the SoC id, not the name: the name in soc=00001860(<name>) comes from the
    # sunxi-fel table and is missing on older builds ("unknown"). 0x1860 is the H713
    # (issue #1: the distribution's sunxi-fel reported "(unknown)").
    if "00001860" not in banner:
        console.error("This is no H713 (SoC id 0x1860 not found). Aborted.")
        return None, 1
    if "1860(H713)" not in banner and "(sun50iw12" not in banner:
        console.warn("sunxi-fel does not know this SoC by name -- take the sunxi-fel from "
                     "the release, otherwise the next step fails.")

    # --- 2. Drive exposure
    console.step(2, "Expose the eMMC as a USB drive")
    if not args.uboot:
        console.error("--uboot is missing (U-Boot with the drive exposure).")
        return None, 2
    console.info("loading U-Boot volatile -- not one byte onto the eMMC")
    subprocess.run([fel, "uboot", args.uboot], check=True, timeout=120)
    for _ in range(20):
        time.sleep(1)
        hits = find_drive()
        if hits:
            break
    else:
        console.error("No drive has appeared.")
        return None, 3
    if args.device:
        path = args.device
    elif len(hits) > 1:
        console.error("Several matching drives: %s -- please give --device."
                      % ", ".join(t[0] for t in hits))
        return None, 3
    else:
        path = hits[0][0]
    console.ok("%s, %d sectors (7.28 GiB)" % (path, hits[0][1]))
    return path, None
