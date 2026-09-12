#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hy310-mkimage -- das einspielbare Abbild fuer den HY310/H713-Beamer bauen.

Erzeugt aus den vorhandenen Bausteinen (SPL, U-Boot proper, Kernel-FIT, den
beiden ext4-Dateisystemen) ein Abbild nach Layout v3 (doku/109 §2), dazu die
Offsettabelle, ein Manifest, Pruefsummen und eine Liesmich-Datei.

DAS ABBILD HAT EIN LOCH.
Bei LBA 12288..14335 liegt der Secure Storage: HDCP-Schluessel, die WLAN- und
Bluetooth-MAC-Adressen und die Seriennummer des Geraets. Geraetespezifisch, in
keinem Firmware-Abbild, nicht wiederherstellbar (doku/109 §2.3). Deshalb ist
das Abbild NICHT eine durchgehende Datei, sondern drei Stuecke, und der
gesperrte Bereich kommt in keinem davon vor. Ein `dd` von Hand kann ihn damit
gar nicht ueberschreiben -- auch nicht, wenn der Nutzer die Sperre des
Installers nicht hat. Begruendung ausfuehrlich in doku/nachtlog/S47.

DIE PROPRIETAEREN DATEIEN SIND PLATZHALTER.
43 Dateien (19 Anzeige-Artefakte, 3 Firmware-Dateien, 8 PQ-Dateien, 13 WLAN-
Firmware-Dateien) duerfen nicht mitverteilt werden. Im Abbild stehen an ihrer Stelle Platzhalter genau
richtiger Groesse; `hy310-install` fuellt sie aus dem, was `h713-extract` aus
dem Geraet des Nutzers geholt hat. Wo sie liegen, steht in der Offsettabelle.

DER SSH-SCHLUESSEL DES NUTZERS IST AUCH EIN PLATZHALTER.
/root/.ssh/authorized_keys liegt im Abbild als Datei fester Groesse (4096 B),
gefuellt mit Zeilenumbruechen -- fuer sshd eine leere Datei, also gueltig, auch
wenn niemand sie fuellt. `hy310-install --authorized-key DATEI` schreibt den
oeffentlichen Schluessel hinein, aufgefuellt mit Zeilenumbruechen (Nullbytes
machten die Datei kaputt). Kein Schluessel im verteilten Abbild (doku/107 §3),
kein ext4-Schreiber noetig. Die Offsets kommen aus dem ext4, nicht aus dem
Fuellmuster, deshalb darf dieser Platzhalter anders aussehen als die anderen.
Besitz und Rechte (root:root, /root/.ssh 0700, Datei 0600) stellt der Baum
sicher -- und Schritt 5 prueft sie im fertigen ext4, weil sshd sonst den
Schluessel stillschweigend ignoriert.

Aufrufe:

  hy310-mkimage.py --out out/hy310-v0.1.img
        Abbild (drei Teile) + Tabelle + Manifest + LIESMICH erzeugen.

  hy310-mkimage.py --pruefen out/hy310-v0.1.tabelle.json
        Ein fertiges Abbild gegen seine Tabelle validieren: Groessen,
        Pruefsummen, GPT, Lage der Platzhalter, Loch frei.

  hy310-mkimage.py --baum-boot VERZ
  hy310-mkimage.py --baum-rootfs VERZ
        Nur die Dateibaeume mit den Platzhaltern schreiben. Aus ihnen bauen
        wir (im Container, NICHT beim Nutzer) mit mke2fs die beiden ext4 --
        siehe mkimage-eingaben.sh.

Laeuft unter Linux und Windows: Python 3.9+, reine Standardbibliothek, keine
externen Programme. Der einzige Programmteil, der mehr braucht, ist das Suchen
der Platzhalter-Offsets im fertigen ext4 -- dafuer wird der ext4-Leser aus
h713-extract geladen (auch reines Python, S45). Das geschieht beim Bau, nicht
beim Nutzer; --pruefen kommt ohne ihn aus.
"""

import argparse
import binascii
import hashlib
import json
import os
import re
import struct
import zlib
import sys
import time
import uuid

VERSION = "0.1"

# ---------------------------------------------------------------- Layout v3
# Alle Zahlen aus doku/109 §2.1/§2.2, die GUIDs am Geraet abgelesen
# (10.09.2026, /dev/sda nach dem Lauf aus doku/109 §12) -- damit das Abbild
# byteweise die Tabelle traegt, mit der das Geraet nachweislich bootet.

SECT = 512
DISK_SEKTOREN = 15269888              # 7,28 GiB -- die eMMC des HY310
FIRST_USABLE = 16                     # doku/109 §2.2: auch die Rohbereiche
LAST_USABLE = DISK_SEKTOREN - 34
NENT, ENTSZ = 26, 128                 # mehr Eintraege reichten in die SPL
ARR_SEKT = (NENT * ENTSZ + SECT - 1) // SECT          # 7
TYP_GUID = "0fc63daf-8483-4772-8e79-3d69d8477de4"     # Linux filesystem data
DISK_GUID = "ab6f3888-569a-4926-9668-80941dcb40bc"

# name, start-lba, sektoren, unique-guid
PARTITIONEN = [
    ("hy310-spl",    16,      64,       "cf5e1195-48e8-41bf-9394-1afdeff2bf01"),
    ("hy310-uboot",  2048,    10240,    "3c05da4e-39e8-4472-bd09-17f0433da668"),
    ("hy310-keys",   12288,   2048,     "404b1401-5772-4781-88ab-1b56c4682a97"),
    ("hy310-env",    14336,   2048,     "0a175557-ceb7-4ce5-b247-45e28a588dfd"),
    ("hy310-boot",   16384,   262144,   "f6d66c6c-2079-4e06-b550-4f37e6c5ab84"),
    ("hy310-rootfs", 278528,  14991327, "45f95906-692a-4dcf-94e5-10bf1672909d"),
]

# Der gesperrte Bereich. Identisch mit SPERRE_ERSTER/SPERRE_LETZTER in
# hy310-install.py -- beide Werte gehoeren zusammen und werden hier geprueft.
SPERRE_ERSTER = 12288
SPERRE_LETZTER = 14335

LBA_SPL = 16
LBA_UBOOT = 2048
LBA_ENV = 14336
ENV_BYTES = 0x10000     # CONFIG_ENV_SIZE, eine Kopie (109 §7)
LBA_BOOT = 16384
LBA_ROOTFS = 278528

# Die drei Stuecke des Abbilds.
TEIL_A_LBA, TEIL_A_SEKT = 0, SPERRE_ERSTER            # 0..12287, 6 MiB
TEIL_B_LBA = SPERRE_LETZTER + 1                       # 14336 = 7 MiB
TEIL_C_LBA = DISK_SEKTOREN - 33                       # 15269855, 33 Sektoren
TEIL_C_SEKT = 33

# ---------------------------------------------------------------- Platzhalter
# name (so heisst die Datei auch in der Ausgabe von h713-extract)
#   -> (groesse in Byte, zielpartition, pfad im dateisystem)
# Die Groessen sind am HY310 gemessen (r2-extract/out-hy310, 10.09.2026) und
# hier festgeschrieben: das Abbild wird einmal gebaut und dann verteilt.

PLATZHALTER = [
    # 19 Anzeige-Artefakte -> hy310-boot:/mips/
    ("boot/mips/database.TSE",           282464,  "hy310-boot",   "/mips/database.TSE"),
    ("boot/mips/display.bin",            1256216, "hy310-boot",   "/mips/display.bin"),
    ("boot/mips/display_cfg.xml",        4766,    "hy310-boot",   "/mips/display_cfg.xml"),
    ("boot/mips/LogoRegData.bin",        15652,   "hy310-boot",   "/mips/LogoRegData.bin"),
    ("boot/mips/pq_custom.TSE",          15016,   "hy310-boot",   "/mips/pq_custom.TSE"),
    ("boot/mips/ProjectID_0x0001.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0001.TSE"),
    ("boot/mips/ProjectID_0x0012.TSE",   48952,   "hy310-boot",   "/mips/ProjectID_0x0012.TSE"),
    ("boot/mips/ProjectID_0x0013.TSE",   47880,   "hy310-boot",   "/mips/ProjectID_0x0013.TSE"),
    ("boot/mips/ProjectID_0x0014.TSE",   47880,   "hy310-boot",   "/mips/ProjectID_0x0014.TSE"),
    ("boot/mips/ProjectID_0x0015.TSE",   47880,   "hy310-boot",   "/mips/ProjectID_0x0015.TSE"),
    ("boot/mips/ProjectID_0x0016.TSE",   47880,   "hy310-boot",   "/mips/ProjectID_0x0016.TSE"),
    ("boot/mips/ProjectID_0x0020.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0020.TSE"),
    ("boot/mips/ProjectID_0x0030.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0030.TSE"),
    ("boot/mips/ProjectID_0x0031.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0031.TSE"),
    ("boot/mips/ProjectID_0x0032.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0032.TSE"),
    ("boot/mips/ProjectID_0x0033.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0033.TSE"),
    ("boot/mips/ProjectID_0x0034.TSE",   17328,   "hy310-boot",   "/mips/ProjectID_0x0034.TSE"),
    ("boot/mips/ProjectID_0x0035.TSE",   19992,   "hy310-boot",   "/mips/ProjectID_0x0035.TSE"),
    ("boot/mips/projecttable.TSE",       1384,    "hy310-boot",   "/mips/projecttable.TSE"),
    # 3 Firmware-Dateien -> hy310-rootfs:/lib/firmware/
    ("lib/firmware/h713-arisc.bin",      176132,  "hy310-rootfs", "/lib/firmware/h713-arisc.bin"),
    ("lib/firmware/h713/msp-patch.bin",  2896,    "hy310-rootfs", "/lib/firmware/h713/msp-patch.bin"),
    ("lib/firmware/hy310-edid.bin",      512,     "hy310-rootfs", "/lib/firmware/hy310-edid.bin"),
    # 8 PQ-Dateien -> hy310-rootfs:/etc/h713/tvconfig/
    ("pq/portmap.cfg",                   312,     "hy310-rootfs", "/etc/h713/tvconfig/portmap.cfg"),
    ("pq/pq_colortemp.ini",              865,     "hy310-rootfs", "/etc/h713/tvconfig/pq_colortemp.ini"),
    ("pq/pq_factory_extern.ini",         592528,  "hy310-rootfs", "/etc/h713/tvconfig/pq_factory_extern.ini"),
    ("pq/pq_overscan_config.ini",        10877,   "hy310-rootfs", "/etc/h713/tvconfig/pq_overscan_config.ini"),
    ("pq/pq_picturemode.ini",            10216,   "hy310-rootfs", "/etc/h713/tvconfig/pq_picturemode.ini"),
    ("pq/pqcontrol_config_setting.xml",  1055,    "hy310-rootfs", "/etc/h713/tvconfig/pqcontrol_config_setting.xml"),
    ("pq/pqcontrol_custom_setting.xml",  1326,    "hy310-rootfs", "/etc/h713/tvconfig/pqcontrol_custom_setting.xml"),
    ("pq/tvpq.db",                       36864,   "hy310-rootfs", "/etc/h713/tvconfig/tvpq.db"),
    # 13 WLAN-Firmware-Dateien -> hy310-rootfs:/lib/firmware/aic8800_fw/SDIO/aic8800D80/
    # (12.09.2026, Groessen aus h713-extract, Profil hy310: byteidentisch mit
    # dem Satz, der am selben Tag wlan0 hochgebracht hat.) Der Zielpfad ist
    # CONFIG_AIC_FW_PATH des Treibers -- weicht er ab, laedt fdrv stumm nichts.
    # OPTIONAL fuer den Installer: fehlt der ganze Satz im Abzug, hat das
    # Geraet keinen Chip, und die Platzhalter bleiben genullt (h713-wifi sagt
    # dann "Firmware fehlt" statt den Treiber zu laden).
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/aic_userconfig_8800d80.txt",      2807,   "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/aic_userconfig_8800d80.txt"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80.bin",              261352, "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_h_u02.bin",        328912, "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_h_u02.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_u02.bin",          328720, "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fmacfw_8800d80_u02.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80.bin",             1680,   "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80_u02.bin",         1708,   "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_adid_8800d80_u02.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80.bin",            8348,   "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02.bin",        31592,  "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02_ext0.bin",   10956,  "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_8800d80_u02_ext0.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80.bin",      648,    "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80_u02.bin",  23472,  "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/fw_patch_table_8800d80_u02.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80.bin",           302105, "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80.bin"),
    ("lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80_u02.bin",       256810, "hy310-rootfs", "/lib/firmware/aic8800_fw/SDIO/aic8800D80/lmacfw_rf_8800d80_u02.bin"),
]

# Platzhalter, die NICHT aus h713-extract kommen, sondern vom Nutzer:
# gleiche Mechanik (feste Groesse, Offset aus dem ext4), andere Quelle und
# andere Fuellung. hy310-install fuehrt sie unter "platzhalter_nutzer" in der
# Tabelle; ein aelterer Installer kennt den Schluessel nicht und laesst die
# Datei, wie sie ist -- und so, wie sie ist, ist sie gueltig (nur Zeilenumbrueche).
#   name -> (groesse, zielpartition, pfad, modus)
PLATZHALTER_NUTZER = [
    ("authorized_keys", 4096, "hy310-rootfs", "/root/.ssh/authorized_keys", 0o600),
]
# Verzeichnisse, die der Baum dafuer mit festem Modus anlegt (pfad, modus).
VERZEICHNISSE_NUTZER = [
    ("/root/.ssh", 0o700),
]
# Was im fertigen ext4 stimmen muss, sonst nimmt sshd den Schluessel nicht
# (StrictModes): Besitzer root, und diese Modi. /etc/passwd steht mit drin,
# weil ein als Nutzer ausgepackter Baum JEDE Datei uid 1000 gibt -- das ist
# am 11.09. im Abbild v0.5 so gewesen (mkimage-eingaben.sh lief nicht als
# root). (pfad, erwarteter modus oder None, uid, gid)
RECHTE_ROOTFS = [
    ("/etc/passwd", 0o644, 0, 0),
    ("/etc/shadow", 0o640, 0, 42),          # root:shadow
    ("/usr/sbin/unix_chkpwd", 0o2755, 0, 42),   # setgid shadow -- faellt als Nutzer weg
    ("/root", 0o700, 0, 0),
    ("/root/.ssh", 0o700, 0, 0),
    ("/root/.ssh/authorized_keys", 0o600, 0, 0),
    ("/usr/local/sbin/h713-tv", 0o755, 0, 0),
]

KERNEL_FIT = "h713-kernel.fit"        # echt, gehoert uns, kein Platzhalter


# ---------------------------------------------------------------- Kleinkram

def mib(b):
    return b / 2**20


class K:
    _farbe = sys.stdout.isatty() and os.name != "nt"

    @classmethod
    def _c(cls, code, t):
        return "\033[%sm%s\033[0m" % (code, t) if cls._farbe else t

    @classmethod
    def schritt(cls, n, t):
        print("\n%s %s" % (cls._c("1;36", "[%d]" % n), t))

    @classmethod
    def ok(cls, t):
        print("  %s %s" % (cls._c("32", "OK  "), t))

    @classmethod
    def info(cls, t):
        print("       %s" % t)

    @classmethod
    def warn(cls, t):
        print("  %s %s" % (cls._c("33", "HM  "), t))

    @classmethod
    def fehler(cls, t):
        print("  %s %s" % (cls._c("1;31", "FEHL"), t), file=sys.stderr)


def _rel(p, basis):
    """Relativ zur Projektwurzel, wenn das geht -- unter Windows liegen Pfade
    auf verschiedenen Laufwerken, und dann wirft relpath."""
    try:
        return os.path.relpath(p, basis)
    except ValueError:
        return os.path.abspath(p)


def sha256_datei(pfad, stueck=8 << 20):
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        while True:
            b = f.read(stueck)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def muster(name, laenge):
    """Der Inhalt eines unbefuellten Platzhalters.

    Bewusst kein Nullblock: (1) im Hexdump sieht man sofort, dass die Datei
    noch nicht gefuellt ist und welche es ist, (2) mke2fs legt fuer lauter
    Nullen unter Umstaenden ein Loch an (sparse) -- dann gaebe es keine
    physischen Bloecke, in die der Installer schreiben koennte.
    """
    kern = ("HY310-PLATZHALTER %s -- hy310-install fuellt das. " % name).encode("ascii", "replace")
    n = -(-laenge // len(kern))
    return (kern * n)[:laenge]


def ist_nutzer_platzhalter(name):
    return any(name == n for n, _g, _t, _p, _m in PLATZHALTER_NUTZER)


def fuellung(name, laenge):
    """Der Inhalt eines unbefuellten Platzhalters, je nach Art.

    Vendor-Dateien tragen das Muster (siehe muster()). authorized_keys besteht
    aus Zeilenumbruechen: sshd ueberliest Leerzeilen, die Datei ist so gueltig
    und leer, ob nun ein Installer sie fuellt oder nicht. Nullbytes oder das
    Muster stuenden dagegen als Muell in authorized_keys. Kein Nullblock --
    mke2fs -d legte sonst ein Loch statt eines Datenblocks an.
    """
    if ist_nutzer_platzhalter(name):
        return b"\n" * laenge
    return muster(name, laenge)


# ---------------------------------------------------------------- GPT

def gpt_bauen(disk_sektoren=DISK_SEKTOREN, partitionen=PARTITIONEN,
              diskguid=DISK_GUID, typguid=TYP_GUID):
    """Schutz-MBR, primaerer Kopf, Tabelle und beide Sicherungskopien.

    Rueckgabe: {lba: bytes}. Vorbild ist stock_gpt_bauen() in hy310-install.py;
    die Unterschiede zur Stock-Tabelle sind Absicht und stehen in doku/109 §2.2:
    FirstUsableLBA 16 statt 73728, sechs Eintraege, das reservierte Feld bei
    Offset 20 bleibt 0 (der Hersteller schreibt dort 1).
    """
    last_usable = disk_sektoren - 34
    arr = bytearray()
    for i in range(NENT):
        if i < len(partitionen):
            name, lba, sekt, ug = partitionen[i]
            e = (uuid.UUID(typguid).bytes_le + uuid.UUID(ug).bytes_le +
                 struct.pack("<QQQ", lba, lba + sekt - 1, 0) +
                 name.encode("utf-16-le").ljust(72, b"\0")[:72])
        else:
            e = b"\0" * ENTSZ
        arr += e[:ENTSZ]
    entcrc = binascii.crc32(bytes(arr)) & 0xFFFFFFFF

    def kopf(mylba, altlba, entlba):
        h = bytearray(92)
        h[0:8] = b"EFI PART"
        struct.pack_into("<III", h, 8, 0x10000, 92, 0)      # Rev, Kopfgroesse, CRC=0
        struct.pack_into("<I", h, 20, 0)                    # reserviert
        struct.pack_into("<QQQQ", h, 24, mylba, altlba, FIRST_USABLE, last_usable)
        h[56:72] = uuid.UUID(diskguid).bytes_le
        struct.pack_into("<QIII", h, 72, entlba, NENT, ENTSZ, entcrc)
        struct.pack_into("<I", h, 16, binascii.crc32(bytes(h)) & 0xFFFFFFFF)
        return bytes(h).ljust(SECT, b"\0")

    back_arr = disk_sektoren - 1 - ARR_SEKT
    mbr = bytearray(SECT)
    mbr[510:512] = b"\x55\xaa"
    # Wie am Geraet gemessen: Typ 0xEE ueber die ganze Platte, Groesse
    # 0xFFFFFFFF statt der echten Sektorzahl (bei Schutz-MBRs ueblich).
    mbr[446:462] = (b"\x00\x00\x02\x00\xee\xff\xff\xff" +
                    struct.pack("<II", 1, 0xFFFFFFFF))
    tab = bytes(arr).ljust(ARR_SEKT * SECT, b"\0")
    return {
        0: bytes(mbr),
        1: kopf(1, disk_sektoren - 1, 2),
        2: tab,
        back_arr: tab,
        disk_sektoren - 1: kopf(disk_sektoren - 1, 1, back_arr),
    }


def gpt_pruefen(mbr_kopf_tab, teil_c, disk_sektoren=DISK_SEKTOREN):
    """Eine gebaute oder gelesene GPT nachrechnen. Rueckgabe: Liste Probleme."""
    p = []
    if mbr_kopf_tab[510:512] != b"\x55\xaa":
        p.append("Schutz-MBR ohne 55AA")
    if mbr_kopf_tab[450] != 0xEE:
        p.append("Schutz-MBR: erster Eintrag ist nicht Typ 0xEE")
    hdr = mbr_kopf_tab[SECT:2 * SECT]
    if hdr[:8] != b"EFI PART":
        p.append("primaerer GPT-Kopf ohne Signatur")
        return p
    hsz = struct.unpack_from("<I", hdr, 12)[0]
    gespeichert = struct.unpack_from("<I", hdr, 16)[0]
    roh = bytearray(hdr[:hsz])
    struct.pack_into("<I", roh, 16, 0)
    if binascii.crc32(bytes(roh)) & 0xFFFFFFFF != gespeichert:
        p.append("CRC des primaeren GPT-Kopfs stimmt nicht")
    mylba, altlba, first, last = struct.unpack_from("<QQQQ", hdr, 24)
    entlba, nent, entsz, entcrc = struct.unpack_from("<QIII", hdr, 72)
    if (mylba, altlba) != (1, disk_sektoren - 1):
        p.append("MyLBA/AlternateLBA falsch (%d/%d)" % (mylba, altlba))
    if first != FIRST_USABLE:
        p.append("FirstUsableLBA ist %d, erwartet %d" % (first, FIRST_USABLE))
    if last != disk_sektoren - 34:
        p.append("LastUsableLBA ist %d, erwartet %d" % (last, disk_sektoren - 34))
    if (nent, entsz) != (NENT, ENTSZ):
        p.append("%d Eintraege a %d Byte, erwartet %d a %d" % (nent, entsz, NENT, ENTSZ))
    tab = mbr_kopf_tab[entlba * SECT:entlba * SECT + nent * entsz]
    if binascii.crc32(tab) & 0xFFFFFFFF != entcrc:
        p.append("CRC der Partitionstabelle stimmt nicht")
    gefunden = []
    for i in range(nent):
        e = tab[i * entsz:(i + 1) * entsz]
        if not any(e[:16]):
            continue
        s, en, _at = struct.unpack_from("<QQQ", e, 32)
        gefunden.append((e[56:128].decode("utf-16-le").rstrip("\0"), s, en - s + 1))
    soll = [(n, l, s) for n, l, s, _g in PARTITIONEN]
    if gefunden != soll:
        p.append("Partitionsliste weicht ab: %r" % (gefunden,))
    # Sicherungskopie
    if teil_c is not None:
        bhdr = teil_c[(disk_sektoren - 1 - TEIL_C_LBA) * SECT:][:SECT]
        if bhdr[:8] != b"EFI PART":
            p.append("Sicherungskopie des GPT-Kopfs fehlt am Plattenende (Befund S46 B7)")
        else:
            bmy, balt, _bf, _bl = struct.unpack_from("<QQQQ", bhdr, 24)
            bent = struct.unpack_from("<Q", bhdr, 72)[0]
            if (bmy, balt) != (disk_sektoren - 1, 1):
                p.append("Sicherungskopf: MyLBA/AlternateLBA falsch")
            btab = teil_c[(bent - TEIL_C_LBA) * SECT:][:nent * entsz]
            if btab != tab:
                p.append("Sicherungstabelle weicht von der primaeren ab")
            bhsz = struct.unpack_from("<I", bhdr, 12)[0]
            bges = struct.unpack_from("<I", bhdr, 16)[0]
            broh = bytearray(bhdr[:bhsz])
            struct.pack_into("<I", broh, 16, 0)
            if binascii.crc32(bytes(broh)) & 0xFFFFFFFF != bges:
                p.append("CRC des Sicherungskopfs stimmt nicht")
    return p


# ---------------------------------------------------------------- Baeume

def baum_boot(verz, fit=None, log=K):
    """Der Dateibaum, aus dem hy310-boot.ext4 entsteht."""
    os.makedirs(os.path.join(verz, "mips"), exist_ok=True)
    n = 0
    if fit:
        ziel = os.path.join(verz, KERNEL_FIT)
        with open(fit, "rb") as q, open(ziel, "wb") as z:
            while True:
                b = q.read(8 << 20)
                if not b:
                    break
                z.write(b)
        kopf = open(ziel, "rb").read(4)
        if kopf != b"\xd0\x0d\xfe\xed":
            raise SystemExit("%s traegt keine FIT-Kennung d00dfeed" % fit)
        log.ok("%-34s %9d Byte (echt)" % (KERNEL_FIT, os.path.getsize(ziel)))
        n += 1
    for name, groesse, teil, pfad in PLATZHALTER:
        if teil != "hy310-boot":
            continue
        ziel = os.path.join(verz, pfad.lstrip("/").replace("/", os.sep))
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "wb") as z:
            z.write(muster(name, groesse))
        n += 1
    log.ok("%d Dateien in %s" % (n, verz))
    return n


def baum_rootfs(verz, log=K):
    """Nur die Platzhalter, die ins Rootfs gehoeren -- als Overlay ueber den
    ausgepackten Baum aus hy310-rootfs.tar."""
    n = 0
    for name, groesse, teil, pfad in PLATZHALTER:
        if teil != "hy310-rootfs":
            continue
        ziel = os.path.join(verz, pfad.lstrip("/").replace("/", os.sep))
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "wb") as z:
            z.write(muster(name, groesse))
        n += 1
    # Die Nutzer-Platzhalter: Rechte ausdruecklich, nicht aus der umask.
    # Besitzer wird, wer den Baum schreibt -- deshalb muss das root sein
    # (mkimage-eingaben.sh prueft das); Schritt 5 prueft es im ext4 nach.
    for pfad, modus in VERZEICHNISSE_NUTZER:
        ziel = os.path.join(verz, pfad.lstrip("/").replace("/", os.sep))
        os.makedirs(ziel, exist_ok=True)
        os.chmod(ziel, modus)
    for name, groesse, teil, pfad, modus in PLATZHALTER_NUTZER:
        if teil != "hy310-rootfs":
            continue
        ziel = os.path.join(verz, pfad.lstrip("/").replace("/", os.sep))
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "wb") as z:
            z.write(fuellung(name, groesse))
        os.chmod(ziel, modus)
        n += 1
    log.ok("%d Platzhalter in %s (davon %d vom Nutzer zu fuellen: %s)"
           % (n, verz, len(PLATZHALTER_NUTZER),
              ", ".join(p for _n, _g, _t, p, _m in PLATZHALTER_NUTZER)))
    return n


# ---------------------------------------------------------------- ext4-Offsets

def _extraktor_laden(pfad=None):
    """h713-extract als Modul laden -- dort steckt der ext4-Leser (S45).
    Gleiche Mechanik wie _extraktor_laden() in hy310-install.py."""
    import importlib.machinery
    import importlib.util
    if pfad is None:
        hier = os.path.dirname(os.path.abspath(__file__))
        for k in (os.path.join(hier, "h713-extract"),
                  os.path.join(hier, "..", "r2-extract", "h713-extract")):
            if os.path.isfile(k):
                pfad = k
                break
    if not pfad or not os.path.isfile(pfad):
        raise SystemExit("h713-extract nicht gefunden -- der ext4-Leser steckt dort.")
    spec = importlib.util.spec_from_loader(
        "h713_extract", importlib.machinery.SourceFileLoader("h713_extract", pfad))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def ext4_offsets(datei, pfade, extraktor=None, log=K):
    """Fuer jeden Pfad im ext4-Abbild den Byte-Offset seiner Daten finden.

    Bedingung: die Datei muss EIN zusammenhaengendes Stueck sein, sonst ist ein
    einzelnes (Offset, Laenge) falsch. Wird geprueft, nicht angenommen. Zur
    Gegenprobe wird jede Datei einmal ueber den ext4-Leser und einmal roh am
    berechneten Offset gelesen und verglichen.
    """
    from pathlib import Path
    ex = _extraktor_laden(extraktor)
    q = ex.DateiQuelle(Path(datei))
    fs = ex.Ext4(q, label=os.path.basename(datei))
    bs = fs.block_size
    roh = open(datei, "rb")
    try:
        out = {}
        for pfad in pfade:
            ino = fs.pfad_ino(pfad)
            if ino is None:
                raise SystemExit("%s: %s gibt es nicht" % (datei, pfad))
            inode = fs.inode(ino)
            groesse = inode["groesse"]
            karte = fs._karte(ino, inode)
            if not karte:
                raise SystemExit("%s: %s hat keine Datenbloecke" % (datei, pfad))
            lb0, _n0, pb0 = karte[0]
            if lb0 != 0:
                raise SystemExit("%s: %s beginnt mit einem Loch" % (datei, pfad))
            gesehen, erw_p = 0, pb0
            for lb, n, pb in karte:
                if lb != gesehen or pb != erw_p:
                    raise SystemExit(
                        "%s: %s liegt nicht am Stueck (%d Fragmente) -- ein "
                        "einzelner Offset waere falsch" % (datei, pfad, len(karte)))
                gesehen += n
                erw_p += n
            if gesehen * bs < groesse:
                raise SystemExit("%s: %s hat ein Loch am Ende" % (datei, pfad))
            off = pb0 * bs
            roh.seek(off)
            if roh.read(groesse) != fs.lies(pfad):
                raise SystemExit("%s: %s -- Gegenprobe am Offset %d schlug fehl"
                                 % (datei, pfad, off))
            out[pfad] = (off, groesse)
        log.ok("%-22s Blockgroesse %d, %d Datei(en) am Stueck, Gegenprobe gleich"
               % (os.path.basename(datei), bs, len(out)))
        return out
    finally:
        roh.close()


def ext4_rechte_pruefen(datei, erwartung=RECHTE_ROOTFS, extraktor=None, log=K):
    """Besitzer und Modus einiger Dateien im fertigen ext4 nachsehen.

    Warum: mke2fs -d uebernimmt uid/gid/Modus aus dem Baum. Wird der Baum als
    normaler Nutzer ausgepackt, gehoert danach ALLES uid 1000 -- /etc/shadow,
    /root, sshd's authorized_keys. Das System bootet trotzdem, aber sshd
    verweigert den Schluessel (StrictModes), und vieles andere ist falsch.
    Genau so war es im Abbild v0.5 (11.09.2026). Deshalb ist das hier ein
    Abbruchgrund, kein Hinweis.
    """
    from pathlib import Path
    ex = _extraktor_laden(extraktor)
    fs = ex.Ext4(ex.DateiQuelle(Path(datei)), label=os.path.basename(datei))
    probleme = []
    for pfad, modus, uid, gid in erwartung:
        ino = fs.pfad_ino(pfad)
        if ino is None:
            probleme.append("%s fehlt" % pfad)
            continue
        i = fs.inode(ino)
        ist = i["mode"] & 0o7777
        if (i["uid"], i["gid"]) != (uid, gid):
            probleme.append("%s gehoert %d:%d statt %d:%d" % (pfad, i["uid"], i["gid"], uid, gid))
        if modus is not None and ist != modus:
            probleme.append("%s hat Modus %04o statt %04o" % (pfad, ist, modus))
    if probleme:
        for x in probleme:
            log.fehler(x)
        raise SystemExit("%s: Besitz/Rechte stimmen nicht -- der Baum wurde nicht als "
                         "root ausgepackt? (mkimage-eingaben.sh im Container mit "
                         "`podman exec -u root` ausfuehren)" % os.path.basename(datei))
    log.ok("%-22s Besitz root:root und Modi geprueft (%d Pfade, darunter /root/.ssh 0700, authorized_keys 0600)"
           % (os.path.basename(datei), len(erwartung)))


# ---------------------------------------------------------------- Bauen

def _kopiere(ziel_f, quelle, log=None):
    n = 0
    with open(quelle, "rb") as q:
        while True:
            b = q.read(8 << 20)
            if not b:
                break
            ziel_f.write(b)
            n += len(b)
    return n


def uboot_version(pfad):
    """Die Versionszeile aus einem U-Boot- oder SPL-Abbild ziehen.

    Am 10.09. ist ein Abbild mit einem U-Boot von zwei Commits vorher
    ausgeliefert worden. Es fehlte `net.ifnames=0`, die Netzschnittstelle hiess
    darum MAC-basiert, `allow-hotplug eth0` griff nie und das Geraet war nicht
    im Netz. Der Bauer sagt jetzt bei jedem Lauf, was er einbaut, und schreibt
    es in die Tabelle -- ein alter Stand faellt dann sofort auf.
    """
    try:
        with open(pfad, "rb") as fh:
            roh = fh.read()
    except OSError:
        return None
    m = re.search(rb"U-Boot(?: SPL)? \d{4}\.\d{2}[-\w.+]*", roh)
    return m.group(0).decode("latin1") if m else None


def bauen(args):
    hier = os.path.dirname(os.path.abspath(__file__))
    # Projektwurzel: das naechste Elternverzeichnis mit mainline/build/build.sh --
    # gilt im Arbeitsverzeichnis (analyse/release/arbeit/r0-fel) wie im Release-Repo
    # (installer/ direkt unter der Wurzel), doku/116 P3. Ohne Fund: das alte Muster.
    wurzel = hier
    while wurzel != os.path.dirname(wurzel) and not os.path.isfile(os.path.join(wurzel, "mainline", "build", "build.sh")):
        wurzel = os.path.dirname(wurzel)
    if not os.path.isfile(os.path.join(wurzel, "mainline", "build", "build.sh")):
        wurzel = os.path.abspath(os.path.join(hier, "..", "..", "..", ".."))

    def vorgabe(p):
        return os.path.join(wurzel, p)

    # Vorgaben: was release/build-all.sh unter mainline/build/out/ ablegt. tftp/ war die
    # Handablage bis v0.9 und bleibt nur als Rueckfall, wenn dort nichts liegt.
    def baustein(name):
        p = vorgabe("mainline/build/out/" + name)
        return p if os.path.isfile(p) else vorgabe("tftp/" + name)
    spl = args.spl or baustein("spl-release.bin")
    ub = args.uboot or baustein("uboot-proper-release.bin")
    env = args.env or baustein("hy310-env-release.bin")
    boot = args.boot_ext4 or os.path.join(hier, "tmp", "hy310-boot.ext4")
    root = args.rootfs_ext4 or os.path.join(hier, "tmp", "hy310-rootfs-platz.ext4")
    for w, p in (("--spl", spl), ("--uboot", ub), ("--env", env),
                 ("--boot-ext4", boot), ("--rootfs-ext4", root)):
        if not os.path.isfile(p):
            raise SystemExit("%s: %s nicht gefunden" % (w, p))

    ziel = os.path.abspath(args.out)
    verz = os.path.dirname(ziel) or "."
    os.makedirs(verz, exist_ok=True)
    stamm = ziel[:-4] if ziel.lower().endswith(".img") else ziel
    basis = os.path.basename(stamm)
    a_datei = stamm + "-a-bootkette.img"
    b_datei = stamm + "-b-system.img"
    c_datei = stamm + "-c-gptkopie.img"
    t_datei = stamm + ".tabelle.json"

    # --- 1. Groessen pruefen, bevor irgendetwas geschrieben wird
    K.schritt(1, "Bausteine pruefen")
    n_spl, n_ub = os.path.getsize(spl), os.path.getsize(ub)
    v_spl, v_ub = uboot_version(spl), uboot_version(ub)
    for was, pfad, ver in (("SPL", spl, v_spl), ("U-Boot", ub, v_ub)):
        if ver:
            K.info("  %-7s %s  (%s)" % (was, ver, os.path.basename(pfad)))
        else:
            K.warn("%s: keine Versionskennung in %s gefunden" % (was, pfad))
    n_boot, n_root = os.path.getsize(boot), os.path.getsize(root)
    if open(spl, "rb").read(12)[4:12] != b"eGON.BT0":
        raise SystemExit("%s traegt keine eGON.BT0-Kennung -- das ist keine SPL" % spl)
    if n_spl > 64 * SECT:
        raise SystemExit("SPL ist %d Byte, hy310-spl fasst %d" % (n_spl, 64 * SECT))
    if n_ub > 10240 * SECT:
        raise SystemExit("U-Boot ist %d Byte, hy310-uboot fasst %d" % (n_ub, 10240 * SECT))
    if n_boot != 262144 * SECT:
        raise SystemExit("hy310-boot.ext4 ist %d Byte, die Partition hat %d"
                         % (n_boot, 262144 * SECT))
    if n_root % SECT or n_root > 14991327 * SECT:
        raise SystemExit("hy310-rootfs.ext4 passt nicht (%d Byte)" % n_root)
    # Die Umgebung: 64 KiB, vorn ein CRC32 (little-endian) ueber den Rest --
    # so liest U-Boot sie (env/mmc.c, CONFIG_ENV_SIZE=0x10000, eine Kopie).
    # Bis v0.8 wurde hier ein Nullblock geschrieben; U-Boot meldete dann bei
    # jedem Start zweimal "bad CRC, using default environment", und jede
    # Installation loeschte die gespeicherte Umgebung (Marco, 12.09.: "das
    # geht nicht"). Jetzt kommt die eingebaute Vorgabe des mitgelieferten
    # U-Boot mit, aus `make u-boot-initial-env` + mkenvimage -- dieselben
    # Werte, aber gueltig, und h713_gate=1 steht damit ausdruecklich drin.
    n_env = os.path.getsize(env)
    if n_env != ENV_BYTES:
        raise SystemExit("%s ist %d Byte, die Umgebung hat %d (CONFIG_ENV_SIZE)" % (env, n_env, ENV_BYTES))
    with open(env, "rb") as f:
        env_roh = f.read()
    env_crc = struct.unpack("<I", env_roh[:4])[0]
    if env_crc != (zlib.crc32(env_roh[4:]) & 0xffffffff):
        raise SystemExit("%s: CRC32 im Kopf (%08x) passt nicht zum Inhalt -- keine U-Boot-Umgebung"
                         % (env, env_crc))
    env_eintraege = [e.decode("ascii", "replace") for e in env_roh[4:].split(b"\0") if e and e != b"\xff" * len(e)]
    env_gate = [e for e in env_eintraege if e.startswith("h713_gate=")]
    for w, p, n in (("SPL", spl, n_spl), ("U-Boot proper", ub, n_ub), ("Umgebung", env, n_env),
                    ("hy310-boot.ext4", boot, n_boot), ("hy310-rootfs.ext4", root, n_root)):
        K.ok("%-16s %11d Byte  %s" % (w, n, _rel(p, wurzel)))
    K.info("  Umgebung: %d Eintraege, CRC %08x, %s" % (len(env_eintraege), env_crc,
           ", ".join(env_gate) if env_gate else "KEIN h713_gate -- pruefen"))

    # --- 2. Teil A: GPT + SPL + U-Boot, LBA 0..12287
    K.schritt(2, "Teil A -- Boot-Kette (LBA %d..%d)" % (TEIL_A_LBA, TEIL_A_SEKT - 1))
    gpt = gpt_bauen()
    a = bytearray(TEIL_A_SEKT * SECT)
    a[0:SECT] = gpt[0]
    a[SECT:2 * SECT] = gpt[1]
    a[2 * SECT:2 * SECT + len(gpt[2])] = gpt[2]
    with open(spl, "rb") as f:
        a[LBA_SPL * SECT:LBA_SPL * SECT + n_spl] = f.read()
    with open(ub, "rb") as f:
        a[LBA_UBOOT * SECT:LBA_UBOOT * SECT + n_ub] = f.read()
    with open(a_datei, "wb") as f:
        f.write(bytes(a))
    K.ok("%s  %d Byte (%.0f MiB)" % (os.path.basename(a_datei), len(a), mib(len(a))))

    # --- 3. Teil C: Sicherungskopie der GPT am Plattenende (Befund S46 B7)
    K.schritt(3, "Teil C -- Sicherungskopie der GPT (LBA %d, %d Sektoren)"
              % (TEIL_C_LBA, TEIL_C_SEKT))
    c = bytearray(TEIL_C_SEKT * SECT)
    back_arr = DISK_SEKTOREN - 1 - ARR_SEKT
    c[(back_arr - TEIL_C_LBA) * SECT:(back_arr - TEIL_C_LBA) * SECT + len(gpt[back_arr])] = gpt[back_arr]
    c[(DISK_SEKTOREN - 1 - TEIL_C_LBA) * SECT:] = gpt[DISK_SEKTOREN - 1]
    with open(c_datei, "wb") as f:
        f.write(bytes(c))
    K.ok("%s  %d Byte -- raeumt zugleich Reste der alten Tabelle weg"
         % (os.path.basename(c_datei), len(c)))

    probleme = gpt_pruefen(bytes(a[:9 * SECT]), bytes(c))
    if probleme:
        for x in probleme:
            K.fehler(x)
        raise SystemExit("die gebaute GPT ist nicht in Ordnung")
    K.ok("GPT nachgerechnet: CRCs, FirstUsable %d, %d Eintraege, sechs Partitionen, "
         "Sicherungskopie stimmt" % (FIRST_USABLE, NENT))

    # --- 4. Teil B: Umgebung + Rest von hy310-env (SPL-Parkplatz, leer) + hy310-boot + hy310-rootfs
    K.schritt(4, "Teil B -- System (LBA %d ...)" % TEIL_B_LBA)
    with open(b_datei, "wb") as f:
        f.write(env_roh)                                             # hy310-env: die Umgebung, LBA 14336
        f.write(b"\0" * ((LBA_BOOT - TEIL_B_LBA) * SECT - n_env))   # Rest der Partition (SPL-Parkplatz 14464), leer
        _kopiere(f, boot)
        _kopiere(f, root)
    n_b = os.path.getsize(b_datei)
    soll_b = (LBA_BOOT - TEIL_B_LBA) * SECT + n_boot + n_root
    assert n_b == soll_b, (n_b, soll_b)
    K.ok("%s  %d Byte (%.0f MiB)" % (os.path.basename(b_datei), n_b, mib(n_b)))
    K.info("hy310-env traegt die eingebaute Vorgabe des mitgelieferten U-Boot (%s) -- gueltig ab dem ersten Start"
           % (", ".join(env_gate) if env_gate else "ohne h713_gate"))

    # --- 5. Platzhalter-Offsets suchen
    K.schritt(5, "Platzhalter im Abbild finden")
    off_boot = ext4_offsets(boot, [p for _n, _g, t, p in PLATZHALTER if t == "hy310-boot"],
                            args.extraktor)
    off_root = ext4_offsets(root, [p for _n, _g, t, p in PLATZHALTER if t == "hy310-rootfs"] +
                            [p for _n, _g, t, p, _m in PLATZHALTER_NUTZER if t == "hy310-rootfs"],
                            args.extraktor)
    ext4_rechte_pruefen(root, extraktor=args.extraktor)
    basis_boot = (LBA_BOOT - TEIL_B_LBA) * SECT
    basis_root = (LBA_ROOTFS - TEIL_B_LBA) * SECT

    tabelle, nutzer, info = {}, {}, {}
    alle = [(n, g, t, p, "h713-extract") for n, g, t, p in PLATZHALTER] + \
           [(n, g, t, p, "hy310-install --authorized-key") for n, g, t, p, _m in PLATZHALTER_NUTZER]
    for name, groesse, teil, pfad, quelle in alle:
        if teil == "hy310-boot":
            o, g = off_boot[pfad]
            o += basis_boot
        else:
            o, g = off_root[pfad]
            o += basis_root
        if g != groesse:
            raise SystemExit("%s: %d Byte im Dateisystem, %d in der Tabelle"
                             % (name, g, groesse))
        (nutzer if ist_nutzer_platzhalter(name) else tabelle)[name] = [o, g]
        info[name] = {
            "ziel": "%s:%s" % (teil, pfad),
            "laenge": g,
            "lba": (TEIL_B_LBA * SECT + o) // SECT,
            "disk_offset": TEIL_B_LBA * SECT + o,
            "quelle": quelle,
            "fuellung": "zeilenumbrueche" if ist_nutzer_platzhalter(name) else "muster",
            "sha256_muster": hashlib.sha256(fuellung(name, g)).hexdigest(),
        }
    K.ok("%d Platzhalter fuer h713-extract, zusammen %d Byte"
         % (len(tabelle), sum(g for _o, g in tabelle.values())))
    K.ok("%d Platzhalter fuer den Nutzer: %s"
         % (len(nutzer), ", ".join("%s (%d Byte, Zeilenumbrueche)" % (n, g)
                                   for n, (_o, g) in nutzer.items())))

    # Gegenprobe: steht am errechneten Offset in Teil B wirklich die Fuellung?
    with open(b_datei, "rb") as f:
        for name, (o, g) in list(tabelle.items()) + list(nutzer.items()):
            f.seek(o)
            if f.read(g) != fuellung(name, g):
                raise SystemExit("%s: an Offset %d steht nicht die erwartete Fuellung" % (name, o))
    K.ok("alle %d Offsets in Teil B gegengeprueft" % (len(tabelle) + len(nutzer)))

    # --- 6. Loch pruefen
    K.schritt(6, "Der gesperrte Bereich")
    teile = [(a_datei, TEIL_A_LBA), (b_datei, TEIL_B_LBA), (c_datei, TEIL_C_LBA)]
    for datei, lba in teile:
        ende = lba + os.path.getsize(datei) // SECT - 1
        if lba <= SPERRE_LETZTER and ende >= SPERRE_ERSTER:
            raise SystemExit("%s deckt LBA %d..%d ab und beruehrt damit den "
                             "Secure Storage" % (datei, lba, ende))
    K.ok("kein Teil beruehrt LBA %d..%d -- auch ein dd von Hand kann den Secure "
         "Storage nicht treffen" % (SPERRE_ERSTER, SPERRE_LETZTER))

    # --- 7. Pruefsummen, Tabelle, Manifest, Liesmich
    K.schritt(7, "Tabelle, Manifest, Liesmich")
    teil_liste = []
    for datei, lba in teile:
        n = os.path.getsize(datei)
        teil_liste.append({
            "datei": os.path.basename(datei),
            "lba": lba,
            "sektoren": n // SECT,
            "bytes": n,
            "sha256": sha256_datei(datei),
            "dd": "dd if=%s of=/dev/sdX bs=512 seek=%d conv=fsync"
                  % (os.path.basename(datei), lba),
        })
    daten = {
        "format": "hy310-abbild-tabelle",
        "version": 1,
        "werkzeug": "hy310-mkimage " + VERSION,
        "erzeugt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "abbild": basis,
        "sektorgroesse": SECT,
        "disk_sektoren": DISK_SEKTOREN,
        "layout": "v3 (doku/109 §2.2)",
        "partitionen": [{"name": n, "lba": l, "sektoren": s, "guid": g}
                        for n, l, s, g in PARTITIONEN],
        "loch": {
            "lba": SPERRE_ERSTER,
            "sektoren": SPERRE_LETZTER - SPERRE_ERSTER + 1,
            "partition": "hy310-keys",
            "warum": ("Secure Storage: HDCP-Schluessel, WLAN-/BT-MAC-Adressen und "
                      "Seriennummer. Geraetespezifisch, in keinem Firmware-Abbild, "
                      "nicht wiederherstellbar (doku/109 §2.3). Deshalb steht dieser "
                      "Bereich in keinem Teil des Abbilds."),
        },
        "teile": teil_liste,
        "bausteine": {
            "spl": {"datei": _rel(spl, wurzel), "bytes": n_spl,
                    "sha256": sha256_datei(spl), "lba": LBA_SPL,
                    "version": v_spl},
            "uboot": {"datei": _rel(ub, wurzel), "bytes": n_ub,
                      "sha256": sha256_datei(ub), "lba": LBA_UBOOT,
                      "version": v_ub},
            "env": {"datei": _rel(env, wurzel), "bytes": n_env,
                    "sha256": sha256_datei(env), "lba": LBA_ENV,
                    "crc32": "%08x" % env_crc, "eintraege": len(env_eintraege)},
            "boot_ext4": {"datei": _rel(boot, wurzel), "bytes": n_boot,
                          "sha256": sha256_datei(boot), "lba": LBA_BOOT},
            "rootfs_ext4": {"datei": _rel(root, wurzel), "bytes": n_root,
                            "sha256": sha256_datei(root), "lba": LBA_ROOTFS},
        },
        # Genau das Format, das platzhalter_fuellen() in hy310-install.py
        # erwartet: name -> (byte_offset, laenge), Offset in der Datei
        # unter "platzhalter_datei".
        "platzhalter_datei": os.path.basename(b_datei),
        "platzhalter": tabelle,
        # Gleiche Form, andere Quelle: fuellt hy310-install aus --authorized-key,
        # aufgefuellt mit Zeilenumbruechen. Ein Installer, der den Schluessel
        # nicht kennt, laesst die Datei leer (nur Zeilenumbrueche) -- gueltig.
        "platzhalter_nutzer": nutzer,
        "platzhalter_info": info,
    }
    with open(t_datei, "w", encoding="utf-8") as f:
        json.dump(daten, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")
    K.ok(os.path.basename(t_datei))

    sums = stamm + ".sha256"
    with open(sums, "w", encoding="utf-8") as f:
        for t in teil_liste:
            f.write("%s  %s\n" % (t["sha256"], t["datei"]))
        f.write("%s  %s\n" % (sha256_datei(t_datei), os.path.basename(t_datei)))
    K.ok(os.path.basename(sums))

    liesmich = stamm + "-LIESMICH.txt"
    with open(liesmich, "w", encoding="utf-8") as f:
        f.write(liesmich_text(daten))
    K.ok(os.path.basename(liesmich))

    gesamt = sum(t["bytes"] for t in teil_liste)
    K.schritt(8, "Fertig")
    K.info("drei Teile, zusammen %.0f MiB (%.2f GB)" % (mib(gesamt), gesamt / 1e9))
    K.info("Verzeichnis: %s" % verz)
    K.info("Pruefen mit:  %s --pruefen %s"
           % (os.path.basename(sys.argv[0]), _rel(t_datei, os.getcwd())))
    return 0


# ---------------------------------------------------------------- Pruefen

def pruefen(tabelle_datei, log=K):
    verz = os.path.dirname(os.path.abspath(tabelle_datei))
    with open(tabelle_datei, encoding="utf-8") as f:
        d = json.load(f)
    if d.get("format") != "hy310-abbild-tabelle":
        raise SystemExit("%s ist keine Abbild-Tabelle" % tabelle_datei)
    schlecht = 0

    log.schritt(1, "Teile: Groesse und Pruefsumme")
    teile = {}
    for t in d["teile"]:
        p = os.path.join(verz, t["datei"])
        if not os.path.isfile(p):
            log.fehler("%s fehlt" % t["datei"])
            schlecht += 1
            continue
        n = os.path.getsize(p)
        if n != t["bytes"]:
            log.fehler("%s ist %d Byte, erwartet %d" % (t["datei"], n, t["bytes"]))
            schlecht += 1
            continue
        h = sha256_datei(p)
        if h != t["sha256"]:
            log.fehler("%s: sha256 %s…, erwartet %s…" % (t["datei"], h[:16], t["sha256"][:16]))
            schlecht += 1
            continue
        teile[t["datei"]] = (p, t["lba"], n)
        log.ok("%-34s LBA %-9d %11d Byte  %s…" % (t["datei"], t["lba"], n, h[:16]))

    log.schritt(2, "Der gesperrte Bereich (Secure Storage)")
    erster = d["loch"]["lba"]
    letzter = erster + d["loch"]["sektoren"] - 1
    if (erster, letzter) != (SPERRE_ERSTER, SPERRE_LETZTER):
        log.fehler("die Tabelle nennt LBA %d..%d, dieses Werkzeug kennt %d..%d"
                   % (erster, letzter, SPERRE_ERSTER, SPERRE_LETZTER))
        schlecht += 1
    beruehrt = False
    for name, (p, lba, n) in teile.items():
        ende = lba + n // SECT - 1
        if lba <= letzter and ende >= erster:
            log.fehler("%s deckt LBA %d..%d ab und beruehrt den Secure Storage"
                       % (name, lba, ende))
            beruehrt = True
            schlecht += 1
    if not beruehrt:
        log.ok("kein Teil beruehrt LBA %d..%d -- der Bereich bleibt, wie er ist"
               % (erster, letzter))

    log.schritt(3, "Partitionstabelle")
    a = [x for x in d["teile"] if x["lba"] == 0]
    c = [x for x in d["teile"] if x["lba"] == DISK_SEKTOREN - 33]
    if not a or a[0]["datei"] not in teile:
        log.fehler("kein Teil bei LBA 0 -- GPT nicht pruefbar")
        schlecht += 1
    else:
        kopf = open(teile[a[0]["datei"]][0], "rb").read(9 * SECT)
        cbytes = open(teile[c[0]["datei"]][0], "rb").read() if c and c[0]["datei"] in teile else None
        probleme = gpt_pruefen(kopf, cbytes, d["disk_sektoren"])
        for x in probleme:
            log.fehler(x)
        schlecht += len(probleme)
        if not probleme:
            log.ok("CRCs stimmen, FirstUsableLBA %d, %d Eintraege, sechs Partitionen"
                   % (FIRST_USABLE, NENT))
            log.ok("Sicherungskopie am Plattenende vorhanden und gleich (Befund S46 B7)")

    log.schritt(4, "Platzhalter")
    pd = d["platzhalter_datei"]
    if pd not in teile:
        log.fehler("%s fehlt -- Platzhalter nicht pruefbar" % pd)
        return 1
    pfad, plba, pn = teile[pd]
    offen, gefuellt, kaputt = 0, 0, 0
    beide = dict(d["platzhalter"])
    beide.update(d.get("platzhalter_nutzer", {}))
    with open(pfad, "rb") as f:
        for name in sorted(beide):
            off, laenge = beide[name]
            info = d.get("platzhalter_info", {}).get(name, {})
            if off < 0 or off + laenge > pn:
                log.fehler("%s: Offset %d + %d liegt ausserhalb von %s"
                           % (name, off, laenge, pd))
                kaputt += 1
                continue
            disk = plba * SECT + off
            if info.get("disk_offset") not in (None, disk):
                log.fehler("%s: disk_offset in der Tabelle passt nicht zum Teil" % name)
                kaputt += 1
                continue
            sperre_von, sperre_bis = erster * SECT, (letzter + 1) * SECT
            if disk < sperre_bis and disk + laenge > sperre_von:
                log.fehler("%s liegt im gesperrten Bereich" % name)
                kaputt += 1
                continue
            f.seek(off)
            b = f.read(laenge)
            if b == fuellung(name, laenge):
                offen += 1
            elif info.get("sha256_muster") and \
                    hashlib.sha256(b).hexdigest() == info["sha256_muster"]:
                offen += 1
            else:
                gefuellt += 1
    log.ok("%d Platzhalter geprueft: %d unbefuellt (Fuellung steht), %d bereits gefuellt"
           % (len(beide), offen, gefuellt))
    if kaputt:
        log.fehler("%d Platzhalter stimmen nicht" % kaputt)
        schlecht += kaputt
    if gefuellt:
        log.warn("dieses Abbild ist nicht mehr das Verteilstueck -- es traegt "
                 "geraeteeigene Daten und gehoert nicht weitergegeben")

    log.schritt(5, "Ergebnis")
    if schlecht:
        log.fehler("%d Beanstandung(en)" % schlecht)
        return 1
    log.ok("alles in Ordnung")
    return 0


# ---------------------------------------------------------------- Liesmich

# Wortlaut aus doku/110-plan-installationsweg.md §9 bzw. dem Kasten dort ganz
# oben. doku/110 §9: "Der Kasten oben ist keine Formsache und darf nicht
# wegredigiert werden." Deshalb steht er hier woertlich.
BETA_WARNUNG = """\
 ⚠ Was jedem Nutzer vor dem ersten Schritt gesagt werden muss

 Das hier ist eine Beta. Nicht im Sinne von „ein paar Ecken sind unrund",
 sondern: es kann schiefgehen, und dann steht ein Gerät da, das nicht mehr
 startet.

 Deshalb gilt, ohne Ausnahme und in dieser Reihenfolge:

 1. Mach einen Vollabzug. Nicht den kleinen — den vollen, 7,3 GB, 17 Minuten.
    Damit spielst du dein Gerät genau so zurück, wie es war.
 2. Oder halte die passende Herstellerfirmware bereit, bevor du anfängst.
    Nicht danach suchen, wenn es klemmt.
 3. Erst dann loslegen.

 Wer beides überspringt, riskiert ein Gerät ohne Rückweg. Der FEL-Modus rettet
 die Boot-Kette, aber er stellt keine Daten wieder her, die niemand gesichert
 hat.
"""


def liesmich_text(d):
    z = []
    b = z.append
    b("HY310/H713-Beamer — Abbild %s" % d["abbild"])
    b("=" * (28 + len(d["abbild"])))
    b("")
    b("Gebaut am %s mit %s." % (d["erzeugt"], d["werkzeug"]))
    b("")
    b("-" * 78)
    b(BETA_WARNUNG.rstrip())
    b("-" * 78)
    b("")
    b("")
    b("Was hier liegt")
    b("--------------")
    b("")
    b("Das Abbild besteht aus DREI Dateien. Das ist kein Versehen, sondern der")
    b("Kern der Sache — siehe den nächsten Abschnitt.")
    b("")
    for t in d["teile"]:
        b("  %-34s %11d Byte   ab Sektor %d" % (t["datei"], t["bytes"], t["lba"]))
    b("  %-34s             wo die Platzhalter liegen" % (d["abbild"] + ".tabelle.json"))
    b("  %-34s             Prüfsummen" % (d["abbild"] + ".sha256"))
    b("")
    b("")
    b("Warum drei Dateien und nicht eine")
    b("---------------------------------")
    b("")
    b("Zwischen den Teilen A und B liegt eine Lücke: die Sektoren %d bis %d,"
      % (d["loch"]["lba"], d["loch"]["lba"] + d["loch"]["sektoren"] - 1))
    b("also 1 MiB. Dort steht das Secure Storage deines Geräts:")
    b("")
    b("  * die HDCP-Schlüssel (ohne sie kein geschütztes Bild über HDMI)")
    b("  * die MAC-Adressen von WLAN und Bluetooth")
    b("  * die Seriennummer")
    b("")
    b("Diese Daten gibt es NUR auf deinem Gerät. Sie stehen in keinem")
    b("Firmware-Abbild, auch nicht in dem des Herstellers, und niemand kann sie")
    b("nachbauen. Wer sie überschreibt, hat sie für immer verloren.")
    b("")
    b("Ein durchgehendes Abbild würde sie beim Schreiben mit Nullen zudecken.")
    b("Deshalb kommt der Bereich in keiner der drei Dateien vor. Du kannst ihn")
    b("gar nicht treffen — auch nicht mit einem dd von Hand, auch nicht, wenn du")
    b("einen Befehl vergisst.")
    b("")
    b("")
    b("Einspielen")
    b("----------")
    b("")
    b("Gerät in den FEL-Modus bringen (Reset-Taste halten, Strom einstecken),")
    b("dann mit hy310-install die Laufwerksfreigabe starten. Danach ist die eMMC")
    b("ein ganz normales USB-Laufwerk.")
    b("")
    b("Der bequeme Weg — hy310-install macht Sicherung, Extraktion und Schreiben:")
    b("")
    b("    hy310-install --uboot u-boot-sunxi-with-spl.bin \\")
    b("                  --abbild %s.tabelle.json" % d["abbild"])
    b("")
    b("Der Weg von Hand, wenn die eMMC schon als /dev/sdX zu sehen ist. ALLE DREI")
    b("Befehle, in dieser Reihenfolge, und /dev/sdX vorher zweimal prüfen:")
    b("")
    for t in d["teile"]:
        b("    dd if=%s of=/dev/sdX bs=512 seek=%d conv=fsync"
          % (t["datei"], t["lba"]))
    b("")
    b("(Teil B geht mit bs=1M seek=7 schneller — dasselbe Ziel, weil Sektor")
    b("%d genau 7 MiB sind.)" % TEIL_B_LBA)
    b("")
    b("Danach Strom abziehen und wieder einstecken.")
    b("")
    b("")
    b("Was danach noch fehlt")
    b("---------------------")
    b("")
    b("Im Abbild stecken %d Platzhalter: Dateien in der richtigen Größe, aber mit"
      % len(d["platzhalter"]))
    b("Füllmuster statt Inhalt. Es sind die Teile, die dem Hersteller gehören und")
    b("die wir nicht mitverteilen dürfen:")
    b("")
    b("  * 19 Anzeige-Artefakte (mips/) — ohne sie bleibt das Bild schwarz")
    b("  * 3 Firmware-Dateien (ARISC, EDID, MSP-Patch)")
    b("  * 8 PQ-Dateien (Bildabstimmung)")
    b("")
    b("Sie kommen aus deinem eigenen Gerät: h713-extract liest sie aus dem")
    b("Vollabzug, den du vorher gezogen hast, und hy310-install schreibt sie an")
    b("die Stellen, die in %s.tabelle.json stehen — am PC," % d["abbild"])
    b("bevor überhaupt etwas auf die eMMC geht.")
    b("")
    b("Solange sie nicht gefüllt sind, startet das System zwar, aber ohne Bild.")
    b("")
    b("Ein Platzhalter mehr gehört dir selbst: /root/.ssh/authorized_keys. Im")
    b("Abbild ist die Datei leer (4096 Zeilenumbrüche). Mit")
    b("")
    b("    hy310-install ... --authorized-key ~/.ssh/id_ed25519.pub")
    b("")
    b("kommt dein öffentlicher SSH-Schlüssel hinein, und du kommst per ssh als")
    b("root auf das Gerät. Ohne den Schalter bleibt nur die serielle Konsole")
    b("(Passwort-Login ist aus). Kein Schlüssel wird mitverteilt.")
    b("")
    b("")
    b("Wenn etwas schiefgeht")
    b("---------------------")
    b("")
    b("NICHT den Strom ziehen und hoffen. Das Gerät in den FEL-Modus bringen")
    b("(Reset halten, Strom einstecken) und von vorn anfangen — die Boot-Kette")
    b("ist von dort immer erreichbar. Wenn du einen Vollabzug hast, spielt")
    b("hy310-install --restore ihn zurück.")
    b("")
    return "\n".join(z) + "\n"


# ---------------------------------------------------------------- main

def main(argv=None):
    p = argparse.ArgumentParser(
        description="Das einspielbare Abbild fuer den HY310/H713-Beamer bauen (doku/109, doku/110).",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--out", metavar="DATEI.img",
                   help="Ziel; daneben entstehen Tabelle, Pruefsummen und LIESMICH")
    p.add_argument("--pruefen", metavar="TABELLE.json",
                   help="ein fertiges Abbild gegen seine Tabelle validieren")
    p.add_argument("--baum-boot", metavar="VERZ",
                   help="nur den Dateibaum fuer hy310-boot schreiben")
    p.add_argument("--baum-rootfs", metavar="VERZ",
                   help="nur die Rootfs-Platzhalter schreiben (Overlay)")
    p.add_argument("--fit", help="Kernel-FIT fuer --baum-boot")
    p.add_argument("--spl", help="SPL (Vorgabe: tftp/spl-release.bin)")
    p.add_argument("--uboot", help="U-Boot proper (Vorgabe: tftp/uboot-proper-release.bin)")
    p.add_argument("--env", help="U-Boot-Umgebung, 64 KiB mit CRC aus mkenvimage (Vorgabe: tftp/hy310-env-release.bin)")
    p.add_argument("--boot-ext4", help="fertiges hy310-boot.ext4 (128 MiB)")
    p.add_argument("--rootfs-ext4", help="fertiges hy310-rootfs.ext4 mit Platzhaltern")
    p.add_argument("--extraktor", help="Pfad zu h713-extract (sonst daneben gesucht)")
    p.add_argument("--version", action="version", version="hy310-mkimage " + VERSION)
    args = p.parse_args(argv)

    print("hy310-mkimage %s" % VERSION)
    if args.baum_boot:
        return 0 if baum_boot(args.baum_boot, args.fit) else 1
    if args.baum_rootfs:
        return 0 if baum_rootfs(args.baum_rootfs) else 1
    if args.pruefen:
        return pruefen(args.pruefen)
    if args.out:
        return bauen(args)
    p.print_help()
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        sys.exit(130)
