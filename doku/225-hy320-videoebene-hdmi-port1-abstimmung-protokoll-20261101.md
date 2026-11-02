# 225 HY320: Videoebene, HDMI an Port 1, Abgleich gegen Stock - Protokoll

Datum: 01.11.2026. Gerät: der HY320 seines Besitzers (TEST-Abbild), Quelle eine Xbox One X. Augen und Ohren: der Besitzer.
Kernel-Patches `0336` - `0345`, U-Boot-Fork `ca8263484e1`, `fc66272cec5`. Beschreibung der Dauerzustände: `boards/hy320/README.md`,
`docs/subsystems/arisc.md` (DDC-Porttabelle), `docs/subsystems/hdmi-in.md` (Port der Buchse), `docs/kernel-patches.md` §27/27b.

## 1 Videoebene und Einblendungen

- `0x058c0000` (Spiegel `0x058c1000`): das `LogoRegData.bin` des Boards lässt `0x10000040` stehen; Bit 28 = nur der RGB-Kanal.
  `0x10000040` schwarz, `0x00000040` sichtbar, `0x10000000` schwarz (am laufenden Bild, Augen). In U-Boot gelöscht: Videoebene da,
  aber das Boot-Logo mit Nachzieh-Kopien, solange es stand. Jetzt gehört das Bit dem AFBD-Treiber (`0339`/`0340`, Fenster "mix"):
  gesetzt bei Probe und ohne Videoebene, gelöscht mit ihr. Logo sauber (Augen), `0x00000040` unter dem Xbox-Bild, `0x10000040` auf
  der Konsole.
- RGB über Video erst mit `0x051c0014` Bit 27 und `0x051c0028[5:4]` (`0x18000000`, `0x30`, die L018-Werte); keins allein. U-Boot
  schreibt sie. Beleg: Countdown über Farbbalken (Augen), die Lautstärke-Pille im Panel-Histogramm `0x051c0380..03fc` (~55000 Pixel).

## 2 HDMI: Port 1 und das nie geschriebene DDC-RAM

- Hot-Plug-Callback `0x38d780e2` meldet Quelle 4 (HDMI-2 = Port 1) beim Einstecken. `allwinner,hdmi-port = <1>` (`0337`/`0338`).
- Danach 640x480 ohne Ton: DDC-RAM `0x07091c00/1d00/1e00` (Gate `0x07091b04` zum Lesen zu) = EDID, Zufall, EDID. Der DDC-Schreiber
  der Hersteller-ARISC (v0.8: `0x11728`) bildet Maske -> Port über eine Tabelle (`0x15838`, logisch `00 01 03 02`) mit Byte-Lesen,
  die unter dem Little-Endian-Fenster `02 03 01 00` sehen: Port 1 nie geschrieben, 0 und 2 vertauscht. `0336` schreibt die vier
  Bytes in der Ordnung, die die Firmware liest. Ergebnis ohne Handarbeit: 1920x1080p60, 48 kHz PCM.
- HDCP: eine Streaming-App auf der Xbox spielt (Besitzer); keine 2.2-Sitzung, also 1.4. Später am Tag mit Netflix: **2.2-Sitzung
  steht** (`0x422 = 0x01`, Firmware "port2 HDCP_base:0x6840000 HDCP Process cost tick:676").
- 4K: 3840x2160p24 von der Xbox gefangen und skaliert (EDID mit 4K30 als erster Timing), die Xbox kehrt aber nach 2..4 s selbst
  auf 1080p60 zurück. 4K50/60: die gesperrten TSE-Sätze im Speicher freigeschaltet, Y420-Block (VIC 96/97) und HF-VSDB ins EDID -
  die Xbox sendet, INCAP rastet nie ein. Alles zurückgesetzt.
- Warum die Xbox von 4K24 zurückkehrt (Abtastung alle 50 ms: HPD-Register `0x07091014`, DDC-Gate, Signal, HDCP-Sitzung; drei
  Versuche): HPD bleibt stehen (`0x5`), die 2.2-Sitzung steht während der ganzen 4K24-Phase, das Signal bleibt gerastet - der
  Wechsel zurück geht von der Xbox aus. Mit einem EDID, das 4K nur bei 30 Hz anbietet, schickt die Xbox trotzdem 4K24 und zeigt:
  "4K wird bei 60 Hz nicht unterstützt, HDR10 nicht, Dolby Vision nicht". Die Oberfläche der Xbox will 4K nur mit 60 Hz; 4K30
  sendet sie gar nicht. Ohne 4K60 im Empfänger (s. o.) bleibt 1080p60.

## 3 Abgleich gegen Stock

| Thema | Befund | Folge |
|---|---|---|
| Ton | Line-Out bei uns stumm (`0x02030310` LMUTE/RMUTE 0), Stock: an, Mono-Differential, `speaker_vol 0x1a`, HP `0x80808f8c`. HP-Verstärker 5 s aus: Ton bleibt -> Lautsprecher am Line-Out | `0343`, `asound.state` gespeichert; Besitzer: "sauber" |
| `dacdrc_used 1` | vom Stock-Treiber gelesen, nie benutzt | nichts |
| Weißabgleich | gleicher Mechanismus wie HY310, vier Namen an anderen Adressen (`wb_r_gain` `0x4b1ff424`) | `h713-tv` mit Firmware-Tabelle; Cyan/Rosa/zurück gesehen |
| Lagesensor | STK8BA58, ID 0x87, 12 Bit, IRQ PB0; 0x0e antwortet nicht | `0341`/`0342`; 1 g gelesen; Achsen offen, `h713-keystone-auto` am Gerät aus |
| NTC | Stock liest GPADC 1 nur bei LRADC_DATA0 ≤ 5, hier 63; Kanal 1 streut 1313..1526 | `0344` (Kanal, kein `ntc_num`) |
| Lampe | PWM-Kanal 5 = `d_pwm5`, nur PG7 = Bluetooth-UART-RX; PWM-Block 0; Stocks Backlight-Pfad (PWM 3) ohne Pad | `0345` (Kommentare); PB4 als PWM2 ohne Beobachter getestet |
| Warp | 1080p60 durch die GPU: 60 fps, 2 ms/Bild, `check` 0 Abweichungen; starkes Trapez flüssig (Augen) | nichts |
| Ein/Aus | `poweroff` -> rote LED -> Taste -> Logo -> Bild | kein Standby (Hersteller-ARISC) |

## 4 Offen

NTC ja/nein (Kaltstart-Reihe), PB4/PB5 als Dimmer mit Beobachter, Achsen des Lagesensors (drei Lagen), andere Quellmodi als
1080p60, IR-/BT-Fernbedienung (keine vorhanden), Webcam-Mapping (keine Kamera vorhanden).
