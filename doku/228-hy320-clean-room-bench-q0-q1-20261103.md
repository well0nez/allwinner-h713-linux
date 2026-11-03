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
