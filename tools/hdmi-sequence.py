#!/usr/bin/env python3
"""
hdmi-sequence.py -- die Stock-HDMI-Init-Sequenz aus Linux fahren, auf arm64.

Warum es das gibt: `userspace/hy310-hdmird` ist arm32-C++ und laeuft auf
diesem Board nicht. Das hier ist dieselbe Sequenz, dieselben Argumente,
dieselben Shmem-Offsets -- nur in Python gegen /dev/cpu_comm und /dev/mem.

Quelle fuer JEDES Argument unten ist hy310-hdmird/src/main.cpp, dessen
Kommentare die Herkunft nennen (libhaldisplay.so-Wrapper-RE + Stock-elog).
Wo diese Datei von tools/uboot-hdmi-sequence.txt abweicht, hat hdmird recht:
die U-Boot-Datei trug bis 04.09.2026 drei falsche Argumentsaetze.

  ./hdmi-sequence.py list                 Schritte zeigen, nichts tun
  ./hdmi-sequence.py run                  Schritte 1..N-1 (STOPPT vor SetSource)
  ./hdmi-sequence.py run --from 3 --to 7  nur diese Schritte
  ./hdmi-sequence.py run --setsource      auch SetSource -- SIEHE WARNUNG
  ./hdmi-sequence.py callbacks            nur die 10 MipsHalCallback_* anmelden

WARNUNG SetSource: am 01.09.2026 an Position 2 gerufen -- kein RETURN, der
einzige BG_Thread der Firmware blockierte, alle folgenden Aufrufe liefen ins
Leere. Erholung nur per Stromzyklus. Deshalb ist es ein eigener Schalter und
laeuft nie mit `run` allein.

NIEMALS 0152f134 (THal_Vp_EnableScreenCover): wedgt CPU_COMM dauerhaft.
"""
import argparse
import fcntl
import mmap
import os
import struct
import sys
import time

DEV = "/dev/cpu_comm"
IOCTL_CALL = 0xC0087F26
IOCTL_INSTALL_RT = 0xC0087F30

# aus hy310-hdmird/include/cpucomm.h
NAME2ID_SEED = 0x00123456
SHMEM_PHYS_BASE = 0x4E300000
SHMEM_SIZE = 0x00500000

# Shmem-Belegung, exakt wie hdmird sie waehlt (main.cpp).
# HDCP22 bei 0x36000, weil Stock genau diese Adresse benutzt und IOCTL_MALLOC
# auf Mainline scheitert (Trid_SMM_MallocAttr liefert 0, MIPS-SMM-Heap nicht
# initialisiert). Der MIPS dereferenziert die Phys-Adresse ohnehin.
HDCP22_OFFSET = 0x36000
WCE_SRC_OFFSET = 0x37000
WCE_DST_OFFSET = 0x37020
WCE_ASPECT_OFFSET = 0x37040
VP_INIT_STAGING = SHMEM_PHYS_BASE + 0x00400000  # 0x4E700000, 64 KiB frei

HDCP22_FILE = "/lib/firmware/hdcp_v22.bin"
HDCP22_FILE_SIZE = 960   # auf der Platte
HDCP22_CALL_SIZE = 912   # was Stock an den MIPS meldet: 48 B Header uebersprungen

# Pause zwischen Aufrufen. Die FreeCall-FIFO hat 21 Plaetze und wird nur
# MIPS-seitig nachgefuellt; ohne Drossel laeuft ARM dem MIPS davon.
CALL_GAP_MS = 50

CALLBACKS = [
    "MipsHalCallback_SignalChange",
    "MipsHalCallback_HdmiHotPlugByPortHandler",
    "MipsHalCallback_HdmiSignalValidCallback",
    "MipsHalCallback_OnNewSPDPacket",
    "MipsHalCallback_OnNewGCPacket",
    "MipsHalCallback_OnNewAVIPacket",
    "MipsHalCallback_OnNewACRPacket",
    "MipsHalCallback_DisplayLatencyChange",
    "MipsHalCallback_OnNewAudioInfoPacket",
    "MipsHalCallback_OnNewVSIPacket",
]


def _crc32_table():
    tbl = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0xEDB88320 if (c & 1) else (c >> 1)
        tbl.append(c)
    return tbl


_TABLE = _crc32_table()


def name2id(name):
    crc = NAME2ID_SEED
    for b in name.encode():
        crc = _TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc & 0xFFFFFFFF


def routine_name(base, target_cpu, pid=0):
    return "%s_%x_%03x" % (base, target_cpu, pid & 0xFFF)


class Shmem:
    """Das 5-MiB-Fenster bei 0x4E300000, ueber /dev/mem."""

    def __init__(self):
        self.fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        self.m = mmap.mmap(self.fd, SHMEM_SIZE, mmap.MAP_SHARED,
                           mmap.PROT_READ | mmap.PROT_WRITE,
                           offset=SHMEM_PHYS_BASE)

    def write(self, offset, data):
        self.m[offset:offset + len(data)] = data

    def read(self, offset, n):
        return bytes(self.m[offset:offset + n])

    def phys(self, offset):
        return SHMEM_PHYS_BASE + offset

    def close(self):
        self.m.close()
        os.close(self.fd)


class CpuComm:
    def __init__(self):
        self.fd = os.open(DEV, os.O_RDWR)

    def install(self, base_name, target_cpu=0, channel=0):
        """IOCTL_INSTALL_RT -- 96-Byte RoutineDesc.

        reserved0 bei +2 traegt target_cpu: ohne das schreibt AddInRoutine
        entry+2=0 und SendComm2CPUEx routet zu ARM statt MIPS (Y2, 04.05.).
        """
        name = routine_name(base_name, target_cpu, 0)
        cid = name2id(name)
        buf = bytearray(96)
        struct.pack_into("<H", buf, 0, channel)
        struct.pack_into("<H", buf, 2, target_cpu)
        struct.pack_into("<I", buf, 4, os.getpid())
        struct.pack_into("<I", buf, 8, cid)
        nb = name.encode()[:63]
        buf[12:12 + len(nb)] = nb
        struct.pack_into("<i", buf, 92, -1)
        fcntl.ioctl(self.fd, IOCTL_INSTALL_RT, bytes(buf), True)
        return cid, name

    def call(self, comp_id, params, dst_cpu=1):
        """IOCTL_CALL -- 168-Byte CallMsg. params ab +68, Anzahl bei +64."""
        buf = bytearray(168)
        struct.pack_into("<H", buf, 2, dst_cpu)
        struct.pack_into("<I", buf, 40, comp_id)
        struct.pack_into("<I", buf, 64, len(params))
        for i, p in enumerate(params[:10]):
            struct.pack_into("<I", buf, 68 + 4 * i, p & 0xFFFFFFFF)
        t0 = time.time()
        out = fcntl.ioctl(self.fd, IOCTL_CALL, bytes(buf), True)
        ms = (time.time() - t0) * 1000
        n = struct.unpack_from("<I", out, 120)[0]
        vals = [struct.unpack_from("<I", out, 124 + 4 * i)[0]
                for i in range(min(n, 10))]
        return n, vals, ms

    def close(self):
        os.close(self.fd)


def load_hdcp22(shm):
    """Key ins Shmem legen und die Phys-Adresse liefern. 0 bei Fehler."""
    try:
        data = open(HDCP22_FILE, "rb").read()
    except OSError as e:
        print("  [hdcp] %s nicht lesbar: %s" % (HDCP22_FILE, e))
        return 0
    if len(data) != HDCP22_FILE_SIZE:
        print("  [hdcp] %s hat %d Byte, erwartet %d"
              % (HDCP22_FILE, len(data), HDCP22_FILE_SIZE))
        return 0
    if data[:4] != b"\x5a\xa5\xa5\x5a":
        print("  [hdcp] Allwinner-Header fehlt (%s)" % data[:4].hex())
        return 0
    shm.write(HDCP22_OFFSET, data)
    phys = shm.phys(HDCP22_OFFSET)
    print("  [hdcp] %d Byte -> shmem+0x%x = phys 0x%08x, Aufruf meldet %d Byte"
          % (len(data), HDCP22_OFFSET, phys, HDCP22_CALL_SIZE))
    return phys


def wce_buffers(shm, w=1920, h=1080, aspect=2):
    """Drei Strukturen fuer Wce_SetWindow ablegen, Phys-Adressen liefern.

    Layout {h_start, h_size, v_start, v_size}, vier int32 -- belegt ueber
    libhaldisplay.so::THal_Vp_Wce_SetWindow @0x5B5C und die Stock-elog-Zeile
    "WCETop::SetWindow [%5d, %5d, %5d, %5d]". Das dritte Argument ist das
    Seitenverhaeltnis (2 = 16:9), NICHT low_latency -- belegt ueber
    libtvpq.so::PQOverScan::doWceSetWindow @0x375C4.
    """
    win = struct.pack("<iiii", 0, w, 0, h)
    shm.write(WCE_SRC_OFFSET, win)
    shm.write(WCE_DST_OFFSET, win)
    shm.write(WCE_ASPECT_OFFSET, struct.pack("<i", aspect))
    return (shm.phys(WCE_SRC_OFFSET),
            shm.phys(WCE_DST_OFFSET),
            shm.phys(WCE_ASPECT_OFFSET))


def build_steps(shm):
    """Die Sequenz. Jeder Eintrag: (Name, [Args], Notiz)."""
    hdcp_phys = load_hdcp22(shm)
    src, dst, asp = wce_buffers(shm)

    steps = [
        ("THal_Vp_Init", [0, 0, VP_INIT_STAGING],
         "ParaCount 3. Para[2] MUSS eine gueltige Staging-Phys sein -- 0 laesst "
         "den MIPS ein NULL-memcpy ueber 55296 Byte machen (Session Z)."),

        ("THal_Vp_RegisterSignalChangeCallback", [11],
         "ParaCount 1: nur source_id, 11 = alle Quellen. Die Callback-ID ist "
         "KEIN Argument -- sie wird ARM-seitig ueber den Namens-Hash aufgeloest."),

        ("THal_Vp_SetHDMIHotPlugByPortCallback", [1],
         "ParaCount 1: Enable-Flag, nicht die Callback-ID."),

        ("Thal_Vp_SetBacklightLevel", [0x64], "kleines 'Thal_', Vendor-Tippfehler"),
        ("THal_Vp_SetBacklightWorkMode", [0x00], ""),
        ("THal_Vp_SetTNR", [0x02], ""),
        ("THal_Vp_SetSNR", [0x01], ""),
        ("THal_Vp_SetDCI", [0x02], ""),
        ("THal_Vp_SetBlackExtension", [0x01], ""),
        ("THal_Vp_SetPictureMode", [0x01], ""),
        ("THal_Vp_SetVideoRange", [0x00], ""),

        ("THal_Vp_Wce_SetWindow", [src, dst, asp],
         "drei Shmem-Zeiger. hdmird: 'SKIPPING THIS WAS THE LVDS-ROUTING "
         "BLOCKER through Z-session'."),

        ("THal_Vp_CvbsSetPedestalMode", [0x01], ""),

        ("THal_Vp_HDMI_SetPortMap", [1, 0], "(port, port_map) -- nicht (3,0)"),
        ("THal_Vp_HDMI_SetPortMap", [2, 1], ""),
        ("THal_Vp_HDMI_SetPortMap", [3, 2], ""),

        ("THal_Vp_Wce_SetWindow", [src, dst, asp], "zweites Mal, nach der Port-Map"),

        ("THal_Vp_DisableBlackScreen", [], "ParaCount 0"),
        ("THal_Vp_TurnOnARCAudioPath", [0x01], ""),
        ("THal_Vp_SwitchARCTXPath", [0x00], ""),
    ]

    if hdcp_phys:
        steps.append(("THal_Vp_SetHDCP22Key", [hdcp_phys, HDCP22_CALL_SIZE],
                      "ParaCount 2: (phys, size). size ist 912, nicht 960."))
    else:
        print("  [hdcp] uebersprungen -- DEAD-ENDS.md: 'TMDS reaches lock "
              "without them', also kein Blocker fuer den ersten Versuch")

    steps.append(("THal_Vp_HDMI_SetHPDTimeInterval", [0xC8], "200 ms"))
    return steps


SETSOURCE = ("THal_Vp_SetSource", [3],
             "ZULETZT. Falsche Reihenfolge blockiert den einzigen BG_Thread "
             "der Firmware; Erholung nur per Stromzyklus.")


def cmd_list(a):
    shm = Shmem()
    try:
        steps = build_steps(shm)
    finally:
        shm.close()
    for i, (name, args, note) in enumerate(steps, 1):
        cid = name2id(routine_name(name, 1))
        print("%2d. %-40s 0x%08x %s" % (i, name, cid,
                                        " ".join("0x%x" % x for x in args)))
        if note:
            print("    %s" % note)
    print("--  %-40s 0x%08x %s" % (SETSOURCE[0], name2id(routine_name(SETSOURCE[0], 1)),
                                   " ".join("0x%x" % x for x in SETSOURCE[1])))
    print("    %s" % SETSOURCE[2])
    return 0


def cmd_callbacks(a):
    cc = CpuComm()
    try:
        for base in CALLBACKS:
            cid, name = cc.install(base, target_cpu=0)
            print("  install %-46s 0x%08x" % (name, cid))
    finally:
        cc.close()
    print("HINWEIS: der fd wird beim Beenden geschlossen. Fuer den Empfang von")
    print("MIPS->ARM-Callbacks muss ein Prozess /dev/cpu_comm offen halten.")
    return 0


def cmd_run(a):
    shm = Shmem()
    cc = CpuComm()
    rc = 0
    try:
        steps = build_steps(shm)
        if a.setsource:
            steps = steps + [SETSOURCE]

        lo = a.start or 1
        hi = a.end or len(steps)
        print("=== Schritte %d..%d von %d ===" % (lo, hi, len(steps)))

        for i, (name, args, note) in enumerate(steps, 1):
            if i < lo or i > hi:
                continue
            cid = name2id(routine_name(name, 1))
            argtxt = " ".join("0x%x" % x for x in args) or "(keine)"
            print("%2d. %-38s 0x%08x  %s" % (i, name, cid, argtxt))
            if a.dry_run:
                continue
            time.sleep(CALL_GAP_MS / 1000.0)
            try:
                n, vals, ms = cc.call(cid, args)
                print("      RETURN %6.1fms  nret=%d %s"
                      % (ms, n, [hex(v) for v in vals]))
            except OSError as e:
                print("      FEHLER errno=%d (%s)" % (e.errno, e.strerror))
                rc = 1
                if not a.keep_going:
                    print("      -> Abbruch. --keep-going erzwingt Weiterlaufen.")
                    break
    finally:
        cc.close()
        shm.close()
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list")
    sub.add_parser("callbacks")
    r = sub.add_parser("run")
    r.add_argument("--from", dest="start", type=int)
    r.add_argument("--to", dest="end", type=int)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--keep-going", action="store_true")
    r.add_argument("--setsource", action="store_true",
                   help="SetSource(3) anhaengen -- Firmware-Killer bei falscher Reihenfolge")
    a = ap.parse_args()
    if a.cmd == "list":
        return cmd_list(a)
    if a.cmd == "callbacks":
        return cmd_callbacks(a)
    if a.cmd == "run":
        return cmd_run(a)
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
