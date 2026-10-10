# 189 - Handoff 10.10.2026 abends: das Aus über crust ist in `main`; als Nächstes das Aus am HY310 messen und mit Marco das Kaltstart-Gate besprechen; OSD und Konsole im Warp laufen als eigenes Paket

Einstieg für die nächste Sitzung, auch ohne jeden Kontext. Löst `doku/186` ab. Diese Sitzung steht in zwei Einträgen:
`doku/187` (Cloud-RE A/B/C ausgewertet) und `doku/188` (Aus über crust, 0,3 W, Abbild `geuaus1`). Die eine
Aufgabenliste ist `TODO.md`. Die Arbeitsregeln (lokal, nicht im Repo) stehen in `referenz/arbeitsregeln.md`, die
Geräteadressen in `referenz/geraete.md`.

**Marco, 10.10. abends:** "du machst den HY-Test nicht mehr mit mir, das wird die nächste Session machen." Beim
Kaltstart-Gate ist ihm wichtig, "dass der Agent mit mir darüber spricht, was mit Kaltstart-Gate genau berührt"
(Abschnitt 4).

## 1 Was diese Sitzung erreicht hat

| Thema | Ergebnis | Beleg |
|---|---|---|
| Cloud-RE A/B/C | ausgewertet: Stock-"Aus" = ARISC zieht PL6 low (alle Schienen), DSP wird nach Standby bei Stock nicht neu aufgebaut, Log-Stufe | `doku/187` |
| Aus über crust (HY300PRO-G-EU) | `poweroff` -> TF-A fragt crust (Port-3-Auftrag 0x19) -> Cluster in Reset, DRAM Self-Refresh, VDD_SYS getrennt (Stock `0xdea8`), PL6 low; **0,3 W** wie Stock (vorher Gate 2,4 W); Taste, IR-Fernbedienung und Timer wecken | `doku/188`, `arbeit/aus-pl6-20261010/` |
| `h713-power` | Vorgabe `short = poweroff`; neu `h713-power set KEY VALUE` (umstellen ohne Editor), `status` sagt, wer ausschaltet | `docs/tools/h713-power.md` |
| Abbild `geuaus1` | komplett gebaut (reproducible), auf dem G-EU installiert, Kurztests bestanden (crust, WLAN, BT, HDMI/HDCP 1.4, Ton, Standby, Aus) | `doku/188` §4 |
| Integration | Merge `versuch/aus-pl6` -> `main` `9f334b1`; Forks lokal: TF-A `sun50i-h713` `1dd03734` (0031), crust `h713` `d8a8d56` (0082-0087), Spiegel nachgezogen | `tfa-h713/SERIES.txt`, `crust-h713/SERIES.txt` |
| Entscheidungen | 1.1b ARISC vs. crust entschieden (crust nur mit eigener Konfiguration, sonst Hersteller-Firmware), Plan 5.20 (Anzeige im Installer, `h713-arisc`); 5.17 umgeschrieben (build-all setzt automatisch fort, **keine** neuen Schalter, die `--skip-*` fallen weg) | `TODO.md` |
| neue Punkte | 2.38 Ausschalt-OSD, 2.39 Kaltstart-Gate, 2.40 R_WDOG-Warnung, 2.41 OSD-A wie Stock | `TODO.md` |
| OSD/Konsole | Methode entschieden, Paket für eine eigene Sitzung vorbereitet | Abschnitt 5 |

## 2 Stand

- **`main`** = dieser Commit, gut 230 Commits vor `origin`, **nichts gepusht** (`git rev-list --count origin/main..main`).
  Veröffentlicht wird nur `main`, jeder Push nur mit Marcos Ja für genau diesen Push (1.6, 1.7, 1.7a).
- **Fork-Köpfe lokal:** U-Boot `h713-hy310` `7b1ea388da0d` (unverändert), TF-A `sun50i-h713` `1dd0373449df`, crust `h713`
  `d8a8d56f8c46` (der crust-Fork liegt noch nicht auf GitHub). sunxi-tools unverändert.
- **HY300PRO-G-EU:** läuft `geuaus1`, `h713_gate=1`, `power.conf` `short = poweroff`, BLE-Fernbedienung gekoppelt, Warp im
  Bypass (alle Ecken 0). Kein Fokusmotor, keine Kamera, Panel 1280x720.
- **HY310:** zuletzt `r2test4` + Schnell-Deploy `0245` aus der eMMC, `h713_gate=1`, `power.conf` `short = standby`. Am Abend
  per ssh nicht erreichbar (aus, im Gate). Das Aus über crust ist dort **nicht gemessen**, `h713_hy310_sr_defconfig` hat
  `CONFIG_H713_POWER_OFF` darum noch nicht.
- **Arbeitsordner:**
  - `arbeit/aus-pl6-20261010/`: das Paket dieser Sitzung, integriert. Es bleibt stehen, weil der HY310-Test (Abschnitt 3) seine
    Skripte und Bauten braucht: Worktrees `repo/` und `crust/` (beide `versuch/aus-pl6`), `bau.sh`, `test/aus-lauf.sh`,
    `bau/h713_hy310_sr_off_test/` (18:37, crust `d8a8d56`), `plan-kaltstart-gate.md`, `BERICHT.md`.
  - `arbeit/warp-konsole-20261010/`: das OSD-/Konsolen-Paket für eine andere Sitzung (Abschnitt 5). Nicht anfassen,
    solange sie läuft.

## 3 Zuerst: das Aus über crust am HY310 messen (TODO 2.32)

Gleiche Pins wie am G-EU laut Stock-Baum (PL6 Schienen, PB5 Lampe/Lüfter, PL3 USB). Erwartet wird dasselbe Bild wie in
`doku/188` §2. Ablauf wie am G-EU, alles per FEL, die eMMC-Bootkette bleibt unberührt:

1. **Marco:** HY310 einschalten (im Gate: Power-Taste), A-auf-A-Kabel (FEL) steckt, niemand hängt an der UART-Brücke. Dann
   `ssh hy310`. Laufzeiten und Tastendrücke vorher ansagen (Gedächtnis "Gerätetests kosten Stromzyklen").
2. **crust-Datei tauschen, mit Marcos OK:** Der Kernel-Treiber ersetzt beim Start ein laufendes crust, das nicht der Datei in
   `/lib/firmware` entspricht (0192). Darum die HY310-crust-Datei (Name am Gerät nachsehen: `ls /lib/firmware/*crust*`)
   nach `/root/sicherung-aus-pl6/` sichern (mit md5), dann durch `bau/h713_hy310_sr_off_test/scp.bin` ersetzen.
3. **Lauf "test"** (USB steckt, kein Wattmeter): `test/aus-lauf.sh hy1 hy310 test fel`, dann `... aus`, dann `... danach`.
   Erwartet: dunkel, nach 60 s von selbst zurück; Record Phase 7 (`poweroff`), Schritt `0x613`, GP5 `RUN1`, etwa 60000 ms im
   Aus. Der Testbau weckt sich selbst (`H713_POWER_OFF_TEST_WAKE_S`).
4. **Watt:** zweiter Lauf, nach dem FEL-Start das USB-Kabel ziehen (es speist mit, Gedächtnis "FEL-Kabel speist parallel").
   Marco liest das Wattmeter. Ziel 0,3 W, heute im Gate 2,9 W (`doku/181`).
5. **Taste und Fernbedienung:** braucht eine Release-Konfiguration mit Aus. In einem Versuchszweig im crust-Worktree
   `CONFIG_H713_POWER_OFF=y` in `h713_hy310_sr_defconfig` setzen und `bau.sh h713_hy310_sr` neu bauen (der Bau
   `bau/h713_hy310_sr/` von 11:20 ist alt und hat das Aus nicht). Dann `aus-lauf.sh hy3 hy310 taste ...`: die Power-Taste weckt,
   danach die IR-Fernbedienung.
6. **Zurück:** Original-crust-Datei zurück, md5 prüfen, Neustart in die eMMC-Kette.
7. **Bestanden:** `CONFIG_H713_POWER_OFF=y` in `h713_hy310_sr_defconfig` auf crust `h713`, Spiegel `crust-h713/` neu (Baum-Hash
   in `SERIES.txt`), `main` nachziehen (`release/tor.sh && git commit`), neuer Journaleintrag, `docs/hardware.md` (Zeile
   HY310), TODO 2.32 schließen.

Risiken (aus dem BERICHT): bleibt die Box dunkel stehen, dann USB ab, Sonoff aus/an, Taste (Gate). Ein Reset im Aus endet im
Gate wie heute. Kein eMMC-Schreiben, kein Brick-Pfad.

## 4 Danach: Kaltstart-Gate über crust (TODO 2.39) - erst das Gespräch, dann Code

**Status: nur Plan. Nichts gebaut, nichts geändert.** Das Gate ist Marcos Bedienlogik (Gedächtnis "Gate nicht anfassen",
Marco 11.09.: "ich will nicht dass du etwas am gate änderst"). **Ohne sein ausdrückliches Ja zu genau dieser Änderung wird
nichts angefasst**, und vor dem Ja kommt das Gespräch in 4.4.

### 4.1 Warum

- Seit `doku/188` geht ein `poweroff` aus Linux auf dem G-EU in crusts Aus: 0,3 W. **Nach dem Einstecken** (Netz-Ein,
  Kaltstart) zieht die Box weiter **2,4 W** (Marco, 10.10. abends). Dort wartet U-Boots Gate mit einem ARM-Kern in einer
  Schleife auf die Taste (`docs/uboot/power-gate.md`, `doku/181`: 2,4 W G-EU, 2,9 W HY310).
- Stock macht den Kaltstart wie das Aus (`doku/187` §1): BL31 sieht RTC-GP2 = 0, liest `/box_start_os0 : start_type`, setzt
  GP2 = 2 und schickt die ARISC-Firmware in den "fake poweroff" (PL6 low). Darum hat Stock auch eingesteckt-aus 0,3 W.

### 4.2 Was sich ändern würde (Vorschlag)

Das Gate **wartet nicht mehr selbst**, sondern übergibt das Warten an crust, über den Weg, der seit `doku/188` gemessen ist:
U-Boot ruft PSCI `SYSTEM_OFF` (`psci_system_off()`, `arch/arm/cpu/armv8/fwcall.c`; `SYSRESET_PSCI`/`CMD_POWEROFF` sind in
unserer Konfiguration). BL31 schreibt `GATE` in GP5 und fragt crust (`sunxi_scp_off.c`), crust zieht PL6. Die Taste oder
die IR-Fernbedienung weckt, crust schreibt `RUN1` und setzt zurück, U-Boot sieht `RUN1` und bootet durch.

Ort: `mainline/external/u-boot` `board/sunxi/board.c`, `h713_power_gate()` / `h713_gate_wait()` (Fork `h713-hy310`, Spiegel
`uboot-h713/`). Etwa zehn Zeilen.

**Unverändert bleiben sollen:** `h713_gate=1/0` in der Umgebung (Abschalten ohne Neubau), der 3-s-Bypass (Taste beim
Einstecken halten), die Entscheidung nach GP5 (`RUN1` bootet durch, alles andere wartet), dunkel mit PB5/PL3 low (rote LED),
die Pfade ohne crust.

### 4.3 Was bedacht werden muss

1. **Reset-Schleife auf Boards ohne crust-Aus.** Nimmt crust den Auftrag nicht an (Hersteller-ARISC, crust ohne
   `H713_POWER_OFF` wie heute am HY310, altes crust), fällt TF-A auf "GATE + Watchdog-Reset" zurück. U-Boot säße wieder
   im Gate und riefe wieder `SYSTEM_OFF`: **endlose Resets**. Darum prüft U-Boot **vorher selbst**, ob crust kann: die
   Vertragsseite im SRAM A2 (ARM `0x00123800`): MAGIC `0x33313748` ("H713") bei +0x000, VERSION >= 5 bei +0x004, BUILD2
   (+0x264) Bit 24, Herzschlag (STATUS +0x008 bewegt sich). Und **nur einmal pro Kaltstart**: nur bei GP5 = 0 (Netz-Ein).
   Steht schon `GATE` (ein Aus, das zurückfiel) oder `STBY`, wartet das Gate wie heute in der Schleife.
2. **Ein Reset im Aus** endet wie heute: GP5 `GATE`, das Gate wartet (dann in der alten Schleife, 2,4 W).
3. **Die Zeit bis zum Bild nach dem Tastendruck** wird länger: heute macht U-Boot nach der Taste direkt weiter; mit crust
   kommt ein voller Neustart davor (boot0, BL31, U-Boot noch einmal, ein paar Sekunden). Messen.
4. **Tastengefühl:** heute startet das Loslassen nach 50 ms Entprellung (U-Boot); crust entprellt 3 x 20 ms und weckt
   ebenfalls erst nach dem Loslassen (oder nach 3 s gehalten). Ähnlich, nicht gleich.
5. **Die IR-Fernbedienung weckt dann auch aus dem eingesteckt-Aus** (heute nur die Taste, die U-Boot pollt).
6. **Die Bluetooth-Fernbedienung** weckt weder heute noch dann: BT ist im Aus stromlos.
7. **HY310:** erst, wenn dort das Aus über crust gemessen und in der Defconfig ist (Abschnitt 3); bis dahin greift die
   Prüfung aus 1 und das Gate wartet wie heute.
8. **FEL-Kabel/USB gesteckt:** unverändert (das Kabel speist mit; Stromschnitt erst nach dem Ziehen).

### 4.4 Das Gespräch mit Marco - vor jeder Zeile Code

Ihm diese Punkte vorlegen, in einfachen Worten, und seine Antworten sofort ins Protokoll schreiben (Gedächtnis
"Freigaben festhalten"):

- a) **Was genau berührt wird:** nur `board/sunxi/board.c` im U-Boot-Fork. Die Warteschleife bekommt einen Vorlauf "crust
  fragen". Sonst nichts am Gate: Umgebung, Bypass, GP5-Regeln und LED bleiben.
- b) Ist ihm recht, dass das Gate dann nicht mehr in U-Boot wartet, sondern in crust? Von außen bleibt es gleich, nur
  0,3 W statt 2,4 W.
- c) Soll die IR-Fernbedienung die Box aus dem eingesteckt-Aus wecken dürfen (heute nein)?
- d) Soll ein gescheiterter Standby (GP5 `STBY`) auch über crust warten oder in der alten Schleife bleiben?
- e) Wie getestet wird: per FEL wie heute, am G-EU zuerst; Messpunkte in 4.5.

### 4.5 Messen (wenn Marco Ja sagt)

Per FEL, U-Boot-Abbild aus einem Versuchszweig, G-EU zuerst:
1. Netz aus/an (USB ab) -> dunkel, Wattmeter etwa 0,3 W; Taste -> Bild; Zeit Taste -> Bild gegen heute.
2. Taste beim Einstecken 3 s halten -> der Bypass bootet direkt (wie heute).
3. `h713_gate=0` -> bootet direkt (wie heute).
4. crust ohne `H713_POWER_OFF` (z. B. die heutige HY310-Konfiguration) -> das Gate wartet in der alten Schleife, **keine
   Reset-Schleife**.
5. Ein `poweroff` aus Linux -> crusts Aus wie in `doku/188` (unverändert).
6. IR aus dem eingesteckt-Aus (wenn Marco c) bejaht).

### 4.6 Referenzen

`doku/187` §1 (Stock-Kaltstart: GP2, `start_type`, fake poweroff), `doku/188` (Aus über crust, Messungen, `0xdea8`),
`doku/181` (Leistung Gate/Standby), `doku/179` (STBY), `doku/103-plan-einschaltgate.md` (Plan 103, das Gate),
`docs/uboot/power-gate.md`, `board/sunxi/board.c` (`h713_power_gate`, `h713_gate_wait`), TF-A `sunxi_scp_off.c` und
`sunxi_power.c`, crust `drivers/hdmi/sun50i-h713-hdmi.c` (`power_off_request`), `referenz/irrwege.md` (PL6 ohne VDD_SYS-Trennung).
Der Entwurf, aus dem dieser Abschnitt stammt: `arbeit/aus-pl6-20261010/plan-kaltstart-gate.md`.

## 5 Parallel: OSD und Konsole im Warp - eine eigene Sitzung

Marco will Einblendungen für lauter/leiser, Stumm und Fokus hoch/runter, "vernünftig aussehend", und die Konsole durch den
Warp (2.7a). Die Methode hat er dieser Sitzung überlassen.

- **Paket:** `arbeit/warp-konsole-20261010/` mit `AUFTRAG.md` (Ziel, Entscheidung, Aussehen, Bauweise mit Größenmaßstäben,
  Phasen, Tests, Bau-Rezepte geprüft), `REGELN.md` (was erlaubt ist und was nie), Worktree `repo/` auf `versuch/warp-konsole`
  ab `9f334b1`, `material/`, schreibgeschützte Bau-Eingaben `bau-eingaben/`, Kamera-Skripte. Start: neue Sitzung (Opus) in
  diesem Ordner, "Lies AUFTRAG.md und REGELN.md und arbeite danach."
- **Entscheidung:** OSD und Konsole sind im Warp weitere Texturen im Quellraum des Bildes. Sie gehen durch Trapez, Zoom
  und Projektionsmodus und stehen an der Wand wie das Bild. **Marco: "das Wechseln ist nicht akzeptabel"** (Ring <-> Warp
  zeigt heute kurz die Konsole). Darum hält der Warp mit `osd = on` die Video-Ebene, solange ein Signal da ist, auch ohne
  Trapez. Die Kosten werden gemessen und Marco gezeigt.
- **Wie Stock es macht** (Marcos Frage): Stock zeigt das HDMI-Bild nie über Android (NULL-Sideband, AP2k). Die Firmware
  zeigt es direkt, und Androids Oberfläche liegt auf der Hardware-Ebene **OSD-A (AFBD-Kanal 1)** darüber
  (Stock-Abzug `doku/64` §6, Entwurf AP3n in `umbau/re-apps/AP3n/`). Bei uns nimmt Kanal 1 keine Bilder an; am 23.09. dreimal
  am U-Boot-Prompt versucht, "das Tor liegt außerhalb der drei Blöcke" (`doku/131`). Darum mischt bei uns die GPU. Neu
  **TODO 2.41**: OSD-A öffnen wie Stock, als eigenes RE-Paket, getrennt vom Warp-Baum.
- **Was die Hauptsitzung tut, wenn das Paket abgibt:** `BERICHT.md` lesen, die Tests selbst laufen lassen und die Kompilate
  selbst prüfen (Gedächtnis "Agentenergebnisse selbst nachprüfen"). Dann die Patches auf einen Zweig, bauen, messen,
  `release/tor.sh && git commit`, nach `main`, Journaleintrag, TODO 2.7a/2.38/9.9 nachziehen. Das Paket schreibt selbst weder
  `doku/` noch `TODO.md`.

## 6 Danach, in dieser Reihenfolge

1. **7.19 Doku-Runde** (Marco: "Doku-Nachzug ist wieder gefordert"): dazu jetzt das Aus über crust (G-EU 0,3 W),
   `h713-power set`, die Vorgabe `short = poweroff`, `geuaus1`. README/Board-Liste, `docs/README.md`, `STATUS.md`, `ROADMAP.md`,
   `known-issues.md`, `boards/README.md`, RELEASES-Entwurf.
2. **2.40** R_WDOG-Warnung nach dem Aus als Info melden (Kernel `arisc_tfa_report`).
3. **5.17** build-all setzt nach einem Abbruch automatisch fort (keine neuen Schalter).
4. **5.20** ARISC-Wahl: Anzeige im Installer und `h713-arisc`.
5. **1.1a** Release-Neubau, **1.7a** Leck-Prüfung, **1.6** Forks (jetzt mit TF-A `1dd03734` und crust `d8a8d56`), **1.7** `main`.
   Jeder Push nur mit Marcos Ja.

## 7 Was man wissen muss (neu)

- **FEL-Tests mit crust:** der Kernel-Treiber lädt das crust aus `/lib/firmware` nach, wenn das laufende anders ist (0192).
  Für einen FEL-Test die Datei tauschen (mit Sicherung) und danach zurücklegen.
- **PL6 low ohne VDD_SYS-Trennung** setzt den SoC nach wenigen Millisekunden zurück (`referenz/irrwege.md`). Stock-Reihenfolge
  `0xdea8`: R_PRCM `0x260` Bit 0 löschen, `0x250` Bit 2 und 8 setzen, dann PL6.
- **systemd hält den SoC-Watchdog scharf** (16 s, `10-h713-watchdog.conf`), auch über ein `poweroff`; crust stoppt ihn im Aus.
- **FEL nach Umstecken:** meldete der PC `device descriptor read error -110`, half ein Neustart des PCs (kein Befund an der Box).
- **`geu-install.sh`** wartet jetzt auf die Partitionen (`udevadm settle`, `partprobe`); vorher "no partition" in Schritt 4.
- **Stock-OSD über HDMI** = Hardware-Ebene OSD-A, bei uns zu (Abschnitt 5, 2.41).
- **Warp-Bau** braucht `MESA_PREFIX=<mesa-stage>/usr/local` (nicht `<mesa-stage>`), sonst fehlt `EGL/egl.h`; die GL-Tests
  laufen nur auf dem Host (der Container hat keinen GLES-Treiber), Rezept in `arbeit/warp-konsole-20261010/AUFTRAG.md` §8.
