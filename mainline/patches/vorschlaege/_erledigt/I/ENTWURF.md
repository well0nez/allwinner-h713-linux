# Paket I — Bildeinstellungen als V4L2-Controls am `sun50i-h713-hdmirx`

**Stand 07.09.2026, Vormittag. Offline gearbeitet, kein Board angefasst, nichts gebaut.**
Ergebnis dieses Verzeichnisses:

| Datei | Inhalt |
|---|---|
| `ENTWURF.md` | diese Seite |
| `0101-media-sun50i-h713-hdmirx-pq-controls.patch` | der Patch |

**Zur Nummer: 0101.** Geplant war ≥ 0099. Während dieser Sitzung sind in `patches/kernel/series` erst
`0099-media-drm-h713-rearm-capture-after-descriptor.patch` (11:04) und dann
`0100-soc-sunxi-cpu-comm-register-callbacks-off-the-bring-up-path.patch` (~11:25) aufgetaucht. Die
nächste freie Nummer ist damit **0101**; läuft die Serie weiter, ist der Patch vor dem Einreihen
umzubenennen — am Inhalt ändert das nichts.

---

## 0. Was der Patch tut, in vier Sätzen

Er hängt an `/dev/video1` neun V4L2-Controls, die die Bildeinstellungen der MIPS-Firmware setzen:
Helligkeit, Kontrast, Sättigung, Farbton, Schärfe als Standard-IDs, dazu vier eigene für die beiden
Rauschunterdrückungen, den dynamischen Kontrast und die Schwarzdehnung. Jedes Control schickt genau
einen `THal_Vp_Set*`-RPC über die `cpu_comm`-Kernel-API, ohne den Wert umzurechnen. Beim Probe fragt
der Treiber einmal die zugehörigen `THal_Vp_Get*`-Routinen und übernimmt deren Antworten als Startwert
**und** als Vorgabewert der Controls; wo keine Antwort kommt, tritt der `standard`-Preset des Herstellers
ein und das Log sagt es. Geschrieben wird beim Probe **nichts** — `v4l2_ctrl_handler_setup()` wird
absichtlich nicht gerufen.

---

## 1. Die Tabelle

Spalte **Beleg** unterscheidet drei Stufen:

* **[G]** = am Gerät gemessen (Messwert und Fundstelle genannt),
* **[D]** = aus Vendor-Datei oder statischer RE erschlossen, am Gerät nicht nachgemessen,
* **[V]** = Vermutung — kommt in dieser Tabelle **nicht** vor; was Vermutung wäre, ist nicht eingebaut
  (Abschnitt 4).

### 1.1 Die fünf Standard-IDs

| V4L2-Control-ID | RPC | Item | Register | Feld | Bereich / Schritt | Vorgabe | Beleg |
|---|---|---|---|---|---|---|---|
| `V4L2_CID_BRIGHTNESS` | `THal_Vp_SetBrightness` | 3 | `0x05001234` | `[15:0]` | 0…100 / 1 | Rückfrage, sonst 50 | **[G]** Register: `SetBrightness 100` → `0x00000064`, K5 (e). Wirkung **und Bereich am 07.09., 11:10–11:25 nachgemessen**: std im ROI 12,6 → 16,2 → 22,7 für 0/50/100, darüber flach bis 255 (`I0-helligkeit-nachgemessen.md`). Abschnitt 6.2 |
| `V4L2_CID_CONTRAST` | `THal_Vp_SetContrast` | 4 | `0x05001234` | `[31:16]` | 0…100 / 1 | Rückfrage, sonst 50 | **[G]** Register: 20/80/100 → `0x14/0x50/0x64`, K5 (c). Wand: 0→100 = **12,16 %** der Bildpunkte, mean 11,27, K5 (d) |
| `V4L2_CID_SATURATION` | `THal_Vp_SetSaturation` | 5 | `0x05001238` + `0x05140508` | `[15:0]` bzw. `[23:16]` | 0…100 / 1 | Rückfrage, sonst 50 | **[G]** fünf Punkte 0/50/59/60/100, `Gain = floor(Arg × 1,28)`, K5 (f). Wand: 60→100 = 0,56 % (Quelle überwiegend weiß) |
| `V4L2_CID_HUE` | `THal_Vp_SetHue` | 6 | `0x05001238` | `[31:16]` | 0…100 / 1 | Rückfrage, sonst 50 | **[D]** UIMapping-Tabelle, `doku/85` §A.1/§A.4. **Am Gerät nie gemessen** |
| `V4L2_CID_SHARPNESS` | `THal_Vp_SetSharpness` | 7 | `0x05001228` | `[23:8]` | 0…100 / 1 | Rückfrage, sonst 50 | **[D]** UIMapping-Tabelle. **Am Gerät nie gemessen** |

### 1.2 Die vier eigenen IDs

Alle vier sind **Menüs** mit den Stufen `Off / Low / Middle / High` — die Namen stehen wörtlich im
Kopf von `pq_picturemode.ini` (`#tnr :0-off,1-low,2-middle,3-high`, ebenso `snr`, `dci`,
`blackextenstion`). Sie sind also nicht erfunden, sondern übernommen.

| V4L2-Control-ID | RPC | Item | Register | Bereich | Vorgabe | Beleg |
|---|---|---|---|---|---|---|
| `V4L2_CID_H713_TEMPORAL_NR` | `THal_Vp_SetTNR` | 13 | **keins** | 0…3 | Rückfrage, sonst 2 | **[D]** Tabelleneintrag mit Adresse 0 → schreibt kein Register (`doku/85` §A.1/§A.5). Init-Sequenz setzt 2 (Stock-Session 17) |
| `V4L2_CID_H713_SPATIAL_NR` | `THal_Vp_SetSNR` | 12 | `0x05001248` `[7:0]` | 0…3 | Rückfrage, sonst 1 | **[G, schwach]** am Gerät stand dort die von `prep_after_boot.sh` gesetzte 1, K5 (b) — Wiedererkennen, keine Stellwegmessung |
| `V4L2_CID_H713_DYNAMIC_CONTRAST` | `THal_Vp_SetDCI` | 9 | `0x0500123C` `[7:0]` | 0…3 | Rückfrage, sonst 2 | **[G, schwach]** dito, Wert 2, K5 (b) |
| `V4L2_CID_H713_BLACK_EXTENSION` | `THal_Vp_SetBlackExtension` | 8 | **keins** | 0…3 | Rückfrage, sonst 1 | **[D]** Adresse 0 in der Tabelle. Init-Sequenz setzt 1 (Stock-Session 20) |

**Bereich 0…100 der ersten fünf:** aus dem Kopf von `pq_picturemode.ini`
(`#brightness:0~100` … `#sharpness :0~100`) — **[D]**, aber Vendor-Datei, nicht Schätzung. Am Gerät sind
davon die Punkte 0, 20, 50, 59, 60, 80 und 100 tatsächlich gefahren worden (K5 c/e/f). **Für die
Helligkeit ist die Obergrenze seit dem 07.09. gemessen** und nicht mehr nur gelesen: `SetBrightness`
150, 200 und 255 schreiben ihr Register weiter (`0x96`/`0xC8`/`0xFF`), ändern an der Wand aber nichts
mehr — vier Aufnahmen mit identischem `std 22,7` und `p95 185`
(`I0-helligkeit-nachgemessen.md`). **[G]**

**Vorgabewerte:** Die Spalte „Rückfrage" heißt: der Treiber fragt beim Probe `THal_Vp_Get<Größe>` und
nimmt die Antwort. Die genannte Zahl ist der Ersatzwert aus der Zeile `[HDMI1] standard` von
`pq_picturemode.ini` (50, 50, 50, 50, 50, tnr 2, snr 1, dci 2, blackextenstion 1) — **[D]**. Warum nicht
einfach der Presetwert: Abschnitt 3.

### 1.3 Zwei Belege, die diese Sitzung neu erbracht hat

**(a) Alle Routinennamen sind über den Hash gegengeprüft.** `cpu_comm_name2id()` ist ein `crc32_le` mit
Startwert `0x00123456` über `"<Name>_<cpu>_<pid:3>"`. Nachgerechnet für alle 35 in
`mainline/docs/reference/cpu-comm-call-table.md` genannten IDs: **jede** reproduziert sich, und zwar
genau mit dem Präfix `THal_Vp_` — mit den zwei bekannten Ausnahmen `Thal_Vp_SetBacklightLevel` und
`Thal_Vp_SetBacklightPwmInfo` (Kleinschreibung, wie die Seite es schon vermerkt). Damit steht fest, dass
die im Patch als Zeichenketten stehenden Namen zur Laufzeit die richtigen Komponenten-IDs ergeben —
`SetBrightness` → `0x7221d017`, `GetContrast` → `0x6665fe81` usw. Das ist ein Test, der hätte scheitern
können; die Seite selbst behauptet nämlich, die IDs seien „**not** derivable from the name" (das galt für
den Namen *ohne* Suffix und ohne den Startwert).

**(b) Die Aufrufform der `Get*`-Routinen ist belegt, nicht angenommen.** In
`re/captures/weltneuheit/k5-pq-handler-20260907.log` stehen die Dekompilate:

```c
/* THal_Vp_GetBrightness @ 0x8b10a528 */
int sub_8B10A528(int a1, _DWORD *a2)
{
  result = sub_8B149580();   /* a1 wird nie gelesen -> kein Argument */
  *a2 = 1;                   /* genau ein Rückgabewort */
  a2[1] = result;            /* und das ist der Wert */
  return result;
}
```

Dasselbe Dekompilat liegt für `GetContrast`, `GetSaturation` und `GetHue` vor. Für `GetSharpness`,
`GetDCI`, `GetBlackExtension`, `GetTNR` und `GetSNR` ist es **nicht** dekompiliert; belegt ist dort nur,
dass ihre Handler in derselben Set/Get-Kette der Routinentabelle liegen und **exakt gleich lang** sind
(jeder `Set`-Handler `0x2c` Byte, jeder `Get`-Handler `0x30` Byte,
`k5-calltable-static-20260907.log`). Deshalb verwirft der Treiber eine Antwort außerhalb des Bereichs,
statt sie zu benutzen — genau für den Fall, dass diese fünf doch anders aussehen.

Das ist zugleich der Grund, warum die Rückfrage **ungefährlich** ist: kein `Get`-Handler liest einen
Zeiger. `SetGamma`, `SetWhiteBalance` und `SetColorManagement` tun das sehr wohl (im selben Log
sichtbar) — das ist die Fehlerart, die die Firmware bei `THal_Vp_Init` mit Adresse 0 mitreißt. Keine der
drei ist eingebaut.

---

## 2. Standard-ID oder eigene Klasse — und warum

`V4L2_CID_BRIGHTNESS`, `_CONTRAST`, `_SATURATION`, `_HUE`, `_SHARPNESS` gibt es als Standard-IDs und sie
bedeuten dort dasselbe wie hier. Sie werden benutzt.

Für die vier anderen gibt es in `include/uapi/linux/v4l2-controls.h` **nichts Passendes**. Nachgesehen
im Baum 6.18.38 nach `NOISE`, `BLACK_LEVEL`, `DETAIL`, `SHARPNESS`, `BACKLIGHT`, `GAMMA`, `COLORFX`:

* Für zeitliche oder örtliche Rauschunterdrückung existiert **keine** Standard-ID, in keiner Klasse.
* `V4L2_CID_BLACK_LEVEL` ist als *Deprecated* markiert und meint einen Pegel, nicht eine
  Schwarzdehnung in vier Stufen.
* Für dynamischen Kontrast (DCI) gibt es nichts. `V4L2_CID_BACKLIGHT_COMPENSATION` ist eine
  Belichtungskorrektur der Kameraklasse, kein Bildverbesserer.

Deshalb ein eigener Block. Er wird im uapi-Header angemeldet, wie es für private Controls vorgesehen
ist:

```c
#define V4L2_CID_USER_SUN50I_H713_BASE		(V4L2_CID_USER_BASE + 0x1230)
```

`0x1230` ist der nächste freie Platz: der höchste vergebene Block im Baum ist
`V4L2_CID_USER_RKISP1_BASE` bei `+0x1220`. Reserviert werden wie üblich 16 IDs, vergeben sind vier. Die
IDs selbst stehen im Treiber (`V4L2_CID_H713_TEMPORAL_NR` … `_BLACK_EXTENSION`), so wie `adv7180` es
auch macht — nur die *Basis* gehört in den gemeinsamen Header, damit sie kein zweiter Treiber belegt.

---

## 3. Umrechnung — es gibt keine, und das ist der Punkt

```
V4L2-Control-Wert 0..100  ==  RPC-Argument  ->  Firmware  ->  Register
```

Der Treiber bildet den V4L2-Bereich auf das **RPC-Argument** ab und hört dort auf. Begründung:

* Jedes am Gerät gemessene Feld des PQ-Blocks enthält das Argument **unverändert**:
  `SetContrast 20/80/100` → `0x14/0x50/0x64`, `SetBrightness 100` → `0x64`,
  `SetSaturation 0/50/100` → `0x00/0x32/0x64` (`doku/81` §3). Es gibt in diesem Block keinen Faktor.
* Die Sättigung zeigt, warum man trotzdem **nicht** auf Registerwerte rechnen darf: derselbe RPC setzt
  zusätzlich den Chroma-Gain `0x05140508[23:16]` auf `floor(Argument × 1,28)`. Wer den Registerwert
  selbst ausrechnete, träfe die eine Hälfte und verfehlte die andere. Genau dieser Fehler ist Paket G
  am 07.09. passiert und korrigiert worden (`G-korrektur-saettigung.md`).
* Die Werkskurve aus `pq_factory_extern.ini` liegt **nicht** auf dieser Kette (`doku/81` §3.2, offen).
  Sie taucht im Treiber deshalb nirgends auf.
* Die einzige ungemessene Stufe der Kette — Benutzerwert → RPC-Argument (`doku/81` §2.1) — liegt
  **oberhalb** des Treibers. Der Treiber bekommt vom Anwender einen Wert 0…100 und schickt ihn als
  Argument; wer Preset-Werte einsetzen will, holt sie aus `hy310-pq`. Damit erbt der Kernel die offene
  Frage nicht.

### 3.1 Warum die Vorgabe erfragt und nicht gesetzt wird

Ein V4L2-Control muss einen Vorgabewert nennen und auf `G_CTRL` einen Ist-Wert liefern. Drei Wege waren
möglich:

1. **Vorgabe 50 und beim Probe schreiben.** Ehrlich, aber es verstellt das Bild bei jedem Boot: der
   Kontrast steht am Gerät im Ruhezustand auf `0x00000000` (K5 (c), Zeile „Ausgangszustand"), also auf
   0 — und der Ruhezustand ist der von Stock, weil `prep_after_boot.sh` dieselbe Sequenz fährt. Beim
   Probe 50 zu schreiben hieße, absichtlich von Stock abzuweichen.
   Bei der Sättigung kommt hinzu: der Ruhewert des Chroma-Gains ist `0x4C`, das entspricht
   `SetSaturation 60` — obwohl `SetSaturation` nie gerufen wurde (K5 (f)). Ob der PQ-Block
   `0x05001238` im Ruhezustand denselben Wert trägt, ist **nicht gemessen**; sein Nachbar `0x05001234`
   steht dort auf 0. Ein Schreibvorgang „auf den angenommenen Wert" kann das Bild also verändern, und
   bei Argument 0 wird es grau.
2. **Vorgabe 0 und nichts schreiben.** Wahr für den Kontrast, falsch für die Sättigung — siehe oben.
3. **Firmware fragen.** Kostet neun Aufrufe beim Probe und erfindet keine Zahl. Gewählt.

Der Treiber legt die Controls deshalb erst an, **nachdem** er gefragt hat, und benutzt die Antwort als
`def` *und* als Startwert. `v4l2-ctl -L` zeigt dann `default=<X> value=<X>` und beides ist wahr.

**Der Rückfrage-Lauf prüft sich selbst.** Die Init-Sequenz hat unmittelbar davor `SetTNR 2`, `SetSNR 1`,
`SetDCI 2` und `SetBlackExtension 1` geschickt (Stock-Sessions 17–20). Der Treiber liest den erwarteten
Wert **aus der Sequenztabelle selbst** (`h713_hdmirx_init_arg()`), nicht aus einer zweiten Abschrift, und
vergleicht. Im Log erscheint:

```
hdmirx: Bildwerte: 9 von 9 aus der Firmware gelesen, 4 von 4 gegen die Init-Sequenz bestaetigt
```

Steht dort `0 von 4` oder eine `liefert X, die Init-Sequenz hat Y gesetzt`-Warnung, ist die Deutung der
`Get*`-Routinen in Abschnitt 1.3 falsch. Das ist ein Test, der scheitern kann, und er läuft bei jedem
Boot.

---

## 4. Was **nicht** eingebaut ist, und warum

Der Nachtplan (`doku/78` §3 „I") nennt zusätzlich `PictureMode` und `VideoRange` als Custom-Controls.
Beide fehlen. Das ist eine bewusste Abweichung, keine Auslassung:

| Weggelassen | Grund | Was es hineinbrächte |
|---|---|---|
| **PictureMode** | `SetPictureMode` lädt ein ganzes Preset und setzt die fünf Bildgrößen hinter dem Treiber neu (`doku/85` §A.5) — ein Control dafür machte fünf andere still unwahr. Zusätzlich ist die **Nummerierung der Modi aus keiner ausgelieferten Datei auflösbar**; `[CONFIG] picture_mode=standard,cinema,vivid,game,energy_saving` + `special_mode=computer,hdr,custom` ist ein Kandidat, aber der Kopf der Datei verweist auf `include/PQCommon.h`, das wir nicht haben. Ein Menü, dessen Einträge man nicht benennen kann, ist schlechter als keins | Messung in Abschnitt 6.3 |
| **VideoRange** | Es gibt keine Vendor-Angabe, was 0 und 1 bedeuten — nicht einmal, wie viele Werte es gibt. Der V4L2-gerechte Ort dafür ist `v4l2_pix_format_mplane::quantization`, und `G_FMT` antwortet heute fest `V4L2_QUANTIZATION_LIM_RANGE`. Ein Control, das nicht sagen kann, welcher seiner Werte zu dieser Antwort passt, macht den Knoten in sich widersprüchlich | Messung in Abschnitt 6.3 |
| **LowLatencyMode** | dasselbe: `SetLowLatencyMode` ist aufrufbar, aber kein Vendor-Datum sagt, welche Werte es kennt. Erfundener Bereich = erfundene Zahl | Messung in Abschnitt 6.3 |
| **Backlight / dyn. Backlight** | Die Lampe hat bereits einen Treiber (`pwm-backlight` auf PWM2/PB4, Patch 0032) und ein Klassengerät. Ob `Thal_Vp_SetBacklightLevel` dieselbe Lampe stellt, ist nicht gemessen. Zwei Besitzer einer Lampe sind schlechter als einer | Beide gleichzeitig verstellen und die Wand messen |
| **Gamma** | gehört an den DRM-Knoten, Abschnitt 5 | — |
| **Weißabgleich / ColorManagement** | gehört an den DRM-Knoten (CTM), Abschnitt 5; zusätzlich nimmt `SetWhiteBalance` einen **Zeiger** | — |

---

## 5. Abgrenzung zu Paket H (DRM) — was gehört wohin

Die Frage ist berechtigt, weil Gamma und Weißabgleich auf diesem Chip **zweimal** existieren.

| Größe | Wo sie hingehört | Warum |
|---|---|---|
| **Gamma-Kurve** | **DRM**, `GAMMA_LUT` am CRTC (Patch 0095) | Das ist die **DE2**-Stufe, hinter dem Mux, in ARM-eigenen Registern (`0x05208000/0x05208800/0x05209000`, Steuerung `0x051C00E8`). Sie ist **[G]** am Gerät belegt: invertierte LUT ändert 100,00 % der Konsole und 86,56 % des Videobildes, Rückkehr 0,00 % (`doku/87` §0). Die MIPS-Seite dagegen meldet beim Start `Can not get MP GAMMAModuleID` — das Modul ist auf diesem Gerät gar nicht bestückt. `V4L2_CID_GAMMA` wäre ein zweiter Besitzer derselben sichtbaren Größe ohne festgelegten Vorrang |
| **Weißabgleich** | **DRM**, `CTM` am CRTC | Der Stock-Weißabgleich ist ein Gain je Farbkanal, der **in die Gamma-Kurve eingerechnet** wird — also genau eine Diagonalmatrix, und genau das ist `CTM` (`doku/87` §4). Die MIPS-Variante `SetWhiteBalance` will drei werkskalibrierte `double`s über einen Zeiger, die dieses Projekt nicht hat; die Init-Sequenz lässt sie deshalb schon heute weg |
| **Helligkeit, Kontrast, Sättigung, Farbton, Schärfe, TNR, SNR, DCI, Schwarzdehnung** | **V4L2**, dieser Patch | Das sind Stufen **in der MIPS-Bildkette**, vor der DE. Sie sind nur über RPC erreichbar, es gibt keinen ARM-Registerweg dorthin, und sie gehören inhaltlich an den Aufnahmeknoten: sie beschreiben, wie das Bild entsteht, das `/dev/video1` liefert |

Kurzregel: **was die ARM-Seite selbst schreiben kann, gehört an den DRM-Knoten; was nur die Firmware
kann, gehört an den V4L2-Knoten.** Beide Stufen wirken hintereinander auf dasselbe Bild — Paket H hat
gemessen, dass die DE2-Stufe auch den Videopfad einfärbt (86,56 %), Paket I stützt sich darauf, dass die
MIPS-Stufe im selben Pfad davor liegt (12,16 % beim Kontrast). Es gibt keine Überschneidung, aber es gibt
eine bekannte Wechselwirkung: **Farbe und Video-Plane sind mit den heutigen Werkzeugen nicht gleichzeitig
zu bedienen**, weil `gamma_test` und `hdmi_plane_test` beide DRM-Master sein wollen (`doku/87` §0). Das
betrifft den Abnahmelauf, nicht den Treiber.

---

## 6. Wie man jedes Control am Gerät falsifiziert

**Werkzeuglage zuerst:** auf dem Board liegt weder `v4l2-ctl` noch `modetest`
(`analyse/v4l2/hdmirx_test.c`, Kopf). Für die Abnahme fehlt genau eine Kleinigkeit: `hdmirx_test`
kennt heute keine Controls. Nötig ist ein Schalter

```
./hdmirx_test /dev/video1 --ctrl <id>=<wert>     -> VIDIOC_S_CTRL
./hdmirx_test /dev/video1 --ctrls                -> VIDIOC_QUERYCTRL/QUERYMENU über alle
```

— zwei `ioctl`-Aufrufe mit `struct v4l2_control` bzw. `struct v4l2_queryctrl`, beide schon in
`linux/videodev2.h`, das die Datei ohnehin einbindet. Ohne den Schalter ist nur **Lesen** möglich, über
`/sys/kernel/debug/sun50i-h713-hdmirx/status` (der Patch druckt dort einen Abschnitt `bild:` mit
Ist-Wert, Startwert und Herkunft je Control). Das ist Absicht: der Treiber bekommt **keinen**
Schreibweg über debugfs, der an V4L2 vorbeiführt.

Registerkontrolle jeweils mit `analyse/hdmi-seq/pq_probe.py` (liest `0x05001000, 0x600`; für die
Sättigung zusätzlich `blocks 0x05140000 0x600`), Wandkontrolle mit `wandcheck.py`/ROI wie in K5.
**Wichtig aus K5:** 16 Wörter `0x05001570…0x050015F8` laufen frei mit; sie sind vor jedem Diff
abzuziehen, sonst sieht jede Messung nach 18 Unterschieden aus.

### 6.0 Zwei Versuche, die den ganzen Patch treffen

| Versuch | Erwartung | Scheitert, wenn |
|---|---|---|
| **I-0a Selbstprüfung beim Probe.** `dmesg \| grep Bildwerte` | `9 von 9 aus der Firmware gelesen, 4 von 4 gegen die Init-Sequenz bestaetigt` | weniger als 4 bestätigt, oder eine `liefert X, die Init-Sequenz hat Y gesetzt`-Zeile → die Deutung der `Get*`-Routinen (Abschnitt 1.3) ist falsch. Bei `0 von 9` gelesen ist die Aufrufform falsch |
| **I-0b Sichtbarkeit.** `hdmirx_test --ctrls` (oder `v4l2-ctl -L` auf einem Rechner mit dem Gerät) | neun Controls; die vier eigenen als Menü mit `Off/Low/Middle/High`; Bereiche 0…100 bzw. 0…3 | ein Control fehlt → `hdl->error` beim Anlegen, Probe wäre schon fehlgeschlagen; Menü ohne Namen → `qmenu` nicht angekommen |

### 6.1 Die drei, die schon Wirkung gezeigt haben

| Control | Versuch | Erwartung | Scheitert, wenn |
|---|---|---|---|
| **Kontrast** | `--ctrl contrast=0`, Abzug; `--ctrl contrast=100`, Abzug; Wandaufnahme je Zustand | `0x05001234[31:16]` = `0x0000` bzw. `0x0064`; Wand ≈ 12 % der Bildpunkte > 25 (K5 (d): 12,16 %) | das Register folgt dem Control nicht → das Control erreicht den RPC nicht (der RPC selbst ist belegt). Wand < 5 % bei geglückter Registeränderung → die Vorbedingung aus K5 gilt in dieser Sitzung nicht mehr |
| **Sättigung** | `--ctrl saturation=60`, Abzug **beider** Blöcke; dann `=100`; dann `=0` | `0x05001238[15:0]` = 60/100/0 **und** `0x05140508[23:16]` = `0x4C`/`0x80`/`0x00`; bei 0 wird das Bild grau (Cb/Cr-Streuung im ROI bricht ein) | der Gain folgt nicht → der zweite, nachgelagerte Schreibzugriff hängt nicht am RPC (`doku/85` §A.7 hält fest, dass für ihn statisch kein Schreiber gefunden wurde). **Achtung:** `saturation=0` ist der Zustand „grau"; das ist gewolltes Verhalten der Firmware, kein Fehler |
| **Helligkeit** | **eigener Abschnitt 6.2** | | |

### 6.2 Helligkeit — entschieden, am 07.09. um 11:10–11:25

**Diese Frage ist beantwortet, während dieser Entwurf entstand.** Der Vollständigkeit halber der Hergang,
weil er die Regel zeigt, um die es in diesem ganzen Abschnitt geht.

Die alte Messung (K5 (e)): `SetBrightness 100` schreibt `0x05001234 = 0x00000064`, aber die Wand ändert
sich um 0,00 % der Bildpunkte, während derselbe Stellweg beim Kontrast 12,16 % ergab. Schluss damals:
„wirkt nicht — bitte nicht als Control anbieten".

Der Fehler lag in der Vorlage, nicht im Register: die Messung lief gegen eine **fast weiße Seite**.
Helligkeit verschiebt den unteren Teil der Kennlinie; auf einer Fläche nahe am oberen Anschlag ist dort
nichts zu verschieben. Das Kriterium „0,00 % über 25 Graustufen" konnte unter diesen Umständen gar nicht
**gelingen** — und ein Kriterium, das nicht gelingen kann, prüft so wenig wie eines, das nicht scheitern
kann.

Nachgemessen mit dunklem Material (Zuspieler auf 20 %, `I0-helligkeit-nachgemessen.md`):

| `SetBrightness` | 0 | 50 | 100 | 150 | 200 | 255 |
|---|---|---|---|---|---|---|
| `0x05001234` | `0x00` | `0x32` | `0x64` | `0x96` | `0xC8` | `0xFF` |
| std im ROI | 12,6 | 16,2 | **22,7** | 22,7 | 22,7 | 22,7 |
| p95 | 151 | 170 | **185** | 185 | 185 | 185 |

Gegenprobe hin und zurück (0/100/0/50): `std` 12,5 / 22,5 / 12,5 / 16,0 — jeder Wert trifft seine Zeile
wieder. Eine Belichtungsautomatik driftet, sie rastet nicht dreimal auf denselben Wert ein.

**Für Paket I folgt daraus zweierlei:** das Control wird angeboten wie die anderen acht, und sein Bereich
**0…100** ist gemessen statt gelesen — über 100 ändert sich nichts mehr.

**Was weiterhin offen ist:** die Kennlinie. p95 steigt, p05 bleibt bei ~115; im Tageslicht und mit
Belichtungsautomatik ist daraus keine Übertragungsfunktion abzuleiten. Der Treiber braucht sie nicht.
Und ungeprüft bleibt, ob Helligkeit einen **nachgelagerten** PROC-Registerzugriff hat wie die Sättigung
ihren Chroma-Gain (`doku/81` §3.1) — Messvorschrift: `pq_probe.py blocks 0x05140000 0x600` vor und nach
`SetBrightness 0→100`.

### 6.3 Die vier, die am Gerät noch nie gemessen wurden

| Control | Versuch | Erwartung | Scheitert, wenn |
|---|---|---|---|
| **Farbton** (`hue`) | Farbbalken zuspielen. `hue=0`, `=50`, `=100`, je Abzug + Aufnahme | `0x05001238[31:16]` = `0x0000`/`0x0032`/`0x0064`; auf der Wand wandern Cb/Cr der Farbfelder gegenläufig | das Register folgt nicht → die UIMapping-Zeile für Item 6 stimmt nicht (heute nur **[D]**). Register folgt, Wand nicht → zweiter Fall „Helligkeit" |
| **Schärfe** | Hochfrequenz-Testbild (feines Gitter/Zonenplatte). `sharpness=0` vs `=100` | `0x05001228[23:8]` = `0x0000`/`0x0064`; im ROI steigt die Kantenenergie (Summe \|∇\| oder Varianz eines Hochpasses) messbar | Register folgt nicht → Item 7 falsch. Kantenenergie unverändert → Schärfemodul nicht bestückt |
| **SNR** | verrauschte Quelle. `snr=0` vs `=3`, Abzug | `0x05001248[7:0]` = 0 bzw. 3; Bild-zu-Bild-Differenz zweier aufeinanderfolgender Aufnahmen sinkt sichtbar | Register folgt nicht (heute nur über Wiedererkennen des Ruhewerts 1 belegt) |
| **DCI** | Bild mit großem Dynamikumfang. `dci=0` vs `=3`, Abzug | `0x0500123C[7:0]` = 0 bzw. 3; Histogramm im ROI spreizt | Register folgt nicht |

### 6.4 Die zwei ohne Registerweg

`SetTNR` und `SetBlackExtension` haben in der UIMapping-Tabelle **Adresse 0** — sie schreiben
nachweislich kein Register (`doku/85` §A.1/§A.5). Für sie gibt es deshalb keine Registerkontrolle; das
ist keine Lücke des Patches, sondern eine Eigenschaft der Firmware.

| Control | Versuch | Erwartung | Scheitert, wenn |
|---|---|---|---|
| **TNR** | elog mitlesen (`re/captures/…/elog-*`), dabei `tnr=0` und `tnr=3` setzen | je Aufruf ein Paar `THal_Vp_SetTNR() ENTER` / `OnHalPqTNRChange` | kein elog-Paar → der RPC kommt nicht an (dann ist auch die Init-Sequenz betroffen, die `SetTNR 2` schickt) |
| **TNR, Wirkung** | verrauschte, **statische** Quelle; `tnr=0` vs `tnr=3`; je 30 Bilder über `hdmirx_test` mitschreiben | die mittlere Differenz aufeinanderfolgender Bilder sinkt | keine Änderung → das TSE-Modul ist nicht bestückt (dieselbe Klasse Befund wie bei der Helligkeit) |
| **Schwarzdehnung** | dunkles Material, `blackextenstion=0` vs `=3` | Schwarzpegel/`dunkel`-Anteil im ROI ändert sich | keine Änderung → Modul nicht bestückt |

### 6.5 Versuche für das, was nicht eingebaut ist

Damit die Auslassungen aus Abschnitt 4 nicht dauerhaft bleiben:

* **Bildmodus-Nummerierung.** `SetPictureMode N` für N = 0…7 durchprobieren und nach jedem N
  `GetContrast`, `GetSaturation`, `GetSharpness`, `GetTNR`, `GetSNR`, `GetDCI` und
  `GetBlackExtension` lesen; das Ergebnis gegen die sieben Zeilen von `[HDMI1]` in
  `pq_picturemode.ini` halten. Über diese sieben Werte sind `cinema`, `vivid`, `game`, `computer` und
  `hdr` **eindeutig** bestimmt; `standard` und `energy_saving` sind darin wertgleich und unterscheiden
  sich nur im `backlight` (100 gegen 80), für das es keine `Get`-Routine gibt — dieses eine Paar bleibt
  also offen. Fünf sichere Zuordnungen genügen, um die Reihenfolge aufzulösen, und der Lauf ist
  zugleich die Probe darauf, ob `SetPictureMode` die Einzelwerte überhaupt neu setzt (`doku/85` §A.5
  sagt es, gemessen ist es nicht).
* **VideoRange.** Quelle einmal auf Full Range, einmal auf Limited stellen, `SetVideoRange 0` und `1`
  durchprobieren und den Schwarzpegel im ROI messen. Erst wenn feststeht, welcher Wert zu
  `V4L2_QUANTIZATION_LIM_RANGE` gehört, kann das Control kommen — dann zusammen mit dem passenden Feld
  in `G_FMT`.
* **LowLatencyMode.** `SetLowLatencyMode 0…3`, danach `GetLowLatencyMode`. Was zurückkommt, sagt den
  Wertebereich. `GetDisplayLatency` dazu, wenn es antwortet.

---

## 7. Verhältnis zu Paket G (`userspace/hy310-pq`)

**`hy310-pq` bleibt und wird nicht dünner.** Die Arbeitsteilung ist sauber und es gibt keine
Überschneidung:

| | Paket G (`hy310-pq`) | Paket I (dieser Patch) |
|---|---|---|
| liest die Vendor-Daten (`pq_picturemode.ini`, `tvpq.db`, XML) | ja | nein |
| kennt die Bildmodi und ihre Werte | ja | nein |
| rechnet die Gamma-LUT | ja | nein (das ist Paket H) |
| setzt etwas am Gerät | **nein** (kein `/dev/mem`, kein RPC, kein Daemon) | ja, über die RPCs |

Der Weg von G nach I ist derselbe wie von G nach H, nur ohne Datei: `hy310-pq show HDMI1 vivid` nennt
die RPC-Argumente eines Bildmodus, und die setzt man als Control-Werte. Beispiel `vivid`:
Kontrast 55, Sättigung 60, Schärfe 60, TNR 2, SNR 1, DCI 3, Schwarzdehnung 1.

**Der einzige Kollisionspunkt — benannt, nicht verschwiegen:** der Treiber merkt sich die Control-Werte.
Wer denselben RPC am Treiber vorbei absetzt (über `/dev/cpu_comm`, `hdmi_seq.py`, `pq_probe.py`), macht
den gemerkten Wert unwahr, ohne dass es jemand bemerkt. Heute wird nur beim Probe zurückgelesen.
Entschärft ist das dreifach:

1. `debugfs` druckt Ist-Wert **und** Startwert nebeneinander, also sieht man, was der Treiber glaubt;
2. der Registerabzug ist die unabhängige Kontrolle, mit der jede Abnahme ohnehin arbeitet;
3. die saubere Lösung liegt bereit: die neun Controls als `V4L2_CTRL_FLAG_VOLATILE` mit einem
   `g_volatile_ctrl`, das die `Get*`-Routine ruft. Dann wäre jedes `G_CTRL` die Wahrheit der Firmware.
   **Bewusst nicht in diesem Patch**, weil damit jedes `v4l2-ctl -L` neun RPCs auslöst und weil zuerst
   Versuch I-0a zeigen soll, dass die `Get*`-Routinen überhaupt so antworten, wie Abschnitt 1.3 es liest.
   Fällt I-0a positiv aus, ist das ein Vierzeiler.

---

## 8. Trockenlauf

**Ergebnis: sauber.** Verfahren wie vorgeschrieben:

```bash
tmp=$(mktemp -d)
tar -C $tmp --strip-components=1 -xf mainline/build/cache/linux-6.18.38.tar.xz
while read -r p; do patch -s -d $tmp -p1 < "$p"; done < mainline/patches/kernel/series
patch -d $tmp -p1 --verbose < .../0101-media-sun50i-h713-hdmirx-pq-controls.patch
```

* Die Serie selbst läuft ohne Fehlschlag durch (74 Patches).
* `0101` danach: **12 Hunks in 2 Dateien, alle ohne `offset` und ohne `fuzz`.**
* Gegenprobe: die entstandene Datei ist byteweise identisch mit der Arbeitsfassung.
* `scripts/checkpatch.pl --strict`: **0 errors, 2 warnings**. Beide sind
  `Block comments use a trailing */ on a separate line` und treffen die Abschnittsköpfe im Stil dieser
  Datei — dasselbe Muster erzeugt im bestehenden `0094-media-sun50i-h713-hdmirx.patch` 22 gleichartige
  Warnungen. Nicht geändert, weil die Datei sonst zwei Kommentarstile hätte.

**Grundlage (bitte prüfen, falls die Serie weiterläuft):**

| | Wert |
|---|---|
| `patches/kernel/series` | `md5 20615c16d31bc0e1c4f0930352966cd0`, 74 Einträge |
| `sun50i-h713-hdmirx.c` **nach** der Serie, **vor** `0101` | `md5 15ab6f1515f4a5ad4c4dde9c6bbb0d80`, 2012 Zeilen |
| dieselbe Datei **nach** `0101` | `md5 460b3f5984f5a81f8f96cc20386e155c`, 2461 Zeilen |

Das ist nicht nebensächlich: die Serie hat sich **während** dieser Sitzung dreimal geändert — 11:04 kam
`0099-media-drm-h713-rearm-capture-after-descriptor.patch` hinzu, 11:10 wurde es neu geschrieben, und
gegen 11:25 ist `0100-soc-sunxi-cpu-comm-register-callbacks-off-the-bring-up-path.patch` aus
`vorschlaege/callback2` (Callback-Registrierung aus dem Probe nach
`open()`) aufgenommen worden. Der Patch ist dreimal rebasiert worden, zuletzt auf den Stand oben. Passt
der `md5` der Serie nicht mehr, vor dem Anwenden neu prüfen — die Berührungspunkte sind der Fehlerpfad im
Probe (`err_vdev` / `err_ctrl` / `err_v4l2`) und die Init-Sequenz-Tabelle, aus der
`h713_hdmirx_init_arg()` liest.

**Die Nummer ist deshalb dreimal gewandert** (0099 → 0100 → 0101). Vor dem Einreihen noch einmal
nachsehen, welche Nummer frei ist; der Inhalt ändert sich dadurch nicht, nur der Dateiname.

### 8.1 Berührungspunkt `callback2` — erledigt

`vorschlaege/callback2` verlegt die Callback-Registrierung aus dem Probe nach `open()`/`release()`
(`cb_lock`, `cb_users`, eigenes `h713_hdmirx_open()`) und ist inzwischen **in der Serie**. `0101` ist
darauf rebasiert: die Fehlerkette im Probe lautet jetzt `err_vdev → err_ctrl → err_v4l2`, und `0101`
fasst weder `h713_hdmirx_register_callbacks()` noch `h713_hdmirx_drop_callbacks()` an. Der Rest von
`0101` (Tabelle, Rückfrage, Controls, debugfs) berührt nichts, was `callback2` ändert.

**Eine Folge davon ist zu beachten:** seit `callback2` werden die Callbacks erst beim ersten `open()`
angemeldet. Die Rückfrage in Abschnitt 3.1 läuft weiterhin im Probe und ist davon unberührt — sie ist ein
ausgehender Aufruf, kein Callback, und trägt keinen Deskriptor in die Routinentabelle ein. Sie fällt
damit in die Klasse „zweiundzwanzig Aufrufe hinaus, kein Deskriptor hinein", die `callback2` als
unbedenklich beschreibt; aus neun mach einunddreißig.

**Nicht geprüft: die Übersetzung.** Ein Bau war in dieser Sitzung nicht erlaubt. Statt dessen ist der
Code zweimal gegen die V4L2-Control-API des Baums gelesen worden; was dabei nachgeschlagen wurde:

| Geprüft | Fundstelle im Baum | Ergebnis |
|---|---|---|
| Menü-Controls brauchen `step == 0`, `menu_skip_mask` ist der Ersatz | `v4l2-ctrls-core.c`, `v4l2_ctrl_new_custom()` mit `WARN_ON(step)` und `check_range()` (`step == menu_skip_mask`) | `.step` wird nicht gesetzt |
| `qmenu` darf keine leeren Zeichenketten enthalten, NULL-Abschluss üblich | `v4l2-ctrls-core.c` Zeile 1303 | vier Einträge + `NULL` |
| ein Menü-Control ist `is_int` — `v4l2_ctrl_g_ctrl()` warnt sonst | `ctrl->is_int = !ctrl->is_ptr && type != INTEGER64` | debugfs darf `v4l2_ctrl_g_ctrl()` benutzen |
| die Control-Ioctls brauchen keine `ioctl_ops`-Einträge | `v4l2-dev.c` `determine_valid_ioctls()`: `if (vdev->ctrl_handler \|\| ops->…)` | `vdev.ctrl_handler` genügt |
| `v4l2_ctrl_find()` und `v4l2_ctrl_g_ctrl()` nehmen die Handler-Sperre selbst | `v4l2-ctrls.h`, `find_ref_lock()` | nacheinander, keine Verschachtelung |
| `hdl->lock` **nicht** auf `rx->lock` legen | `video_ioctl2` hält `vdev->lock` bereits | Handler behält seine eigene Sperre |
| `id >= V4L2_CID_PRIVATE_BASE` wird abgelehnt | `v4l2-ctrls-core.c` Sanity-Check | `0x00981B30` liegt weit darunter |
| `cpu_comm_call()` mit `nargs = 0` ist vorgesehen | `cpu_comm_api.c`; im Treiber schon benutzt (`THal_Vp_DisableBlackScreen`) | Rückfrage ohne Argument ist regulär |
| `V4L2_EVENT_CTRL` | `subscribe_event` fällt jetzt auf `v4l2_ctrl_subscribe_event()` zurück | Pflicht, sobald es Controls gibt |

Zusätzlich: Klammerbilanz der geänderten Datei geprüft (0/0); die elf Ankerstellen im Treiber und die
eine im uapi-Header waren jede genau einmal vorhanden (das Änderungsskript bricht bei Mehrdeutigkeit ab,
was beim ersten Serienwechsel auch ausgelöst hat).

---

## 9. Offene Punkte, die dieser Patch **nicht** schließt

1. ~~**Wirkt die Helligkeit?**~~ — **beantwortet am 07.09., 11:25: ja** (Abschnitt 6.2). Offen bleibt
   nur die Kennlinie, die der Treiber nicht braucht.
2. **Farbton und Schärfe** sind am Gerät nie gemessen worden (Abschnitt 6.3).
3. **Haben Helligkeit und Kontrast einen nachgelagerten PROC-Registerzugriff** wie die Sättigung ihren
   Chroma-Gain? Nie gemessen (`doku/81` §3.1), Messvorschrift dort und in 6.2.
4. **Wer schreibt `0x05001234[15:0]`?** Statisch findet `doku/85` §A.6 **keine** Funktion, die
   `UIvalueMapping` mit Item 3 ruft, und trotzdem schreibt `SetBrightness` das Register. Der Weg dorthin
   fehlt in der Analyse; Kandidat ist die TSE-Namensschnittstelle (`mp_brightness`).
5. **Was ändert `0x05001038`** (`0xc003003c → 0xc06a003c`) bei Kontrast *und* Helligkeit mit? Ungedeutet.
6. **Die Bildmodus-Nummerierung** (6.5) — solange sie offen ist, gibt es kein PictureMode-Control.
7. **Wozu die Werkskurve dient** (`doku/81` §3.2) — für diesen Patch ohne Folge, weil er sie nicht
   benutzt.
