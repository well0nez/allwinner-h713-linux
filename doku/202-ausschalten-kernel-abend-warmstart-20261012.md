# 202 - Ausschalt-Einblendung, Abendkernel (UCLAMP, BT-Flusssteuerung), Maus, und zwei dunkle Starts (11./12.10.2026, nachts)

**Kurz:** Marco nach `doku/201`: TODO bereinigen, dann 2.60, 2.59, 2.10, 2.24, 2.27, 2.38, 2.40, 2.49, 2.50, 2.51, 2.54 und 5.18
planen und umsetzen. Erledigt und in `main`: `ctl off` hält (2.27), das Land aus `wifi.env` gilt (2.24), die
**Ausschalt-Einblendung** (2.38, Variante B von drei Mockups), 2.10 und 2.50 geschlossen (Marco), 2.59 und 2.61 geparkt. Gebaut und
am G-EU installiert, **nicht** in `main`: ein Kernel mit `CONFIG_UCLAMP_TASK` (2.60), Hardware-Flusssteuerung der Bluetooth-UART
(2.49, `0256`) und R_WDOG als Info (2.40, `0257`). Die Maus der Fernbedienung ist fertig (2.51 halb). Verworfen: ein Panel mit allen
Einstellungen (2.54, Marco: "extrem unübersichtlich"). Neu: 2.63 (Warmstart, der MIPS stirbt erneut beim Routinen-Resync, Wand dunkel)
und 2.64 (ein Standby kam nicht zurück). Pakete: `arbeit/kleinkram-20261011/`, `aus-einblendung-20261011/`, `kernel-abend-20261011/`,
`hostname-20261011/`, `panel-20261011/`, Entscheidungen `arbeit/plan-abend-20261011/ENTSCHEIDUNGEN.md`.

## 1 Kleinkram (538afbf)

- **2.27:** `cmd_warp_claim` prüfte nur das Signal, nicht `POLICY_OFF`; h713-warp fragt jede Sekunde und bekam das Bild zurück. G-EU,
  Trapez `tl x 50`, `off-test.sh`: vorher ab t+2 s wieder `warped` bei `mode off`, nachher 8/8 s `console`, `ctl auto` nach 2 s
  `warped`. Ein Zusatz in h713-warp war toter Code (`exchange()` lehnt schon ab) und ist zurückgenommen, der Warp bytegleich `e65b25d5`.
- **2.24:** cfg80211 ist eingebaut und sucht `regulatory.db` bei 0,23 s, vor dem Rootfs; `iw reg set` blieb still auf `00`.
  `h713-wifi` macht `iw reg reload` davor; nach einem Neustart `country DE: DFS-ETSI` (das Land aus `wifi.env`, leer bleibt 00).

## 2 Ausschalt-Einblendung (2.38, 386ad38)

Drei Mockups mit dem echten Zeichencode (`osd-mockup`, über Fotos, mit Animation): A Leiste unten, B groß in der Mitte mit Uhrkreis,
C Ring um die Auswahl. Marco: B. Ein kurzer Druck zeigt 15 s lang einen Ring mit Sekunden, links Standby, rechts Aus; Links/Rechts
wählen, OK oder ein zweiter Druck führt aus, Zurück bricht ab, nach 15 s gilt die Wahl; Vorgabe `default = poweroff` in `power.conf`
(`short` gilt weiter als Alias). Standby nur, wo das Abbild Suspend erlaubt, `[deep]` da ist und crust bereit; sonst der Ring allein.
Ohne Bild (`ok unseen` von h713-osd) sofort wie bisher. h713-power läuft jetzt auf **jedem** Abbild. h713-osd hält jedes Bild eine
Sekunde, ein toter h713-power hinterlässt nichts.

Gemessen am G-EU: zwei Countdowns, Wahl gewechselt, zweimal Zurück (Journal), Marco "sieht gut aus"; 12 ms je Bild bei ~10 Bildern/s.
Standby gewählt + OK: die Box schlief 15,5 s - das Aufwachen scheiterte (Abschnitt 6). Nicht gemessen: das Ablaufen bis Aus.
Tests: h713-power 32 (5 neu), h713-osd 11.

## 3 Abendkernel (Zweig `versuch/kernel-abend`, am G-EU)

- **2.60:** `CONFIG_UCLAMP_TASK=y` im Defconfig, `h713-cpufreq` schreibt `sched_util_clamp_min_rt_default = 0` ("was 1024"), die
  Panfrost-IRQ-Threads bleiben SCHED_FIFO; ohne die Datei weiter `chrt` (alter Kernel). Wirkt am G-EU; die Messreihe wie m30/m31 fehlt.
- **2.49 (`0256`):** UART1 las `MCR = 0x0b`, `CPR = 0` - 8250_dw kannte weder FIFO-Größe noch Auto-Flow und machte RTS/CTS in
  Software. Kompatibel `allwinner,sun50i-h713-uart` (nur UART1) mit CPR-Wert 64-Byte-FIFO + AFCE (Stock: `sunxi,uart-fifosize = <0x40>`).
  **Erster Bau wirkungslos:** `cpr_value` gilt nur mit `.quirks = DW_UART_QUIRK_CPR_VALUE`; zweiter Bau: `MCR = 0x2b`, `AFCE = 1`.
- **2.40 (`0257`):** nach einem Aus über crust wird der Bericht des vorigen Laufs (Phase poweroff ohne Ursache) und TF-As
  "R_WDOG found armed" Info statt Warnung; `H713_PHASE_POWEROFF` im Vertrag. Nicht gemessen (braucht Aus über crust + Start).

## 4 Bluetooth-Start

Zweimal nach einem Warmstart (alter und erster neuer Kernel) beantwortete der Chip den ersten HCI-Reset 8 s lang nicht, die Unit
startete neu und hatte sofort Antwort; nach dem Kaltstart und nach dem Warmstart mit `0256` beim ersten Versuch (154 ms). Zu wenige
Starts für einen Befund (2.49).

## 5 Fernbedienung: Maus fertig, Mikrofon offen (2.51)

- **Maus:** im Mausmodus `REL_X`/`REL_Y` (~90 Berichte/s) und OK als echter Linksklick `BTN_LEFT` (btmon: Mausbericht Handle 0x38,
  Byte 0 Bit 0); außerhalb ist OK `KEY_SELECT`; die Maus-Taste selbst sendet nichts. Für einen Desktop nichts zu tun. Der erste
  Mitschnitt zeigte keinen Klick - der Ablauf, nicht der Kernel (`arbeit/maus-mitschnitt.py`, `maus-btmon-geu.snoop`).
- **Mikrofon:** beide Geräte 125 Pakete/s zu 60 Byte (die ~63/s in `doku/193` zählten die Pause mit). Kein fortlaufender Zähler, die
  4-Bit-Codes gleichverteilt: kein ATV-Voice-IMA-ADPCM (Marcos Hinweis: Google Assistant auf Stock). Byte 0 hat nur 37 Werte und
  wandert langsam. Offen; nächster Schritt: die Sprachkomponente aus dem Stock-`super` lösen.

## 6 Ein Standby kam nicht zurück (2.64)

21:24 Standby aus der Einblendung: "system suspend", 15 483 ms geschlafen, "back from system suspend", dann sofort U-Boot SPL und
"gate: a standby did not finish" - crust Phase resuming (`0x124`, Ursache 0), Linux war nicht fertig. Der Watchdog war es nicht
(`sunxi_wdt` hält ihn im Schlaf an; 30 s Standby lief am 10.10.). Keine Spur: Linux schreibt beim Aufwachen nicht auf die UART, das
Journal war flüchtig. Seitdem am G-EU dauerhaft (`h713-logs persistent`).

## 7 Dunkle Starts (2.63)

| Start | Bild | Spur |
|---|---|---|
| 21:31 Warmstart nach dem gescheiterten Standby, Abendkernel 1 | nein | keine Sperr-Meldungen, unklar |
| 21:34 Kaltstart, Abendkernel 1 | ja | - |
| 21:50 Warmstart, Abendkernel 2 | nein | cpu_comm Sperre 2 `refcnt=1 thread=0xff`, `SpinUnLock(2): no thread_id`, hdmirx "callbacks cannot be registered (-16)" 100×/s, h713-tv `/dev/video0 ... busy` dreimal, systemd gibt auf |
| 20:46 Warmstart, alter Kernel | ja | - |

Lampe an, Wand dunkel, Panel und Quelle in Ordnung (ohne HDMI ist die Konsole zu sehen). Beim Warmstart übernimmt Linux den
laufenden MIPS; das Anmelden der Routinen löst seinen Tabellen-Resync unter Sperre 2 aus, und er stirbt dabei - wie in `doku/72`.
`h713-mips-restart` von Hand holte das Bild in 3,4 s zurück. Ob UCLAMP (langsamerer Boottakt) es häufiger macht, ist nicht gemessen.

## 8 Panel (2.54) verworfen

Ein Sonnet-Agent baute nach einem Inventar alle Einstellungen ins Panel (Reiter Remote/Network/System, WLAN mit 120-s-Rückfall,
Hostname, 72 Tests). Am G-EU: Marco "extrem unübersichtlich", Debug und Expertenwerte zwischen den Alltagsreglern, Design "abgrundtief
schlecht" - sofort zurückgespielt. Die vielen Optionen sind gewollt, aber gruppiert in eigene Menüs und nur mit Mockup zuerst.
Zweig `versuch/panel-einstellungen` bleibt lokal.

## 9 Hostname je Board, G-EU verified (Zweig `versuch/hostname`)

`HOSTNAME_BOARD` (variant.env vor board.env, sonst `BOARD_ID`): `hy310`, `hy300pro` (G-EU), `hy300proplus`; install-projekt.sh schreibt
`/etc/hostname` und `/etc/hosts`, `h713-wifi` fällt auf `h713` zurück. Variante `projector05061226` ist `STATUS=verified` (Marco).
Funktion geprüft, kein Abbild damit gebaut.

## 10 Handoff (12.10.2026, ~01:30)

**`main` (nicht gepusht):** `538afbf` (2.27/2.24/TODO), `1a68349` (TODO 2.63/2.64), `386ad38` (2.38), `79784d7` (TODO 2.54) und dieser
Eintrag. **Zweige:** `versuch/kernel-abend` (0256/0257/UCLAMP, gebaut, Baum `ddb1b5fa`), `versuch/hostname`, `versuch/panel-einstellungen`
(geparkt), `versuch/warp-einpass` und `versuch/warp-konsole` (Belege).

**G-EU:** Abendkernel 2 (FIT `bf149a9f`, Module samt aic8800 bsp/fdrv), `h713-cpufreq` mit UCLAMP, h713-tv `26fa96e6`, h713-osd und
h713-power aus `386ad38`, h713-wifi mit `reg reload`, Panel wieder das alte, **Journal dauerhaft** (`/data/log`). Rückwege:
`/boot/h713-kernel.fit.alt` + `/lib/modules/6.18.38.alt` (Abendkernel 1), `/root/sicherung-{kleinkram,aus-einblendung,panel-einstellungen}/`.

**Als Nächstes (Marco):** die Warmstarts am G-EU (2.63) klären und beheben, dann committen. 2.51 Mikro und 2.54 Panel bleiben offen.

**Gelernt:** dunkle Wand erst über `h713-tv`-Status und die Konsole eingrenzen, bevor man Panel oder Quelle verdächtigt; 8250_dw nimmt
`cpr_value` nur mit dem Quirk; ein Panel ohne Mockup wird verworfen; der UART-Ringpuffer des ESP hat viele Bitfehler (lesbar mit
einem Filter auf druckbare Zeichen).
