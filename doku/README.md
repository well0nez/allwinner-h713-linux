# Das Arbeitsjournal (das Entwickler-Logbuch) - und warum es hier liegt

**Das ist nicht die Dokumentation. Die steht in [`../docs/`](../docs/) und ist auf Englisch.**

Hier liegen 277 datierte Einträge (169 nummerierte, 108 im Nachtlog) aus der Arbeit an diesem Projekt, auf Deutsch, in der
Reihenfolge, in der sie entstanden sind. Sie sind der **Beleg** für die Dokumentation:
`PROVENANCE.md` verspricht, dass keine Aussage in der englischen Dokumentation etwas
behauptet, was nicht hier mit Datum und Messung steht. Dieses Versprechen ist der Grund,
dass das Journal überhaupt veröffentlicht wird.

## Wie man es liest

* **Fang nicht hier an.** Wer das Gerät benutzen, bauen oder verstehen will, liest
  `../docs/` - rund 9 000 Zeilen mit den Wurzelseiten, aktuell gehalten, auf Vollständigkeit geschrieben.
* **Komm hierher, wenn du einer Aussage nicht glaubst.** [`INDEX.md`](INDEX.md) §1 dreht die
  Zitate um: zu jedem Dokument in `docs/` steht dort, auf welchen Einträgen es ruht.
* **Erwarte keinen aktuellen Stand.** Ein Eintrag sagt, was an einem Tag gemessen wurde.
  Was heute gilt, steht in `docs/`.

## Die eine Regel, die das Journal tragfähig macht

**Einträge werden nicht nachträglich umgeschrieben.** Ein datierter, unveränderter Eintrag
ist ein Beleg; derselbe Satz in einem nachpolierten Text ist nur noch eine Behauptung. Wenn
sich ein Befund als falsch erweist, kommt ein **neuer** Eintrag dazu und der alte bekommt
eine Zeile im Kopf, die auf ihn zeigt - gelöscht oder stillschweigend korrigiert wird nichts.
Deshalb stehen hier auch Irrwege und zurückgezogene Behauptungen. Das ist Absicht: eine
Fehlerliste, die nur Erfolge enthält, ist keine.

Redigiert wird nur eines, und es ist vermerkt, wo es passiert ist: Material, das ein Rezept
zum Umgehen von Kopierschutz auf **fremden** Geräten wäre - Schlüsselmaterial, Kennungen und
Adressen des Hersteller-Trusted-OS, die Lage von Hardwareschlüsseln. Die *Befunde* bleiben
vollständig, weil sie erklären, warum unser eigener Code so aussieht; die Handgriffe für
fremde Geräte sind entfernt. Analyse am eigenen Gerät ist von §§ 69d/69e UrhG gedeckt, die
Verbreitung von Umgehungsmitteln von § 95a UrhG nicht.

Ein zweites Mal redigiert wurde am 23.10.2026, vor der Veröffentlichung von v0.97-beta, und nur Privates:
Adressen im Heimnetz, lokale Pfade, die auf Personen zeigen, die Adresse eines Mailservers. Jede Stelle trägt
den Marker *geschwärzt am 23.10.2026: <was>* (in Codeblöcken `<geschwaerzt 23.10.2026: was>`); der Befund
daneben ist unverändert, Vornamen bleiben. Dieses Journal ist das Logbuch der Entwicklung, kein Handbuch: es
sagt, was an einem Tag gemessen wurde, und was heute gilt, steht in `../docs/`.

## Was für Einträge es gibt

| Art | was es ist |
|---|---|
| **Analyse** | ein Thema auseinandergenommen: Register, Firmware, Formate |
| **Plan** | was gemacht werden soll, mit Abbruchbedingungen |
| **Protokoll** | ein Testlauf mit Ergebnis, oft ein Großtest vor einem Release |
| **Handoff** | Stand am Ende eines Arbeitstages, damit die nächste Sitzung anknüpfen kann |
| **Nachtlog** (`nachtlog/`) | die Sitzungen selbst, 108 Einträge - das Rohmaterial |

Die Nummern laufen chronologisch, nicht thematisch; ein Thema zieht sich darum über mehrere
Nummern. `INDEX.md` §2 listet alle mit Art, Datum und Titel. Dass `128` und `128a` beide
existieren, ist eine alte Kollision, die bewusst so stehen bleibt, weil anderswo darauf
verwiesen wird.

**56 der nummerierten Einträge zitiert niemand** (`INDEX.md` §3; die Nachtlog-Seiten zählen nicht mit). Das ist in Ordnung - ein Journal
darf Material tragen, aus dem nie eine Doku wurde.

## Pflege

```bash
release/doku-index.py            # INDEX.md neu erzeugen
release/doku-index.py --pruefen  # bricht ab, wenn INDEX.md nicht dem Stand entspricht
```
