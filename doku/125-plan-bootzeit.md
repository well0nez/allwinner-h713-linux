# 125 - Bootzeit bis zum Logo, und USB ohne `usb start`

Angelegt 15.09.2026, abends. Marcos Vorgabe: das Bild muss sofort kommen, `usb start` in U-Boot ist ein Hack
(der Kernel muss USB selbst hochbringen), keine Workarounds ausser Stock macht es genauso oder es geht nicht anders.
Kein Commit ohne Absprache (Marco, 19:40). Stand der Checkouts: der Fork-Checkout `umbau/src/mainline/external/u-boot`
steht auf `e2fae2d` (Installer-Fragment `CONFIG_PREBOOT="usb start"`, Release-Fragment `CONFIG_BOOTDELAY=1`; lokal
committet 19:39:43, 24 s vor Marcos Ansage, **nicht gepusht**, `origin/h713-hy310` steht auf `d4b7979` = `v0.7-dev2`);
der Kernel-Nachtrag `0005a` liegt uncommittet im Checkout `umbau/src`. Beides wartet auf Marcos Entscheidung.

## 1 Gemessen am 15.09.

**Unser Stand `v0.7-dev2`** (Fork d4b7979: Preboot ohne `usb start`, `bootdelay` 0), Mitschnitt mit Zeitstempeln
`umbau/test-20260915/boottime-dev2-193348.log` (Stempel = Ankunft des Zeilenumbruchs davor, die Tastenwartezeit
liegt zwischen "gate: power key" und "Net:"):

| Schritt | Zeit |
|---|---|
| SPL-Banner bis Gate ("waiting for power key") | ~1,9 s (SPL, BL31, U-Boot, Env laden) |
| Taste bis `init` startet ("Net:" / "loading vendor artifacts") | ~0 s (kein USB-Scan, kein Countdown mehr) |
| `init`: Artefakte von ext4 laden (1,2 MB display.bin 0,1 s; 6,2 MB Logo 0,4 s), Records, Panel-Vorlauf 550 ms | 1,5 s |
| **Taste bis Panel scannt das Logo** ("stock GPIO phase complete") | **1,6 s** |
| MIPS-Start bis Bereitschaft, zweites Veroeffentlichen | +1,0 s |
| `Starting kernel` | +1,0 s nach Bereitschaft (Kernel-FIT 7,6 MB in 485 ms) |
| Logo sichtbar, bis fbcon die Konsole aufs Panel legt | ~3 s |
| Kernel bis Login | 10 s |

Marco am Geraet: "das Logo kam sofort, aber war auch sofort wieder weg." Vorher (`v0.7-dev`, mit `usb start` und
`bootdelay` 2) hatte er 7 s bis zum Bild gemessen.

**Stock** (`re/captures/HY310-DEV/boot.log`, zwei Boots vom Maerz, Vendor-U-Boot 2018.05 vom 24.07.2025; die
Behauptung in doku/123, Stock sei am UART stumm, ist damit widerlegt - in den Kopien `umbau/src/doku/123`, `repo-neu/doku/123`
steht sie noch, beim naechsten Abgleich mitnehmen). Ausgewertet von Paket S1 (`umbau/work/S1/REPORT.txt`, Ghidra-Datenbank
des Vendor-U-Boots `umbau/work/S1/ghidra/vuboot`, Review `umbau/reviews/S1.md`). Wichtigste Korrektur: boot0 und
Vendor-U-Boot stempeln mit **derselben** Uhr (BL31 + OP-TEE dauern in beiden Boots exakt 94 ms, `[470]` -> `[00.564]`),
die U-Boot-Stempel sind also keine eigene Uhr ab 0. Der zweite Boot (ohne Host-Scan, laeuft bis Android) als Referenz:

| Schritt | Zeit ab boot0-Start |
|---|---|
| boot0 Start / DRAM 792 MHz fertig / "Jump to second Boot" (boot0 macht **nichts** mit Display oder USB) | 26 ms / 208 ms / 470 ms |
| BL31 + OP-TEE (94 ms), U-Boot-Banner, Relocation, Flash-Init | 0,47 bis 0,67 s |
| "zztest---usb power enable" = **PL3 (VBUS) an**, aus dem DTB-Knoten `/soc/prj`, jeder Boot | 0,67 s |
| "usb burn from boot" bis "overtime … no usb exist": USB0 im **Geraetemodus**, 800 ms Warten auf ein Brenn-Tool, dann Abbau (Bedingung: `burn_key`=1, workmode 0, kein `key_burned`-Flag im Secure Storage - bei uns jeder Boot) | 0,70 bis 1,51 s |
| nur Boot 1: `usb reset` (nicht `usb start`) mit Host-Scan USB0/USB1 = u-disk-Auto-Update-Suche; laeuft nur, wenn RTC-GP2 (`0x07090108`) != 0xF (Boot 1: `rtc[2]=0x2`, Boot 2: `0xf`) | 0,90 s |
| Secure-Storage-Fehlversuche (widevine, ec_key) | 1,55 bis 1,59 s |
| **zuerst** LogoRegData.bin (15.652 B) und bootlogo.bmp (6.220.856 B in 48 ms, fatload aus der FAT der `bootloader`-Partition; bevorzugt `bootlogo.jpg`, dann `.bmp`) | ~1,60 s |
| panel_config.ini, display.bin (11 ms), display_cfg.xml, vier TSE-Tabellen | 1,66 bis 1,96 s |
| 546 ms Luecke = der Panel-Vorlauf, den wir als "stock power pre-delay 550 ms" nachbauen | 1,96 bis 2,50 s |
| **"Display fastlogo finish!"** - das Bild, vor dem Autoboot (`bootdelay=0`, kein `preboot` in der Stock-Env) | **2,50 s** |
| "List file under ULI/factory" = `fatls` auf der eMMC-Partition `private` (kein USB), scheitert | 2,50 bis 3,58 s |
| update part info / bootcmd / dts, "Hit any key to stop autoboot: 0" | 3,58 bis 4,06 s |
| "Starting kernel" | 4,06 s |

Stock hat das Bild also **2,5 s nach boot0-Start** (nicht "gut 3 s"; BROM-Zeit davor ist im Log nicht sichtbar), der Kernel
startet 1,56 s spaeter. Ohne die 0,8 s Brenn-Probe waere Stock bei 1,7 s. Unser Weg ist ab der Taste (1,6 s) schneller als
Stock ab Reset; was fehlt, ist die Zeit vor der Taste (1,9 s bis zum Gate) und dass fbcon das Logo nach 3 s wieder wegnimmt.
Was Stock anders macht und wir uebernehmen koennen: (a) **Logo zuerst** laden, vor display.bin und den TSE-Tabellen
(Stock beweist, dass die Reihenfolge sicher ist); (b) keine Pruefsumme - wir rechnen zweimal SHA-256 ueber 6,2 MB
(je ~0,1 s, `[340.771]`-`[341.174]` und `[342.914]`-`[343.020]` im dev2-Log), und unser ext4-Lesen des Logos braucht
~0,4 s gegen 48 ms fatload bei Stock - Lesen und Hashen getrennt messen. Was wir bewusst nicht kopieren: die Brenn-Probe,
die `ULI/factory`-Suche, den Host-Scan. Was wir zusaetzlich bezahlen: den MIPS-Bereitschaftsnachweis (~0,6 s, Stock
prueft nichts und druckt nur "finish"); das ist unser Schutz gegen das Ueberschreiben des Logos beim Firmware-Start.
Offen (S1 §5): 6.220.856 gegen 6.220.854 Byte beim Logo-Lesen (alle unsere Kopien haben 6.220.854; Aufrundung des
Vendor-Loaders oder andere Datei im Maerz), und ob Stock die MIPS in der 546-ms-Luecke freigibt (S1 §5.3).

## 2 Befund `usb start`

Ohne `usb start` im U-Boot-Preboot findet Linux an keinem der sechs USB-Ports ein Geraet (nur Root-Hubs); die
interne Kamera (Realtek 0bda:5803 an EHCI1 `0x04200000`, doku/10) fehlt, `/dev/video0..1` sind nur der HDMI-Eingang.
Mit `usb start` (Boot 18:11) war sie da. Ausserdem meldet sich das Installer-U-Boot ohne `usb start` nicht als
USB-Laufwerk (drei Fehlversuche, Host: "Cannot enable … unable to enumerate"). Stock tut im Bootloader
"usb power enable" plus den Brenn-Detect auf USB0, manchmal einen Host-Scan; der Stock-Kernel bringt seine Ports
aber selbst hoch. Paket U1 (Opus, `umbau/work/U1`) sucht, was `usb start` fuer EHCI1/PHY1 hinterlaesst, das unser
Kernel mit unserem Geraetebaum nie programmiert; Paket S1 (`umbau/work/S1`) wertet die Stock-Logs und das
Vendor-U-Boot aus. Zwischenstand des Installers: `CONFIG_PREBOOT="usb start"` nur im Installer-Fragment
(gebaut, `umbau/build/uboot-installer-usbstart/`, damit lief das Einspielen von `v0.7-dev2` sofort).

**Ergebnis U1 (20:0x, `umbau/work/U1/REPORT.txt`, von mir im Quelltext nachgesehen):** ein einziges fehlendes Register-Bit.
Die HCI-PHYs kommen mit gesetztem **SIDDQ** (Bit 3 von `pmu + 0x10`, also `0x04101810`, `0x04200810`, `0x04300810`)
aus dem Reset, d. h. abgeschaltet; der Kernel-PHY-Treiber loescht das Bit nur, wenn die SoC-Konfiguration
`.hci_phy_ctl_clear = PHY_CTL_SIDDQ` traegt - unser Patch 0005 hat das fuer den H713 nicht (`phy-sun4i-usb.c:1022-1029`),
der H616 daneben schon. U-Boots `usb start` loescht es (unser Fork, `sun50i_h713_cfg` mit `.hci_phy_ctl_clear`, Commit
e4ab8f511fb - dessen Kommentar sagt sogar, der Kernel-Eintrag verlasse sich auf einen Bootloader), und der Vendor-Kernel
loescht es selbst (`open_clock` 0xc066b4d8, `pmu+0x10 &= ~8`, aus `sunxi_insmod_ehci` 0xc066307c vor `usb_add_hcd`;
IDA-Datenbank `analyse/ida/db-audio-vmlinux`). Also genau der Fall "Stock macht es genauso": der Fix gehoert in den
Kernel, eine Zeile im PHY-Treiber. Vorbereitet, **nicht committet**: `0005a-phy-sun4i-usb-h713-clear-siddq-on-the-hci-phys.patch`
im Checkout `umbau/src` (Nachtrag, 0005 bleibt byteidentisch), Kernelbau laeuft. Ausgeschlossen: VBUS (PL3/PB5 schaltet
`h713_poweron_lines()` unabhaengig von `usb start`), Takte/Resets (Kernel- und U-Boot-CCU decken sich), `dr_mode`
(`usb_add_hcd` erzwingt Host-Modus am PHY). Nebenbefunde: `.pmu_enable_bit0` aus 0005 ist wirkungslos (`sun4i_usb_phy_passby`
setzt dasselbe Bit), doku/10 Zeile 150-154 behauptet faelschlich, Patch 0001 decke CCU-Bit 29 ab; die Kamera muesste bei
uns als Bus 2 erscheinen, nicht Bus 1. **Beweis am Geraet** (vor dem Neubau moeglich): `0x04200810` lesen - Bit 3 gesetzt
ohne `usb start`, geloescht mit; nach dem Fix aus Linux ohne `usb start` geloescht, auch `0x04300810`. Werkzeug dafuer:
`umbau/work/U1/mmio/mmio-rd` (6 KB, aarch64, per UART-Base64 uebertragbar).

**S1 bestaetigt die Stock-Seite:** der Vendor-Bootloader programmiert auf dem Boot, der Linux erreicht, keinen EHCI/OHCI-Host
(kein `usb start`, kein Scan; nur PL3 an und die abgebaute Geraetemodus-Probe), und der Stock-Kernel bringt seine Ports selbst
hoch (`clk_summary`: bus-ehci1/2, bus-ohci1/2, usb-ohci1/2 an; Kamera an `4200000.ehci1-controller/usb1/1-1`). Ein
Host-Scan im Bootloader ist also keine Voraussetzung - genau die Luecke, die 0005a schliesst. Kernel mit 0005a gebaut
(20:16, `umbau/src/mainline/build/out/h713-kernel.fit`, `phy-sun4i-usb.o` traegt das Flag). **Beweis am Geraet, 20:4x, Marco auf
`v0.7-dev2` (kein `usb start`, kein Fix), aus Linux per python3/`/dev/mem`:** `0x04101810`, `0x04200810`, `0x04300810` = je `0x8`,
also genau das SIDDQ-Bit gesetzt, alle drei PHYs aus (kein Busybox im Rootfs, python3 ist drin). `v0.7-dev3` gebaut (20:29,
`umbau/build/release-v0.7-dev3`: Fork e2fae2d + Kernel-FIT 63ac2010 mit 0005a, ALL GREEN). **Eingespielt 20:5x aus FEL
(`--small`, Abzug `h713-dump-T5`, Log `umbau/test-20260915/install-v0.7-dev3-*.log`), Kaltstart, und am Geraet bestanden:**
dieselbe python3-Zeile liefert `0x04101810`, `0x04200810`, `0x04300810` = je `0x0` (SIDDQ frei), `/dev/video0..3` - die
USB-Kamera ist ohne `usb start`, ohne `usb reset`, ohne Scan da. Der Kernel bringt USB selbst hoch, wie bei Stock.
Damit ist Plan-Punkt 1 erledigt; offen ist nur noch das Committen (0005a nach main, e2fae2d pushen) mit Marcos Okay.

## 3 Weitere Befunde

- Ein Stoerzeichen (`~`) auf der Leitung hat einen Start am U-Boot-Prompt enden lassen (`=> ~` im Log): U-Boot
  bricht den Autoboot ab, sobald irgendein Byte im Puffer liegt, auch bei `bootdelay` 0. Vorschlag: Stopp-Sequenz
  (`CONFIG_AUTOBOOT_KEYED` + `CONFIG_AUTOBOOT_STOP_STR`, dazu `CONFIG_AUTOBOOT_FLUSH_STDIN`, das den Puffer vor dem
  Lesen der Sequenz leert - alle drei in `boot/Kconfig` dieses U-Boots vorhanden) statt "irgendeine Taste"; `bootdelay`
  bleibt 1 (Marco). Noch nicht gebaut, noch nicht abgesprochen.
- Die zwei Kernelzeilen `hy310-cpu-comm: error -ENXIO: IRQ index 1/2 not found` (Marco 21:0x: "noch nie gesehen").
  Befund: die Msgbox ist da und faehrt (Block `0x03003000`, drei Baenke, unser cpu-comm-Treiber, nicht der Mainline-Msgbox-Treiber).
  Stock-DTB (`legacy/reference/stock_dts/hy310-board.dts:1403`): `msgbox@3003000`, drei Baenke, drei Leitungen SPI 46/109/108,
  `msgbox_amp_counts = 3`; der Vendor-Treiber `sunxi_msgbox_probe` (IDA, 0xc07db360) fordert **alle** `of_irq_count` Leitungen
  mit einem Handler an, der alle Baenke bedient. Unser Geraetebaum: `cpu-comm@3003000` mit **einer** Leitung (0024 von
  cstenger: SPI 21 und 0x400; unser 0024a: 46 und 0x1000, aber weiter nur eine Leitung, obwohl der Patchkopf 46/109/108 nennt);
  unser Treiber (0014a, April-Fix) fragt drei Indizes ab, der Kern druckt fuer Index 1 und 2 den Fehler, der Treiber macht mit
  "1/3 msgbox IRQs registered" weiter. Seit wann: in jedem Mitschnitt seit 10.09. (`analyse/boot/v4-kaltstart-20260910.txt`),
  vorher im loglevel-7-Wust unsichtbar, seit dem leisen v0.7-Boot (loglevel 4) sind es die einzigen Fehlerzeilen. Schadet es:
  kein Hinweis - RX von der MIPS kommt ueber Bank 0 auf SPI 46, keine cpu_comm-Timeouts in den ausfuehrlichen Logs, alle
  MIPS-Aufrufe laufen. Richtig nach Stock waere: drei Leitungen im Geraetebaum **und** ein Handler, der alle drei Baenke
  bedient (unserer draint nur Bank 0 und gibt sonst IRQ_NONE zurueck - mit den Leitungen 109/108 allein waere das ein
  "nobody cared"-Abschalten, kein Absturz). Eigenes kleines Paket mit Geraetetest (`/proc/interrupts` 46/109/108 zaehlen).
  Nebenbefund: unser `watchdog@2051000` nennt SPI 46 (Stock: SPI 53); der wdt-Treiber nutzt keinen IRQ, also folgenlos,
  aber im selben DT-Patch zu korrigieren.
- Marco: "bootet das System jetzt auch ohne USB nicht, aus U-Boot heraus" - noch unklar, klaeren wenn er zurueck ist.

## 4 Plan (Reihenfolge)

1. ERLEDIGT 15.09. 20:5x: SIDDQ-Fix 0005a, am Geraet bewiesen (Register vorher `0x8`, nachher `0x0`, Kamera da);
   `usb start` ist aus dem Produkt-Preboot raus (seit d4b7979), im Installer bleibt es (ums braucht den Host-Stack).
   Offen: Commit von 0005a nach main und Push von e2fae2d, nur mit Marcos Okay.
2. ERLEDIGT (Marco, 16.09. 01:0x): die Konsole bleibt auf dem Panel, keine Debatte; fbcon nach dem Logo ist gewollt.
2a. ERLEDIGT 16.09. 02:2x (v0.7-dev7, Fork uncommittet): der Boot-Pfad hasht das Logo nicht mehr (vorher 2 x 105 ms fuer die
    Zeile "stock logo recognised"); die Identitaet rechnet nur noch `panel-test vendor-logo` bei Bedarf. Reihenfolge bleibt
    (Marco: Logo nach display.bin ist ok). Gemessen dev7 (`umbau/test-20260915/boot-dev7-021733.log`): Taste 66,2 s, Countdown
    1 s, display.bin 1,2 MB in 0,1 s, Logo 6,2 MB in 0,40 s (ext4-Lesen, kein Hash mehr), Panel scannt 68,6 s (2,4 s nach der
    Taste inkl. 1 s bootdelay), Kernel 70,5 s, Login 81,0 s. **Naechster Hebel: MMC-Geschwindigkeit in SPL und U-Boot.** Unsere
    Lesungen laufen mit 12-15 MB/s (Stock fatload 130 MB/s), und der SPL braucht 1,6 s vom "Trying to boot from MMC2" bis BL31
    (Stock-boot0: 0,4 s bis "Loading boot-pkg Succeed"). Befund 02:4x: Linux faehrt die eMMC in **HS400** ("mmc0: new HS400 MMC
    card", `dd` 154 MB/s); der Vendor-U-Boot auch ("Best spd md: 4-HS400, freq 200000000, Bus width 8"), boot0 mit HSSDR52 8 bit.
    Unser U-Boot: Mainline `sunxi_mmc.c` kann nur HS-52 mit 8 bit (`host_caps = 8BIT | HS_52MHz`, `f_max` 52 MHz, Kommentar im
    Treiber: HS400 nicht unterstuetzt), und selbst davon kommen nur 12-15 MB/s an; der SPL ist mit 1,6 s fuer ~1 MB noch weit
    darunter. Paket dafuer (nach v0.7 oder davor, Marcos Wahl): (a) messen, mit welchem Takt/Modus SPL und U-Boot wirklich
    lesen (`mmc info`, Takt der mmc2-Quelle im CCU), (b) ext4-Lesepfad (Blockgroesse) und SPL-FIT-Ladepfad, (c) HS200/DDR52 im
    Treiber nur, wenn (a) und (b) nicht reichen. Hash-Entfernung committet: Fork `1562527` (gepusht).
    **(a) gemessen 02:5x am U-Boot-Prompt** (`umbau/test-20260915/mmc-bench-*.log`): `mmc info` sagt 52 MHz HS 8 bit, das
    CCU-Register `0x02001838` hielt `0x8100000b` (Mux 1, M=12) - auf dem H713 haengt an Mux 1 fuer MMC2 aber pll-periph0-800M
    (400 MHz effektiv), der Treiber rechnet mit 600 MHz wie beim H6: die eMMC lief mit **33 MHz**. Roh 8 MiB in 0,59 s = 14 MB/s,
    ext4load 15 MiB/s (das Dateisystem kostet nichts). Fix im Fork (`sunxi_mmc.c`, H713-Zweig wie beim A523): Register jetzt
    `0x81000007` (M=8, 50 MHz), roh 0,42 s = 20 MB/s, ext4load 22,5 MiB/s; Logo 396 -> 264 ms, Kernel 485 -> 323 ms,
    Installer schreibt in 2 statt 3 min. Deckel ist jetzt das PIO-Lesen (kein DMA im Mainline-Treiber; Kernel hat IDMAC,
    154 MB/s). Marco fragte nach DMA: eigenes Paket, Deskriptorformat aus dem Kernel bekannt. (b) SPL 1,6 s: offen, Verdacht
    SD-Slot-Probe (mmc0) vor dem Laden von mmc2 - im SPL-Code nachlesen, Fehler dort heisst FEL.
    Fork-Commit `mmc: sunxi: H713 MMC2 runs off PERIPH0_800M` gepusht (03:0x). **Marcos Auftrag fuer den 16.09.:** (1) HS400
    (oder HS200) fuer U-Boot wie Stock - Vendor-U-Boot per RE (Ghidra-Datenbank `umbau/work/S1/ghidra/vuboot`, Strings
    "Best spd md: 4-HS400", Tuning "tunning data addr"), dazu Treibervergleich: Vendor-Kernel `sunxi-mmc` (Legacy-Patch 0006
    kennt DS_CLK_CTRL 0x10c und CLK_MODE_CTRL 0x054 fuer HS400 auf v4p5x+), Mainline-Linux `sunxi-mmc.c` (HS200/HS400 mit
    IDMAC, 154 MB/s bei uns), eventuell Vendor-U-Boot-Quellen online (lichee/brandy sunxi_mmc HS400-Pfad); PIO bleibt ohne
    DMA der Deckel. (1b) **DMA im U-Boot-Treiber** (Marco 16.09. 03:1x, ausdruecklich): IDMAC-Deskriptoren wie in
    `drivers/mmc/host/sunxi-mmc.c` des Kernels (Vendor-U-Boot nutzt sie auch); ohne DMA bringt HS400 wenig, mit DMA allein
    waeren bei HS-52 schon ~45 MB/s drin. Reihenfolge im Paket: erst DMA messen, dann HS200/HS400. (2) der SPL-Punkt (1,6 s,
    SD-Slot-Probe?).
    **Ergebnis 16.09. vormittags (Pakete M1 + M2, Opus, `umbau/work/M1`, `umbau/work/M2`, Reviews folgen):** M1 liefert
    IDMAC-DMA (jedes Register mit Fundstelle im Vendor-U-Boot `sunxi_mmc_do_send_cmd_common` 0x4a01db68 und im Kernel-Treiber,
    PIO bleibt Rueckfall und im SPL) und HS200 (Tuning liest nur den CMD21-Block, kein Muster-Schreiben wie der Vendor bei
    Block 0x5fc0); HS400 als Nachtrag begruendet ausgelassen (Strobe-Kalibrierdaten, im Kernel-Zweig auf einem zweiten Board
    instabil). M2: die 1,6 s sind NICHT BL31, sondern der SPL kopiert die eingebetteten FIT-Nutzdaten byteweise (memcpy aus
    lib/string.c nur wortweise bei 8-Byte-Ausrichtung beider Seiten, die FIT-Daten liegen 4 mod 8) bei abgeschaltetem Cache
    (SPL-Map: nur `dcache_disable`); Fix zwei binman-Zeilen (`fit,external-offset`, `fit,align 0x200`), 0 Byte Kopie.
    Fork jetzt 644feba (4fa6175 M2, 73dfed4 DMA, 644feba HS200). **v0.7-dev9 per FEL geladen (ohne Schreiben), am Prompt
    gemessen** (`umbau/test-20260915/fel-dev9-prompt-103922.log`): Takt-Register `0x81000001` (200 MHz), NTSR 2x-Modus,
    SAMP_DL Schritt 0, ext4load **87,6 MiB/s** (Kernel-FIT 7,6 MB in 83 ms, Logo 6,2 MB in 68 ms; vorher 323/264 ms), DMA-Register
    nach dem Transfer wieder 0, GCTRL ohne AHB-Bit, FTRGLEVEL 0x000f0000 und ein Setzen auf 0x20070008 aendert nichts.
    Der erste Befehl (`mmc dev 1`) war vom Stopp-Byte verstuemmelt, daher fehlen `mmc info` und der 8-MiB-Rohvergleich; der
    Nachweis der Datenkorrektheit kommt mit dem Kaltstart von dev9 (Kernel-FIT sha256 ueber bootm, Installer-Rueckvergleich).
    **Kaltstart dev9, 16.09. 10:5x, bestanden** (`umbau/test-20260915/boot-dev9-104526.log`; Einspielen mit Rueckvergleich ueber
    den neuen Treiber ok). Marco: "oha der war sofort gebootet". Zeiten (Ankunft der Zeile):
    | Schritt | dev7 | dev9 |
    |---|---|---|
    | SPL "Trying to boot from MMC2" bis BL31 laeuft (2. BL31-Zeile) | 1,61 s | **0,68 s** |
    | SPL-Banner bis U-Boot-Banner | 1,74 s | **0,81 s** |
    | Taste bis Autoboot-Zeile (Env laden usw.) | ~1,0 s (bootdelay 1 inkl.) | 1,0 s |
    | display.bin + Logo laden | 0,1 + 0,40 s | 0,11 + 0,07 s |
    | Taste bis Panel scannt das Logo | 2,4 s | **2,0 s** |
    | Kernel-FIT 7,6 MB | 264 ms | **84 ms** (86,6 MiB/s), sha256+ OK fuer Kernel und DTB |
    | Taste bis "Starting kernel" | 4,3 s | **3,5 s** |
    | Kernel bis Login | 10,5 s | 9,7 s |
    Die Rest-Luecke im SPL (0,68 s statt der von M2 vorhergesagten 0,27 s) ist das PIO-Lesen des 940-KB-FIT ohne Cache im SPL
    (M2 §5: D-Cache im SPL oder DMA im SPL waeren die naechsten Hebel, beides groesser). Datenkorrektheit: sha256 des Kernel-FIT
    und der DTB durch bootm nach DMA-Lesen bei HS200, Installer-Stichproben gleich.
    **M4 (D-Cache im SPL) fertig, Review `umbau/reviews/M4.md`:** nein - der echte SPL-Deckel ist 32768 B (eGON auf 8 KiB
    gerundet, Release-Split bei 32768, Partition 32 KiB; heute 30848 B, 1920 B frei), D-Cache braeuchte +2392 B, dazu
    Fallen bei FEL-Rueckkehr und BL31-Uebergabe. Gewinn ~0,11 s gegen ~0,09 s mit DMA (M3). I-Cache-Option (default aus)
    liegt in `work/M4`, nicht integriert. M3 laeuft mit dem 32768-B-Deckel als Auflage.
    **M3 (DMA im SPL) fertig und am Geraet bestanden, 16.09. 11:4x** (Review `umbau/reviews/M3.md`, Fork 4c7e49b: SPL nutzt
    den IDMAC-Pfad, Cache-Pflege nur bei laufendem D-Cache, IDMA-Fehler wiederholt per PIO mit UART-Zeile, b_max = Kette;
    u-boot-spl.bin 31984 B, eGON-Bild 32768 B; Guard `spl_size_ok` im Release-Skript). v0.7-dev10 Kaltstart
    (`umbau/test-20260915/boot-dev10-113504.log`): "Trying to boot from MMC2" bis BL31 **0,14 s** (dev9 0,68 s, dev7 1,61 s),
    SPL-Banner bis U-Boot-Banner **0,27 s** (dev9 0,81 s, dev7 1,74 s; Stock boot0->U-Boot 0,54 s), keine IDMA-Fehlerzeile,
    Kernel-FIT 84 ms, sha256+ OK, Login 9,6 s nach Kernelstart. Damit ist die Bootzeit-Arbeit fuer v0.7-beta abgeschlossen;
    Rest (SPL-eMMC-Bring-up ~0,06 s, FDT-Ausrichtung 1 ms, HS400, DMA-Schreibpfad-Test) nach dem Release.
    **v0.7-beta gebaut (16.09. 12:0x, 18 min 58 s von vorn, Repo 18c83f3, Fork 4c7e49b, Kernelbaum 64519542, ALL GREEN)**,
    Upload-Satz gepackt und geprueft (`umbau/build/upload-v0.7-beta`), GitHub-Entwurf angelegt (Draft + Pre-Release, Ziel main,
    10 Assets; Tag entsteht erst beim Veroeffentlichen). Offen bis Marco zurueck ist: dieses Abbild einspielen und die
    Abnahme fahren (Kaltstart mit Logo, Kamera, HDMI-Stecken), dann annotierter Tag v0.7-beta auf 18c83f3, Entwurf
    veroeffentlichen, repo-neu nachziehen, doku/61 aufraeumen.
    **Abnahme des finalen Abbilds 16.09. 13:0x bestanden** (`umbau/test-20260915/boot-v0.7-beta-130024.log`): Einspielen
    (Abzug T13), Kaltstart mit Logo (SPL->BL31 0,14 s, Logo ~2 s nach der Taste, sha256 OK, keine IDMA-Zeile), Kamera
    (`/dev/video2..3`), HDMI stecken nach dem Boot (direkte Freigabe 164 ms), ziehen/stecken (Bild zurueck bei 99,9 s).
    Tag `v0.7-beta` annotiert auf 18c83f3, Release veroeffentlicht.
3. Zeit vor der Taste: 1,9 s bis zum Gate, davon 1,6 s der SPL-Ladevorgang (MMC-Geschwindigkeit, siehe 2a).
4. GESTRICHEN (Marco 16.09.: nicht gewuenscht): Stopp-Sequenz fuer den Autoboot. IRQ-Zeilen: doku/61 B nach dem Release.
5. Erst dann `v0.7`.
