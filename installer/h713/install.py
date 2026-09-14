# SPDX-License-Identifier: GPL-2.0
"""The installation path itself: filling the placeholders of a built image with
the device's own files, checking the image package, carrying the intent keys of
the old U-Boot environment over, and writing everything onto the eMMC in one go.

Stage 1 of plan doku/121: moved from hy310-install.py (I:656-694, 696-923,
1222-1402, 1436-1453). Every printed string, every prompt and every exit code is
unchanged.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
import time

from .blockdev import LOCK_FIRST, LOCK_LAST, SECT, SECTORS_EXPECTED
from .env import ENV_BYTES, ENV_CARRY_OVER, env_read, env_write
from .log import Quiet, console
from .util import duration, mib
from .verify import verify_image, write_image


def fill_placeholders(image, table, sources, log=console):
    """Write the device's own files into the LOCAL image file, before anything
    at all goes onto the eMMC.

    The order is on purpose (Marco, 10.09.): the image is finished on the PC and
    then written ONCE. The other way round -- write first, add later -- costs a
    second pass at 7.7 MB/s, and an abort in between would leave half a system.

    'table' is the offset table that comes out of building the image:
    name -> (byte_offset, length). The image carries placeholders of the right
    size there, so nobody needs an ext4 writer.
    """
    missing = [n for n in table if n not in sources]
    if missing:
        raise RuntimeError("keine Quelle fuer: %s" % ", ".join(sorted(missing)))
    with open(image, "r+b") as f:
        for name in sorted(table):
            off, length = table[name]
            data = sources[name]
            if len(data) > length:
                raise RuntimeError(
                    "%s ist %d Byte gross, der Platzhalter fasst nur %d"
                    % (name, len(data), length))
            f.seek(off)
            f.write(data)
            if len(data) < length:
                f.write(b"\0" * (length - len(data)))   # zero the rest cleanly
            log.ok("%-28s %7d Byte an Offset 0x%x" % (name, len(data), off))
        f.flush()
        os.fsync(f.fileno())


# ---------------------------------------------------------------- SSH key

KEY_TYPES = (b"ssh-ed25519", b"ssh-rsa", b"ecdsa-sha2-nistp256",
             b"ecdsa-sha2-nistp384", b"ecdsa-sha2-nistp521",
             b"sk-ssh-ed25519@openssh.com", b"sk-ecdsa-sha2-nistp256@openssh.com")


def read_public_key(path, length):
    """--authorized-key: prepare the public key as the content for the
    placeholder /root/.ssh/authorized_keys.

    What is checked is what a typo would cost: a private key (that must never
    go into the image), a file without a single key line, NUL bytes, overlength.
    Padding is done with newlines up to the placeholder length -- sshd skips
    empty lines, NUL bytes would make the file unusable (doku/60 point 13, here
    the special case "file smaller than the placeholder"). Return value: exactly
    `length` bytes.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read(length + 1)
    except OSError as e:
        raise RuntimeError("--authorized-key %s: %s" % (path, e))
    if b"PRIVATE KEY" in raw:
        raise RuntimeError("--authorized-key %s ist ein PRIVATER Schluessel -- gemeint ist "
                           "die .pub-Datei. Nichts geschrieben." % path)
    if b"\0" in raw:
        raise RuntimeError("--authorized-key %s enthaelt Nullbytes -- keine Schluesseldatei" % path)
    text = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    lines = [line.strip() for line in text.split(b"\n")]
    lines = [line for line in lines if line]
    hits = [line for line in lines if not line.startswith(b"#") and
            any(line.startswith(kind + b" ") or (b" " + kind + b" ") in line for kind in KEY_TYPES)]
    if not hits:
        raise RuntimeError("--authorized-key %s: keine Zeile sieht wie ein oeffentlicher "
                           "OpenSSH-Schluessel aus (%s ...)"
                           % (path, ", ".join(kind.decode() for kind in KEY_TYPES[:3])))
    content = b"\n".join(lines) + b"\n"
    if len(content) > length:
        raise RuntimeError("--authorized-key %s: %d Byte, der Platzhalter fasst %d -- weniger "
                           "Schluessel oder kuerzere Kommentare" % (path, len(content), length))
    return content.ljust(length, b"\n"), len(hits)


def user_sources(args, user, log=console):
    """Fill the user placeholders of the table (today: authorized_keys).
    Return value: name -> bytes in the full placeholder length, or {} when there
    is nothing to do (then the file stays as built: empty, only newlines)."""
    sources = {}
    if "authorized_keys" in user:
        off, length = user["authorized_keys"]
        if args.authorized_key:
            data, n = read_public_key(args.authorized_key, length)
            sources["authorized_keys"] = data
            log.ok("authorized_keys: %d Schluessel aus %s, %d Byte, mit Zeilenumbruechen auf %d aufgefuellt"
                   % (n, args.authorized_key, len(data.rstrip(b"\n")) + 1, length))
        else:
            log.warn("kein --authorized-key: /root/.ssh/authorized_keys bleibt leer -- auf das "
                     "Geraet kommt man dann nur ueber die serielle Konsole")
    elif args.authorized_key:
        raise RuntimeError("--authorized-key: dieses Abbild hat keinen Platzhalter fuer "
                           "authorized_keys (Tabelle ohne platzhalter_nutzer, aelter als "
                           "11.09.2026) -- der Schluessel kaeme nicht an. Abbruch.")
    unknown = [n for n in user if n != "authorized_keys"]
    if unknown:
        raise RuntimeError("die Tabelle nennt Nutzer-Platzhalter, die dieses Skript nicht "
                           "kennt: %s -- neueres hy310-install noetig" % ", ".join(unknown))
    return sources


def check_placeholders(image, table, sources):
    """Compare back after filling -- on the PC, costs seconds."""
    bad = []
    with open(image, "rb") as f:
        for name, (off, length) in table.items():
            f.seek(off)
            if f.read(len(sources[name])) != sources[name]:
                bad.append(name)
    return bad


# ---------------------------------------------------------------- image package

def image_package(path):
    """Resolve --abbild. Three things are allowed:

      * the table itself         out/hy310-v0.1.tabelle.json
      * the directory around it  out/
      * a single file            irgendwas.img   (then it needs --tabelle)

    Return value: (directory, table|None). The table comes out of hy310-mkimage;
    its structure is documented there.
    """
    if os.path.isdir(path):
        hits = sorted(x for x in os.listdir(path) if x.endswith(".tabelle.json"))
        if len(hits) != 1:
            raise RuntimeError(
                "in %s liegen %d Dateien *.tabelle.json -- bitte die richtige "
                "direkt angeben" % (path, len(hits)))
        path = os.path.join(path, hits[0])
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("format") != "hy310-abbild-tabelle":
            raise RuntimeError("%s ist keine Abbild-Tabelle von hy310-mkimage" % path)
        return os.path.dirname(os.path.abspath(path)), d
    return os.path.dirname(os.path.abspath(path)), None


def check_package(directory, d, log=console):
    """Sizes and checksums of the pieces, before anything is written."""
    for t in d["teile"]:
        p = os.path.join(directory, t["datei"])
        if not os.path.isfile(p):
            raise RuntimeError("%s fehlt -- das Abbild ist unvollstaendig" % t["datei"])
        if os.path.getsize(p) != t["bytes"]:
            raise RuntimeError("%s ist %d Byte, erwartet %d"
                               % (t["datei"], os.path.getsize(p), t["bytes"]))
        h = hashlib.sha256()
        with open(p, "rb") as f:
            while True:
                b = f.read(8 << 20)
                if not b:
                    break
                h.update(b)
        if t.get("sha256") and h.hexdigest() != t["sha256"]:
            raise RuntimeError("%s: sha256 stimmt nicht -- Uebertragung kaputt?" % t["datei"])
        log.ok("%-34s LBA %-9d %11d Byte  %s"
               % (t["datei"], t["lba"], t["bytes"],
                  "sha256 ok" if t.get("sha256") else "sha256 " + h.hexdigest()[:16] + "…"))
    hole = d.get("loch")
    if hole and (hole["lba"], hole["lba"] + hole["sektoren"] - 1) != (LOCK_FIRST, LOCK_LAST):
        raise RuntimeError("die Tabelle sperrt LBA %d..%d, dieses Skript %d..%d -- "
                           "nicht zusammengehoerig"
                           % (hole["lba"], hole["lba"] + hole["sektoren"] - 1,
                              LOCK_FIRST, LOCK_LAST))
    if d.get("disk_sektoren") != SECTORS_EXPECTED:
        raise RuntimeError("die Tabelle ist fuer %s Sektoren gebaut, hier sind %d erwartet"
                           % (d.get("disk_sektoren"), SECTORS_EXPECTED))


# Placeholders a device may also NOT have. Today only the WLAN firmware: not
# every H713 device carries the AIC8800 chip, and h713-extract expressly does
# not treat a missing vendor:/etc/firmware/aic8800d80/ as an error (12.09.2026).
# If the WHOLE set is missing, the placeholders stay zeroed and h713-wifi
# reports "Firmware fehlt" on the device. If only a part is missing, that is a
# finding and no special case -- then abort as with everything else.
OPTIONAL_GROUPS = ("lib/firmware/aic8800_fw/",)


def vendor_sources(directory, table, log=console):
    """Read in the device's own files that h713-extract put down. The names in
    the table are exactly the paths below the --out of h713-extract, so this is
    a putting-together and not a matching-up."""
    sources, missing, too_big = {}, [], []
    for name, (_off, length) in table.items():
        p = os.path.join(directory, name.replace("/", os.sep))
        if not os.path.isfile(p):
            missing.append(name)
            continue
        with open(p, "rb") as f:
            b = f.read()
        if len(b) > length:
            too_big.append("%s (%d > %d)" % (name, len(b), length))
        sources[name] = b
    for prefix in OPTIONAL_GROUPS:
        group = [n for n in table if n.startswith(prefix)]
        gone = [n for n in group if n in missing]
        if group and len(gone) == len(group):
            log.warn("%s: keine der %d Dateien im Abzug -- dieses Geraet hat den Chip "
                     "wohl nicht. Die Platzhalter bleiben genullt, WLAN bleibt aus."
                     % (prefix, len(group)))
            for n in gone:
                sources[n] = b""
                missing.remove(n)
    if missing:
        raise RuntimeError("in %s fehlen %d Datei(en), z. B. %s"
                           % (directory, len(missing), ", ".join(sorted(missing)[:3])))
    if too_big:
        raise RuntimeError("passt nicht in den Platzhalter: %s" % ", ".join(too_big))
    too_small = [n for n, b in sources.items() if len(b) < table[n][1]]
    if too_small:
        # No abort: the placeholder is filled up with zeros. But it means that
        # this firmware has other sizes than the one the image was built
        # against -- that belongs said.
        log.warn("%d Datei(en) sind kleiner als ihr Platzhalter (%s) -- der Rest "
                 "wird genullt. Andere Firmware als beim Bau des Abbilds?"
                 % (len(too_small), ", ".join(sorted(too_small)[:3])))
    return sources


def _load_extractor(path=None, search_dir=None):
    """Load h713-extract as a module -- there sit the IMAGEWTY reader and the
    source classes that we reuse here instead of rebuilding them.
    `search_dir`: where the script ships (the installer directory, passed by the
    calling script); the module directory only as a fallback."""
    if path is None:
        here = search_dir or os.path.dirname(os.path.abspath(__file__))
        for candidate in (os.path.join(here, "h713-extract"),
                          os.path.join(here, "..", "r2-extract", "h713-extract")):
            if os.path.isfile(candidate):
                path = candidate
                break
    if not path or not os.path.isfile(path):
        raise SystemExit("h713-extract nicht gefunden -- es gehoert neben dieses Skript.")
    spec = importlib.util.spec_from_loader(
        "h713_extract", importlib.machinery.SourceFileLoader("h713_extract", path))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run_extractor(dump, target, extractor=None, log=console, search_dir=None):
    """Let h713-extract loose on the dump (plan 110 §3): the user reads the
    proprietary parts out of their own device, not out of a download."""
    ex = _load_extractor(extractor, search_dir)
    log.info("h713-extract %s -> %s" % (os.path.basename(dump), target))
    rc = ex.main([dump, "--out", target, "-q"])
    if rc == 0:
        log.ok("Extraktion vollstaendig und gegen die Referenz geprueft")
    elif rc == 1:
        log.warn("h713-extract meldet Abweichungen (unbekannter Stand oder "
                 "fehlende Teile) -- die Ausgabe liegt trotzdem in %s" % target)
    else:
        raise RuntimeError("h713-extract ist mit Fehler %d ausgestiegen" % rc)
    return rc


# ---------------------------------------------------------------- run

def ask(text, default=None):
    if not sys.stdin.isatty():
        return default
    try:
        answer = input(text).strip().lower()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nAbgebrochen.")
    return answer or default


def confirm(what):
    """A typed confirmation, not a comfortable [j/N] -- and the same abort rule
    at every place that writes (finding S46 B15, plan 110 §9)."""
    console.info("")
    console.warn(what)
    console.info("")
    console.info("  Das hier ist eine Beta. Wenn waehrend des Schreibens etwas")
    console.info("  schiefgeht: NICHT den Strom ziehen und neu starten. Das Geraet")
    console.info("  in den FEL-Modus bringen (Reset halten, Strom einstecken) und")
    console.info("  von vorn anfangen -- die Boot-Kette ist von dort immer erreichbar.")
    console.info("")
    # ask() gives the answer back in lower case -- the comparison has to fit
    # that, otherwise every confirmation fails (10.09.).
    return ask("  Zum Fortfahren JA eintippen: ", "") == "ja"


def carry_env(args, tab, work, part_file, log=console):
    """Write the intent keys of the old environment into the new one -- in the
    working copy of part B, before anything goes onto the eMMC.

    Only when: our layout (otherwise there is no old one), the image brings an
    environment along (bausteine.env, since 12.09.2026; older images have zeros
    there, nothing is invented), the old one was valid, and the user did not say
    --env-neu.
    """
    if args.env_neu or not args._unser_layout:
        return 0
    block = (tab.get("bausteine") or {}).get("env")
    if not block:
        log.info("Umgebung: dieses Abbild bringt keine mit (aelter als 12.09.) -- nichts zu uebernehmen")
        return 0
    old_path = os.path.join(args.sicherung, "uboot-env.bin")
    if not os.path.isfile(old_path):
        return 0
    with open(old_path, "rb") as f:
        old = env_read(f.read())
    if not old:
        return 0
    part_lba = next((t["lba"] for t in tab["teile"] if t["datei"] == part_file), None)
    if part_lba is None or block["lba"] < part_lba:
        log.warn("Umgebung liegt nicht im Teil mit den Platzhaltern -- Uebernahme uebersprungen")
        return 0
    off = (block["lba"] - part_lba) * SECT
    with open(work, "r+b") as f:
        f.seek(off)
        new = env_read(f.read(ENV_BYTES))
        if new is None:
            log.error("Umgebung im Abbild bei Offset 0x%x hat keinen gueltigen CRC" % off)
            return 11
        taken = []
        for k in ENV_CARRY_OVER:
            if k in old and old[k] != new.get(k):
                taken.append("%s=%s (Abbild: %s)" % (k, old[k], new.get(k, "-")))
                new[k] = old[k]
        if not taken:
            log.ok("Umgebung: %s stimmen mit der Vorgabe des Abbilds ueberein -- nichts zu uebernehmen"
                   % ", ".join(ENV_CARRY_OVER))
            return 0
        f.seek(off)
        f.write(env_write(new))
        f.flush()
        os.fsync(f.fileno())
        f.seek(off)
        if env_read(f.read(ENV_BYTES)) != new:
            log.error("Umgebung nach dem Schreiben nicht wie erwartet")
            return 11
    log.ok("Umgebung: aus der alten uebernommen: %s" % "; ".join(taken))
    log.info("  Alles andere kommt vom U-Boot des Abbilds. Die alte liegt in %s." % old_path)
    return 0


def write_package(args, disk, path, directory, tab, here=None):
    """The installation path out of plan 110 §1, steps 4 and 5.

    The order is on purpose (see fill_placeholders): first a working copy of the
    part with the placeholders is filled and read back on the PC, then
    EVERYTHING goes onto the eMMC in one go. An abort on the PC costs nothing;
    an abort in the middle of a second write pass would have left half a system.
    """
    console.step(4, "Abbild pruefen (%s, %s)" % (tab.get("abbild"), tab.get("layout")))
    check_package(directory, tab, console)
    console.info("Loch bei LBA %d..%d (%s) -- bleibt unberuehrt"
                 % (tab["loch"]["lba"], tab["loch"]["lba"] + tab["loch"]["sektoren"] - 1,
                    tab["loch"]["partition"]))

    table = {k: tuple(v) for k, v in tab.get("platzhalter", {}).items()}
    user = {k: tuple(v) for k, v in tab.get("platzhalter_nutzer", {}).items()}
    part_file = tab.get("platzhalter_datei")
    work = None

    # Whoever writes only ONE part -- the boot chain for instance, to renew the
    # bootloader without loading the whole system anew -- does not need the
    # placeholders: they sit in a part that is not touched at all. Without this
    # check the tool laid down a 1.15 GB working copy, filled it and threw it
    # away.
    chosen = {t["datei"] for t in tab["teile"]}
    if (table or user) and part_file not in chosen:
        console.info("Platzhalter uebersprungen: %s wird bei diesem Lauf nicht geschrieben"
                     % part_file)
        if args.authorized_key:
            console.warn("--authorized-key bleibt damit ohne Wirkung")
        table, user = {}, {}

    sources = {}
    if table:
        console.step(5, "Die geraeteeigenen Dateien einsetzen (%d Platzhalter)" % len(table))
        vendor = args.vendor
        if not vendor:
            full = os.path.join(args.sicherung, "emmc-voll.img")
            if os.path.isfile(full):
                vendor = os.path.join(args.sicherung, "extrakt")
                os.makedirs(vendor, exist_ok=True)
                run_extractor(full, vendor, args.extraktor, search_dir=here)
            else:
                console.error("Es gibt weder --vendor noch einen Vollabzug in %s."
                              % args.sicherung)
                console.info("  Die 43 Dateien (Anzeige-Artefakte, Firmware, PQ, WLAN) stehen nur")
                console.info("  auf deinem eigenen Geraet. Ohne sie bleibt das Bild schwarz.")
                console.info("  Also: den VOLLEN Abzug ziehen (--abzug voll) oder ein")
                console.info("  Verzeichnis von h713-extract mit --vendor angeben.")
                return 8
        sources = vendor_sources(vendor, table, console)
        console.ok("%d Dateien aus %s" % (len(sources), vendor))

    # The user's key: same mechanics, other source. Here and not in
    # vendor_sources(), because it does not come out of the device -- and
    # because it must be settable without vendor files as well.
    if user:
        if not table:
            console.step(5, "Den eigenen SSH-Schluessel einsetzen")
        own = user_sources(args, user, console)
        # Only the filled ones are written; an empty placeholder stays as it was
        # built (newlines), and is valid that way.
        for name in own:
            table[name] = user[name]
            sources[name] = own[name]

    if table:
        work = args.arbeitskopie or os.path.join(args.sicherung, "abbild-gefuellt.img")
        source_part = os.path.join(directory, part_file)
        if args.dry_run:
            console.info("WUERDE: %s nach %s kopieren und %d Platzhalter fuellen"
                         % (part_file, work, len(table)))
        else:
            console.info("Arbeitskopie: %s (%.0f MiB)" % (work, mib(os.path.getsize(source_part))))
            shutil.copyfile(source_part, work)
            fill_placeholders(work, table, sources, log=Quiet)
            bad = check_placeholders(work, table, sources)
            if bad:
                console.error("nach dem Fuellen weichen ab: %s" % ", ".join(bad))
                return 9
            console.ok("%d Platzhalter gefuellt und zurueckgelesen -- alle gleich" % len(table))
            rc = carry_env(args, tab, work, part_file, console)
            if rc:
                return rc

    console.step(6, "Auf die eMMC schreiben")
    for t in tab["teile"]:
        console.info("  %-34s ab LBA %-9d %11d Byte" % (t["datei"], t["lba"], t["bytes"]))
    if args.dry_run:
        console.info("Trockenlauf -- nichts geschrieben.")
        return 0
    if not confirm("Das ueberschreibt die eMMC."):
        return 1
    t0 = time.time()
    for t in tab["teile"]:
        file = work if (work and t["datei"] == part_file) else os.path.join(directory, t["datei"])
        write_image(disk, file, lba0=t["lba"])
        console.ok("%s geschrieben" % t["datei"])
    console.ok("alles geschrieben in %s" % duration(time.time() - t0))

    console.step(7, "Zurueckvergleichen")
    errors = 0
    for t in tab["teile"]:
        file = work if (work and t["datei"] == part_file) else os.path.join(directory, t["datei"])
        errors += verify_image(disk, file, samples=4, lba0=t["lba"])
    if errors:
        console.error("%d Stichprobe(n) weichen ab -- nicht neu starten, nachfragen." % errors)
        return 6
    console.ok("Stichproben stimmen")
    # And the acid test: the locked region must not have changed. The small dump
    # has been there since step 3.
    ss = os.path.join(args.sicherung, "secure-storage.bin")
    if os.path.isfile(ss):
        with open(ss, "rb") as f:
            before = f.read()
        after = disk.read(LOCK_FIRST, len(before) // SECT)
        if after == before:
            console.ok("Secure Storage unveraendert (byteweise gegen den Abzug verglichen)")
        else:
            console.error("DER SECURE STORAGE HAT SICH GEAENDERT -- bitte melden, "
                          "nichts weiter tun, %s aufheben." % ss)
            return 10
    console.info("")
    console.info("Fertig. Strom abziehen und wieder einstecken.")
    return 0
