# Plan - DE-Scaler und Auflösungsunterstützung

> **Erledigt (Stand 08.09.2026):** dieser Plan ist abgearbeitet und am Gerät abgenommen; was davon abweicht und was übrig blieb, steht in [`00-STATUS.md`](00-STATUS.md) §4 und [`60-offen.md`](60-offen.md). Das Dokument bleibt als Planungsstand und Begründung.

Angelegt 07.09.2026. Löst den offenen Rest von [`91-plan-drei-punkte.md`](91-plan-drei-punkte.md)
Punkt 2 ab. Grundlage: [`89-composition-block.md`](89-composition-block.md),
[`nachtlog/E6-aufloesung-erkennung-und-scaler.md`](nachtlog/E6-aufloesung-erkennung-und-scaler.md).

## Was fehlt, präzise

Die Kette Quelle → Panel hat fünf Glieder. Vier stehen:

| # | Glied | Stand |
|---|---|---|
| 1 | Erkennen (INCAP misst, SignalChange feuert) | fertig, auflösungsunabhängig |
| 2 | Aufnehmen (Firmware stellt Capture auf die Quellgröße) | macht die Firmware selbst |
| 3 | Lesen (Plane, Y/C-Stride korrekt) | fertig (`0107`) |
| 4 | **Abbilden Quelle → Panel 1920×1080** | **fehlt - der DE-Scaler** |
| 5 | Anzeigen | fertig |

Der Scaler ist **notwendig für jede** Nicht-Panel-Auflösung. Ob er auch **hinreichend** ist, gilt
nur für progressive Quellen ≤ Panel. Zwei Sonderfälle sind eigene Arbeit und nicht Teil dieses
Plans: **Zeilensprung** (1080i braucht Deinterlacing) und **Downscale** (4K, andere
Filterkoeffizienten als beim Hochskalieren).

## Stand 07.09., 20:40 - S1/S2 gelaufen, der Plan ist korrigiert

Zwei Annahmen dieses Plans sind durch Messung widerlegt, siehe
[`nachtlog/S1`](nachtlog/S1-scaler-gefunden.md) und [`nachtlog/S2`](nachtlog/S2-scaler-anwenden-versuche.md):

- **Die 852×480-Spalte in `doku/89` ist kein Stock-Abzug**, sondern cstengers kaputter Zustand. Der
  darauf gebaute Gegenprobe-Schritt entfällt, und meine „Schrittweite in 1/96"-Formel war eine
  Extrapolation aus einem Datenpunkt zweifelhafter Herkunft.
- **`0x05000174` ist nicht der Scaler.** Der Scaler ist der PROC-Block: `0x05140104/0108` Quelle,
  `0x05140124/0128` Ziel, `0x0514011C` Freigabe - Feldlayout aus `ProcWinNode__WriteReg` hergeleitet
  und am Gerät bei 1080p bestätigt.

**Nachtrag 22:30 - [`S3`](nachtlog/S3-scaler-gefunden-und-bewiesen.md):** Der Scaler ist gefunden
(`0x05180008`/`0x0518003C` Verhältnis in 16.16, `0x05180014` Bit 27 = 1:1-Flag, Phasen in
`0x05180000`/`0x05180038`), die Formel `CalcScaleRatio` hergeleitet und **bitgenau gegen den
laufenden 1080p-Zustand geprüft** (5 von 5 Registern, inklusive der Modusfelder). Schreiben wirkt
sichtbar. Ein korrektes Bild kommt aus dem Userspace trotzdem nicht zustande; offen ist, woher der
aktive Scaler seine *Eingangs*geometrie nimmt.

**Was jetzt gesichert ist:**

1. Beim Auflösungswechsel ändern sich **nur vier Register, alle im AFBD-Block** - unser Treiber
   folgt der Quelle, der ganze Rest der Kette bleibt auf 1920×1080 stehen.
2. Den Fensterneubau der Firmware können wir **nicht** auslösen: die vollständige
   Stock-Quellwechselfolge läuft fehlerfrei durch und ändert nichts (M6 = nein, deckt sich mit
   `DEAD-ENDS` §81, `UpdateWce` ist HW-IRQ-getaktet).
3. Die **PROC-Skalierstufe ist umgangen** - bei 1080p ein Zielfenster von 960×540 gesetzt, Bild
   blieb vollflächig; die Gates `0x05140114/0134` lesen 0.
4. Die **DE-Lesegeometrie ist der Abnehmer**: zehn Register geschlossen auf Quellgröße gesetzt
   machte das Bild deutlich richtiger (Inhalt lesbar, Taskleiste da). Ein Register trägt noch 1920.
5. **Diese Register vertragen kein Durchprobieren im Betrieb** - die Firmware blieb hängen und
   brauchte einen Neustart.

## Schritte

**S1 - Extraktion (idalib, offline, kein Board).** *(gelaufen, siehe oben)*
Aus `display.bin`: die vollständige `kHalSignalID_*`-Tabelle (ID, Geometrie, Porches, Pixeltakt,
Interlace-Flag); `PanelWinNode__CalcWindow` und `__WriteReg` dekompiliert; die Herkunft **jedes**
geschriebenen Registerwertes im `0x0500xxxx`-Block; die `COEF_FLT`-Tabelle bei `0x130030` mit ihrer
Indizierung (welcher Koeffizientensatz für welches Verhältnis).
*Fertig, wenn:* für `0x174`, `0x224`, `0x844`, `0x804`, `0x80C` je eine Formel in Quell- und
Panelgeometrie dasteht - und die untere Hälfte von `0x844` erklärt ist.

**S2 - Gegenprobe.** *(gelaufen; der geplante 852×480-Vergleich entfällt, siehe oben)*
Die Formeln aus S1 auf 852×480→1920×1080 und auf 1920×1080→1920×1080 anwenden und mit den Abzügen
in `doku/89` bzw. unseren eigenen 1:1-Dumps vergleichen.
*Fertig, wenn:* beide Fälle bitgenau reproduziert werden. Weicht etwas ab, gilt S1 als nicht
abgeschlossen - **nicht** die Abweichung wegdefinieren.

**S3 - Treiberpatch.** *(jetzt der nächste Schritt, mit korrigiertem Ziel: nicht `0x05000174`,
sondern die vollständige Folge aus `ProcWinNode__WriteReg` + `sub_8B1A5DF0` + `sub_8B1A604C`,
vorher vollständig dekompiliert. Ein einziger begründeter Schreibvorgang, Test direkt nach einem
Neustart.)*
Den Scaler im AFBD-`atomic_update` programmieren, wenn Quellgeometrie ≠ Panelgeometrie; bei
Gleichheit weiter genau nichts anfassen (kein Verhaltenswechsel für 1080p). Koeffizienten laden,
falls S1 zeigt, dass sie verhältnisabhängig sind. Kein Schreiben in `0x0694xxxx`.
*Fertig, wenn:* der Patch gebaut ist und 1080p unverändert läuft.

**S4 - Board-Test.**
720p-Quelle: volles, unverzerrtes Bild auf dem Panel. Dann 1080p ↔ 720p ↔ 1080p im Wechsel, mit
Blick auf den RPC-Zähler (`0 ohne Antwort` muss halten). Erst wenn das sitzt, fliegt die
Konsolen-Sperre aus `userspace/hy310-tv/main.c` wieder raus.

**S5 - Die übrigen Auflösungen.**
`timings_cap` und `match_preset` aus der Tabelle von S1 füllen; jede Auflösung, die die Tabelle
nennt und die der Zuspieler ausgeben kann, einmal an der Wand prüfen. Was die Tabelle nicht nennt,
wird sauber abgelehnt statt halb dargestellt.

## Regeln, die auch hier gelten

Keine Workarounds - wenn eine Formel nicht hergeleitet ist, wird sie nicht geraten und
„eingestellt, bis es passt". Registerwerte werden nur geschrieben, wenn ihre Bedeutung belegt ist.
`0x0694xxxx` bleibt nur-lesend. Gebaut wird im Container `h713-build`.
