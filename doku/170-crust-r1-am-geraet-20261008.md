# 170 - crust als Firmware des HY310 (R1) am Gerät: Abend 1 gemessen, zwei Funde behoben (08.10.2026, 13:15)

**Kurz:** Die Gerätestufen von Abend 1 aus `arbeit/crust-release-20261007/integration/TESTPLAN.md` sind am HY310 gelaufen,
zuerst mit dem Eigentümer an der Box, ab 09:00 ohne ihn (seine Freigabe; Rückfallebene `box-hart-neustart` nach seinem Ja,
nicht gebraucht). Alle Stufen bestanden: S0a-S0d, W1, N0, A0 (R1-Abbild installiert: Kabel, Quelle, `h713-tv`, HDCP-Paar,
Ton), W2. Zwei Funde wurden gemessen, offline behoben, in ein zweites Testabbild `r1test2` gebaut, installiert und
nachgemessen. Alles liegt weiter in Kopien (Branch `versuch/crust-release`, crust `versuch/mips-drop`, TF-A
`versuch/crust-release-tfa`); `main` trägt nur diesen Text. Fortsetzung von `doku/169`. Protokoll mit allen Zeiten:
`arbeit/crust-20261007/STATE.md`; Belege `arbeit/crust-release-20261007/geraet-20261008/`.

## 1 Gemessen auf `r1test1` (crust a5723aa, TF-A 3d2992566)

- **S0a** (nur lesen): R_WDOG lesbar (CFG 1, MODE 0), PLL_DDR0 N=66 = 792 MHz wie die Formel.
- **W1** 6/6 (FEL-Bild): Reset 0,580-0,592 s nach `reboot:`/`Power down`, Ausschalten über das Gate ohne Taste.
- **N0** (Vergleichslauf alter Standby C2 auf dem alten System): bestanden.
- **A0** R1-Abbild installiert (ohne Abzug, N2-Pfad; Rückvergleich, Secure Storage unverändert, `h713_gate=0` übernommen).
  Kabel ziehen/stecken (Eigentümer): Bild jedes Mal zurück. Quelle aus/an: Konsole, dann Bild 1,5 s nach dem Einschalten.
  `h713-tv@video2` neu gestartet: Bild nach 1,4 s. **HDCP 1.4 als Paar** (zwei Warmstarts, `h713_hdcp14_wipe=1`, dann
  Default): Quelle `Desired`, dann `Enabled`; Senke 0x93 = 0x41, dann 0x45. **Ton** (ThinkPad-Mikrofon): HDMI 1 kHz -12,9 dBFS
  (Box `present=1 rate=48000`), Geräteton 500 Hz -22,3 dBFS, gemischt beide. crust in allen Schritten ohne Fehlerbit.
- **W2** 12/12 (Linux-Zeitschalter `sunxi-wdt` 16 s): Testprogramm füttert nicht mehr - Reset 16,46 s; `sysrq-c` mit
  `kernel.panic=0` - Reset 14,0-16,1 s (je nach letztem PID-1-Ping); `reboot`/`poweroff` unter Runtime-/RebootWatchdogSec
  0,58-0,60 s.
- **S0b-S0d** (zweiter Zeitschalter R_WDOG `0x07020400`): Füttern über CTRL `+0x0c = 0x14af` wirkt (60 s gefüttert, kein Reset;
  nur-Interrupt-Lauf: Auslösung nach 16,39 s); Auslösen aus Linux: Reset nach 16,40 s; Reset-Folge am Prompt 0,59 s gegen
  gestoppten und scharfen Block; CFG-Bit 8 lässt sich setzen; RTC-RC-Oszillator: RTC-Sekunde = 1,071 s; R_WDOG läuft auf dem
  Quarz. Die Vertragsseite im SRAM A2 übersteht Warmstart und R_WDOG-Reset. S0e nicht gefahren (eigenes Ja nötig).

## 2 Zwei Funde, behoben und nachgemessen

**Fund 1: „crust: error counts, MIPS frames dropped +N" bei jedem Hotplug - ein Fehlalarm.** Die Vertragsseite zeigte zu jeder
gültigen 0x16-Meldung der Anzeige-MIPS genau drei verworfene Einheiten. Die Hersteller-ARISC-Firmware liest Wörter ohne
Rahmenmarke 0xa5 außerhalb eines Rahmens und verwirft sie still (0x80c4/0x80c8); crust zählte sie als Fehler. Port und Aktion
las crust richtig. Behoben in crust `ecf2ddc` (auf a5723aa): solche Wörter werden nur aufgezeichnet (Vertragsseite K `+0x2b4`
letzter Kopf, `+0x2b8` letztes Wort, `+0x2bc` Port/Anzahl), als Fehler zählt nur, was der Blob mit ERR meldet, neu auch eine
0x16 mit Aktion außerhalb 1..3. Am Gerät (`r1test2`): 0 Warnzeilen; Kopf `0x030202a5` = **Typ 2** (wie der Blob verlangt),
3 Wörter **nach** jeder 0x16 auf Queue 1, das letzte `0x8b49f6b4`; drei `ctl replug`: je +2 Meldungen, +6 Wörter, 0 verworfen.
Den Typfilter des Blobs (0x11828) schaltet crust noch nicht ein: gemessen ist der Typ nur für 0x16, nicht für 0x17.

**Fund 2: der R_WDOG bleibt über seinen eigenen Reset scharf** (S0c: MODE 0xb1 am Prompt). Ein ausgelöstes Netz im Standby
hätte die Box alle 16 s neu gestartet. Das Gegenmittel T7 (BL31 entschärft einen scharf vorgefundenen R_WDOG) war in TF-A
schon da, aber aus, weil das Layout nicht gemessen war. TF-A `175c6948f`: T7 ist Vorgabe. Am Gerät: S0c mit GP7 - Zeile
`PSCI: R_WDOG found armed (MODE 0xb1 STA 0x1), fed and stopped: MODE 0x0`, am Prompt MODE 0; ohne GP7 (der Ernstfall) - ein
Reset, Boot durch, stabil, der Kernel meldet `TF-A: R_WDOG found armed (word 0x030100b1)`. Im R1 ohne Standby-Netz schaltet
niemand den R_WDOG scharf; für R2 ist T7 Pflicht.

## 3 Gemessen auf `r1test2` (crust ecf2ddc, TF-A 175c6948f)

Gegen `r1test1` nur TF-A und crust geändert (Bauprotokolle verglichen). Installiert ohne Abzug; **Neustart nach der
Installation ohne Stromzyklus**: Ctrl-C beendet `ums` im Installer-U-Boot, `reset` am Prompt. W1 (reboot 0,589 s, poweroff
0,591 s) und W2c (0,590/0,596 s) auf dem installierten BL31, Banner nach dem Reset geprüft; W2a 16,46 s, W2b 13,99 s.
Quelle aus/an, Replug, Ton (HDMI -12,7 dBFS, Gerät -22,3 dBFS), T7 wie oben: bestanden.

**Beobachtung, nicht behoben:** fordert die Quelle (ThinkPad, i915) HDCP 1.4 sofort beim Moduswechsel an, bleibt sie 40 s auf
`Desired` (zweimal wiederholt); eine Anforderung 2, 4 oder 6 s nach dem Einrasten steht nach 5 s auf `Enabled`. Der Empfänger
ist im ersten Augenblick nicht bereit, und i915 fragt nicht nach; crust ist nicht beteiligt (HPD bleibt oben). Mit der
Hersteller-ARISC-Firmware und mit dem Fire-TV-Stick ist das nicht gemessen.

## 4 Was offen ist

- Langlauf auf `r1test2` (Überwachung `geraet-20261008/dauerlauf/dauerlauf.sh` läuft seit 13:14).
- M1 (Strom, Messgerät), Abend 2 (Standby-Stufen V1', N1-N4, K, L, M2, D1a') mit dem Eigentümer an der Box, dann TODO 3.3.
- Einspielen in die Linie (crust-Spiegel, TF-A- und U-Boot-Fork, Serie in `main`) erst nach Abschluss von R1.
