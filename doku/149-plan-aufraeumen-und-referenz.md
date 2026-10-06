# 149 — Plan: Aufräumen, und eine Referenz, auf der eine Wissensdatenbank stehen kann

Stand 05.10.2026. Grundlage ist die Bestandsaufnahme desselben Tages: 74 Paket-Checkouts,
282 G unter `umbau/`, und **keine verlorene Arbeit** — jedes Erzeugnis jedes geprüften Pakets
liegt in der Hauptlinie, bei den vier Kernel-Checkouts zu 100 % der hinzugefügten Zeilen.

Der Plan hat drei Teile, in dieser Reihenfolge: **erst buchen, dann löschen, dann aufbauen.**
Löschen ohne Inventar ist Raten; das Inventar ist der Teil, der bleibt.

## 0 Die Regel, die gefehlt hat

74 Pakete sind entstanden, integriert — und ihr Klon blieb liegen. Niemand wusste hinterher,
ob noch etwas darin steckt, und genau deshalb musste angenommen werden, TF-A sei im Repo.
Also:

> **Ein Paket ist fertig, wenn sein Ergebnis in der Hauptlinie ist, sein `REPORT.txt` im
> Paketordner bleibt und sein Klon weg ist.** Wer den Klon behalten will, schreibt in den
> Report, warum.

## 1 Teil A — buchen (nichts wird gelöscht)

### A1 Das Paket-Inventar

Eine Tabelle pro Paket: Name, Zweck, **was es geliefert hat**, wo das in der Hauptlinie liegt,
Urteil (integriert / offen / verwaist), und ob der Klon entbehrlich ist. Für die 13 geprüften
Pakete steht das Urteil schon fest; die übrigen 61 sind mit demselben Verfahren in einem Lauf
zu messen:

* `src`-Checkouts: liegen die Erzeugnisse in `fable-main`? (Datei für Datei, nicht nach Gefühl)
* `linux`-Checkouts: stehen die hinzugefügten Zeilen in `mainline/patches/kernel/`?
* `u-boot`-Checkouts: stehen die Commits im Fork bzw. in `uboot-h713/`?

Das Inventar ist die Löschfreigabe. Ohne Zeile im Inventar wird nichts gelöscht.

### A2 Das Register der unersetzlichen Artefakte

Was **nie** gelöscht werden darf, mit SHA-256, Herkunft und Datum — damit man es nicht
jedes Mal neu herausfinden muss:

| Artefakt | warum unersetzlich |
|---|---|
| `re/device-dumps/emmc-*` (28 G) | die **einzigen** Abbilder, die den Secure Storage tragen (Magic `0x17253948` an LBA 12304 geprüft) |
| `*/secure-storage.bin` (0600 root) je Gerät | HDCP-1.4/2.2-Schlüssel, MACs, Seriennummer — gerätegebunden, nicht wiederherstellbar |
| `~/Downloads/*OTA*.img`, `update.img`, `boot_a.img` | Android-Originale der Geräte |
| `firmware/` (9,5 G) | Herstellerartefakte, Grundlage jeder Extraktion |

Die `abbild-gefuellt.img` / `image-filled.img` (je 1,2 G) sind **nicht** in dieser Liste: sie
sind zusammengesetzt und tragen den Secure Storage **nicht** (geprüft — der liegt in einer
genullten Lücke). Sie sind ableitbar, also entbehrlich, aber das muss im Register stehen,
sonst hält sie jemand für Sicherungen.

## 2 Teil B — löschen, nach Risiko geordnet

**Stufe 1, risikofrei (≈ 170 G).** Reproduzierbar oder belegbar entbehrlich:

| was | Größe | Grund |
|---|---|---|
| `umbau/build/` | 68 G | Bauausgaben, aus den Quellen reproduzierbar |
| die 74 Paket-Klone (nicht die Paketordner!) | 99 G | Erzeugnisse in der Hauptlinie, gemessen. `REPORT.txt`, Briefs und Patches bleiben |
| `analyse/cstenger-abgleich-20260922/repo` | — | ausgeräumter Vergleichsklon (nur Löschungen offen) |
| `re/zip-rescue/HY310-DEV` | — | dito |
| `/opt/Projekte/h713/mainline` (Standalone) | — | Checkout vom 07.09., 133 Patches gegen 207 committete |
| `umbau/ab/src` | 9,3 G | Branch `hy300-pro-ab` restlos überholt; Ref bleibt in `repo-neu` |

**Stufe 2, nach Sichtung (≈ 7 G).** Alte Gerätestände, die durch neuere ersetzt sind:

* `hy310-sicherung-20260912*` (vier Stände à 1,2 G, plus drei à 50 M) — der 04.10.-Stand
  `hy310-sicherung-20261004-v096` ist der aktuelle. **Regel: pro Gerät den neuesten
  vollständigen Stand behalten, plus den letzten Stock-Stand**, alles dazwischen weg.
* `h713-dump/image-filled.img` — abgeleitet, Region liegt daneben.
* `tftp/` (339 M) — laut `release/build-all.sh` ohnehin „a development shelf, not an input".

**Stufe 3, nie.** Teil A2.

**Vor jeder Stufe:** Register schreiben, Hashes prüfen, dann löschen. Nicht umgekehrt.

## 3 Teil C — der Referenzordner

Ein Ort, `referenz/`, der für eine Maschine gemacht ist, die etwas *nachschlägt* — nicht für
einen Menschen, der eine Geschichte liest. Der Unterschied: jede Datei beantwortet **eine**
Frage, der Name sagt welche, und am Ende steht, wie man einen Eintrag ändert.

```
referenz/
  00-INDEX.md             welche Frage steht in welcher Datei (einzige Datei, die man lesen muss)
  geraete.md              pro Gerät: Modell, Platine, Board-Ordner, IP, ADB, UART, wie man es
                          in FEL bringt, wie man es stromlos macht, was es NICHT verzeiht
  werkzeuge.md            IDA/idalib/Ghidra samt Projektpfaden, podman-Welt zum Bauen, sonoff,
                          ser2net am Orange Pi, sunxi-fel, h713-fel, wo jedes Binary liegt
  baeume.md               welche Quellbäume es gibt, welcher wohin spiegelt, wer Hauptlinie ist
  pakete.md               das Inventar aus A1
  artefakte.md            das Register aus A2
  messregeln.md           wie man messen MUSS, damit es zählt (HDCP: löschen -> Desired ->
                          pushen -> Enabled, im selben Boot; Watchdog scharf; usw.)
  irrwege.md              was nachweislich NICHT geht, mit Beleg - teurer als alles andere
```

**Warum nicht in `docs/`:** `docs/` erklärt das Produkt einem Benutzer. `referenz/` beantwortet
Arbeitsfragen und enthält Dinge, die nie veröffentlicht werden (Adressen im Heimnetz, lokale
Pfade). Es bleibt lokal, und `sperr-scan.py` bekommt es in die Sperrliste, damit es nicht
versehentlich mitgeht.

### Die Eigenschaft, auf die es ankommt

Jede Datei endet mit demselben Abschnitt:

> **Etwas geändert?** Hier eintragen, mit Datum und Messung. Wer eine Aussage hier widerlegt,
> ersetzt sie nicht stillschweigend, sondern schreibt die neue hin und die alte als überholt
> darunter.

Das ist derselbe Grundsatz, der das Journal tragfähig macht, nur auf eine Datei angewandt, die
aktuell sein *muss*.

## 4 Was noch offen ist und hier hineingehört

* **„Welcher Ordner ist mein Gerät?"** — `boards/hy300-pro` ist das Gerät des Melders,
  `boards/hy200-qz713df-a1` ist die Platine und damit der HY300PRO-G-EU. Das ist sachlich
  richtig und trotzdem verwirrend, weil der Ordnername das Handelsgerät nicht nennt. Gehört
  als Tabelle nach `geraete.md` **und** nach `boards/README.md`.
* **Die beiden Forks sind nicht gepusht** (U-Boot 6, TF-A 2 Commits), und `fable-main` ist
  58 Commits vor GitHub. Eigener Schritt, bewusst aufgehoben.
* **Die WLAN-Timeouts sind unverifiziert** (`doku/144`): Rootfs neu bauen, mit absichtlich
  verklemmtem Funk booten.

## 5 Stand 06.10.2026

* **Teil A (buchen):** erledigt 05.10. - `referenz/artefakte.md` fuehrt die unersetzlichen Artefakte mit Hash;
  die drei letzten Abzuege werden am 06.10. gehasht (TODO 7.9).
* **Teil B (loeschen):** erledigt 05.10., +192 GB frei, nichts verloren (74 Paket-Checkouts inventarisiert,
  `re/device-dumps/` unangetastet). Die Sicherungs-Tags und -Branches (`vor-main-umzug/*`, `von-src/*`,
  `sicherung/*`) warten auf Marcos Ja (TODO 7.7/7.8).
* **Teil C (Referenz):** steht - `referenz/00-INDEX.md` mit geraete, werkzeuge, baeume, pakete, messregeln,
  irrwege, artefakte, protokolle/. Dazu seit 05.10. MemPalace (nur H713) und Graphify im Probebetrieb bis 12.10.
* **§4 offene Punkte:** Boards-Tabelle steht in `geraete.md`; Forks weiter ungepusht (TODO 1.6, bewusst);
  WLAN-Timeouts im v0.96-beta-Abbild drin, Haengefall offen (TODO 1.3).
* Diese Datei lebte bis heute nur im Journal-Master; ab jetzt in der Repo-Kopie (`repo-neu/doku/149`).

