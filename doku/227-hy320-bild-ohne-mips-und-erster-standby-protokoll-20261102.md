# 227 HY320: Bild ohne display.bin, und der erste Standby über crust - Protokoll

Datum: 02.11.2026 (Gerätezeit falsch, April 2026). Gerät: der HY320 seines Besitzers. Augen: der Besitzer. Pläne:
`DisplayStage1` (E2/E5), `CrustScope` S5-S7.

## 1 E2: U-Boot zeigt das Logo, die MIPS bleibt im Reset

Einmal-`bootcmd` (Variable `h713_e2`, vor dem Versuch gelöscht, danach `reset`): `h713_disp init 0x30 noboot logo`, 40 bzw. 60 s
stehen lassen. Konsole (h713_conlog): `MIPS held in reset (noboot); display driven by the ARM sequence alone`, `sequence complete,
LVDS FIFO status=0`, Zeitgebung latched, `display initialised from the ARM sequence alone`. Besitzer (zweiter Lauf): **das Logo
stand 60 s, normal**. display.bin wurde nie gestartet; die Daten sind die LogoRegData-Sätze des eigenen Geräts.

## 2 E5: Linux auf der Anzeige ohne MIPS

Einmal-Start eines Test-FIT (`h713-kernel-e5.fit`: der HY320-Baum mit `allwinner,handoff-state = <0x03001901 0 0>`, weil noboot
VIDEO_CTRL 0 hinterlässt), `module_blacklist=hy310_cpu_comm,sun50i_h713_hdmirx,sun50i_h713_mips,sun50i_h713_msp` (ein
`modprobe.blacklist` reichte nicht: hdmirx zog cpu_comm als Abhängigkeit nach, cpu_comm startete die MIPS selbst - "volle
Initialisierung"), h713-tv/warp/osd/desktop maskiert.

- afbd übernimmt (`adopting 1920x1080 ... source 6c100000`), fb0 auf `0x76d00000`, `0x058c0000 = 0x10000040` (RGB allein),
  CCU `0x600`/`0x60c` (MIPS-Takt) 0.
- Warnung `[CRTC:36:crtc-0] vblank wait timed out`: ohne MIPS kommt der AFBD-Vsync-Interrupt nicht (offen).
- fbcon stand auf `blank = 4` (daher zuerst schwarz). Nach `echo 0 > blank` und einem Testbild in `/dev/fb0`: Besitzer - **rot,
  grün, blau von oben, wie geschrieben**.
- Ohne afbd (auch auf der Sperrliste) blieb das U-Boot-Logo stehen; der Registervergleich mit dem afbd-Lauf unterscheidet sich
  nur in der Quelladresse des RGB-Kanals. Der Panelblock (`0x051c0100..013c`, `0x051c0000..000c`) bleibt ohne MIPS 0 - für das
  RGB-Bild allein nicht nötig.

Ergebnis: Panel und RGB-Ebene laufen vom ARM aus, ohne display.bin, ohne cpu_comm.

## 3 Neues Abbild v0.97.2-beta mit `--standby`

Gebaut (`release/build-all.sh --board hy320 --test-image --standby --profile media,desktop`, 23 min), per FEL von pve installiert
(`h713-fel`, Secure Storage byteweise gleich). Netz-Ein: **mit dem A-A-Kabel gesteckt reagierte die Taste in der roten Pforte
nicht**; ohne USB-Kabel startete die Taste. Danach: `crust is running ..., image kept`, `mem_sleep s2idle [deep]`, `ready=1`,
EDID/HPD Port 1, Xbox 1080p60, HDCP 2.2.

## 4 Erster Standby (RTC, 30 s)

`systemctl suspend` mit Weckzeit +30 s: Besitzer - aus, nach etwa 30 s wieder da, **Xbox-Bild zurück**. Journal: `fan power rail
on`, `aicwf_sdio_resume`, `h713-mode: the display MIPS is parked, h713-mips-restart`, `cpu_comm: resumed`. **Aber das WLAN-AP
"h713" war danach weg** (pve sah die SSID nicht mehr, hostapd lief weiter, Station nach 60 s "disassociated due to inactivity").
Und `sun50i-h713-msp: the DSP lost its power in the sleep and is not rebuilt (rebuild_after_sleep=0)`. Nur ein Zyklus.
Wiederhergestellt mit langem Tastendruck (Aus über crust: nächster Start `powered off through crust ... cycle 1`) und Taste.

## 5 Offen

WLAN nach dem Standby (nur HY320? auf dem HY310/G-EU überlebt es seit `doku/171`), Ton nach dem Standby, Taste in der Pforte bei
gestecktem USB, Vsync ohne MIPS, Wake über Taste/Fernbedienung, Zyklen, Brummen im Standby.

## 6 Nachtrag: vier weitere Standbys, WLAN-Abhilfe

- Zweiter Standby (Skript, 30 s RTC): nach dem Aufwachen `wlan0` DOWN, `hostapd_cli`: keine Steuerdatei; `systemctl restart
  h713-wifi` -> AP sofort zurück, pve wieder verbunden.
- `h713-mode sleep-post` startet h713-wifi neu, wenn eine wlan-Schnittstelle nicht `operstate up` ist. Eine erste Fassung prüfte
  `IFF_UP` - falsch: Messung (Standby 5, Sekundenprotokoll über den Schlaf) zeigt nach dem Aufwachen `operstate down` bei
  `flags 0x1003` und laufendem hostapd. Test `test_mode.py` deckt down/up/aus ab.
- Standby 3: Bild zurück, WLAN weg (die IFF_UP-Fassung griff nicht). Standby 4: crust meldet beim nächsten Start "phase released,
  step 0x619, 205 ms in the phase" - die CPUs wurden freigegeben, Linux kam nicht zurück. Standby 5: Aufwachen, `h713-mips-restart`
  beginnt, 2 s später Neustart (`standby: a reset until the core runs again ends in the power gate`) -> U-Boot-Logo -> Pforte
  (rote LED). Besitzer: "Logo, dann aus".
- Bilanz 5 Standbys: 3 mit Bild zurück, 1 Hänger nach der Freigabe, 1 Rücksetzung im MIPS-Neustart. Der MIPS-Neustart auf dem HY320
  (`CrustScope` Lücke 5, S6) ist das nächste Ziel; die WLAN-Abhilfe ist nach einem gelungenen Aufwachen noch nicht gemessen.

## 7 Nachtrag: MIPS-Neustart wach, Standby-Schleife mit dauerhaftem Journal

- `h713-mips-restart` 3x im Wachbetrieb: alle `rc=0`, Bild nach 4.3/4.5/5.4 s, Xbox 1080p60 zurück. `0x051c0014 = 0x18000005`,
  `0x051c0028 = 0x1f300030` vor und nach einem Neustart - die DE-Endwörter überleben ihn (`CrustScope` Lücke 5 geschlossen).
- `h713-logs persistent`, dann 5 Zyklen (RTC 20 s, 45 s wach): Zyklus 1 und 2 gut - Bild zurück, `h713-mode: after the sleep:
  wlan0 is down, h713-wifi restarted`, danach `wlan=up` (die WLAN-Abhilfe wirkt). Zyklus 3: das Journal endet bei `PM: suspend
  entry (deep)`, die Box stand danach in der Pforte (rote LED), crust meldete beim nächsten Start keinen Vorlauf.
- Bilanz bis hier: 8 Standbys, 5 gut, 3 verloren (einmal Hänger nach der Freigabe, einmal Rücksetzung im MIPS-Neustart, einmal
  ohne Spur nach dem Eintritt). crust bleibt auf dem HY320 experimentell; die Hersteller-Firmware ist der sichere Weg
  (`h713-arisc set vendor`).

## 8 Stand am Gerät (für die Wiederaufnahme)

- Schleife 2 (10 Zyklen): schon Zyklus 1 verloren (Journal endet bei `PM: suspend entry (deep)`, kein crust-Vorlauf beim nächsten
  Start - der Fehler liegt vor der Übergabe an crust oder löscht dessen Seite). Bilanz 5 von 9.
- Danach: Kern mit `KERNEL_CONFIG=pstore` (neues Fragment `patches/kernel/board/pstore.config`) als `/boot/h713-kernel.fit`,
  der Release-Kern liegt als `/boot/h713-kernel-release.fit`; `bootargs_base` trägt `ramoops.mem_address=0x46000000
  ramoops.mem_size=0x100000 ramoops.console_size=0x80000 ramoops.record_size=0x20000 no_console_suspend`. Schleife 3 lief an
  (`dmesg -n 8`, `pm_debug_messages 1` kamen nicht mehr an) und ging früh verloren; Auswertung: `/sys/fs/pstore` nach dem Start.
- Zurück zum Release: `/boot/h713-kernel-release.fit` nach `/boot/h713-kernel.fit`, die ramoops-Wörter aus `bootargs_base`.
- Schleife 3: Zyklus 1 verloren, `/sys/fs/pstore` danach leer - der Fehlerweg endet in der Pforte, die die Schienen abschaltet,
  und der RAM-Inhalt ist weg. Deshalb jetzt `h713_gate=0` (ein Fehler startet gleich durch, pstore bleibt) und Schleife 4
  (`sbloop4`, 10 Zyklen, `/data/log/sbloop.log`). Nach der Auswertung `fw_setenv h713_gate 1` zurück.

## 9 Ursache eingegrenzt: der MIPS-Neustart nach dem Aufwachen (03.11.2026)

Alle Spuren auf dem Gerät unter `/data/log/standby-20261103/`.

- Release-Kern, 15 Versuche mit `h713_gate=0`: 2 gut, 13 verloren (`sbsoak.log`). Jeder Verlust ist ein Hänger, kein
  Neustart von selbst: mit abgeschaltetem Hardware-Watchdog (`RuntimeWatchdogSec=off`) stand die Box nach dem Aufwachen
  schwarz, Fernbedienung ohne Wirkung, kein Ping - die "Neustarts" bisher waren systemds 16-s-Watchdog.
- crust ist es nicht: der Vorlauf nach einem Verlust sagt Phase `released` (step 0x619) - der Kern hatte die Bestätigung
  geschrieben, also PM_POST_SUSPEND erreicht. Kalt- statt Warmstart vor dem Versuch: ebenso verloren.
- `pm_test` devices/platform/processors/core: alle rc=0 (`pmt*.log`). Ein späterer "Hänger" nach `devices` war nur das
  WLAN (das Skript startete h713-wifi nicht neu; der Besitzer sah den Launcher) - Lehre: Erreichbarkeit ist kein Lebenszeichen.
- Ein echter Schlaf über `/sys/power/state` ohne die systemd-Haken (`sbtrace.sh`, Zeile für Zeile mit `sync`): **8 von 8 gut**,
  die MIPS bleibt geparkt. Über `systemctl suspend` (dann startet `h713-sleep-post` `h713-mips-restart`): **5 von 6 verloren**;
  die drei Spuren mit Kernlog enden alle in `restart from parked`, mitten in den Schritten auf `0x0200160c` (Freigabe der MIPS).
- Registervergleich wach (MIPS läuft) gegen geparkt nach dem Schlaf (`dsnap*.txt`: CCU, R_PRCM, DRAM COM/MC, SYS_CFG, PPU,
  TV-Top): verschieden nur MIPS-Wörter, CCU-Laufzeitzustände (PLL_CPU, mmc2) und der TV-Top - `+0/+4/+8` (stellt der Neustart
  wieder her) und `+0x1c` 1 -> 0. `+0x1c = 1` von Hand vor dem Neustart: hängt genauso (`rs1c.log`). Anders als beim HY310
  (doku/172) bleibt DRAM-COM `+0x004` gleich.
- Stand: auf dem HY320 hängt der Neustart von display.bin aus der Standby-Parkposition das SoC auf, die Ursache unter dem
  TV-Top ist offen. Entscheidung (lead, 03.11.): nicht weiter verfolgen - der Clean-Room-Treiber (`docs/cleanroom.md`) startet
  display.bin nicht, damit entfällt der Neustart.
- Bis dahin am Gerät: Standby aus. `/etc/systemd/sleep.conf.d/10-h713.conf` sagt `AllowSuspend=no` (das Original liegt als
  `/etc/h713/10-h713.conf.with-standby`; zurück: zurückkopieren). Gemessen: `systemctl suspend` -> "Sleep verb 'suspend' is
  disabled by config", `h713-power can-standby` -> nein, die Taste schaltet aus. `h713_gate=1` wieder gesetzt, `sbsoak.service`
  entfernt.
