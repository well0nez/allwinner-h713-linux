# Plan 117 - P5: die englische Dokumentation des Repos

Erteilt von Marco am 12.09.2026, 20:20: „p5 klingt gut … du kennst mein Ziel, meine Prämisse und meine
Ängste, also leg ichs in deine Hand." Dieser Plan hält fest, **was** entsteht, **wie kurz** es sein darf und
**woher** jede Aussage kommt - damit auch ein Agent nicht raten muss.

## 1. Die drei Vorgaben, wörtlich

1. **Im Kontext übersetzen, nicht Satz für Satz.** `doku/` ist die Quelle, nicht die Vorlage. Ein englischer
   Text darf anders gegliedert sein als der deutsche, solange er dasselbe belegt.
2. **Kompakt, aber nicht stichwortartig.** Marco: „nicht kurz im Sinne von kurze Sätze oder Stichwörter,
   sondern kompakte Informationen, die aber dennoch nicht überfordern." Die Kernaussage muss beim Überfliegen
   auffindbar sein - das ist die eigentliche Anforderung. KI-Fließtext, der dreimal dasselbe sagt, ist der
   Fehlerfall.
3. **Jeder abtrennbare Bereich bekommt seine eigene Datei** (MIPS, HDMI-Eingang, `h713-tv`, Fokusmotor …).
   **Und: was wir in U-Boot gebaut haben, muss in *diesem* Repo stehen**, nicht nur im Fork. Der Nutzer soll
   die Funktionen kennen, die Gerät und Werkzeuge mitbringen, ohne ein zweites Repo zu lesen.

## 2. Gerüst - das alte Repo hatte es schon richtig

`legacy/` (Branch im neuen Repo) trägt genau die Struktur, die wir fortschreiben: README mit Leseordnung und
Hardware-Kurztabelle, `STATUS.md` als ehrliche Momentaufnahme, `docs/subsystems/*` je Thema, `docs/hardware.md`,
`docs/architecture.md`, `docs/known-issues.md`. Wir übernehmen das Gerüst und füllen es mit dem arm64-Stand;
neu sind `docs/tools/`, `docs/uboot/` und `docs/install/`.

```
README.md          Was es ist, was läuft, Leseordnung, Hardware-Kurztabelle          ≤ 130 Zeilen
STATUS.md          Tabelle je Teilsystem: Zustand + Beleg (Datum/Datei)              ≤ 130
FLASHING.md        Der Nutzerweg: FEL → ums → hy310-install → erster Start           ≤ 150
BUILDING.md        build-all, Container, Voraussetzungen, was herauskommt            ≤ 120
PROVENANCE.md      Herkunft: cstenger, unsere Forks, Vendor-Blobs (nie im Repo)      ≤  80
docs/hardware.md   Was auf dem Brett sitzt                                           ≤ 120
docs/architecture.md  Drei Prozessoren (ARM, MIPS, ARISC) und wer was besitzt        ≤ 130
docs/known-issues.md  Was klemmt, mit Umgehung                                       ≤ 150
docs/dead-ends.md  aus doku/70 - was wir ausgeschlossen haben, damit es niemand      ≤ 120
                   zweimal versucht
docs/uboot/README.md       Bootkette, Defconfig-Matrix, Verhältnis zum Fork          ≤ 100
docs/uboot/commands.md     h713_disp, h713_mips, h713_logo, h713_i2c                 ≤ 120
docs/uboot/environment.md  hy310.env: jede Variable, was sie tut                     ≤ 100
docs/uboot/power-gate.md   Das Einschalt-Gate - eigene Datei, weil es der erste       ≤  70
                           Stolperstein jedes Nutzers ist
docs/subsystems/display.md      Panel, AFBD-Scanout, KMS                             ≤  90
docs/subsystems/mips.md         Der Coprozessor, seine Artefakte, elog                ≤  90
docs/subsystems/hdmi-in.md      HDMI-Eingang als V4L2-Gerät, Capture-Ring             ≤  90
docs/subsystems/audio.md        HDMI-Ton: Takte, Codec-I2S, MSP-DSP                   ≤  80
docs/subsystems/video.md        VE-Dekodierung, IOMMU, GPU-Pfad                       ≤  80
docs/subsystems/cpu-comm.md     ARM↔MIPS-IPC, In-Kernel-API                           ≤  80
docs/subsystems/arisc.md        Der zweite Coprozessor: PMU, HPD, EDID                ≤  70
docs/subsystems/wifi.md         AIC8800D80, Firmware aus dem eigenen Abzug            ≤  80
docs/subsystems/focus-motor.md  PH14 ist ein Bereichswächter, kein Endschalter        ≤  70
docs/subsystems/board-mgr.md    Lüfter, Tacho, NTC, Temperaturen                      ≤  70
docs/subsystems/crypto-engine.md  CE: was geht, was ungeklärt ist                     ≤  60
docs/subsystems/pq.md           Bildqualität: Stock-Daten → Register                  ≤  80
docs/subsystems/emmc-layout.md  Partitionslayout v3, das Loch, secure storage         ≤  70
docs/tools/h713-tv.md      Der HDMI-Eingang als Dienst, Steuerkanal                   ≤  90
docs/tools/h713-pq.md      PQ-Rechner                                                 ≤  60
docs/tools/h713-focus.md   Fokusmotor von Hand                                        ≤  60
docs/tools/h713-cam.md     Interne Kamera                                             ≤  60
docs/tools/h713-wifi.md    WLAN-Dienst und /etc/h713/wifi.env                         ≤  70
docs/tools/h713-extract.md Vendor-Teile aus der eigenen Firmware ziehen               ≤  80
docs/tools/hy310-install.md  Der Installer                                            ≤  90
docs/tools/hy310-mkimage.md  Der Abbild-Bauer                                         ≤  70
docs/kernel-patches.md     Wie die Serie funktioniert, wie man einen Patch ergänzt    ≤  80
```

Die Obergrenzen sind Obergrenzen, kein Ziel. Wer 40 Zeilen braucht, schreibt 40.

## 3. Form, für jede Datei gleich

- **Erster Absatz sagt, was das Ding für den Leser tut** - nicht, was das Dokument enthält.
- Danach: wie man es benutzt (Befehl, Datei, Schalter). Dann: die Grenzen, ehrlich.
- **Tabellen für Matrizen, Prosa für Begründungen.** Keine Stichwortlisten, wo ein Satz die Ursache erklärt.
- **Belegpflicht:** Was am Gerät bewiesen ist, sagt wo (Datum, `analyse/…`). Was nur gelesen/vermutet ist,
  heißt „unverified" - nie durchgewinkt.
- **Letzte Zeile: „Details: doku/NN"** - die deutsche Fassung bleibt die Langform.
- Keine Füllsätze („This document describes…"), keine Wiederholung derselben Aussage in drei Abschnitten.

## 4. Ablauf

1. Ich schreibe **README, STATUS und eine Teilsystemdatei** selbst - sie sind der Maßstab (Gedächtnis:
   „Agenten brauchen einen Größenmaßstab").
2. Agenten schreiben die übrigen Dateien **als Entwurf** nach `analyse/release/arbeit/p5-entwuerfe/`,
   nie direkt nach `docs/` (Marcos stehende Regel: Agenten schreiben nicht in bestehenden Code).
   Jeder Auftrag nennt: Zieldatei, Zeilenobergrenze, die Quelldateien in `doku/`, die Maßstabsdatei.
3. Ich lese jeden Entwurf gegen die Quelle, kürze und lege ihn nach `docs/`.
4. `release/repo-skelett.sh` nimmt `docs/`, `README.md` usw. beim nächsten Lauf automatisch mit.

## 5. Fortschritt

- ☑ README.md (104 Z.), STATUS.md (73), `docs/subsystems/display.md` (53) - selbst geschrieben, Maßstab
- ☑ Wurzeldateien: FLASHING (91), BUILDING (86), PROVENANCE (61) - selbst geschrieben
- ☑ `docs/uboot/*`: README (Bootkette + Defconfig-Matrix), commands, environment, power-gate
- ☑ `docs/subsystems/*`: display, mips, cpu-comm, arisc, hdmi-in, pq, audio, video, crypto-engine,
  emmc-layout, wifi, focus-motor, board-mgr (13 Dateien, 45-83 Zeilen)
- ☑ `docs/tools/*`: h713-tv, -pq, -focus, -cam, -wifi, -extract, hy310-install, hy310-mkimage (8)
- ☑ `docs/{hardware,architecture,known-issues,dead-ends,kernel-patches}.md`
- ☑ **Drei Prüfläufe** (nur lesend, Berichte in `p5-entwuerfe/BEFUND-*.md`): Nutzersicht (13 Funde),
  Code gegen Doku (8 echte Abweichungen), Lücken und Widersprüche. Alles Substanzielle abgearbeitet -
  siehe Tabelle unten.
- ☑ Aus den Befunden **neu entstanden**: `RELEASES.md` (Versionsbegriffe), `ROADMAP.md`,
  `docs/services.md` (was auf dem Gerät läuft, inkl. Root-Autologin auf der seriellen Konsole),
  `docs/build-container.md`, `docs/tools/h713-fel.md`, `docs/usage/first-hour.md`
- ☑ Verweisprüfung: **99 interne Verweise, keiner tot**
- ☑ `repo-skelett.sh` neu gelaufen (12.09., 21:44): 830 Dateien, **Sperr-Scan ohne Funde**,
  `--dry-run` aus dem Klon läuft. Die deutsche `r2-extract/README.md` wird nicht mehr mitexportiert
  (Marco: zwei Beschreibungen desselben Werkzeugs verwirren)
- ☐ Marco liest README + FLASHING gegen

### Beim Gegenlesen gefunden (12.09., alles behoben)

| Fund | Woher |
|---|---|
| „cost three boards in one session" - im Journal steht „Boards ‚starben'" **in Anführungszeichen**, gemeint sind Hänger; die Hardware lebt | `arisc.md`, Quelle `doku/75` Läufe 103a-d |
| **Kein Notaus ist scharf**: `thermal_shutdown` ist Vorgabe *aus*, `0141` hat den Lüfterstillstands-Poweroff ausgebaut. `00-STATUS` klang nach vorhandenem Schutz | `board-mgr.md`; `doku/00-STATUS.md` und `STATUS.md` nachgezogen |
| Unser Brett ist **`HY260_QZ713_V3.1`, DDR3 792 MHz** (dritte Variante, vierfach belegt) - mein eigener README-Satz hatte cstengers `HY200_QZ713_V2`/LPDDR3 als unseres ausgegeben | `doku/10`, README + `hardware.md` |
| debugfs-Pfade (`cpu_comm/call`, `h713-arisc/`) ohne den Hinweis, dass `DEBUG_FS` im Release aus ist | `cpu-comm.md`, `arisc.md` |
| „Wi-Fi (AP and station)" in der Zusammenfassung, obwohl Station ungeprüft ist | `STATUS.md`, README |
| „upstream" für cstengers Baum (upstream heißt kernel.org) | `known-issues.md`, `dead-ends.md`, `kernel-patches.md`, `hardware.md` |
| **Root-Autologin auf der seriellen Konsole** war nirgends benannt - wer die UART-Pads erreicht, hat root | `services.md` neu, im Rundgang verlinkt |
| Elf Bildregler, nicht neun, und nicht alle 0-100: vier Vierstufen-Menüs, Video-Range 3, Bildmodus 14 | `hdmi-in.md`, am Treiber nachgezählt |
| Serie: Abschnitt 3 hat **17** cstenger-Patches, nicht 16 - der Zählfehler stand in der `series` selbst | `series`, `PROVENANCE`, `video.md` |
| `mainline/patches/README.md` behauptete 38 Patches und zwei Serien; es sind 133/7/3 plus zwei Nachbarverzeichnisse | Datei korrigiert |
| `--force` gibt es beim Installer nicht; `aic8800-0007` ist entgegen der Doku in der Serie; „six upstream" waren fünf; `ALLES GRUEN` gilt nur mit `--vendor` | vier Seiten |
| Vier Versionsnummern nebeneinander ohne Erklärung - der beste Stand trug die kleinste | `RELEASES.md` neu |
| Baucontainer war Voraussetzung ohne Rezept; serielle Konsole ohne Pins und Baudrate; kein Ausschalten, kein Update-Weg, keine Logs im Rundgang | `build-container.md` neu, `hardware.md`, `first-hour.md` |
| Deutsche Schalter in englischer Doku (`--trocken`, `--schritt`, Antworten `ok`/`fehler`) - benannt statt versteckt, Entscheidung aufs Todo | `h713-focus.md`, `h713-tv.md`, `61-todo` |
