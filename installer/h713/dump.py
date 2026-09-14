# SPDX-License-Identifier: GPL-2.0
"""The backup the installer takes before it writes anything: the device-only
regions, the whole eMMC, the read-back check, the manifest and the question
which of the two sizes it should be.

Stage 1 of plan doku/121: moved from hy310-install.py (I:42, 48-50, 95-101,
462-574, 925-943, 1405-1435). Every printed string is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time

from .blockdev import SECT, SECTORS_EXPECTED
from .env import ENV_BYTES, ENV_CARRY_OVER, ENV_LBA, ENV_SECTORS, env_read
from .install import ask
from .log import console
from .util import duration, mib

# Version of the hy310-install tool (I:42), not the version of the package
# (h713.VERSION): it goes into MANIFEST.json as "werkzeug" and into LIESMICH.txt.
VERSION = "0.1 (Entwurf, doku/110)"

# Regions that exist ONLY on this device: no firmware image in the world brings
# them back. They are always saved, in the small dump as well.
# Evidence: doku/109 §2.3 and §9.1.
UNIQUE_REGIONS = [
    ("secure-storage", 12288, 2048, "HDCP-Schluessel, WLAN-/BT-MAC-Adressen, Seriennummer"),
    ("private", 4891648, 32768, "Android Secure-Storage-Partition"),
    ("reserve0-a", 5489664, 32768, "Reserve0, Slot A"),
    ("reserve0-b", 5522432, 32768, "Reserve0, Slot B"),
]


def dump_small(disk, target, log=console, our_layout=False):
    """Only the regions that exist nowhere else (doku/110 §2).

    our_layout: the GPT carries hy310-* (device_kind). Only then does a U-Boot
    environment lie at LBA 14336; on a stock device Android lies there, and a
    random CRC would be no detection but a coincidence.
    """
    os.makedirs(target, exist_ok=True)
    manifest = []
    empty = []
    for name, lba, sectors, purpose in UNIQUE_REGIONS:
        data = disk.read(lba, sectors)
        path = os.path.join(target, "%s.bin" % name)
        with open(path, "wb") as f:
            f.write(data)
        try:
            os.chmod(path, 0o600)      # key material: the owner only
        except OSError:
            pass
        h = hashlib.sha256(data).hexdigest()
        # A region that is empty throughout means: nothing stands here (any
        # more). On a stock device that would be unusual -- the device has
        # probably been converted once already.
        is_empty = data.count(0) == len(data)
        if is_empty:
            empty.append(name)
        manifest.append((name, lba, sectors, h, purpose + (" [leer]" if is_empty else "")))
        # The hash goes into the manifest (verification), but NOT onto the
        # screen: the one of secure-storage/private is a fingerprint of the
        # device that users otherwise post in logs (Issue #1). Empty regions
        # have nothing secret -- there it may stay.
        # known bug, stage 2 C…: reserve0-a/-b are device-only as well (they
        # stand in UNIQUE_REGIONS), and their hash does go onto the screen.
        # A4A6's tests/test_dump_plan.py pins that as today's behaviour.
        secret = name in ("secure-storage", "private") and not is_empty
        log.ok("%-16s LBA %-8d %5.1f MiB  %s%s"
               % (name, lba, mib(len(data)),
                  "gesichert (Hash im Manifest)" if secret else h[:16] + "…",
                  "  (leer)" if is_empty else ""))
    if empty:
        log.warn("Leer und damit ohne Inhalt: %s." % ", ".join(empty))
        log.info("  Auf einem unangetasteten Geraet stuende dort etwas. Entweder wurde")
        log.info("  dieses Geraet schon einmal umgebaut, oder diese Firmware nutzt die")
        log.info("  Bereiche nicht. Der Secure Storage ist davon unabhaengig.")
    # The U-Boot environment -- only on our layout is there one at all. The new
    # image replaces it with its own default; the intent keys (ENV_CARRY_OVER)
    # are carried over by write_package(), the rest lies here as uboot-env.bin
    # in case someone wants more of it back (fw_setenv).
    if our_layout:
        raw_env = disk.read(ENV_LBA, ENV_SECTORS)
        d = env_read(raw_env) if len(raw_env) == ENV_BYTES else None
        if d is not None:
            path = os.path.join(target, "uboot-env.bin")
            with open(path, "wb") as f:
                f.write(raw_env)
            h = hashlib.sha256(raw_env).hexdigest()
            intent = ", ".join("%s=%s" % (k, d[k]) for k in ENV_CARRY_OVER if k in d) or "keine Absichts-Schluessel"
            manifest.append(("uboot-env", ENV_LBA, ENV_SECTORS, h,
                             "U-Boot-Umgebung, %d Eintraege (%s)" % (len(d), intent)))
            log.ok("%-16s LBA %-8d %5.1f MiB  %s  (%d Eintraege; %s)"
                   % ("uboot-env", ENV_LBA, mib(len(raw_env)), h[:16] + "…", len(d), intent))
        else:
            log.info("uboot-env: unser Layout, aber bei LBA %d liegt keine gueltige Umgebung "
                     "(leer oder ohne CRC) -- nichts zu sichern, nichts zu uebernehmen" % ENV_LBA)
    return manifest


def dump_full(disk, file, log=console):
    """The whole eMMC, with progress. That is the user's failsafe."""
    total = disk.sectors * SECT
    chunk = 4 << 20
    h = hashlib.sha256()
    done = 0
    t0 = time.time()
    with open(file, "wb") as f:
        while done < total:
            n = min(chunk, total - done)
            b = disk.read(done // SECT, n // SECT)
            if len(b) != n:
                raise RuntimeError("nur %d von %d Byte gelesen bei %d" % (len(b), n, done))
            f.write(b)
            h.update(b)
            done += n
            if done % (256 << 20) == 0 or done == total:
                speed = done / max(time.time() - t0, 0.001)
                left = (total - done) / max(speed, 1)
                log.info("  %5.1f%%  %6.1f MiB/s  noch %s" %
                         (100.0 * done / total, mib(speed), duration(left)))
        f.flush()
        os.fsync(f.fileno())
    return h.hexdigest(), time.time() - t0


def verify_dump(disk, file, samples=8):
    """Compare the freshly taken dump against the device. Fixed places
    (start, boot chain, secure storage, end) plus random (finding S46 B5)."""
    total = os.path.getsize(file)
    fixed = [0, 1, 16, 2048, 12288, 14336, 16384, disk.sectors - 8]
    places = fixed + [random.randrange(0, disk.sectors - 64)
                      for _ in range(max(0, samples - len(fixed)))]
    bad = 0
    with open(file, "rb") as f:
        for lba in places:
            n = 8
            if (lba + n) * SECT > total:
                continue
            f.seek(lba * SECT)
            want = f.read(n * SECT)
            if disk.read(lba, n) != want:
                bad += 1
    return bad


def write_manifest(directory, manifest, device):
    data = {
        "erzeugt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "werkzeug": "hy310-install " + VERSION,
        "geraet": device,
        "sektoren": SECTORS_EXPECTED,
        "teile": [{"name": n, "lba": l, "sektoren": s, "sha256": h, "zweck": p}
                  for n, l, s, h, p in manifest],
    }
    with open(os.path.join(directory, "MANIFEST.json"), "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    with open(os.path.join(directory, "LIESMICH.txt"), "w") as f:
        f.write(
            "Sicherung eines HY310/H713-Beamers\n"
            "==================================\n\n"
            "Erzeugt am %s von hy310-install %s.\n\n"
            "Was hier liegt:\n%s\n"
            "Zurueckspielen (Geraet vorher in den FEL-Modus: Reset halten,\n"
            "Strom einstecken):\n\n"
            "    hy310-install --uboot <u-boot.bin> --restore emmc-voll.img\n\n"
            "Die einzelnen .bin-Dateien sind Rohbereiche der eMMC. Sie stehen in\n"
            "keinem Firmware-Abbild -- ohne sie verliert das Geraet HDCP, seine\n"
            "MAC-Adressen und seine Seriennummer. Gut aufheben.\n"
            % (data["erzeugt"], VERSION,
               "".join("  %-18s %s\n" % (t["name"] + ".bin", t["zweck"])
                       for t in data["teile"])))


def choose_dump(args):
    if args.abzug:
        return args.abzug
    console.info("")
    console.info("Der Abzug ist deine Sicherung. Zwei Groessen:")
    console.info("")
    console.info("  klein  49 MiB, rund 10 Sekunden.")
    console.info("         Alles, was es NUR auf diesem Geraet gibt: HDCP-Schluessel,")
    console.info("         die MAC-Adressen von WLAN und Bluetooth, die Seriennummer.")
    console.info("         Das bringt kein Firmware-Abbild der Welt zurueck.")
    console.info("")
    console.info("  voll   7,3 GB, rund 17 Minuten.")
    console.info("         Die ganze eMMC. Damit spielst du dein Geraet 1:1 zurueck,")
    console.info("         Android eingeschlossen, ohne irgendetwas herunterzuladen.")
    console.info("")
    answer = ask("  Welchen Abzug? [klein/voll] ", "klein")
    return "voll" if answer.startswith("v") else "klein"
