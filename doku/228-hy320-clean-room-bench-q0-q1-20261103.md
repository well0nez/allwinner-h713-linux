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
