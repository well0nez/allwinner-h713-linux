# Plan 120 — HY300 Pro: von „geht nicht" zu einem Test, den der Melder fahren kann

Nachfolger von [`119`](119-plan-fremdgeraete-und-installer-fixes.md) §A. Dort stand die Politik („fremde Geräte
sind community-getragen"), hier steht der Weg. Anlass: die Antwort auf Issue #1 endete ohne Auftrag — der
Melder wusste nach dem Lesen nicht, was er tun soll. Das ist der Fehler, den dieser Plan behebt.

Alle Werte unten sind belegt: aus seinem geposteten UART-Log, aus seiner `h713-extract`-Ausgabe oder aus
unserem eigenen Baum. Wo etwas unbekannt ist, steht das da.

## 1. Was das Gerät ist

| | HY310 (unseres) | HY200 QZ713DF_A1 (cstengers Bank) | **HY300 Pro (Melder)** |
|---|---|---|---|
| DRAM | DDR3, 1 GiB, **792 MHz** | DDR3, 1 GiB, **624 MHz** | DDR3, 1 GiB, **636 MHz** |
| DRAM-ZQ | `0x007b7bfb` | `0x007b7bfb` | **`0x7b7bfb`** (gleich) |
| Projekt-ID | 0x30 | **0x34** | **0x34** |
| Panel | 1920×1080, dual-port | **1280×720** | unbekannt (Stock rendert 1080p) |
| `display.bin` | 1 256 216 B, `16c74a28…` | 1 255 696 B, `4380f1b3…` | **1 253 136 B, `cf9649bc…`** |
| Layout | HY310, `Reserve0_a/_b` | — | Android A/B mit `super`, 25 Partitionen |
| Stock-Android | 11, 64 bit | — | 10, **32 bit** (ARMv7-Kernel 5.4.99) |

Belege für die HY300-Pro-Spalte: UART-Log im Issue-Rumpf Z. 127–133 (`DRAM CLK = 636 MHz`, `Type = 3`,
`ZQ 0x7b7bfb`, `SIZE = 1024 M`), Z. 206 (`Project id:0x34 version:24-5-7-19`), seine Extraktionsausgabe
(`boot/mips/display.bin: 1253136 B sha256 cf9649bc…`, GPT-Zeile mit 25 Einträgen).

**Zu cstenger:** sein Bank-Board ist ein **HY200_QZ713DF_A1**, kein HY300 (sein Repo:
„H713 (sun50iw12) SoC / HY200 board"; `mainline/README.md:20`). Für uns zählt aber nicht der Modellname,
sondern dass es ein **0x34-Board** ist — dieselbe Display-Projekt-ID wie das HY300 Pro. Und mehr noch:

- Unser **Installer-U-Boot benutzt bereits seinen Device Tree**:
  `CONFIG_DEFAULT_DEVICE_TREE="allwinner/sun50i-h713-hy200-qz713df-a1"`
  (`analyse/release/arbeit/r0-fel/patches/hy310_installer_defconfig:4`).
- Unsere DRAM-Werte sind **bis auf den Takt identisch** mit seinem Board. Heute nachgemessen:

  ```
  diff <(grep ^CONFIG_DRAM hy200_qz713df_a1_defconfig) <(grep ^CONFIG_DRAM hy310_felmmc_defconfig)
  1c1
  < CONFIG_DRAM_CLK=624
  ---
  > CONFIG_DRAM_CLK=792
  ```

  **Eine einzige Zeile.** Zwei unabhängige Boards teilen den kompletten Wertesatz; das HY300 Pro teilt
  DDR3, 1 GiB und denselben ZQ `0x7b7bfb`. Ein 636-MHz-Bau ist damit keine Raterei, sondern ein Einzeiler.
- Unsere Firmware-Tabelle hat **schon eine 0x34-Zeile** (`h713_mips.c:326`).

Das ist der eigentliche Hebel: das HY300 Pro liegt zwischen zwei Boards, die wir beide schon beschrieben haben.

## 2. Warum unser Release auf seinem Gerät nicht läuft — drei Tore

Nicht „vermutlich nicht", sondern nachweisbar. `h713_disp init 0x34` würde bei ihm dreimal scheitern, und
zwar bevor irgendetwas passiert:

| Tor | Code | Was passiert |
|---|---|---|
| 1. Größe | `h713_mips_load()`, `h713_mips.c:3625` | akzeptiert nur Größen, die eine Tabellenzeile nennt (`0x132910`, `0x132b18`). Seine: **`0x131f10`** → „rejected size" |
| 2. Identität | `h713_mips_verify()`, `h713_mips.c:3583` | vergleicht den SHA-256 gegen die Tabelle. Seiner ist unbekannt → „firmware identity rejected" |
| 3. HDCP-Warteschleife | `h713_mips_release_raw()`, `h713_mips.c:3770` | patcht eine **revisionsspezifische Adresse**; bei falscher Adresse Abbruch mit Meldung (immerhin: die Prüfung verhindert, dass wir fremde Firmware zerschreiben) |

Dazu ein vierter, stiller Fehler:

4. **Panel wird über die Projekt-ID gewählt** (`h713_board_by_project()`, `h713_mips.c:369`). Projekt 0x34
   liefert `h713_panel_cfg_board_b` — und das ist cstengers **1280×720**-Panel. Sein Gerät rendert im Stock
   1080p. Projekt-ID und Panel sind zwei verschiedene Dinge; unsere Tabelle wirft sie zusammen, weil bisher
   zwei Boards mit je einem Panel gereicht haben.

Genau deshalb nützt es nichts, ihm einfach eine Befehlsfolge zu schicken. **Erst muss unser Code ein drittes
Board überhaupt zulassen.** Das ist unsere Arbeit, nicht seine.

## 3. Was wir ändern (alles offline, ohne sein Gerät)

### 3.1 HDCP-Warteadresse suchen statt festnageln
Statt je Revision eine Konstante: im geladenen Abbild nach der Instruktion `sltiu v1,v1,0x33` (`0x2c630033`)
suchen. Gegenprobe an unserer eigenen `display.bin` heute gemacht:

```
Muster 0x2c630033: 2 Treffer — 0x3d0a4 (VA 0x4b13d0a4) und 0x61478 (VA 0x4b161478)
```

Der erste ist genau die für den HY310 festgenagelte Adresse. Die beiden lassen sich sauber trennen: nur im
±1-KiB-Fenster des richtigen Treffers stehen die Hälften der HDMI-RX-Pollingadresse `0x06840093`
(`0x0684` 1×, `0x0093` 2×; beim falschen Treffer 0× und 0×). Also: **suchen, per Kontext bestätigen, melden
was gefunden wurde**. Damit fällt `hdcp_wait_va` als Pflichtangabe je Board weg — und Tor 3 öffnet sich für
jede Revision.

### 3.2 Panel von der Projekt-ID entkoppeln
Das Panel gehört an die Digest-Zeile, nicht an die Projekt-ID. Für ein unbekanntes Board ohne Panelbeschreibung
darf kein Panel geraten werden — dann muss der Befehl sagen „ich kenne dein Panel nicht" statt still ein
720p-Panel auf 1080p-Hardware zu programmieren.

### 3.3 Eine dritte Tabellenzeile, aus seinen öffentlichen Daten
Alles außer dem Panel haben wir schon:

```
.board = "HY300 Pro", .project_id = 0x34, .panel = NULL /* unbekannt */,
.size = 0x131f10,
.digest = cf9649bcc84a111ce590fc7acde723c25557fd2332abbb9fd10225905aae13a2
```

Größe aus seinem eigenen Stock-Log (`size: 0x131f10`), Digest aus seiner Extraktionsausgabe. Beides sind
Hashes und Längen, keine Vendor-Inhalte — er hat sie selbst öffentlich gepostet.

### 3.4 Die Firmware-Tabelle steht an zwei Stellen
Nicht vergessen: dieselbe Tabelle gibt es ein zweites Mal im Extraktor —
`H713_MIPS_FW_REVS` (`analyse/release/arbeit/r2-extract/h713-extract:266`), mit `board`/`project_id`/`panel`/
`size`/`sha256`. Eine neue Revision muss in **beide**, sonst meldet der Extraktor weiter „keine bekannte
Revision" (`h713-extract:3072`) oder einen Board-Namens-Konflikt (`:2595`).

### 3.5 Erkennung und Extraktor-Profil (aus `119` §A1)
`h713-extract` hat **schon zwei Profile**: `hy310` und `l018` (`h713-extract:98`, `:143`) — L018 ist ein
H713-Beamer, den wir nie besessen haben, nur seine Firmware. Der Mechanismus für ein drittes Profil ist also
erprobt, und `hy300pro` ist kein Sonderfall.

Eine Falle dabei: `ex.kennung()` (`h713-extract:185`) greift **unbedingt** auf zehn Felder zu. Fehlt eines,
fliegt ein `KeyError` — und zwar im Installer bei `hy310-install.py:1549`, außerhalb des dortigen `try`.
Ein halb ausgefülltes Profil bricht die Erkennung also härter ab als gar keins. Entweder vollständig oder
`kennung()` muss tolerant werden.

Der Installer vergleicht ohnehin nur ein einziges Feld: `erwartung["build_fingerprint"]`
(`hy310-install.py:1549`). Für seine Erkennung reicht `ADT-3/…/6245789`.
Beides nur Erkennung — **kein Schreibweg**.

## 4. Der Test, der etwas beweist: ein Sonden-U-Boot für **unidentifizierte** Geräte

Entschieden (Marco, 14.09.): **kein Einzelstück für dieses eine Gerät, sondern ein Werkzeug.**
`u-boot-h713-probe.bin` — ein FEL-Startabbild für jedes unbekannte H713-Board. Es schreibt nichts und gibt
aus, was das Board ist: DRAM, GPT, `display.bin`-Größe und -Digest, Projekt-ID, gefundene HDCP-Stelle, Panel.
Also genau die Zeile, die danach in `h713_mips_fw_revs[]` und in `H713_MIPS_FW_REVS` eingetragen wird.

Das ändert den Zuschnitt: die Sonde muss ein **unbekanntes** Board vertragen, statt eines bekannten mit
falschen Werten. Konkret heißt das, die drei Tore aus §2 werden nicht für das HY300 Pro geöffnet, sondern
generell — unbekannte Größe und unbekannter Digest sind im Sondenmodus **kein Abbruch, sondern ein Befund**,
und die HDCP-Stelle wird gesucht (§3.1) statt nachgeschlagen. Das Panel bleibt der harte Fall: ohne
Beschreibung wird keines geraten (§3.2), die Sonde meldet nur, was sie sieht.

Der Melder startet sie über FEL, schaut zu, postet das UART-Log. Nichts wird geschrieben — FEL lädt in den RAM, `CONFIG_ENV_IS_NOWHERE` verhindert selbst ein
versehentliches `saveenv`, und der MIPS-Pfad enthält keinen einzigen Schreibaufruf (geprüft: kein
`blk_dwrite`/`fs_write`/`env_save` in `h713_mips.c`).

**`u-boot-hy300pro-probe.bin`** — abgeleitet vom Installer-U-Boot, mit:

| | |
|---|---|
| `CONFIG_DRAM_CLK` | **636** statt 792, sonst derselbe Wertesatz |
| Umgebung | `h713_mips_dev=1:2` (seine `bootloader_b`, dort liegt `mips/`), `h713_project=0x34` |
| `bootcmd` | `h713_disp init 0x34 elog=3` und dann **Prompt**, kein Booten |
| Rückweg | `ums 0 mmc 1` bleibt drin, damit er im selben Lauf noch einen Abzug ziehen kann |

Was ein Durchlauf beantwortet, in einem Rutsch:

1. **Hält sein RAM bei Vendor-Takt?** (Unsere 792 haben bei ihm schon 17 min unter Last getragen — das war
   der Abzugslauf. 636 ist der konservativere Wert.)
2. **Lädt unsere Kette seine Firmware?** Größe, Digest, TSE-Gruppe 0x34 aus seiner eigenen Partition.
3. **Findet die Suche seine HDCP-Warteadresse?** (§3.1)
4. **Kommt ein Bild?** Und wenn ja: richtig oder verzerrt — das sagt uns, ob `board_b` (720p) passt oder ob
   sein Panel wie unseres 1080p dual-port ist.
5. Der `elog=3` gibt die **firmwareeigene Logausgabe** aus — daher kommen die Paneldaten, die bei uns aus
   Laufzeitmitschnitten stammen (`re/captures/…`), nicht aus einer Datei, die er einfach aufmachen könnte.

### 4.1 Doch zwei Zahlen von ihm — Korrektur an mir selbst

Erster Gedanke war: „wir brauchen seine DRAM-Werte nicht, der Takt steht im Log". Beim Nachmessen an unserem
eigenen Vollabzug stimmt das nur zur Hälfte. Bei LBA 16 und LBA 256 steht je ein `eGON.BT0`, ab Offset `0x38`
der 24-Wort-Block. Abgleich mit unserem ausgelieferten defconfig:

| | aus dem boot0 | im defconfig | Herkunft |
|---|---|---|---|
| `tpr0`, `tpr1`, `tpr2` | `0x004a2195`, `0x02423190`, `0x0008b061` | `0x00482151`, `0x01b1a94c`, `0x0006e04d` | **gerechnet** aus dem Takt (cstengers generalisierter DDR3-Block) |
| `para2`, `tpr13` | `0`, `0x34010100` | `0x04000000`, `0xb4016103` | vom Flash-Werkzeug gepatcht |
| `zq`, `para1`, `mr0‑3`, `tpr3‑12` | — | **byteidentisch** | **direkt aus dem boot0** |

`tpr11`/`tpr12` sind also **keine gerechneten Werte, sondern boardspezifische PHY-Impedanzabstimmung** — und
genau die weichen beim echten HY300 (shift-Repo, `re/notes/H713_DRAM_REVERSE_ENGINEERING.md:72`) von unseren
ab: `0x44440000`/`0x00005555` statt `0x44340000`/`0x00006666`, bei 640 MHz.

Also **doch fragen**, aber gezielt: den 24-Wort-Block aus seinem eigenen Abzug, als Text. Das Rezept ist an
unserem Vollabzug getestet und reproduziert `doku/10`:

```
dd if=emmc-voll.img bs=512 skip=16 count=64 | <24 u32 ab Offset 0x38 ausgeben>
```

Das sind Zahlen aus einem Speichercontroller, kein Schlüsselmaterial und kein Vendor-Code.

*(Nebenbei: `doku/10-hardware.md:31‑33` sagt, die Tabelle dort stamme aus dem laufenden boot0. Das stimmt für
`tpr0/1/2`, aber `para2` und `tpr13` sind dort die defconfig-Werte. Gehört korrigiert.)*

### 4.2 636 MHz nimmt einen anderen Codepfad — und der ist nicht ungetestet

`dram_sun50iw12.c:657` verzweigt bei `para->clk > 672`. Unsere 792 gehen in den `if`-Zweig, **636 in den
`else`-Zweig** — einen Pfad, den unser Gerät nie gefahren ist. Entwarnung: cstengers Bank-Board läuft mit
**624 MHz**, also täglich auf genau diesem Zweig. Der Timing-Block selbst ist über einen 30-Punkt-Sweep
312–1200 MHz generalisiert (`dram_sun50iw12.c:423`), die Speed-Bin-Grenze liegt bei 800 MHz (`:437`) — 624,
636 und 640 liegen alle im selben Bin.

Und ein dritter, unabhängiger Datenpunkt: das echte HY300 (shift) fährt **640 MHz**. Die HY300-Familie liegt
also wirklich bei 636–640, nicht in der Nähe unserer 792.

**Physisches Risiko:** PB5 schaltet Lüfter und Lampe gemeinsam
(`CONFIG_H713_POWERON_LIGHT_FAN`, `board/sunxi/board.c:988`) — das lief bei seinem 17-Minuten-Abzug schon.
Der Sondenlauf fügt nur LVDS/TCON/MIPS hinzu, keine neue Wärmequelle. Trotzdem sagen wir ihm: nicht
unbeaufsichtigt laufen lassen, danach Strom weg.

## 4a. Für Stufe 5: cstengers Weg ist für ein fremdes Gerät der bessere

Ein Unterschied, der bisher nirgends als Entscheidung notiert war: **cstenger partitioniert nicht um.** Er
behält die Werks-GPT (26 Einträge) und quartiert sich in Nischen ein — U-Boot proper in die Stock-Partition
`empty` bei LBA 4 828 160, Environment bei Byte-Offset `0x93d80000`, Rootfs in `UDISK`, Display-Artefakte in
der Vendor-FAT `bootloader_b`. Wir dagegen legen mit Layout v3 eine eigene GPT an.

Für **unser** Gerät ist unser Weg richtig — wir haben es vermessen und einen Vollabzug. Für ein **fremdes**
Gerät ist seiner deutlich besser:

- Android bleibt vollständig stehen, der Rückweg ist nicht „Abzug zurückspielen", sondern „unsere Nischen
  wieder freiräumen".
- Es hängt **nicht** an Fix B2 und nicht daran, dass wir sein Layout korrekt nachbauen — wir müssen sein
  Layout gar nicht anfassen.
- `hy310-mkimage` mit seinen 43 gemessenen Platzhaltern und `DISK_SEKTOREN=15269888` entfällt komplett.

Sein Layout hat die Nischen, die cstenger benutzt, allerdings anders: `Reserve0` einfach statt `_a`/`_b`,
`media_data` mit 208 MiB, und ob es bei ihm eine `empty`-Partition gibt, steht in seiner GPT — ja:
`empty@4828160+30720`, **derselbe LBA wie bei cstenger**. Das ist kein Zufall, sondern dasselbe
Allwinner-Referenzlayout.

**Entschieden (Marco, 14.09.): nein — es bleibt bei unserem Layout.** Sein Argument: wer in diesen Baum
aufgenommen wird, spielt nach den Regeln dieses Baums, nicht umgekehrt. Ein Layout heißt ein Installer, ein
`mkimage`, ein Rückweg, eine Doku. Zwei Layouts hieße alles davon doppelt — dauerhaft, für ein Gerät, das
niemand hier hat.

Was das kostet, damit es notiert ist: **B2 wird damit Pflicht** (GPT statt Konstanten), `hy310-mkimage` muss
`DISK_SEKTOREN` und die 43 Platzhalter aus dem jeweiligen Gerät nehmen statt aus HY310-Messwerten, und der
Rückweg bleibt „Vollabzug zurückspielen". Alles machbar, aber es gehört vor Stufe 5, nicht mittendrin.

## 4b. Gebaut (14.09.) — vier Commits im Fork, Gerätetest steht aus

| Commit | Was |
|---|---|
| `1e9daac` | Panel aus der **Identität** statt aus der Projekt-ID; Identifikation nach vorn in `h713_disp_load()`; die zwei doppelten Größenprüfungen zu `h713_mips_accept_size()` zusammengelegt |
| `80397f0` | HDCP-Wartestelle **suchen** statt festnageln (§3.1); die Tabellenwerte sind jetzt Gegenprobe |
| `fcc147d` | `h713_probe` + `h713_probe_defconfig` (624 MHz) |
| `218792f` | Die deklarierte Projekt-ID gehört dem Board: `H713_DISP_BOARD_PROJECT_ID` raus |

Der letzte war ein Nebenfund mit echtem Fehler: die Konstante stand auf `0x34` (Bank-Board) und der Hinweis
dahinter feuerte bei **jedem HY310-Start** — unser bootcmd fährt `0x30` — mit „this board declares project
0x34 (panel_config.ini ProjectID = 52)". Unsere `panel_config.ini` sagt 48. Die Meldung war auf dem Board
falsch, auf dem sie gedruckt wurde. Jetzt kommt sie aus der Tabellenzeile, oder gar nicht.

Beides gebaut: Auslieferungs-defconfig und `h713_probe_defconfig`, je 957 bzw. 965 KiB, ohne neue Warnungen.

**Was noch fehlt, und ohne das geht nichts raus:**
1. Sonde per FEL auf **unserem** Gerät — sie muss „HY310 (QZ713 V3.1)", Panel 1920×1080, Projekt 0x30,
   HDCP-Stelle `0x4b13d0a4` und im boot0-Block `dram_clk 0x318` (792) melden. Das ist die Gegenprobe gegen
   bekannte Wahrheit, inklusive des 624-MHz-Takts auf einem 792-MHz-Board.
2. Rückfallprüfung: das **Auslieferungs**-U-Boot muss unverändert booten und ein Bild zeigen (die
   Panelauswahl und die HDCP-Suche liegen im normalen Pfad).

Erst danach: Fork pushen, Submodul-Pin nachziehen, Sperr-Scan, `repo-neu` pushen.
(`repo-neu` hat den Commit `933b292` schon **lokal**; nichts davon ist draußen.)

### Der Gerätetest, Schritt für Schritt

Vorbereitet, damit er ohne Nachdenken läuft, sobald das Gerät frei ist. Kostet **zwei** Einschaltvorgänge.

| | Was | Wer |
|---|---|---|
| 0 | UART-Adapter und A-auf-A-Kabel stecken. **Achtung:** mit gestecktem FEL-Kabel startet die Steckdose nicht neu — erst Kabel ziehen, dann schalten | Marco |
| 1 | Reset halten + Strom → FEL. `lsusb` muss `1f3a:efe8` zeigen | Marco |
| 2 | `sunxi-fel uboot mainline/build/uboot-probe/u-boot-sunxi-with-spl.bin`, UART mitschneiden | ich |
| 3 | Erwartet: `HY310 (QZ713 V3.1)`, Panel 1920×1080, Projekt 0x30, HDCP-Stelle `0x4b13d0a4`, `dram_clk 0x318` (792) — und zwar auf einem U-Boot, das mit **624** trainiert hat | ich |
| 4 | Strom weg, Kabel ziehen, normal einschalten (Taste) → Auslieferungs-U-Boot muss booten und ein Bild zeigen | Marco + ich |

Schritt 3 prüft vier Dinge auf einmal: dass die Sonde auf bekannter Wahrheit die Wahrheit sagt, dass die
HDCP-Suche denselben Wert findet wie die festgenagelte Adresse, dass 624 auf einem 792-MHz-Board trainiert
(also das konservative Ende wirklich konservativ ist), und dass der boot0-Block an Offset `0x38` auf dem
Gerät dasselbe liefert wie am Abzug.

Schritt 4 ist die Rückfallprüfung: Panelauswahl und HDCP-Suche liegen im **normalen** Pfad, nicht nur im
Sondenpfad. Wenn dort etwas kaputt wäre, bliebe das Bild schwarz.

## 4c. Am Gerät, 14.09.

**Sonde auf unserem HY310 (Layout v3), per FEL:**
- SPL trainiert mit **624 MHz** auf dem 792-MHz-Board.
- Display bestätigt: Digest `16c74a28…`, Identität `HY310 (QZ713 V3.1)`, **HDCP-Stelle per Suche `0x4b13d0a4`** — genau
  der festgenagelte Wert —, Panel 1920×1080, Projekt 0x30. Die Firmware trägt 15 Projekt-Deskriptoren (auch 0x36/0x37).
- Zwei Fehler der Sonde gefunden und behoben (`a9c6304`): bei LBA 16 liegt auf unserem Layout **unser SPL** (auch
  `eGON.BT0`, erkennbar an `SPL` bei `0x14`) — die Sonde hatte dessen DT-Namen als DRAM-Werte gedruckt; LBA 256 ist
  leer (so geplant, `109` Z. 123). Und `hy310-boot` fehlte in der Kandidatenliste.
- `run fel` fehlte in der Sonde, weil nur drei Builds `hy310.env` laden → jetzt für jeden H713-Build in
  `sunxi-common.h` (`359e96c`), am Gerät bestätigt.
- Stock-Pfade gegen den Stock-Vollabzug geprüft: `1:2`=`bootloader_b` FAT16 mit `display.bin` `16c74a28…`, `1:1`
  dieselbe; boot0 an LBA 16 und 256 mit Kopfgröße `0x30` bei `0x14`, clk 792 / Typ 3.

**Vorfall: `hy310_felmmc_defconfig` ist kein Testbuild.** Als „Rückfalltest ohne Flashen" geladen, nach dem Namen
geraten. Er setzt `CONFIG_H713_SPL_FORCE_MMC`: der SPL schreibt `h713_spl_payload.h` — ein altes **Vendor-boot0** —
nach LBA 16–79 und hält an. Lief zweimal; danach startete Vendor-BOOT0 und scheiterte an `Loading boot-pkg`.
Repariert über den Release-Installer: 64 Sektoren aus dem v0.5-beta-Abbild zurück, Rücklesen identisch, Teil A
(LBA 0–12287) danach byte-gleich zum Release, beide Dateisysteme ohne Fehler. Secure Storage war nie im Schreibbereich.
Die zwischendurch notierte Vermutung „Uploads nach `run fel` brechen ab" war falsch — das war dieser SPL, der nach
dem Schreiben nicht zurückkehrt. **Offen:** ein Build, der per FEL startet und dann vom eMMC bootet, ohne zu
schreiben — für den Rückfalltest des normalen Pfads.

**Danach:** Stock frisch aus `update.img` (erprobter P6-Weg), Sonde auf echtem Stock.

## 5. Reihenfolge

| | Wer | Was | Risiko |
|---|---|---|---|
| 1 | wir | §3.1–3.3 im U-Boot-Fork; Gegenprobe **an unserem Gerät** (HY310 muss unverändert booten) | keins für ihn |
| 2 | wir | `u-boot-hy300pro-probe.bin` bauen, Prüfsumme, kurze Anleitung | keins |
| 3 | **er** | FEL-Start, zuschauen, UART-Log posten, sagen ob ein Bild kommt | schreibt nichts |
| 4 | wir | aus seinem Log: Panel eintragen, ggf. DRAM nachziehen, Erkennung + Extraktorprofil | keins |
| 5 | **er** | erst dann: `--dry-run`, dann echtes Schreiben, `--restore` als Rückweg | echtes Risiko, mit Netz |

Schritt 1 ist die Bedingung für alles Weitere und **darf nicht übersprungen werden**: ohne ihn scheitert sein
Lauf an Tor 1, und wir hätten ihm wieder eine Aufgabe gegeben, die nicht funktionieren kann.

## 6. Nebenbefund: stale Hilfetext im veröffentlichten Fork

`h713_mips.c:11315` sagt „this board's project ID is 0x34" — das gilt für cstengers Bank-Board, nicht für den
HY310 (dessen `panel_config.ini` sagt `ProjectID = 48` = 0x30, `re/vendor/HY310/…/panel_config.ini`). Der Satz
steht so im veröffentlichten `well0nez/u-boot`. Beim nächsten Anfassen der Datei mitkorrigieren.

## 7. B2 ist kleiner als gedacht

Der kleine Abzug nimmt seine Offsets aus der Modulkonstante `EINMALIG` (`hy310-install.py:96‑99`) —
`private` bei LBA 4891648, `reserve0-a/-b` bei 5489664/5522432, alles aus der **HY310**-Stock-GPT.

Der Leser, der es besser wüsste, läuft aber schon: in `geraet_erkennen()` steht bei
`hy310-install.py:1513` bereits ein `ex.Gpt(q, stumm)`, und dessen `parts` ist
`{Partitionsname: (start_lba, sektoren)}`. Benutzt wird davon bisher nur `super`. Der eigene Mini-Leser
`ist_unser_geraet()` (`:347`) sammelt sogar über alle Einträge, wirft aber Start und Größe weg und behält
nur die Namen.

Also: `abzug_klein()` die `gpt.parts` durchreichen und `private`/`Reserve0` **nach Namen** suchen; nur der
Secure Storage bei LBA 12288 bleibt eine Konstante, weil er außerhalb jeder Partition liegt. Gegenprobe:
unser eigener kleiner Abzug muss danach byteidentisch bleiben. Beim HY300 Pro hieße `Reserve0` dann einmal
`Reserve0@5358592+32768` statt zweimal falsch.

Das ist Voraussetzung für Stufe 5 in §5, nicht für den Sondenlauf.
