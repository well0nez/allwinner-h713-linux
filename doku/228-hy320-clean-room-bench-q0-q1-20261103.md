# 228 HY320: Clean-Room-Bench, Q0 und Q1 - Protokoll

Datum: 03.11.2026 (Gerätezeit falsch, April 2026). Gerät: der HY320 des Besitzers. Augen: **keine** - der Besitzer war
nicht da, alles über Registerlesungen und Logs. Rolle: Spezifikationsseite des Clean-Room-Prozesses
(`docs/cleanroom.md`); Fragen aus `/srv/h713/cleanroom-held/90-open-questions.md` Q0, Q1. Werkzeuge und Rohlogs:
`analyse/cleanroom-bench-20261103/` (Spezifikationsseite, gehen nicht über die Wand). Ergebnis in der Spezifikation:
`cleanroom-h713` Commit `17108b6` (00 §3.1, 10 §6.1, 20 S1/§5.1/§6, 95 §1.1).

## 1 Sicherer Bench-Boot ohne Besitzer

- Einmal-Schalter wie bei E2/E5 (`doku/227` §1-2): `bootcmd` einmalig umhüllt - `if test -n "${h713_bench}"; then
  setenv h713_bench; saveenv; run bench_boot; fi;` vor dem unveränderten Normal-`bootcmd`. `bench_boot`: `wdt dev
  watchdog@2051000; wdt start 16000; h713_disp init ${h713_project} noboot logo; h713_conlog 0x45000000; mmc dev 1; mmc
  write 0x45000000 0x2800 0x400; run bench_hang; run bench_kernel; reset`. `bench_kernel`: der vorhandene
  `/boot/h713-kernel.fit` mit `module_blacklist=hy310_cpu_comm,sun50i_h713_hdmirx,sun50i_h713_mips,sun50i_h713_msp,sun50i_h713_afbd`,
  `systemd.mask=` für h713-tv@video1, warp, osd, desktop, keystone-auto, `consoleblank=0`. Kein neuer Kern, kein
  Test-FIT (afbd steht mit auf der Liste, also braucht es kein `handoff-state`; das U-Boot-Logo bleibt auf Kanal 2).
- U-Boots `wdt start` läuft hier **ohne Bedienung** (`CONFIG_WATCHDOG` aus): die Konsole sagt `WDT: Started
  watchdog@2051000 without servicing (16s timeout)`. Linux: `sunxi-wdt` hält ihn bei 0.145 s an, systemd startet ihn bei
  0.79 s wieder (16 s, `10-h713-watchdog.conf`). Lücke 0.65 s ohne Netz, ohne Anzeigezugriff.
- **H1** (U-Boot-Hänger): `bench_hang = sleep 60`. Nach 52 s war die Box im **Normalboot** zurück (Normal-Kommandozeile,
  `h713_bench` leer); das conlog auf LBA 0x2800 zeigt Watchdog gestartet, noboot-Initialisierung fertig - also kam
  der Reset im `sleep 60`. Gate-Wort danach `RUN1`.
- **H2** (Kernel tot): im Bench-Linux `echo 0 > /proc/sys/kernel/panic`, dann `sysrq c`. 41 s später im Normalboot
  zurück (normaler Start ~25 s). Damit ist der Watchdog-Weg für Busshänger belegt.
- Funde dabei:
  - Vor der Serie stand GP5 (`0x07090114`) auf **`STBY`** - ein `sbtrace.sh full` (Dienst `sbtq2`, aus der
    Standby-Untersuchung `doku/227` §9) hatte um 61 s nach dem Start direkt über `/sys/power/state` geschlafen, die MIPS
    blieb geparkt, das Wort blieb `STBY`. Ein Watchdog-Reset in diesem Zustand hätte im dunklen Gate geendet. Ein
    `systemctl reboot` schreibt `RUN1` (Reboot-Notifier im MIPS-Treiber) - danach war es sauber. Regel in 95 §1.1:
    vor riskanten Läufen GP5 = `RUN1` prüfen.
  - `fw_setenv -s` von libubootenv will `key=value`; eine Datei im Format `key value` legt eine Variable mit dem Namen bis
    zum ersten `=` im Wert an (hier: `bench_kernel if ext4load ... loglevel`). Gelöscht. Werte jetzt einzeln mit
    `fw_setenv name "wert"`.
  - U-Boots `saveenv` im Bench-Pfad schreibt Laufzeitvariablen mit (`fdtcontroladdr`, `mmc_bootdev`, `serial#`, und
    `fdtfile` ändert sich von `allwinner/allwinner/sun50i-h713-hy320.dtb` auf `allwinner/sun50i-h713-hy320.dtb`). Am Ende
    alles gegen den Abzug `/data/bench/env-before-20261103.txt` zurückgesetzt: `diff` leer.

## 2 Q0: Lesbarkeit unter dem Bench-Boot

Lauf `q0.py` (vor jedem ersten Zugriff Logzeile mit fsync auf `/data/bench`): **kein Hänger**. CCU-Anzeigewörter und
DTOP wie im Normalboot. PROC, SCL, BORDER, NRC, DEI lesen Resetwerte (meist 0), SCL komplett 0 (alle vier Kopien),
DEI komplett 0, NRC fast 0, `0x05001000..15fc` alles `0xffffffff`. Schreib/Lese-Probe (`q0b.py`): `0x05180034`,
`0x0518003c`, `0x05140104`, `0x05000224`, `0x05200004`, `0x05200018` lesen den geschriebenen Wert, `0x0520000c` ist
nur lesbar. Gamma-Ports: je Port eine Konstante (`0x4000`, `0x0076275f`, `0x00fe6fe3`). PROC_LOCK/PNL_LOCK gleich
belegt, `fe08 = 0x08c9112f`. TVTOP `0x00111111/0x01111117/0x404` (normal `0x504`), CAP `0x06940000 = 1`,
`0x06940400 = 0`. PNL-Zeilenzähler `0x051c0174` = 0 und steht; Histogramm eingefroren (ein Fach, 99313). Laufend:
TCON `+0`, SCANOUT `0x184`/`0x30c`, PNL `0x37c`, PROC_LOCK `fe68`.

## 3 Q1: Kanal 0 ohne Firmware

Bild: NV12 1920x1080 bei `0x4c000000`/`0x4c1fa400` (im `framebuf`-Reservat, das ohne MIPS niemand benutzt; der
HDMI-Ring liegt im Normalboot bei `0x4c3ef000..`), per `/dev/mem` beschrieben. `q1.py`:

- Q1a wie 90 beschrieben (T1-Werte, Reihenfolge L4 ohne Chroma-Gain, `VCH_CTRL 0x03000013`, Latch): `VCH_LATCH` 1 bei
  20/50/100 ms und dauerhaft, `VCH_ADDR_LATCH` 1, ARMED 0/0, `0x0c0` = 0, Zeilenzähler 0. Schritt 4 (`PNL_SEL
  0x39000000`, MIX `0x40`) ändert nichts. Q1b (`VCH_GATE 0x11`) ebenso. Q1c: 0 Vsyncs/s in beiden Zuständen.
- Weiter mit den Init-Tabellen der eigenen `database.TSE` (mit `tools/tse_dump.py` ausgelesen, `inittables.json`):
  `INIT_VPANEL` (nichts), `INIT_VPROC` -> **`0x0c0` Bit 0 kommt**, 16/s; `INIT_VNR` -> **PNL-Zeilenzähler läuft**;
  `INIT_VDEINT`; `DBUS_MP_RST_PROJECTOR`. `fe08` beider Lock-Blöcke `0x08c9112f` -> `0x04640897`: Vsync alle 15.26 ms
  (65.5 Hz, Panel 60 Hz).
- Latch trotzdem nie verbraucht. Zusätzlich ohne Wirkung: NRC-Lesegeometrie und `0x05000040` Bit 25 aus dem
  Normalboot, `SCAN_IRQ_EN = 1`, PROC_LOCK `fe0c..fe50` und `fe30 = 0x10000104`, TVTOP `+8 = 0x504`, `VCH_CTRL` mit
  Bit 31 (liest `0x83000013`, zurückgesetzt), Latches neu gepulst. Latches lassen sich mit 0 nicht zurücknehmen.
- Kein Hinweis auf Abholung: Histogramm nach `INIT_VPANEL` ein Fach (`0x03f4 = 896661`), unverändert bei weiß ->
  schwarz -> grau -> weiß im DRAM; PROC-Sonde `0x05140600 = 0x0fff0000` fest; `0x320/0x324` = 0.
- Vergleich Normalboot (`snap.py`, nur lesen; `h713-tv ctl bare 120` gegen die Abdeckseite): HDMI-Ring NV16,
  `VCH_GATE` **`0x1`** (nicht `0x11`), Slots rotieren (drei Puffer), ARMED `0x6a/0x4c`, `0x310` Bit 21 kippt,
  `0x0c4 = 1`, PROC_LOCK `fe64` (Eingangs-Vsync-Stempel) läuft - auf der Bench steht er. Abdeckseite: `VCH_CTRL
  0x03000200`, 720x240-Geometrie. SCL 1:1 auf dem HY320 erstmals gelesen (20 S1).

Ergebnis Q1: **nein** - ohne Firmware übernimmt Kanal 0 seine Konfiguration nicht, auch mit allen fünf Init-Tabellen
und laufendem Video-Vsync. Vermutung (`[INFERENCE]`): der Bildstart von Kanal 0 hängt am Eingangstakt der
Video-Pipeline (Capture-Seite), den es für eine DRAM-Quelle ohne Firmware erst noch zu finden gilt. Q2 nicht begonnen
(setzt Q1 voraus). Nächste Kandidaten: die übrigen PROC-Steuerwörter des Normalboot-Abzugs (`0x05140008..0058`,
`0x05140100..01c0`) und die Capture-Seite (Q6, Leistungsdomäne - eigenes Experiment).

## 4 Stand am Gerät

Normalboot (`uptime` frisch, normale Kommandozeile), `h713-tv ctl status` ok, `fw_printenv` gleich dem Abzug vor der
Serie (kein `h713_bench`, keine `bench_*`), GP5 `RUN1`, MIPS läuft (`0x0200160c = 0x00070001`). Auf dem Gerät liegen
die Werkzeuge und Logs unter `/data/bench/`.

## 5 Runde 2: was Kanal 0 ohne Firmware einrasten lässt

Auftrag des Leads (WALL `f829da8`): die Eingangstakt-Vermutung prüfen und den Latch zum Einrasten bringen. Ergebnis in
der Spezifikation: `cleanroom-h713` `1423868` (10 §6.2, neues Dokument 12, 00 §2, 20 §5.1).

- **Normalboot, nur lesen** (`mon.py`, `snap.py` jetzt mit dem ganzen INCAP `0x06940000..0ffc`):
  - Mit HDMI (`h713-tv ctl bare 600`): Kanal 0 läuft, `VCH_ADDR_LATCH` pro Bild, `VCH_LATCH` bleibt 0 (wird gar nicht
    gepulst), `0x310` zählt `0x008/9/a/b00210`, `fe64` läuft.
  - HPD weg ohne Hände: `v4l2-ctl -d /dev/video1 --clear-edid=0` -> `no signal`, `fe64` steht, die Firmware schaltet
    Kanal 0 ab (`0x03000200`). `h713-warp ctl test grid` wird ohne Signal von h713-tv abgelehnt ("no signal to warp").
  - Ohne Signal, aber mit Wayland-Client (`h713-tv ctl source client; systemctl start h713-desktop`): **Kanal 0 läuft**
    aus DRAM (`0x78f00000`), `fe64` steht. Die Eingangstakt-Vermutung ist damit widerlegt. Zwischen "kein Signal, aus"
    und "kein Signal, Client" ändern sich nur Kanal-0-Wörter; INCAP, Lock-Blöcke, TV-Top, DTOP, NRC/PROC-Anfang gleich.
  - Rückweg: Neustart; h713-tv veröffentlicht die EDID beim Start, danach `query-dv-timings` 1920x1080, `fe64` läuft,
    HDCP 2.2 steht. `h713-desktop` ist nach dem Neustart inaktiv (statische Unit).
- **Datendateien**: keine Registertabelle für kein Signal / Freilauf / Testbild. `OUTPUT_TIMING_*` und `CRTC_MAIN_TV`
  sind EquTable-Parameter ohne Adressen. `0x0500046c` schreibt nur `V_NR/MP_PFU_RAGT_VNR` (`0xa00d`), `0x05000840`
  keine Tabelle.
- **Bench** (8 Boots, jeweils GP5 `RUN1` geprüft): der Firmware-Zustand "kein Signal + Client" minus Bench-Zustand
  (`replay-client.json`, 796 Wörter ohne Zähler/Stempel/Statistik, zwei Wörter mit Adressen außerhalb der Reservate
  ausgelassen) gruppenweise aufgespielt (`replay.py`):
  - Lock-Wörter, PROC, SCL, DEI: kein Latch. **NRC: Latch verbraucht**, ARMED zählt, `0x310` wie mit Firmware.
  - Eingegrenzt (Boot 2, 4-8): **`0x0500046c = 0x006f81c1` und `0x05000840 = 0x04390010` zusammen** genügen, in
    beliebiger Reihenfolge, keins allein; `0x804/808/80c` und `0x05000040` Bit 25 nicht nötig.
  - Bild nach Histogramm (`histchk.sh`, weiß/schwarz/grau/P1 im DRAM): mit nur den Latch-Wörtern volle Bilder in Fach 0;
    folgt dem Inhalt erst mit NRC `0x844..0x860` + `0x000..0x0fc` (+ `0x900..0xa98` für sauber: weiß 2073600 in Fach
    31, schwarz nur Fächer 5/6) und BORDER. Niemand hat auf die Wand geschaut.
  - Video-Vsync bleibt bei 15.26 ms (65.5 Hz) gegen 60 Hz am Panel, auch mit den Lock-Wörtern der Firmware.
  - Boot 3 (Skripte 20 s nach Kernelstart): Video-Raster startete nach den Init-Tabellen nicht (Zeilenzähler 0,
    `fe74/78` mit Boot-Totalen), auch nicht bei erneutem Aufspielen; mit 15 s Wartezeit 5 von 5 gut. Ursache offen.
- Am Ende: Normalboot, `fw_printenv` gleich dem Abzug (Bench-Variablen und die von `saveenv` mitgeschriebenen
  Laufzeitvariablen wieder entfernt), GP5 `RUN1`, HDMI-Signal zurück. Werkzeuge und Logs:
  `analyse/cleanroom-bench-20261103/` (`r2-*.log`, `diff-*.txt`).
- Nächstes: welche Wörter von PROC/SCL/PNL/DEI über die Init-Tabellen hinaus für das Bild nötig sind; Frame-Lock auf
  60 Hz; ein Bild mit Augen an der Wand.

## 6 Runde 3: Minimalsatz, 65.5 Hz, 720p skaliert, das Werkzeug der sauberen Seite

Auftrag des Leads (WALL `fe3b521`, danach die Zusatzaufträge A/B). Spezifikation: `cleanroom-h713` `5f0eb3f`
(10 §6.3, 12 §M, 20 S2 HY320, 00 §4, 40 §7, `notes/bench-results-stage2.md`).

- **Minimalsatz** (`minimize.py`, im Prozess, Bilder per Adress-Flip weiß `0x4c000000` / schwarz `0x6ca00000` / P1
  `0x6cd00000`): ganz 12 -> exakt; ohne DEI und ohne die Lock-Wörter weiter exakt; ohne NRC, PROC, SCL, PNL oder BORDER
  kaputt. Gieriges Entfernen: 40 Wörter für schwarz/weiß (P1 fällt auf zwei Fächer), 85 Wörter mit P1-Kriterium; beide
  in einem frischen Boot allein bestätigt. **Einmal Hänger**: ein Pufferadress-Wort von NRC allein auf 0 gesetzt, während
  die NRC-Schreibkanäle an waren -> SoC hing, Watchdog -> Normalboot (das Netz hat im Ernstfall gegriffen). Danach
  Adresswörter ausgespart.
- **60 Hz gibt es nicht**: RGB-Kanal fertig-Bit 65.6/s, Video-Vsync 15.267 ms, in der Bench und mit Firmware gleich
  (`rate.py`: `fe68` 65.5/s im Normalboot). Das Panel läuft mit ~65.5 Hz; 00 §4 korrigiert.
- **Raster-Hänger**: bei 19.4/19.6/20.4/31 s Start nicht wieder aufgetreten (0 von 4, insgesamt 1 von 13). Erkennungsmerkmale
  in 10 §6.3 (`fe74`[31:16] = Boot-Totale, Zeilenzähler steht).
- **720p**: Firmware-Referenz über den Zoom 1.5 (`h713-tv ctl zoom in 1.5` bei HDMI, nur lesen): Phasen `0x6aaa`/`0xd555`,
  PROC/NRC auf Quellgröße, `VCH_OUTSIZE` = Quellfenster, `0x050/0x054` Fensteranfang. Auf der Bench mit echtem
  1280x720-NV12 (`q4.py`): Quadrant 25.00 %, linke/obere Hälfte je 50.00 % - exakt.
- **Q-PQ-4**: Weißabgleich über die Firmware gemessen, Kurvenergebnis wird abgeschnitten (600 -> `0x960`, 1000 -> `0xfa2`).
- **vp-bench der sauberen Seite** (Auftrag A, wie geschrieben, `run-vp-bench.sh`, Start 40.8 s): T1 besteht (Latch, Scan,
  Histogramm weiß/schwarz/grau/P1 exakt auf den Referenzen), `apply` meldet 39 Rücklese-Abweichungen = Statuswörter aus
  12 (Spezifikationsfehler, jetzt 12 §M.3). T2: `verify t2` PASS, aber Geometrie falsch (Quadrant 19 % statt 25 %), weil
  S2 nur die vier HY310-Wörter hatte, NRC/PROC auf 1080 blieben und `VCH_OUTSIZE` 1080 geschrieben wurde; `verify scan`
  bei 720p: `0x310` Bit 21 kippte nicht (bei 720p nie gemessen). Code nicht angefasst.
- Fragen der sauberen Seite (Auftrag B): 40 §7 aus den Dateien beantwortet; Q-TSE-4/6 offen (nicht nötig für das Bild).
- Gerät am Ende: Normalboot, `fw_printenv` gleich dem Abzug, GP5 `RUN1`, HDMI 1080p zurück, Zoom aus, WB neutral.

## 7 Runde 4: Stufe 1 für den sauberen DRM-Treiber (Übergabe, RGB-Ebene, Interrupts, Takte, Mode)

Spezifikation: `cleanroom-h713` `136933f` (neues 05, 95 Stufe-1-Tests). Gerätesperre `/tmp/h713-device.lock` für die
Bench-Phase gehalten (mit RustInfra geteilt), danach Normalboot mit Release-Kern (`c5b9719a…`), Umgebung gleich dem
Abzug, Sperre frei.

- **Übergabezustand B0** (`r4.py handoff`): TCON/LVDS/OSD/RASTER/MIX/PNL/Kanal 2 gelesen; TCON ab `0x48` liest
  `0xdeadabba`. Kanal 2: `0x150/0x154/0x160/0x170/0x174` wie Kanal 0 aufgebaut (1088er Höhe, 7680 Pitch), `0x178` = Logo
  `0x6c100000`, Format `0x19` = XRGB8888 (Augenbeleg doku/227 §2).
- **Bildrate exakt**: Fertig-Bit des RGB-Kanals 1310 Intervalle in 19.988 s -> 65.538 Hz, 15.2583 ms -> 162.21 MHz bei
  2200x1125.
- **Interrupts ohne Firmware** (GIC-Pending-Register `0x03021200+`, Leitungen in Linux nicht freigegeben): RGB-Fertig
  `0x168` Bit 1 + Freigabe `0x16c` Bit 4 -> **SPI 112** (id 144), Pegel; Video-Vsync `0x0c0` Bit 0 + `0x0c4` Bit 0 -> SPI
  110 (id 142), aber nur bei laufendem Video-Raster (Kanal 0 an + Init-Tabellen). Darum lief der Stufe-1-Treiber im
  E5-Versuch in den vblank-Timeout: der DT nennt nur SPI 110. 132/132 Ereignisse je Leitung.
- **RGB-Flip**: Inhalt sichtbar im Histogramm nur, wenn RGB über ein Videobild gemischt wird (`PNL_SEL 0x29000000`,
  Alpha `0x051c0070`); Adresse allein wirkt nicht, Latch `0x144` wird an der nächsten Bildgrenze genommen (1.4-13.8 ms),
  Adresse nach dem Latch im selben Bild gilt. 65.5 Zeilen bleiben beim Mischen unbedeckt (bekanntes "gerolltes" Overlay).
- **Takte**: Boot ohne `clk_ignore_unused`/`pd_ignore_unused` (nur CCU gelesen): Video-PLL Bit 31, `db0`, `db4`, `db8`
  Bit 31, `dc0` Bit 31, `dd8` Bit 0 weg; `dd8` Bit 16 bleibt. Der ganze RTC-Block las dabei `0x00010000` (Lesepfad
  abgeschaltet) - GP5 also nicht prüfbar; nach dem angeforderten Neustart war GP5 wieder `RUN1` (Inhalt erhalten).

## 8 Nachtrag Runde 4: Prozess, Q-TSE-8, Q-VP-5/12/13, ein Speicherschaden

- Prozess (Lead): neue Entwürfe gehören nach `/srv/h713/cleanroom-held/drafts/`, nicht ins saubere Repo. Das schon
  eingecheckte 05 (`136933f`) mit `git revert` (`9e40ad5`) aus `cleanroom-h713` genommen; 00, 05, 95 als vollständige
  Dateien in `drafts/`, dazu 12 und 40 mit den neuen Antworten. `136933f` bleibt in der Historie sichtbar.
- Q-TSE-8: die Kopfzeile der Farbraum-Zeilen sind (0, Typ)-Paare ab `0x3cdfa` (davor `0xffffffff`); meine erste
  Fassung hatte (Typ, 0).
- Q-VP-5: Chroma-Gain der HY320-Firmware `0x04400000`; Bit 28 ohne sichtbare Wirkung im Histogramm; Gain 0 macht die
  Balken grau (550000 Pixel wandern in drei Grau-Fächer).
- Q-VP-12: `0x05001028` wechselt mit dem Zustand (`0xffffffff`, `0xff000001`, `0x3f000000`, `0xff000000`), ohne Wirkung
  im Histogramm.
- Q-VP-13: weder der 40- noch der 85-Wort-Satz gibt bei 720p die richtigen Flächen; mit 12s NRC-, PROC- und SCL-Wörtern
  unter den S2-Wörtern exakt (25/50/50 %). `0x858` bleibt `0x04380010`.
- **Speicherschaden** im Boot r5-2: NRC-Schreibkanäle an (S2-Wörter `0x278/0x2b8` und 12s NRC-Block), Pufferadressen
  nicht gesetzt -> DMA ins RAM, danach Segfaults/"Illegal instruction" in Userspace, `systemctl reboot` stürzte ab.
  Rückweg mit `sysrq s`/`b`: Normalboot, ext4-Journal sauber nachgezogen, keine fehlgeschlagenen Units, Release-FIT
  `c5b9719a`, Umgebung gleich dem Abzug. In 12 §M.4 als Sicherheitsregel festgehalten.
- Gerätesperre: mit RustInfra geteilt (`flock /tmp/h713-device.lock`); RustInfra hatte zwei Neustarts um 08:38
  Gerätezeit unter der Sperre, ich danach. Sperre frei, RustInfra benachrichtigt.

## 9 Runde 5: DRM-Modul der sauberen Seite, Fragen Q-DRM-1..5, Takt der Init-Tabellen

- Entwürfe in `cleanroom-held/drafts/` (vollständige Dateien): 05 (§3 GIC-Konfiguration id 144 = Pegel, CPU0; §4.1
  Takt-IDs der Projekt-Bindung: `CLK_PLL_VIDEO2` 7, `CLK_DEINT` 125, `CLK_PANEL` 126, `CLK_SVP_DTL` 127, `CLK_AFBD` 128,
  `CLK_BUS_DISP` 129, `RST_BUS_DISP` 57; §6 reservierter Speicher, `nr_base`, Entladen; RGB-Pitch: `0x170` = Pitch,
  `0x174`[15:0] = Bytes pro Zeile, gemessen mit Pitch 8192), 10 §6.3 (Takt der Init-Tabellen), 12 §M.3 (`0x051c0300`),
  20 (`0x05001028` kein Zielwort), 95 (S1-T3 umformuliert).
- RustInfra: zweiter Kern `/boot/h713-kernel-rust.fit` (6.18.38-rust) neben dem Release; Bench mit nur geändertem
  Dateinamen in `bench_kernel`. Gerätesperre `/tmp/h713-device.lock` für jede Boot-Phase.
- **h713_drm.ko wie geschrieben** (`notes/bench-results-drm.md`, Logs `notes/bench-logs/2026-11-03-drm/`): Laden,
  Mode (162210 kHz, 65.539 Hz), RGB-Übernahme, 3930 Flips 65.54/s ohne Timeout, Video T1 mit Histogramm 4/4, 655
  Overlay-Flips, 720p-Flächen exakt (Kriterium "Rest in Fächern 0..8" zu streng), Ebenen zusammen wie R4/R5, `rmmod`
  sauber. Fehler: erste volle Aktivierung im frischen Boot meldete Raster-Hänger + Latch-Timeout (spätere sauber);
  S1-T3 (`/proc/interrupts` beim Stehbild nur +237/10 s, DRM schaltet vblank ab, `kms-test vblank` 65.44/s); `verify t2`
  an `0x05001028` (Zustandswort); einmal `0x051c0300` live.
- **Takt der Init-Tabellen** (`r7.py`, `r8.py`, drei frische Boots): alle fünf Tabellen + Totale in 12 ms -> Video-Seite
  kaputt (Kanal 0 rastet nie, `PNL 0x148..0x158` = 0, Zeilenzähler läuft über 1124), auch langsames Neuschreiben hilft in
  dem Boot nicht. Mit 200 ms zwischen den Tabellen oder 1 ms pro Schreibzugriff: Raster normal, Latch 25-27 ms nach den
  zwei Latch-Wörtern. Erklärt den Raster-Hänger von Runde 2 (Boot 3) nicht sicher, aber den ersten Commit des Moduls.
  `0x0c0` Bit 0 setzt nur mit eingeschaltetem Kanal 0.
- Prozessfehler meinerseits: die Pacing-Zahlen standen kurz in `notes/bench-results-drm.md` des sauberen Repos (`22f5012`),
  mit `8be200a` wieder herausgenommen; in der Historie sichtbar.
- Gerät: Normalboot, Release-FIT `c5b9719a`, `h713_boot=emmc`, Umgebung gleich der Referenz nach `boot_rust`, GP5 `RUN1`,
  Sperre frei.

## 10 Runde 6: RGB über Video - zwei Raster, Ausrichtung

- Auftrag (lead): welche Wörter setzen Lage/Größe der RGB-Ebene im gemischten Pfad (05 §2 R4, S1-T6 scheitert bei
  Alpha 255/128); erwartetes Histogramm für Alpha 128 über Schwarz.
- Normalboot, nur lesend: `RASTER 0x0525c000..` und `OSD 0x0524c000..` gleich dem Bench-Zustand; `PNL 0x051c0000..007c`
  der Firmware stehen nach dem 12-Satz (`minimize.py all`) schon da. Mit offener Seite (Launcher) ist die Videoebene aus
  (RGB allein), die Lautstärke-Pille erschien in der Abtastung nicht über dem Video - kein Firmware-Zustand zum Kopieren
  (doku/225 §3b: mit Firmware ebenfalls verrollt).
- Bench (drei frische Boots, `r9.py`, `r10.py`, `meas.py`, `align3.py`): die fehlende Fläche ist immer
  86400 + 1035·n Pixel (45 Zeilen + n Spalten; n = 14, 95, 57, Runde 4: 38). Mit Spalten- und Zeilenstreifen (24 Grau-
  stufen, je eigenes Histogrammfach) sichtbar: es fehlen ganze RGB-Zeilen und -Spalten - genau 45 und 280, die Austastung
  eines 2200x1125-Rasters. Die RGB-Ebene läuft auf ihrem eigenen Raster (`RASTER 0x000`), die Videoebene auf dem
  Video-Raster; der Versatz der beiden ist die Lage des Overlays.
- `RASTER 0x000` verschiebt nur das RGB-Raster: Vertikal-Total wird je Bild übernommen (ein Bild 2200x(1125+c), c=25..100,
  schiebt um genau c Zeilen, Spalten bleiben; 13 von 14 Gruppen), Horizontal-Total je Zeile (ein Bild mit 2199/2201
  schiebt um 1125 Spalten, aus Python manchmal daneben). Ein Bild nur 1 Zeile länger oder kürzer verschiebt auch die
  Spalten (unbrauchbar). Kein statisches Wort (Fenster `RASTER 0x018..0x034`, `OSD 0x004`) und kein Bit in
  `RASTER 0x004..0x038`, `OSD 0x000/008/014/018` koppelt die Raster.
- **Ausgerichtet** (geschlossener Regelkreis über die Streifen, zwei Boots): weiß bei Alpha 0xff = Fach 31 alle 2073600,
  0x80 = Fach 19, 0x40 = Fach 12, 0 = Fächer 5/6 (777600/1296000); schwarz 0/3/4, grau 0x80 16/11/8; 20 s stabil. Zeit
  Video-Vsync -> RGB-done dann 13,784..13,786 ms (1016 Zeilen) in beiden Boots; direkt nach dem 12-Satz 9,064 ms (668
  Zeilen) in beiden Boots, die Spaltenlage aber verschieden (57 und 95). Offen: hardwareseitiges Koppeln; Spaltenlage
  nur über das Histogramm lesbar.
- `h713_bench=`: die Variable ist nicht in der Umgebung (`fw_printenv | grep -c bench` = 0); `fw_printenv NAME` druckt
  für jede unbekannte Variable `NAME=` mit Rückgabe 0 (geprüft mit `h713_no_such_var_xyz`). Harmlos, nichts zu löschen.
- Entwürfe: `cleanroom-held/drafts/05-rgb-plane-and-handoff.md` (§2 R4 neu, §2.1 B1-B8 + Histogrammtabelle, §5 Zeile
  "rasters"), `95-test-procedures.md` (S1-T6). Werkzeuge und Logs in `analyse/cleanroom-bench-20261103/`.
- Gerät: Normalboot, 6.18.38, Umgebung gleich der Referenz (`env-before-r6.txt`), GP5 `RUN1`, `h713-tv ctl status` ok,
  keine fehlgeschlagenen Units, Sperre frei. `/lib/firmware/h713/database.TSE` und `/root`-Werkzeuge bleiben (lead).

## 11 Runde 7: DRM-Modul Runde 2 und 3, Q-DRM-6/7, Q-ALN-1..3

- **Modul Runde 2** (`fb4e236`, -rust-Kern, B0, wie geschrieben; `notes/bench-results-drm.md`, Logs
  `notes/bench-logs/2026-11-03-drm-r2/`): alles PASS bis auf das erwartete S1-T6 (U = 114345). Erste volle
  Aktivierung des Boots sauber (`0 timeouts, 0 check failures`, kein Raster-Hänger), 16 Commits sauber, S1-T3 +656/10 s,
  Pitch 8192 = 7680, `rmmod` stellt das Logo zurück (`0x178 = 0x6c100000`, `MIX 0x10000040`).
- **Q-DRM-7** (drei frische Boots, Composer `vp-bench apply --pace`): nur 200 ms zwischen Tabellen oder nur 1 ms pro
  Schreiben reicht, je drei volle Aktivierungen im selben Boot sauber, Bild folgt dem Rahmen. Ohne Pause: Raster läuft,
  aber `0x05600310` Bit 21 steht (`0x00a00210`), auch nach einer späteren gepacten Aktivierung.
- **Q-DRM-6**: `0x170` ist 16 Bit (`0xffffffff` -> `0xffff`, `0x12000` -> `0x2000`); die Abholung nimmt den Pitch in
  16-Byte-Schritten (8196/8200 wie 8192, 7684 wie 7680); 8208..8448, 12288, 16384, 18000, 65532 ohne schwarze Zeilen.
  Pitch-Probe zuerst mit Bus error (unausgerichtete memcpy auf `/dev/mem` mit O_SYNC), danach am Stück kopiert.
- **Q-ALN-1**: Horizontal-Total wirkt zeilenweise: 2201 für m Zeilen (Schreiben 8 us nach dem Zeilenschritt des
  Video-Zeilenzählers, zurück nach m Zeilen) schiebt um m Spalten (m = 8..800, 25 von 32), aber 7 von 32 Fenstern
  sprangen um genau 65536 Pixeltakte (-30 Zeilen +464 Spalten) oder anders; sichere Schreibposition unbekannt; eine
  Serie mit 24 kurzen Fenstern bewegte gar nichts (unverstanden).
- **Q-ALN-2**: gleiche Geometrie neu aktiviert -> bleibt ausgerichtet; 1080p -> 720p verliert eine Zeile, ausgerichtet bei
  720p 13,772 ms (1015 Zeilen); zurück wieder eine Zeile.
- **Q-ALN-3**: ftrace fehlt im -rust-Kern; das Modul (IRQ-Zeitstempel) las 13,784/13,785 ms bei zeilengenau
  ausgerichteten Zeilen (1080p) und 13,772 ms (720p) = die gepollten Werte; Unterschied der Leitungen < 0,002 ms.
- **Modul Runde 3, Schritt 5** (`0af7d18`): `s1t6` meldet `align: vblank interrupt unavailable` (nicht ausgerichtet,
  U = 122625 / mit align_cal aus dem vorigen Zustand 37800); beim Halten richtet `align=1` die Zeilen aus (9,064 ->
  13,784 ms, 348 Zeilen in 4 Bildern; U = 37800 = 35 Spalten), `align_cal=1` Spalten 35 -> 10, U = 10800; 720p:
  ohne Kalibrierung eine Zeile daneben (U = 39685), mit Kalibrierung Zeilen 1 -> 0 (13,772 ms).
- Entwürfe: `cleanroom-held/drafts/05-rgb-plane-and-handoff.md` (§1.2 Pitch-Tabelle, §2.1 B9-B11),
  `10-video-plane.md` (§6.3 Pacing-Zeilen und Text). Werkzeuge/Logs in `analyse/cleanroom-bench-20261103/`.
- Gerät: Normalboot 6.18.38, Umgebung gleich `env-before-r7.txt`, GP5 `RUN1`, `h713-tv` ok, keine fehlgeschlagenen
  Units, Sperre frei.

## 12 Runde 8: DRM-Modul Runde 4

- `d193bd0` (Hashes `25704598…`, `dc05ac52…`, `866c2c2d…`), -rust-Kern, B0, Schritte 0-4 und 6 als Regression, Schritt 5
  wie geschrieben (`notes/bench-results-drm.md` r4, Logs `notes/bench-logs/2026-11-03-drm-r4/`).
- Regression: alles PASS (S1-T5, S1-T3 +656/10 s, 3930 Flips, erste volle Aktivierung sauber, T1/T2, 17 Commits ohne
  Fehler, Logo nach `rmmod` zurück).
- Schritt 5, Standard (`align=1`): kein "vblank interrupt unavailable" mehr; Zeilen ausgerichtet (9,066 -> 13,786 ms,
  348 Zeilen in 4 Bildern; 720p 13,772 ms), Spalten offen: U = 18360 (17 Spalten) bei 1080p und 720p.
- `align_cal=1`: Spalten 17 -> 8 (Gitter) -> 0 (ein Zeilenfenster, 0 Sprünge), Zeilen 23 -> 0; **S1-T6 PASS bei allen vier
  Alphas** (31/19/12 = 2073600, 5/6 = 777600/1296000), 720p ebenfalls 2073600. Kein Rastersprung -> Q-ALN-4 nicht nötig.
- Gerät: Normalboot 6.18.38, Umgebung gleich `env-before-r8.txt`, GP5 `RUN1`, `h713-tv` ok, Sperre frei.

## 13 Runde 9: Bildverarbeitung ohne Firmware (Gamma, Weißabgleich, Helligkeit/Kontrast)

Ein Bench-Boot (Release-Kern), 12-Zustand, RGB-Ebene über Video ausgerichtet, Werkzeug `gam.py`, Log `g-bench.log`.
Niemand hat auf die Wand gesehen.

- **Histogramm** (Q13): ein Fach zählt max(R, G, B) nach Weißabgleich und Gamma, 10 Bit >> 5. **Sonden**:
  `0x051c0304` = ein Pixel nach WB/Gamma (R [29:20], B [19:10], G [9:0], 10 Bit); `0x051c0144` = Videopfad davor.
- **Gamma** (Q12): zwei Bänke; Bit 28 wählt die sichtbare, die Ports schreiben in die andere und nur mit Bit 30.
  Ablauf: Bit 30 setzen, R/G/B je 512 Wörter, Bit 30 löschen, Bit 28 umschalten - fertig, ohne Bildwarten und ohne
  23/22. Angewendet nur mit Bit 26 und [21:20] = 3 ([23:22]: 00 schwarz, 10 weiß, x1 Kurve); sonst exakt linear
  (Bypass = neutral, Q14). Nichts löscht sich selbst - die binär abgeleitete Lesart von Q12 stimmt so nicht.
  Nach B0 `e8 = 0`; die Panel-Init-Tabelle schreibt `0x00f00000` (Bypass); der 12-Zustand `0x14f00000` schaltet Bank 1
  ein, die nach Warmstart noch die dritte Kurve des Besitzers hielt. Die drei Kurven: rotlastig, blaulastig,
  fast neutral (Sonde).
- **Weißabgleich** (Q16): jedes Feld wirkt vom ARM ohne Firmware auf seinen Kanal, auf RGB- und Videoebene, vor dem
  Gamma; Verstärkung `0x800` = 1,0, Offset-Einheit = halber 10-Bit-Schritt.
- **Helligkeit/Kontrast** (`pq_custom.TSE`): Helligkeit -> `PROC 0x051405bc` [17:8] (vorzeichenbehaftet, ~1,17
  Stufen/Einheit), Kontrast -> drei Verstärkungen `0x05140d34` [27:16] grün, [11:0] blau, `0x05140d38` [11:0] rot
  (`0x958` = 1,0), `0x05140d38` [27:16] = Schwarzwert `0x40`. Neutral wandelt Y begrenzt -> voll exakt (Y 128 -> 523).
  Der 12-Zustand trägt Helligkeit +100 und Verstärkung `0xd8c` (Y 128 -> 928).
- Entwürfe: `cleanroom-held/drafts/30-picture-processing.md` (§3.3, §4.1, §4.3, §4.5); Notizen in
  `cleanroom-held/90-open-questions.md` unter Q12, Q13, Q14, Q16.
- Gerät: Normalboot 6.18.38, Umgebung gleich `env-before-r9.txt`, GP5 `RUN1`, `h713-tv` ok, Sperre frei.

## 14 Runde 10: Q-PQ-6/7/8, DRM-Modul Runde 5, eine zurückgenommene Zeile

- **Q-PQ-6**: `0x051405bc` [17:8] = feine Helligkeit (Runde 9); [7:0] = grobe Y-Verschiebung in 8-Bit-Codes, `0x80` = 0
  (Y 128: `0x70`/`0x80`/`0x90`/`0xa0` -> 449/523/598/673; 0 schwarz, `0xff` weiß); die Kurve fasst [7:0] nicht an.
- **Q-PQ-7**: Schärfe messbar mit Y-64/192-Streifen: `0x05140c4c` (12-Zustand `0x80780855`) treibt 4-Pixel-Streifen
  von Fach 7/25 auf 3/28, `0x80aa00aa` auf 0/30; 0 oder [23:0] = 0 keine Wirkung; Bit 31 = dunkle Seite; [7:4] stärker
  als [3:0]; `0x05140020` [11:6] ohne Wirkung.
- **Q-PQ-8**: Farbton [9:0] dreht (Cb, Cr) um etwa -0,35 Grad je Einheit (+256 -> -91 Grad, -256 -> +90 Grad); Rot wird
  bei +256 magenta-blau, bei -256 grün. Sättigung [23:16], `0x40` = 1,0, 0 = grau. WB-Tönungen pro Kanal wie Runde 9.
- **Modul Runde 5** (`c50d31d`): Regression 1-5 PASS bis auf einen `verify scan`-Fehler (`0x310` Bit 21 in 20 Lesungen
  nie gelöscht); S1-T6 mit `align_cal=1` PASS; `pqcheck` drei PASS, `pq:` ohne Fehler, Dumps wie erwartet, nur der
  Commit "zurück auf Standard" ließ `0x05140508 = 0x04000000` (erwartet `0x04400000`); nach `rmmod` bleibt `0x051c00dc`
  auf `0x06400800`.
- **Zurückgenommen**: Bit 21 von `0x05600310` ist im laufenden Bild nur 7-10 % der Zeit gelöscht; ein 20-Lesungen-Test
  verfehlt das etwa jedes siebte Mal. Die Zeile "ohne Pause bleibt `0x310` bei `0x00a00210`" (Runde 7, in 10 §6.3
  gekreuzt) beruhte darauf; ein zweiter Boot ohne Pause: 10,1 % gelöscht, Bild folgt. Entwurf 10 §6.3 korrigiert.
- Entwürfe: `drafts/30-picture-processing.md` (zusätzlich §3.3 [7:0], §3.4 Farbton/Sättigung, §3.5 Schärfe),
  `drafts/10-video-plane.md` (§6.3 korrigiert). Gerät: Normalboot, Umgebung gleich `env-before-r10.txt`, `RUN1`, Sperre frei.

## 15 Runde 11: Q-PQ-9/10, Dither, DRM-Modul Runde 6

- **Q-PQ-9**: `0x051c0304` tastet Pixel (1900, 10) ab; `0x051c0268` = (x << 16) | y verschiebt die Abtastung sofort
  (geprüft mit einem RGB-Puffer, dessen Pixel ihre Koordinaten tragen). `0x051c0144` tastet Pixel (3, 3) des
  Videobilds; keines von 15 PNL-Kandidatenwörtern verschiebt es.
- **Q-PQ-10**: rotes Bild (Y 128, Cb 64, Cr 192), neutral: Farbton 0 -> 953/411/1023, 50 -> 1023/397/0, 100 ->
  109/705/0. Matrix aus ±32-Schritten: B-Cb 1,84, R-Cr 1,62, G-Cr -0,45, G-Cb -0,09 (relativ zur Luma-Verstärkung); nahe
  BT.709 bei B-Cb und G-Cr, R-Cr 5 % höher, G-Cb halb, ein kleiner R-Cb-Anteil.
- **Dither** (91 O15): `0x051c00ec` wirkt: 0 / `0x10101000` -> `0x0304` = `0x0144`; `0x14141400` (12-Zustand) bis +4;
  `0x16161600` bis +16, im Histogramm sichtbar. Erklärt die pqcheck-Abweichungen von 4 und die 5/6-Aufteilung von Schwarz.
- **Modul Runde 6** (`4145b66`): Schritte 1-5 PASS bis auf P3-Grau (Fach 28 statt 29) und S1-T6 bei Alpha 0x80 (Fach 18)
  und 0 (alles Fach 5); pqcheck 21 PASS / 14 FAIL (alle FAILs = +4 aus dem Dither am Sondenpixel); Dumps wie erwartet;
  einmal "RGB latch still pending at a new flip" während der 3930 Flips.
- Entwurf: `drafts/30-picture-processing.md` (§3.4 Q-PQ-10, §4.4 Dither, §4.5 `0x0268` und Lage von `0x0144`).
  Umgebung: die Kernel-Spur hat `boot_k73` und 7.3-FITs ergänzt; Referenz `env-before-r11.txt` enthält das. Gerät:
  Normalboot, Umgebung gleich der Referenz, `RUN1`, Sperre frei.

## 16 Runde 12: Q-PQ-11, DRM-Modul Runde 7

- Gerät war ~20:00-20:40 (Arbeitsplatzzeit) nicht erreichbar: der Einmal-Start des 7.3.1-Kerns der Kernel-Spur kam ohne
  WLAN-Anmeldung hoch; Besitzer hat aus- und eingeschaltet, danach Normalboot 6.18.38, Umgebung gleich `env-before-r11.txt`.
- **Q-PQ-11**: dritte Kurve des Besitzers hochgeladen, Dither 0, beide Sonden auf (3, 3): 16 Graustufen x 3 Kanäle,
  Ausgang = ceil(Probe / 4) des dekodierten 12-Bit-Werts am 10-Bit-Eingang, in allen 48 Fällen - Dekodierung stimmt bitgenau.
- **Modul Runde 7** (`ae0a45c`): S1-T5, S1-T3, T1 (P3 wieder Fach 29), T2 PASS; 3930 Flips ohne Timeout, aber nur 32,8/s
  (Flip-Ereignis wartet auf das Latch, zwei Vblanks je Flip); S1-T6 mit `align_cal=1` PASS bei 0xff/0x80/0x40, Alpha 0
  FAIL (Schwarz jetzt 518400/1555200 in Fach 5/6 mit der Standardkurve); pqcheck 38 PASS / 1 FAIL (Sättigung zurück:
  1264 Pixel); Dumps und Entladen wie erwartet.
- Entwurf `drafts/30-picture-processing.md` §4.3 (Q-PQ-11). Gerät: Normalboot, Umgebung gleich `env-before-r12.txt`,
  `RUN1`, Sperre frei.

## 17 Runde 13: S1-T6/T1-Histogramme mit und ohne Standardkurve

Ein Bench-Boot (`t6c.py`, Log `t6c-bench.log`): 12-Zustand, ausgerichtet, dritte Kurve hochgeladen. Kurve an / LUT aus:
Schwarz 518400/1555200 in Fach 5/6 bzw. alles Fach 5; Weiß 31/31; P3 29/28; S1-T6 Alpha 0xff 31/31, 0x80 19/18, 0x40
12/12, 0 wie Schwarz. Entwurf `drafts/95-test-procedures.md` (Tabelle nach den Stufe-1-Tests). Gerät: Normalboot,
Umgebung gleich `env-before-r13.txt`, `RUN1`, Sperre frei.

## 18 Runde 14: DRM-Modul Runde 8, Q-FLIP-1

- `3d821fe`: alles PASS außer den erwarteten S1-T6-Spalten ohne Kalibrierung (U = 48600); 3930 Flips wieder 65,55/s;
  S1-T6 mit `align_cal=1` PASS bei allen vier Alphas (Alpha 0 = 518400/1555200 bei Standardkurve); pqcheck 39 PASS,
  0 FAIL; P1 zwischen zwei Lesungen: 11 Pixel (Dither 1) gegen 1255 (Standard-Dither).
- **Q-FLIP-1**: Entlade-Zähler 684/3944/14 und 59/9/5: das Latch ist beim RGB-done-IRQ oder spätestens beim ersten
  Poll 100 us danach genommen; 19 von 4715 Flips kamen zu spät für die Grenze. Entwurf 05 §2 R2a.
- Start und Ende in `/srv/h713/notes/kernel-bump.md` vermerkt; Gerät: Normalboot, Umgebung gleich `env-before-r14.txt`,
  `RUN1`, Sperre frei. Weitere Bench-Boots erst nach Freigabe durch den lead (Kernel-Spur).

## 19 Stufe 3 offline: Entwürfe 50/55/59/96

- Faktensammlung durch drei Späher (Empfänger, Aufnahme, binär abgeleitete Fakten) aus hdmi-in.md, arisc.md, doku/71-
  228 und den Nachtlogs; Rohlisten in `analyse/cleanroom-bench-20261103/stage3-*-facts.md`.
- Entwürfe in `cleanroom-held/drafts/`: `50-hdmi-receiver.md` (Blöcke `RX_CTL 0x06800000`, `RX_LINK 0x06840000`,
  `RX_APLL 0x06880000`, `AUX 0x07091000`; Zugriffe, die hängen; Strom/Takt; EDID/Hot-Plug über den ARISC; Lock-Zeichen
  nur stromabwärts; Audio-Statusbytes), `55-capture-to-video-plane.md` (Ring, Schreibindex `0xa0c`, Größen, Freigaben,
  Weg zu Kanal 0, Quell- gegen Panelrate, Bench-Befund), `59-stage3-open.md` (31 gehaltene binär abgeleitete Fakten,
  16 offene Fragen, 9 Experimente X1-X9), `96-stage3-tests.md` (T3-00..T3-08, Xbox 1080p60).
- X1 teilweise: Normalboot (jetzt 7.3.1), ohne Signal (Xbox aus), 8-Bit-Dumps `RX_CTL`, `RX_LINK`, `0x06841000`, `AUX`,
  `CAP`, `TVTOP`, CCU `0x02001d00..`, PPU (`logs/x1-normal.log`). Der Teil mit Signal braucht die eingeschaltete Xbox
  (Besitzer).

## 20 Runde 15: Stufe 3 auf dem Prüfstand (59 X3, X4, X6), ohne Quelle

Einmal-Start B0 mit dem 6.18.38-rust-Kern (MIPS, cpu_comm, hdmirx, msp gesperrt; Watchdog wie §1), Konsole aus, also
kein Signal. Werkzeuge: `analyse/cleanroom-bench-20261103/tools/{x346.sh,cap6.py,spx4/}`, Protokolle `logs/x346-*`,
Vergleich mit dem Normalstart ohne Signal (`x1-normal.log`, `x2-normal.log`) in `logs/rx-bench-vs-normal.txt`.

- X3: `RX_CTL 0x06800000..fff` und `RX_LINK 0x06840000..7ff`/`0x06841000..7ff` (8 bit), `0x068c0000..3ff`,
  `0x05700000..88`, `0x06700000`, TVTOP, PPU, CCU `0x02001d00..dff` lesen ohne Hänger (jede erste Lesung vorher
  protokolliert und gesynct). `RX_APLL` nicht gelesen. Ohne Firmware sind die Empfängerfenster nicht leer (94/206/79
  Bytes ungleich 0); gegen den Normalstart ohne Signal weichen 31/42/15 Bytes ab. CCU `0x02001d10..d60` ohne Bit 31,
  `0x02001d64 = 0` (mit Firmware Bit 31 überall, `0x00010001`); `0x06700000/04` lesen 0, TVTOP `+8 = 0x404`, `+0x1c = 0`.
  `0x068c0000..` gleich bis auf die 8 Ringadresswörter. `0x07010120/124` = 0 bis zum EDID-Reset der ARISC.
- X4: eigenes Hilfsmodul `spx4.ko` (Spec-Werkzeug, ruft die vorhandene ARISC-API): `arisc_hdmi_edid_init(1, hy310-edid.bin)`
  = 0, `get_edid` liefert 256 Bytes zurück, Byte 168 `0x10 -> 0x20`, Byte 255 `0x24 -> 0x14` (die ARISC setzt die
  physische Adresse des Ports und korrigiert die Prüfsumme), `hpd(1, reset)` = 0; danach `0x07091014 = 0x5`,
  `0x07091b04 = 0x7`, `0x07010120/124 = 0x00010000/0x80000000`. EDID und Hot-Plug gehen also ohne display.bin.
- X6: `cap6.py` schreibt die 75 Konfigurationswörter des 1080p60-Zustands mit eigenem Ring ab `0x4b100000` (Ring mit
  `0x5a` gefüllt); alles liest sich zurück wie geschrieben. Ausgänge 2 s an (`0x928/0x968 = 0xe0020438`): nichts
  bewegt sich (`0x104` = 0, `0xa0c` steht, Ring unbeschrieben, `0x05600320/324` = 0), `0x540 = 0x80000000`; Ausgänge
  wieder aus ohne Folgen. Zweiter Durchlauf mit TVTOP `+8 = 0x504`: gleich. Ohne Quelle war nicht mehr zu erwarten.
- Danach: Umgebung per `envrestore.py` exakt auf den Stand vor der Runde (`diff` leer), Normalstart 7.3.1,
  `h713-tv ctl status` ok, keine fehlgeschlagenen Units, `0x07090114 = RUN1`, Sperre freigegeben.
- Spec: 50 §6a + Anhang A, 55 §7 (sauberes Repo `43cca36`, WALL-Zeilen "not yet checked by lead"); 59 (gehalten)
  um den Stand von X3/X4/X6 ergänzt.
- Offen: alles mit Signal (X5, X7, Rest von X6, die Lock-Zeichen) braucht die Konsole an, also den Besitzer.

## 21 Runde 9 (7.3.1) und Stufe 3 mit Quelle

**Runde 9:** `h713_drm.ko` `c990fc7a…` (7.3.1-rustbench), `kms-test` `5a1e62a3…`, `vp-bench` `22b68345…`, Bench B0 mit
`/boot/h713-kernel-rustbench73.fit` (gebaut aus kernel-7.3 `727b88a6`, ohne den späteren 0354/tmpfs-ACL-Commit).
Schritte 0-7 wie geschrieben: auf jeder Zeile dasselbe Urteil wie Runde 8 (6.18). 3930 Flips 65,55/s, T1/T2 PASS, 5a
Spalten-FAIL (jetzt 9 statt 45 Spalten), 5b PASS bei allen vier Alphas, `pqcheck` 39/39, alle 22 `commit:`-Zeilen und 115
`pq:`/`gamma:`-Zeilen ohne Fehlschreibung, Logo nach `rmmod` zurück. Kern: kein Oops/BUG/WARNING/RCU-Stall, AP hielt.
Sauberes Repo `c673e98`, `b5bcb3b` (`notes/bench-results-drm.md` Runde 9, Logs `notes/bench-logs/2026-11-03-drm-r9/`).

**Quelle am HDMI (Besitzer):** Normalstart 7.3.1: `h713-tv ctl status` 1920x1080p60 148,5 MHz, VIC 16, HDCP 2.2
authentifiziert, EDID ausgeliefert, Ton 48 kHz; Launcher bedeckte das Bild bis zu einem Tastendruck (danach
`picture plane on`). Zeile für die Kernel-Spur in `/srv/h713/notes/kernel-bump.md`.

- X1 mit Signal gegen ohne (`logs/stage3-r2/x1-sig.log`, `x1-sig-diff.txt`): `RX_LINK +0x28..0x3f` = CTA-1080p60 als
  16-bit-Paare (2200/1920/280/88/44/148, 1125/1080/45/4/5/36); H5-Freigaben genau wie gehalten; `0x0684037a = 0x04`
  (Empfängerport 2 = ARISC-Port 1); `RX_CTL 0x8fc` Bit 7 und `0x9ab..0x9af` zeigen TMDS an (auch auf dem Bench);
  `AUX 0x07091010 = 0x2` mit eingeschalteter Quelle. 12+6 Bytes laufen. X2: keine Takt-/Energieänderung mit Signal.
- Panne: im ersten X5-Lauf las `rxdump` `AUX` vor dem EDID-Reset der ARISC - Hänger, der Watchdog setzte den Bench in
  den Normalstart zurück (wie in §1 vorgesehen; `x57-hang1.log`). Reihenfolge korrigiert.
- X4 vollständig: mit EDID+HPD vom ARM ohne Firmware sendet die Quelle TMDS.
- X5: `RX_LINK` nimmt ohne Firmware keine Schreibzugriffe an (8 und 32 bit), bis `0x06841001 = 0x05`. Ausgeschlossen als
  Tor: PLL_VIDEO1, CCU-Display-Wörter, TVTOP, `0x06700000`, `SYS_CFG 0x03000090`; ganze CCU, R_CCU, PPU, SYS_CFG, PIO/
  R_PIO, TVTOP-Fenster verglichen (`ccu-full-*.txt`, `gate*-*.log`, `pio-normal.log`). Danach H2->H5 nachgespielt,
  zweiter HPD-Puls: H-Timing rastet auf 2200/1920/88/44/148 und bleibt, V nicht (0xffff bzw. Vielfache eines Frames).
  `CAP 0x104` bleibt 0. Offen: was V braucht (HDCP-1.4-Schlüssel nicht geladen, PD_IDCLK).
- X6/X7: Capture nimmt die Programmierung, schreibt ohne V-Lock nicht; Kanal 0 zeigt den eigenen Ring (Histogramm =
  Markierung 0x5a in Fach 25). Ein HDMI-Bild über den sauberen Pfad gibt es noch nicht.
- Sichtfenster für den Besitzer: Zustand 1 (Normalstart-HDMI) stand 15:46-16:03 Gerätezeit, keine Antwort; vertagt.
  Jeder Zustand mit einem Befehl: `tools/visual-window.sh ref|1|bench|2|3|4|restore`.
- Spec: 50 §4/§6a/Anhang B, 55 §7 (sauberes Repo `ff44e49`, WALL "not yet checked by lead"); 59 (gehalten) ergänzt.
- Ende: Umgebung = Referenz (`diff` leer), Normalstart 7.3.1, `ctl status` ok, keine fehlgeschlagenen Units, RUN1, Sperre frei.

## 22 X5 gelöst: Empfänger, Capture und Kanal 0 ohne display.bin

- Normalstart, nur lesend: Relock der Firmware über `h713-tv ctl replug`, alle 8 ms abgetastet (`logs/stage3-r3/
  relock1.log`, `relock1-seq.txt`): HPD tief -> Freigaben 0, `+0x000` Bit 6; ~300 ms später PHY-Reset (`0x8f1` 0x81 und
  zurück, `+0x1b` 0x15 -> 0x01, `+0x1b5` 0x21 -> 0x31); TMDS 1,6 s später; 9 ms danach Freigaben, 8 ms danach `+0x000`
  Bit 6 und `+0x1d` Bit 0 weg; H gültig 80 ms nach TMDS, V 30 ms nach H.
- Nachgespielt (`x5j.py`, `x5k.py`): H rastet nur zufällig, V nie. Dann der Fund: `RX_CTL` ist 0x4000 groß (Alias alle
  0x10000, `scanalias.py`), die Seiten 1-3 waren nie verglichen. Normal gegen Bench: genau zwei Bytes, `0x06801017 = 0x03`
  und `0x0680101a = 0x20` (Bench 0). Mit beiden: Lock 2200/1920/1125/1080, stabil, übersteht einen HPD-Puls.
- X6: Capture läuft erst mit `CAP +0x000 = 0x3a7b` (Normalwert; vorher 1): Bildzähler 60/s, `0x548 = 0x04650898`,
  Schreibindex 0..2, alle drei Ringplätze mit dem Quellbild.
- X7: Kanal 0 auf Platz 0 (vp-bench, NV16): Panel-Histogramm breit (Fächer 5..31) und wechselnd, vorher alles in Fach 25
  (Markierung). Auf 6.18.38-rust und 7.3.1-rustbench (ARISC mit crust) gleich.
- Sichtfenster: Zustände 2-5 in einem Bench-Start nacheinander probegefahren (P1, Overlay nach `align_cal=1`, Logo nach
  `rmmod`, dann HDMI über den sauberen Pfad) - alle Rücklesungen gut. `tools/visual-window.sh ref|1|bench|2|3|4|5|restore`.
- Spec: 50 §4/§6a, 55 §7 (sauberes Repo, WALL "not yet checked by lead"); 59 (gehalten) ergänzt.
- Ende: Umgebung = Referenz, Normalstart 7.3.1, `ctl status` ok, keine fehlgeschlagenen Units, RUN1, Sperre frei.

## 23 Antworten an die saubere Seite, Schreibindex, Bisektion (04.11.)

- Q-CAP-1/Q-RX-1..3 als 55 §8 / 50 §8 (78 bzw. 91 Schreibzugriffe in Reihenfolge) - vom Lead übernommen (`46f4b58`).
- Entwurf 57 (`cleanroom-held/drafts/`): die Aufrufe des ARISC-Treibers als Schnittstelle (Prototypen, Ports, Zeiten:
  `edid_init` 0,64 s, `get_edid` 0,21 s, `hpd(RESET)` 0,83 s; Reihenfolgeregel AUX), ohne Befehlsformat der ARISC.
- 55 §9 (`cap8.py`, `logs/stage3-r4/cap8.log`): `0x104` = Bildzähler/Zeilenzähler, `0xa0c` = gerade beschriebener Platz,
  springt 3-4 Zeilen nach dem Bildwechsel; Zeile r wird bei Zeilenzähler r + 37 geschrieben. Kein Capture-Interrupt im
  GIC-Pending sichtbar (nur SPI 21/95, auch mit Capture aus).
- 50 §9 Bisektion (16 Bench-Starts, `x5min.py`, `bis.sh`, `logs/stage3-r4/bis.log`): nötig sind der Link-Öffner
  `0x06841001`, die zwei Lock-Bytes `0x06801017/0x0680101a` und von der Ohne-Signal-Liste die Gruppen b (RX_CTL-Seiten
  8/a/b/c), c (RX_LINK `+0x000..0x0fc`) für den Lock und e (`+0x310`, `+0x35e`, `+0x3c5`) für die Capture. Nicht nötig:
  CCU/PLL/TVTOP, Port-Select, PHY-Reset, `+0x002`, die Freigaben, Gruppen a und d.
- Ende: Umgebung = Referenz, Normalstart 7.3.1, RUN1, Sperre frei.

## 24 Runde 10: Stufe 3 über das saubere Modul, Q-HDMI (04.11.)

- Modul `f907a5a7…` (7.3.1-rustbench, hängt an `sun50i-h713-arisc`): Schritte 1-7 wie Runde 9; Schritt 8 HDMI: alle
  `kms-test hdmi`-Zeilen PASS (599 Bilder/10 s, Schreibindex, Kanal 0 auf dem Ring, 598 von 599 gezeigt, 0 übersprungen),
  Empfänger 90 / Capture 78 Schreibzugriffe; T3-08 PASS; T3-05 (Verlust durch HPD tief über den Provider, 10 s):
  Verlust in 70 ms erkannt, Rückkehr 11,7 s nach TMDS (96 will 5 s). `notes/bench-results-drm.md` Runde 10.
- Q-HDMI-1: ohne Pausen rastet der Empfänger 0,1-0,7 s nach den Schreibzugriffen, erstes Capture-Bild nach 7 ms.
- Korrektur 50 §9: der Ring wird nur mit `TVTOP 0x06e00008 = 0x504` beschrieben (0x404: Zähler läuft, Ring leer); die
  Bisektion hatte nur den Zähler geprüft.
- Q-HDMI-2 (Gate-Tests, je 0,5 s; zwei Watchdog-Resets, beide erwartet): `svp-dtl` (127) aus -> RX_CTL-Lesen hängt;
  `bus-tvcap` (124) aus -> Lesen 0, Block verliert den Zustand; `vincap-dma` (120) aus -> Ring leer; `tcd3` (119) aus ->
  Bildzähler stand (2 von 3). Bench ohne `clk_ignore_unused`: das Aufräumen schaltet 119/121/123/125-129 und PLL_VIDEO2
  ab, das erste RX_CTL-Lesen hängt; der ARISC-Provider war in diesem Start unbrauchbar ("startup notify malformed").
- Q-HDMI-4: Ring liegt in `mips-firmware@4b100000` (no-map, in 6.18 und 7.3 gleich); eine Markierung überlebte einen
  Normalstart mit laufender Firmware. Q-HDMI-5: `/lib/firmware/hy310-edid.bin` (vom Installer aus dem Stock-Image),
  Kopie in `testdata/hy320/`.
- Sichtfenster: Zustände 2-5 (5 = HDMI über das Modul) in einem Bench-Start probegefahren, alle Rücklesungen gut.
- Ende: Umgebung = Referenz, Normalstart 7.3.1, RUN1, Sperre frei.

## 25 Runde 11: Stufe 3 ohne Pausen (04.11.)

- Modul `517689fe…` (7.3.1-rustbench): 1-7 wie Runde 10; Schritt 8 alle Zeilen PASS. Q-HDMI-6: die volle Reihenfolge
  (90 Schreibzugriffe) rastet ohne Pausen, TMDS -> capturing 0,31 s (kurz `unsupported` mit 2200x1085, dann 1125).
  T3-08 PASS; T3-05 (HPD 10 s tief über den Provider): Rückkehr 0,21 s nach TMDS, 2,3 s nach dem HPD-Aufruf - PASS.
  Auffällig: beim zweiten und dritten Full-Enable je 1 Timeout und "raster stall suspected"; `+0x3c5` ist ein
  Statusbyte. `notes/bench-results-drm.md` Runde 11 (sauber `31fc952`).
- Sichtfenster: ein Befehl `tools/window.sh` (feste Folge 1 -> Bench -> 2 -> 3 -> 4 -> 5 -> zurück, UTC-Zeitstempel),
  Zustand 5 mit diesem Modul. Wartet auf "ready" des Besitzers.
- Ende: Umgebung = Referenz, Normalstart 7.3.1, RUN1, Sperre frei.

## 26 Runde 12 (04.11.)

- Modul `fa01d83e…`: 1-7 wie Runde 11; Schritt 8 14 PASS, 0 FAIL; Neuladen und Signalrückkehr ohne Timeout und ohne
  "raster stall"; T3-05 Rückkehr 0,21 s nach TMDS. Alle 25 Commit-Zeilen sauber. Zustand 5 des Sichtfensters mit diesem Modul.
  Gerät danach im Normalstart, Umgebung = Referenz, Sperre frei.

## 27 Standby ohne display.bin, erste Versuche (04.11.)

Bench B0 mit 7.3.1-rustbench, crust-h713 v5, `echo mem > /sys/power/state`, RTC +20 s, `h713_gate=0` für die Dauer.
- s1 (sauberes Modul, `kms-test hdmi` läuft): verloren. crust beim nächsten Start: `phase reset, step 0x619, cause 2
  (resuming budget over) ... 60000 ms` - CPUs freigegeben, Linux meldete sich nicht.
- s2 (ohne Modul): zurück nach 20,46 s, rc 0, RTC-Wort RUN1; alle Anzeigeblöcke (vp-bench-Liste, 3265 Wörter) gleich bis
  auf Zähler; das erste Lesen von `CAP 0x06940000` nach dem Aufwachen hängte das SoC (TV-Top im Schlaf zurückgesetzt),
  16-s-Watchdog -> Normalstart.
- s3 (ohne Modul, nur sichere Blöcke): WLAN-AP nach dem Aufwachen weg (mein Skript startete h713-wifi nicht neu, Fehler
  von mir; doku/227 §6). Gerät seit ca. 18:40 UTC nicht erreichbar, nichts setzt es zurück; Besitzer um Stromzyklus gebeten
  (Lead). Bis 20:13 UTC alle 5 min geprüft: weiter weg.
- Seitdem in jedem Standby-Skript: `h713-wifi`-Neustart nach dem Aufwachen und ein Wächter (`systemd-run --on-active=600`,
  Monotonuhr, ohne Schlafzeit), der ohne Host-Kontakt in den Normalstart neu startet. Werkzeuge `tools/stb.sh`, `rsm.py`,
  `stbrun.sh`; Logs `logs/standby/`. Entwurf `cleanroom-held/drafts/60-standby-resume.md` (sauber `b862472`, WALL).
- Offen am Gerät: `h713_gate` steht auf 0 (nach der Rückkehr auf 1 zurück, Umgebungsreferenz `/data/bench/env-before-stb.txt`).

## 28 Sichtfenster, Standby-Bisektion (04.11.)

- Sichtfenster 02:17-02:21 UTC nach festem Plan (`tools/window.sh`): Besitzer "좋아보여" - alle fünf Zustände PASS.
- 61 Standbys (s, v, w, x; Bench 7.3.1-rustbench, crust v5, `h713_gate=0`, WLAN-Neustart und Selbst-Rückfall in jedem
  Lauf; der Wächter holte das Gerät einmal ohne Besitzer zurück). Ergebnisse als Entwurf 2 von
  `cleanroom-held/drafts/60-standby-resume.md`:
  - Kanal 0 (oder die NRC-Schreibkanäle) aktiv im Schlaf -> verloren (8/8, crust "resuming budget over"); alles gestoppt
    (Kanal 0 aus + Latch, NRC-Schreibkanäle Bit 31) -> 9/9 zurück; ohne Stufe 2 41/41 zurück.
  - Anzeige nach dem Aufwachen: alle Blöcke gehalten, kein Panel-Neuaufbau nötig; Stufe 2 läuft nach Neuschreiben nur,
    wenn auch der RGB-Kanal im Schlaf aus war (3/3; sonst steht Kanal 0, 6/6).
  - TV-Seite: TV-Top im Schlaf zurückgesetzt; RX/CAP nach dem Aufwachen ohne Neuaufbau hängen; bester Ablauf (vorher kalt,
    danach die TV-Taktschreibungen des Bootloaders + TV-Top-Folge) 5/6 - keine sichere Folge gefunden.
  - Das saubere Modul (6c79c29) verliert den Schlaf mit Bild (3/3), weil seine Suspend-Folge die DMA nicht wie oben stoppt.
- MAC-Adressen/Seriennummern in allen Logs unter `analyse/cleanroom-bench-20261103/` maskiert (`tools/scrub.py`), tor.sh grün.
- Ende: Umgebung = Referenz (`h713_gate=1`), Normalstart 7.3.1, RUN1, Sperre frei.

## 29 Runde 13 (V4L2) und der Gerätetest von h713-tv auf dem sauberen Stapel (04.11.)

- Runde 13 (Modul `a3dfeaa8…`, sauber `2e13640`): Schritt 8 PASS; 8b alle Zeilen PASS außer `QUERYCAP` (Treibername
  `h713-hdmirx-clean` hat 17 Zeichen, das V4L2-Feld fasst 15 -> `h713-hdmirx-cle`); 59,5/60,05 Bilder/s, 0 verloren,
  Inhalt bewegt sich. Nach dem Ende beider Programme kein `hdmi: off`: der CRTC-Nutzer aus Schritt 8 bleibt.
- h713-tv/h713-warp aus hy320 `7dcf8b48`/`924f0fdd` (Kreuzbau, sha256 `e7e12d0f…`/`e67c823f…`), Prozedur aus
  `docs/tools/h713-tv.md` "Device test on a clean-stack boot", Bench-Start ohne Masken (`logs/h713-tv-clean/`):
  - Start durch die udev-Regel, Journal wie beschrieben (`stack clean`, `display /dev/dri/card1 (h713-drm)`, `crtc 42 on:
    ... the panel is black`, `plane 39 ... video_source`, Preset ohne tnr/snr/dci/black, WB 512 auf dem CRTC). Die vier
    gespeicherten Werte tnr/snr/dci/black werden mit Warnung verworfen. `-n` meldet `signal present`, Exit 0.
  - Erster Durchlauf lief unter dem Launcher (h713-keys öffnet ihn beim Start): `cover`, `video_source buffer`, 0 gezeigt.
    Zweiter Durchlauf mit `h713-osd ctl launcher close`: `video_source hdmi`, Zähler steigen (+118 Quellbilder in 2 s, 0
    übersprungen), Histogramm des Quellbilds.
  - Regler, Preset cinema, WB (`0x051c00dc = 0x06400800`, nach `wb reset` `0x08000800`), alle fünf Ablehnungen, Gamma
    1/3 (`gamma: LUT ... 0 read-back mismatches`), `replug` (S_EDID 0 / 512, -> locked) wie beschrieben.
  - Verlust/Rückkehr per HPD tief 10 s (Spec-Seite): Seite "No signal on HDMI", zurück 0,2 s nach TMDS.
  - Seiten: Lautstärke über dem Bild ohne Popup (kein Ton-Karte, Lautstärke gespeichert). 720p und HOME-Taste: Besitzer.
  - Kodi über h713-warp: `warp on ... 591 commits, 0 busy, 0 refused`. Warp-Ring mit Trapez (tl x 80): Panfrost rendert,
    keine Ablehnung des Imports im Journal, `picture warped`; Reißen nur für den Besitzer sichtbar.
  - Ausweg: `systemctl stop h713-tv@*` -> `console plane off, RGB channel and selector back`, aber kein `hdmi: off`: h713-warp
    hält `/dev/video1` offen, der Eingang läuft weiter (`0x928` Bit 31 gesetzt).
  - Herstellerstart danach mit den neuen Binärdateien: keine `stack`-Zeile, HDCP 2.2, cm, WB wie zuvor.
  - Danach die alten Binärdateien und die alte Regel zurück (`/data/bench/h713-tv-orig/`), Umgebung = Referenz, Normalstart.

## 30 Schritt 9 (Standby mit Modul e65a229) und Q-SLEEP-1/3/4 (04.11.)

- 12 von 12 Schlafphasen zurück (DMA-Stopp des Moduls wirkt). Nur Anzeige: 4/4 mit scan PASS und gleichem Histogramm.
  Mit HDMI: 4 von 8 zurück, 3 Rücksetzungen direkt nach der TV-Neuinitialisierung, 1 ohne Rückkehr im Fenster.
- Beste TV-Folge (kalt vorher, Takte + TV-Top danach): insgesamt 8 von 12. Kein lesbares Zeichen gefunden (TV-Top, Domänen,
  CCU, PIO usw. in guten und schlechten Läufen gleich). Entwurf 60 v3 §3a. Sauber `9b13dd9`.
- Ende: Umgebung = Referenz (`h713_gate=1`), Normalstart, Sperre frei.

## 31 Letzte begrenzte Runde Q-SLEEP-1 (04.11.)

Alle auf dem besten Rezept (kalt vor dem Schlaf, Takte + TV-Top danach), je eine Abwandlung: a) PLL-Lock abwarten
(Bit 28 fiel in keinem Lesezugriff ab, also nichts zu warten) 1/3; b) Reset-Puls DEMOD+TVCAP 0/3; c) TVFE/TVCAP aus/ein
direkt nach dem Aufwachen 1/3; d) Modul neu laden nach dem Aufwachen (erst `tvtop_init=none`) 0/2 - das frische Modul
startet HDMI ohne TV-Neuinit und hängt am ersten Empfängerzugriff. Jeder Fehlschlag hing genau am ersten `RX_CTL`-Lesen.
Keine Variante 6/6: Vorgabe "kein HDMI nach dem Aufwachen bis zum Neustart". Entwurf 60 v4 §3b. Gerät: Normalstart,
Umgebung = Referenz.

## 32 HDMI-Audio: N1-N3 (Normalstart, nur lesen) und B1/B3/B4 (Bank) (04.11.)

Quelle: die Xbox des Besitzers, 1080p60, 48 kHz PCM - aber mit stillen Samples (Pegelmesser im DSP 0, auch im Normalstart
mit gepatchtem DSP). Ergebnisse (Entwurf 70 v2, §2a/§3a/§4.6/§6.4/§9a; 79 §4 für die gehaltenen Zeilen):

- N1: `RX_APLL` mit Firmware = Bankwerte bis auf `+0x04 = 0x50000003`; unverändert über zwei Relocks (12-ms-Schnappschüsse).
  Die Firmware programmiert die APLL nicht (HA14-Erfolgsweg kommt nicht).
- N2: Relock-Zeitachse wie am 03.11.; neu: `+0x36a/+0x36b` laufen nur mit Audio (Abstand ~0x1f, vermutlich FIFO-Zeiger),
  `+0x3af = 4` mit Audio; `+0x1c0..` trägt keinen Paketinhalt (HA9 widerlegt).
- N3: Zustandstabelle (AU_*, CODEC, CODEC_I2S ganz, DSP-Register des Treibers, Lautstärke 0xf684 = -9,5 dB).
- B1: **ohne Firmware erkennt der Empfänger das Audio selbst** (N/CTS, Kanalstatus, `+0x15f = 0x30`, Zeiger laufen);
  `+0x4b = 0x31` statt `0x33` (Bit 1 setzt die Firmware).
- B3: Insel auf der Bank hoch, ROM antwortet (`0x0000 = 0x5451`, `0x00ee = 0x0200`), 3 von 3.
- B4: ungepatchtes ROM nimmt die ganze Direktroute an (alle Rückleseworte richtig). Fallstrick: Leseanforderung bei
  gesetztem Schreib-busy-Bit blockiert den Briefkasten bis zum Inselreset (2 von 2), mit Warten auf Bit 4: keine Blockade.
- Offen, braucht den Besitzer: eine Quelle mit Ton und Ohren/Mikrofon (N4, N5, B4-Entscheidung, B6).
- Gerät am Ende: Normalstart, Umgebung = Referenz, RUN1.

## 33 Runde 15/15b: Standby-Politik und der TMDS-Befund (04.11.)

- Sauber 3d383b1 (Modul 14f1d7f7): Schritt 9 a/b/c 9 von 9 Aufwachen ohne Hänger; b: `unavailable-after-sleep`, ENOLINK;
  c: das Laden prüft das TV-Top (`0x10/0/0`) und lässt den Empfänger in Ruhe. Die V4L2-Zeile kam alle 100 ms (behoben).
- Frischstart ohne HDMI-Lock war **kein Build-Fehler**: die Quelle (Xbox) sendet nach einem Start, der mit Tiefschlaf
  endete oder den Empfänger nie aufsetzte, kein TMDS mehr; ein Hot-Plug-Puls allein holt es nicht zurück, das Altmodul
  (Runde 13) scheiterte ebenso (A/B, abwechselnd). Der Herstellerstart holt sie zurück.
- Sauber 5fd6cd6 (Modul dbd25d04) schreibt die Empfängerfolge 3 s nach dem Hot-Plug auch ohne TMDS: 3 von 3 Starts im
  Fehlerzustand (`0x8fc = 0x3f` vorher) locken in 6,0 s, 3 von 3 im Normalzustand ebenso; Schritt 9 a/b/c wieder grün.
- Entwurf 50 §4a (Zusatz) an der Wand; sauber f9c9072. Gerät: Normalstart, Umgebung = Referenz.
