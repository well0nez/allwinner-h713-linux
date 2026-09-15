# A - Board-Abnahme (Board-Slot 1, Hauptsitzung)

## Ausrollen

| Zeit | Schritt |
|---|---|
| 21:58 | `KERNEL_CONFIG=netboot build/build.sh kernel` → `h713-kernel-netboot.fit` (7 831 804 B), Baum `linux-6.18.38-162ea031fab0…` |
| 22:01 | Sperre gesetzt, TFTP geprüft (`[::]:69` lauscht), FIT gesichert nach `tftp/h713-kernel-netboot.fit.bak-20260906-vorA` |
| 22:01 | Module: `make modules_install INSTALL_MOD_PATH=build/modroot.neu` (25 Module), Board-Sicherung `/lib/modules/6.18.38.bak-20260906-vorA`, dann per `tar` über SSH ins NFS-Root, `depmod -a` |
| 22:02 | neue FIT nach `tftp/`, `sonoff_ctl restart --host 192.168.8.179` |
| 22:03 | Board erreichbar (43 s), `/proc/uptime` 24,77 s = echter Kaltstart |

Das Löschen des alten Modulverzeichnisses schlug fehl (`Directory not empty`) - NFS-Silly-Rename, weil die
Module geladen sind. Statt zu erzwingen: darüber entpackt, `.nfs*` entfernt, Bestand geprüft (genau 25 `.ko`,
keine Reste; die drei Vendor-Audio-Module aus unserem verworfenen 0050 sind weg).

## Abnahmepunkte

1. **Kaltstart mit dem neuen Kernel - grün.** `Linux h713-arm64 6.18.38 #1 SMP Sun Sep 6 19:58:43 UTC 2026`.
2. **Konsole auf der Wand - grün.** `sun50i-h713-afbd 5600000.display: [drm] adopting 1920x1080, stride 7680,
   source 6c100000` - genau der Gutfall, den A vorhergesagt hat. Die Handanpassung an 0078 (Wegfall der
   1280×720-Zusicherung) war also **notwendig und richtig**: ohne sie hätte der Probe mit `-ENODEV` abgebrochen.
   Foto `A/A-01-konsole.jpg` (Textblock oben links, Rest schwarz - ROI-mean 8,2 ist deshalb erwartungsgemäß niedrig).
3. **Zweite Plane - grün.** `modetest` gibt es auf dem Board nicht; stattdessen `/sys/kernel/debug/dri/1/state`:
   `plane[34]: plane-0` (Primary, XR24, 1920×1080, `dma_addr=0x76d00000` = unser Carveout aus 0049) und
   **`plane[38]: video-0`** (Overlay, `crtc=(null)`, `fb=0`). **Plane-ID für Paket D ist 38.**
   Zusatzbefund für D: die Plane meldet `color-encoding=ITU-R BT.601 YCbCr`, `color-range=YCbCr limited range`.
4. **Sequenz aus Nachtplan §1 - ROT.** Siehe unten.

## Der Fehlschlag und seine Ursache

Die Sequenz lief formal durch: `prep_after_boot.sh` sauber (cpu_comm 4/4 Ready, alle RPCs mit RETURN),
`SetSource(3)` (AppTop-Quelle `0x4B8C8E5C` = 3), `arisc_edid_init.sh` (Zuspieler `connected`),
`viddec_descriptor.py set` **genau einmal** (AppTop-Zustand `0x4B8C8D80` 0 → **4**), `afbd_source0.py on`
(Y0 `0x4C3EF000`, C0 `0x4C9EC000`, Gain `0x144C0000`, Selektor `0x39000000`, C-Stride `0x0F00`).
Die Firmware meldete im elog sogar `EnterWaitingPipeLineReady` → `NotifySignalChange` →
`signal_id = kHalSignalID_1080P` → `EnterSignalSteady`.

**Trotzdem kein Bild:** die Wand zeigte ein gleichmäßiges Grün (`A/A-02-bild.jpg`), `chroma_stat.py` gab
Y = Cb = Cr = 0,0 und der Flip-Zeiger `0x05600320` stand fest auf `0x4C7ED000`. Das ist der **leere Ring** -
der Anzeigepfad lief, die Capture schrieb nicht.

Der Registervergleich gegen den Abzug von 21:47 zeigt es eindeutig: **der gesamte INCAP-Block liest `0x00000000`**,
auch `0x06940000` (vorher `0x00003a7b`). Ein Block, der durchgehend Null liest, ist nicht untätig, sondern
**ungetaktet**. Bestätigung: `pm_genpd_summary` meldet `TVCAP off-0` und `TVFE off-0`.

**Ursache:** `h713-tvcap` (Modul geladen, Treiber registriert) bindet auf `allwinner,h713-tvcap` - und dieser
**DT-Knoten fehlt im neuen DTB**. `strings` auf die FITs: alte FIT 1 Treffer, neue FIT 0 Treffer.
Der Knoten stand **in keinem Patch der Serie**, sondern nur als **Handänderung direkt im alten Baubaum**
`build/linux-6.18.38-d9f9ca8b…/arch/arm64/boot/dts/allwinner/sun50i-h713.dtsi`. Ein neuer Baum hat ihn deshalb
nicht. Das ist kein Fehler von Paket A: A hat cstengers `0087-EXPERIMENT-…-bring-up-tvcap-for-hdmi-rx`
auftragsgemäß **nicht** übernommen (EXPERIMENT), und unsere eigene Fassung war nie gesichert.

## Die Behebung (kein Workaround)

Neuer Patch **`0096-arm64-dts-h713-add-the-tvcap-bringup-node.patch`**, in `series` hinter 0090 aufgenommen:
er trägt genau den Knoten, der bisher nur im Baubaum stand - `tvcap@50c0000`, `allwinner,h713-tvcap`,
vier Takte (`CLK_BUS_TVCAP`, `CLK_BUS_CAP_300M`, `CLK_VINCAP_DMA`, `CLK_TVFE_1296M`), `power-domains = <&ppu 1>,
<&ppu 2>`, **kein Interrupt** (GIC_SPI 110 gehört h713-afbd) und **keine Panel-Eigenschaften** (tvtops
`panel_bl_en` = PB5 ist Hintergrundbeleuchtung und Lüfter). Danach Neubau und zweiter Abnahmelauf.

**Lehre für den Rest der Nacht:** ein Zustand, der nur in einem Baubaum lebt, überlebt den nächsten Bau nicht.
Alles, was das Board zum Laufen braucht, gehört in `series`.

## Hänger 22:37 (protokolliert nach Regel 5)

Lauf mit dem Kernel 0096+0097, nach Kaltstart 22:35:09. `prep_after_boot.sh` sauber, `SetSource(3)` RETURN
378 ms, danach `arisc_edid_init.sh` - der Zuspieler blieb aber **`disconnected`**, `0x06940928` stand auf
`0x600200F0` (statt `…0438`: keine gültige Signalgeometrie) und `0x06940104` zählte nicht.

`arisc_hdmi.py status` zeigte die Ursache: **`FIFO user1 P0/P3 = 4 / 0`** - vier unverarbeitete Nachrichten in
der Sendewarteschlange von Port 0, und `RPM-Puffer 11 20 00 00 …` = der Unterbefehl `0x2011 ResetEDIDModule`
lag noch unbearbeitet. Die ARISC hat Port 0 in diesem Boot also nicht mehr abgearbeitet. Ein anschließendes
`PullHotPlug UP` brachte den Zähler nicht hoch; unmittelbar danach war das Board per SSH nicht mehr erreichbar.

**Nicht überinterpretieren:** an einem hängenden Gerät ist die stehende Warteschlange kein Beleg gegen das
Poll-Ergebnis von 22:25 - sie kann genauso die Folge des Hängers sein. Die Puls-Messung wird deshalb in einem
sauberen Lauf wiederholt, bevor Paket B den Puls streicht.

## Zweiter Abnahmelauf 22:38-22:42 - A ist grün

Kernel 0096+0097 (FIT `8ffceb0b…`, Baum `a9eb6d69…`), Kaltstart 22:37:35.

| Zeit | Schritt | Ergebnis |
|---|---|---|
| 22:40:21 | `prep_after_boot.sh` | `fertig (clean)`, cpu_comm 4/4, alle RPCs mit RETURN |
| 22:40:32 | `SetSource(3)` | RETURN 247 ms |
| 22:40:44 | `arisc_edid_init.sh` | Zuspieler **`connected`**, `FIFO user1 P0/P3 = 0/0` |
| 22:41:2x | Signal-Lock | `0x06940928 = 0xE0020438` (Bit 31 **gesetzt**), `+0x104` zählt +61/s |
| 22:41:32 | `viddec_descriptor.py set` (**einmal**) | AppTop-Zustand → 4; `0x928` → `0x60020438` (Bit 31 **gelöscht**) |
| 22:41:35 | `PullHotPlug` DOWN 8 s → UP | `0x928` → **`0xE0020438`**, `+0x104` zählt wieder |
| 22:42:0x | `afbd_source0.py on` | Bit 31 bleibt gesetzt; `chroma_stat`: Y 118,5 / **Cb 122,2 (42-200) / Cr 140,4 (64-229)** = echtes YUV |

**Liveness-Beweis** (nicht nur ein Foto): Gamma-Reiz `1:0.2:0.2` am Zuspieler → Differenz zum Ausgangsbild
**mean 9,04, 7,26 % der Bildpunkte > 25**; zurück auf `1:1:1` → Differenz **mean 0,73, 0,00 % > 25**, also
deckungsgleich. Die Wand folgt der Quelle. Fotos `A-07-live-normal.jpg`, `A-08-reiz.jpg`, `A-09-zurueck.jpg`.

### Korrektur meiner ersten Ursachenzuweisung

Um 22:22 hatte ich das eingefrorene Bild dem EDID-Testbefehl `SetEDIDVersion(2)` zugeschrieben. **Das war
falsch.** Der Kaltstart-Gegenversuch um 22:26 zeigte es ohne jeden Zusatzbefehl: `0x928` steht vor dem
Descriptor auf `0xE0020438` und unmittelbar danach auf `0x60020438` - **der Descriptor-Schreibvorgang selbst**
schaltet die Capture ab. Die Firmware nimmt ihn als VideoDec-Ereignis, setzt MemoryAgent `+8` auf 1 und
`memory_agent_onoff` löscht dabei die INCAP-Freigabe, weil die Capture nicht zur Maske der Quelle VideoDec
gehört. `+0x104` zählt danach weiter 60/s, geschrieben wird aber nichts - die Wand zeigt den zuletzt
aufgenommenen Rahmen.

Damit ist auch der A/B-Versuch gegen den Kernel von vor A **gegenstandslos**: es war **keine Regression von
Paket A**. Marcos Lauf um 21:08 lief nur deshalb live weiter, weil er um 21:15 einen HPD-Zyklus gefahren hat
(im Nachtplan A.3 dokumentiert) - genau der Vorgang, der die Freigabe wieder setzt.

Der A/B-Versuch wurde abgebrochen, der alte Kernel und die alten Module wurden zurückgetauscht; das Board
fährt wieder `8ffceb0b…` mit den 25 aktuellen Modulen.

## Vierter Lauf 23:11-23:20 - nach dem Umfallen des Beamers

Um 23:05 kam das Board nach einem Kaltstart nicht zurück (`ARP INCOMPLETE`, keine TFTP-Anfrage, Steckdose an).
**Ursache: der Beamer ist umgefallen** (Meldung von Marco) - vermutlich hatte sich Netzwerk oder Strom gelöst.
Ich hatte den vorangegangenen Aussetzer zunächst meiner eigenen ARISC-Messung zugeschrieben; das war falsch und
ist in `B-puls-messung.md` richtiggestellt.

Nach dem Wiederaufstellen lief die volle Sequenz durch, diesmal mit dem **Quellenwechsel** als Freigabe
(B2-Weg) statt des HPD-Zyklus:

| Zeit | Schritt | Messwert |
|---|---|---|
| 23:11 | Kaltstart, `prep` | `cpu_comm_ready=4`, `mips_run=0x1`, `fertig (clean)` |
| 23:11-23:14 | **M3** (Vorbereitungsphase) | siehe `B-puls-messung.md` |
| 23:16 | `SetSource(3)` | RETURN 248 ms |
| 23:16 | `arisc_edid_init.sh` | Zuspieler `connected` |
| 23:16 | **B1-Messung vor dem Descriptor** | `0x928=0xE0020438`, `0x824=0x0000000B`, `0x400=0x21`, `0x84c=0x04000C00`; **`chroma_stat`: Cb 126,2 / Cr 133,2 - schon YUV** |
| 23:17 | `viddec_descriptor.py set` (einmal) | `0x928` → `0x60020438`, `0x824` → `0x8000000B`, `0x400` → `0x61` |
| 23:17 | `SetSource(1)` → `SetSource(3)` | `0x928` → **`0xE0020438`**, INCAP zählt; `0x824` → `0x0000000B`, `0x400` → `0x21` |
| 23:18 | `afbd_source0.py on` | Bild auf der Wand |
| 23:20 | **Liveness** | Gamma-Reiz **3,10 %** der Bildpunkte > 25; Rückkehr **0,00 %** |

### B1 ist damit beantwortet - und die Erwartung war falsch herum

Die Messvorschrift B1 erwartete vor dem Descriptor „Cb/Cr **nicht** um 128 (RGB-artig)" und formulierte selbst
das Abbruchkriterium: „misst es dort schon YUV um 128, ist die Polarität umgekehrt und Abschnitt 2.2 von
doku/84 muss korrigiert werden." Gemessen wurde **Cb 126,2 / Cr 133,2 - bereits YUV**, bei `0x824` Bit 31 = 0.

Zusammen mit B2 ergibt sich ein stimmiges Bild:

| Zustand | `0x928` Bit 31 | `0x824` Bit 31 | `0x400` | Capture |
|---|---|---|---|---|
| nach Signal-Lock, vor Descriptor | 1 | **0** | `0x21` | schreibt, YUV |
| nach dem Descriptor | **0** | **1** | `0x61` | steht |
| nach Freigabe (Quellenwechsel oder HPD) | 1 | **0** | `0x21` | schreibt, YUV |

`0x824` Bit 31 = 1 und `0x400 = 0x61` kennzeichnen also den **abgeschalteten** Zustand, nicht den guten.
Die Deutung in doku/84 §2.2 und doku/76 §12.4 ist entsprechend zu drehen.

### Hinweis zu den Fotos

Der Beamer steht nach dem Umfallen **anders**: die Projektion sitzt im Kamerabild weiter rechts und etwas
kleiner. Fotos von **vor** 23:05 sind mit späteren daher **nicht** pixelweise vergleichbar; der ROI
(220,40,1090,560) trifft die Projektion weiterhin, ist aber nicht mehr auf sie kalibriert. Vergleiche innerhalb
eines Laufs (wie der Liveness-Beweis oben) bleiben gültig.

### Neuer Messbereich nach dem Umfallen (Vorschlag, alter bleibt unangetastet)

Die Projektion liegt im Kamerabild jetzt bei **x 227…1200, y 69…612** (robust gemessen an
`A-14-kontrolle.jpg`: Spalten/Zeilen mit mehr als 25 % der Spitzenzahl heller Bildpunkte; die äußersten
hellen Punkte reichen von x 170 bis 1201 und y 46 bis 633). Der bisherige ROI **220 40 1090 560** schneidet
rechts also gut 110 Bildpunkte der Projektion ab und nimmt links etwas dunkle Wand mit.

**Nicht geändert:** `re/captures/weltneuheit/wand-aktuell/roi.txt` bleibt auf dem alten Wert - sonst wären alle
Aufnahmen dieser Nacht untereinander nicht mehr vergleichbar. Wer nach dem Umfallen **neu** kalibrieren will:

```bash
WAND_DIR=<neues-verzeichnis> python3 analyse/hdmi-seq/wandcheck.py roi 240 80 1190 605
```

(etwas innerhalb der gemessenen Grenzen, damit der Rand der Projektion nicht mitzählt). Für die Abnahmen von
**D** und **H** ist das zu empfehlen - beide beurteilen Helligkeitsänderungen im ROI, und ein um 10 % zu
kleiner Ausschnitt verschiebt jede Prozentangabe.
