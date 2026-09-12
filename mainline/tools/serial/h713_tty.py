#!/usr/bin/env python3
"""Resolve the H713 U-Boot CDC ACM tty by USB vendor ID."""

from __future__ import annotations

import glob
import os


USB_SYSFS = "/sys/bus/usb/devices"
ALLWINNER_VID = "1f3a"


def resolve_port(path: str) -> str:
    """Return an explicit tty path, or locate the board when path is ``auto``."""
    if path != "auto":
        return path

    matches: list[str] = []
    for device in glob.glob(f"{USB_SYSFS}/*"):
        try:
            with open(os.path.join(device, "idVendor"), encoding="ascii") as stream:
                if stream.read().strip().lower() != ALLWINNER_VID:
                    continue
        except OSError:
            continue

        matches.extend(glob.glob(f"{device}*:*/tty/*"))

    ttys = sorted({f"/dev/{os.path.basename(match)}" for match in matches})
    if not ttys:
        raise SystemExit(f"H713 board tty not found (USB VID {ALLWINNER_VID})")
    if len(ttys) > 1:
        raise SystemExit(f"multiple Allwinner ttys found: {', '.join(ttys)}; use --port")
    return ttys[0]
