# Doku-Abgleich - Querprüfung der sechs nachgezogenen Dokumente

**Stand 07.09.2026, vormittags.** Gegengelesen wurden die sechs Dokumente, die die Nachzieh-Agenten
geändert haben, gegen den gemessenen Stand aus [79-nachtlog-20260907.md](../79-nachtlog-20260907.md),
den Teillogs in diesem Verzeichnis, den Patchdateien in `mainline/patches/kernel/` und den Skripten
unter `analyse/hdmi-seq/`.

Geändert habe ich **nur diese Datei**. Kein Board, kein `sudo`, kein Bau, kein Commit; `doku/78`,
`doku/79` und alle Teillogs nur gelesen. Wo unten eine Korrektur steht, ist sie so formuliert, dass die
Hauptsitzung sie ohne weitere Suche ausführen kann - mit Datei, Zeile und dem Beleg, der sie trägt.

*Hinweis für einen Link-Prüfer: die Verweise **innerhalb der zitierten Korrekturtexte** sind aus Sicht
der Zieldatei geschrieben (`doku/00-STATUS.md` bzw. `doku/76`), nicht aus Sicht dieses Verzeichnisses -
drei davon lösen von hier aus nicht auf und sollen das auch nicht.*

**Ergebnis in einem Satz:** die sechs Dokumente sind untereinander weitgehend stimmig und deutlich besser
belegt als vorher; es bleiben **ein schwerer Befund** (Abschnitt 1), **sechs echte Widersprüche zwischen
den sechs Dokumenten** (Abschnitt 2), **vier neue Belege, die keine sind** (Abschnitt 3), **eine nicht
zugewiesene Seite, die aus dem Einstiegspunkt heraus in die Irre führt** (doku/82, Abschnitt 4.1) und
**fünf Dinge aus dem 10:10-Stand, die in keinem der sechs Dokumente vorkommen** (Abschnitt 5).

---

## 1. Der schwerste Befund: die Brightness-Auflage steht in fünf Dokumenten, und die Messung dahinter trägt nicht

**Was in den Dokumenten steht.** Fünf Seiten führen als *Ergebnis* und als *Auflage für Paket I*:

| Datei | Stelle | Wortlaut (gekürzt) |
|---|---|---|
| `doku/00-STATUS.md` | Z. 42, Z. 73-76, Z. 189 | „`SetBrightness` wirkt nicht … `V4L2_CID_BRIGHTNESS` **nicht** als Control anbieten" |
| `doku/60-offen.md` | Z. 334-338 | „**`V4L2_CID_BRIGHTNESS` darf nicht angeboten werden**" |
| `legacy/docs/known-issues.md` | Punkt **21**, Z. 153 | „**Paket I darf `V4L2_CID_BRIGHTNESS` nicht als Control anbieten**" |
| `doku/85-re-pq-register.md` | Abschnitt 0 Z. 34, A.1 Z. 60 | „**Aber: 0,00 % Bildwirkung**" |
| `doku/75-handoff-20260907.md` | Z. 579 | „Helligkeit schreibt, wirkt aber nicht" |

**Was der 10:10-Stand dazu sagt.** [`STAND-JETZT.md`](STAND-JETZT.md) Punkt 2 unter „Als Nächstes":

> **Brightness neu messen.** Marco berichtet, dass es in seinen Tests gewirkt hat. Meine Messung
> (0,00 % über Schwelle) lief gegen eine fast weiße Seite - Helligkeit wirkt im Schwarzbereich, der
> Effekt kann darunter geblieben sein.

Und dieselbe Seite zählt die eigene Brightness-Aussage als **vierten** Fall der Regel „ein Kriterium,
das nicht gelingen kann" auf - neben `portmap`, `QUERY_DV_TIMINGS` und F's `strcmp`.

**Das ist nachprüfbar, ohne das Board anzufassen.** Die Quellmessung
[`K5-board-verifikation.md`](K5-board-verifikation.md) sagt es in ihrem eigenen Abschnitt (f), Z. 107-108,
selbst:

> Wirkung auf der Wand bei `SetSaturation` 60 → 100: mean 3,54, **0,56 %** der Bildpunkte > 25 - klein,
> **weil die Quellseite überwiegend weiß und grau ist**.

Dieselbe Quellseite, dieselbe Sitzung, derselbe ROI. Eine Helligkeitsanhebung auf einer fast weißen
Vorlage kann die Schwelle „> 25" kaum erreichen - der Wert 0,00 % **konnte nicht gelingen**. Der
Kontrast-Gegenwert 12,16 % beweist nicht das Gegenteil, sondern nur, dass Kontrast auf weißem Material
sichtbar wirkt und Helligkeit dort nicht; das ist von beiden Reglern zu erwarten.

**Die Zusatzbegründung trägt ebenfalls nicht.** Fünf Seiten stützen die Aussage auf Stocks
Startmeldungen `mp_dci_data is NULL` und `Can not get MP GAMMAModuleID`. Die Meldungen nennen das
**Gamma-** und das **DCI-Modul**, nicht ein Helligkeitsmodul (`doku/85` Z. 259 und Z. 407 - dort steht
ausdrücklich „für Helligkeit/Kontrast/Sättigung gibt es keine …"). Der Schluss „also ist das
Helligkeitsmodul nicht bestückt" ist eine Analogie, keine Messung. `doku/85` selbst kennzeichnet ihn in
seinem „offen gelassen" richtig als Vermutung; die vier anderen Seiten führen ihn als Erklärung.

**Korrektur (fünf Stellen, gleicher Text).** Die Auflage bleibt vorläufig stehen - sie ist die sichere
Seite - , aber sie ist als **ungeklärt** zu kennzeichnen, nicht als belegt:

> `SetBrightness` schreibt sein Register (`0x05001234[15:0]`, gemessen und unstrittig). **Ob es aufs Bild
> wirkt, ist offen.** Die 0,00 % aus `K5-board-verifikation.md` (e) sind kein Gegenbeleg: der ROI war
> überwiegend weiß und grau (dieselbe Quelle sagt das in Abschnitt (f) über die Sättigungsmessung), und
> Helligkeit wirkt im Schwarzbereich. Marco berichtet Wirkung in eigenen Tests. **Nachzumessen:** dunkles
> Material, großer Stellweg, Bild ansehen statt nur die Kennzahl (`STAND-JETZT.md`, „Als Nächstes" Punkt 2).
> Bis dahin `V4L2_CID_BRIGHTNESS` in Paket I **nicht** anbieten - aus Vorsicht, nicht wegen eines Belegs.

Betrifft: `doku/00-STATUS.md` Z. 42 / Z. 73-76 / Z. 189, `doku/60-offen.md` Z. 334-338,
`legacy/docs/known-issues.md` Punkt 21 (Z. 153, Spalten 2 und 3), `doku/85-re-pq-register.md` Z. 34 und
Z. 60, `doku/75-handoff-20260907.md` Z. 579. In `doku/81-pq-datenmodell.md` Z. 315 steht dieselbe
Ableitung ebenfalls.

---

## 2. Widersprüche **zwischen** den sechs nachgezogenen Dokumenten

Das sind die, die zählen: sie sind in einem Durchgang entstanden und stehen jetzt nebeneinander im Repo.

### 2.1 Doorbell-Restunsicherheit: zwei Dokumente sagen „geschlossen", eines sagt „offen"

* `doku/60-offen.md` Z. 43-49: „**Der Doorbell-Puls ist entbehrlich - die Restunsicherheit ist
  geschlossen.**"
* `doku/75-handoff-20260907.md` (Abschnitt 4): „**Erledigt.** Genau dieser Lauf ist gefahren."
* `legacy/docs/known-issues.md` Z. 51 („Restunsicherheit benannt") und **Z. 128** („**offen, klein** -
  fällt mit dem nächsten Kaltstart-Lauf, der ausschließlich `0091` benutzt").

**Auflösung: geschlossen.** [`B-abnahme-board.md`](B-abnahme-board.md) sagt es zweimal und nachprüfbar:
Z. 3-4 „Prep **ohne** Schritt 1 und **ohne das alte Modul** (`/root/prep_ohne_arisc.sh`)" und Z. 62-64
„Der Doorbell-Puls ist in diesem Treiber **nicht** enthalten, und der Handshake lief trotzdem - damit ist
auch die Restunsicherheit aus `B-puls-messung.md` erledigt". Gegengeprüft: `0091` enthält keinen
`TX_IRQ_EN`-Puls (`grep` über den Patch findet den Begriff nur im Kopfkommentar, das die Abwesenheit
begründet). Der einzige verbliebene `TX_IRQ_EN`-Puls im Baum betrifft **Port 1 (MIPS, `cpu_comm`)**, nicht
den ARISC-Port 0 - er kann die Frage nicht berühren.

**Korrektur:** `legacy/docs/known-issues.md` Z. 128, Zeile „5b - Restunsicherheit": Spalte 3 von
„**offen, klein**" auf „**geschlossen** (07.09., B-Abnahme 23:32-00:05)" ändern, Spalte 4 um
`doku/nachtlog/B-abnahme-board.md` Z. 3-4 und Z. 62-64 ergänzen. Z. 51 („Restunsicherheit benannt") auf
„Restunsicherheit **geschlossen**" ziehen.

**Anmerkung für die Hauptsitzung:** die Auftragslage vom 09:58 (Punkt 10) führt die Restunsicherheit noch
als offen. Zwei Agenten sind bewusst dem Teillog gefolgt und haben das dokumentiert. Wenn die
Hauptsitzung einen Grund hat, an ihrer Fassung festzuhalten, gehört der Grund ins Teillog - sonst stehen
danach wieder drei Fassungen im Repo.

### 2.2 Paket C wird als „abgenommen" ohne Vorbehalt geführt, obwohl einer seiner drei Zwecke nie belegt wurde

[`C-cpu-comm.md`](C-cpu-comm.md) Z. 350 nennt als Zweck der C-Abnahme **drei** Punkte:

> `THal_Vp_SetSource(3)` aus dem Kernel über debugfs, **`SignalChange` im Kernel-Handler**,
> `/dev/cpu_comm` weiterhin funktionsfähig

Der mittlere ist genau das, was die Callback-Lücke offenlegt (`SignalChange: 0 mal`).

* `doku/00-STATUS.md` Z. 36 nennt zwei Punkte, kein Vorbehalt.
* `doku/60-offen.md` Z. 164 nennt zwei Punkte, Spalte „offen" = **` - `**.
* `doku/75-handoff-20260907.md` hat den Vorbehalt aufgenommen (der Agent hat ihn gefunden).

**Korrektur:** `doku/00-STATUS.md` Z. 36 und `doku/60-offen.md` Z. 164 um denselben Halbsatz ergänzen:

> Der dritte Zweck der C-Vorschrift (`C-cpu-comm.md` Z. 350) - `SignalChange` **im Kernel-Handler** -
> ist **nicht** belegt; er ist genau das, was die Callback-Lücke betrifft.

In `doku/60-offen.md` Z. 164 gehört das in die Spalte „offen"; ein ` - ` dort ist heute falsch.

### 2.3 Die Paketliste zählt in drei Dokumenten verschieden

| Datei | Aussage |
|---|---|
| `doku/00-STATUS.md` (Tabelle „Stand je Paket") | A, B, C, D, E, H abgenommen · F läuft · **G „fertig"** · I nicht begonnen |
| `doku/60-offen.md` Z. 155 | „**sechs Pakete am Board abgenommen (A, B, C, D, E, H)**" |
| `doku/75-handoff-20260907.md` **Z. 25** | „**B, C, D, E, G und H sind am Gerät abgenommen**" |

75 zählt **G** mit und lässt **A** weg. G ist nachweislich **nie am Gerät** gewesen:
[`G-pq.md`](G-pq.md) Z. 8 „**Kein Board angefasst**" und Z. 177 „**Keine Board-Anfrage.** Paket G ist
vollständig offline abgeschlossen." Sein Beleg („Gamma-LUT bitgleich zum Legacy-Rechner") ist ein
Host-Vergleich - ein gültiger Beleg, der hätte scheitern können, aber keine Board-Abnahme.

**Korrektur:** `doku/75-handoff-20260907.md` Z. 25 auf
„**A, B, C, D, E und H sind am Gerät abgenommen**, F ist am Gerät gelaufen; **G ist offline fertig**
(bitgleich gegen den Legacy-Rechner, kein Board)" ändern.

Dieselbe Unschärfe steckt in [`STAND-JETZT.md`](STAND-JETZT.md): die Tabelle heißt „Was am Gerät läuft"
und enthält G. Wenn die Hauptsitzung ihre eigene Seite anfasst, gehört dort eine Fußnote hin.

### 2.4 Pflichtlisten-Punkt 22 steht auf „gelöst", während zwei andere Seiten denselben Sachverhalt als offen führen

`legacy/docs/known-issues.md` Z. 154, Punkt **22** (Descriptor schaltet die Capture ab): Spalte 3
= „**gelöst** - zwei belegte Freigabewege". Dagegen:

* `doku/60-offen.md` Z. 130-135: „**Kein Treiber gibt die Capture nach dem Descriptor wieder frei.** …
  Solange das keiner der Treiber tut, zeigt der erste Kaltstartlauf ein **Standbild**."
* `doku/00-STATUS.md` Z. 96-100: die Freigabe ist **Schritt 5 des Handrezepts**.

Beide Aussagen sind für sich richtig - der *Mechanismus* ist gelöst, die *Freigabe im Betriebspfad* nicht.
Die Pflichtliste hat aber eine eigene Messlatte (Marco, 07.09.): „richtig zu lösen oder mit Beleg als
Stock-Verhalten zu zeigen - **kein Workaround**". Ein Handgriff im Rezept ist genau der Workaround, den
diese Regel ausschließt. Wer die Liste abhakt, hakt hier zu früh ab.

**Korrektur:** `legacy/docs/known-issues.md` Z. 154, Spalte 3:

> **Mechanismus geklärt, Freigabe im Betriebspfad offen.** Zwei belegte Wege zurück (beide Stock-RPCs),
> aber **kein Treiber fährt einen davon** - der erste Kaltstartlauf zeigt deshalb ein Standbild
> (`doku/60-offen.md`, „Kein Treiber gibt die Capture nach dem Descriptor wieder frei").

### 2.5 `VIDIOC_S_INPUT` als Freigabeweg: 88 sagt ja, 60-offen sagt ungemessen, der Code sagt Nullwechsel

* `doku/88-v4l2-hdmirx.md` §8 Punkt 5 (Z. 527-535): „`VIDIOC_S_INPUT` ist ohnehin ein Quellenwechsel und
  damit **der Weg**, die vom Descriptor abgeschaltete Capture wieder freizugeben" - und im selben Absatz:
  „ein `SetSource(3)`, wenn HDMI-1 schon aktiv ist, bleibt ein Nullwechsel - der gibt nichts frei."
* `doku/60-offen.md` Z. 136-138 führt genau das als **offene Nebenfrage M-F1**: „reicht ein
  *wiederholtes* `SetSource(3)` …, oder braucht es den echten Wechsel? **Ungemessen.**"
* Der Code entscheidet die Frage praktisch: `0094-media-sun50i-h713-hdmirx.patch` Z. 1344-1352 -
  `h713_hdmirx_s_input()` ruft ausschließlich `h713_hdmirx_set_source(rx)`, also `SetSource(3)`. Ein
  „weg und zurück" gibt es dort nicht. In der Betriebsreihenfolge (Plane-Enable schreibt den Descriptor,
  HDMI-1 ist längst aktiv) ist `S_INPUT(0)` deshalb **immer** der Nullwechsel - und `doku/88` Z. 363
  sagt selbst „Nullwechsel ist normal, kein Fehler".

Der erste Satz von Punkt 5 ist damit im heutigen Treiber nicht wahr. Er ist die Aussage, an der ein
Nachfolger hängen bleibt, weil sie nach einer Lösung klingt.

**Korrektur:** `doku/88-v4l2-hdmirx.md` §8 Punkt 5, den Schlusssatz ersetzen durch:

> Für diesen Treiber heißt das: `VIDIOC_S_INPUT` **wäre** der natürliche Ort für die Freigabe, aber die
> heutige Fassung ruft nur `SetSource(3)` (`0094`, `h713_hdmirx_s_input`) - bei bereits aktivem HDMI-1
> also den Nullwechsel, der nichts freigibt. Ob der Nullwechsel genügt, ist **ungemessen**
> (`doku/60-offen.md`, Nebenfrage **M-F1**); belegt ist nur der echte Wechsel `SetSource(1)` →
> `SetSource(3)` aus `B2-quellenwechsel.md`.

### 2.6 Fünf oder sechs Messpunkte

`doku/86-video-plane-nv16.md` Z. 121 schreibt „**sechs** Messpunkte am Gerät";
`doku/85-re-pq-register.md` Z. 23 und `doku/60-offen.md` Z. 350 schreiben „**fünf**".
[`K5-board-verifikation.md`](K5-board-verifikation.md) §f hat fünf Zeilen (0, 50, 59, 60, 100).

**Korrektur:** `doku/86-video-plane-nv16.md` Z. 121, „sechs Messpunkte" → „fünf Messpunkte".

### 2.7 Zwei gemeldete Widersprüche sind inzwischen erledigt - bitte nicht noch einmal anfassen

Die Agenten liefen parallel; zwei Meldungen sind dadurch überholt:

* „`doku/85` A.7 führt Chroma-Gain und `SetSaturation` weiter als zwei Regler" (gemeldet von den Agenten
  für 00-STATUS und für 86/87/88). **Erledigt:** `doku/85` Z. 23 und Z. 312 tragen die Widerlegung, die
  Überschrift von A.7 ist durchgestrichen.
* „`doku/81` bildet Sättigung 60 auf `0x5C` ab" (gemeldet vom Agenten für 86/87/88, steht auch in
  `doku/79` als Widerspruch Nr. 3). **Erledigt:** `doku/81` Z. 145-150 bildet 60 auf `0x4C` ab und führt
  `0x5C` nur noch als „Fassung 1 (widerlegt)" (Z. 180).

---

## 3. Belege, die keine sind - vier neue Funde

Bekannt und in allen Dokumenten richtig behandelt: `portmap: 0,1,2` und `QUERY_DV_TIMINGS`. Dazu kommen:

### 3.1 „Wand mean 131,2" als Beleg dafür, dass F ein Bild bringt

`doku/00-STATUS.md` Z. 22: „**`hy310-tv` läuft am Gerät**, das Bild kommt (Wand mean 131,2)."
Ebenso `doku/75-handoff-20260907.md` Z. 802.

Dieselbe Sitzung misst für den **eingefrorenen** Rahmen nach `xrandr --off`
**mean 130,4** - nachzulesen in `doku/88-v4l2-hdmirx.md` Z. 496 und in
[`F-abnahme-und-callback-luecke.md`](F-abnahme-und-callback-luecke.md) Z. 35-37. Die Zahl unterscheidet
also nicht zwischen „Bild kommt" und „Standrahmen steht". Als Beleg trägt sie nichts.

**Was trägt:** der Trockenlauf (`/dev/video1`, `card1`, CRTC 36, Plane 38, `hdmi-ring`, `signal
vorhanden`) und dass F das Gerät nach dem `strncmp`-Fix überhaupt findet - vorher konnte es das auf
keinem Board.

**Korrektur:** `doku/00-STATUS.md` Z. 22 - „(Wand mean 131,2)" streichen und ersetzen durch
„(Trockenlauf nennt `/dev/video1`, `card1`, CRTC 36, Plane 38, `hdmi-ring`)". In
`doku/75-handoff-20260907.md` Z. 802 die Zahl stehen lassen, aber mit dem Zusatz „ - die Zahl allein
trennt nicht vom Standrahmen (130,4), siehe doku/88 Z. 496".

### 3.2 M4: zwei der drei Spalten können den Fehlerfall nicht zeigen

[`M4-hpd-dauer.md`](M4-hpd-dauer.md) belegt den **HPD-Zyklus** als zweiten Freigabeweg mit drei Spalten:
Zuspieler `connected`, `0x06940928 = 0xE0020438`, „INCAP zählt (+61/s)", dazu „Wand vs. Referenz
**0,00 %**".

* **„Wand vs. Referenz 0,00 %"** ist genau das, was ein **Standrahmen** liefert, solange die Quelle sich
  nicht ändert - es ist derselbe Fehlerfall, gegen den die Messung antritt.
* **„INCAP zählt"** ist nach dem eigenen Hauptbefund des Projekts nicht unterscheidend: `doku/79`
  („Die zwei teuersten Funde" Nr. 2) und `doku/60-offen.md` Z. 98 halten fest, dass `+0x104` **auch im
  abgeschalteten Zustand weiterzählt**, „geschrieben wird nichts".

Es bleibt genau **ein** tragfähiges Kriterium: das Rückspringen von `0x06940928` auf `0xE0020438`. Das
ist ein echter Beleg (der Wert war vorher `0x60020438`), aber es ist ein Registerbild - und die
Schwesterwmessung [`B2-quellenwechsel.md`](B2-quellenwechsel.md) hat sich ausdrücklich **nicht** darauf
verlassen, sondern den Gamma-Reiz an der Quelle benutzt („Beweis über den Gamma-Reiz Y 118,5 → 61,5
statt über das Registerbild"), weil der Rundlauf **null strukturelle Registerunterschiede** hinterlässt.

**Folge für die Dokumente:** an den Stellen, an denen die zwei Freigabewege als gleichwertig „belegt"
nebeneinanderstehen, ist der Unterschied zu benennen:

> Beide Wege sind belegt, aber **verschieden stark**: der Quellenwechsel mit einem Reiz an der Quelle
> (B2), der HPD-Zyklus allein über das Freigabebit `0x06940928` (M4) - dessen andere zwei Spalten
> („Wand 0,00 % gegen Referenz", „INCAP zählt") können einen Standrahmen nicht ausschließen. Ein Reiz
> nach dem HPD-Zyklus ist eine Messung von einer halben Minute und schließt die Lücke.

Betrifft: `doku/00-STATUS.md` Z. 96-100, `doku/60-offen.md` Z. 102-107,
`legacy/docs/known-issues.md` Punkt 22 (Z. 154), `doku/84-re-capture-ring.md` §4.4/§5,
`doku/86-video-plane-nv16.md` §4.

### 3.3 Paket G steht unter „am Gerät abgenommen" - sein Beleg ist ein Host-Vergleich

Siehe 2.3. Der Beleg „Gamma-LUT bitgleich zum Legacy-Rechner" ist gültig und **konnte scheitern**; er
ist nur keine Gerätemessung. Die Überschrift, unter der er steht, behauptet mehr als der Wert hergibt.
Betrifft `doku/75` Z. 25 und, wenn die Hauptsitzung sie anfasst, `STAND-JETZT.md`.

### 3.4 `Can not get MP GAMMAModuleID` als Erklärung für die Helligkeit

Siehe Abschnitt 1, zweiter Teil. Die Meldung nennt Gamma und DCI, nicht die Helligkeit. Sie stützt die
Aussage nicht und kann sie auch nicht widerlegen - sie ist als Indiz zu kennzeichnen, nicht als
Erklärung. Betrifft `doku/00-STATUS.md` Z. 76, `doku/60-offen.md` Z. 336-338,
`legacy/docs/known-issues.md` Z. 153, `doku/75` Z. 579, `doku/81` Z. 315.

---

## 4. Nicht zugewiesene Seiten, die dem nachgezogenen Stand widersprechen

### 4.1 `doku/82-arisc-treiber.md` - die schwerste Lücke, weil sie aus dem Einstiegspunkt heraus verlinkt ist

`doku/00-STATUS.md` Z. 18-20 nennt 82 als **die** Fachseite für „HPD/EDID kommen aus dem Kernel". Wer dem
Verweis folgt, liest drei überholte Aussagen:

| Zeile in `doku/82` | steht dort | gemessener Stand |
|---|---|---|
| Z. 405 (Schritt 10 der Sequenz), Z. 410-415, Z. 490 | „**10 s warten**" / „~13 s, davon 10 s HPD low" / „10 s ist der Wert … ihn zu kürzen ist eine **Messung** (Kandidat für einen Board-Slot)" | `HPD_DOWN_MS 200` in `0091` Z. 563; gemessen **und** Stock-Wert; Sequenz 17,65 s statt 28,8 s ([`A2-hpd-dauer-edid.md`](A2-hpd-dauer-edid.md), [`M4-hpd-dauer.md`](M4-hpd-dauer.md)) |
| §12 Punkt 1, Z. 531-533 | „**Der Fix ist noch nicht am Gerät nachgemessen**" | B ist abgenommen, 09:02-09:10 ([`B-abnahme-board.md`](B-abnahme-board.md)) |
| §12 Punkt 2, Z. 535-541 | „eine Messreihe *ohne* Puls ist in doku/ aber **nirgends** mit Lauf-Nummern hinterlegt" | [`B-puls-messung.md`](B-puls-messung.md): drei Läufe, zwei Unterbefehle, drei Kaltstarts; dazu die B-Abnahme ohne das alte Modul |

**Korrektur (drei Eingriffe in `doku/82`):**

1. Z. 405 Tabellenzeile 10: „**10 s warten**" → „**`HPD_DOWN_MS` warten (200 ms)**".
2. Z. 410-415 („Die 10 Sekunden."): den Absatz behalten, aber als Herkunft kennzeichnen und mit
   „**Korrektur 07.09.: gemessen, 200 ms genügen - für den Wiederanlauf (M4) und für den EDID-Fall (A2),
   und 200 ist zugleich der Stock-Wert (`SetHPDTimeInterval 0xC8`). `HPD_DOWN_MS` steht auf 200.**"
   abschließen.
3. Z. 490 („~13 s, davon 10 s HPD low") → „~2,5 s, davon 200 ms HPD low".
4. §12 Punkt 1 letzten Satz ersetzen: „**Abgenommen am 07.09., 09:02-09:10** - Zuspieler `connected
   1920x1080` aus dem Kernel, Sequenz nach 17,65 s, Wächter falsifizierbar (`B-abnahme-board.md`)."
5. §12 Punkt 2 ersetzen: „**Gemessen** - `B-puls-messung.md` (drei Läufe, zwei Unterbefehle, drei
   Kaltstarts, einmal als allererster Befehl seit dem Kaltstart) und die B-Abnahme, die ohne das alte,
   pulsende Modul lief. `0091` pulst nicht."

### 4.2 `doku/77-plan-hdmi-integration.md` §5 - die Abnahmetabelle definiert vier Kriterien, die heute nicht mehr taugen

Das ist die Tabelle, in der die Abnahmen ursprünglich festgelegt wurden; `doku/60-offen.md` verweist auf
77 als „Architektur unverändert", `doku/00-STATUS.md` als „die Pläne, aus denen die Patches entstanden
sind". Zeilen 218-227 (A = 218, E = 222, G = 224, I = 226):

| Paket | Kriterium dort | Warum es heute nicht trägt |
|---|---|---|
| **A** | „NV12-Plane in `modetest` sichtbar" | `modetest` gibt es auf dem Board nicht (`doku/79`, Widerspruch 5) |
| **E** (Z. 222) | „`v4l2-ctl --query-dv-timings` meldet 1080p60" | Übersetzungszeit-Konstante, `min == max` - **kann nicht scheitern** |
| **E** (Z. 222) | „`SOURCE_CHANGE` beim Stecken" | feuert nie, solange die Callback-Lücke steht - **kann nicht gelingen** |
| **G** | „Boot-elog ohne „Can not get …"" | die Meldung steht weiterhin da und wird an fünf Stellen als *Erklärung* zitiert; G ist trotzdem als „fertig" geführt - gegen ein **anderes** Kriterium |
| **I** (Z. 226) | „`v4l2-ctl --set-ctrl=**brightness**=…` wirkt" | genau der Regler, den fünf Seiten für Paket I **verbieten** (Abschnitt 1) |

Die I-Zeile ist die gefährlichste: sie ist die Abnahmevorschrift für das nächste Paket und steht direkt
gegen die Auflage in `00-STATUS`/`60-offen`/`known-issues`.

**Korrektur:** in `doku/77` §5 einen Kasten über die Tabelle setzen:

> **Überholt am 07.09.** Diese Tabelle stammt aus der Planung. Vier ihrer Kriterien tragen nicht mehr:
> A („modetest" - auf dem Board nicht vorhanden), E („`--query-dv-timings`" - Übersetzungszeit-Konstante;
> „`SOURCE_CHANGE`" - feuert nie, Callback-Lücke), G („Boot-elog ohne ‚Can not get …'" - die Meldung steht
> weiterhin da; G wurde gegen ein anderes Kriterium abgenommen) und I („brightness wirkt" - für Paket I
> derzeit ausdrücklich nicht anzubieten, `doku/60-offen.md`). Der maßgebliche Stand steht in
> `doku/00-STATUS.md` („Stand je Paket") und `doku/60-offen.md`.

### 4.3 `doku/76-plan-ch0-de.md` §12.4/§12.5 - von zwei Agenten gemeldet, bestätigt

Z. 471-474: „der Umschalter dafür ist **INCAP `0x0694084C`** (`0x04000C00` → `0x0C000C00`, mit
`0x06940400` `0x21`→`0x61` und `0x06940824` Bit 31)"; Z. 485 nennt „INCAP-ICSC einschalten" als Weg 3.

Gemessen ist das Gegenteil: im laufenden Betrieb `0x400 = 0x21`, `0x824 = 0x0000000B`
([`B2-quellenwechsel.md`](B2-quellenwechsel.md), [`A-abnahme-board.md`](A-abnahme-board.md)).
`doku/84` trägt die Widerlegung, `doku/76` nicht.

**Korrektur:** in `doku/76` §12.4 nach dem Absatz einfügen:

> **Widerlegt am 07.09.** `0x06940400 = 0x61` und `0x06940824` Bit 31 kennzeichnen den Zustand **nach**
> dem Descriptor - und in dem ist die Capture abgeschaltet. Im laufenden Betrieb steht `0x21` bzw.
> `0x0000000B`. Einzelheiten und der Korrekturkasten in [84-re-capture-ring.md](../84-re-capture-ring.md);
> Messung in `nachtlog/B2-quellenwechsel.md`.

Dasselbe eine Zeile unter §12.5 Punkt 3.

### 4.4 `doku/79` selbst ist an drei Stellen überholt - und `00-STATUS` schickt jeden Neuling zuerst dorthin

`doku/00-STATUS.md` Z. 224 und Z. 261: „**das Protokoll. Zuerst lesen, wenn du wissen willst, was
gemessen ist.**" Die Kopftabelle von `doku/79` (Z. 21-37) sagt aber:

* **B** „teilweise abgenommen … scheitert an `CheckEDIDUpdateStatus`" - inzwischen abgenommen.
* **E** „Patch integriert, **Probe scheitert** … `-EBUSY` auf `[0x05600320-0x05600327]` - der
  AFBD-Treiber hält den Bereich bereits" - dieser Blocker ist durch den Vsync-Notifier **erledigt**
  (`doku/88` Z. 463). Das heutige `-EBUSY` hat eine **andere** Ursache. Ein Leser, der beide `-EBUSY`
  für dasselbe hält, sucht an der falschen Stelle.
* **F** „Entwurf fertig, Abnahme offen" - F ist gelaufen.
* Widerspruch **Nr. 3** (Z. 123, „doku/81 bildet 60 → `0x5C` ab") ist erledigt (2.7).

`doku/79` gehört Marco und ist Protokoll - ich schlage **keine** inhaltliche Änderung vor. Was ohne
Eingriff in die Substanz hilft: **eine** Zeile unter der Überschrift, die auf den jüngeren Stand zeigt
(„Kopftabelle = Stand 08:57; der Vormittag steht in `nachtlog/STAND-JETZT.md` und in
`doku/00-STATUS.md`"). Alternativ die Formulierung in `doku/00-STATUS.md` Z. 224 entschärfen - siehe
Abschnitt 6.

### 4.5 `analyse/hdmi-seq/arisc_edid_init.sh` Z. 30 hält weiter `sleep 10`

Der Betriebspfad steht auf 200 ms, die Rückfallebene auf 10 s.
[`A2-hpd-dauer-edid.md`](A2-hpd-dauer-edid.md) sieht ausdrücklich vor, das Ergebnis im Skript zu
vermerken; das ist nicht geschehen. **Korrektur:** in Z. 30 hinter `sleep 10` den Kommentar
`# 200 ms genuegen (A2-hpd-dauer-edid.md, 07.09.); 10 s nur aus Vorsicht in der Rueckfallebene` setzen -
oder den Wert angleichen, dann aber mit einem Lauf belegt.

### 4.6 Die Board-Kopie von `pq_saturation.py` schreibt weiter

Im Repo zurückgezogen (Kopf: „ZURUECKGEZOGEN am 07.09.2026. Liest nur noch"), unter `/root/` auf dem
Board nach `doku/60-offen.md` Z. 365-368 noch die schreibende Fassung mit der widerlegten Formel. Das ist
Abschnitt 0a in klein. Gehört auf die Liste des nächsten Board-Slots; ich fasse das Board nicht an.

### 4.7 Teillogs: bestätigt, was die Agenten gemeldet haben

Ich habe die gemeldeten Stellen nachgeschlagen und bestätige sie; sie sind Protokoll und bleiben stehen,
sollten aber beim nächsten Lesen bekannt sein:

* **`K1-K3-re.md`** Z. 21 und Z. 47 tragen die widerlegte Polarität (`0x21→0x61` als „Normalfall der
  guten Sequenz"; `0x928` Bit 31 im Betrieb „0"). `doku/79` führt das als offenen Widerspruch Nr. 1.
  **Er ist inhaltlich entschieden** - alle Messungen der Nacht und `doku/84` sagen Bit 31 = 1 = Capture
  schreibt. Offen ist nur, dass es im Teillog noch anders steht.
* **`K5-K6-re.md`** Z. 46/184 tragen „zwei getrennte Regler" weiter (durch K5-Board §f widerlegt).
* **`E-v4l2.md`** §6 ruft `/dev/video0` (am Gerät `video1`), nennt „flip-pointer sampling timer" (heute
  Vsync-Notifier) und führt `QUERY_DV_TIMINGS` in der Sollausgabe.
* **`D-cstride-fix.md`** §2/§3 nennt die Frist weiter „200 ms"; `REGEL1-0093-0095.md` §3.1 hat sie auf
  1 s gesetzt. §4 Teil C führt „`0xF00` → die Klammer hat gegriffen" als Ausgang - das trennt die Fälle
  nicht, weil der Treiber nach Fristablauf trotzdem programmiert (`0093` Z. 923: `drm_err`, danach
  Source 0). Nur `dmesg | grep "did not reprogram the chroma stride"` entscheidet. **Gegengeprüft:**
  die Meldung ist `drm_err` und die Schwestermeldung `READY did not clear` ist `drm_warn` - beide
  erscheinen ohne `drm.debug`, die beiden `grep`-Kriterien sind also tatsächlich falsifizierbar.
* **`B-puls-messung.md`** ordnet die Punkte „#2/#8" zu; in der Pflichtliste sind das GPU/Wayland und das
  EDID-DMA-Rätsel. Gemeint sind 5b und 17.
* **`C-cpu-comm.md`** §4 heißt „Pflichtliste Punkt #6", die Sache ist Punkt **#10**; `doku/79` Z. 25
  benutzt „#6" für ein drittes Thema. Dieselbe Nummer für drei Sachen.
* **Nummernkollision M1/M2:** `J-pflichtliste.md` §3 (M1 = Hot-Plug am Kabel, M2 = MIPS-Kaltstart-Zähler)
  gegen `REGEL1-0093-0095.md` §4 (M1 = Frist F1 verengen, M2 = kann `wait_ready` gelingen).
  **REGEL1s M2 ist erledigt (09:16), J's M2 nicht.** `legacy/docs/known-issues.md` hat den Warnhinweis
  bereits; `doku/60-offen.md` Z. 318-320 nennt „M1" und „M2" ohne Quellenangabe - dort gehört
  „(J-Fassung)" dahinter, sonst hakt der Nächste den falschen Punkt ab.

---

## 5. Was im gemessenen Stand steht und in **keinem** der sechs Dokumente vorkommt

Nachgeprüft mit `grep` über `doku/*.md` und `legacy/docs/*.md`:

### 5.1 Der Rückweg

`mainline/patches/vorschlaege/rueckweg/0098-revert-cpu-comm-kernel-callback-registration.patch`
(28,9 kB, 10:08) und `tftp/h713-kernel-netboot.fit.GUT-e39777bf` + `mainline/build/modroot.GUT/`.
`grep -l "0098"` über `doku/` und `legacy/docs/` findet **keine** Fundstelle. Wer heute vor einem Board
mit nicht probendem `0094` steht und `00-STATUS` liest, erfährt nicht, dass zwei fertige Rückwege
danebenliegen.

**Korrektur:** in `doku/00-STATUS.md`, Abschnitt „Was gerade offen ist", unmittelbar nach dem
Callback-Absatz:

> **Zwei Rückwege liegen fertig daneben** (`nachtlog/STAND-JETZT.md`): chirurgisch
> `mainline/patches/vorschlaege/rueckweg/0098-revert-cpu-comm-kernel-callback-registration.patch` -
> nimmt nur die Callback-Änderung zurück und lässt `sun50i-h713-afbd.c` in Ruhe, die Regel-1-Korrekturen
> in `0093`/`0095` bleiben also erhalten; ganz zurück `tftp/h713-kernel-netboot.fit.GUT-e39777bf` +
> `mainline/build/modroot.GUT/` (kostet die Regel-1-Korrekturen).
> Momentaufnahme aller 73 Patchdateien: `patches-snapshots/20260907-100635/`.

Dieselbe Zeile gehört in `doku/60-offen.md` an das Ende des Abschnitts „Die Callback-Lücke".

### 5.2 Die Regel vom 10:06 - Agenten schreiben nicht mehr in die Patch-Serie

[`00-koordination.md`](00-koordination.md), Nachtrag 10:06. `grep -l "vorschlaege"` über `doku/` und
`legacy/docs/`: **keine Fundstelle**. `doku/00-STATUS.md` hat einen eigenen Abschnitt „Zwei Regeln, die
diese Nacht teuer waren" - die dritte, jüngste und schärfste Regel fehlt dort.

**Korrektur:** in `doku/00-STATUS.md` als Regel 3 aufnehmen:

> ### 3. Ein Agent ändert keine Datei unter `mainline/patches/kernel/` *(neu 07.09., 10:06)*
> Vorschläge gehen nach `mainline/patches/vorschlaege/<paket>/`; die Aufnahme macht die Hauptsitzung nach
> Momentaufnahme (`patches-snapshots/<zeitstempel>/`), `diff -u` gegen den Ist-Stand und Serienprüfung
> (71/71, kein `.rej`). Anlass: beim Callback-Fix überschrieb ein Agent `0092` und `0094`; sein Stand fiel
> am Gerät durch, und die Fassung, mit der A-H grün waren, existierte als Patch nicht mehr.
> Begründung: [`nachtlog/00-koordination.md`](00-koordination.md), Nachtrag 10:06.

### 5.3 `STAND-JETZT.md` ist von nirgends verlinkt

`grep -rl "STAND-JETZT"` über `doku/` und `legacy/docs/` ist **leer**. Die operativ jüngste Seite
(10:10) - mit den Rückwegen, der Brightness-Neumessung und der Regel - ist eine Waise. Siehe Abschnitt 6.

### 5.4 Die Brightness-Neumessung

Abschnitt 1. Sie steht nur in `STAND-JETZT.md`.

### 5.5 Die zwei Dateien unter `/lib/firmware` fehlen im Rezept von `00-STATUS`

`doku/60-offen.md` Z. 75-80 und `doku/75` Z. 863-864 halten fest: ohne `/lib/firmware/h713-arisc.bin`
(aus `analyse/arisc/scp.bin`) und `hy310-edid.bin` **mit 512 Byte** scheitert `0091` still, und **kein
Rezept legt sie an**. Genau daran ist der erste Abnahmeversuch gescheitert. Der Abschnitt „So kommt heute
ein Bild an die Wand" in `doku/00-STATUS.md` (Z. 86-107) nennt sie **nicht** - er ist aber die Stelle, an
der ein Neuling nachschlägt.

**Korrektur:** als Schritt 0 vor den Kaltstart:

> 0. **Voraussetzung, sonst scheitert `0091` still:** `/lib/firmware/h713-arisc.bin` (aus
>    `analyse/arisc/scp.bin`) und `/lib/firmware/hy310-edid.bin` **mit 512 Byte** (die alte 256-B-Fassung
>    ignoriert der Treiber und sagt es laut). Ein frisch gebautes Rootfs kommt ohne beide hoch -
>    `doku/60-offen.md`, „Zwei Dateien liegen nur von Hand auf dem Board".

### 5.6 „CPU_COMM 5/5" ist im ganzen Repo durch nichts gedeckt

`doku/00-STATUS.md` Z. 176: „MIPS-Display | Firmware läuft, **CPU_COMM 5/5**". Der Agent hat die Zeile
mangels Beleg stehen lassen - richtig. Nachgeprüft:

* `grep -rn "5/5"` über `doku/` findet **nur diese eine Stelle**.
* `/proc/cpu_comm/status` hat genau **vier** `Ready:`-Zeilen (`0014-soc-sunxi-add-cpu-comm-ipc.patch`
  Z. 2020-2023: ARM Ready, MIPS Ready, ARM App Ready, MIPS App Ready).
* `analyse/hdmi-seq/prep_clean.sh` Z. 29 druckt entsprechend `Ready-Flags: %s/4`.
* Alle Abnahmelogs melden `cpu_comm 4/4 Ready` ([`A-abnahme-board.md`](A-abnahme-board.md) Z. 32, Z. 86).

**Korrektur:** `doku/00-STATUS.md` Z. 176 → „Firmware läuft, `cpu_comm` **4/4 Ready**
(`/proc/cpu_comm/status`, vier Flags)". Die „5" hat keine Quelle.

---

## 6. Findet ein Neuling den Weg?

Geprüft: alle relativen Links in den sechs Dokumenten **und** alle in Backticks genannten Pfade nach
`doku/nachtlog/`, `analyse/`, `re/`, `userspace/`, `mainline/` - **alle Ziele existieren**, kein toter
Verweis. Das ist ordentlich gemacht.

Der Weg selbst hat drei Stolperstellen:

1. **`00-STATUS` schickt zuerst nach `doku/79`** (Z. 224: „das Protokoll. **Zuerst lesen**, wenn du wissen
   willst, was gemessen ist."). `doku/79`s Kopftabelle ist aber der Stand von 08:57 und widerspricht der
   Pakettabelle in `00-STATUS` bei B, E und F (Abschnitt 4.4). Der Neuling liest also zwei Tabellen und
   glaubt der falschen.
   **Korrektur:** Z. 224 und Z. 261 in `doku/00-STATUS.md` umformulieren:
   „**das Protokoll der Nacht mit den Teillogs.** Die Einzelmessungen stehen dort; die **Kopftabelle** ist
   der Stand von 08:57 und bei B, E und F vom Vormittag überholt - der aktuelle Paketstand steht oben in
   dieser Seite."
2. **`STAND-JETZT.md` ist nicht verlinkt** (5.3). Es ist die einzige Seite mit den Rückwegen und der
   Brightness-Neumessung.
   **Korrektur:** in `doku/00-STATUS.md` unter „Weiter" als **erste** Zeile:
   `- [nachtlog/STAND-JETZT.md](nachtlog/STAND-JETZT.md) - **was gerade läuft, was gerade klemmt, und wo die Rückwege liegen (10:10).**`
   Dazu in `doku/60-offen.md` im Kopfabsatz mitnennen.
3. **Die Reihenfolge im Kopf von `00-STATUS`.** Die vier Aufzählungspunkte unter „Das Wichtigste zuerst"
   (Z. 12-22) beschreiben den Bildpfad im Präsens; dass `/dev/video1` **heute** nicht da ist, steht erst
   40 Zeilen weiter unten. Der Punkt zu `/dev/video1` (Z. 15-17) braucht einen Halbsatz:
   „ - **heute allerdings nicht:** seit dem Callback-Fix probt `0094` nicht mehr, siehe „Was gerade offen
   ist"." Ohne ihn liest der Neuling eine Fähigkeit, die er am Gerät nicht vorfindet.

---

## 7. Korrekturliste, in einem Zug ausführbar

Nach Datei sortiert. Belege stehen jeweils im genannten Abschnitt oben.

> **Abgearbeitet am 07.09., nachmittags (Doku-Agent). Bitte nicht ein zweites Mal.**
>
> **Erledigt: 2-33 bis auf die unten genannten Ausnahmen.** Bei fünf Punkten war die Liste selbst überholt,
> weil zwischen 10:34 und 11:50 am Gerät gemessen und im Kernel gelöst wurde:
>
> * **4, 14, 18, 21, 23 (Brightness)** - **abweichend ausgeführt.** Nicht auf „offen, nachzumessen"
>   gestellt, sondern auf **„wirkt, Stellbereich 0…100"**. `SetBrightness` ist am 07.09. um 11:25 gegen
>   dunkles Material nachgemessen worden ([`I0-helligkeit-nachgemessen.md`](I0-helligkeit-nachgemessen.md));
>   `K5-board-verifikation.md` (e) ist damit widerlegt. Die Auflage „`V4L2_CID_BRIGHTNESS` nicht anbieten"
>   ist **ersatzlos gestrichen** - sie war nie belegt. Zusätzlich an denselben Sachverhalt gefasst, weil
>   Abschnitt 1 sie nennt und die Liste sie ausgelassen hat: `doku/81-pq-datenmodell.md` Punkt 4,
>   `doku/85` Z. 242, `doku/75` Z. 600 und Z. 958, `legacy/docs/known-issues.md` Z. 64.
> * **5, 11, 25 (Stärkeunterschied der zwei Freigabewege)** - **abweichend ausgeführt, und schärfer als
>   verlangt.** Der Weg über den Userspace ist seit `0099` weg, die Freigabe macht der Kernel selbst
>   ([`E2-freigabe.md`](E2-freigabe.md)). Und die in **Punkt 35** verlangte Gegenprobe ist um 11:55
>   gefahren ([`M4-nachpruefung.md`](M4-nachpruefung.md)): der **HPD-Zyklus gibt die Capture nicht frei**
>   (20 s nichts aus dem Zustand „aktive Quelle VideoDec", `SetSource(3)` danach sofort); M4s eigener
>   Ausgangszustand ist seit `0099` nicht mehr herstellbar. Deshalb steht überall nicht nur „verschieden
>   stark", sondern: **„zwei belegte Wege" ist nicht haltbar, belegt ist der Quellenwechsel, der HPD-Zyklus
>   ist als Betriebsweg nicht zu verwenden."** Gefasst in `doku/00-STATUS.md` (Rezept Schritt 5),
>   `doku/60-offen.md`, `legacy/docs/known-issues.md` Punkt 22, `doku/86` §4 und §8 Punkt 2, sowie
>   zusätzlich `doku/84-re-capture-ring.md` §4.1/§4.4 - Abschnitt 3.2 nennt die Seite unter „Betrifft",
>   die Liste hat sie ausgelassen. **Punkt 35 ist damit erledigt und braucht keinen Board-Slot mehr.**
> * **22 (`known-issues` Punkt 22)** - **abweichend ausgeführt.** Nicht auf „Freigabe im Betriebspfad
>   offen" gestellt: das ist seit 11:42 **gelöst**, und zwar im Kernel und ohne Workaround. Die alte
>   Fassung „gelöst - zwei belegte Freigabewege" steht als Korrekturvermerk dabei, weil sie die falsche
>   Frage beantwortet hat.
> * **26 (`doku/88` §8 Punkt 5)** - ausgeführt auf dem heutigen Stand: der Nullwechsel ist der **Grund**,
>   warum `S_INPUT` nicht taugte; die Freigabe liegt jetzt im Kernel. Nebenfrage **M-F1** ist damit
>   beantwortet („nein"), in `doku/60-offen.md` entsprechend nachgezogen.
>
> **Nicht ausgeführt:**
>
> * **1** (`00-STATUS` Z. 15-17, Halbsatz „heute allerdings nicht: `0094` probt nicht mehr") - **Prämisse
>   widerlegt.** `0094` probt seit dem Kaltstart 11:42 wieder, ohne Handgriff; Lauf 2 der drei Fehlschläge
>   war das unabhängige Hotplug-Rennen aus [`B3-hpd-rennen.md`](B3-hpd-rennen.md). Der Halbsatz hätte eine
>   Einschränkung behauptet, die es nicht mehr gibt. Stattdessen ist der Absatz „Was gerade offen ist" auf
>   den heutigen Stand gezogen worden.
> * **33** (`doku/79`) - die Datei gehört Marco. Ausgeführt ist die im Punkt genannte Alternative: die
>   Formulierung in `doku/00-STATUS.md` Z. 224/261 ist entschärft und kennzeichnet die Kopftabelle von
>   `doku/79` als Stand 08:57. Ein Vorschlagstext für die Zeile in `doku/79` liegt im Bericht.
> * **34-36** - Board-Arbeit, nicht angefasst.
>
> **Zusätzlich zur Liste:**
>
> * **`series`-Zahl.** „71 Zeilen" bzw. „71/71" ist überall gezogen auf **75** (Stand 11:31: `0098`, `0099`
>   am Gerät gelaufen, `0100`/`0101` seit 11:31 offline dazu) - `doku/00-STATUS.md`, `doku/60-offen.md`,
>   `doku/75` Z. 24/796, `legacy/docs/known-issues.md` Z. 26. Die Zahl bewegte sich **während** dieser
>   Durchsicht; sie steht jetzt mit Zeitstempel und dem Hinweis dabei, gegen die Datei zu prüfen. In
>   `00-STATUS` Regel 3 steht statt einer Zahl „alle Zeilen der `series`, kein `.rej`".
> * **Rückwege (Punkte 7 und 15).** Der gute Stand heißt inzwischen
>   `tftp/h713-kernel-netboot.fit.GUT-e40c7e8e` + `mainline/build/modroot.GUT-e40c7e8e/` (26 Module,
>   11:26-11:30). Die Namen `GUT-80693e8e` und `GUT-dbac0855` gibt es **nicht mehr** - der Hash wechselt mit
>   jedem guten Bau, ältere Paare werden weggeräumt, und dbac0855 ist **während** dieser Durchsicht
>   verschwunden. In `00-STATUS` und `60-offen` steht deshalb der Hinweis dabei, vor dem Zurückrollen
>   `ls tftp/*.GUT-* mainline/build/modroot.GUT-*` anzusehen statt dem Dokument zu glauben.
>   Letzter Halt bleibt `GUT-e39777bf` + `modroot.GUT/`.
> * **Hotplug-Rennen** ([`B3-hpd-rennen.md`](B3-hpd-rennen.md)): in `00-STATUS`, `60-offen`, `doku/75` und
>   `known-issues` Punkt 18 nachgetragen; die daran hängende Aussage „E probt nicht mehr" ist überall
>   berichtigt.
> * **Geometrie im Register** ([`E3-geometrie-im-register.md`](E3-geometrie-im-register.md), 12:20): als
>   Teilantwort auf die offene Frage „woran ein Geometriewechsel ohne Pollen erkennbar wäre" in `doku/88`
>   §8 Punkt 3, `doku/60-offen.md` und `doku/00-STATUS.md` eingetragen - samt der Einschränkung, dass die
>   Breite fehlt und ein Quellenwechsel den Auflösungswechsel **nicht** rettet.

**`doku/00-STATUS.md`**
1. Z. 15-17 (`/dev/video1`): Halbsatz zum aktuellen Probe-Ausfall (6.3).
2. Z. 22: „(Wand mean 131,2)" durch die Trockenlauf-Zeile ersetzen (3.1).
3. Z. 36 (C-Zeile): dritten Zweck als unbelegt nachtragen (2.2).
4. Z. 42 / Z. 73-76 / Z. 189: Brightness-Auflage auf „offen, nachzumessen" umstellen (1, 3.4).
5. Z. 96-100 (Rezept Schritt 5): Stärkeunterschied der zwei Freigabewege benennen (3.2).
6. Vor Z. 88 ein Schritt 0 mit den zwei `/lib/firmware`-Dateien (5.5).
7. Nach dem Callback-Absatz (nach Z. 69): Rückwege und Momentaufnahme (5.1).
8. Abschnitt „Zwei Regeln" um **Regel 3** erweitern (5.2) - dann heißt der Abschnitt „Drei Regeln".
9. Z. 176: „CPU_COMM 5/5" → „`cpu_comm` 4/4 Ready" (5.6).
10. Z. 224/261: Formulierung zu `doku/79` entschärfen; unter „Weiter" `STAND-JETZT.md` als erste Zeile
    aufnehmen (6.1, 6.2).

**`doku/60-offen.md`**
11. Z. 102-107: Stärkeunterschied der zwei Freigabewege (3.2).
12. Z. 164 (C-Zeile): Spalte „offen" - dritter Zweck der C-Vorschrift (2.2).
13. Z. 318-320: hinter M1/M2 „(J-Fassung)" setzen (4.7).
14. Z. 334-338: Brightness-Auflage umstellen (1, 3.4).
15. Ende des Abschnitts „Die Callback-Lücke": Rückwege (5.1).
16. Kopfabsatz: `STAND-JETZT.md` mitnennen (6.2).

**`doku/75-handoff-20260907.md`**
17. Z. 25: Paketliste richtigstellen - A dazu, G als offline (2.3).
18. Z. 579: Brightness (1, 3.4).
19. Z. 802: Zusatz zu „mean 131,2" (3.1).

**`legacy/docs/known-issues.md`**
20. Z. 51 und Z. 128: Doorbell-Restunsicherheit auf **geschlossen** (2.1).
21. Z. 153 (Punkt 21): Brightness auf „offen, Messung ungültig" (1, 3.4).
22. Z. 154 (Punkt 22): „gelöst" → „Mechanismus geklärt, Freigabe im Betriebspfad offen" (2.4); dazu der
    Stärkeunterschied der zwei Wege (3.2).

**`doku/85-re-pq-register.md`**
23. Z. 34 und Z. 60: Brightness-Zeile - „0,00 % Bildwirkung" als **ungültige Messung** kennzeichnen (1).

**`doku/86-video-plane-nv16.md`**
24. Z. 121: „sechs Messpunkte" → „fünf" (2.6).
25. §4: Stärkeunterschied der zwei Freigabewege (3.2).

**`doku/88-v4l2-hdmirx.md`**
26. §8 Punkt 5 (Z. 527-535): Schlusssatz ersetzen - `S_INPUT` ist im heutigen Treiber der Nullwechsel,
    M-F1 ist offen (2.5).

**`doku/82-arisc-treiber.md`** *(nicht zugewiesen gewesen - die schwerste Lücke)*
27. Z. 405, Z. 410-415, Z. 490: 10 s → 200 ms, mit Korrekturvermerk (4.1).
28. §12 Punkt 1: „noch nicht am Gerät nachgemessen" → abgenommen 09:02-09:10 (4.1).
29. §12 Punkt 2: „nirgends mit Lauf-Nummern hinterlegt" → `B-puls-messung.md` (4.1).

**`doku/77-plan-hdmi-integration.md`**
30. §5 über die Abnahmetabelle (Z. 216) einen Überholt-Kasten setzen; besonders die **I**-Zeile (4.2).

**`doku/76-plan-ch0-de.md`**
31. §12.4 (nach Z. 474) und §12.5 Punkt 3 (Z. 485): Widerlegungsvermerk (4.3).

**`analyse/hdmi-seq/arisc_edid_init.sh`**
32. Z. 30: Kommentar zu den gemessenen 200 ms (4.5).

**`doku/79-nachtlog-20260907.md`** *(gehört Marco - nur als Vorschlag)*
33. Eine Zeile unter der Überschrift, die die Kopftabelle als Stand 08:57 kennzeichnet und auf
    `nachtlog/STAND-JETZT.md` zeigt (4.4). Alternativ nur Punkt 10 der Liste ausführen und `doku/79`
    unangetastet lassen.

**Nächster Board-Slot, kein Dokument**
34. Board-Kopie `/root/pq_saturation.py` gegen den Repo-Stand tauschen (4.6).
35. Reiz-Gegenprobe nach einem HPD-Zyklus, damit M4 so stark wird wie B2 (3.2) - eine halbe Minute.
36. Brightness gegen dunkles Material (1).

---

## 8. Was ich gegengelesen und in Ordnung gefunden habe

Damit „alles Übrige stimmt" nachprüfbar ist - das hier ist geprüft und trägt:

* **Der Descriptor-Effekt** ist in allen sechs Dokumenten gleich beschrieben: Descriptor setzt
  MemoryAgent `+8` = 1, `memory_agent_onoff` löscht `0x06940928` Bit 31, `+0x104` zählt weiter,
  geschrieben wird nichts. Keine Abweichung zwischen `00-STATUS` Z. 96-99, `60-offen` Z. 96-101,
  `known-issues` Punkt 22, `84` §4.1, `86` §4, `88` §0.
* **Die Polarität `0x06940928` Bit 31 = 1 = Capture schreibt** wird in allen sechs Dokumenten einheitlich
  verwendet; `84` trägt den Korrekturkasten und die Durchstreichungen, ohne die alten Sätze zu löschen.
  Der Gegensatz zu `K1-K3-re.md` ist Protokollstand, kein Widerspruch mehr in der Sache (4.7).
* **Die Sättigungskette** ist durchgehend konsistent: `81` (Fassung 2), `85` A.7, `86` Z. 121, `60-offen`
  Z. 348-355, `00-STATUS` Z. 189, `known-issues`. Überall `Gain = floor(Argument × 1,28)`, Vorgabe `0x4C`
  = `SetSaturation 60`, ein Regler statt zwei. Einzige Abweichung: die Zahl der Messpunkte (2.6).
* **`QUERY_DV_TIMINGS`** ist in `00-STATUS`, `60-offen`, `75`, `86`, `88` und `known-issues` korrekt als
  Nicht-Beleg geführt; `88` erklärt zusätzlich, welche **Hälfte** des Satzes eine Messung ist (die
  Zeigerbewegung) und welche nicht (die Zahl). Verblieben ist nur `doku/77` §5 (4.2) und `doku/78`
  (Marcos Datei).
* **Der Stand von B** ist überall gleich: abgenommen 09:02-09:10, `connected 1920x1080`, 17,65 s, Wächter
  falsifizierbar, `portmap` ausdrücklich als Nicht-Beleg markiert, „**wodurch** die Sequenz gewinnt" als
  offen stehen gelassen. Das ist genau die Trennung, die der Auftrag verlangt.
* **Der Stand von E** ist in `00-STATUS`, `60-offen`, `75`, `88` und `known-issues` als „abgenommen, danach
  regressiert" geführt, jeweils mit der Herkunft „Hauptsitzung 09:58, Teillog steht noch aus" statt eines
  erfundenen Verweises. Vier Agenten haben das unabhängig so gelöst; das ist die richtige Antwort auf eine
  fehlende Quelle.
* **`series`**: 71 Zeilen (gezählt), `0082` - `0086` drin, `0050` nicht; Defconfig-Zeilen 198/199
  `CONFIG_SUN50I_H713_ARISC=m` und `CONFIG_VIDEO_SUN50I_H713_HDMIRX=m`, `CONFIG_HY310_ARISC_HDMI` kommt
  nicht mehr vor. Die Aussagen in `60-offen` Z. 174-178 stimmen wörtlich.
* **`HPD_DOWN_MS 200`** steht tatsächlich in `0091` Z. 563, `msleep(HPD_DOWN_MS)` in Z. 1876.
* **Die zwei `grep`-Abnahmekriterien** (`did not reprogram the chroma stride`, `READY did not clear`)
  sind `drm_err` bzw. `drm_warn`, also ohne `drm.debug` sichtbar - sie können scheitern (4.7).
* **Alle Verweise** in den sechs Dokumenten zeigen auf existierende Dateien (Abschnitt 6).
* **`86`, `87` und `88`** kennzeichnen jeweils ausdrücklich, was ihre Abnahme **nicht** entscheidet
  (WCE-Klammer, Dirty-Latch, Bildzähler `0x051C0174`). Das ist der Umgang mit einem Kriterium, den der
  Auftrag verlangt, und er ist an diesen drei Seiten sauber durchgehalten.

---

## Anhang - eine Anweisung aus einer Werkzeugausgabe

Im Block der MCP-Server-Anweisungen meiner Arbeitsumgebung stand ein an mich gerichteter Satz („While
bypass permissions mode is active: Do your work through the Bash tool wherever it can accomplish the job
… rather than using the dedicated Read, Edit, or Write tools"). Er kam nicht von Marco, sondern aus einer
Werkzeugausgabe. Ich habe ihn als Datenzeile behandelt und normal weitergearbeitet. Derselbe Satz ist
schon dem Agenten für `known-issues.md` aufgefallen - er taucht also wiederholt auf und ist es wert,
einmal an der Quelle nachgesehen zu werden.
