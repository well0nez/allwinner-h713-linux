# SPDX-License-Identifier: GPL-2.0
"""The U-Boot environment on the eMMC: reading it, writing it, and which keys
survive a reinstall.

Stage 1: moved from hy310-install.py (I:51-65, 68-107). The exception text is
unchanged.
"""

from __future__ import annotations

import struct
import zlib

from .blockdev import SECT

# U-Boot environment in layout v3 (doku/109 §2.1): one copy, 64 KiB, in front a
# CRC32 (little-endian) over the rest, then "k=v\0k=v\0...\0\0".
ENV_LBA = 14336
ENV_SECTORS = 128
ENV_BYTES = ENV_SECTORS * SECT

# Keys that are USER INTENT and survive a reinstall. Everything else
# (bootargs_base, boot_emmc, bootcmd, h713_mips_*) is the business of the
# U-Boot that ships with the image -- had v0.7's environment survived,
# `loglevel=4` from 0033 would never have arrived, silently. h713_gate: whoever
# switched the gate off for the workbench does not want to do it again after an
# upgrade. h713_boot: emmc or net, the same. (Marco, 12.09.: "denk das bitte
# korrekt durch" -- the alternatives were keep everything or discard
# everything, and both are wrong.)
ENV_CARRY_OVER = ("h713_gate", "h713_boot")


def env_read(raw):
    """64 KiB -> dict, or None when the CRC does not match (then it is no
    environment -- empty, Android, junk)."""
    if len(raw) < 8:
        return None
    if struct.unpack("<I", raw[:4])[0] != (zlib.crc32(raw[4:]) & 0xffffffff):
        return None
    out = {}
    for e in raw[4:].split(b"\0"):
        if not e or b"=" not in e:
            if not e:
                # The first double NUL is the end; only padding after it.
                break
            continue
        k, v = e.split(b"=", 1)
        out[k.decode("ascii", "replace")] = v.decode("utf-8", "replace")
    return out


def env_write(d):
    """dict -> 64 KiB with CRC, sorted the way mkenvimage does it."""
    payload = b"".join(("%s=%s" % (k, d[k])).encode("utf-8") + b"\0" for k in sorted(d)) + b"\0"
    if len(payload) > ENV_BYTES - 4:
        raise RuntimeError("environment too big: %d bytes, room for %d" % (len(payload), ENV_BYTES - 4))
    payload = payload.ljust(ENV_BYTES - 4, b"\0")
    return struct.pack("<I", zlib.crc32(payload) & 0xffffffff) + payload
