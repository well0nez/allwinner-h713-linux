# SPDX-License-Identifier: GPL-2.0
"""Which device is this? -- the features of a stock image and of a stock drive.

The tables and the two feature helpers come from h713-extract (X:178-207, X:1961), the drive-side
recognition from hy310-install.py (I:1456-1620). Stage 1 of doku/121: identifiers and comments are
English, every user-visible string is unchanged.
"""

from __future__ import annotations

from typing import Optional, Tuple

from h713.blockdev import SECT, device_kind
from h713.fs import Ext4, LpSuper
from h713.gpt import Gpt
from h713.log import Log, console
from h713.profiles import UBOOT_FW_REVS, legacy_devices
from h713.source import SliceSource, Source
from h713.util import sha256_bytes

# Features a device is recognised by even without an image fingerprint (--part, --fex-dir, --no-hash).
# Order = weight of evidence. EDID, MSP patch, monitor, optee, libmspsound.so and the dtb compatible are
# the same on both devices and tell them apart in nothing -- they are checked, but they do not count for
# recognition. Of the MIPS artefacts exactly one file tells the two devices apart: mips/database.TSE
# (0.3, S42 §9) -- with it even a bare bootloader partition can be assigned to a device.
ID_FEATURES = ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version", "arisc_version",
               "build_fingerprint", "mips_database_sha256", "sunxi_version", "vendor_size")
# Only these pin a device down; vendor_size and sunxi_version merely confirm or contradict.
STRONG_FEATURES = ("scp_sha256", "uboot_sha256", "dtb_sha256", "uboot_version", "arisc_version",
                   "build_fingerprint", "mips_database_sha256")


def features_of(profile: dict) -> dict:
    # Two shapes reach this: a row of legacy_devices() ("erwartung"/"paket_item_sha256", what the moved
    # readers hand over) and a board profile of A3 ("expected"/"package_item_sha256"). Same values, so
    # only the two names are looked up -- everything below is X:185 unchanged.
    e = profile["erwartung"] if "erwartung" in profile else profile["expected"]
    if "paket_item_sha256" not in e:
        e = dict(e, paket_item_sha256=e["package_item_sha256"])
    return {"scp_sha256": e["paket_item_sha256"]["scp"], "uboot_sha256": e["paket_item_sha256"]["u-boot"],
            "dtb_sha256": e["paket_item_sha256"]["dtb"], "uboot_version": e["uboot_version"],
            "arisc_version": e["arisc_version"], "build_fingerprint": e["build_fingerprint"],
            "mips_database_sha256": e["mips_database_sha256"],
            "sunxi_version": e["sunxi_version"], "vendor_size": e["vendor_size"]}


def feature_matches(name: str, actual, expected) -> bool:
    if name in ("uboot_version", "arisc_version"):
        return str(actual).startswith(str(expected))
    return actual == expected


# Whole input files recognised by their sha256 -> device (profile key), description
KNOWN_IMAGES = {
    "c518251a00b5cc7b0404e0bb479dc4f18a7558af6df97e9e999d81b31ef3c25d": ("hy310", "HY310 update.img (Stock)"),
    "64c629b15538f897f40caf446a52862a92234797328fbb17bc9fd073354a50d6": ("hy310", "HY310 update_rooted.img (Stock + Root, gleiche Firmware)"),
    "812392c7d3de68433b0716aa94155c38d87898956b9fc7e4998cb12b9e111066": ("l018", "L018 update.img (Stock)"),
    "5d2c5e1d2c4a3af6accfdcb6f5fdff8d88aec055743ffe29b82ceccff0c74851": ("hy310", "HY310 Dev-Gerät, roher eMMC-Dump LBA 0..614399 (300 MiB)"),
}


def firmware_revision_of(data: bytes) -> Optional[dict]:
    """Find a display.bin again by its sha256 in h713_mips_fw_revs[] -- that determines the *used* project id."""
    h = sha256_bytes(data)
    for r in UBOOT_FW_REVS:
        if r["sha256"] == h:
            return r
    return None


class DiskSource:
    """The extractor reads through its source interface; here it lies on the block
    device instead of on a file. Read only."""

    def __init__(self, disk):
        self._d = disk
        self.size = disk.sectors * SECT
        self.name = disk.path

    def read(self, off, n):
        if off < 0 or n < 0:
            raise ValueError("negativer Lesezugriff")
        first = off // SECT
        front = off - first * SECT
        sectors = (front + n + SECT - 1) // SECT
        return self._d.read(first, sectors)[front:front + n]

    def backing(self):
        return None

    def sub(self, off, size, name) -> Source:
        return SliceSource(self, off, size, name)


def identify_device(disk, extractor=None, log=console):
    """What are we dealing with? (plan 110 §8)

    A deliberate path instead of a search: GPT -> super -> LP metadata ->
    vendor -> build.prop. Together about 1.2 MiB, so fractions of a second;
    reading the whole eMMC takes 17 minutes.

    Nothing is computed here: GPT, LP metadata, ext4 reader and the device
    table are in the package. A second copy of them would be exactly the
    double bookkeeping this project has already paid for twice.

    `extractor` is the path to h713-extract. It is still taken so that callers
    do not change, and it is no longer used -- the package imports itself
    (api-h713.md: `_extraktor_laden` is deleted).

    Return: dict with 'layout', and on stock additionally 'fingerprint',
    'geraet', 'bekannt'. Never throws -- whoever does not recognise, says so.
    """
    out = {"layout": None, "fingerprint": None, "geraet": None, "bekannt": False}

    out["layout"] = device_kind(disk.path)
    # Only a stock layout has a vendor partition with build.prop. The text
    # comes from device_kind() -- "Stock-Layout, N Partitionen" or
    # "unser Layout (...)"; check the first word, not the whole sentence
    # (the number of partitions is in it).
    if not (out["layout"] or "").startswith("Stock-Layout"):
        return out

    try:
        q = DiskSource(disk)
        quiet = Log(quiet=True)
        gpt = Gpt(q, quiet)
        sup = gpt.partition(q, "super")
        if sup is None:
            log.warn("Geraeteerkennung: keine Partition 'super'")
            return out
        lp = LpSuper(sup, quiet)
        # In super the names carry the slot suffix ("vendor_a"), on older
        # states without. First the active slot, then the other, then without.
        ven = None
        for name in ("vendor_a", "vendor_b", "vendor"):
            ven = lp.partition(name, quiet)
            if ven is not None:
                out["lp_partition"] = name
                break
        if ven is None:
            # known bug, stage 2 C: `%` binds tighter than `or`, so the fallback
            # "keine" can never appear -- the formatted line is always truthy.
            log.warn("Geraeteerkennung: keine LP-Partition 'vendor' (gefunden: %s)"
                     % ", ".join(getattr(lp, "parts", {})) or "keine")
            return out
        fs = Ext4(ven, None, "vendor", quiet)
        if not fs.exists("/build.prop"):
            log.warn("Geraeteerkennung: /build.prop fehlt in vendor")
            return out
        text = fs.read("/build.prop").decode("utf-8", "replace")
    except Exception as e:                      # noqa: BLE001
        log.warn("Geraeteerkennung abgebrochen: %s" % e)
        return out

    for line in text.splitlines():
        if line.startswith("ro.vendor.build.fingerprint="):
            out["fingerprint"] = line.split("=", 1)[1].strip()
            break
    if not out["fingerprint"]:
        log.warn("Geraeteerkennung: kein ro.vendor.build.fingerprint in build.prop")
        return out

    for gid, profile in legacy_devices().items():
        k = features_of(profile)
        if k.get("build_fingerprint") == out["fingerprint"]:
            out["geraet"], out["bekannt"] = profile.get("name", gid), True
            break
    return out


def interpret_fingerprint(fp) -> Tuple[str, str]:
    """Get the Android version and the build date out of the fingerprint.

    Shape (stock HY310):
      Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/Projector07241019:user/release-keys
      0        1             2           ^^  3               4          ^^^^^^^^
                                  Android 11                      MMDDHHmm = 24.07., 10:19

    The build date sits as MMDDHHmm in the last number of the build field --
    that is how Android counts its builds. The year is nowhere; HY310 is 2025
    (plan 110 §8), so it is not claimed.
    """
    parts = fp.split("/")
    version = "?"
    if len(parts) > 2 and ":" in parts[2]:
        version = parts[2].rsplit(":", 1)[1] or "?"
    date = "?"
    if len(parts) > 4:
        mark = parts[4].split(":")[0]
        digits = "".join(c for c in mark if c.isdigit())
        if len(digits) == 8:
            mm, dd, hh, mi = digits[:2], digits[2:4], digits[4:6], digits[6:]
            if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
                date = "%s.%s., %s:%s Uhr (%s)" % (dd, mm, hh, mi, mark)
            else:
                date = mark
        else:
            date = mark
    return version, date


def report_device(found, log=console, writing=True):
    """Print the recognition in plain words. Return: may writing go on?
    (plan 110 §8, points 3 to 5)

    writing=False (--nur-abzug/--dry-run): an unknown firmware is then no
    reason to stop, but a note -- reading changes nothing anyway
    (issue #1: the message sounded like a stop and then went on)."""
    if found["layout"] and not found["layout"].startswith("Stock-Layout"):
        log.ok("%s -- kein Android mehr, nur der Abzug ist sinnvoll" % found["layout"])
        return True
    if not found["layout"]:
        log.warn("Das Laufwerk sieht nach nichts Bekanntem aus.")
        return True
    if not found["fingerprint"]:
        log.warn("Die Firmware liess sich nicht bestimmen.")
        return True
    version, date = interpret_fingerprint(found["fingerprint"])
    log.info("  Kennung   %s" % found["fingerprint"])
    if found["bekannt"]:
        log.ok("%s erkannt -- Android %s, Stand %s" % (found["geraet"], version, date))
        return True
    if not writing:
        log.warn("Unbekannte Firmware: Android %s, Stand %s -- es wird nur "
                 "gelesen, nichts geschrieben." % (version, date))
        log.info("  Bitte die Kennungszeile oben melden, dann kommt das Geraet")
        log.info("  in die Tabelle (github.com/well0nez/allwinner-h713-linux).")
        return True
    log.error("Unbekannte Firmware: Android %s, Stand %s -- kein Schreiben." % (version, date))
    log.info("  Die Fundstellen einer fremden Version zu raten, kostet im")
    log.info("  schlimmsten Fall den Secure Storage -- deshalb kein Weiter.")
    log.info("  Bitte die Kennungszeile oben melden, dann kommt sie in die Tabelle.")
    return False
