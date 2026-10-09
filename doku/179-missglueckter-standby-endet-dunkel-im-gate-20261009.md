# 179 - Ein missglückter Standby endet dunkel im Gate (TODO 2.30) (09.10.2026, 18:40)

**Kurz:** Bisher lief jeder Reset aus einem Standby, der nicht fertig wurde, als Warmstart am Gate vorbei: Die Box ging
von selbst wieder an, Lampe an. Marco wollte es dunkel, aber ausgeschaltet und nicht hängend. Jetzt setzt der Treiber
der Anzeige-MIPS (`sun50i-h713-mips`, Kernel `0245`) das Gate-Wort GP5 vom Beginn des Standbys an auf "STBY" und erst
wieder auf "RUN1", wenn der Kern nach dem Aufwachen läuft. Jeder Reset dazwischen landet in U-Boots Gate, wie nach
einem Ausschalten. Am HY310 mit absichtlich ausgelösten Hängern gemessen: 4 von 4. Alles in einer Kopie (Paket
`arbeit/standby-gate-20261009/`, Zweig `versuch/standby-gate`, Box mit Sicherung `/root/sicherung-standby-gate/`).

## 1 Der Weg

- U-Boot schreibt bei jedem Boot "RUN1" nach GP5 (`0x07090114`) und startet bei einem Reset, der "RUN1" findet,
  durch; BL31 schreibt beim Ausschalten "GATE". Jedes andere Wort schickt U-Boot schon heute ins Gate (Code gelesen,
  `board/sunxi/board.c`). U-Boot muss also nicht geändert werden; ein Patch, der dem Wort eine eigene Zeile gibt
  ("a standby did not finish"), liegt im Paket und kommt mit 1.1a.
- Der Treiber hält GP5 als vierte reg. Ein PM-Notifier macht bei PM_SUSPEND_PREPARE aus "RUN1" "STBY" - vor dem
  noirq-Fenster, in dem C1 hing (`doku/173`). Zurück auf "RUN1": wenn der Kern nach dem Start aus dem Park "ready"
  meldet, am Ende eines Schlafs, der nichts geparkt hat, und vor einem `reboot` aus Linux (Reboot-Notifier, ohne
  Sperre). Das Wort entscheidet, kein Merker: nur "RUN1" wird "STBY", nur "STBY" wird wieder "RUN1".
- BL31 nicht: PSCI SYSTEM_SUSPEND kommt erst nach dem noirq-Fenster, für C1 zu spät.

## 2 Gemessen (Box r2test4 mit neuem DTB im FIT und dem Modul in `updates/`, `h713_gate=1` auf Marcos Freigabe)

Basis: Kernel aus `main` neu gebaut, Baum `76289cdd` wie r2test4, die FIT bitgleich mit der auf der Box (`f9295061`);
Modul und DTB daraus, W=1 ohne Warnung, der DTB weicht nur in der reg-Zeile des MIPS-Knotens ab. Testmodul
`gate-haenger` (nur Test): hängt syscore suspend oder resume mit Absicht. UART nur gelesen.

| Lauf | Ablauf | Ergebnis |
|---|---|---|
| g1 Kontrolle | Standby über h713-power, RTC 20 s | "STBY" beim Einschlafen, "standby over" ("RUN1") nach "ready"; Bild nach 5,3 s, Audio-DSP im 1. Versuch |
| g4 reboot | h713-power gestoppt, `systemctl suspend`, RTC 20 s: Kern bleibt geparkt, GP5 "STBY"; dann `systemctl reboot` | U-Boot "gate: warm start (GP5 52554e31), booting" |
| g2 Hänger beim Einschlafen | syscore suspend hängt | crust-Reset nach 15000 ms (err 0x200, path 0x102), U-Boot "gate: cold start (GP5 53544259)", dunkel; Marcos Taste -> bootet |
| g3 Hänger beim Aufwachen | "back from system suspend", dann hängt syscore resume | crust-Reset nach 60000 ms, Gate wie g2, dunkel; Marcos Taste -> bootet |

Die "cold start"-Zeile ist das alte U-Boot auf der Box; das Wort `53544259` ist "STBY".

## 3 Was bleibt

- Nicht gefangen: hängt crust selbst im Schlaf, setzt nur R_WDOG zurück, und das ist im Schlaf noch nicht scharf (CR-1).
- Ein Reset, während der Kern nach dem Aufwachen startet (der alte Stufe-3-Hänger), ist vom Code her abgedeckt - das
  Wort steht bis "ready" auf "STBY" -, aber nicht provoziert.
- Mit `h713_gate=0` startet die Box nach einem missglückten Standby weiter durch, wie bei allem anderen.
- Mit 1.1a: die U-Boot-Zeile in den Fork (Patch gebaut, `board.o`), und der Kommentar in TF-A `sunxi_native_pm.c`
  ("the boot loader finds RUN1") stimmt bei einem verweigerten Standby nicht mehr.
- Lauf g4 hat Marco nicht verlangt; er prüft nur, dass ein gewolltes `reboot` trotz "STBY" durchstartet.
