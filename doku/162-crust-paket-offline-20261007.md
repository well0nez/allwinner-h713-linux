# 162 - Crust als Paket für den Gerätetest vorbereitet, offline, nicht gemessen (07.10.2026)

**Kurz:** In der Nacht 06./07.10. hat ein Agent den FB-CRUST-Port (`umbau/work/FB-CRUST`, 27.09., nie am Gerät) bis zur
Testreife gebracht: crust für Normalbetrieb und Standby, DRAM-Selbstauffrischung und Tiefschlaf aus dem Hersteller-Blob
portiert, Kernel-, TF-A- und U-Boot-Patches, vier per FEL ladbare Testabbilder, Testskripte. Am Gerät ist **nichts**
gemessen: um 01:20 war der HY310 nicht erreichbar, und mit gestecktem USB-Kabel gibt es keinen Fern-Reset - Marco und ich
haben die Gerätearbeit für die Nacht abgesagt. Zwei Prüfrunden der Hauptsitzung (41 und 17 Funde) und zwei
Nachbesserungen folgten. Lieferung: `arbeit/crust-20261007/` (`BERICHT.md`, `PRUEFUNG*-20261007.md`, `patches/`,
`bin/`, `skripte/`, `belege/`). Einstieg in TODO 3.2 (Crust-Weg) und 3.1 (Hersteller-Standby, gestrichen).

## 1 Was vorbereitet ist

- **crust:** FB-CRUST plus 25 Commits, `patches/crust/0001-0028` auf upstream 499a362; sechs Bilder (HY310 und
  HY300 Pro, je Licht, Selbstauffrischung, Tiefschlaf). Vertragsseite Version 4 mit Herzschlag, Schlafdauer, Build-
  und Codekennung.
- **Kernel** (Nummern vorläufig, gegen Baum 50e281fd): 0186-0186c crust laden oder einen laufenden behalten, 0186a nur
  Prüfstand (`firmware=`), 0187-0187d FB-STANDBY neu aufgesetzt plus Standby nur mit crust, 0188-0191 Lüfter, MIPS
  parken und afbd ruhen, nur bei Suspend-to-RAM.
- **TF-A** 0001-0004 (crust aus dem DRAM-Staging starten, SYSTEM_SUSPEND nur als Bauoption und nur, wenn crust lebt),
  **U-Boot** 0001 (crust im FIT). Vier FEL-Abbilder: `release-crust` (ohne Suspend) und `release-standby{,-sr,-deep}`.
- **Skripte:** `phase1.sh` (Normalbetrieb, ~27 min + 30 min Dauerlauf), `box/crust-box.sh` (auf der Box; nichts
  Installiertes wird ersetzt, Test nur aus `/root/crust-test/`, Sicherung `/root/sicherung-crust/`, GP2/GP3 werden vor
  der Rückkehr zum Blob zurückgeschrieben, GP5 nie), Testpläne für FEL (§5) und Standby (§6) im Bericht.

## 2 Was das Modell vor dem ersten Gerätetest fand (statisch oder Modell, nicht gemessen)

- Das Little-Endian-Fenster des Blobs (R_CPUCFG, über [GP3, GP3+1 MiB)) übersteht vermutlich den AR100-Reset; FB-CRUSTs
  Bild hätte dann seine Konstanten verdreht gelesen und nie gemeldet. crust schließt das Fenster jetzt beim Start.
- TF-A hätte den Staging-Bereich `0x48100000` ungemappt gelesen (Data Abort beim Boot); der CIR-Pin hatte Funktion 2
  statt 3 (IR-Wecken unmöglich); der Tasten-Interrupt auf PL4 wäre nach dem Wecken tot gewesen; der Cluster-Reset kam
  2 ms nach dem Rahmen (Rennen mit TF-As Sperren); nach dem Aufwachen lief der AR100 auf dem Takt des Blobs weiter.
- **Möglicher Mitgrund für `doku/139` („Aufwachen nie"):** der Blob liest beim DRAM-Ausgang Takt, Typ und Timing aus
  `arisc_para`, und unser Treiber füllt diesen Block mit Nullen. Statisch, nicht gemessen; der Hersteller-Standby bleibt
  gestrichen (TODO 3.1), crust nimmt die Werte aus seiner Konfiguration.
- Differenzspuren im selben Registermodell: DRAM-Selbstauffrischung (5 SID-Zweige, 2 LPDDR3-Sätze, HY300 Pro),
  Tiefschlaf und Cluster ab/auf greifen in Reihenfolge und Wert wie der Blob zu, bis auf zwei gewollte Stellen. Das sagt
  nichts darüber, ob der DRAM es übersteht.

## 3 Die Prüfungen (Hauptsitzung)

Selbst nachgemessen nach jeder Runde: crust-Bilder aus den Patches bytegleich (Endstand Baum `4a333c9d`), Kernel-Serie
ohne Versatz auf den Baumdateien, Emulator 34/34 PASS, Spuren reproduziert, FIT-Inhalt der FEL-Abbilder gleich `bin/`,
die Geräteskripte Zeile für Zeile gelesen. Die Prüfer fanden in Runde 1 unter anderem: `stopp` hielt `h713-warp` nicht
an (Phase 1 wäre bei Schritt 2 stehen geblieben), der Standby-Plan rechnete mit einem Watchdog-Reset, den es nicht gibt
(TODO 2.25), der Emulator bewertete Standby und Zeitgeber gar nicht; in Runde 2 einen Vergleich auf `masked` statt
`masked-runtime`. Alles behoben, Einordnung je Fund in `BERICHT.md` §9/§10. Ein offener Punkt (B35): ob HDCP 1.4 nach
einem Tiefschlaf zurückkommt, ist offline nicht prüfbar - mit dem HDCP-Paket (`doku/161`) gibt es nur eine
Senken-Schreibung pro Boot.

## 4 Für den Gerätetest

Kein Hängernetz: unter Linux ist kein Watchdog scharf (TODO 2.25), U-Boot stoppt den aus BL31, crust schaltet keinen
scharf. Jeder Hänger braucht Marco an der Box (USB ziehen, dann Sonoff). Reihenfolge: Phase 1 im Normalbetrieb
(`BOX=<ip> skripte/phase1.sh 0..9`, Rückweg Schritt 8 oder ein Neustart), dann FEL mit `release-crust`, dann Standby
Stufe A/B/C nur mit Marco an der Box. Gelernt in dieser Nacht, eingetragen in `referenz/irrwege.md` und `messregeln.md`:
objcopy ohne Ausgabedatei, leerer `printf` in sysfs, `modprobe.blacklist=` gegen Dienste, `masked-runtime`,
Glob-Reihenfolge unter `de_DE`; ein Modell-PASS zählt erst, wenn das Modell den alten Fehler findet.
