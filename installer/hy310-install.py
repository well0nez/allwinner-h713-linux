#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""
hy310-install -- HY310/H713-Beamer auf Linux umstellen, von einem PC aus.

Laeuft unter Linux und Windows, mit Python 3.9+ und ohne weitere Pakete.
Vorgabe: doku/110-plan-installationsweg.md.

Der ganze Ablauf in vier Schritten:

  1. Geraet in den FEL-Modus bringen: Reset-Taste halten, Strom einstecken.
     (Kein Gehaeuse oeffnen, kein Pad, kein Loeten.)
  2. Dieses Skript starten. Es laedt U-Boot fluechtig ueber USB -- dabei wird
     KEIN Byte auf die eMMC geschrieben -- und laesst es die eMMC als
     USB-Laufwerk freigeben.
  3. Es zieht einen Abzug (Groesse zur Wahl), holt die geraeteeigenen Teile
     daraus und schreibt das neue Abbild.
  4. Strom aus und wieder an. Fertig.

Aus der Laufwerksfreigabe kommt man nur durch Stromabschalten heraus -- das
ist kein Mangel, sondern der Abschluss: danach startet ohnehin das neue System.

Mit --authorized-key DATEI kommt der eigene oeffentliche SSH-Schluessel ins
Abbild (Platzhalter /root/.ssh/authorized_keys, 4096 Byte, aufgefuellt mit
Zeilenumbruechen). Ohne ihn gibt es keinen ssh-Zugang, nur die serielle
Konsole -- das Abbild traegt absichtlich keinen Schluessel (doku/107 §3).
"""

import argparse
import gzip
import hashlib
import importlib.machinery
import os
import platform
import shutil
import struct
import subprocess
import sys
import time
import zlib

VERSION = "0.1 (Entwurf, doku/110)"

SECT = 512
SECTORS_EXPECTED = 15269888          # 7,28 GiB -- die eMMC des HY310
FEL_VID_PID = "1f3a:efe8"

# Bereiche, die es NUR auf diesem Geraet gibt: kein Firmware-Image der Welt
# bringt sie zurueck. Sie werden immer gesichert, auch beim kleinen Abzug.
# Belege: doku/109 §2.3 und §9.1.
# U-Boot-Umgebung in Layout v3 (doku/109 §2.1): eine Kopie, 64 KiB, vorn ein
# CRC32 (little-endian) ueber den Rest, dann "k=v\0k=v\0...\0\0".
ENV_LBA = 14336
ENV_SEKTOREN = 128
ENV_BYTES = ENV_SEKTOREN * SECT

# Schluessel, die NUTZERABSICHT sind und eine Neuinstallation ueberleben. Alles
# andere (bootargs_base, boot_emmc, bootcmd, h713_mips_*) ist Sache des
# U-Boot, das mit dem Abbild kommt -- haette v0.7s Umgebung ueberlebt, waere
# `loglevel=4` aus 0033 nie angekommen, still. h713_gate: wer das Gate fuer
# die Werkbank abgeschaltet hat, will es nach einem Upgrade nicht neu tun.
# h713_boot: emmc oder net, dasselbe. (Marco, 12.09.: "denk das bitte korrekt
# durch" -- die Alternativen waren alles behalten oder alles verwerfen, und
# beide sind falsch.)
ENV_UEBERNEHMEN = ("h713_gate", "h713_boot")


def env_lesen(roh):
    """64 KiB -> dict, oder None wenn der CRC nicht stimmt (dann ist es keine
    Umgebung -- leer, Android, Muell)."""
    if len(roh) < 8:
        return None
    if struct.unpack("<I", roh[:4])[0] != (zlib.crc32(roh[4:]) & 0xffffffff):
        return None
    aus = {}
    for e in roh[4:].split(b"\0"):
        if not e or b"=" not in e:
            if not e:
                # Erstes Doppel-NUL ist das Ende; danach nur Fuellung.
                break
            continue
        k, v = e.split(b"=", 1)
        aus[k.decode("ascii", "replace")] = v.decode("utf-8", "replace")
    return aus


def env_schreiben(d):
    """dict -> 64 KiB mit CRC, sortiert wie mkenvimage es tut."""
    nutz = b"".join(("%s=%s" % (k, d[k])).encode("utf-8") + b"\0" for k in sorted(d)) + b"\0"
    if len(nutz) > ENV_BYTES - 4:
        raise RuntimeError("Umgebung zu gross: %d Byte, Platz fuer %d" % (len(nutz), ENV_BYTES - 4))
    nutz = nutz.ljust(ENV_BYTES - 4, b"\0")
    return struct.pack("<I", zlib.crc32(nutz) & 0xffffffff) + nutz

EINMALIG = [
    ("secure-storage", 12288, 2048, "HDCP-Schluessel, WLAN-/BT-MAC-Adressen, Seriennummer"),
    ("private", 4891648, 32768, "Android Secure-Storage-Partition"),
    ("reserve0-a", 5489664, 32768, "Reserve0, Slot A"),
    ("reserve0-b", 5522432, 32768, "Reserve0, Slot B"),
]

# Der Secure-Storage-Block wird NIE beschrieben, auch nicht mit --force.
# Er ist geraetespezifisch und nicht wiederherstellbar (doku/109 §2.3).
SPERRE_ERSTER = 12288
SPERRE_LETZTER = 14335


def mib(b):
    return b / 2**20


def dauer(sekunden):
    if sekunden < 90:
        return "%.0f s" % sekunden
    return "%.0f min" % (sekunden / 60)


class Konsole:
    """Ausgabe, die auch in einer Windows-Eingabeaufforderung lesbar bleibt."""

    def __init__(self, farbe=None):
        if farbe is None:
            farbe = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
        self.f = farbe

    def _c(self, code, text):
        return "\033[%sm%s\033[0m" % (code, text) if self.f else text

    def schritt(self, n, text):
        print("\n%s %s" % (self._c("1;34", "[%s]" % n), self._c("1", text)))

    def ok(self, text):
        print("  %s %s" % (self._c("32", "OK"), text))

    def warn(self, text):
        print("  %s %s" % (self._c("33", "!"), text))

    def info(self, text):
        print("  %s" % text)

    def fehler(self, text):
        print("\n%s %s" % (self._c("31", "FEHLER:"), text), file=sys.stderr)


K = Konsole()


class _Still:
    """Wie K, aber ohne die 30 Erfolgszeilen beim Fuellen der Platzhalter --
    dort zaehlt nur, dass alle stimmen. Warnungen kommen durch."""

    @staticmethod
    def ok(_t):
        pass

    @staticmethod
    def info(_t):
        pass

    @staticmethod
    def warn(t):
        K.warn(t)


# ---------------------------------------------------------------- Plattform

class Platte:
    """Rohzugriff auf ein Blockgeraet -- unter Linux /dev/sdX, unter Windows
    \\\\.\\PhysicalDriveN. Python oeffnet beides binaer; die Unterschiede sind
    das Finden des Geraets und die Frage, wer es gerade haelt."""

    def __init__(self, pfad, schreiben=False, exklusiv=None):
        self.pfad = pfad
        self.schreiben = schreiben
        if exklusiv is None:
            exklusiv = schreiben
        if exklusiv:
            # Wer noch eingehaengt ist, schreibt seinen Cache ueber unser
            # frisches Abbild zurueck -- und eine Rueckleseprobe ueber denselben
            # Cache meldet trotzdem "stimmt" (Befund S46). Also vorher pruefen.
            offen = eingehaengt(pfad)
            if offen:
                # Der Desktop haengt die Partitionen ungefragt ein, sobald das
                # Laufwerk erscheint -- und zwar NACHEINANDER. Ein einziger
                # Durchgang haengt die erste aus, waehrend die zweite gerade
                # dazukommt (am 11.09. genau so passiert). Also mehrere
                # Durchgaenge, bis zweimal hintereinander nichts mehr da ist.
                K.warn("Der Desktop hat Partitionen eingehaengt: %s"
                       % ", ".join(offen))
                ruhig = 0
                for _ in range(12):
                    aushaengen(pfad, K)
                    time.sleep(0.4)
                    offen = eingehaengt(pfad)
                    ruhig = ruhig + 1 if not offen else 0
                    if ruhig >= 2:
                        break
            if offen:
                raise RuntimeError(
                    "Von %s ist noch etwas eingehaengt und laesst sich nicht "
                    "loesen: %s. Dort arbeitet noch jemand -- schliesse das "
                    "Programm oder haenge von Hand aus ('udisksctl unmount -b "
                    "...'), sonst ueberschreibt das laufende Dateisystem, was "
                    "wir schreiben." % (pfad, ", ".join(offen)))
        flags = os.O_RDWR if schreiben else os.O_RDONLY
        if hasattr(os, "O_BINARY"):          # Windows
            flags |= os.O_BINARY
        if exklusiv and hasattr(os, "O_EXCL"):
            flags |= os.O_EXCL               # Linux: haelt Einhaengungen fern
        # O_EXCL scheitert auch dann mit EBUSY, wenn NICHTS eingehaengt ist:
        # der Desktop (udisks) haelt ein frisch erschienenes Laufwerk kurz
        # offen, um es zu untersuchen. Das dauert Sekundenbruchteile, also
        # ein paar Anlaeufe statt eines Abbruchs -- und zwischendurch noch
        # einmal aushaengen, falls er inzwischen doch eingehaengt hat.
        letzter = None
        for versuch in range(10):
            try:
                self.fd = os.open(pfad, flags)
                break
            except OSError as e:
                letzter = e
                if not (exklusiv and getattr(e, "errno", None) == 16):
                    raise
                if versuch == 0:
                    K.info("  %s ist noch belegt (der Desktop untersucht es) -- "
                           "ich warte" % pfad)
                aushaengen(pfad)
                time.sleep(0.5)
        else:
            offen = eingehaengt(pfad)
            raise RuntimeError(
                "%s ist nach 5 s immer noch belegt%s. Schliesse das Programm, "
                "das darauf zugreift (Dateimanager, Datentraegerverwaltung), "
                "und versuche es erneut." % (pfad,
                    " (eingehaengt: %s)" % ", ".join(offen) if offen else ""))
        self.sektoren = self._groesse() // SECT

    def _groesse(self):
        if platform.system() == "Windows":
            import ctypes
            import ctypes.wintypes as wt
            # IOCTL_DISK_GET_LENGTH_INFO
            handle = ctypes.windll.kernel32._get_osfhandle(self.fd)
            buf = ctypes.create_string_buffer(8)
            ret = wt.DWORD()
            if not ctypes.windll.kernel32.DeviceIoControl(
                    handle, 0x0007405C, None, 0, buf, 8, ctypes.byref(ret), None):
                raise OSError("Groesse des Laufwerks nicht lesbar")
            return int.from_bytes(buf.raw[:8], "little")
        return os.lseek(self.fd, 0, os.SEEK_END)

    def lies(self, lba, sektoren):
        os.lseek(self.fd, lba * SECT, os.SEEK_SET)
        rest = sektoren * SECT
        teile = []
        while rest:
            b = os.read(self.fd, min(rest, 4 << 20))
            if not b:
                break
            teile.append(b)
            rest -= len(b)
        return b"".join(teile)

    def schreib(self, lba, daten):
        if not self.schreiben:
            raise RuntimeError("nur zum Lesen geoeffnet")
        ende = lba + (len(daten) + SECT - 1) // SECT - 1
        if lba <= SPERRE_LETZTER and ende >= SPERRE_ERSTER:
            raise RuntimeError(
                "Schreibversuch auf LBA %d..%d beruehrt den Secure Storage "
                "(%d..%d). Dort stehen HDCP-Schluessel, die MAC-Adressen und "
                "die Seriennummer dieses Geraets -- nicht wiederherstellbar."
                % (lba, ende, SPERRE_ERSTER, SPERRE_LETZTER))
        os.lseek(self.fd, lba * SECT, os.SEEK_SET)
        blick = memoryview(daten)
        while blick:
            n = os.write(self.fd, blick[:4 << 20])
            blick = blick[n:]

    def sync(self):
        try:
            os.fsync(self.fd)
        except OSError:
            pass

    def close(self):
        self.sync()
        os.close(self.fd)


def eingehaengt(pfad, roh=False):
    """Welche Partitionen dieses Laufwerks sind gerade eingehaengt?

    roh=False: Liste lesbarer Zeilen fuer die Meldung.
    roh=True:  Liste der Geraetepfade -- die braucht aushaengen().
    """
    treffer = []
    if platform.system() != "Linux":
        return treffer
    try:
        with open("/proc/self/mounts") as f:
            zeilen = f.read().splitlines()
    except OSError:
        return treffer
    basis = os.path.realpath(pfad)
    for z in zeilen:
        teile = z.split()
        if len(teile) < 2:
            continue
        quelle = os.path.realpath(teile[0])
        if quelle == basis or (quelle.startswith(basis) and quelle[len(basis):].isdigit()):
            treffer.append(teile[0] if roh else "%s auf %s" % (teile[0], teile[1]))
    return treffer


def aushaengen(pfad, log=None):
    """Die Partitionen dieses Laufwerks aushaengen und sagen, was passiert.

    Warum es das gibt: sobald die eMMC als Laufwerk erscheint, haengt jede
    Desktop-Oberflaeche die lesbaren Partitionen von selbst ein -- unter Linux
    Mint binnen einer Sekunde. Frueher brach der Installer dann ab und der
    Nutzer musste von Hand aushaengen; beim ersten scharfen Lauf am 10.09. hat
    genau das drei Anlaeufe gekostet. Ausgehaengt wird nur, was zu DIESEM
    Laufwerk gehoert, und nur, was wir gerade selbst schreiben wollen.

    Rueckgabe: (ausgehaengt, geblieben) als Listen von Geraetepfaden.
    """
    ausgehaengt, geblieben = [], []
    for dev in eingehaengt(pfad, roh=True):
        for befehl in (["udisksctl", "unmount", "-b", dev],
                       ["umount", dev]):
            try:
                r = subprocess.run(befehl, capture_output=True, timeout=20)
            except (OSError, subprocess.SubprocessError):
                continue
            if r.returncode == 0:
                ausgehaengt.append(dev)
                break
        else:
            geblieben.append(dev)
    if log:
        for dev in ausgehaengt:
            log.info("  %s ausgehaengt" % dev)
    return ausgehaengt, geblieben


def ist_unser_geraet(pfad):
    """Inhaltlich pruefen, ob das wirklich der Beamer ist -- die Sektorzahl
    allein reicht nicht, eine fremde Platte kann zufaellig gleich gross sein
    (Befund S46). Erkannt wird entweder unser eigenes Layout oder das Stock-
    Layout; beides an den Partitionsnamen der GPT."""
    import struct
    try:
        p = Platte(pfad, schreiben=False, exklusiv=False)
    except PermissionError:
        # Ohne Leserechte laesst sich nichts sagen -- das ist etwas anderes
        # als "sieht nicht wie der Beamer aus" und darf nicht so klingen.
        raise
    except OSError:
        return None
    try:
        kopf = p.lies(1, 1)
        if kopf[:8] != b"EFI PART":
            return "keine GPT"
        entlba, nent, entsz = struct.unpack_from("<QII", kopf, 72)
        if nent > 128 or entsz not in (128, 256):
            return "GPT unplausibel"
        arr = p.lies(entlba, (nent * entsz + SECT - 1) // SECT)
        namen = []
        for i in range(nent):
            e = arr[i * entsz:(i + 1) * entsz]
            if e[:16] == b"\0" * 16:
                continue
            namen.append(e[56:56 + 72].decode("utf-16-le", "replace").rstrip("\0"))
    finally:
        p.close()
    if any(n.startswith("hy310-") for n in namen):
        return "unser Layout (%s)" % ", ".join(n for n in namen if n.startswith("hy310-"))
    if "bootloader_a" in namen and "super" in namen:
        return "Stock-Layout, %d Partitionen" % len(namen)
    return None


def finde_laufwerk(erwartet=SECTORS_EXPECTED):
    """Das freigegebene Laufwerk suchen: richtige Groesse UND Wechselmedium.
    Der Inhaltsabgleich passiert in ist_unser_geraet()."""
    system = platform.system()
    treffer = []
    if system == "Linux":
        for name in sorted(os.listdir("/sys/block")):
            if not name.startswith(("sd", "vd")):
                continue
            try:
                with open("/sys/block/%s/size" % name) as f:
                    n = int(f.read().strip())
                with open("/sys/block/%s/removable" % name) as f:
                    wechsel = f.read().strip() == "1"
            except OSError:
                continue
            if n == erwartet and wechsel:
                treffer.append(("/dev/" + name, n, wechsel))
    elif system == "Windows":
        for i in range(16):
            pfad = r"\\.\PhysicalDrive%d" % i
            try:
                p = Platte(pfad)
                n = p.sektoren
                p.close()
            except OSError:
                continue
            if n == erwartet:
                treffer.append((pfad, n, True))
    else:
        raise SystemExit("Nicht unterstuetztes System: %s" % system)
    return treffer


# ---------------------------------------------------------------- FEL

def fel_werkzeug(vorgabe=None):
    """sunxi-fel finden: mitgeliefert, im Pfad, oder vom Aufrufer benannt."""
    if vorgabe:
        if not os.path.isfile(vorgabe):
            raise SystemExit("--sunxi-fel %s nicht gefunden" % vorgabe)
        return vorgabe
    name = "sunxi-fel.exe" if platform.system() == "Windows" else "sunxi-fel"
    hier = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    if os.path.isfile(hier):
        return hier
    gefunden = shutil.which(name)
    if gefunden:
        return gefunden
    raise SystemExit(
        "sunxi-fel nicht gefunden. Es gehoert neben dieses Skript oder in den PATH.")


def fel_da(fel):
    try:
        p = subprocess.run([fel, "version"], capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0:
        return None
    text = p.stdout.decode("latin1", "replace").strip()
    return text if "AWUSBFEX" in text else None


def fel_anleitung():
    K.info("")
    K.info("So kommt das Geraet in den FEL-Modus:")
    K.info("  1. Strom abziehen.")
    K.info("  2. Die Reset-Taste gedrueckt halten.")
    K.info("  3. Strom einstecken, Taste noch zwei Sekunden halten, loslassen.")
    K.info("")
    K.info("Das Geraet bleibt dabei dunkel -- das ist richtig so.")
    K.info("Es braucht ein USB-A-auf-A-Kabel, dessen Stromader getrennt ist.")
    K.info("Kein Gehaeuse oeffnen, kein Pad, kein Loeten.")


# ---------------------------------------------------------------- Abzug

def abzug_klein(platte, ziel, log=K, unser_layout=False):
    """Nur die Bereiche, die es sonst nirgends gibt (doku/110 §2).

    unser_layout: die GPT traegt hy310-* (ist_unser_geraet). Nur dann liegt bei
    LBA 14336 eine U-Boot-Umgebung; auf einem Stock-Geraet liegt dort Android,
    und ein Zufalls-CRC waere keine Erkennung, sondern ein Zufall.
    """
    os.makedirs(ziel, exist_ok=True)
    manifest = []
    leer = []
    for name, lba, sektoren, zweck in EINMALIG:
        daten = platte.lies(lba, sektoren)
        pfad = os.path.join(ziel, "%s.bin" % name)
        with open(pfad, "wb") as f:
            f.write(daten)
        try:
            os.chmod(pfad, 0o600)      # Schluesselmaterial: nur der Eigentuemer
        except OSError:
            pass
        h = hashlib.sha256(daten).hexdigest()
        # Ein durchgehend leerer Bereich heisst: hier steht nichts (mehr).
        # Auf einem Stock-Geraet waere das ungewoehnlich -- vermutlich wurde
        # das Geraet schon einmal umgebaut.
        ist_leer = daten.count(0) == len(daten)
        if ist_leer:
            leer.append(name)
        manifest.append((name, lba, sektoren, h, zweck + (" [leer]" if ist_leer else "")))
        # Der Hash geht ins Manifest (Verifikation), aber NICHT auf den Schirm:
        # der von secure-storage/private ist ein Fingerabdruck des Geraets, den
        # Nutzer sonst in Logs posten (Issue #1). Leere Bereiche haben nichts
        # Geheimes -- da darf er stehen bleiben.
        geheim = name in ("secure-storage", "private") and not ist_leer
        log.ok("%-16s LBA %-8d %5.1f MiB  %s%s"
               % (name, lba, mib(len(daten)),
                  "gesichert (Hash im Manifest)" if geheim else h[:16] + "…",
                  "  (leer)" if ist_leer else ""))
    if leer:
        log.warn("Leer und damit ohne Inhalt: %s." % ", ".join(leer))
        log.info("  Auf einem unangetasteten Geraet stuende dort etwas. Entweder wurde")
        log.info("  dieses Geraet schon einmal umgebaut, oder diese Firmware nutzt die")
        log.info("  Bereiche nicht. Der Secure Storage ist davon unabhaengig.")
    # Die U-Boot-Umgebung -- nur auf unserem Layout ueberhaupt eine. Das neue
    # Abbild ersetzt sie durch seine Vorgabe; die Absichts-Schluessel
    # (ENV_UEBERNEHMEN) traegt _paket_schreiben() hinueber, der Rest liegt
    # hier als uboot-env.bin, falls jemand mehr zurueck will (fw_setenv).
    if unser_layout:
        umg = platte.lies(ENV_LBA, ENV_SEKTOREN)
        d = env_lesen(umg) if len(umg) == ENV_BYTES else None
        if d is not None:
            pfad = os.path.join(ziel, "uboot-env.bin")
            with open(pfad, "wb") as f:
                f.write(umg)
            h = hashlib.sha256(umg).hexdigest()
            absicht = ", ".join("%s=%s" % (k, d[k]) for k in ENV_UEBERNEHMEN if k in d) or "keine Absichts-Schluessel"
            manifest.append(("uboot-env", ENV_LBA, ENV_SEKTOREN, h,
                             "U-Boot-Umgebung, %d Eintraege (%s)" % (len(d), absicht)))
            log.ok("%-16s LBA %-8d %5.1f MiB  %s  (%d Eintraege; %s)"
                   % ("uboot-env", ENV_LBA, mib(len(umg)), h[:16] + "…", len(d), absicht))
        else:
            log.info("uboot-env: unser Layout, aber bei LBA %d liegt keine gueltige Umgebung "
                     "(leer oder ohne CRC) -- nichts zu sichern, nichts zu uebernehmen" % ENV_LBA)
    return manifest


def abzug_voll(platte, datei, log=K):
    """Die ganze eMMC, mit Fortschritt. Das ist das Failsafe des Nutzers."""
    gesamt = platte.sektoren * SECT
    stueck = 4 << 20
    h = hashlib.sha256()
    getan = 0
    t0 = time.time()
    with open(datei, "wb") as f:
        while getan < gesamt:
            n = min(stueck, gesamt - getan)
            b = platte.lies(getan // SECT, n // SECT)
            if len(b) != n:
                raise RuntimeError("nur %d von %d Byte gelesen bei %d" % (len(b), n, getan))
            f.write(b)
            h.update(b)
            getan += n
            if getan % (256 << 20) == 0 or getan == gesamt:
                v = getan / max(time.time() - t0, 0.001)
                rest = (gesamt - getan) / max(v, 1)
                log.info("  %5.1f%%  %6.1f MiB/s  noch %s" %
                         (100.0 * getan / gesamt, mib(v), dauer(rest)))
        f.flush()
        os.fsync(f.fileno())
    return h.hexdigest(), time.time() - t0


# ---------------------------------------------------------------- Abbild schreiben

def pruefe_abzug(platte, datei, stichproben=8):
    """Den frisch gezogenen Abzug gegen das Geraet vergleichen. Feste Stellen
    (Anfang, Boot-Kette, Secure Storage, Ende) plus Zufall (Befund S46 B5)."""
    import random
    gesamt = os.path.getsize(datei)
    fest = [0, 1, 16, 2048, 12288, 14336, 16384, platte.sektoren - 8]
    stellen = fest + [random.randrange(0, platte.sektoren - 64)
                      for _ in range(max(0, stichproben - len(fest)))]
    schlecht = 0
    with open(datei, "rb") as f:
        for lba in stellen:
            n = 8
            if (lba + n) * SECT > gesamt:
                continue
            f.seek(lba * SECT)
            soll = f.read(n * SECT)
            if platte.lies(lba, n) != soll:
                schlecht += 1
    return schlecht


def abbild_schreiben(platte, datei, log=K, lba0=0):
    """Unser Abbild auf die eMMC. Die Sperre in Platte.schreib() haelt den
    Secure Storage frei -- das Abbild ist so gebaut, dass es ihn ausspart.

    'lba0' ist der Sektor, an dem die Datei beginnt. Unser Abbild kommt in drei
    Stuecken (hy310-mkimage): eines ab 0, eines ab 14336, eines am Plattenende.
    Ein Vollabzug ist ein Stueck ab 0 -- die Vorgabe."""
    gesamt = os.path.getsize(datei)
    if lba0 * SECT + gesamt > platte.sektoren * SECT:
        raise RuntimeError("Abbild (%.1f MiB ab LBA %d) ist groesser als die eMMC"
                           % (mib(gesamt), lba0))
    stueck = 4 << 20
    getan = 0
    t0 = time.time()
    with open(datei, "rb") as f:
        while True:
            b = f.read(stueck)
            if not b:
                break
            lba = lba0 + getan // SECT
            ende = lba + (len(b) + SECT - 1) // SECT - 1
            if lba <= SPERRE_LETZTER and ende >= SPERRE_ERSTER:
                # Das Stueck ueberlappt den geschuetzten Block: in drei Teile
                # zerlegen und den mittleren auslassen.
                for teil_lba, teil in _um_sperre(lba, b):
                    platte.schreib(teil_lba, teil)
            else:
                platte.schreib(lba, b)
            getan += len(b)
            if getan % (128 << 20) == 0 or getan == gesamt:
                v = getan / max(time.time() - t0, 0.001)
                log.info("  %5.1f%%  %6.1f MiB/s  noch %s" %
                         (100.0 * getan / gesamt, mib(v),
                          dauer((gesamt - getan) / max(v, 1))))
    platte.sync()
    return time.time() - t0


def _um_sperre(lba, daten):
    """Ein Schreibstueck in die Teile vor und hinter dem Secure Storage zerlegen."""
    teile = []
    n = len(daten) // SECT
    vor = SPERRE_ERSTER - lba
    if vor > 0:
        teile.append((lba, daten[:vor * SECT]))
    nach_lba = SPERRE_LETZTER + 1
    if lba + n > nach_lba:
        off = (nach_lba - lba) * SECT
        teile.append((nach_lba, daten[off:]))
    return teile


def pruefe_abbild(platte, datei, stichproben=6, log=K, lba0=0):
    """Nach dem Schreiben stichprobenweise zurueckvergleichen."""
    import random
    gesamt = os.path.getsize(datei)
    fehler = 0
    with open(datei, "rb") as f:
        stellen = [0, gesamt - (1 << 20)]
        stellen += [random.randrange(0, max(gesamt - (1 << 20), 1))
                    for _ in range(stichproben - 2)]
        for off in stellen:
            off -= off % SECT
            if off < 0:
                continue
            lba = lba0 + off // SECT
            if lba <= SPERRE_LETZTER and lba + 2048 >= SPERRE_ERSTER:
                continue                       # der gesperrte Block, absichtlich anders
            f.seek(off)
            soll = f.read(1 << 20)
            if not soll:
                continue
            ist = platte.lies(lba, len(soll) // SECT)
            if ist != soll:
                log.warn("Abweichung bei LBA %d" % lba)
                fehler += 1
    return fehler


# ---------------------------------------------------------------- Platzhalter

def platzhalter_fuellen(abbild, tabelle, quellen, log=K):
    """Die geraeteeigenen Dateien in die LOKALE Abbild-Datei schreiben, bevor
    irgendetwas auf die eMMC geht.

    Reihenfolge ist Absicht (Marco, 10.09.): das Abbild wird am PC fertig
    gemacht und dann EINMAL geschrieben. Andersherum -- erst schreiben, dann
    nachtragen -- kostet bei 7,7 MB/s einen zweiten Durchlauf, und ein Abbruch
    dazwischen hinterliesse ein halbes System.

    'tabelle' ist die Offsettabelle, die beim Bau des Abbilds entsteht:
    Name -> (byte_offset, laenge). Das Abbild enthaelt dort Platzhalter
    richtiger Groesse, deshalb braucht niemand einen ext4-Schreiber.
    """
    fehlend = [n for n in tabelle if n not in quellen]
    if fehlend:
        raise RuntimeError("keine Quelle fuer: %s" % ", ".join(sorted(fehlend)))
    with open(abbild, "r+b") as f:
        for name in sorted(tabelle):
            off, laenge = tabelle[name]
            daten = quellen[name]
            if len(daten) > laenge:
                raise RuntimeError(
                    "%s ist %d Byte gross, der Platzhalter fasst nur %d"
                    % (name, len(daten), laenge))
            f.seek(off)
            f.write(daten)
            if len(daten) < laenge:
                f.write(b"\0" * (laenge - len(daten)))   # Rest sauber nullen
            log.ok("%-28s %7d Byte an Offset 0x%x" % (name, len(daten), off))
        f.flush()
        os.fsync(f.fileno())


# ---------------------------------------------------------------- SSH-Schluessel

SCHLUESSEL_ARTEN = (b"ssh-ed25519", b"ssh-rsa", b"ecdsa-sha2-nistp256",
                    b"ecdsa-sha2-nistp384", b"ecdsa-sha2-nistp521",
                    b"sk-ssh-ed25519@openssh.com", b"sk-ecdsa-sha2-nistp256@openssh.com")


def schluessel_lesen(pfad, laenge):
    """--authorized-key: den oeffentlichen Schluessel als Inhalt fuer den
    Platzhalter /root/.ssh/authorized_keys aufbereiten.

    Geprueft wird, was ein Tippfehler kosten wuerde: ein privater Schluessel
    (der darf nie ins Abbild), eine Datei ohne eine einzige Schluesselzeile,
    Nullbytes, Ueberlaenge. Aufgefuellt wird mit Zeilenumbruechen bis zur
    Platzhalterlaenge -- sshd ueberliest Leerzeilen, Nullbytes machten die
    Datei unbrauchbar (doku/60 Punkt 13, hier der Sonderfall "Datei kleiner
    als Platzhalter"). Rueckgabe: genau `laenge` Byte.
    """
    try:
        with open(pfad, "rb") as f:
            roh = f.read(laenge + 1)
    except OSError as e:
        raise RuntimeError("--authorized-key %s: %s" % (pfad, e))
    if b"PRIVATE KEY" in roh:
        raise RuntimeError("--authorized-key %s ist ein PRIVATER Schluessel -- gemeint ist "
                           "die .pub-Datei. Nichts geschrieben." % pfad)
    if b"\0" in roh:
        raise RuntimeError("--authorized-key %s enthaelt Nullbytes -- keine Schluesseldatei" % pfad)
    text = roh.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    zeilen = [z.strip() for z in text.split(b"\n")]
    zeilen = [z for z in zeilen if z]
    treffer = [z for z in zeilen if not z.startswith(b"#") and
               any(z.startswith(a + b" ") or (b" " + a + b" ") in z for a in SCHLUESSEL_ARTEN)]
    if not treffer:
        raise RuntimeError("--authorized-key %s: keine Zeile sieht wie ein oeffentlicher "
                           "OpenSSH-Schluessel aus (%s ...)"
                           % (pfad, ", ".join(a.decode() for a in SCHLUESSEL_ARTEN[:3])))
    inhalt = b"\n".join(zeilen) + b"\n"
    if len(inhalt) > laenge:
        raise RuntimeError("--authorized-key %s: %d Byte, der Platzhalter fasst %d -- weniger "
                           "Schluessel oder kuerzere Kommentare" % (pfad, len(inhalt), laenge))
    return inhalt.ljust(laenge, b"\n"), len(treffer)


def nutzer_quellen(args, nutzer, log=K):
    """Die Nutzer-Platzhalter der Tabelle (heute: authorized_keys) fuellen.
    Rueckgabe: name -> Bytes in voller Platzhalterlaenge, oder {} wenn nichts
    zu tun ist (dann bleibt die Datei, wie gebaut: leer, nur Zeilenumbrueche)."""
    quellen = {}
    if "authorized_keys" in nutzer:
        off, laenge = nutzer["authorized_keys"]
        if args.authorized_key:
            daten, n = schluessel_lesen(args.authorized_key, laenge)
            quellen["authorized_keys"] = daten
            log.ok("authorized_keys: %d Schluessel aus %s, %d Byte, mit Zeilenumbruechen auf %d aufgefuellt"
                   % (n, args.authorized_key, len(daten.rstrip(b"\n")) + 1, laenge))
        else:
            log.warn("kein --authorized-key: /root/.ssh/authorized_keys bleibt leer -- auf das "
                     "Geraet kommt man dann nur ueber die serielle Konsole")
    elif args.authorized_key:
        raise RuntimeError("--authorized-key: dieses Abbild hat keinen Platzhalter fuer "
                           "authorized_keys (Tabelle ohne platzhalter_nutzer, aelter als "
                           "11.09.2026) -- der Schluessel kaeme nicht an. Abbruch.")
    fremd = [n for n in nutzer if n != "authorized_keys"]
    if fremd:
        raise RuntimeError("die Tabelle nennt Nutzer-Platzhalter, die dieses Skript nicht "
                           "kennt: %s -- neueres hy310-install noetig" % ", ".join(fremd))
    return quellen


def platzhalter_pruefen(abbild, tabelle, quellen):
    """Nach dem Fuellen zurueckvergleichen -- am PC, kostet Sekunden."""
    schlecht = []
    with open(abbild, "rb") as f:
        for name, (off, laenge) in tabelle.items():
            f.seek(off)
            if f.read(len(quellen[name])) != quellen[name]:
                schlecht.append(name)
    return schlecht


# ---------------------------------------------------------------- Abbild-Paket

def abbild_paket(pfad):
    """--abbild aufloesen. Erlaubt sind drei Dinge:

      * die Tabelle selbst      out/hy310-v0.1.tabelle.json
      * das Verzeichnis darum   out/
      * eine einzelne Datei     irgendwas.img   (dann braucht es --tabelle)

    Rueckgabe: (verzeichnis, tabelle|None). Die Tabelle stammt aus
    hy310-mkimage; Aufbau dort dokumentiert.
    """
    import json
    if os.path.isdir(pfad):
        treffer = sorted(x for x in os.listdir(pfad) if x.endswith(".tabelle.json"))
        if len(treffer) != 1:
            raise RuntimeError(
                "in %s liegen %d Dateien *.tabelle.json -- bitte die richtige "
                "direkt angeben" % (pfad, len(treffer)))
        pfad = os.path.join(pfad, treffer[0])
    if pfad.endswith(".json"):
        with open(pfad, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("format") != "hy310-abbild-tabelle":
            raise RuntimeError("%s ist keine Abbild-Tabelle von hy310-mkimage" % pfad)
        return os.path.dirname(os.path.abspath(pfad)), d
    return os.path.dirname(os.path.abspath(pfad)), None


def paket_pruefen(verz, d, log=K):
    """Groessen und Pruefsummen der Teile, bevor irgendetwas geschrieben wird."""
    for t in d["teile"]:
        p = os.path.join(verz, t["datei"])
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
    loch = d.get("loch")
    if loch and (loch["lba"], loch["lba"] + loch["sektoren"] - 1) != (SPERRE_ERSTER, SPERRE_LETZTER):
        raise RuntimeError("die Tabelle sperrt LBA %d..%d, dieses Skript %d..%d -- "
                           "nicht zusammengehoerig"
                           % (loch["lba"], loch["lba"] + loch["sektoren"] - 1,
                              SPERRE_ERSTER, SPERRE_LETZTER))
    if d.get("disk_sektoren") != SECTORS_EXPECTED:
        raise RuntimeError("die Tabelle ist fuer %s Sektoren gebaut, hier sind %d erwartet"
                           % (d.get("disk_sektoren"), SECTORS_EXPECTED))


# Platzhalter, die ein Geraet auch NICHT haben darf. Heute nur die WLAN-
# Firmware: nicht jedes H713-Geraet traegt den AIC8800-Chip, und h713-extract
# behandelt ein fehlendes vendor:/etc/firmware/aic8800d80/ ausdruecklich nicht
# als Fehler (12.09.2026). Fehlt der GANZE Satz, bleiben die Platzhalter
# genullt und h713-wifi meldet am Geraet "Firmware fehlt". Fehlt nur ein Teil,
# ist das ein Befund und kein Sonderfall -- dann Abbruch wie bei allem anderen.
OPTIONALE_GRUPPEN = ("lib/firmware/aic8800_fw/",)


def vendor_quellen(verz, tabelle, log=K):
    """Die geraeteeigenen Dateien einlesen, die h713-extract abgelegt hat.
    Die Namen in der Tabelle sind genau die Pfade unterhalb des --out von
    h713-extract, deshalb ist das ein Zusammensetzen und kein Zuordnen."""
    quellen, fehlend, gross = {}, [], []
    for name, (_off, laenge) in tabelle.items():
        p = os.path.join(verz, name.replace("/", os.sep))
        if not os.path.isfile(p):
            fehlend.append(name)
            continue
        with open(p, "rb") as f:
            b = f.read()
        if len(b) > laenge:
            gross.append("%s (%d > %d)" % (name, len(b), laenge))
        quellen[name] = b
    for praefix in OPTIONALE_GRUPPEN:
        gruppe = [n for n in tabelle if n.startswith(praefix)]
        weg = [n for n in gruppe if n in fehlend]
        if gruppe and len(weg) == len(gruppe):
            log.warn("%s: keine der %d Dateien im Abzug -- dieses Geraet hat den Chip "
                     "wohl nicht. Die Platzhalter bleiben genullt, WLAN bleibt aus."
                     % (praefix, len(gruppe)))
            for n in weg:
                quellen[n] = b""
                fehlend.remove(n)
    if fehlend:
        raise RuntimeError("in %s fehlen %d Datei(en), z. B. %s"
                           % (verz, len(fehlend), ", ".join(sorted(fehlend)[:3])))
    if gross:
        raise RuntimeError("passt nicht in den Platzhalter: %s" % ", ".join(gross))
    klein = [n for n, b in quellen.items() if len(b) < tabelle[n][1]]
    if klein:
        # Kein Abbruch: der Platzhalter wird mit Nullen aufgefuellt. Aber es
        # heisst, dass diese Firmware andere Groessen hat als die, gegen die
        # das Abbild gebaut wurde -- das gehoert gesagt.
        log.warn("%d Datei(en) sind kleiner als ihr Platzhalter (%s) -- der Rest "
                 "wird genullt. Andere Firmware als beim Bau des Abbilds?"
                 % (len(klein), ", ".join(sorted(klein)[:3])))
    return quellen


def extrahieren(abzug, ziel, extraktor=None, log=K):
    """h713-extract auf den Abzug loslassen (Plan 110 §3): der Nutzer liest die
    proprietaeren Teile aus seinem eigenen Geraet, nicht aus einem Download."""
    ex = _extraktor_laden(extraktor)
    log.info("h713-extract %s -> %s" % (os.path.basename(abzug), ziel))
    rc = ex.main([abzug, "--out", ziel, "-q"])
    if rc == 0:
        log.ok("Extraktion vollstaendig und gegen die Referenz geprueft")
    elif rc == 1:
        log.warn("h713-extract meldet Abweichungen (unbekannter Stand oder "
                 "fehlende Teile) -- die Ausgabe liegt trotzdem in %s" % ziel)
    else:
        raise RuntimeError("h713-extract ist mit Fehler %d ausgestiegen" % rc)
    return rc


# ---------------------------------------------------------------- Ablauf

def frage(text, vorgabe=None):
    if not sys.stdin.isatty():
        return vorgabe
    try:
        a = input(text).strip().lower()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nAbgebrochen.")
    return a or vorgabe


def bestaetigen(was):
    """Eine getippte Bestaetigung, kein bequemes [j/N] -- und an jeder
    Schreibstelle dieselbe Abbruchregel (Befund S46 B15, Plan 110 §9)."""
    K.info("")
    K.warn(was)
    K.info("")
    K.info("  Das hier ist eine Beta. Wenn waehrend des Schreibens etwas")
    K.info("  schiefgeht: NICHT den Strom ziehen und neu starten. Das Geraet")
    K.info("  in den FEL-Modus bringen (Reset halten, Strom einstecken) und")
    K.info("  von vorn anfangen -- die Boot-Kette ist von dort immer erreichbar.")
    K.info("")
    # frage() liefert die Antwort in Kleinbuchstaben zurueck -- der Vergleich
    # muss darauf passen, sonst schlaegt jede Bestaetigung fehl (10.09.).
    return frage("  Zum Fortfahren JA eintippen: ", "") == "ja"


def waehle_abzug(args):
    if args.abzug:
        return args.abzug
    K.info("")
    K.info("Der Abzug ist deine Sicherung. Zwei Groessen:")
    K.info("")
    K.info("  klein  49 MiB, rund 10 Sekunden.")
    K.info("         Alles, was es NUR auf diesem Geraet gibt: HDCP-Schluessel,")
    K.info("         die MAC-Adressen von WLAN und Bluetooth, die Seriennummer.")
    K.info("         Das bringt kein Firmware-Abbild der Welt zurueck.")
    K.info("")
    K.info("  voll   7,3 GB, rund 17 Minuten.")
    K.info("         Die ganze eMMC. Damit spielst du dein Geraet 1:1 zurueck,")
    K.info("         Android eingeschlossen, ohne irgendetwas herunterzuladen.")
    K.info("")
    a = frage("  Welchen Abzug? [klein/voll] ", "klein")
    return "voll" if a.startswith("v") else "klein"


def main(argv=None):
    p = argparse.ArgumentParser(
        description="HY310/H713-Beamer auf Linux umstellen (doku/110).",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--abbild", metavar="TABELLE|VERZ|DATEI",
                   help="das zu schreibende Abbild: die *.tabelle.json von "
                        "hy310-mkimage, das Verzeichnis darum, oder eine "
                        "einzelne .img-Datei")
    p.add_argument("--tabelle", help="Offsettabelle, wenn --abbild eine einzelne Datei ist")
    p.add_argument("--vendor", metavar="VERZ",
                   help="fertige Ausgabe von h713-extract; ohne das wird aus "
                        "dem Vollabzug extrahiert")
    p.add_argument("--authorized-key", metavar="DATEI",
                   help="oeffentlicher SSH-Schluessel (z. B. ~/.ssh/id_ed25519.pub) fuer "
                        "/root/.ssh/authorized_keys im Abbild; ohne ihn kein ssh-Zugang")
    p.add_argument("--arbeitskopie", metavar="DATEI",
                   help="wohin die gefuellte Kopie des Abbilds geht "
                        "(Vorgabe: <sicherung>/abbild-gefuellt.img, ~1,2 GB)")
    p.add_argument("--sicherung", default="hy310-sicherung",
                   help="Verzeichnis fuer den Abzug (Vorgabe: %(default)s)")
    p.add_argument("--abzug", choices=["klein", "voll"],
                   help="ohne Rueckfrage: welcher Abzug")
    p.add_argument("--uboot", help="U-Boot fuer die Laufwerksfreigabe (u-boot-sunxi-with-spl.bin)")
    p.add_argument("--sunxi-fel", dest="fel", help="Pfad zu sunxi-fel")
    p.add_argument("--device", help="Laufwerk von Hand angeben (sonst gesucht)")
    p.add_argument("--nur-abzug", action="store_true",
                   help="nur sichern, nichts schreiben")
    p.add_argument("--restore", metavar="ABZUG",
                   help="einen Vollabzug zurueckspielen statt zu installieren")
    p.add_argument("--restore-stock", metavar="UPDATE.IMG",
                   help="die Herstellerfirmware (IMAGEWTY-Container) einspielen")
    p.add_argument("--extraktor", help="Pfad zu h713-extract (sonst daneben gesucht)")
    p.add_argument("--env-neu", dest="env_neu", action="store_true",
                   help="bei einer Neuinstallation auf unserem Layout NICHTS aus der alten "
                        "U-Boot-Umgebung uebernehmen (Vorgabe: %s werden uebernommen)"
                        % ", ".join(ENV_UEBERNEHMEN))
    p.add_argument("--ohne-erkennung", dest="ohne_erkennung", action="store_true",
                   help="die Geraeteerkennung ueberspringen (Plan 110 §8). Nur fuer "
                        "Entwicklung -- sie ist der Schutz davor, auf einer fremden "
                        "Firmware zu raten.")
    p.add_argument("--dry-run", action="store_true", help="nichts schreiben")
    p.add_argument("--version", action="version", version="hy310-install " + VERSION)
    args = p.parse_args(argv)

    print("hy310-install %s   (%s)" % (VERSION, platform.system()))

    # --- 0. Haengt die eMMC schon als Laufwerk? Dann ist FEL erledigt.
    #        (Aus der Freigabe kommt man nur durch Stromabschalten heraus;
    #         wer das Skript zweimal startet, soll nicht neu anfangen muessen.)
    schon_da = finde_laufwerk()
    if args.device and not schon_da and os.path.exists(args.device):
        # Wer den Pfad ausdruecklich nennt, meint ihn auch -- etwa wenn die
        # Erkennung das Geraet nicht mag. Frueher fiel dieser Fall in den
        # FEL-Zweig und scheiterte dort, weil das Geraet laengst U-Boot fuhr.
        schon_da = [(args.device, 0, "--device")]
    if schon_da:
        if args.device:
            pfad = args.device
        elif len(schon_da) > 1:
            K.fehler("Mehrere Laufwerke passen: %s. Bitte --device angeben."
                     % ", ".join(t[0] for t in schon_da))
            return 3
        else:
            pfad = schon_da[0][0]
        K.schritt(1, "eMMC haengt bereits als Laufwerk")
        try:
            art = ist_unser_geraet(pfad)
        except PermissionError:
            K.fehler("Keine Leserechte auf %s. Das Skript braucht erhoehte "
                     "Rechte (unter Linux sudo, unter Windows als "
                     "Administrator)." % pfad)
            return 3
        if not art:
            K.fehler("%s hat die richtige Groesse, sieht aber nicht wie der "
                     "Beamer aus (weder unser noch das Stock-Layout)." % pfad)
            K.info("  Mit --device laesst es sich erzwingen -- aber sieh vorher nach,")
            K.info("  was das fuer ein Laufwerk ist.")
            return 3
        sekt = next((t[1] for t in schon_da if t[0] == pfad), 0)
        K.ok("%s, %s Sektoren, %s -- FEL und Freigabe uebersprungen"
             % (pfad, sekt or "?", art))
        return _arbeiten(args, pfad)

    # --- 1. FEL
    K.schritt(1, "Geraet im FEL-Modus suchen")
    fel = fel_werkzeug(args.fel)
    kennung = fel_da(fel)
    if not kennung:
        K.warn("Kein Geraet im FEL-Modus gefunden.")
        fel_anleitung()
        if frage("\n  Nochmal versuchen? [J/n] ", "j").startswith("n"):
            return 1
        kennung = fel_da(fel)
        if not kennung:
            K.fehler("Immer noch nichts. Steckt das A-auf-A-Kabel?")
            return 1
    K.ok(kennung.split("\n")[0])
    # An der SoC-ID pruefen, nicht am Namen: der Name in soc=00001860(<name>)
    # kommt aus der sunxi-fel-Tabelle und fehlt bei aelteren Staenden ("unknown").
    # 0x1860 ist der H713 (Issue #1: distro-sunxi-fel meldete "(unknown)").
    if "00001860" not in kennung:
        K.fehler("Das ist kein H713 (SoC-ID 0x1860 nicht gefunden). Abbruch.")
        return 1
    if "1860(H713)" not in kennung and "(sun50iw12" not in kennung:
        K.warn("sunxi-fel kennt diesen SoC nicht beim Namen -- nimm das "
               "sunxi-fel aus dem Release, sonst scheitert der naechste Schritt.")

    # --- 2. Laufwerksfreigabe
    K.schritt(2, "eMMC als USB-Laufwerk freigeben")
    if not args.uboot:
        K.fehler("--uboot fehlt (U-Boot mit Laufwerksfreigabe).")
        return 2
    K.info("laedt U-Boot fluechtig -- kein Byte auf die eMMC")
    subprocess.run([fel, "uboot", args.uboot], check=True, timeout=120)
    for _ in range(20):
        time.sleep(1)
        treffer = finde_laufwerk()
        if treffer:
            break
    else:
        K.fehler("Es ist kein Laufwerk erschienen.")
        return 3
    if args.device:
        pfad = args.device
    elif len(treffer) > 1:
        K.fehler("Mehrere passende Laufwerke: %s -- bitte --device angeben."
                 % ", ".join(t[0] for t in treffer))
        return 3
    else:
        pfad = treffer[0][0]
    K.ok("%s, %d Sektoren (7,28 GiB)" % (pfad, treffer[0][1]))
    return _arbeiten(args, pfad)


def _arbeiten(args, pfad):
    schreiben = not (args.dry_run or args.nur_abzug)
    platte = Platte(pfad, schreiben=schreiben)
    # Fuer die Umgebung zaehlt allein die GPT: hy310-* heisst unser Layout. Das
    # ist unabhaengig von --ohne-erkennung, weil es nichts raet -- es liest
    # Partitionsnamen, 1 KiB.
    args._unser_layout = (ist_unser_geraet(pfad) or "").startswith("unser Layout")
    args._alte_env = None
    try:
        # Vor dem ersten Schreibzugriff: womit haben wir es zu tun? (Plan 110 §8)
        # Kostet 1,2 MiB und Bruchteile einer Sekunde und verhindert, dass wir
        # auf einer unbekannten Firmware raten.
        if not args.ohne_erkennung:
            K.schritt("1b", "Geraet erkennen")
            erk = geraet_erkennen(platte, args.extraktor)
            if not geraet_melden(erk, schreibt=schreiben) and schreiben:
                return 10
        if platte.sektoren != SECTORS_EXPECTED:
            K.fehler("%s hat %d Sektoren, erwartet %d -- falsches Laufwerk?"
                     % (pfad, platte.sektoren, SECTORS_EXPECTED))
            return 4

        # --- Herstellerfirmware einspielen
        if args.restore_stock:
            # Plan 110 §2: vor jedem Schreibzugriff der kleine Abzug. Er kostet
            # Sekunden und rettet, was kein Image zurueckbringt (Befund S46 B2).
            if not args.dry_run:
                K.schritt(2, "Kleiner Abzug (Pflicht, auch vor dem Zuruecksetzen)")
                os.makedirs(args.sicherung, exist_ok=True)
                mf = abzug_klein(platte, args.sicherung, unser_layout=args._unser_layout)
                _manifest_schreiben(args.sicherung, mf, pfad)
            K.schritt(3, "Herstellerfirmware einspielen")
            if not os.path.isfile(args.restore_stock):
                K.fehler("%s nicht gefunden" % args.restore_stock)
                return 5
            K.info("%s (%.0f MiB)" % (args.restore_stock, mib(os.path.getsize(args.restore_stock))))
            K.info("Der Secure Storage (LBA %d..%d) bleibt dabei unberuehrt."
                   % (SPERRE_ERSTER, SPERRE_LETZTER))
            if args.dry_run:
                stock_zurueck(platte, args.restore_stock, args.extraktor, trocken=True)
                K.info("Trockenlauf -- nichts geschrieben.")
                return 0
            if not bestaetigen("Das ueberschreibt die eMMC mit Android."):
                return 1
            t0 = time.time()
            n, parts = stock_zurueck(platte, args.restore_stock, args.extraktor)
            K.ok("%.0f MiB in %s geschrieben" % (mib(n), dauer(time.time() - t0)))
            K.info("")
            K.info("Jetzt Strom abziehen und wieder einstecken.")
            return 0

        # --- Zurueckspielen statt installieren
        if args.restore:
            if not args.dry_run:
                K.schritt(2, "Kleiner Abzug (Pflicht, auch vor dem Zuruecksetzen)")
                os.makedirs(args.sicherung, exist_ok=True)
                mf = abzug_klein(platte, args.sicherung, unser_layout=args._unser_layout)
                _manifest_schreiben(args.sicherung, mf, pfad)
            K.schritt(3, "Vollabzug zurueckspielen")
            if not os.path.isfile(args.restore):
                K.fehler("%s nicht gefunden" % args.restore)
                return 5
            K.info("%s (%.1f MiB)" % (args.restore, mib(os.path.getsize(args.restore))))
            if not bestaetigen("Das ueberschreibt die eMMC mit deinem Abzug."):
                return 1
            t = abbild_schreiben(platte, args.restore)
            K.ok("zurueckgespielt in %s" % dauer(t))
            K.info("")
            K.info("Jetzt Strom abziehen und wieder einstecken.")
            return 0

        # --- 3. Abzug
        wahl = waehle_abzug(args)
        K.schritt(3, "Abzug ziehen (%s)" % wahl)
        os.makedirs(args.sicherung, exist_ok=True)
        manifest = abzug_klein(platte, args.sicherung, unser_layout=args._unser_layout)   # immer, auch bei "voll"
        if wahl == "voll":
            datei = os.path.join(args.sicherung, "emmc-voll.img")
            K.info("7,3 GB, das dauert. Zwischenstand:")
            h, t = abzug_voll(platte, datei)
            K.ok("%s  sha256 %s…  in %s" % (datei, h[:16], dauer(t)))
            # Ein Abzug, den niemand geprueft hat, ist kein Failsafe.
            K.info("Stichproben gegen das Geraet:")
            schlecht = pruefe_abzug(platte, datei)
            if schlecht:
                K.fehler("%d Stichprobe(n) weichen ab -- der Abzug taugt nicht. "
                         "Abbruch, bevor irgendetwas geschrieben wird." % schlecht)
                return 7
            K.ok("Abzug stimmt mit dem Geraet ueberein")
            manifest.append(("emmc-voll", 0, platte.sektoren, h, "vollstaendiger Klon"))
        _manifest_schreiben(args.sicherung, manifest, pfad)
        K.ok("Sicherung liegt in %s" % os.path.abspath(args.sicherung))

        if args.nur_abzug:
            K.info("\n--nur-abzug: es wird nichts geschrieben. Strom aus und an.")
            return 0

        # --- 4. Abbild vorbereiten (am PC!) und schreiben
        if not args.abbild:
            K.warn("--abbild fehlt -- es wurde nur gesichert.")
            K.info("  Ein Abbild baut hy310-mkimage (liegt daneben); --abbild nimmt")
            K.info("  dessen Tabelle oder das Verzeichnis, in dem sie liegt.")
            return 0

        verz_p, tab = abbild_paket(args.abbild)
        if tab is None and args.tabelle:
            # Einzeldatei plus eigene Tabelle: dieselbe Mechanik, ein Teil.
            verz_p, tab = abbild_paket(args.tabelle)
            if tab is None:
                K.fehler("%s ist keine Abbild-Tabelle" % args.tabelle)
                return 5
            tab = dict(tab)
            tab["teile"] = [t for t in tab["teile"]
                            if t["datei"] == os.path.basename(args.abbild)] or [{
                                "datei": os.path.basename(args.abbild), "lba": 0,
                                "bytes": os.path.getsize(args.abbild),
                                "sha256": None}]
            verz_p = os.path.dirname(os.path.abspath(args.abbild)) or "."
        if tab is not None:
            return _paket_schreiben(args, platte, pfad, verz_p, tab)

        # Einzeldatei ohne Tabelle: ein Stueck ab LBA 0, ohne Platzhalter.
        K.schritt(4, "Abbild schreiben")
        if args.dry_run:
            K.info("WUERDE: %s auf %s schreiben (%.1f MiB)"
                   % (args.abbild, pfad, mib(os.path.getsize(args.abbild))))
            return 0
        K.info("%s (%.1f MiB)" % (args.abbild, mib(os.path.getsize(args.abbild))))
        if not bestaetigen("Das ueberschreibt die eMMC."):
            return 1
        t = abbild_schreiben(platte, args.abbild)
        K.ok("geschrieben in %s" % dauer(t))
        fehler = pruefe_abbild(platte, args.abbild)
        if fehler:
            K.fehler("%d Stichprobe(n) weichen ab -- nicht neu starten, nachfragen." % fehler)
            return 6
        K.ok("Stichproben stimmen")
        K.info("")
        K.info("Fertig. Strom abziehen und wieder einstecken.")
        return 0
    finally:
        platte.close()


def env_uebernehmen(args, tab, arbeit, teil_datei, log=K):
    """Absichts-Schluessel der alten Umgebung in die neue schreiben -- in der
    Arbeitskopie von Teil B, bevor irgendetwas auf die eMMC geht.

    Nur wenn: unser Layout (sonst gibt es keine alte), das Abbild eine
    Umgebung mitbringt (bausteine.env, ab 12.09.2026; aeltere Abbilder haben
    dort Nullen, da wird nichts erfunden), die alte gueltig war, und der
    Nutzer nicht --env-neu gesagt hat.
    """
    if args.env_neu or not args._unser_layout:
        return 0
    baustein = (tab.get("bausteine") or {}).get("env")
    if not baustein:
        log.info("Umgebung: dieses Abbild bringt keine mit (aelter als 12.09.) -- nichts zu uebernehmen")
        return 0
    alt_pfad = os.path.join(args.sicherung, "uboot-env.bin")
    if not os.path.isfile(alt_pfad):
        return 0
    with open(alt_pfad, "rb") as f:
        alt = env_lesen(f.read())
    if not alt:
        return 0
    teil_lba = next((t["lba"] for t in tab["teile"] if t["datei"] == teil_datei), None)
    if teil_lba is None or baustein["lba"] < teil_lba:
        log.warn("Umgebung liegt nicht im Teil mit den Platzhaltern -- Uebernahme uebersprungen")
        return 0
    off = (baustein["lba"] - teil_lba) * SECT
    with open(arbeit, "r+b") as f:
        f.seek(off)
        neu = env_lesen(f.read(ENV_BYTES))
        if neu is None:
            log.fehler("Umgebung im Abbild bei Offset 0x%x hat keinen gueltigen CRC" % off)
            return 11
        genommen = []
        for k in ENV_UEBERNEHMEN:
            if k in alt and alt[k] != neu.get(k):
                genommen.append("%s=%s (Abbild: %s)" % (k, alt[k], neu.get(k, "-")))
                neu[k] = alt[k]
        if not genommen:
            log.ok("Umgebung: %s stimmen mit der Vorgabe des Abbilds ueberein -- nichts zu uebernehmen"
                   % ", ".join(ENV_UEBERNEHMEN))
            return 0
        f.seek(off)
        f.write(env_schreiben(neu))
        f.flush()
        os.fsync(f.fileno())
        f.seek(off)
        if env_lesen(f.read(ENV_BYTES)) != neu:
            log.fehler("Umgebung nach dem Schreiben nicht wie erwartet")
            return 11
    log.ok("Umgebung: aus der alten uebernommen: %s" % "; ".join(genommen))
    log.info("  Alles andere kommt vom U-Boot des Abbilds. Die alte liegt in %s." % alt_pfad)
    return 0


def _paket_schreiben(args, platte, pfad, verz, tab):
    """Der Installationsweg aus Plan 110 §1, Schritte 4 und 5.

    Reihenfolge mit Absicht (siehe platzhalter_fuellen): erst wird am PC eine
    Arbeitskopie des Teils mit den Platzhaltern gefuellt und zurueckgelesen,
    dann geht ALLES in einem Rutsch auf die eMMC. Ein Abbruch am PC kostet
    nichts; ein Abbruch mitten in einem zweiten Schreibdurchlauf haette ein
    halbes System hinterlassen.
    """
    K.schritt(4, "Abbild pruefen (%s, %s)" % (tab.get("abbild"), tab.get("layout")))
    paket_pruefen(verz, tab, K)
    K.info("Loch bei LBA %d..%d (%s) -- bleibt unberuehrt"
           % (tab["loch"]["lba"], tab["loch"]["lba"] + tab["loch"]["sektoren"] - 1,
              tab["loch"]["partition"]))

    tabelle = {k: tuple(v) for k, v in tab.get("platzhalter", {}).items()}
    nutzer = {k: tuple(v) for k, v in tab.get("platzhalter_nutzer", {}).items()}
    teil_datei = tab.get("platzhalter_datei")
    arbeit = None

    # Wer nur EINEN Teil schreibt -- etwa nur die Boot-Kette, um den Bootloader
    # zu erneuern, ohne das ganze System neu aufzuspielen -- braucht die
    # Platzhalter nicht: die stecken in einem Teil, der gar nicht drankommt.
    # Ohne diese Pruefung legte das Werkzeug eine 1,15-GB-Arbeitskopie an,
    # fuellte sie und warf sie weg.
    gewaehlt = {t["datei"] for t in tab["teile"]}
    if (tabelle or nutzer) and teil_datei not in gewaehlt:
        K.info("Platzhalter uebersprungen: %s wird bei diesem Lauf nicht geschrieben"
               % teil_datei)
        if args.authorized_key:
            K.warn("--authorized-key bleibt damit ohne Wirkung")
        tabelle, nutzer = {}, {}

    quellen = {}
    if tabelle:
        K.schritt(5, "Die geraeteeigenen Dateien einsetzen (%d Platzhalter)" % len(tabelle))
        vendor = args.vendor
        if not vendor:
            voll = os.path.join(args.sicherung, "emmc-voll.img")
            if os.path.isfile(voll):
                vendor = os.path.join(args.sicherung, "extrakt")
                os.makedirs(vendor, exist_ok=True)
                extrahieren(voll, vendor, args.extraktor)
            else:
                K.fehler("Es gibt weder --vendor noch einen Vollabzug in %s."
                         % args.sicherung)
                K.info("  Die 43 Dateien (Anzeige-Artefakte, Firmware, PQ, WLAN) stehen nur")
                K.info("  auf deinem eigenen Geraet. Ohne sie bleibt das Bild schwarz.")
                K.info("  Also: den VOLLEN Abzug ziehen (--abzug voll) oder ein")
                K.info("  Verzeichnis von h713-extract mit --vendor angeben.")
                return 8
        quellen = vendor_quellen(vendor, tabelle, K)
        K.ok("%d Dateien aus %s" % (len(quellen), vendor))

    # Der Schluessel des Nutzers: gleiche Mechanik, andere Quelle. Hier und
    # nicht in vendor_quellen(), weil er nicht aus dem Geraet kommt -- und weil
    # er auch ohne Vendor-Dateien gesetzt werden koennen muss.
    if nutzer:
        if not tabelle:
            K.schritt(5, "Den eigenen SSH-Schluessel einsetzen")
        eigene = nutzer_quellen(args, nutzer, K)
        # Nur die gefuellten werden geschrieben; ein leerer Platzhalter bleibt,
        # wie er gebaut wurde (Zeilenumbrueche), und ist so gueltig.
        for name in eigene:
            tabelle[name] = nutzer[name]
            quellen[name] = eigene[name]

    if tabelle:
        arbeit = args.arbeitskopie or os.path.join(args.sicherung, "abbild-gefuellt.img")
        quelle_teil = os.path.join(verz, teil_datei)
        if args.dry_run:
            K.info("WUERDE: %s nach %s kopieren und %d Platzhalter fuellen"
                   % (teil_datei, arbeit, len(tabelle)))
        else:
            K.info("Arbeitskopie: %s (%.0f MiB)" % (arbeit, mib(os.path.getsize(quelle_teil))))
            shutil.copyfile(quelle_teil, arbeit)
            platzhalter_fuellen(arbeit, tabelle, quellen, log=_Still)
            schlecht = platzhalter_pruefen(arbeit, tabelle, quellen)
            if schlecht:
                K.fehler("nach dem Fuellen weichen ab: %s" % ", ".join(schlecht))
                return 9
            K.ok("%d Platzhalter gefuellt und zurueckgelesen -- alle gleich" % len(tabelle))
            rc = env_uebernehmen(args, tab, arbeit, teil_datei, K)
            if rc:
                return rc

    K.schritt(6, "Auf die eMMC schreiben")
    for t in tab["teile"]:
        K.info("  %-34s ab LBA %-9d %11d Byte" % (t["datei"], t["lba"], t["bytes"]))
    if args.dry_run:
        K.info("Trockenlauf -- nichts geschrieben.")
        return 0
    if not bestaetigen("Das ueberschreibt die eMMC."):
        return 1
    t0 = time.time()
    for t in tab["teile"]:
        datei = arbeit if (arbeit and t["datei"] == teil_datei) else os.path.join(verz, t["datei"])
        abbild_schreiben(platte, datei, lba0=t["lba"])
        K.ok("%s geschrieben" % t["datei"])
    K.ok("alles geschrieben in %s" % dauer(time.time() - t0))

    K.schritt(7, "Zurueckvergleichen")
    fehler = 0
    for t in tab["teile"]:
        datei = arbeit if (arbeit and t["datei"] == teil_datei) else os.path.join(verz, t["datei"])
        fehler += pruefe_abbild(platte, datei, stichproben=4, lba0=t["lba"])
    if fehler:
        K.fehler("%d Stichprobe(n) weichen ab -- nicht neu starten, nachfragen." % fehler)
        return 6
    K.ok("Stichproben stimmen")
    # Und die Probe aufs Exempel: der gesperrte Bereich darf sich nicht
    # geaendert haben. Der kleine Abzug liegt seit Schritt 3 vor.
    ss = os.path.join(args.sicherung, "secure-storage.bin")
    if os.path.isfile(ss):
        with open(ss, "rb") as f:
            vorher = f.read()
        nachher = platte.lies(SPERRE_ERSTER, len(vorher) // SECT)
        if nachher == vorher:
            K.ok("Secure Storage unveraendert (byteweise gegen den Abzug verglichen)")
        else:
            K.fehler("DER SECURE STORAGE HAT SICH GEAENDERT -- bitte melden, "
                     "nichts weiter tun, %s aufheben." % ss)
            return 10
    K.info("")
    K.info("Fertig. Strom abziehen und wieder einstecken.")
    return 0


def _manifest_schreiben(verzeichnis, manifest, geraet):
    import json
    daten = {
        "erzeugt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "werkzeug": "hy310-install " + VERSION,
        "geraet": geraet,
        "sektoren": SECTORS_EXPECTED,
        "teile": [{"name": n, "lba": l, "sektoren": s, "sha256": h, "zweck": z}
                  for n, l, s, h, z in manifest],
    }
    with open(os.path.join(verzeichnis, "MANIFEST.json"), "w") as f:
        json.dump(daten, f, indent=2, ensure_ascii=False)
    with open(os.path.join(verzeichnis, "LIESMICH.txt"), "w") as f:
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
            % (daten["erzeugt"], VERSION,
               "".join("  %-18s %s\n" % (t["name"] + ".bin", t["zweck"])
                       for t in daten["teile"])))


# ---------------------------------------------------------------- Stock zurueck

def _extraktor_laden(pfad=None):
    """h713-extract als Modul laden -- dort stecken der IMAGEWTY-Leser und die
    Quelle-Klassen, die wir hier wiederverwenden statt sie nachzubauen."""
    import importlib.util
    if pfad is None:
        hier = os.path.dirname(os.path.abspath(__file__))
        for kandidat in (os.path.join(hier, "h713-extract"),
                         os.path.join(hier, "..", "r2-extract", "h713-extract")):
            if os.path.isfile(kandidat):
                pfad = kandidat
                break
    if not pfad or not os.path.isfile(pfad):
        raise SystemExit("h713-extract nicht gefunden -- es gehoert neben dieses Skript.")
    spec = importlib.util.spec_from_loader(
        "h713_extract", importlib.machinery.SourceFileLoader("h713_extract", pfad))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _PlatteQuelle:
    """Der Extraktor liest ueber seine Quelle-Schnittstelle; hier liegt sie auf
    dem Blockgeraet statt auf einer Datei. Nur lesen."""

    def __init__(self, platte, ex):
        self._p = platte
        self.size = platte.sektoren * SECT
        self.name = platte.pfad
        self._TeilQuelle = ex.TeilQuelle

    def read(self, off, n):
        if off < 0 or n < 0:
            raise ValueError("negativer Lesezugriff")
        erst = off // SECT
        vorn = off - erst * SECT
        sekt = (vorn + n + SECT - 1) // SECT
        return self._p.lies(erst, sekt)[vorn:vorn + n]

    def backing(self):
        return None

    def sub(self, off, size, name):
        return self._TeilQuelle(self, off, size, name)


def geraet_erkennen(platte, extraktor=None, log=K):
    """Womit haben wir es zu tun? (Plan 110 §8)

    Ein gezielter Pfad statt einer Suche: GPT -> super -> LP-Metadaten ->
    vendor -> build.prop. Zusammen rund 1,2 MiB, also Bruchteile einer
    Sekunde; die ganze eMMC zu lesen dauert 17 Minuten.

    Gerechnet wird nichts selbst -- GPT, LP-Metadaten, ext4-Leser und die
    Geraetetabelle stehen im Extraktor. Eine zweite Fassung davon waere genau
    die Doppelpflege, die dieses Projekt schon zweimal teuer bezahlt hat.

    Rueckgabe: dict mit 'layout', und bei Stock zusaetzlich 'fingerprint',
    'geraet', 'bekannt'. Wirft nie -- wer nicht erkennt, meldet es.
    """
    aus = {"layout": None, "fingerprint": None, "geraet": None, "bekannt": False}
    try:
        ex = _extraktor_laden(extraktor)
    except Exception as e:                      # noqa: BLE001 -- Erkennung darf nie toeten
        log.warn("Geraeteerkennung: Extraktor nicht ladbar (%s)" % e)
        return aus

    aus["layout"] = ist_unser_geraet(platte.pfad)
    # Nur ein Stock-Layout hat eine vendor-Partition mit build.prop. Der Text
    # kommt aus ist_unser_geraet() -- "Stock-Layout, N Partitionen" oder
    # "unser Layout (...)"; auf das Anfangswort pruefen, nicht auf den ganzen
    # Satz (die Zahl der Partitionen steht darin).
    if not (aus["layout"] or "").startswith("Stock-Layout"):
        return aus

    try:
        q = _PlatteQuelle(platte, ex)
        stumm = ex.Log(quiet=True)
        gpt = ex.Gpt(q, stumm)
        sup = gpt.partition(q, "super")
        if sup is None:
            log.warn("Geraeteerkennung: keine Partition 'super'")
            return aus
        lp = ex.LpSuper(sup, stumm)
        # In super liegen die Namen mit Slot-Endung ("vendor_a"), auf aelteren
        # Staenden ohne. Erst den aktiven Slot, dann den anderen, dann ohne.
        ven = None
        for name in ("vendor_a", "vendor_b", "vendor"):
            ven = lp.partition(name, stumm)
            if ven is not None:
                aus["lp_partition"] = name
                break
        if ven is None:
            log.warn("Geraeteerkennung: keine LP-Partition 'vendor' (gefunden: %s)"
                     % ", ".join(getattr(lp, "parts", {})) or "keine")
            return aus
        fs = ex.Ext4(ven, None, "vendor", stumm)
        if not fs.existiert("/build.prop"):
            log.warn("Geraeteerkennung: /build.prop fehlt in vendor")
            return aus
        text = fs.lies("/build.prop").decode("utf-8", "replace")
    except Exception as e:                      # noqa: BLE001
        log.warn("Geraeteerkennung abgebrochen: %s" % e)
        return aus

    for z in text.splitlines():
        if z.startswith("ro.vendor.build.fingerprint="):
            aus["fingerprint"] = z.split("=", 1)[1].strip()
            break
    if not aus["fingerprint"]:
        log.warn("Geraeteerkennung: kein ro.vendor.build.fingerprint in build.prop")
        return aus

    for gid, prof in getattr(ex, "GERAETE", {}).items():
        k = ex.kennung(prof) if hasattr(ex, "kennung") else prof
        if k.get("build_fingerprint") == aus["fingerprint"]:
            aus["geraet"], aus["bekannt"] = prof.get("name", gid), True
            break
    return aus


def _fingerprint_deuten(fp):
    """Android-Version und Baudatum aus dem Fingerabdruck holen.

    Aufbau (Stock HY310):
      Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/Projector07241019:user/release-keys
      0        1             2           ^^  3               4          ^^^^^^^^
                                  Android 11                      MMTTSSmm = 24.07., 10:19

    Das Baudatum steckt als MMTTSSmm in der letzten Zahl des Bau-Feldes -- so
    zaehlt Android seine Builds. Das Jahr steht nirgends; HY310 ist 2025
    (Plan 110 §8), also wird es nicht behauptet.
    """
    teile = fp.split("/")
    version = "?"
    if len(teile) > 2 and ":" in teile[2]:
        version = teile[2].rsplit(":", 1)[1] or "?"
    datum = "?"
    if len(teile) > 4:
        marke = teile[4].split(":")[0]
        ziffern = "".join(c for c in marke if c.isdigit())
        if len(ziffern) == 8:
            mm, tt, ss, mi = ziffern[:2], ziffern[2:4], ziffern[4:6], ziffern[6:]
            if 1 <= int(mm) <= 12 and 1 <= int(tt) <= 31:
                datum = "%s.%s., %s:%s Uhr (%s)" % (tt, mm, ss, mi, marke)
            else:
                datum = marke
        else:
            datum = marke
    return version, datum


def geraet_melden(erk, log=K, schreibt=True):
    """Die Erkennung im Klartext ausgeben. Rueckgabe: darf weitergeschrieben
    werden? (Plan 110 §8, Punkte 3 bis 5)

    schreibt=False (--nur-abzug/--dry-run): eine unbekannte Firmware ist dann
    kein Abbruchgrund, sondern eine Notiz -- gelesen wird ohnehin nichts
    veraendert (Issue #1: die Meldung klang nach Abbruch und lief dann weiter)."""
    if erk["layout"] and not erk["layout"].startswith("Stock-Layout"):
        log.ok("%s -- kein Android mehr, nur der Abzug ist sinnvoll" % erk["layout"])
        return True
    if not erk["layout"]:
        log.warn("Das Laufwerk sieht nach nichts Bekanntem aus.")
        return True
    if not erk["fingerprint"]:
        log.warn("Die Firmware liess sich nicht bestimmen.")
        return True
    version, datum = _fingerprint_deuten(erk["fingerprint"])
    log.info("  Kennung   %s" % erk["fingerprint"])
    if erk["bekannt"]:
        log.ok("%s erkannt -- Android %s, Stand %s" % (erk["geraet"], version, datum))
        return True
    if not schreibt:
        log.warn("Unbekannte Firmware: Android %s, Stand %s -- es wird nur "
                 "gelesen, nichts geschrieben." % (version, datum))
        log.info("  Bitte die Kennungszeile oben melden, dann kommt das Geraet")
        log.info("  in die Tabelle (github.com/well0nez/allwinner-h713-linux).")
        return True
    log.fehler("Unbekannte Firmware: Android %s, Stand %s -- kein Schreiben." % (version, datum))
    log.info("  Die Fundstellen einer fremden Version zu raten, kostet im")
    log.info("  schlimmsten Fall den Secure Storage -- deshalb kein Weiter.")
    log.info("  Bitte die Kennungszeile oben melden, dann kommt sie in die Tabelle.")
    return False


def stock_plan(ex, image_q):
    """Aus sys_partition.fex im Image lesen, was wohin gehoert.

    Rueckgabe: (partitionen, roh). partitionen sind (name, start_lba, sektoren,
    quelldatei|None) in der Reihenfolge der Datei; roh sind die Stellen
    ausserhalb jeder Partition (boot0 und das sunxi-package, je zweimal).
    """
    import re
    img = ex.Imagewty(image_q, ex.Log() if hasattr(ex, "Log") else None)
    sysp = img.datei("sys_partition.fex")
    if sysp is None:
        raise RuntimeError("sys_partition.fex fehlt im Image -- kein Allwinner-Vollimage?")
    text = sysp.read(0, sysp.size if hasattr(sysp, "size") else 1 << 20).decode("latin1")

    partitionen = []
    lba = 73728                       # erste Partition, wie im Stock gemessen
    for block in re.findall(r"\[partition\](.*?)(?=\[partition\]|\[partition_end\]|\Z)",
                            text, re.S):
        # sys_partition.fex hat CRLF-Zeilenenden: ohne .strip() zieht der
        # Ausdruck den Wagenruecklauf in jeden ungequoteten Wert, und die
        # GPT-Partitionsnamen tragen dann ein unsichtbares U+000D. Android
        # findet seine Partitionen dann nicht mehr (Befund S46).
        d = {k: v.strip()
             for k, v in re.findall(r"^\s*(\w+)\s*=\s*\"?([^\"\r\n]+)\"?\s*$",
                                    block, re.M)}
        if "name" not in d:
            continue
        sekt = int(d.get("size", "0"))
        partitionen.append((d["name"], lba, sekt, d.get("downloadfile")))
        lba += sekt

    roh = [("boot0_sdcard.fex", 16), ("boot0_sdcard.fex", 256),
           ("boot_package.fex", 24576), ("boot_package.fex", 32800)]
    return img, partitionen, roh


SPARSE_MAGIC = 0xed26ff3a
_CHUNK_RAW, _CHUNK_FILL, _CHUNK_DONT_CARE, _CHUNK_CRC32 = 0xCAC1, 0xCAC2, 0xCAC3, 0xCAC4


def ist_sparse(kopf):
    """Android-Sparse-Abbild? Die ersten vier Bytes verraten es."""
    return len(kopf) >= 28 and struct.unpack_from("<I", kopf, 0)[0] == SPARSE_MAGIC


def sparse_schreiben(platte, d, plba, trocken=False):
    """Ein Android-Sparse-Abbild entpacken und an plba schreiben.

    super.fex ist so gepackt: 1537 MiB Datei, 2048 MiB Inhalt. Wer den
    Container roh auf die Partition schreibt, hinterlaesst dort Datenmuell --
    Android findet dann system, vendor und product nicht und startet in den
    Bootloader zurueck (am 10.09. genau so passiert, ohne jede Meldung).

    Rueckgabe: die Zahl der geschriebenen Bytes.
    """
    (_, maj, _mn, fhsz, chsz, blk, nblk, nchunk, _crc) = struct.unpack(
        "<IHHHHIIII", d.read(0, 28))
    if maj != 1:
        raise RuntimeError("Sparse-Version %d wird nicht unterstuetzt" % maj)
    if blk % SECT:
        raise RuntimeError("Sparse-Blockgroesse %d ist kein Vielfaches von %d" % (blk, SECT))
    happen = 1 << 20                      # in 1-MiB-Schritten schreiben
    pos, block, geschrieben = fhsz, 0, 0

    def schreib_am(bl, daten):
        if not trocken:
            platte.schreib(plba + bl * (blk // SECT), daten)

    for _ in range(nchunk):
        typ, _res, cblk, csz = struct.unpack("<HHII", d.read(pos, chsz))
        quelle, laenge = pos + chsz, csz - chsz
        if typ == _CHUNK_RAW:
            off = 0
            while off < laenge:
                n = min(happen, laenge - off)
                schreib_am(block + off // blk, d.read(quelle + off, n))
                off += n
            geschrieben += laenge
        elif typ == _CHUNK_FILL:
            muster = d.read(quelle, 4)
            gesamt = cblk * blk
            voll = muster * (happen // 4)
            off = 0
            while off < gesamt:
                n = min(happen, gesamt - off)
                schreib_am(block + off // blk, voll[:n])
                off += n
            geschrieben += gesamt
        elif typ == _CHUNK_DONT_CARE:
            # "egal" heisst auf einem frisch geloeschten Geraet: Nullen. Bei uns
            # stuende dort sonst das Vorgaengersystem.
            gesamt = cblk * blk
            null = b"\0" * happen
            off = 0
            while off < gesamt:
                n = min(happen, gesamt - off)
                schreib_am(block + off // blk, null[:n])
                off += n
            geschrieben += gesamt
        elif typ == _CHUNK_CRC32:
            pass
        else:
            raise RuntimeError("unbekannter Sparse-Stuecktyp 0x%04x" % typ)
        block += cblk
        pos += csz
    if block != nblk:
        raise RuntimeError("Sparse-Abbild unvollstaendig: %d von %d Bloecken"
                           % (block, nblk))
    return geschrieben


def stock_zurueck(platte, image_datei, extraktor=None, log=K, trocken=False):
    """Die Herstellerfirmware aus einem IMAGEWTY-Container einspielen.

    Der Secure Storage bei LBA 12288 wird dabei nicht berührt: die rohen Ziele
    liegen bei 16, 256, 24576 und 32800, die erste Partition beginnt bei 73728.
    Die Sperre in Platte.schreib() wacht trotzdem darüber.
    """
    ex = _extraktor_laden(extraktor)
    q = ex.DateiQuelle(__import__("pathlib").Path(image_datei))
    if not ex.Imagewty.ist_imagewty(q):
        raise RuntimeError("%s ist kein IMAGEWTY-Container" % image_datei)
    img, partitionen, roh = stock_plan(ex, q)

    log.info("%d Partitionen laut sys_partition.fex" % len(partitionen))
    geschrieben = 0
    fehlend = []

    # 0. Partitionstabelle -- ohne sie findet Android seine Partitionen nicht.
    gpt = stock_gpt_bauen(partitionen, platte.sektoren)
    if not trocken:
        for lba in sorted(gpt):
            platte.schreib(lba, gpt[lba])
    log.ok("%-22s -> GPT (Schutz-MBR, Kopf, Tabelle, Sicherungskopien)" % "sys_partition.fex")

    # 1. Rohbereiche vor der ersten Partition
    for name, ziel_lba in roh:
        d = img.datei(name)
        if d is None:
            fehlend.append(name)
            continue
        daten = d.read(0, d.size)
        if not trocken:
            platte.schreib(ziel_lba, daten)
        geschrieben += len(daten)
        log.ok("%-22s -> LBA %-6d %7.2f MiB" % (name, ziel_lba, mib(len(daten))))

    # 2. Partitionen
    for pname, plba, psekt, quelle in partitionen:
        if not quelle:
            continue                    # B-Slots und Laufzeitdaten: bleiben leer
        d = img.datei(quelle)
        if d is None:
            fehlend.append(quelle)
            continue
        if ist_sparse(d.read(0, 28)):
            n = sparse_schreiben(platte, d, plba, trocken)
            if psekt and n > psekt * SECT:
                raise RuntimeError("%s entpackt %.1f MiB, %s fasst nur %.1f MiB"
                                   % (quelle, mib(n), pname, mib(psekt * SECT)))
            geschrieben += n
            log.ok("%-22s -> %-16s LBA %-8d %7.2f MiB entpackt (Sparse, Datei %.0f MiB)"
                   % (quelle, pname, plba, mib(n), mib(d.size)))
            continue
        daten = d.read(0, d.size)
        if psekt and len(daten) > psekt * SECT:
            raise RuntimeError("%s (%.1f MiB) passt nicht in %s (%.1f MiB)"
                               % (quelle, mib(len(daten)), pname, mib(psekt * SECT)))
        if not trocken:
            platte.schreib(plba, daten)
        geschrieben += len(daten)
        log.ok("%-22s -> %-16s LBA %-8d %7.2f MiB"
               % (quelle, pname, plba, mib(len(daten))))

    # 3. Was keine Quelle hat, muss genullt werden (Befund S46 B8).
    #
    #    Das Werkzeug des Herstellers loescht die eMMC, bevor es schreibt. Wir
    #    schreiben nur, was im Image steht -- alles andere behaelt den Inhalt des
    #    vorigen Systems. Android findet dann in "metadata" kein ext4, bricht ab
    #    und startet in den Bootloader zurueck. Am 10.09. genau so passiert:
    #    "EXT4-fs (mmcblk0p19): VFS: Can't find ext4 filesystem", p19 = metadata.
    #
    #    Ausgenommen bleiben die Bereiche, die es nur auf diesem einen Geraet
    #    gibt und die kein Image zurueckbringt. Der Secure Storage ist ohnehin
    #    durch die Sperre in Platte.schreib() geschuetzt.
    #    Wer gleich ein Dateisystem bekommt (Schritt 4), wird nicht erst genullt.
    DATEISYSTEME = {"metadata": "metadata-leer-16m.ext4.gz"}
    NICHT_NULLEN = {"private", "reserve0_a", "reserve0_b"}
    KOPF_SEKT = 131072                  # 64 MiB toeten ein ext4 samt Reserve-Superbloecken
    null = b"\0" * (1 << 20)
    for pname, plba, psekt, quelle in partitionen:
        if quelle:
            continue
        if pname.lower() in NICHT_NULLEN:
            log.info("  %-16s bleibt unangetastet -- gibt es nur auf diesem Geraet"
                     % pname)
            continue
        if pname.lower() in DATEISYSTEME:
            continue                    # bekommt gleich ein Dateisystem
        rest = psekt if psekt else platte.sektoren - 33 - plba
        if rest <= 0:
            continue
        sekt = min(rest, KOPF_SEKT)
        if not trocken:
            getan = 0
            while getan < sekt:
                n = min(len(null) // SECT, sekt - getan)
                platte.schreib(plba + getan, null[:n * SECT])
                getan += n
        geschrieben += sekt * SECT
        log.ok("%-22s -> %-16s LBA %-8d %7.2f MiB genullt%s"
               % ("(kein Abbild)", pname, plba, mib(sekt * SECT),
                  "" if sekt == rest else " (Kopf)"))

    # 4. Dateisysteme anlegen, die das Image nicht mitbringt.
    #
    #    Die fstab aus dem vendor_boot-Ramdisk (first_stage_ramdisk/fstab.sun50iw12p1)
    #    sagt fuer metadata:
    #
    #      /dev/block/by-name/metadata  /metadata  ext4  errors=panic
    #                                   wait,first_stage_mount,formattable,check
    #
    #    "formattable" hilft hier nicht: der Eintrag ist zugleich
    #    "first_stage_mount", und die erste Stufe von init hat kein mke2fs --
    #    das liegt erst in /system. Sie kann also nicht formatieren und startet
    #    stattdessen in den Bootloader zurueck:
    #
    #      EXT4-fs (mmcblk0p19): VFS: Can't find ext4 filesystem
    #      reboot: Restarting system with command 'bootloader'
    #
    #    Auf einem Werksgeraet legt das PC-Werkzeug des Herstellers dieses
    #    Dateisystem an. Wir liefern es als leeres, gepacktes Abbild mit (17 KB
    #    fuer 16 MiB). UDISK braucht das nicht: seine Zeile ist "latemount" ohne
    #    "first_stage_mount", die zweite Stufe formatiert sie selbst.
    hier = os.path.dirname(os.path.abspath(__file__))
    for pname, plba, psekt, quelle in partitionen:
        blob = DATEISYSTEME.get(pname.lower())
        if not blob:
            continue
        pfad_blob = os.path.join(hier, blob)
        if not os.path.isfile(pfad_blob):
            log.warn("%s fehlt -- %s bleibt ohne Dateisystem, Android startet "
                     "dann nicht durch" % (blob, pname))
            continue
        with gzip.open(pfad_blob, "rb") as fh:
            daten = fh.read()
        if psekt and len(daten) > psekt * SECT:
            raise RuntimeError("%s (%.1f MiB) passt nicht in %s"
                               % (blob, mib(len(daten)), pname))
        if not trocken:
            platte.schreib(plba, daten)
        geschrieben += len(daten)
        log.ok("%-22s -> %-16s LBA %-8d %7.2f MiB leeres ext4"
               % (blob, pname, plba, mib(len(daten))))

    if fehlend:
        log.warn("nicht im Image und daher ausgelassen: %s" % ", ".join(sorted(set(fehlend))))
    if not trocken:
        platte.sync()
    return geschrieben, partitionen


def stock_gpt_bauen(partitionen, disk_sektoren=SECTORS_EXPECTED,
                    diskguid="ab6f3888-569a-4926-9668-80941dcb40bc",
                    guid_basis="a0085546-4166-744a-a353-fca9272b8e45"):
    """Die Stock-Partitionstabelle aus sys_partition.fex nachbauen.

    Ohne sie findet Android seine Partitionen nicht -- das Herstellerwerkzeug
    schreibt sie mit, also müssen wir das auch. Die Werte sind am Gerät
    abgelesen (Dump vor dem Umbau): 26 Einträge à 128 Byte ab LBA 2,
    FirstUsable 73728, Typ-GUID durchgehend die Allwinner-übliche, und die
    Unique-GUIDs sind schlicht durchnummeriert -- p1 endet auf 8e45, p2 auf
    8e46 und so fort.
    """
    import struct
    import uuid
    import zlib

    TYP = uuid.UUID("ebd0a0a2-b9e5-4433-87c0-68b6b72699c7").bytes_le
    basis = uuid.UUID(guid_basis)
    basis_zahl = int.from_bytes(basis.bytes[-6:], "big")
    nent, entsz = 26, 128
    first_usable = partitionen[0][1] if partitionen else 73728
    last_usable = disk_sektoren - 34

    arr = bytearray()
    for i in range(nent):
        if i < len(partitionen):
            name, lba, sekt, _quelle = partitionen[i]
            ende = (last_usable if not sekt else lba + sekt - 1)
            u = uuid.UUID(bytes=basis.bytes[:10] +
                          (basis_zahl + i).to_bytes(6, "big"))
            # Attribute, am Stock-Dump nachgemessen: Bit 63 auf jeder
            # Partition, und "frp" traegt zusaetzlich Bit 47.
            attr = (1 << 63) | ((1 << 47) if name == "frp" else 0)
            e = (TYP + u.bytes_le + struct.pack("<QQQ", lba, ende, attr) +
                 name.encode("utf-16-le").ljust(72, b"\0")[:72])
        else:
            e = b"\0" * entsz
        arr += e[:entsz]
    entcrc = zlib.crc32(bytes(arr)) & 0xFFFFFFFF

    def kopf(mylba, altlba, entlba):
        h = bytearray(92)
        h[0:8] = b"EFI PART"
        # Das Feld bei +20 ist laut UEFI reserviert und muss 0 sein; der
        # Hersteller schreibt dort 1. Nachgebaut, damit die Tabelle byteweise
        # der Stock-Tabelle entspricht.
        struct.pack_into("<III", h, 8, 0x10000, 92, 0)
        struct.pack_into("<I", h, 20, 1)
        struct.pack_into("<QQQQ", h, 24, mylba, altlba, first_usable, last_usable)
        h[56:72] = uuid.UUID(diskguid).bytes_le
        struct.pack_into("<QIII", h, 72, entlba, nent, entsz, entcrc)
        struct.pack_into("<I", h, 16, zlib.crc32(bytes(h)) & 0xFFFFFFFF)
        return bytes(h).ljust(SECT, b"\0")

    arr_sekt = (nent * entsz + SECT - 1) // SECT
    back_arr = disk_sektoren - 1 - arr_sekt
    # Schutz-MBR: ein Eintrag vom Typ 0xEE über die ganze Platte
    mbr = bytearray(SECT)
    mbr[510:512] = b"\x55\xaa"
    # Der Hersteller traegt als Groesse 0xFFFFFFFF ein statt der echten
    # Sektorzahl -- ueblich bei Schutz-MBRs, hier nachgebaut, damit der
    # Sektor byteweise dem Stock entspricht.
    mbr[446:462] = (b"\x00\x00\x02\x00\xee\xff\xff\xff" +
                    struct.pack("<II", 1, 0xFFFFFFFF))
    return {
        0: bytes(mbr),
        1: kopf(1, disk_sektoren - 1, 2),
        2: bytes(arr).ljust(arr_sekt * SECT, b"\0"),
        back_arr: bytes(arr).ljust(arr_sekt * SECT, b"\0"),
        disk_sektoren - 1: kopf(disk_sektoren - 1, 1, back_arr),
    }


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        sys.exit(130)
