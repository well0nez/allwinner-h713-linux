# 88 - `sun50i-h713-hdmirx`: der HDMI-Eingang als V4L2-Gerät

**Stand 07.09.2026, vormittags - am Gerät gelaufen und abgenommen, danach regressiert: siehe
[Abschnitt 0](#0-stand-am-gerät).** Geschrieben am 06.09.2026, 22:45; Nachtrag 07.09.2026, 06:19
(Slot-Quelle). Paket E aus [78-nachtplan-hdmi-switch.md](78-nachtplan-hdmi-switch.md).
Zur Laufzeit braucht der Treiber Paket B (ARISC), C (`cpu_comm`-Kernel-API) und D (Anzeigetreiber,
liefert die Slot-Ereignisse).

> **Korrektur 07.09.:** der Satz „noch nie am Gerät gelaufen" ist überholt - der Treiber ist gelaufen,
> hat 60 von 60 Bildern geliefert, und ein Teil dessen, was hier als belegt stand, hat die Messung
> nicht überstanden (Abschnitt 0).

> **Nachtrag 07.09.2026, 06:19.** Die Slot-Quelle ist der **Vsync-Notifier aus 0093**, nicht mehr ein
> eigener Abtasttakt. Der Treiber bildet die Flip-Zeiger **nicht mehr selbst ab**; damit entfällt auch
> das `reg` am DT-Knoten. Siehe [§5](#5-slot-erkennung-die-kleine-schnittstelle), [§7](#7-gerätebaum-und-kconfig)
> und [nachtlog/DE-vsync-notifier.md](nachtlog/DE-vsync-notifier.md).

Ergebnis: `mainline/patches/kernel/0094-media-sun50i-h713-hdmirx.patch`.
Arbeitskopie der Quelle für weitere Prüfbauten: `analyse/hdmirx-drv/`.
Abnahmeprogramm: `analyse/v4l2/hdmirx_test.c` (freistehend, arm64, ohne libc).

---

## 0. Stand am Gerät

### Abgenommen (07.09., Vormittag)

| Beleg | Wert |
|---|---|
| Probe | `hdmirx: Init-Sequenz vollstaendig (22 Aufrufe)`, EDID/HPD danach abgeschlossen 17,65 s nach dem Kaltstart |
| Gerät | **`/dev/video1`**, `Slot-Quelle: AFBD vsync notifier (GIC 142)` |
| Eingang | `S_INPUT` setzt die Quelle (`SetSource(3)`) |
| Bilder | **60 von 60** NV16M geliefert, `rc=0` |
| Vsync-Notifier | **287 Ereignisse** |
| Sichtprüfung | das rekonstruierte Bild 29 ist ein **pixelgenauer Screenshot der Quelle** (`re/captures/weltneuheit/ours-20260907-nacht/E/frame29.png`) |

Quellen: [nachtlog/B-abnahme-board.md](nachtlog/B-abnahme-board.md) (dmesg des 09:02-Kaltstarts),
[nachtlog/A6-4-aufloesungswechsel.md](nachtlog/A6-4-aufloesungswechsel.md) (Korrektur 08:55).

### Ein Beleg, der keiner war: `QUERY_DV_TIMINGS`

Die Zeile `QUERY_DV_TIMINGS: 1920x1080p, 148 MHz Pixeltakt` aus dem Abnahmelauf **trägt nichts**. Der Wert
ist im Treiber eine **Übersetzungszeit-Konstante** (`V4L2_DV_BT_CEA_1920X1080P60`), und die
Fähigkeitsgrenzen klemmen `min == max` in Breite, Höhe und Pixeltakt. Er wird bei **jeder** Quellauflösung
gedruckt, solange überhaupt ein Signal anliegt - er hätte gar nicht anders ausfallen können. Wer ihn als
Messwert liest, liest eine Konstante. Einzelheiten in §6, Herleitung in
[A6-4-aufloesungswechsel.md](nachtlog/A6-4-aufloesungswechsel.md), Korrektur 08:55.

Was die Abnahme statt dessen trägt, steht in der Tabelle darüber: 60 von 60 Bildern und das rekonstruierte
Bild.

### Der Auflösungswechsel: alles meldet Erfolg, der Inhalt ist Müll

Zuspieler von 1920×1080 auf 1280×720 und zurück (07:55-08:05):

| | vor dem Wechsel | Quelle auf 1280×720 | zurück auf 1920×1080 |
|---|---|---|---|
| `signal:` | vorhanden | **vorhanden** (Flip-Zeiger wandern weiter) | vorhanden |
| `timings:` | 1920x1080p | 1920x1080p (die Konstante) | 1920x1080p |
| `format:` | NV16M 1920×1080 | **unverändert** | unverändert |
| `SignalChange:` | 0 mal | **0 mal - der Callback feuert nicht** | 0 mal |
| Bilder | 60/60 | **10/10, formal fehlerfrei** | 10/10 |

Das rekonstruierte 720p-Bild zeigt oben das neue Bild **dreifach nebeneinander und zerrissen** (die neue
Geometrie landet in einem Ring, dessen Zeilenabstand noch 1920 ist) und darunter unverändert den alten
1080p-Inhalt. Der Rückweg auf 1080p ist sauber, ohne Zutun. **Ein Verbraucher, der sich auf
`V4L2_EVENT_SOURCE_CHANGE` verlässt, merkt den Wechsel nie.**

### Die Callback-Lücke - und die Regression, die gerade offen ist

**Gemessen (09:11):** die Firmware feuert bei Signalverlust und -rückkehr (`elog` Stufe 5:
`port1 invalid signal!!!`, `CallbackOfSignalChange`, `NotifySignalChange`, zehn passende Zeilen), und die
Kernel-Handler dieses Treibers zählen **null** - `SignalChange: 0 mal`, `HotPlug: 0 mal`
([F-abnahme-und-callback-luecke.md](nachtlog/F-abnahme-und-callback-luecke.md)).

**Ursache gefunden** ([CALLBACK-luecke.md](nachtlog/CALLBACK-luecke.md)): `cpu_comm_register_callback()`
trug den Handler nur in eine treiberinterne Tabelle ein und meldete die Routine **nie in der
Routinentabelle im Shared Memory** an. Die Firmware sucht den Empfänger dort, findet nichts und schickt
gar nicht erst ab (`SendComm2CPUEx` bricht bei fehlgeschlagenem `FindRoutine` mit `-3` ab, vor FIFO und
Doorbell). Der Kernel-Zustellpunkt war nie der Fehler.

**Fix gebaut** (`0092` meldet mit `AddInRoutine()` + `Comm_AddNewChannel()` an, `0094` registriert mit
Namen) - **und am Gerät durchgefallen:** der Probe von `0094` kommt nicht mehr durch. Zwei Kaltstarts,
**zwei verschiedene Fehler** (`-110` und `-EBUSY`), also nicht einmal ein stabil reproduzierter Ausfall.
Solange das so ist, gibt es **kein `/dev/video1`**. Ein Agent arbeitet daran.

**Was an dieser Lücke hängt** - drei Beobachtungen, eine Ursache:

1. Paket **F** fällt bei Signalverlust nicht auf die Konsole zurück; es sitzt in `poll()` und bekommt
   keine Zeile.
2. **`V4L2_EVENT_SOURCE_CHANGE` feuert nie** - in *allen* Läufen von `hdmirx_test` stand `0 SOURCE_CHANGE`,
   auch dort, wo das Signal nachweislich weg war.
3. Der **Auflösungswechsel** ist über V4L2 nicht bemerkbar (oben) - auch, weil der einzige Ereignisweg
   tot ist.

Bis der Callback ankommt, ist alles in §6 unter „Firmware, jederzeit" **Entwurf, nicht Verhalten**.

---

## 1. Was der Treiber ist - und was er nicht ist

Der H713 hat **keinen HDMI-Empfänger, den der ARM ansprechen kann**. Empfänger, Bildpipeline und
Capture-DMA gehören dem MIPS-Coprozessor; der ARM erreicht sie als `THal_Vp_*`-Fernaufrufe über
`cpu_comm`. HPD-Pin und EDID-Speicher gehören der ARISC. Der Treiber besitzt also weder den Empfänger
noch die DMA. Er besitzt **die Reihenfolge**, die die Firmware in den Zustand bringt, in dem sie
aufnimmt, und **die Buchführung**, die den Ring, den die Firmware beschreibt, zu V4L2-Puffern macht.

Drei Eigenschaften der Hardware bestimmen alles Weitere:

1. **Das Capture-Ziel ist nicht programmierbar.** Die Firmware schreibt NV16 in drei feste Slot-Paare
   in ihrer eigenen Framebuffer-Reservierung und dreht ein Zeigerpaar durch sie hindurch.
2. **Es gibt auf dem ARM keinen Capture-Interrupt** (K2, [84-re-capture-ring.md](84-re-capture-ring.md)).
3. **Signalverlust und -rückkehr meldet die Firmware von selbst** über den `SignalChange`-Callback
   (gemessen, beide Richtungen, [nachtlog/K4-hotplug.md](nachtlog/K4-hotplug.md)).
   **Korrektur 07.09.: die Firmware meldet - dieser Treiber hört sie nicht.** Die Kernel-Handler zählen
   null, weil die Routine nie in der Shmem-Routinentabelle angemeldet wurde (Abschnitt 0). Der Satz
   beschreibt also die Firmware, nicht den Zustand des Treibers.

Im Zielbild aus Anhang A.4 deckt dieser Treiber die Stufen 3, 4 und 5 ab. Stufe 7 - Descriptor und
AFBD-Sequenz - gehört **Paket D** und steht bewusst nicht hier; INCAP-Register (`0x0694xxxx`) fasst
der Treiber überhaupt nicht an, auch nicht lesend (siehe §8).

---

## 2. Die Probe-Sequenz (Stufe 3) - als Tabelle im Code

Im Treiber ist das das Feld `h713_hdmirx_init_seq[]`, ein `struct h713_hdmirx_step`-Array mit
Name, Argumentart, Argumenten, Stock-Sessionnummer und Begründung pro Zeile. Die comp_id wird zur
Laufzeit aus dem Namen gehasht (`cpu_comm_name2id()`), es steht also keine Zahlentabelle im Treiber.

| # | Aufruf | Argumente | Stock-Session | comp_id (nachgerechnet) |
|---|---|---|---|---|
|  1 | `THal_Vp_Init` | `0, 0, Shmem+0x400000` | - | `0x1c6ff747` |
|  2 | `THal_Vp_RegisterSignalChangeCallback` | `11` | - | `0x671ceca6` |
|  3 | `THal_Vp_SetHDMIHotPlugByPortCallback` | `1` | - | `0xba3e5a70` |
|  4 | `Thal_Vp_SetBacklightLevel` | `0x64` | 14 | `0x51ad877e` |
|  5 | `THal_Vp_SetBacklightWorkMode` | `0` | 15 | `0x4d80db0e` |
|  6 | `THal_Vp_SetTNR` | `2` | 17 | `0xa4bb0747` |
|  7 | `THal_Vp_SetSNR` | `1` | 18 | `0xc0da6a8e` |
|  8 | `THal_Vp_SetDCI` | `2` | 19 | `0xf6a798d3` |
|  9 | `THal_Vp_SetBlackExtension` | `1` | 20 | `0x5c135587` |
| 10 | `THal_Vp_SetPictureMode` | `1` | 21 | `0x83a878bf` |
| 11 | `THal_Vp_SetVideoRange` | `0` | 22 | `0x9817a1c1` |
| 12 | `THal_Vp_Wce_SetWindow` | drei Zeiger: src, dst, aspect | 23 | `0x3356c54b` |
| 13 | `THal_Vp_CvbsSetPedestalMode` | `1` | 24 | `0x24f44438` |
| 14 | `THal_Vp_HDMI_SetPortMap` | `3, 0` | 25 | `0x9ce74c48` |
| 15 | `THal_Vp_HDMI_SetPortMap` | `4, 1` | 26 | `0x9ce74c48` |
| 16 | `THal_Vp_HDMI_SetPortMap` | `5, 2` | 27 | `0x9ce74c48` |
| 17 | `THal_Vp_Wce_SetWindow` | dieselben drei Zeiger | 28 | `0x3356c54b` |
| 18 | `THal_Vp_DisableBlackScreen` | **ParaCount 0** | 29 | `0xb66041d8` |
| 19 | `THal_Vp_TurnOnARCAudioPath` | `1` | 30 | `0x93965d14` |
| 20 | `THal_Vp_SwitchARCTXPath` | `0` | 31 | `0xe9b4464d` |
| 21 | `THal_Vp_SetHDCP22Key` | `Shmem+0x36000, 912` | 32 | `0x50817813` |
| 22 | `THal_Vp_HDMI_SetHPDTimeInterval` | `0xC8` (200 ms) | 33 | `0x6eb4c96a` |

Dazu, **nicht** im Probe, sondern in `VIDIOC_S_INPUT`: `THal_Vp_SetSource(3)` (`0xeaf13de5`,
Stock-Session 34).

**Zur Zahl „24" im Nachtplan.** Die Tabelle hat 22 Einträge, nicht 24. Die Rechnung: Stock-Sessions
14-33 sind 20 Aufrufe, davon fällt **Session 16 `SetWhiteBalance` aus** (braucht einen Zeiger auf drei
werkskalibrierte `double`, die wir nicht haben - `hdmi_seq.py` lässt sie aus demselben Grund weg), also
19; dazu die drei Phase-2-Aufrufe = 22. Mit `SetWhiteBalance` und `SetSource` gerechnet kommt man auf
24. Die Sequenz läuft ohne Session 16 - das ist am Gerät dreimal belegt (Nachtplan §1).

Die comp_ids in der letzten Spalte sind **nachgerechnet** (geseedete CRC-32 über
`"<Name>_1_000"`, Seed `0x00123456`) und stimmen Zeile für Zeile mit `KNOWN_IDS` in
`analyse/hdmi-seq/hdmi_seq.py` überein, die ihrerseits gegen die Routine-Tabelle der Firmware
verifiziert sind. Der Treiber hasht selbst, die Tabelle hier ist nur zum Nachschlagen.

### Argumente, die Zeiger sind

Der MIPS bekommt keine Typinformation, nur 32-Bit-Wörter; ein Pufferargument ist die **physische
Adresse** eines Puffers, den der MIPS sehen kann. Drei davon kommen vor, alle im
`cpu_comm`-Shmem, dessen Basis der Treiber über `memory-region-names = "cpu-comm-shmem"` aus dem
Gerätebaum holt (keine geratene Adresse):

| Offset im Shmem | Inhalt | Warum genau dort |
|---|---|---|
| `+0x036000` | HDCP-2.2-Schlüssel, 912 B | genau die Adresse, die der Stock-tvserver benutzt (`Para[0] = 0x4e336000` im RPC-Mitschnitt) |
| `+0x037000` | `Wce_SetWindow`: src `{0,1920,0,1080}`, dst dito, aspect `2` | Lage beliebig (der MIPS führt keine Buchhaltung), von `hdmird` gewählt |
| `+0x400000` | Staging für `THal_Vp_Init`, 55296 B | der Handler kopiert 55296 B seines `.bss` dorthin, **ungeprüft**; `Para[2] = 0` ist ein memcpy nach NULL und reißt die Firmware mit |

Der Treiber bildet davon nur **zwei Seiten** ab (`0x36000` - `0x38000`, `ioremap_wc`) und schreibt sie
**wortweise**: die Region wird mit einem Coprozessor geteilt, und ein breiter unausgerichteter
Zugriff darauf hat schon einmal gefaultet (doku/67, Ursache 3). Das Staging bildet er gar nicht ab -
er reicht nur die Adresse weiter.

### HDCP-Schlüssel

`request_firmware("hy310-hdcp22.bin")`, Größe muss **exakt 912** sein. Die Datei ist Vendor-Material
(`analyse/hdcp-keys/hdcp22-key-912.bin`) und bleibt außerhalb des öffentlichen Repos; der Patch nennt
nur den Namen (`MODULE_FIRMWARE`). **Fehlt sie, wird Schritt 21 übersprungen** und der Rest der
Sequenz läuft - eine unverschlüsselte Quelle braucht den Schlüssel nicht. Das ist dasselbe Verhalten
wie in `hdmi_seq.py`.

### Kein `--gap`

`hdmi_seq.py` pausiert zwischen den Aufrufen, weil die FreeCall-FIFO 21 Plätze hat. Der Treiber tut
das **nicht** (Pflichtliste: kein Drosseln). Läuft die FIFO leer, liefert `cpu_comm_call()` `-EBUSY`,
und der Probe **scheitert mit dieser Meldung**, statt sie wegzuschlafen. Sollte das am Gerät auftreten,
ist das ein Befund über `cpu_comm`, kein Grund für eine Wartezeit im Treiber.

---

## 3. Stufe 4: EDID und HPD

Am Ende des Probes ruft der Treiber genau einmal

```c
arisc_hdmi_edid_init(0 /* Port */, NULL, 0);
```

Mit `edid == NULL` nimmt der ARISC-Treiber sein eigenes Vorgabe-EDID (`hy310-edid.bin`, 512 B) und
fährt die belegte Reihenfolge: `ResetEDIDModule` → Portmap → EDID-Version 2 → 8 Fragmente →
`CheckEDIDUpdateStatus` → `RequestEDID` → AudioMode → 5 V → HPD DOWN → **200 ms** → HPD UP.

**Korrektur 07.09.: hier standen 10 s, und die waren unbelegt.** `HPD_DOWN_MS` in `0091` ist auf **200**
gesetzt, und der Wert ist doppelt gedeckt: gemessen (kleinste geprüfte Senke, die eine saubere Flanke
**und** ein neu gelesenes EDID erzeugt - vollständige Modusliste am Zuspieler) und zugleich der Stock-Wert
(`HDMI_SetHPDTimeInterval(0xC8)`, im Stock-elog als `SetHPDTimeInterval from 200 to 200`). Herleitung:
[nachtlog/A2-hpd-dauer-edid.md](nachtlog/A2-hpd-dauer-edid.md); die ältere Messung
[M4-hpd-dauer.md](nachtlog/M4-hpd-dauer.md) deckt ausdrücklich **nur** den Wiederanlauf-Zyklus, nicht den
EDID-Fall.

Damit dauert der EDID/HPD-Teil des Probes knapp eine Sekunde statt gut zehn; am Gerät war die Sequenz
17,65 s nach dem Kaltstart abgeschlossen statt 28,8 s ([B-abnahme-board.md](nachtlog/B-abnahme-board.md),
Abnahme 09:02). `.probe_type = PROBE_PREFER_ASYNCHRONOUS` bleibt richtig - der Probe wartet weiterhin auf
Fernaufrufe an einen Coprozessor - , aber die Begründung „über zehn Sekunden" trägt nicht mehr.

`VIDIOC_S_EDID` macht dasselbe mit einem vom Nutzer gelieferten EDID. Zwei Eigenheiten, die in der
Doku stehen müssen, weil sie nicht V4L2-üblich sind:

* Der Firmware-Speicher ist **kein einzelnes EDID**, sondern der HDMI-1.4-Block und der
  HDMI-2.0-Block hintereinander, 512 B. V4L2 sieht das als **ein EDID mit vier Blöcken**; der Treiber
  nimmt nur `blocks == 4` an und gibt sonst `-E2BIG` mit `blocks = 4` zurück, wie die Schnittstelle es
  vorsieht.
* Die Firmware **patcht Byte 168** (Physical Address) und die Prüfsumme selbst. Ein Rücklesen ist
  deshalb nicht byteidentisch mit dem Geschriebenen.

`blocks == 0` heißt in V4L2 „kein EDID": der Treiber legt dann den HPD-Pin (`ARISC_HDMI_HPD_DOWN`).

`VIDIOC_G_EDID` liest über `arisc_hdmi_get_edid()` zurück; ist die Antwort kürzer als verlangt oder
antwortet der Coprozessor nicht, liefert der Treiber die zuletzt geschriebene Fassung statt eines
halben Datensatzes. Ob ein vollständiger 512-B-Rücklesevorgang funktioniert, ist **ungemessen** (§8).

---

## 4. Puffermodell: Puffer *i* **ist** Slot *i*

**Entscheidung: `VB2_MEMORY_MMAP` mit eigenen `vb2_mem_ops`, kein dma-buf-Export.** Begründung:

* Die Firmware schreibt in **feste** Adressen. Ein Puffer kann also nicht *allokiert* werden -
  weder `vb2-dma-contig` noch ein `shared-dma-pool` treffen die Slots. Jede Lösung, die vb2 Speicher
  aussuchen lässt, endet mit einer **Kopie**, und die verbietet der Auftrag.
* `VB2_MEMORY_DMABUF` würde bedeuten, dass der Nutzer die Puffer mitbringt - dieselbe Sackgasse.
* Mit eigenen `mem_ops` ist Puffer *i* dauerhaft an Slot *i* gebunden, `mmap()` reicht den Slot direkt
  an den Nutzer, `QBUF`/`DQBUF` übergeben nur noch das Eigentum. **Null Kopien**, und
  `--stream-mmap`-artige Abnahme funktioniert.

Layout (gemessen, doku/76 §12-13; vom Treiber gegen die DT-Region geprüft, nicht geglaubt):

| Slot | Y | C |
|---|---|---|
| 0 | `0x4C3EF000` | `0x4C9EC000` |
| 1 | `0x4C5EE000` | `0x4CBEB000` |
| 2 | `0x4C7ED000` | `0x4CDEA000` |

Abstand zwischen zwei Y-Slots `0x1FF000`, C-Slot = Y-Slot + `0x5FD000`, gleiche Indizes. Alle sechs
liegen in `mips_framebuf` (26 MB ab `0x4BF41000`), das der Treiber per
`memory-region-names = "hdmi-ring"` bindet.

**Format: `V4L2_PIX_FMT_NV16M`, 1920×1080, zwei Ebenen zu je 1920×1080 Byte.** Das „M" ist keine
Geschmacksfrage: Y und C liegen `0x5FD000` auseinander, das einfache `NV16` verlangt aber C direkt
hinter Y. Also Multiplanar-API (`V4L2_CAP_VIDEO_CAPTURE_MPLANE`).

`REQBUFS` liefert **immer genau drei** Puffer, egal was verlangt wurde (`max_num_buffers = 3`): bei
weniger Puffern fiele jedes Bild weg, das in einem Slot ohne Puffer landet. `VIDIOC_CREATE_BUFS` gibt
es aus demselben Grund **nicht** - es gibt nichts, worauf ein vierter Puffer zeigen könnte.

Die Abbildung an den Nutzer ist **write-combining**, nicht gecacht: der Schreiber ist ein
Coprozessor, dessen Speicherzugriffe nie durch den Cache dieser CPU laufen.

*Kleinigkeit für Mitleser:* vb2 sagt einem Allokator nicht, für welche **Ebene** es ihn ruft. Es geht
die Ebenen eines Puffers der Reihe nach durch und trägt das Ergebnis sofort in
`vb->planes[n].mem_priv` ein (`__vb2_buf_mem_alloc()`), also ist die gesuchte Ebene die erste, die
noch keines hat. Genau so ermittelt der Treiber sie, mit Kommentar an der Stelle.

**Nicht gebaut: `VIDIOC_EXPBUF`.** Für Paket F („`DQBUF` → Plane-Flip" in A.4) wäre ein dma-buf-Export
der Slots nötig. Paket D verfolgt den Ring heute selbst über die Flip-Zeiger, F braucht ihn also noch
nicht. Der Export ist eine `get_dmabuf`-Operation in denselben `mem_ops` - offener Punkt, siehe §8.

---

## 5. Slot-Erkennung: die kleine Schnittstelle

Die Frage „Polling oder Interrupt?" ist RE-Frage **K2 und inzwischen beantwortet**: es gibt auf dem
ARM **keinen** Capture-Interrupt. `0x05600320/324` werden von **keiner** Firmware-Funktion und keiner
TSE-Tabelle geschrieben - sie sind ein Hardware-Paar; das „Slot fertig"-Interrupt existiert nur
MIPS-intern und ist im Stock-DTS nicht auf den ARM verdrahtet ([84](84-re-capture-ring.md)).

Was die ARM-Seite dagegen hat, ist der **Anzeige-Vsync GIC 142**, den `sun50i-h713-afbd` bedient und
in dem dieser Treiber das Flip-Paar für seine eigene Passthrough-Plane ohnehin liest. Genau von dort
kommen die Ereignisse. Der Treiber kapselt die Quelle trotzdem, damit ein echter Capture-Interrupt sie
später ohne Änderung am Rest ablösen könnte:

```c
struct h713_hdmirx_slot_source {
	const char *name;
	int  (*start)(struct h713_hdmirx *rx);
	void (*stop)(struct h713_hdmirx *rx);
};

/* Der eine Trichter, in den jede Quelle mündet. Aus atomarem Kontext erlaubt. */
static void h713_hdmirx_slot_event(struct h713_hdmirx *rx);
```

* `start()` wird aus `start_streaming()` gerufen, `stop()` aus `stop_streaming()`; nach `stop()` darf
  kein Ereignis mehr kommen.
* `h713_hdmirx_slot_event()` bekommt das fertige Flip-Paar, bestimmt den Slot, schließt den zugehörigen
  Puffer ab. Es enthält **die gesamte** Warteschlangenlogik; eine Quelle ist nur Takt.

Die eine Quelle ist `h713_hdmirx_vsync`. `start()` ist
`h713_afbd_register_flip_notifier(&rx->flip_nb)`, `stop()` die Abmeldung; der Notifier-Handler ruft
`h713_hdmirx_slot_event()` mit der Nutzlast, die der Anzeigetreiber mitgibt
(`struct h713_afbd_flip` = die rohen `+0x320/+0x324`). Die Schnittstelle steht in
[86-video-plane-nv16.md §5.1](86-video-plane-nv16.md) und in
`include/linux/soc/sunxi/h713-afbd.h`.

**Das Zerrissen-Lesen steht nicht mehr hier.** Y zweimal um C herum lesen, Paar gegen die
Ring-Grenzen prüfen, „hat sich was bewegt" - das macht der Erzeuger, einmal, und ruft die Kette nur
bei einer echten Änderung. Dieser Treiber sieht das Registerpaar nicht mehr (§7).

**Der 120-Hz-`hrtimer` ist ersatzlos weg**, auch nicht als Rückfall hinter einem Modulparameter. Er
tastete mit einer Rate ab, die mit dem gesuchten Ereignis nichts zu tun hat: die Hälfte der Weckrufe
fand nichts, die andere Hälfte einen Slot, der bis zu 8 ms vorher fertig geworden war. Ein
Abtasttakt, der still neben dem echten Ereignis herläuft, ist ein Quirk (Nachtplan §0 Regel 1) - und
es gibt keine Lage, in der er die bessere Wahl wäre: ohne 0093 gibt es weder Plane noch Descriptor
noch Ring-Grenzen, es ist also nichts da, worauf man zurückfallen könnte. Fehlt der Erzeuger, sagt
der Treiber das (`-EPROBE_DEFER`, wenn `display@5600000` nur noch nicht gebunden ist; ein echter
Fehler, wenn der Treiber gar nicht im Kernel ist), statt still zu tasten.

Gezählt wird, was **nicht** ging - K1/K3 empfehlen das ausdrücklich, damit ein Ratenunterschied
sichtbar wird statt still verschluckt zu werden: `events` (Notifier-Aufrufe, also Vsyncs mit
Slot-Wechsel), `delivered`, `no_buffer` (Slot fertig, aber kein Puffer eingereiht), `skipped` (mehr
als ein Slot auf einmal weitergesprungen), `unchanged` (dürfte nie zählen - der Erzeuger meldet nur
Änderungen), `stray` (Zeiger nicht im Ring). `torn` gibt es nicht mehr; zerrissene Proben verwirft
der Erzeuger. Alles in `/sys/kernel/debug/sun50i-h713-hdmirx/status` und am Ende von
`stop_streaming()` im Log.

**Am Gerät (07.09.):** `events` zählte in einem Abnahmelauf **287** Ereignisse, `delivered` 60 von 60
angeforderten Bildern. Ob `skipped` dabei klein blieb, ist in den vorliegenden Protokollen nicht
festgehalten - die `frames:`-Zeile war eine der drei Bitten aus §7 von
[nachtlog/E-v4l2.md](nachtlog/E-v4l2.md) und bleibt nachzureichen.

---

## 6. Zustände und Ereignisse

```
                probe: Stufe 3 (22 RPCs)  ->  Stufe 4 (EDID, HPD)  ->  /dev/videoN
                                                   |
   open()  ---------------------------------------- |
   S_INPUT(0) ------> SetSource(3)  (Stufe 5; Nullwechsel ist normal, kein Fehler)
   QUERY_DV_TIMINGS -> Flip-Zeiger 20 ms beobachten -> 1920x1080p60  oder  -ENOLINK
                       (nur "oder -ENOLINK" ist gemessen; 1920x1080p60 ist eine Konstante)
   REQBUFS(3)/QBUF/STREAMON -> slot_source.start()
        pro Slot-Wechsel: DQBUF mit dem fertigen Slot  (keine Kopie)
   STREAMOFF -> slot_source.stop(), alle Puffer zurück

   Firmware, jederzeit:
        MipsHalCallback_SignalChange           -> V4L2_EVENT_SOURCE_CHANGE
        MipsHalCallback_HdmiHotPlugByPortHandler -> V4L2_EVENT_SOURCE_CHANGE
```

### Callback-Layouts

Beide Callbacks kommen über `cpu_comm_register_callback()` (Paket C) im **Prozesskontext auf der
Empfangs-Workqueue** an. Regel aus dem C-Header: der Handler darf schlafen, verzögert dabei aber die
Quittung, auf die der MIPS wartet - und er darf **nie** `cpu_comm_call()` rufen. Beide Handler hier
tun nur zwei Dinge: Rohwörter unter einem Spinlock ablegen und das V4L2-Ereignis einreihen.

| Callback | comp_id (cpu 0) | Nutzlast |
|---|---|---|
| `MipsHalCallback_SignalChange` | `0x3e7fbc46` | `Para[0]` = source_id (3 = HDMI-1), `Para[2]` = physischer Zeiger auf 44 B Signal-Info |
| `MipsHalCallback_HdmiHotPlugByPortHandler` | `0x38d780e2` | `Para[0]` = Port |

**Drei Nachträge vom 07.09.** ([CALLBACK-luecke.md](nachtlog/CALLBACK-luecke.md)):

* **Die Callbacks kommen heute nicht an** - dieser ganze Abschnitt beschreibt den Entwurf, nicht das
  gemessene Verhalten (Abschnitt 0).
* **Die Anmeldung nimmt jetzt den Namen, nicht die id.** `cpu_comm_register_callback(const char *base_name,
  …)`: der Routinen-Deskriptor im Shmem trägt den vollen Namen (`…_0_000`), und vom Hash führt kein Weg
  zurück. `0094` hält die beiden Namen als `H713_HDMIRX_CB_SIGNAL`/`H713_HDMIRX_CB_HOTPLUG` an einer Stelle.
* **Beide nehmen die FIFO-Nachrichtenklasse** (`chan=0x0`, `entry_cmd <= 4`), nicht die `> 4`-Klasse - in
  allen fünf Mitschnitten (run80/81/83/84/85), auch für `0x3e7fbc46`. doku/72 sagt dazu das Gegenteil. Das
  ist die Nachrichtenklasse des MIPS, nicht der Zustellkontext auf dem ARM; für die Zustellung selbst ist es
  gleichgültig, weil der Einhängepunkt über der Verzweigung liegt.

**Die Signal-Info ist nicht entschlüsselt.** Belegt sind: sie ist **44 Byte** groß
(`hal_adapter_init` fordert `0x2c` an, doku/74); die Firmware vergleicht bei einem Signalereignis
**`+0, +4, +8, +12, +16, +20, +24`**; und **`+16` ist der `color_format`-Wert des VidDec-Descriptors
plus 1** (doku/84 §1). Wo Breite, Höhe und Bildrate liegen, ist **nicht** bekannt - der Satz „Layout in
`signal_info_buf.py`" im Nachtplan trägt nicht: dieses Skript setzt nur den Zeiger und markiert den
Puffer, es beschreibt keine Felder.

Deshalb **rät der Treiber nicht**. `h713_hdmirx_status` in debugfs bildet die Seite ab, auf die
`Para[2]` zeigt (nur wenn sie im `cpu-comm-shmem` liegt), und druckt die ersten 11 Wörter roh. Ein
Board-Lauf mit einer bekannten Auflösung genügt danach, um das Layout festzuschreiben.

### DV-Timings

`QUERY_DV_TIMINGS` liefert `1920x1080p60` (`V4L2_DV_BT_CEA_1920X1080P60`) - aber **nur, wenn die
Flip-Zeiger sich bewegen**. Genau **eine Hälfte** dieses Satzes ist eine Messung: „Signal vorhanden" ist
hier kein Registerbit, sondern die beobachtete Bewegung der Zeiger. Die **Zahl** dagegen ist eine
Übersetzungszeit-Konstante (`sun50i-h713-hdmirx.c`, `static const struct v4l2_dv_timings
h713_hdmirx_timings = V4L2_DV_BT_CEA_1920X1080P60;`), und `DV_TIMINGS_CAP` klemmt
`min_width == max_width == 1920`, `min_height == max_height == 1080`,
`min_pixelclock == max_pixelclock == 148500000`. **Sie kann nicht anders ausfallen und ist deshalb nie
ein Beleg** - auch nicht in einem Abnahmeprotokoll (Abschnitt 0).

Bei Signalverlust friert der Ring ein und das letzte Bild bleibt stehen (gemessen,
K4); ein **stehendes Bild** ist dagegen kein stehender Ring, die Zeiger drehen sich unabhängig vom
Inhalt weiter. Ohne Bewegung: `-ENOLINK`. `ENUM_INPUT` setzt aus derselben Messung
`V4L2_IN_ST_NO_SIGNAL`.

Diese eine Frage kann nicht auf den nächsten Vsync warten - sie wird gestellt, während gar nicht
gestreamt wird, also ohne angemeldeten Notifier. Sie geht deshalb über `h713_afbd_read_flip()` an den
Anzeigetreiber: zwei Stichproben, 20 ms auseinander. Dieselben zwei Register, derselbe Eigentümer,
keine zweite Abbildung.

Dass 1080p60 fest verdrahtet ist, ist ehrlich gesagt eine Krücke, aber eine begründete: die ganze
Kette - WCE-Fenster, Descriptor, AFBD-Crop - ist auf 1920×1080p60 gebaut. `ENUM_DV_TIMINGS` hat genau
einen Eintrag, `DV_TIMINGS_CAP` genau dieses Fenster; `S_DV_TIMINGS` nimmt nichts anderes an.

**Korrektur 07.09.:** der Auflösungswechsel ist inzwischen **gemessen** (Abschnitt 0), und das Ergebnis
macht die Krücke teurer als gedacht: der Treiber druckt weiter 1080p60, während die Quelle 720p sendet und
der Ring zerrissenen Inhalt trägt. **Ein Vergleich zweier `QUERY_DV_TIMINGS`-Abfragen kann einen
Auflösungswechsel strukturell nie erkennen** - Paket F hat aus diesem Grund darauf verzichtet, ein zweites
Kriterium darauf zu bauen. Die **echten** Timings stehen in der 44-Byte-Signal-Info, die der
`SignalChange`-Callback per `Para[2]` als Shmem-Zeiger liefert; sie zu entschlüsseln ist die Messung, die
alles hier Feste beweglich macht - und sie setzt voraus, dass der Callback überhaupt ankommt
(Abschnitt 0).

---

## 7. Gerätebaum und Kconfig

```dts
/* Wurzelebene, neben sound -- der Knoten hat keine Register. */
hdmirx: hdmi-rx {
        compatible = "allwinner,sun50i-h713-hdmirx";
        memory-region = <&mips_framebuf>, <&cpu_comm_reserved>;
        memory-region-names = "hdmi-ring", "cpu-comm-shmem";
        status = "okay";
};
```

* **Kein `reg` mehr, und deshalb auch keine Einheitsadresse im Namen.** Bis zum 07.09. stand hier
  `hdmi-rx@5600320` mit `reg = <0x05600320 0x8>` - dem Flip-Zeigerpaar, acht Byte **innerhalb** des
  `0x400`-Fensters von `display@5600000`. Der Kommentar darüber sagte „abbilden, ohne zu
  beanspruchen"; `devm_of_iomap()` ruft aber `devm_ioremap_resource()` und **beansprucht**. Da
  `/proc/iomem` das Fenster als `05600000-056003ff : 5600000.display afbd` führt, ist das Ergebnis
  `-EBUSY` und der Probe scheitert. Die Zeiger kommen jetzt über den Vsync-Notifier (§5); das
  Registerfenster hat genau einen Eigentümer.
* **Warum auf der Wurzelebene:** ein Knoten ohne `reg` unter `soc { compatible = "simple-bus"; }`
  bringt eine dtc-Warnung (`simple_bus_reg: … missing or empty reg/ranges property`) - nachgestellt
  im Prüfbau. Neben `sound` steht er richtig; `of_platform_default_populate()` legt für Kinder der
  Wurzel genauso ein Plattformgerät an.
* **`memory-region`** statt geratener Adressen, unverändert. Die Slot-Adressen prüft der Probe gegen
  `hdmi-ring` und bricht ab, wenn eine nicht hineinpasst.
* **Kein `interrupts`** - siehe §5.
* **Kein `firmware-name`**: der HDCP-Dateiname steht im Treiber (`MODULE_FIRMWARE`), und eine
  DT-Eigenschaft, die niemand liest, gehört nicht in die Hardwarebeschreibung.

Kconfig: `VIDEO_SUN50I_H713_HDMIRX`, `depends on HY310_CPU_COMM`, `SUN50I_H713_ARISC` **und**
`DRM_SUN50I_H713_AFBD` (der Notifier-Erzeuger), `select VIDEOBUF2_CORE`, `select VIDEOBUF2_MEMOPS`.
Datei: `drivers/media/platform/sunxi/sun50i-h713-hdmirx/`. Die Modulabhängigkeit steht damit auch im
Modul: `depends=hy310-cpu-comm,sun50i-h713-afbd,sun50i-h713-arisc` - `modprobe` zieht den
Anzeigetreiber von selbst nach, `insmod` allein scheitert an ungelösten Symbolen.

---

## 8. Was belegt ist und was offen

### Belegt (am Gerät gemessen, vor dieser Nacht oder in dieser Nacht)

| Aussage | Beleg |
|---|---|
| Die 22 Aufrufe in dieser Reihenfolge bringen die Firmware hoch | Nachtplan §1, dreimal nach Kaltstart; `hdmi_seq.py --phase 3` |
| `Para[2]` von `Vp_Init` muss gültig sein | doku/74, Session Z |
| `DisableBlackScreen` hat ParaCount 0 | Wrapper-RE, Y2-Fix #17 |
| Schlüssel 912 B bei `0x4e336000` | Stock-RPC-Mitschnitt Session 32, Stock-elog |
| EDID-Reihenfolge und HPD-Zyklus | doku/75, Nachtrag 14:55 |
| `SetSource(3)` ist ein Nullwechsel, wenn HDMI-1 schon aktiv ist | doku/76 §2.2, 21:03 |
| Ring: NV16/YUV in drei Slot-Paaren, Flip-Zeiger drehen 60 Hz | doku/76 §12-13 |
| Bei Signalverlust friert der Ring ein, das Bild bleibt stehen | K4, 21:50:56; am 07.09. erneut gesehen (F: Wand mean 130,4 gegen 131,2 nach `xrandr --off`) |
| `SignalChange` feuert bei Verlust **und** Rückkehr von selbst - **erreicht die Kernel-Handler aber nicht** | K4, elog Stufe 5; Gegenbefund und Ursache: Abschnitt 0 |
| Kein ARM-seitiger Capture-Interrupt | K2, doku/84 |
| comp_id = geseedete CRC-32 über den Namen | Routine-Tabelle der Firmware, `hdmi_seq.py` |
| **Die 22 Aufrufe laufen aus dem Kernel durch** | dmesg 07.09.: `Init-Sequenz vollstaendig (22 Aufrufe)` |
| **Puffer *i* = Slot *i* trägt**: 60 von 60 Bildern, rekonstruiertes Bild pixelgenau | Abschnitt 0 |
| **Der Vsync-Notifier ist die richtige Slot-Quelle**: 287 Ereignisse in einem Abnahmelauf | Abschnitt 0, [DE-vsync-notifier.md](nachtlog/DE-vsync-notifier.md) |
| **200 ms HPD-Senke genügen** für Flanke und EDID-Neulesung | [A2-hpd-dauer-edid.md](nachtlog/A2-hpd-dauer-edid.md) |
| **Ein echter Quellenwechsel macht die Capture wieder scharf** | [B2-quellenwechsel.md](nachtlog/B2-quellenwechsel.md) |

### Offen

0. **Der Treiber probt gerade nicht** (Stand 07.09. vormittags). Nach der Änderung an der
   Callback-Anmeldung scheitert der Probe von `0094`; zwei Kaltstarts, zwei verschiedene Fehler
   (`-110`, `-EBUSY`). Das ist der einzige Punkt, der alle anderen blockiert - Abschnitt 0.
1. **Layout der 44-Byte-Signal-Info.** Nur `+16` ist entschlüsselt. Solange das so ist, sind die
   DV-Timings eine Konstante (§6). Der Rohabzug in debugfs ist da; ein Board-Lauf reicht - **sobald der
   Callback ankommt**, denn `Para[2]` ist der einzige Weg zu dieser Struktur.
2. **`VIDIOC_EXPBUF`/dma-buf-Export der Slots.** Für Paket F, sobald die Plane einen importierten
   Puffer statt der Ring-Zeiger nimmt.
3. ~~**Auflösungswechsel** (Anhang A.6 Punkt 4). Ungemessen.~~ **Gemessen am 07.09.** (Abschnitt 0) und
   schlechter als erwartet: kein `SignalChange`, kein `SOURCE_CHANGE`, formal fehlerfreie Bilder mit
   zerrissenem Inhalt. Offen ist jetzt nicht mehr *ob*, sondern **woran ein Geometriewechsel ohne Pollen
   erkennbar wäre**. Kandidaten, die noch niemand gelesen hat: die INCAP-Timing-Register, die die Firmware
   bei jedem Lock neu rechnet (im elog als `numTotalPixelsPerLine`, `numActiveLines`,
   `offsetFirstActivePixel`), und der Composition-Block `0x05000224`/`0x05000844`
   ([doku/89](89-composition-block.md)). Messvorschrift in
   [A6-4-aufloesungswechsel.md](nachtlog/A6-4-aufloesungswechsel.md).

   **Teilantwort vom 07.09., 12:20** ([E3-geometrie-im-register.md](nachtlog/E3-geometrie-im-register.md)):
   der Auslöser steht in einem Register, das der Treiber ohnehin kennt. `0x06940928`, untere 16 Bit = die
   **Zeilenzahl** des eingerasteten Signals (`0x438` = 1080, `0x2D0` = 720, über vier Modi gemessen); Bit 31
   sagt, **ob** die Firmware einrastet (bei 1600x1200 und 1920x1200 - Modi, die unser EDID nicht führt -
   fällt es aus und die unteren Bits behalten den Altwert). Das hängt an **keinem** Callback und beantwortet
   beide Fragen, die V4L2 stellt, durch Lesen statt durch Warten. **Was fehlt:** die **Breite** - sie steht
   *nicht* in der oberen Hälfte desselben Wortes (die blieb über alle vier Modi `0xE002`/`0x6002`).
   Und der naheliegende Rettungsweg trägt nicht: ein Quellenwechsel bringt die Firmware auf die neue
   Geometrie, das Bild bleibt zerrissen, weil Ring-Zeilenabstand, Zuschnitt und Descriptor auf der
   Anzeigeseite auf 1080p stehen. Ein Auflösungswechsel bleibt damit **nicht unterstützt** - neu ist nur,
   dass er erkennbar wäre. (Der Treiber darf INCAP nur **lesen**; dafür genügt es.)
4. **Vollständiges EDID-Rücklesen** (512 B) über `RequestEDID` - Paket B nennt es selbst ungemessen. Am
   07.09. sind **64 B** zurückgelesen worden (`arisc: EDID zurueckgelesen (64 B)`, gültiger Kopf); die
   vollen 512 B bleiben offen.
5. **`S_INPUT` im Betrieb - die alte Aussage hier ist widerlegt.** Hier stand: „Ein *echter*
   Quellenwechsel macht die Capture nicht wieder scharf (A.6 Punkt 1, K3)." **Er tut es.**
   [B2-quellenwechsel.md](nachtlog/B2-quellenwechsel.md) misst `SetSource(1)` → `SetSource(3)` am
   laufenden Gerät: `0x06940928` geht von `0x60020438` zurück auf `0xE0020438`, `+0x104` zählt wieder, der
   Ringinhalt folgt einem Gamma-Reiz am Zuspieler, und der Rundlauf hinterlässt **null** strukturelle
   Registerunterschiede. ~~Für diesen Treiber ist das die gute Nachricht: `VIDIOC_S_INPUT` ist ohnehin ein
   Quellenwechsel und damit der Weg, die vom Descriptor abgeschaltete Capture wieder freizugeben.~~

   **Korrektur 07.09., 11:42 - `S_INPUT` war der falsche Ort, und die Freigabe macht jetzt der Kernel
   selbst.** `h713_hdmirx_s_input()` rief in der damaligen Fassung ausschließlich
   `h713_hdmirx_set_source(rx)`, also `SetSource(3)`; in der Betriebsreihenfolge (Plane-Enable schreibt den
   Descriptor, HDMI-1 ist längst aktiv) ist das **immer** der Nullwechsel - und der gibt nichts frei. Am
   Gerät nachgemessen: ein einzelner `SetSource(HDMI-1)` wirkte **genau einmal**, unmittelbar nach dem
   Booten (da hatte der Descriptor auf VideoDec geschaltet, es war also ein echter Wechsel); danach dreimal
   nichts, `0x928` blieb auf `0x60020438`. Weg **und zurück** wirkt jedes Mal, und die Freigabe kommt erst
   **536-544 ms** nach der Antwort der Firmware ([E2-freigabe.md](nachtlog/E2-freigabe.md) §2/§3). Damit ist
   auch die offene Nebenfrage **M-F1** aus `doku/60-offen.md` beantwortet, und zwar mit „nein".

   Die Freigabe hängt seit `0099` nicht mehr an `S_INPUT` und an keinem Handgriff: der Anzeigetreiber
   veröffentlicht den Descriptor auf einer eigenen Benachrichtigungskette, der Aufnahmetreiber antwortet mit
   dem Wechsel weg und zurück. Kaltstart 11:42 ohne Zutun: `0x928 = 0xE0020438`, `HDMI-1: ok`, nach
   `h713-tv` „Capture laeuft wieder nach 25 ms", Zuspieler gedimmt → **48,16 %** der Bildpunkte geändert.

   **Nicht** gedeckt bleibt der Fall, dass sich zwischendurch die Geometrie der Quelle ändert (Punkt 3).
6. **INCAP als Statusquelle.** Der Treiber liest `0x0694xxxx` **gar nicht**, obwohl der Zähler
   `+0x104` eine schöne Lebendigkeitsanzeige wäre. Grund: ohne Strom auf TVFE/TVCAP hängt jeder
   Zugriff auf ein HDMI-RX-Fenster den Bus, ohne Abort und ohne Watchdog (Patch 0096) - und die
   Reihenfolge zwischen zwei Treibern zu garantieren wäre eine Zusage, die dieser Treiber nicht
   halten kann. Schreiben ist ohnehin verboten. Die Flip-Zeiger liefern dieselbe Aussage gefahrlos -
   und seit dem Vsync-Notifier liest sie dieser Treiber nicht einmal mehr selbst.
7. ~~**Der Vsync-Notifier am Gerät.** Gebaut und im Prüfbau grün, aber noch nie gelaufen.~~
   **Abgenommen am 07.09.:** `Slot-Quelle: AFBD vsync notifier (GIC 142)` im `dmesg`, 287 Ereignisse,
   60 von 60 Bildern (Abschnitt 0).

---

## 9. Verweise

* [78-nachtplan-hdmi-switch.md](78-nachtplan-hdmi-switch.md), Anhang A - der Gesamtablauf
* [84-re-capture-ring.md](84-re-capture-ring.md) - K1/K2/K3, insbesondere „kein Capture-Interrupt"
* [nachtlog/K4-hotplug.md](nachtlog/K4-hotplug.md) - Signalverlust/-rückkehr am Gerät
* [86-video-plane-nv16.md](86-video-plane-nv16.md) §5.1 - der Vsync-Notifier, Erzeugerseite
* [nachtlog/DE-vsync-notifier.md](nachtlog/DE-vsync-notifier.md) - Entwurf, Prüfbau, Abnahme
* [82-arisc-treiber.md](82-arisc-treiber.md), [83-cpu-comm-api.md](83-cpu-comm-api.md) - die zwei APIs
* [76-plan-ch0-de.md](76-plan-ch0-de.md) §10-13 - Ring, Farbe, C-Stride
* [nachtlog/E-v4l2.md](nachtlog/E-v4l2.md) - Prüfbau, angenommene Signaturen, Abnahmevorschrift
* [nachtlog/A6-4-aufloesungswechsel.md](nachtlog/A6-4-aufloesungswechsel.md) - der Auflösungswechsel am
  Gerät und die Korrektur an `QUERY_DV_TIMINGS`
* [nachtlog/CALLBACK-luecke.md](nachtlog/CALLBACK-luecke.md) - warum kein Callback ankommt, und die
  Abnahmevorschrift für den Fix
* [nachtlog/F-abnahme-und-callback-luecke.md](nachtlog/F-abnahme-und-callback-luecke.md) - der Messbefund
  „Firmware feuert, Treiber zählt null"
* [nachtlog/A2-hpd-dauer-edid.md](nachtlog/A2-hpd-dauer-edid.md) - HPD-Senke beim EDID-Upload: 200 ms
* [nachtlog/B2-quellenwechsel.md](nachtlog/B2-quellenwechsel.md) - der Quellenwechsel als Freigabeweg
