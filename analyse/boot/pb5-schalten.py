#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""pb5-schalten.py -- die geteilte Schiene PB5 (Luefter + Lampe) von Hand schalten.

    pb5-schalten.py lesen
    pb5-schalten.py aus
    pb5-schalten.py an

WOFUER: den Notaus bei Luefterstillstand pruefen (Patch 0159). PB5 aus -> der
Tacho meldet 0 U/min -> nach fg-warn-cnt (8) Sekunden ruft der Treiber
orderly_poweroff(). Das ist der einzige Weg, den Stillstand ohne Schraubendreher
herzustellen, weil die Leitung an einem gpio-hog haengt und Userspace sie
darum nicht ueber gpioset anfordern kann.

WARUM /dev/mem UND NICHT gpioset: der Hog haelt die Leitung; jede saubere
Anforderung scheitert mit -EBUSY. Wir schreiben deshalb einmal am Treiber vorbei
ins Datenregister. Das ist fuer eine Messung in Ordnung und fuer alles andere
nicht -- genau diese Praxis hat Patch 0141 aus dem Treiber entfernt.

REGISTER (H713, D1-artiges Layout mit 0x30 Bankabstand):
    PIO-Basis   0x02000000
    Bank B      Index 1  ->  0x02000000 + 1*0x30 = 0x02000030
    DAT         +0x10    ->  0x02000040, Bit 5 = PB5

VORSICHT: PB5 schaltet Luefter UND Lampe zusammen. "aus" macht das Bild dunkel;
das ist erwartet. Wer nur messen und nicht abschalten will, nimmt vorher
    echo 0 > /sys/module/hy310_board_mgr/parameters/fan_stall_shutdown
und danach wieder 1.
"""
import mmap, os, sys

PIO = 0x02000000
BANK_B = PIO + 1 * 0x30
DAT = BANK_B + 0x10
BIT = 1 << 5
SEITE = 0x1000


def zugriff():
    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    basis = DAT & ~(SEITE - 1)
    m = mmap.mmap(fd, SEITE, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=basis)
    return fd, m, DAT - basis


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("lesen", "aus", "an"):
        print(__doc__.strip()); return 2
    if os.geteuid() != 0:
        print("root noetig (/dev/mem)"); return 2
    fd, m, off = zugriff()
    try:
        alt = int.from_bytes(m[off:off + 4], "little")
        if sys.argv[1] == "lesen":
            print("DAT 0x%08x = 0x%08x, PB5 = %d" % (DAT, alt, 1 if alt & BIT else 0))
            return 0
        neu = (alt | BIT) if sys.argv[1] == "an" else (alt & ~BIT)
        m[off:off + 4] = neu.to_bytes(4, "little")
        zurueck = int.from_bytes(m[off:off + 4], "little")
        print("DAT 0x%08x: 0x%08x -> 0x%08x (PB5 %d -> %d)"
              % (DAT, alt, zurueck, 1 if alt & BIT else 0, 1 if zurueck & BIT else 0))
        return 0 if (zurueck & BIT) == (neu & BIT) else 1
    finally:
        m.close(); os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
