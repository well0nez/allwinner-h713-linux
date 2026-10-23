# 184 - HY300PRO-G-EU mit geucrust2: alles, was am HY310 bestätigt ist, bis auf die Standby-Leistung (10.10.2026, 01:00-02:30)

**Kurz:** Das Testabbild `v0.0-geucrust2-TEST` (Zweig `versuch/geu-crust` `d2abfc7`: Kernel `0246`-`0248`, crust `c5b536f`,
`--standby`) lief auf Marcos HY300PRO-G-EU (Board HY200 QZ713DF A1, Variante `projector05061226`) durch die Testreihe des
HY310: MIPS-Reload, Standby mit drei Weckquellen, HDCP-1.4-Paar, HDCP 2.2, Ton nach dem Standby. Alles bestanden; die
Standby-Leistung wurde nicht gemessen (Marco: Umstecken geht heute nicht). Danach in `main`: Merge `63fd053`, crust-Spiegel
`01bdbfb` (81 Patches). Neue Funde: TODO 2.33-2.37, 5.19. Protokoll: `arbeit/crust-20261007/STATE.md` 00:4x-02:2x
(Rechneruhr); Skripte und Mitschnitte: `arbeit/geu-crust-20261009/standby/`.

## 1 Bau und Installation

- Bau `build-all.sh --board hy200-qz713df-a1 --variant projector05061226 --test-image --standby`: der erste Lauf brach in
  Schritt 6b ab - die Mesa-Stufenprüfung `find ... -exec readelf | grep -q` stirbt unter `pipefail` an SIGPIPE und meldete
  "not aarch64?" bei gutem Stand (die Zeile davor hätte ein libLLVM aus demselben Grund übersehen). Behoben mit `grep -c`
  (`d2abfc7`), weiter mit `--skip-bl31/-uboot/-kernel` (Bausteine aus demselben Lauf); der Stempel sagt deshalb
  "reproducible: no". Serie 272 Patches, Kernelbaum `eaaeba8d`, crust v0.6.82 board 3, Gates grün.
- Geprüft vor der Installation: Gerätebaum mit `panel-power-gpios` (PF6) und `panel-reset-gpios` (PH16), PF6 in der
  Pin-Tabelle, Modul mit Panel-Zyklus, `power.conf` `short = standby` (Testabbild).
- Installation `arbeit/geu-crust-20261009/geu-install2.sh`: Sicherung `/etc/h713` + Host-Schlüssel, `h713-fel`, `h713-install`
  über unser Layout ohne `--dump` (2 min schreiben), Rückvergleich: Secure Storage byte-gleich, HDCP-1.4-Satz da; Sicherung
  zurück; UMS mit Strg-C über den UART-ESP beendet (Marco: "ist dokumentiert"), `reset` - die Box startete ohne Handgriff
  (crust von BL31 gestartet, Gate "warm start", Kernel). Danach 0 fehlgeschlagene Dienste.

## 2 Die Testreihe

| # | Test | Ablauf | Ergebnis |
|---|---|---|---|
| 1 | Bild | Konsole nach dem Start | Marco: Konsole |
| 2 | MIPS-Reload 3x | `h713-mips-restart`, ThinkPad 1080p60 am Eingang | Bildpfad nach 3404 / 3390 / 3359 ms, je "panel supply cycled (300 ms off), reset pulsed"; Marco: dreimal Bild |
| 3 | Standby RTC (s1) | h713-power-Weg (`s3-act.py`, RTC 30 s) | suspends 0->1, crust "wake rtc", 29747 ms geschlafen, Bildpfad 5407 ms, "audio DSP rebuilt (attempt 1)"; Marco: dunkel, dann ThinkPad-Bild |
| 4 | Standby Taste (k1) | Power-Taste kurz, nach ~10 s wieder | "short press: standby", crust "wake key (0x95)", 14784 ms, Bildpfad 5171 ms, DSP attempt 1; Marco: dunkel mit Lüfter an, Bild und HDMI zurück |
| 5 | Fernbedienung (i2) | gekoppelt (LINKS+RECHTS), ihr Power-Druck, Wecken mit ihr | Standby über Bluetooth (`Bluetooth remote`, event2), crust "wake ir (0x9b)", 74909 ms, Bildpfad 4470 ms, DSP attempt 1; Marco: aufgewacht |
| 6 | HDCP-1.4-Paar | Boot `h713_hdcp14_wipe=1`, dann Standard; je Neuanfrage am ThinkPad | Boot 1: "sink overwritten with zeros", 0x93=0x41, `Desired` 4x; Boot 2: "1.4 key set handed to the receiver", 0x93=0x45, `Enabled` 4x |
| 6b | HDCP 1.4 nach Standby (s2) | RTC 20 s, dann Neuanfrage | Bildpfad 5384 ms, DSP **attempt 3**; ohne Neuanfrage `Desired`, mit `Enabled` 3x |
| 7 | Ton | ThinkPad 1 kHz, Amplitude 3000, 60 %, 6 s über HDMI, nach s2 | Box: audio on 48 kHz, source present, msp running, Pegel 75/76; Marco: gehört |
| 8 | HDCP 2.2 | Fire-TV-Stick, zweimal neu gesteckt | "2.2 (session stands)", authenticated, LINK 0x422=0x01; je Stecken neue Firmware-Zeile (Tick 460842 -> 556847 -> 792958); nach dem Neustecken wählte der Stick 720p60 |
| 9 | Leistung im Standby | - | **nicht gemessen** (Marco: USB/Wattmeter umstecken geht heute nicht) |

Zwei eigene Fehler dabei: Reihe 5 war zuerst falsch geplant (am HY310 war nur das Wecken per IR bestätigt, nicht der Standby
per Fernbedienung; der IR-Empfänger hat unter Linux keine Tastenbelegung, ein Druck kam gar nicht an - nach dem Koppeln ging es
über Bluetooth). Und das erste HDCP-Paar war ungleich gemessen (Boot 1 ohne, Boot 2 mit Neuanfrage) - wiederholt, beide mit.
Eine Aussage gegenüber Marco ("anderer Firmware-Stand", zur fehlenden `SKE_SEND_EKS`-Zeile) war falsch: der G-EU läuft die
`display.bin` des HY310 (`16c74a28...`); offen als TODO 2.36. Ein HDMI-Ausfall um 01:26 war der leere Laptop-Akku (Marco),
kein Befund.

## 3 Was dabei auffiel (TODO)

- **2.33** Lüfter im Standby an: `hy310-board-mgr` "fan power rail not ours, left as it is" - der G-EU-Baum gibt ihm die Schiene nicht.
- **2.34** grüner Streifen auf der Konsole, nach dem Boot links, nach dem Aufwachen rechts, geht weg (auch HY310).
- **2.35** IR-Power löst keinen Standby aus (keine Keymap); BLE gekoppelt ja.
- **2.36** HDCP-2.2-Beweis am G-EU ohne `SKE_SEND_EKS`-Zeile (Log-Stufe?).
- **2.37** msp-Neuaufbau einmal erst im 3. Versuch.
- **5.19** `boards/check.sh` meldete in `repo-neu` zwei falsche FAILs, weil dort Gerätebäume vom 05.10. (vor crust) liegen; im
  frisch gebauten Worktree grün.
- Das ThinkPad fragt HDCP nach Neustart oder Standby der Box nicht von selbst neu an (Grenze der Quelle, `docs/subsystems/hdcp.md`).

## 4 Was in `main` kam

`63fd053` Merge `versuch/geu-crust` (Tore mit 412 Installer-Tests und 56 h713-power-Tests grün): Kernel `0246`-`0248`,
`CRUST_DEFCONFIG` in `board.env`, `--standby` für `--test-image`, Mesa-Prüfung. `01bdbfb` crust-Spiegel bis `c5b536f`
(Fork-Zweig `versuch/mips-drop` vorgespult; 81 Patches auf `499a362` ergeben Baum `bba95d32ccea` = Fork-Kopf). Dazu Doku
(`mips.md` Panel-Zyklus, `arisc.md`, `standby.md`, `hdcp.md`, `known-issues.md`, Board-Seite) und TODO. Nichts gepusht;
Push-Reihenfolge TODO 1.6 (crust-Fork jetzt mit Kopf `c5b536f`).

Die Box läuft weiter `geucrust2` (WLAN `.245`, UART-ESP `<geschwaerzt 23.10.2026: Heimnetz-Adresse>`, 2001 nur lesen); der Fire-TV-Stick steckt am Eingang.
