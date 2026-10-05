# 126 - HY300 Pro: vom ersten Bild zum Testabbild test4 (16./17.09.2026)

Journal zum zweiten Geraet eines Fremden (issue #1, Melder fightforlife; HY300 Pro, Android-10-Firmware vom 25.12.2024,
Fingerprint ADT-3 .../6245789, Projekt-ID 0x34, 1280x720 Single-Port-LVDS). Englische Zusammenfassungen stehen in den
Reviews `umbau/reviews/{E4,K1,U1b}.md` und den Analyseberichten `umbau/work/{A9,A10}/REPORT.txt`.

## 1 Ablauf

| Wann | Stand | Ergebnis |
|---|---|---|
| 15.09. | Probe-Lauf des Melders | Profil `hy300_pro` (partial) aus seinen Hashes; Testabbild test1 (v0.6-beta-Basis, Platzhalter) |
| 16.09. mittags | test1 | Install scheitert: drei Dateien fehlen (andere WLAN-Firmware, zwei PQ-Dateien) -> optionale Gruppen (main 95d0e9e) |
| 16.09. nachm. | test1 | Install scheitert: seine Dateien groesser als die HY310-Platzhalter -> **Paket P, Layout v4 ohne Platzhalter** (v0.8-beta) |
| 16.09. abends | test2 | Install ok, U-Boot haengt nach "FIFO status clear", Schirm weiss -> **Paket E4**: LogoRegData-Gruppen aus der Datei statt fester HY310-Offsets (Fork da74b89) |
| 16.09. 22:5x | test3 | **Kernel bootet, WLAN AP+STA, HDCP 2.2 laut Melder** - aber kein Logo (Panel bleibt "dim white"), gruene Streifen ab und zu, kein HDMI-Eingang (ARISC -110) |
| 17.09. nachts | Analysen A9/A10, Pakete K1/U1b | test4 im Bau (Zweig hy300-pro-ab) |

## 2 Befunde

**E4 (U-Boot, LogoRegData):** `h713_disp_prologue/timing/de[]` waren feste Byte-Bereiche der HY310-Datei (15 Deskriptoren,
15652 B). Seine Generation (13 Deskriptoren, 14388 B; identisch mit dem T08-Image im Archiv) liegt 0x30 tiefer mit kuerzeren
Bloecken; der feste Bereich de[6] traf DE-Variante 7 und lief 368 B ueber das Dateiende - 23 Records aus altem DRAM in CCU und
Display-Fabric = stiller Bushang. Fix: Gruppen aus der Blockkette der Datei {index, length, payload}, HY310 nachweislich
identisch (alle 22 Grenzen, Record-Stroeme), `h713_trace=1`, Groessenwaechter, hy300_pro-Preboot ohne `usb start`.

**A9 (ARISC, kein HDMI-Eingang):** unser Treiber (Patch 0091) traegt acht SRAM-Adressen der HY310-Firmware
(`v1.3-3-g293ff69`, Jul 2025). Sein Build `v0.8-4-g792f93b-dirty` (Dec 2024) hat denselben Code an denselben Adressen, die Daten
liegen 0x340/0x338 tiefer (der T08-Build derselben Git-Revision 0x344/0x33c - vier Byte anders). Folge: Nutzlast landet im
IR-Sample-Array statt im Pump-Puffer, der Klassifizierer verwirft den Frame; die Quittungssonde (65 x 0xff) landet im Stack
seiner Firmware; -110, Aux-Block nie zurueckgesetzt, hdmirx-Probe scheitert. Das -110 ist ehrlich. Der Agent schrieb mangels
OpenRISC-Support einen eigenen Disassembler (`umbau/work/A9/or1k.py`).

**A10 (Bild):** TCON-Timing dekodiert = seine panel_config.ini (1360x760/1280x720, 59,70 Hz bei 61,71 MHz). Die DE-Register
0x0525c000/0x0524c010 tragen Total-1 (aus dem Container bewiesen: de[0] = 2199x1124 = 1080p60); die 0x34-Zeile stand in
ini-Konvention -> DE 1361x761 gegen TCON 1360x760 (Schwebung ~8 s). Unser Latch setzt Bit 31 in 0x0588002c/0x05880030, die
Vendor-Gruppe loescht beide (Polaritaet 0/0 bei ihm, 1/1 beim HY310). Weitere Kandidaten, je eigener A/B: PLL-Override
43 -> 36 (Bench-Sweep) gegen seine CCU mit SSC fuer 43; LVDS-Bitsel erzwungen; Backlight-PWM Kanal 5 statt 2. "Dim white" ohne
Logo = kein gueltiger LVDS-Datenstrom; nichts im Log beweist Licht.

## 3 Pakete

- **K1 (Kernel 0091a, main):** Resolver mit zwei Signatur-Ankern und sechs festen Abstaenden, BSS/Stack aus dem Image als
  Grenze, acht Verweigerungsgruende, HY310-Werte als Erwartung geprueft, debugfs zeigt Version und Adressen. Modell
  `tools/arisc-fw-addrs.py` ueber drei Builds.
- **U1b (U-Boot, Zweig `hy300-pro-ab`):** Minus-eins in die Patch-Tabelle, beide Zeilen in ini-Werten, Polaritaet als Felder;
  HY310 im Modell 0 Records geaendert, 0x34: 02f80550 -> 02f7054f und die zwei Latch-Bits.
- Regel (Marco, 17.09.): eine Software fuer beide Boards - keine HY310-Sonderfaelle, alles main-faehig; Experimente auf dem
  Zweig, Testabbilder mit Tag, Merge nach Bewaehrung.

## 4 Offen
- Antwort des Melders auf test4: Bootzeile mit seinen Adressen (g_Data 0x16efc ...), `portmap: 0,1,2`, reset-edid rc=0,
  Logo sauber/gestreift/fehlt.
- Weitere A/Bs: PLL 43 vs 36, Bitsel, PWM-Kanal; elog-Ring-Adresse in cpu_comm ist HY310-spezifisch (kosmetisch).
- `rdinit=/init` in den bootargs (Kosmetik), `hy310-logs` englisch, Doku-Audit A8 (77 Befunde).
