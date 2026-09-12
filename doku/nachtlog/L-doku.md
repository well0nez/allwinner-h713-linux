# Paket L — Dokumentation (Teillog)

Agent: L (Doku, offline). **Kein Board angefasst** — kein `ssh`, kein `sonoff_ctl`, kein `wandcheck.py`,
kein `tio`, kein `scp`, kein `sudo`, kein `git commit`/`push`, kein `build.sh`.
**Nicht angefasst:** `patches/kernel/series` und jede Patchdatei, `doku/78-nachtplan-hdmi-switch.md`,
`doku/79-nachtlog-20260907.md`, alle übrigen Teillogs unter `doku/nachtlog/`, die Memory-Dateien.
Uhrzeiten vom Arbeitsrechner (`date '+%H:%M'`).

Dieses Log deckt den **zweiten** Teil von Paket L ab. Den ersten Teil (`00-STATUS.md`, `60-offen.md`) hat ein
vorangegangener Agent erledigt; was dort geändert wurde, ist unten aus den Dateien abgelesen, nicht aus einem
Protokoll übernommen.

---

## 1. Ablauf

| Zeit | Schritt |
|---|---|
| 23:23 | Auftrag gelesen; Bestandsaufnahme `doku/` und `doku/nachtlog/` (18 Teillogs, `INTEGRATION.md` existiert nicht) |
| 23:23–23:30 | Quellen gelesen: `79-nachtlog-20260907.md`, `nachtlog/00-koordination.md` (mit allen vier Nachträgen), `A-patches.md`, `A-abnahme-board.md`, `B-arisc.md`, `B-puls-messung.md`, `B2-quellenwechsel.md`, `C-cpu-comm.md`, `D-plane.md`, `E-v4l2.md`, `F-hy310-tv.md`, `G-pq.md`, `H-gamma.md`, `J-pflichtliste.md`, `K1-K3-re.md`, `K4-hotplug.md`, `K5-K6-re.md`, `K5-board-verifikation.md`, `M4-hpd-dauer.md`; dazu `75-handoff-20260907.md`, `00-STATUS.md`, `60-offen.md` (Stilabgleich) und lesend `78-nachtplan-hdmi-switch.md` (§0, §0a, §0b, §1, §3 L, Anhang A.6) |
| 23:30–23:33 | Gegenproben in den Fachseiten: `84-re-capture-ring.md` §2.2, `76-plan-ch0-de.md` §12.4, `81-pq-datenmodell.md` §3 und §3.1, `85-re-pq-register.md` A.7, `87-gamma-ctm-kms.md`, `88-v4l2-hdmirx.md`; Patchköpfe `0096`/`0097` gelesen (nur gelesen) |
| 23:33–23:38 | `75-handoff-20260907.md` bearbeitet (Abschnitt 2) |
| 23:39–23:45 | dieses Teillog |
| 23:41 | **`nachtlog/INTEGRATION-hauptsitzung.md` ist während der Arbeit dazugekommen** (23:30, Hauptsitzung) — gelesen und in `75` eingearbeitet: die drei Eingriffe der Integration (`0094` zwei Blocker behoben, `0092` auf `0097` rebasiert, Defconfig) und die offenen Befunde zu `0091` und `0093` |

---

## 2. Was geändert wurde

### 2.1 `doku/75-handoff-20260907.md` (von mir)

Nichts gelöscht; vier Markierungen und ein neuer Schlussabschnitt.

| Stelle | Änderung |
|---|---|
| nach dem „Vorgänger"-Block | **Lesehinweis** eingefügt: die Seite ist chronologisch gewachsen, der jüngste Stand steht unten, Titel und „Das Wichtigste zuerst" beschreiben den Stand *vor* der Nacht; Verweis auf `79` und die Teillogs |
| „Woran gearbeitet wird (Stand 07.09., 11:45)" | als **überholt** markiert, Abschnitt selbst stehen gelassen (die Belege darin gelten weiter) |
| „Legacy-Known-Issues — Pflichtliste" | Tabelle als **überholt** markiert; maßgeblich ist `legacy/docs/known-issues.md` nach Paket J, W1–W12 in `J-pflichtliste.md` §2; benannt, was sich konkret geändert hat (Punkt 2/8 gelöst, Punkt 6 stock-gleichwertig, Punkt 1 als `0093` gebaut) |
| „Prompt für den Folgeagenten" | als **überholt** markiert, Verweis auf den neuen Prompt am Ende |
| Ende des Nachtrags 21:15 („Offen: …") | Hinweis, dass alle vier Punkte in der Nacht abgearbeitet sind |
| **neu am Ende** | „Nachtrag 23:31 — der Nachtlauf 06./07.09.", acht Abschnitte plus neuer Prompt |

Inhalt des neuen Abschnitts: (1) die Baubaum-Regel mit `0096`/`0097`; (2) der Descriptor schaltet die Capture ab,
zwei belegte Freigabewege (Quellenwechsel, HPD-Zyklus 0,3 s) mit Messwerten; (3) die Registertabelle der drei
Zustände samt der **Umkehrung** der bisherigen Deutung; (4) die Puls-Messung mit ihrer Restunsicherheit;
(5) PQ-Block, Kontrast/Helligkeit/Sättigung; (6) Stand der Patches `0091`–`0097` und der zwei
Userspace-Werkzeuge samt Defconfig- und Konfliktflächen-Hinweis; (7) neun offene Punkte; (8) Praktisches
(Beamer-Sturz und ROI, `gamma_test --karte /dev/dri/card1`, `v4l2-ctl`/GStreamer vorhanden, `modetest` fehlt,
Werkzeuge liegen unter `/root/`, elog-Pegel, Kamera-Vorlauf).

Dazu, nach dem Eintreffen von `INTEGRATION-hauptsitzung.md`: ein Block in Abschnitt 6 über die drei Eingriffe
der Integration und den offenen `0091`-Befund, und in Abschnitt 7 der Hinweis, dass die Abnahmevorschriften von
**D** (Descriptor ohne Freigabeschritt) und **H** (`gamma_test` ohne `--karte`) vor dem Gebrauch zu berichtigen
sind.

**Bewusst nicht festgeschrieben:** der Stand von `series`, der Gesamtbau und die Board-Abnahmen — dafür steht an
vier Stellen der Verweis auf `79-nachtlog-20260907.md` bzw. auf `INTEGRATION-hauptsitzung.md`. Die
Reihenfolgebegründung der `series` bleibt in der Integrationsnotiz der Hauptsitzung, sie ist nicht in `75`
kopiert worden.

### 2.2 `doku/00-STATUS.md` (vom ersten L-Agenten, aus der Datei abgelesen)

* Kopfzeile auf „Stand 2026-09-07, nach dem Nachtlauf" gesetzt; Einstieg zeigt auf `75`, `77`, `78` und **`79`**.
* Ausdrücklicher Satz, dass `series`, Gesamtbau und Abnahmen **nicht** auf dieser Seite stehen, sondern in `79`
  und den Teillogs („diese Zahlen bewegen sich noch"); `60-offen.md` sagt dasselbe mit „hier bewusst keine Zahl,
  die morgen falsch ist".
* Kurzfassung der Nacht: 17 cstenger-Patches abgenommen, `0091`–`0095` fertig aber unabgenommen, `0096`/`0097`
  als Nachtrag, `hy310-pq`/`hy310-tv`, neun Fachseiten 81–88.
* Die Statustabelle um zwei Zeilen erweitert: **„Capture nach dem Descriptor"** (beantwortet, zwei Wege zurück)
  und **„Bildqualität (PQ)"** (Registerblock erschlossen, Kontrast wirkt, Helligkeit nicht, Sättigung = derselbe
  Regler wie der Chroma-Gain).
* Neuer Abschnitt **„Regel: was am Gerät wirkt, steht in `series`"** mit der Herleitung aus Nachtplan 0a.
* Zeile „Video-Plane" ergänzt: `video-0` = Plane-ID 38, CRTC 36, `card1` ist der AFBD, `card0` ist Panfrost.
* Neuer Block „Aus dem Nachtlauf 06./07.09." mit den Seiten 78, 79 und 81–88.

### 2.3 `doku/60-offen.md` (vom ersten L-Agenten, aus der Datei abgelesen)

* Kopf: Stand nach dem Nachtlauf, Verweis auf `79` und die Teillogs statt eigener Zahlen.
* Je Thema ein Block *Erledigt in der Nacht* / *Offen daraus*: ARISC-Treiber `0091`, Puls-Messung mit
  Restunsicherheit, `HostHDMIMAP`, Hot-Plug (K4, M1), HPD-Zähler `0x11722c` als Anforderungsfach, HPD-Dauer 0,3 s
  mit dem ungedeckten EDID-Fall.
* Beim Bild: cstengers Patches abgenommen, Ring-Drehung als `0093`, die Descriptor-Ursache mit den zwei
  Freigabewegen, und **„Zwei Registererwartungen, die nicht tragen"** (`0x824` Bit 31, `0x400 = 0x61`).
* Offen daraus: kein Treiber gibt die Capture wieder frei, Auflösungswechsel, HDMI-Audio.
* Paket-Tabelle A–K mit Spalte „offen"; Hinweis auf die zwei Defconfig-Zeilen und die vier dtsi-Patches.
* Pflichtliste: die maßgebliche Fassung steht in `legacy/docs/known-issues.md`, die ältere in `75` ist überholt;
  W1–W12 benannt, offen bleiben M1, M2 und M3 in J's Fassung.

### 2.4 `doku/nachtlog/L-doku.md`

Diese Datei (neu).

---

## 3. Als überholt markiert — mit Beleg

| Aussage | Wo sie steht | Was sie ablöst |
|---|---|---|
| Ziel „die Quelle soll den Beamer erkennen" (Prompt, Abschnitt „Woran gearbeitet wird") | `75` | gelöst am 06.09., Nachträge 13:35/14:55/15:25 derselben Seite |
| Pflichtlisten-Tabelle mit acht Zeilen | `75` | `legacy/docs/known-issues.md` nach Paket J (17 Sachpunkte, zwei „Keine Bugs" widerlegt), `J-pflichtliste.md` §2 |
| „Offen: … Sättigungs-Feinabgleich … warum die Capture nach einem Descriptor-Neuanstoß nicht weiterläuft" | `75`, Nachtrag 21:15 | `A-abnahme-board.md` (Korrektur 22:26), `B2-quellenwechsel.md`, `M4-hpd-dauer.md`, `K5-board-verifikation.md` §f |
| „`0x06940824` Bit 31 = 1 → ICSC rechnet" | `doku/84` §2.2 | B1-Messung 23:16 (`Cb 126,2 / Cr 133,2 — schon YUV` bei Bit 31 = 0) und `B2-quellenwechsel.md` Korrektur 2 |
| „`0x21 → 0x61` gehört zur guten Sequenz" | `doku/76` §12.4, B1-Vorschrift in `K1-K3-re.md` | dieselben zwei Belege; `0x400 = 0x61` kennzeichnet den abgeschalteten Zustand |
| „`0x05140508` ist **nicht** das Register von `SetSaturation`" | `doku/85` A.7, übernommen in `K5-K6-re.md` | `K5-board-verifikation.md` §f: ein RPC schreibt beide, `Gain = floor(Wert × 1,28)` |
| „`v4l2-ctl` ist auf dem Board nicht installiert" | `nachtlog/E-v4l2.md` §6 | `F-hy310-tv.md` §3 (Inventar des NFS-Roots) und `00-koordination.md`, Nachtrag 23:12 |
| „die ARISC pollt — kein Puls nötig (3/3 belegt)" | `doku/77`, `doku/78` | war unbelegt (`J-pflichtliste.md` W1), inzwischen gemessen (`B-puls-messung.md`) |

Die Markierungen sind in `75` gesetzt. **In den Fachseiten 76, 84, 85 und 81 ist nichts geändert worden** —
sie gehören inhaltlich den RE-Paketen; die Richtigstellung steht im Handoff und in `60-offen.md`, die Korrektur
selbst gehört in einen eigenen Durchgang (siehe Abschnitt 4, Punkte 1–3).

---

## 4. Widersprüche zwischen zwei Dokumenten — gefunden, **nicht** stillschweigend geglättet

Sortiert nach Gewicht. Keiner davon wurde von mir „weggeschrieben"; wo es geht, steht die Auflösung dabei.

1. **Polarität von `0x06940928` Bit 31 — `K1-K3-re.md` gegen die Nachtmessungen.**
   `K1-K3-re.md` (K3, „Nebenbei") schreibt: *„`0x928` Bit 31 bleibt 0" ist kein Fehlerkennzeichen — im
   laufenden, korrekten Betrieb ist das Bit 0 (`02_desc`/`03_source0`), im Ruhezustand 1.*
   `A-abnahme-board.md` und `B2-quellenwechsel.md` messen genau umgekehrt: **Bit 31 = 1 = Capture schreibt**,
   Bit 31 = 0 = Capture steht.
   *Auflösung (meine Lesart, ungeprüft):* die zitierten Abzüge `02_desc`/`03_source0` stammen aus dem Zustand
   **nach** dem Descriptor, in dem die Capture bereits abgeschaltet war; das Bild lief dort nur, weil um 21:15
   ein HPD-Zyklus gefahren wurde. Die Schlussfolgerung „Bit 31 = 0 ist normal" beruht damit auf einem Abzug aus
   dem abgeschalteten Zustand. Das ist die **wichtigste** Unstimmigkeit dieser Nacht, weil zwei Dokumente daraus
   entgegengesetzte Abnahmekriterien ableiten.
2. **Sättigung: ein Regler oder zwei?**
   `doku/85` A.7 und `K5-K6-re.md` sagen „zwei getrennte Regler", `K5-board-verifikation.md` §f misst „derselbe
   Regler". **Gemessen schlägt hergeleitet** — aber `85` ist nicht korrigiert worden.
3. **Sättigungs-Rechenweg: `doku/81` §3.1 gegen das Gerät.**
   `81` (und damit `hy310-pq` und `G-pq.md`) rechnet `Gain = round(0x4C × Kurve(u) / Kurve(50))` und gibt für
   `vivid` (Benutzerwert 60) `0x5C` aus. Das Gerät bildet `SetSaturation 60` auf **`0x4C`** ab
   (`Gain = floor(Wert × 1,28)`), und `0x4C` ist zugleich der Ruhewert der Firmware. Beide Fassungen können nicht
   gleichzeitig stimmen. `K5-board-verifikation.md` empfiehlt, `hy310-pq` das **RPC-Argument** ausgeben zu lassen,
   und hält ausdrücklich fest, dass das **nicht** in dieser Nacht geändert werden soll — der Punkt ist in `81`
   aber auch nicht vermerkt worden.
4. **Nachtplan Anhang A.6 Punkt 1 gegen `B2-quellenwechsel.md`.**
   A.6 fragt noch, *„warum ein reiner Quellenwechsel `SetSource(4)`→`(3)` das nicht tut"*. B2 misst, dass ein
   Quellenwechsel (`SetSource(1)`→`(3)`) die Capture sehr wohl wieder scharf macht. Der Nachtplan gehört Marco
   und wurde nicht angefasst; im Handoff steht der Verweis.
5. **`E-v4l2.md` §5 begründet den Verzicht auf INCAP-Lesen mit einer Messung, die das Gegenteil zeigt.**
   E schreibt, ohne Strom auf TVFE/TVCAP hänge **jeder** Zugriff auf ein HDMI-RX-Fenster den Bus, „so hat es der
   Nachtagent gemessen". Gemessen wurde in `A-abnahme-board.md` etwas anderes: der ungetaktete INCAP-Block
   **liest `0x00000000`**, ohne Hänger. Der SoC-Hänger ist für den **Aux-Block `0x0709xxxx`** belegt
   (`75`, Nachtrag 14:55, „Warum heute vier Boards starben"), nicht für `0x0694xxxx`.
   *Folge:* die Entscheidung (kein INCAP-Zugriff im V4L2-Treiber) bleibt vertretbar — die Reihenfolge zwischen
   `h713-tvcap` und dem Treiber kann er wirklich nicht zusagen —, aber ihre Begründung ist falsch belegt.
6. **`D-plane.md` §5 erwartet `device /dev/dri/card0 (sun50i-h713-afbd)`.**
   Auf dem Board ist der AFBD `card1`, `card0` ist Panfrost (`00-koordination.md`, Nachtrag 23:05). Das Programm
   sucht die Karten selbst ab, die **erwartete Ausgabe** in der Abnahmevorschrift stimmt trotzdem nicht.
7. **`H-gamma.md`, Abnahme Punkt 0: der `sed`-Befehl widerspricht dem eigenen Satz daneben.**
   Der Text verlangt „in **numerischer** Ordnung einsortieren … und ein `0093` muss **vor** `0095` stehen"; der
   Befehl darunter fügt `0095` unmittelbar **hinter `0090`** ein — also vor ein später eingefügtes `0093`.
   Dazu ruft die Vorschrift `gamma_test` ohne `--karte /dev/dri/card1` auf; ohne den Schalter läuft sie nicht
   (`00-koordination.md`, Nachtrag 23:05). Beides ist beim Zusammenführen zu berichtigen.
8. **`A-patches.md` §8 Punkt 3 verlangt `modetest`**, das es auf dem Board nicht gibt. Die Abnahme hat es über
   `/sys/kernel/debug/dri/1/state` gelöst (`A-abnahme-board.md` Punkt 3) — die Vorschrift ist damit überholt,
   das Ergebnis (Plane-ID 38) liegt vor.
9. **`79-nachtlog-20260907.md`, Liste der Teillogs, ist unvollständig und an einer Stelle falsch.**
   `E — V4L2-Treiber` ist als *„(nicht angelegt)"* geführt, obwohl `nachtlog/E-v4l2.md` existiert (22:47).
   Nicht verlinkt sind `F-hy310-tv.md`, `B2-quellenwechsel.md`, `M4-hpd-dauer.md` und
   `K5-board-verifikation.md`. `79` gehört der Hauptsitzung und wurde nicht angefasst.
10. **`00-koordination.md`, Nachtrag 23:12, nennt eine Fundstelle, die es nicht gibt.**
    Dort steht, in `doku/88-v4l2-hdmirx.md` sei die Begründung „ohne `v4l2-ctl`" zu streichen. In `88` kommt
    weder `v4l2-ctl` noch `modetest` vor (`grep`); die Behauptung steht allein in `nachtlog/E-v4l2.md` §6 —
    und die ist dort **unkorrigiert** stehen geblieben, obwohl `F-hy310-tv.md` §6 Punkt 3 ausdrücklich um die
    Richtigstellung bittet.
11. **Datumsangaben laufen quer.** In `75` tragen die Nachträge 11:45 bis 13:35 das Datum **07.09.**, die
    **späteren** Nachträge 14:55 bis 21:15 dagegen **06.09.**; `78` datiert Abschnitt 0a auf „07.09., 22:15",
    während dieselbe Erkenntnis im Nachtlog auf den Abend des 06.09. fällt. Die **Uhrzeiten** sind durchweg
    stimmig und aufeinander beziehbar, die Datumsangaben nicht. Ich habe in meinen Ergänzungen deshalb nur
    Uhrzeiten und „die Nacht 06./07.09." benutzt und kein Datum korrigiert.
12. **Scheinbarer Widerspruch, aufgelöst — die 10 s HPD-low.** `B-arisc.md` (und `doku/82` §8) hält an den 10 s
    fest, „bis eine Messung etwas anderes zeigt"; `M4-hpd-dauer.md` misst 0,3 s. Kein echter Widerspruch: M4
    deckt den **Wiederanlauf** ab, die 10 s in `arisc_edid_init.sh` stehen an der Stelle, an der der Zuspieler
    ein **neues** EDID lesen soll — und genau dieser Fall ist ungemessen. Beide Seiten sagen das auch selbst;
    ich führe es auf, weil die beiden Zahlen sonst als Fehler gelesen werden.
13. **Erledigt, aber an zwei Stellen noch als offen geführt:** `C-cpu-comm.md` §5 bittet die Hauptsitzung, die
    verschobene `RX-CALL`-Druckzeile in `0014` nachzuziehen. Sie steckt bereits als dritter Punkt in `0097`
    (Patchkopf gelesen). Im Handoff ist das entsprechend vermerkt.
14. **`D-plane.md` §5 gegen `B2`/`M4` — die Abnahmevorschrift ist falsch herum.** Sie veröffentlicht den
    Descriptor (Plane-Enable) **nach** der EDID/HPD-Sequenz und ohne Freigabeschritt; genau das schaltet die
    Capture ab, die Wand zeigt dann ein Standbild. Dieselbe Beobachtung hat die Hauptsitzung unabhängig in
    `INTEGRATION-hauptsitzung.md` notiert. `F-hy310-tv.md` §7 hat den Fall dagegen bereits richtig als
    „erwarteter Descriptor-Effekt" samt Handgriff zum Freigeben stehen — die beiden Vorschriften widersprechen
    einander also innerhalb derselben Nacht.
15. **`00-koordination.md` Nachtrag 22:15 gegen die Integrationsprüfung.** Die Koordination warnt, `0092` könne
    Hunks doppelt mitbringen, die schon in `0097` stehen; die Prüfung hat das **nicht** bestätigt — der echte
    Konflikt lag woanders (ein Hunk von `0092` löscht den Block, in den `0097` einsetzt). Die Sorge war richtig,
    die Begründung nicht.

---

## 5. Board-Anfrage

**Keine.** Paket L ist vollständig offline.
