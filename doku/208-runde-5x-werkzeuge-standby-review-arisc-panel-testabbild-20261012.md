# 208 - Die 5.x-Runde: Werkzeuge, Reste der Standby-Durchsicht, ARISC-Wahl, Panel-PR, Testabbild runde5x1 am HY310; Handoff (12.10.2026, nachts)

**Kurz:** Marco ging die offenen Punkte aus TODO §5 mit mir einzeln durch und entschied je Punkt (`main` 6301847); dann in der
vereinbarten Reihenfolge: Werkzeuge am PC (nach `main`), Dienste, Kernel, TF-A, ARISC-Umschalter (je auf eigenem Zweig), dazu der
Panel-PR aus `well0nez/h713-panel-dev`; alles in einem Testabbild `runde5x1`, auf den HY310 geschrieben, Teil A des Messplans
allein und leise gemessen. **Teil B** (zweiter Tastendruck, Ton, Panel, ARISC hin und zurück) **steht aus, mit Marco.**

## 1 Entscheidungen der Durchsicht (Marco, 12.10. abends)

| TODO | Entscheidung |
|---|---|
| 5.18 Hostname je Board | geschlossen - seit `234282c` in `main`; Reste zu 1.2b (bei Neuinstallation mitnehmen) und 2.54 (im Panel änderbar) |
| 5.19 `boards/check.sh` und alte DTBs | DTB-Teil raus, **kein Hash** - Schritt 10 von `build-all.sh` prüft am frisch gebauten DTB |
| 5.17 Weiterbauen nach Abbruch | nach dem Release, **Pflicht** (heute zweimal gespürt: der Abbruch in Schritt 9, §4) |
| 5.20 ARISC-Wahl | schlank (Moduloption, `h713-arisc`, Installer-Zeile, Doku), **ohne** Install-Option; gemessen wird zuletzt |
| 5.23 neu | unbekannte Android-Firmware -> Issue; README und Installer-Meldung |
| 5.11 Arbeitskopie/Abzug | keine Rechte-Verschärfung ("übertrieben"); alles gehört dem Nutzer, der sudo aufrief; Arbeitskopie nach bestandenem Vergleich löschen |
| 9.15 neu | eigenständiges Update-Werkzeug, ganz spät |
| 5.12 `v4l2-ctl` | Debian-Paket rein |
| 5.14 Standby-Durchsicht | B2/CR-4/KM-4 abgehakt; Banner, CC-3, TFA-R2-2 (vor 1.6), U2, U5, U6, CC-1, CC-6, U3, B4 jetzt; CC-4, CC-5, U4, CR-3, KM-3 nach dem Release; TFA-R2-1 gestrichen |
| 5.14 U2 | über `/sys/power/pm_wakeup_irq` mit `CONFIG_PM_DEBUG` (nicht über den Fehlercode: zwei eigene echte Verweigerungen melden auch -EBUSY) |
| Rest aus 5.16 (msp "error" nach abgebrochenem Standby) | **Wurzel im Kernel** (Zweitprüfung: U2 macht diesen Abbruch zum Normalfall) |
| 5.16, 5.1 | Patch-Texte jetzt; 5.1 geparkt |
| Panel-PR | integrieren zum Ansehen; Unit mit den zwei `ReadWritePaths`-Zeilen behalten, Werkzeug-Doku und `PRODUCT.md` weg |

## 2 Pakete, Zweige, Stand

| Paket (`arbeit/`) | Zweig, Kopf | Inhalt | Stand |
|---|---|---|---|
| `werkzeuge-20261012` | in `main` b818e98 | 5.19, Banner (B2), B4 + `h713-power` auf jedem Abbild in `check-crust.py` (dabei gefunden: jeder Bau ohne `--standby` wäre in Schritt 10 gescheitert), 5.12, 5.11, 5.23 | **in `main`** |
| `dienste-20261012` | `versuch/dienste` 586fb92 | U2 (243ef22), U6 (6f5db52), U5 (495b1c8, 68ba120), U3 (169e98a), Testgerüst (586fb92) | am Gerät Teil A |
| `kernel-20261012` | `versuch/kernel` 1b54a21 | Kernel `0263` CC-1, `0264` CC-3, `0265` CC-6, `0266` msp misst den Stromverlust, `0267` `firmware=vendor\|crust`; `CONFIG_PM_DEBUG`; Patch-Texte 0231/0240/0243; `h713-arisc`, `h713-mkimage --arisc`, Installer-Zeile, Doku; `--arisc`-Fix (962eb69), Pfadanzeige (1b54a21) | am Gerät Teil A |
| `tfa-wdog-20261012` | TF-A `versuch/wdog-readback` 287dca2fe | R_WDOG zurücklesen (TFA-R2-2); BL31 57468 Bytes wie der unveränderte Kopf, nur zwei Texte anders | nicht gespiegelt |
| `panel-redesign-20261012` | `versuch/panel-redesign` 0c619b0 | Seite, Server, 72 Tests aus dem PR (Server = die verworfene Fassung vom 11.10.); Unit mit `/etc/hosts` und den h713-logs-Pfaden | zum Ansehen, `main` erst nach Marcos Ja |
| `testabbild-20261012` | `versuch/testabbild` c763f3b | `main` + die vier Zweige + TF-A 287dca2fe | `runde5x1` auf dem HY310 |

Alles am PC gemessen: `release/tor.sh --tests` vor jedem Commit (447 Installer-, 73 h713-power-, 22 h713-keys-Tests), Gegenproben
gegen die alten Fassungen scheitern wie erwartet. Kernel gebaut (`build.sh kernel`, 288 Patches), die geänderten Objekte mit W=1
ohne Warnung. Abbild `h713-hy310-v0.0-runde5x1`: crust-Tor und HDCP-Artefakte grün, Tabelle `arisc = crust`,
**reproducible: no** (Schritte 1-8 übernommen, §4).

## 3 Gerätemessung Teil A (HY310 `.131`, 23:00-23:21, Quelle ThinkPad 1080p60)

Ergebnis je Punkt in `arbeit/testabbild-20261012/MESSPLAN.md`. Kurz: Installation 5 min (Secure Storage unverändert); Arbeitskopie
gelöscht, Abzug gehört `user`; Schlusszeile "ARISC: crust"; `v4l2-ctl` 1.30.1 am Empfänger (+4,5 MiB); Hostname `hy310`;
`pm_test=devices` -> "standby aborted before the island lost its power: the DSP is rebuilt" (0266); **10/10 Standbys** per RTC, Bild
nach 3,5-5,5 s, DSP 10/10 im 1. Versuch; U5 per Bind-Mount: Bild ohne 2.2-Schlüssel statt keins; **5/5 Warmstarts** mit Panel-Unit,
Warp, 2.2-Schlüssel, crust. CC-3 nicht beobachtbar (kein Aufruf an den geparkten Kern). TF-A: BL31 `287dca2fe` läuft; die
R_WDOG-Zeile erscheint nur nach einem Aus über crust -> Teil B.

**Nicht am Gerät** (Rechner-Tests sind der Beleg): U3, U6, CC-1, CC-6.

## 4 Fehler und Irrwege des Tages

- **Commit ohne Tests:** 68ba120 ging durch `tor.sh` ohne `--tests`, während ein `--tests`-Lauf davor rot war. Ursache: ein eigener
  Test (U5) flatterte - das Stand-in von `h713-hdcp-key` wartete nicht auf den Fake-Kernel (1 von ~10). Gerüst repariert (586fb92),
  40 + 8 Läufe grün; im Code war nichts falsch. Regel seitdem: `tor.sh --tests > log && git commit`.
- **`--arisc` in `build-all.sh`:** `"${X:+crust}${X:-vendor}"` ergibt bei gesetztem X "crust" + X - Schritt 9 brach ab. Behoben und mit
  Test abgesichert (962eb69); Neubau nur ab Schritt 8 mit `--skip-*` (2 min 34 s statt ~45 min) - genau der Fall von 5.17.
- **Fehl-Commit in `main`:** 66b57a7 nahm uncommittete TODO-Zeilen einer parallelen Sitzung (9.1, 9.1a) mit. Zurückgenommen
  (soft reset, eigener Commit), die Zeilen liegen wieder unberührt bei ihr; nur die eigenen Zeilen per Index committet (882ccfa).
- **Messgröße:** `anzeige.py` zählt bei Warp aus 0 Wechsel von Y0, obwohl das Bild läuft (Marco: "bewegt sich") - die Firmware
  blättert dann selbst; Messgröße dort sind die Zeiger/s (`referenz/messregeln.md`).
- **Panel-PR:** Unit, Werkzeug-Doku und das Weglassen von `PRODUCT.md` zuerst ohne Rückfrage entschieden; danach mit Marco geklärt (§1).

## 5 Handoff (12.10.2026, ~23:45)

**`main`:** 882ccfa (+ dieser Eintrag), **nicht gepusht** - wie seit 234282c alles; Reihenfolge beim Push `TODO.md` §1.

**Geräte:**
- **HY310** (`.131`, UART-ESP `.224`): Testabbild **`runde5x1`** (Kernel 20:18 UTC, BL31 287dca2fe, crust 54e4a08) aus
  `versuch/testabbild`; `/etc/h713`, Bluetooth-Bund, Hostschlüssel (`SBcCAf…`) vom Vorstand; `h713_gate=1`; **Warp an** (Marco),
  Ecken `tl 59,2 tr 45,46 bl 0,70 br 13,22`; `power.conf default = standby`. Schnell-Deploy: `h713-arisc` 1b54a21 (Sicherung
  `/root/sicherung-arisc/`). Testmaterial `/root`: `s3-test.py`, `zustand.sh`, `anzeige.py`. Abzug der Installation:
  `arbeit/testabbild-20261012/install-dump/` (klein, gehört `user`). FEL-Kabel steckt. Eine parallele Sitzung (Medien) misst
  gerade die GPU am HY310.
- **HY300PRO-G-EU**: unverändert seit `doku/206`/`207`.

**Nächstes, in Reihenfolge:**
1. **Teil B mit Marco** (`MESSPLAN.md` B2-B5): zweiter Tastendruck beim Einschlafen (U2 + 0266: Box bleibt an, Bild und Ton),
   kurz hören, Panel ansehen, `h713-arisc set vendor` + Neustart + Aus (Gate, Taste) und zurück; dabei die R_WDOG-Zeile.
2. Bestanden: `versuch/dienste`, `versuch/kernel` nach `main`; TF-A 287dca2fe in den Fork `sun50i-h713`, Spiegel `tfa-h713/` neu,
   Zeiger in `main`; Panel nur nach Marcos Ja. `arbeitsregeln.md` §3 und `referenz/werkzeuge.md`: `h713-arisc` mit der Integration.
3. 7.19 Doku-Runde (dazu: `docs/subsystems/standby.md` Z. 9 und C1, `docs/guides/settings-page.md` für das neue Panel,
   `docs/tools/h713-panel.md` für die neuen Befehle, `FLASHING.md` `~/hy310-dump` gegen `h713-dump`) -> 1.1a -> 1.6/1.7a/1.7 nur mit
   Marcos Ja je Push.
