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
