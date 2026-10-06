# Der Display-Pfad

## Wie es funktioniert

**U-Boot initialisiert das Panel nicht selbst.** Es lädt die Vendor-Firmware
`display.bin` in den MIPS-Coprozessor und startet ihn - *die Firmware* bringt
LVDS und Panel hoch. Sein Kopfkommentar sagt es:

> Only the bench-proven display clock and routing prerequisites belong here;
> **LVDS, TVCAP, HDMI, and INCAP remain out of scope.**

Der Kernel übernimmt später nur, was U-Boot hinterlassen hat. Sein
KMS-Treiber *„adopts the display U-Boot brought up and never touches timing,
the LVDS PHY or `rst_bus_disp`"* - die Abhängigkeit von U-Boot bleibt also
bestehen.

Konsequenz: **ohne den proprietären Blob kein Bild.** Weder bei ihm noch im
Kernel. Ein wirklich freier Display-Pfad bräuchte genau das, was in
`re/notes/` liegt - `DISPLAY-CHAIN-RE.md`, die 38-MB-IDA-Datenbank, die
Chroma-/ICSC-Kette vom Juli.

## Die MIPS-Register

Identisch mit denen im eigenen Kernel-Loader (`sunxi-mipsloader`, Patch 0010).
Beide Seiten haben denselben Loader gebaut, nur auf verschiedenen Stufen.

| | U-Boot | Kernel |
|---|---|---|
| Basis | | `MIPS_CTRL_BASE 0x03061000` |
| Status | `0x0306101c` | `+0x1C` |
| SharedMemAddr | `0x03061024` | `+0x24` |
| SharedMemSize | `0x03061028` | `+0x28` |
| Bootadresse | `0x03061030` | `+0x30` |

Firmware nach `0x4b100000`, Fenster 5 MiB, BSS ab `0x4b232c00`.

## Ablauf von `h713_disp init`

1. Artefakte von `mmc 1:2` laden - `display.bin`, `display_cfg.xml`,
   `database.TSE`, `pq_custom.TSE`, `projecttable.TSE`,
   `ProjectID_0xNNNN.TSE`, `LogoRegData.bin`
2. Takte und Routing vorbereiten
3. Panel-Konfiguration anwenden - bei uns 22 Registerfelder, 12 davon durch
   eine Record-Maske geschützt
4. Logo-Records abspielen (32 + 26 + 55 Stück, mit Pulsen und Verzögerungen)
5. Panel-Power: 550 ms Vorlauf, dann PF6 und PH16
6. Firmware-Identität prüfen
7. HDCP-Warteschleife entschärfen
8. Shared Memory aufbauen - 12 Spinlocks, 1224 Call-Einträge, 8 share_seq,
   5 Listen, 256 Records
9. MIPS-Reset in vier Stufen lösen:
   `0x00010000` → `0x00030000` → `0x00030001` → `0x00070001`
10. Auf den Bereitschaftszeugen warten (eigener Seed `0x4d495053`, nicht das
    CPU-Statusbit)
11. LVDS-PHY-Tail, Timing latchen

## Was er tatsächlich patcht

Die Sorge, er patche wild herum, trifft nicht zu. Drei verschiedene Dinge:

**Firmware-Instruktionen** - im normalen Pfad genau **zwei** Stellen, beide
dieselbe HDCP-Warteschleife. `apply_trace`, `apply_comm_trace` und
`apply_stability` sind Diagnose und laufen nur bei den jeweiligen
Unterbefehlen.

**Strukturen anlegen** - `init_share_seq`, `init_lists`, `init_record_pool`,
`seed_witness`. Kein Patchen, sondern das Aufbauen der cpu_comm-Strukturen,
die die Firmware erwartet.

**Hardware-Register** - die 22 Felder aus `panel_config`, die 113
Logo-Records aus `LogoRegData.bin`, Takte, Routing, Panel-GPIOs. Reine
Wiedergabe von Vendor-Daten.

### Warum die HDCP-Schleife entschärft werden muss

`Rx_HDCP14_LoadKey` pollt HDMI-RX `0x06840093` Bit 0 auf eine Bestätigung und
gibt nach `0x33` Ticks auf. Der Tick ist ein Software-Zähler aus dem
CP0-Compare-Interrupt - und so früh im Start sind Interrupts maskiert. Der
Zähler steht, der Timeout läuft nie ab, und aus einem Fehlerfall, den die
Firmware ausdrücklich überlebt, wird eine Endlosschleife.

Der Fix schreibt die Schleifengrenze auf null (`sltiu $v1,$v1,0x33` →
`sltiu $v1,$v1,0`), damit sie beim ersten Durchlauf aufgibt - derselbe Pfad
wie bei echtem Timeout.

Die Adresse hängt an der Firmware-Revision:

| Revision | Adresse |
|---|---|
| sein Board | `0x4b13d6f8` |
| unser Board | `0x4b13d0a4` |

Interessanter wäre die Frage, **warum** die Interrupts dort maskiert sind. Der
Vendor-Bootloader hat das Problem offenbar nicht, sonst hinge er genauso. Wer
das findet, braucht den Patch gar nicht.

## Unsere Werte

| | |
|---|---|
| ProjectID | `0x30` (seins: `0x34`) |
| Panel | **1920×1080** LVDS dual-port, htotal 2128, vtotal 1120, pclk 143,0016 MHz |
| `display.bin` | 1.256.216 Bytes, sha256 `16c74a28187f342d…` |
| Bootlogo | 1920×1080, 6.220.854 Bytes, sha256 `9684ef71483eb199…` - native Größe |
| HDCP-Stelle | `0x4b13d0a4` |

Die ProjectID stammt aus dem eigenen MIPS-Log:
`I/TSEXX [0] (base/TFDGroup.cpp 131) load group: ProjectID_0x0030`

Sein Hilfetext behauptet `0x34` für „dieses Board" - das gilt für seins.

## Erreichter Stand

```
H713 MIPS: firmware identity accepted (HY260 QZ713 V3.1)
H713 MIPS: HDCP key-load wait defeated at 0x4b13d0a4
H713 MIPS: firmware execution proven (witness overwritten)
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005
H713 MIPS: application readiness proven
H713 panel: 720p timing latched: 00000004 02f80550 02d00500 00140028
```

`ARM=5 MIPS=5` ist dieselbe Zustandsmaschine, die die eigene `STATUS.md` für
den Kernel mit „state machine 1→5 (Running)" angibt - nur hier im Bootloader.

## Das Panel-Timing ist falsch - und die Firmware repariert es

`H713 panel: 720p timing latched` ist **keine Messung**. `h713_mips.c:4816`
wählt fest `h713_panel_cfg_board_b`, die einzige Panel-Config in der Datei,
und die beschreibt sein Board: 1280×720, htotal 1360, vtotal 760, PLL N+1 = 36
für 61,71 MHz DCLK. Unser Panel will 1920×1080 bei 143,0016 MHz.

Sein eigener Kommentar bei Zeile 5442 hat es beobachtet, ohne es zu deuten:

> what it demonstrably does do is overwrite the TCON timing with 1080p once it
> runs […] It also leaves the panel on the tables' native 720p

Auf seinem 720p-Board ist das ein Rätsel. Auf unserem ist es richtig: die
Firmware liest `display_cfg.xml` und stellt das Panel auf seine echten
1920×1080. **Die MIPS weiß es besser als der Bootloader.**

Praktisch heißt das: die ARM-Sequenz latcht ein falsches Timing, die Firmware
korrigiert es beim Start. Deshalb läuft es trotzdem. Sauber ist es nicht - vor
dem MIPS-Start steht der TCON auf einem Timing, das das Panel nicht will, und
`h713_disp init` (ohne Firmware-Start) lässt es dabei.

## Das Bootlogo - gelöst (Nachtrag, geprüft am 11.09.2026)

**Dieser Abschnitt beschrieb einen Zwischenstand und war überholt.** Er ist hier
korrigiert, weil er zweimal zu falschen Schlüssen geführt hat.

Damals stand hier, die OSD-Ebene sei fest auf 1280×720 verdrahtet und ein
1920×1080-Logo passe nicht hinein. Das gilt nicht mehr. Die Ebene folgt heute
dem Panel:

```c
#define H713_DISP_OSD_WIDTH   (h713_disp_panel->width)
#define H713_DISP_OSD_HEIGHT  (h713_disp_panel->height)
```

Und die Logos sind mit Prüfsumme hinterlegt, je Board eines, weil das Bild in
Geometrie **und** Inhalt board-spezifisch ist - für den HY310 ausdrücklich
1920×1080 mit 6.220.854 Byte (`h713_vendor_bootlogos[]` in `h713_mips.c`). Der
Kommentar dort hält fest, warum eine einzelne feste Größe der falsche Weg war:
sie hat das jeweils andere Board zweimal abgelehnt, bevor überhaupt jemand die
Datei angesehen hatte.

Der verworfene Skalier-Blit (Nearest Neighbour auf 1280×720) bleibt verworfen.

## Was der Linux-Videopfad daraus macht

Cstengers KMS-Treiber `sun50i-h713-afbd` (Patches 0037/0038) **übernimmt**, was
U-Boot hinterlässt, und fasst Timing, LVDS-PHY und `rst_bus_disp` nie an. Sein
Probe liest die Geometrie aus der Hardware zurück - auf seinem Board
`adopting 1280x720, stride 5120`.

Auf unserem müsste derselbe Treiber daher **1920×1080** übernehmen, ohne eine
Zeile Änderung. Die U-Boot-Arbeit ist damit die Grundlage für den gesamten
Linux-Displaypfad auf dieser Hardware.

Der Videoweg darüber, seit 15.08. bei ihm laufend, geht **nicht** direkt vom
Decoder auf LVDS - die Behauptung hat er selbst zurückgezogen:

```
VE (Cedrus, H.264) → CMA-Puffer (NV12) → dma-buf → Mali-G31 als EGLImage
                   → Scanout-Carveout (Patch 0036) → AFBD → DE → TCON → LVDS
```

Page-Flip läuft über **`0x05600178`** plus READY-Bit, Vblank auf SPI 110. Genau
dieses Register steht in unserem Stock-Diff, und dort ist die Abweichung
korrekt: es trägt die Framebuffer-Adresse, bei Stock `0x78541000`, bei uns
`0x6c100000`.

---

*Nachtrag 06.10.2026: die folgenden drei Abschnitte standen nur im alten Journal-Master (Stand 15.09.) und fehlten in dieser Kopie; uebernommen beim Zusammenlegen (TODO 7.4).*


## Bootlogo mit laufendem MIPS: `h713_disp init … logo` (15.09.2026, ungetestet)

Marcos Wunsch vom 15.09.: das Logo **und** den korrekten Init. Die Lage vorher:

- `h713_disp auto 0x30 logo` (bootcmd bis 04.09.) zeigt das Logo, **parkt aber den MIPS als letzte Handlung**
  (`h713_disp_quiesce_mips_owner()` in `h713_disp_auto_logo()`). Der AFBD scannt das Logo endlos weiter, Linux
  findet eine tote Firmware: kein cpu_comm, kein SetSource, kein HDMI-Umschalten (doku/67 §1).
- `h713_disp init 0x30` (bootcmd seit 04.09.) startet die Firmware und laesst sie laufen, **veroeffentlicht aber
  kein Bild**: der OSD-Puffer bei `0x6c100000` behaelt, was das DRAM hielt - deshalb der weisse Schirm bis Linux
  die Konsole hineinschreibt.
- cstengers `h713_disp logo-live` (sein U-Boot `76eef86`, 04.09.) ist `auto … logo` ohne den Quiesce, plus DE-Replay,
  von ihm nie als Bootpfad benutzt ("expect contention").

**Warum die Linux-Konsole mit lebendem MIPS geht:** der KMS-Treiber macht in `h713_afbd_set_source()` nur vier
Dinge - `AFBD_SRC` (`0x05600178`) auf seinen Puffer, IRQ-Status (`0x168`) loeschen, `AFBD_CTRL` (`0x140`) Bit 0,
`AFBD_READY` (`0x144`) = 1. Kein DE-Replay, kein Timing-Latch. Genau das ist `h713_disp_commit_osd_frame_quiet()`
in U-Boot. Der ARM besitzt den AFBD, die Firmware alles dahinter (doku/96 §1).

**Neu (Fork `44817b2`, main `f4c18b0`):** `h713_disp init [id] [noboot|quiesce] [elog=N] [logo [file.bmp]]`.
Mit `logo`: (1) das Logo wird **vor** dem Record-Replay und der Panel-Einschaltfolge in den OSD-Puffer geschrieben,
damit das erste Bild, das das Panel je scannt, das Logo ist (Marcos Hinweis: der alte Logo-Boot war fuer einen
Sekundenbruchteil weiss - dort kam das Logo erst *nach* Firmware-Start und Panel-Power); (2) nach bewiesener
Bereitschaft wird aus dem noch geladenen BMP ein zweites Mal veroeffentlicht (falls Replay oder Firmwarestart den
Puffer angefasst haben) und Kanal 1 wie vom KMS-Treiber neu scharf gemacht; (3) kein Quiesce, kein DE-Replay;
(4) fehlt das Logo, nur eine Warnung, der Boot laeuft wie ohne das Wort. Dazu liest `h713_disp_publish_bmp` das
BMP jetzt vom Artefakt-Geraet (`h713_mips_dev`, per Partitionsname) statt vom festen `1:2` - auf Layout v3 ist
`1:2` die rohe U-Boot-Partition. Auf Stock liegt `bootlogo.bmp` in **beiden** Bootloader-Slots im FAT-Wurzelverzeichnis
(HY310: 6.220.854 Byte, SHA-256 `9684ef71…`, der Eintrag in `h713_vendor_bootlogos[]`), nicht unter `mips/`. Auf
unserem Layout muss es nach `/boot/bootlogo.bmp` (Wurzel von `hy310-boot`).

**Was noch fehlt:**
1. **Installer:** `bootlogo.bmp` steht in `vendorfiles.py` unter `MIPS_NOT_OURS` und wird nicht extrahiert. Das
   Paket: Extraktor kopiert es aus dem FAT-Wurzelverzeichnis nach `boot/bootlogo.bmp`, `h713-mkimage` bekommt einen
   6.220.854-Byte-Platzhalter in `hy310-boot`, `install` fuellt ihn, Golden-Ausgaben neu einfrieren, README-Texte.
   Ein halber Tag, kein Gerätetest fuer sich.
2. **Gerätetest** (ein Stromzyklus, beim naechsten Einspielen): Datei per `scp` nach `/boot/bootlogo.bmp` (die
   eigene liegt in `umbau/test-20260915/bootlogo-bootloader_a-root.bmp`, aus dem Vollabzug T gezogen), U-Boot
   mit `44817b2` im Abbild, am Prompt `h713_disp init 0x30 logo`, dann `run boot_emmc` (**nicht** `run bootcmd`,
   das enthaelt ein zweites `init`). Erwartung: Logo ab dem ersten Bild, kein Weiss, `0x0306101c` liest 1, Konsole
   loest das Logo ab, `h713-tv` schaltet auf HDMI. Geht das, wird `bootcmd` zu
   `h713_disp init ${h713_project} logo; run boot_${h713_boot}; run boot_net` (hy310.env, naechster U-Boot-Bau).
3. Wenn das Logo trotz allem verschwindet, sobald die Firmware laeuft (cstengers Warnung), ist die Antwort ein
   Foto und der elog, nicht ein weiterer Registerversuch: dann besitzt die Firmware diese Worte, und das Logo muss
   ueber den VidDec-Deskriptor oder gar nicht kommen.

**Gerätetest 15.09.2026, 16:47 bis 16:56 - bestanden.** Drei Läufe, U-Boot per `sunxi-fel uboot` aus dem RAM gegen
die Stock-Partitionen (Gerät auf Stock-Android, nichts geschrieben), UART über `umbau/test-20260915/uart-boot.py`,
Logs `umbau/test-20260915/logo-test-{164714,165240,165526}.log`. Am Prompt `setenv h713_mips_dev` (die Vorgabe zeigt
auf `hy310-boot`, auf Stock findet der Resolver `1#bootloader_a` selbst), dann `h713_disp init 0x30 logo`.
- Lauf 1: Logo abgelehnt ("unsupported BMP layout 1920x1080 … need 1280x720"): die Prüfung liest die Panelgröße
  aus `h713_disp_panel`, das vor `h713_disp_lookup()` noch auf Board B steht; mein Veröffentlichen lag vor der
  Auswahl. Wand: Rauschen (DRAM-Inhalt nach dem Stock-Lauf im OSD-Puffer). MIPS lief trotzdem, Scanzähler lief.
- Lauf 2 (Auswahl vor dem Veröffentlichen): "stock logo recognised … published at 0x6c100000", MIPS Status 1,
  **Marco: "ich hab das magcubic logo gesehen"**. Das zweite Veröffentlichen nach der Bereitschaft wurde abgelehnt
  (Prüfsumme über die feste 720p-Länge statt über die geladenen 6.220.854 Byte), harmlos, der Puffer behielt das Logo.
- Lauf 3 (Länge gemerkt, ohne Logo schwarz füllen): beide Veröffentlichungen angenommen, "boot logo up at
  0x6c100000 with the firmware running; MIPS reset=00070001 status=00000001 scan=016103e3", `0x05600178` =
  `6c100000`, `0x05600140` = `03001901`, Scanzähler `026000e2 -> 006402e6`, Puffermitte `0x6c4f5100` =
  `ffe9cb37` (Logo-Farbe). Fork `80eae99b99e`.
Damit ist bewiesen: **Logo und laufende Firmware schließen sich auf dem HY310 nicht aus** (cstengers Warnung greift
hier nicht), und das Logo liegt vor dem Einschalten des Panels im Puffer. Offen bleiben der Installer-Teil
(`bootlogo.bmp` nach `/boot`), die `bootcmd`-Umstellung und der Nachweis, dass Linux danach wie gewohnt auf HDMI
schaltet (erwartet, weil der Zustand nach `init … logo` derselbe ist wie nach `init`, plus ein gefüllter Puffer).

**Einspielen und Kaltstart 15.09.2026, 18:0x bis 18:2x - bestanden.** Abbild `h713-hy310-v0.7-dev` (Fork 71f6d76, Kernel
0fa3bf01, 44 Platzhalter) aus FEL mit `h713-install install … --small --dump h713-dump-T3 --vendor
umbau/build/extract-T-20260915 --ssh-key …` eingespielt (3 min, Stichproben gleich, Secure Storage unveraendert; Log
`umbau/test-20260915/install-v0.7-dev-18*.log`). Kaltstart per Stecker und Taste, UART passiv mitgeschnitten
(`umbau/test-20260915/boot-v0.7-dev-181134.log`): Gate, Taste, Artefakte von `1#hy310-boot`, "stock logo recognised …
published at 0x6c100000" **vor** dem Panel-Einschalten, "MIPS: released", "application readiness proven", zweites
Veroeffentlichen, "boot logo up at 0x6c100000 with the firmware running; MIPS reset=00070001 status=00000001", Kernel,
Debian-Login. Marco: "2-5 Sekunden nichts gesehen, dann war das Bild sichtbar fuer ein paar Sekunden, jetzt sehe ich das
Login" - kein Weiss mehr, die dunklen Sekunden sind SPL, U-Boot, Gate und Firmware-Start. Danach im System: hdmirx
Init-Sequenz vollstaendig (22 Aufrufe), ARISC EDID/HPD auf Port 0 abgeschlossen, cpu_comm-Rueckrufe registriert, MSP
laeuft, `h713-tv` aktiv ("kein Signal, Bild Konsole" ohne Quelle). Erster Anlauf des Einspielens mit `--full` verworfen:
er zieht einen NEUEN Vollabzug und ueberschreibt `emmc-full.img` im Zielordner (der alte Vollabzug T ist damit weg; seine
Extraktion liegt in `umbau/build/extract-T-20260915`, weitere Vollabzuege in `hy310-sicherung*`). Merksatz: zum
Einspielen `--small` plus `--vendor <Extraktion>`, `--full` nur, wenn ein neuer Vollabzug gewollt ist.

**Zweiter Kaltstart 15.09., 18:2x, nur lesend mitgeschnitten (`umbau/test-20260915/watch-20260915-182624.log`):**
identischer Ablauf (gate: cold start, Logo veroeffentlicht, MIPS laeuft, Login). Marcos Zeitmessung: **7 s bis das
Bild kommt, dann Logo keine 5 s, dann Konsole** - "das Bild muss eigentlich instantly kommen". Die 7 s sind SPL,
BL31, U-Boot, `starting USB … scanning usb for storage devices` (der USB-Scan vor dem Autoboot), `Hit any key to
stop autoboot: 2`, dann `init`: 1,2 MB display.bin plus 6,2 MB Logo von der eMMC, Record-Replay, 550 ms
Panel-Vorlauf, MIPS-Start und Bereitschaft. Die knapp 5 s Logo enden, sobald fbcon die Konsole auf das Panel legt.
Naechstes Paket dazu in doku/61 ("Bootzeit bis Logo"). Der HDMI-Erststeck-Fehler (Bild 1 s, dann Konsole; nach
Neustecken dauerhaft) ist im Automatikbetrieb reproduziert - der bekannte Punkt aus docs/known-issues.md. Das
"Abschalten beim HDMI-Abziehen" hat sich nicht bestaetigt (Marco: die Power-Taste erwischt; die naechste Gate-Zeile
sagt "cold start", also Netz weg). UART-Lehre: das Oeffnen des Proxys, waehrend U-Boot im Gate wartet, schickt
Zeichen an die Konsole und stoppt den Autoboot ("=>" ohne Boot) - den Mitschnitt vor dem Einschalten oeffnen, und
waehrend Marcos Tests nur lesen, nie senden (seine Ansage 15.09.).
