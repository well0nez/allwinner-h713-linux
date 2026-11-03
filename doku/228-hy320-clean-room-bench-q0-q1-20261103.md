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
