# 168 - Tiefschlaf (Stufe C) vorbereitet, nicht gelaufen (07.10.2026, 14:45)

**Kurz:** Bevor crusts Tiefschlaf zum ersten Mal auf den HY310 geht, hat eine Bereitschaftsprüfung (nur gelesen) zwei
Schritte des aus dem Hersteller-Blob portierten Tiefschlafs als zu riskant für einen ersten Lauf eingestuft. Beide sind
jetzt abschaltbar (crust 0034), ein erster Lauf D1a ohne sie ist gebaut. Gelaufen ist nichts; D1a braucht Marco an der
Box. Nebenbefund: dass der Watchdog die Box mitten im Schlaf sauber zurücksetzt, ist auch für die Self-Refresh-Läufe
nicht gemessen. Fortsetzung von `doku/167`. Belege: `arbeit/crust-20261007/BERICHT.md` §15 (Nachträge 13:50 und 13:58),
`PRUEFUNG4-20261007.md`.

## 1 Gemessen (nur gelesen, Normalbetrieb)

- RTC: `LOSC_CTRL = 0x00008000` - LOSC läuft vom internen RC, der 32-kHz-Quarz ist aus, der Auto-Switch umgangen;
  `LOSC_AUTO_SWT_STA = 0`. Der RTC-Knoten im DT hat kein `clocks`. Ob ein Quarz bestückt ist: unbekannt.
- R_PRCM `0x244 = 0x00040005`: Bit 2 (`CRYSTAL_EN`) gesetzt - der 24-MHz-Takt kann über die Pads der PLL-Domäne
  kommen.

## 2 Was die Prüfung fand

- **VDD_SYS-Schritt** (Blob 0xdea8/0xe3a8): setzt den Hauptbereich zurück - CCU-Gates, Pin-Funktionen, UART0, die
  Msgbox und den SoC-Watchdog, das Netz der Testläufe. Mainline-Linux stellt davon nichts wieder her. Mit ihm gäbe es im
  Schlaf und danach kein Netz, und eMMC und WLAN wären nach dem Aufwachen wahrscheinlich tot.
- **PLL-LDO aus** (0xddbc/0xddec): mit `CRYSTAL_EN` könnte der 24-MHz-Takt mit dem LDO wegfallen; dann stünden crust
  und alle Weckquellen. Upstream-crust schaltet diesen Weg vorher ab.
- **LOSC** (crust 0033, schon vorher): der Blob schaltete beim Aufwachen den Quarz ein und wählte ihn; crust stellt
  jetzt den Zustand von vor dem Schlaf wieder her.
- **Watchdog im Schlaf:** gemessen ist nur, dass er durch einen leichten Standby weiterzählt. Ein Reset mitten im Schlaf
  wurde nie ausgelöst.

## 3 Vorbereitet

- crust 0034: Schalter für beide Schritte (Standard an), Build-Wort Bit 27/28, Bau D1a mit beiden aus. Spurvergleich
  gegen den Blob: D1a verliert genau die LDO- und VDD_SYS-Zugriffe, sonst nichts.
- Testskript für D1a: liest den Watchdog nach dem Aufwachen und schaltet ihn neu scharf, lehnt Weck-Timer über 8 s ab,
  zieht einen Lese-Abzug der Takt- und Watchdog-Register vor und nach dem Schlaf.

## 4 Offen

- Lauf **V1** (Self-Refresh mit 20-s-Timer unter dem 16-s-Watchdog, mit Marco): misst, ob ein Reset im Schlaf sauber
  bootet.
- Lauf **D1a** (mit Marco an der Box), danach schrittweise LDO und VDD_SYS - letzteres erst, wenn jemand den
  Hauptbereich wiederherstellt.
- Strom ist in keiner Stufe gemessen.
