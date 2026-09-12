# Regeln für die Pakete G1–G3 (Plan 103, Einschalt-Gate)

- **Nur lesen** in `mainline/external/u-boot`, `mainline/external/arm-trusted-firmware`, `mainline/build/linux-6.18.38-d5fd82a7*`, `mainline/patches`, `uboot-h713`, `doku`.
- **Schreiben nur** im eigenen Paketordner `analyse/boot/arbeit/<paket>/` (Kopien unter `kopie/` ändern) und den eigenen Bericht
  `doku/nachtlog/S3x-….md`. Kein Board, kein Netz, kein Bau, kein `git` in fremden Bäumen.
- Ergebnis je Paket: `patches/*.patch` (unified diff, `-p1`, Pfade wie im Originalbaum, Kopie gegen Original mit `diff -u`), Bericht, und eine
  Liste offener Annahmen. Der Patch muss ohne Nacharbeit anwendbar sein; im Zweifel klein und klar statt vollständig und riskant.
- Sprache der Berichte: Deutsch. Code-Kommentare: Englisch, knapp, sagen *warum*.
- Zeitbudget: 45 min. Danach abbrechen und Stand mit Restliste abgeben.

## Gemessene Fakten (08.09. 23:20–00:20, am Gerät, gelten verbindlich)

- Taste: **PL4, aktiv-low, externer Pull-up**; Ruhe 1, gedrückt 0. Kein interner Pull nötig. Entprellung 50 ms (Stock).
- LED: **folgt PB5** (`fan-bl-power`): PB5 = 1 → blau, PB5 = 0 → rot. PL0/PL1 wirkungslos. Es gibt **keinen** eigenen LED-Baustein zu treiben.
- Lüfter/Backlight PB5 und USB-VBUS PL3 setzt heute `board_late_init` → `h713_poweron_lines()` (`board/sunxi/board.c:994-1034`) bedingungslos.
  Vor `board_late_init` sind beide 0 (Gerät dunkel und leise).
- RTC-GP-Register: `0x07090100 + 4*n`. **GP5 = `0x07090114` ist frei** und für das Gate reserviert. Nach Netz-aus/an lesen alle GP 0; ein Wert überlebt
  `reset` (U-Boot) und `reboot` (Linux, PSCI). GP7 = Fastboot-Magic (PREBOOT), GP3 wird vom ARISC-Treiber beschrieben (0xb00f), GP2/GP6 Stock.
- Flag-Protokoll: `0` = Kaltstart → Gate; `0x52554E31` „RUN1" = läuft/warmer Neustart → direkt booten; `0x47415445` „GATE" = Ausschaltwunsch → Gate.
- R_PIO `0x07022000`: neues Registerlayout (CFG0 0x00, DAT 0x10, DRV0..3 0x14..0x20, PULL0 0x24). U-Boot kennt die Pins als „PL4", „PB5" per DM
  (`dm_gpio_lookup_name`, Muster `board.c:1010-1024`).
- Kein PMIC, kein echtes Aus: TF-A `sunxi_power_down()` kehrt ohne AXP zurück, `sunxi_system_off()` parkt nur die Kerne.
