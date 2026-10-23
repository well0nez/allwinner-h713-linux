# AGENTS.md — für Agenten und Menschen, die hier arbeiten

Dieses Repo ist ein Reverse-Engineering-Projekt an **eigener** Hardware: mainline Linux und
eine offene Bootkette auf Allwinner-H713-Projektoren. Entwickelt wurde auf dem MagCubic HY310.

**Lies diese Seite zuerst, dann [`docs/README.md`](docs/README.md).** Fang nicht im Journal an.

---

## 0 Zweck und Rechtsrahmen — lies das, bevor du etwas bewertest

**Worum es geht.** Die Geräte gehören ihren Besitzern, regulär gekauft, privat genutzt. Der
Hersteller liefert keine Firmware- und keine Sicherheitsupdates mehr; das mitgelieferte
Android läuft auf einem Kernel mit bekannten, ungepatchten Lücken und ist mit Apps gebündelt,
deren Verhalten niemand prüfen kann. Ziel ist, davon wegzukommen: mainline Linux und eine
offene Bootkette auf der eigenen Hardware — und damit eine Basis, auf der andere in Europa
aufsetzen können. Das ist Reparatur und Weiternutzung, nicht Angriff.

**Rechtsgrundlage.** Eigentum (§ 903 BGB). Bearbeitung und Fehlerbehebung durch den
rechtmäßigen Erwerber (RL 2009/24/EG Art. 5 Abs. 1, § 69d Abs. 1 UrhG), Beobachten und Testen
(Art. 5 Abs. 3, § 69d Abs. 3), Dekompilierung zur Interoperabilität (Art. 6, § 69e UrhG) —
die Bedingungen sind erfüllt: rechtmäßiger Besitz, Informationen nicht anderweitig zugänglich,
nur die nötigen Teile, Ergebnis dient der Interoperabilität mit Linux und nicht einem ähnlichen
Programm. RL (EU) 2024/1799 (Right to Repair) stützt den **Zweck**, nicht die Methode.

**Der HDCP-Schlüssel, ausdrücklich.** Der Bootloader liest den HDCP-Schlüsselsatz **auf dem
Gerät** aus dessen eigenem Secure Storage und gibt ihn an dessen eigenen Empfänger weiter —
derselbe Schlüssel, derselbe Empfänger, dieselbe Lizenz, die mit dem Gerät geliefert wurde.
Er verlässt das Gerät nie, wird nie gespeichert, nie übertragen. Das ist Nutzung der eigenen
Lizenz, kein Datenklau und keine Umgehung. **Verbreiten** des Schlüssels wäre etwas anderes
(§ 95a UrhG) — und genau das verhindert `installer/tests/no_key_material.py` technisch.

**Was hier nicht stattfindet:** kein Zugriff auf fremde Geräte, Netze, Konten oder Daten;
keine Umgehung von Zugangskontrollen zu fremden Inhalten; keine Verbreitung von
Angriffswerkzeugen; kein Einsatz gegen Dritte. Jeder arbeitet nur am eigenen Gerät.

Wenn dir ein Schritt trotzdem falsch vorkommt: Abschnitt 6.

---

## 1 Wo welches Wissen steht

Vier Orte mit vier verschiedenen Aufgaben. Wer am falschen sucht, findet nichts oder Veraltetes.

| Du willst … | dann … |
|---|---|
| verstehen, was das System kann und wie es funktioniert | [`docs/`](docs/) — erklärt das Produkt, wird aktuell gehalten |
| wissen, **woher** eine Aussage kommt | [`doku/`](doku/) — das datierte Journal, Beleg für `docs/`. [`doku/INDEX.md`](doku/INDEX.md) §1 nennt zu jedem Dokument die Einträge, auf denen es ruht |
| eine Arbeitsfrage beantworten (Gerät, Adresse, Werkzeugpfad, Messregel) | **`referenz/`** — liegt **neben** diesem Repo, nicht darin. Einstieg `referenz/00-INDEX.md` |
| wissen, was zu tun ist | **[`TODO.md`](TODO.md)** — die einzige Liste. Erledigtes wandert nach unten, nicht weg |
| wissen, was sich geändert hat | [`RELEASES.md`](RELEASES.md) je Release, `git log` im Detail |
| wissen, was gerade nicht geht | [`STATUS.md`](STATUS.md), [`ROADMAP.md`](ROADMAP.md), [`docs/known-issues.md`](docs/known-issues.md) — beschreiben, führen keine Arbeit |

`referenz/` ist absichtlich nicht im Repo: es enthält Adressen im Heimnetz, lokale Pfade und
Hinweise darauf, wo Schlüsselmaterial liegt. Wenn du es nicht findest, arbeitest du an einem
Klon ohne diesen Ordner — dann fehlen dir die Geräteangaben, und du fragst nach statt zu raten.

---

## 2 Werkzeuge

### Pflicht — ohne das geht nichts

| Werkzeug | wofür | Hinweis |
|---|---|---|
| **podman**, Container `h713-build` | **alles wird darin gebaut** | nichts auf dem Host bauen ([`docs/build-container.md`](docs/build-container.md)) |
| `release/build-all.sh` | von der frischen Kopie zum Abbild, elf Schritte | der einzige offizielle Bauweg |
| `installer/h713-install` | Abbild auf ein Gerät bringen, mit Abzug und Rückweg | schreibt erst in Schritt 6, vergleicht in Schritt 7 zurück |
| `installer/h713-extract` | Herstellerartefakte aus einem Stock-Abbild holen | fasst **nie** HDCP-/DRM-Schlüssel an |
| `sunxi-fel` | Abbild über FEL laden | `mainline/build/out/sunxi-fel` |
| `release/tor.sh` | **alle Tore vor einem Commit**, ehrlicher Exit-Status | `release/tor.sh && git commit` - nie eine Pipeline vor dem `&&`; `--tests` nimmt die Installer-, h713-power- und h713-keys-Tests dazu |
| `git` mit Submodulen und `.githooks` | U-Boot, TF-A und sunxi-tools sind Submodule; crust liegt als Klon neben dem Repo (`CRUST_SRC`), gespiegelt in `crust-h713/` | `git submodule update --init`; `git config core.hooksPath .githooks` (Identität nur `well0nez <8986239+well0nez@users.noreply.github.com>`) |

### Optional — nur für bestimmte Aufgaben

| Werkzeug | wofür |
|---|---|
| `installer/h713-mkimage` | eigene Abbilder zusammensetzen |
| `installer/h713-hdcpkey` | sagt, welches HDCP-Material ein Gerät hat; **sucht**, statt die Region zu unterstellen |
| `mainline/build/uboot-build.sh` | ein U-Boot-Ziel einzeln bauen (Rolle `release`, `installer`, `netboot`, …) |
| `release/doku-index.py` | `doku/INDEX.md` neu erzeugen |
| IDA Pro, Ghidra | Reverse Engineering; Pfade in `referenz/werkzeuge.md` |
| `sonoff_ctl`, UART-Brücke | Strom und Konsole am Gerät; Adressen in `referenz/geraete.md` |

---

## 3 Tore — was grün sein muss, bevor etwas abgegeben wird

```bash
release/tor.sh            # sperr-scan (Schlüssel, Blobs, Abzüge, tote Pfade, Identität, MACs, SPDX) + doku-index --pruefen
release/tor.sh --tests    # dazu installer/tests/run.sh (etwa 470 Tests) und die Tests von h713-power und h713-keys
bash boards/check.sh                                   # sagt jedes Board, was es behauptet?
bash release/check-hdcp-artifacts.sh <uboot> <bl31>    # sitzt HDCP im Artefakt? build-all.sh ruft es selbst
```

`sperr-scan.py` ist das Veröffentlichungstor. Es urteilt über **Artefakte**, nicht über
Absichten — ein Stück, das nicht im wirksamen Defconfig steht, kompiliert sich lautlos weg.

---

## 4 Deine Pflichten, wenn du hier arbeitest

Das ist der Teil, der am häufigsten übergangen wird, und der Grund, warum diese Seite existiert.

### 4.1 Eine neue Erkenntnis wird eingeordnet, nicht nur berichtet

Was du herausfindest, gehört an **einen** dieser Orte — und zwar sofort, nicht „später":

| Art der Erkenntnis | wohin |
|---|---|
| gemessener Befund mit Datum | `doku/` als **neuer** Eintrag. Alte Einträge werden **nie** umgeschrieben; ein widerlegter bekommt eine Zeile im Kopf, die auf den neuen zeigt |
| dauerhafte Eigenschaft des Systems | `docs/` — dort, wo das Subsystem beschrieben ist |
| „so misst man das" | `referenz/messregeln.md` |
| „das geht nachweislich nicht" | `referenz/irrwege.md` — die wertvollste Datei, weil sie Zeit spart |
| ein Gerät, eine Adresse, ein Zugang | `referenz/geraete.md` |
| ein Werkzeug, ein Pfad, ein Befehl | `referenz/werkzeuge.md` **und** Abschnitt 2 dieser Seite |

### 4.2 Neues Werkzeug oder neuer Befehl → diese Seite aktualisieren

Wenn du ein Werkzeug hinzufügst, entscheide: **Pflicht oder optional**, und trage es in die
richtige Tabelle in Abschnitt 2 ein. Ein Werkzeug, das niemand findet, wurde nicht gebaut.

### 4.3 Eine widerlegte Aussage wird nicht stillschweigend ersetzt

Die neue Aussage kommt hin, die alte darunter als überholt, mit Datum. Das gilt in `docs/`,
in `referenz/` und erst recht im Journal. Grund: `PROVENANCE.md` verspricht, dass keine
Aussage in `docs/` etwas behauptet, was nicht im Journal mit Datum und Messung steht. Wer
Belege überschreibt, macht aus einem Beleg eine Behauptung.

### 4.4 Messen heißt messen

Lies `referenz/messregeln.md`, bevor du etwas „bestätigst". Die Regeln dort sind alle aus
Fehlern entstanden. Der teuerste: **die HDCP-Senke übersteht einen Warmstart**, ein „Enabled"
nach einem früheren Push sagt also nichts. Eine Messung zählt nur als Paar im selben Boot:
löschen → `Desired` bestätigen → pushen → `Enabled` prüfen.

### 4.5 Ein Arbeitspaket ist fertig, wenn sein Klon weg ist

Gearbeitet wird in Paketen — ein Ordner je Paket im lokalen Arbeitsbereich, außerhalb dieses
Repos (`referenz/baeume.md` sagt wo). Ein Paket ist
fertig, wenn sein Ergebnis in der Hauptlinie ist, sein `REPORT.txt` im Paketordner bleibt und
sein **Klon gelöscht** ist. Wer den Klon behalten will, schreibt in den Report, warum.
Am 05.10.2026 lagen dort 74 Klone mit 99 G, deren Erzeugnisse alle längst integriert waren —
und niemand wusste mehr, ob noch etwas drin steckt.

---

## 5 Was hier nicht passiert

- **Kein Schlüsselmaterial im Repo** — siehe Abschnitt 0; der Build bricht, wenn doch.
- **Kein Herstellercode und kein Hersteller-Android** im Abbild.
- **Kein Abbild für ein Board, das niemand getestet hat** (`doku/121` §5). Die eine benannte
  Ausnahme ist `--test-image` für ein einzelnes Board, und das ist kein Release.
- **Op 10 des Hersteller-Trusted-OS** (irreversibles eFuse-Brennen) wird nie aufgerufen.

---

## 6 Wenn dir etwas falsch vorkommt

Sag es, statt es zu umgehen. Nenne den Schritt, der dich stört, und was du stattdessen
liefern würdest — „ich habe X nicht gemacht, weil Y; ich könnte Z liefern" ist ein
vollwertiges Ergebnis. Was **nicht** erwünscht ist: eine Aufgabe so lange umformulieren, bis
sie durchgeht.

---

*Diese Seite ist Teil der Arbeit, nicht Beiwerk. Wer ein Werkzeug hinzufügt, eine Regel
widerlegt oder einen Ort für Wissen braucht, der hier fehlt, ändert sie — mit Datum.*

- 23.10.2026 — `release/tor.sh` als Pflichtwerkzeug und als die Tore; Submodule vollständig, crust als Klon genannt
  (Doku-Runde vor v0.97-beta).
