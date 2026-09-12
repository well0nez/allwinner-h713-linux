# S47 — Der Abbild-Bauer

**Auftrag:** das letzte fehlende Stück im Installationsweg bauen — ein Werkzeug, das aus den vorhandenen Bausteinen eine
einspielbare Abbild-Datei erzeugt, mit Offsettabelle für die proprietären Platzhalter. Befund **B6** aus
[`S46`](S46-kritische-pruefung.md) („Es gibt kein Abbild, keinen Abbild-Bauer und keine Offsettabelle") und **B7**
(Backup-GPT am Plattenende) schließen.

**Regeln eingehalten:** geschrieben wurde nur in `analyse/release/arbeit/r0-fel/` und in diesen Bericht. Kein Netz, keine
Git-Operationen, keine Agenten. **Am Gerät nur gelesen** — die drei `dd` in diesem Bericht sind alle `if=/dev/sda`, es gibt
kein einziges `of=`. Gebaut wurde im Container `h713-build`, nichts auf dem Host.
**Stand:** 10.09.2026, nach `S46`.

**Die drei Sätze vorab:**

1. **Das Abbild hat ein Loch, und das ist der Kern der Sache.** Es kommt in **drei Stücken**, und der Secure Storage
   (LBA 12288…14335) steht in keinem davon. Ein `dd` von Hand kann ihn damit gar nicht treffen — auch ohne die Sperre des
   Installers (§3).
2. **Ein eigener ext4-Schreiber war nicht nötig.** Die beiden Dateisysteme entstehen einmal bei uns mit `mke2fs`; das
   verteilte Werkzeug **findet** die Platzhalter nur noch, mit dem ext4-Leser aus `hy310-extract` (§4).
3. **Der Weg läuft von Anfang bis Ende durch.** Abbild bauen → 30 Platzhalter mit den echten Vendor-Dateien füllen →
   auf eine Attrappe schreiben → über das Dateisystem zurücklesen: **30/30 byteidentisch, `e2fsck` sauber, Secure Storage
   unverändert** (§7).

---

## 1. Was jetzt liegt

| Datei | Größe | was sie ist |
|---|---|---|
| `r0-fel/hy310-mkimage.py` | 42 KB | **der Abbild-Bauer.** Python 3.9+, reine Standardbibliothek, keine externen Programme |
| `r0-fel/mkimage-eingaben.sh` | 3 KB | der eine Schritt, der `e2fsprogs` braucht — läuft **im Container**, einmal, bei uns |
| `r0-fel/mkimage-selbsttest.py` | 9 KB | der ganze Weg ohne Gerät, gegen eine Attrappe |
| `r0-fel/hy310-install.py` | 52 KB | erweitert: `--abbild` nimmt jetzt die Tabelle, `platzhalter_fuellen()` wird aufgerufen (§6) |
| `r0-fel/out/…` | **1,22 GB** | das fertige Abbild v0.1, drei Teile plus Tabelle, Prüfsummen, Liesmich |

Das Ergebnis in `r0-fel/out/`:

| Datei | Byte | ab LBA | sha256 |
|---|---:|---:|---|
| `hy310-v0.1-a-bootkette.img` | 6.291.456 | 0 | `eed86f60a4a330b7…` |
| `hy310-v0.1-b-system.img` | 1.209.008.128 | 14336 | `d0ca036122e924f4…` |
| `hy310-v0.1-c-gptkopie.img` | 16.896 | 15269855 | `e085b68113e5b939…` |
| `hy310-v0.1.tabelle.json` | 13.409 | — | `2814056bfaa6cfd2…` |
| `hy310-v0.1.sha256`, `hy310-v0.1-LIESMICH.txt` | 365 / 4.236 | — | — |

**Zusammen 1.215.316.480 Byte = 1159 MiB = 1,22 GB.** Plan [`110`](../110-plan-installationsweg.md) §7 rechnet mit
1,2 GB und rund 2,6 Minuten bei 7,7 MB/s — das trifft zu (2,63 min gerechnet).

Bauzeit auf dem Host: **2,8 Sekunden** (die beiden ext4 sind da schon fertig).

---

## 2. Der Aufbau

Nach [`109`](../109-plan-layout-v3.md) §2.1/§2.2, ohne Abweichung:

| LBA | Sektoren | Inhalt | in Teil |
|---:|---:|---|---|
| 0 | 1 | Schutz-MBR | A |
| 1 | 1 | GPT-Kopf | A |
| 2…8 | 7 | Tabelle, 26 Einträge à 128 B, `FirstUsableLBA` = 16 | A |
| 16 | 64 | SPL, `tftp/spl-v3layout.bin`, 32.768 B, Kennung `eGON.BT0` geprüft | A |
| 2048 | 10240 | U-Boot proper, `tftp/uboot-proper-v3layout.bin`, 886.089 B | A |
| **12288** | **2048** | **Secure Storage — in keinem Teil** | **—** |
| 14336 | 2048 | `hy310-env`, **leer** (U-Boot legt sie beim ersten `saveenv` an) | B |
| 16384 | 262144 | `hy310-boot`, ext4, 134.217.728 B | B |
| 278528 | 2097152 | `hy310-rootfs`, ext4, 1 GiB (wächst per `x-systemd.growfs`) | B |
| 15269855…15269887 | 33 | Sicherungstabelle + Sicherungskopf (Befund **B7**) | C |

Teil A endet exakt bei 6 MiB, Teil B beginnt exakt bei 7 MiB (LBA 14336 · 512 = 7.340.032). Das ist kein Zufall, sondern
die Stelle, an der der gesperrte 1-MiB-Block endet — und es macht den Handbefehl einfach:

```
dd if=hy310-v0.1-a-bootkette.img of=/dev/sdX bs=512 seek=0          conv=fsync
dd if=hy310-v0.1-b-system.img    of=/dev/sdX bs=512 seek=14336      conv=fsync   # = bs=1M seek=7
dd if=hy310-v0.1-c-gptkopie.img  of=/dev/sdX bs=512 seek=15269855   conv=fsync
```

**Die Partitionstabelle ist byteweise die des laufenden Geräts.** Gegenprobe gegen `/dev/sda` (nur gelesen, 10.09.):

```
LBA 0 gleich   LBA 1 gleich   LBA 2 gleich   LBA 3 gleich   LBA 4 gleich
LBA 5 gleich   LBA 6 gleich   LBA 7 gleich   LBA 8 gleich
```

Alle neun Sektoren identisch — Schutz-MBR, Kopf und die 26 Einträge. Damit ist die Byte-Genauigkeit, an der
`--restore-stock` in `S46` §B3 gescheitert war, für **unsere** Tabelle belegt und nicht behauptet. Die GUIDs
(`DiskGUID ab6f3888-…`, sechs Unique-GUIDs) sind am Gerät abgelesen und im Werkzeug festgeschrieben, damit jedes gebaute
Abbild dieselbe, nachweislich bootende Tabelle trägt.

**Nebenbefund am Gerät:** die Sicherungskopie am Plattenende ist unvollständig aufgeräumt. Bei
LBA 15269855…15269861 stehen noch **Reste der alten Android-Sicherungstabelle** (Typ-GUID `ebd0a0a2-…`), die der Umbau vom
10.09. nicht überschrieben hat. Unser Teil C deckt alle 33 Sektoren ab und nullt sie mit — der Zustand, den `S46` §B7 als
Einladung zur falschen Reparatur beschreibt, entsteht mit diesem Abbild nicht mehr.

---

## 3. Die Entscheidung: das Loch, und warum drei Dateien

**Frage:** ein durchgehendes Abbild mit einem markierten Loch, das `hy310-install` überspringt — oder ein Abbild, das den
Bereich gar nicht enthält?

**Entschieden: das Abbild enthält den Bereich nicht.** Drei Stücke, `dd` mit `seek`.

**Begründung.** Die Sperre in `Platte.schreib()` schützt nur, wer `hy310-install` benutzt. Plan `110` §7 stellt aber
ausdrücklich in Aussicht, dass der Nutzer die Datei „schlicht mit `dd`" schreibt, „wie bei einem Einplatinenrechner".
Genau dieser Nutzer hat keine Sperre. Ein durchgehendes Abbild würde bei ihm 1 MiB Nullen über LBA 12288…14335 legen, und
damit über die HDCP-Schlüssel, die WLAN- und Bluetooth-MAC-Adressen und die Seriennummer — **gerätespezifisch, in keinem
Firmware-Abbild, nicht wiederherstellbar** ([`109`](../109-plan-layout-v3.md) §2.3).

Nachgerechnet, nicht angenommen:

```
durchgehendes Abbild, dd von Hand:
  vorher  faff69592ef56083b1300091431537cb
  nachher 30e14955ebf1352266dc2ff8067e6810
  -> SECURE STORAGE WEG
```

Die Fehlerfälle im Vergleich:

| Fehler des Nutzers | durchgehende Datei | drei Teile |
|---|---|---|
| nichts falsch gemacht, `dd` von Hand | **Schlüssel weg** | in Ordnung |
| einen Befehl vergessen | — | Gerät startet nicht, Schlüssel unversehrt, wiederholbar |
| `seek` falsch getippt | — | kann treffen, verlangt aber einen aktiven Fehlgriff |
| `hy310-install` benutzt | in Ordnung (Sperre) | in Ordnung (Sperre **und** Loch) |

**Der schlimmste Fall der durchgehenden Datei ist der Normalfall, der schlimmste Fall der drei Teile verlangt einen
Tippfehler.** Das entscheidet. Es ist außerdem dieselbe Logik wie in `109` §2.4: ein Bereich, den nur unsere Doku schützt,
ist nicht geschützt — hier ist er dadurch geschützt, dass es die Bytes gar nicht gibt.

**Der Preis** ist ein Befehl mehr in der Anleitung und ein `--abbild`, das kein einzelnes `.img` mehr ist, sondern die
Tabelle. Beides ist in der Liesmich beschrieben und im Installer angeschlossen (§6). Der Vorteil obendrein: Teil C
existiert überhaupt nur, weil das Abbild ohnehin nicht durchgehend ist — die Sicherungs-GPT am Plattenende (B7) fällt
damit als eigenes Problem weg statt als Sonderfall behandelt zu werden.

**Doppelt abgesichert.** Der Bauer bricht ab, wenn irgendein Teil den Bereich berührt (§7, Schritt 6 des Bauens), der
Prüfmodus prüft es erneut, und `hy310-install` vergleicht nach dem Schreiben den Bereich byteweise gegen den kleinen
Abzug, der ohnehin Pflicht ist.

---

## 4. Wie das ext4 entsteht — und wie die Offsets gefunden werden

**Ein eigener ext4-Schreiber wäre der schwierigste Teil gewesen. Er wird nicht gebraucht.** Der Weg, der im Auftrag als
„vermutlich klüger" vorgeschlagen war, hält:

| Schritt | wer | womit |
|---|---|---|
| Dateibaum mit Platzhaltern schreiben | `hy310-mkimage --baum-boot` / `--baum-rootfs` | reine Standardbibliothek |
| ext4 daraus bauen | `mkimage-eingaben.sh` **im Container** | `mke2fs -d`, `e2fsck -fn` |
| Offsets der Platzhalter **finden** | `hy310-mkimage --out` | ext4-**Leser** aus `hy310-extract` (`class Ext4`, Extents) |
| Platzhalter füllen | `hy310-install` beim Nutzer | nur `seek` + `write` |

`mke2fs` läuft damit **einmal bei uns**, nie beim Nutzer. Was verteilt wird, sind zwei gewöhnliche Dateien — ab da sind
sie Bausteine wie die SPL oder das U-Boot-Abbild.

**`hy310-boot`** entsteht neu: `h713-kernel.fit` (echt, 7.987.476 B, aus `tftp/h713-kernel-zram.fit` — der Stand mit
zram, `109` §10) plus `mips/` mit 19 Platzhaltern.

**`hy310-rootfs`** entsteht aus `rootfs/out/hy310-rootfs.tar` (dem abgenommenen Baum aus [`107`](../107-plan-rootfs.md) §9)
**plus** elf Platzhaltern, mit denselben `mke2fs`-Optionen wie in `build-rootfs.sh` (`-t ext4 -L hy310-rootfs -m 1 -E
lazy_itable_init=0,lazy_journal_init=0 -d`). Nicht aus dem fertigen `hy310-rootfs.ext4`: die elf Dateien müssen als
richtige Dateien mit richtiger Größe im Dateisystem stehen, und das kann `mke2fs -d` in einem Zug. Der Baum wächst dadurch
von 233.852 auf **234.700 KiB** — 848 KiB, genau die Summe der elf Platzhalter.

**Das Finden der Offsets** geht über `Ext4._karte(ino, inode)`: Liste `(logischer Block, Anzahl, physischer Block)`.
Daraus wird `physischer Block · Blockgröße`. Drei Bedingungen werden **geprüft, nicht angenommen**:

1. **Die Datei liegt am Stück.** Ein einzelnes `(Offset, Länge)` ist sonst falsch. Bei Fragmentierung bricht der Bauer ab.
2. **Kein Loch** — weder am Anfang noch am Ende. Deshalb ist das Füllmuster auch kein Nullblock (§5): für lauter Nullen
   legt `mke2fs` unter Umständen gar keine Blöcke an, und dann gäbe es nichts zu beschreiben.
3. **Gegenprobe.** Jede Datei wird einmal über den ext4-Leser und einmal roh am errechneten Offset gelesen und verglichen.

Alle 30 Dateien liegen am Stück (Blockgröße 4096). Der größte Platzhalter ist `display.bin` mit 1.256.216 B = 307 Blöcken,
weit unter der Extent-Grenze von 32.768 Blöcken.

---

## 5. Die Offsettabelle

Das Format ist **genau das, was `platzhalter_fuellen()` erwartet** — `name -> (byte_offset, laenge)`, direkt als
2-elementige Liste, damit `off, laenge = tabelle[name]` ohne Umbau funktioniert:

```json
"platzhalter_datei": "hy310-v0.1-b-system.img",
"platzhalter": {
  "boot/mips/display.bin":       [35020800, 1256216],
  "lib/firmware/hy310-edid.bin": [258478080, 512],
  "pq/tvpq.db":                  [153718784, 36864]
}
```

Die Offsets sind relativ zu **einer** Datei (`platzhalter_datei`), weil `platzhalter_fuellen()` genau eine Datei öffnet.
Die reicheren Angaben stehen daneben in `platzhalter_info` und stören das erwartete Format nicht:

| Feld | wozu |
|---|---|
| `ziel` | `hy310-boot:/mips/display.bin` — wo die Datei im fertigen System landet |
| `lba`, `disk_offset` | dieselbe Stelle als Sektor bzw. Byte auf der eMMC (für Fehlersuche und Prüfung) |
| `sha256_muster` | Prüfsumme des **unbefüllten** Platzhalters — daran erkennt der Prüfmodus, ob schon gefüllt wurde |

**Die Namen sind die Ausgabepfade von `hy310-extract`.** `boot/mips/display.bin`, `lib/firmware/h713-arisc.bin`,
`pq/tvpq.db` — dadurch ist das Zusammenführen ein Zusammensetzen von Pfaden und keine Zuordnungstabelle, die auseinander
laufen könnte. Gegenprobe gelaufen: die 30 Namen decken das Verzeichnis `r2-extract/out-hy310` **vollständig und ohne
Rest** ab, und alle 30 Größen stimmen auf das Byte.

**30 Platzhalter, zusammen 2.806.825 Byte:**

| Gruppe | Anzahl | Ziel |
|---|---:|---|
| Anzeige-Artefakte (`mips/`) | 19 | `hy310-boot:/mips/` |
| Firmware (ARISC, EDID, MSP-Patch) | 3 | `hy310-rootfs:/lib/firmware/` |
| PQ-Dateien | 8 | `hy310-rootfs:/etc/hy310/tvconfig/` |

Das Füllmuster ist lesbarer Text (`HY310-PLATZHALTER boot/mips/display.bin -- hy310-install fuellt das. …`, wiederholt).
Zwei Gründe: im Hexdump sieht man sofort, dass und welche Datei noch offen ist, und es garantiert echte Blöcke (§4).

Daneben liegen im JSON: die sechs Partitionen mit GUIDs, das Loch mit Begründung im Klartext, die drei Teile mit
Prüfsummen und fertigem `dd`-Befehl, und die vier Bausteine (SPL, U-Boot, beide ext4) mit ihren Prüfsummen — damit später
nachvollziehbar ist, woraus ein Abbild gebaut wurde.

---

## 6. Was am Installer geändert wurde (B6, B7)

`platzhalter_fuellen()` und `platzhalter_pruefen()` waren toter Code, `--tabelle` wurde nie gelesen. Das ist behoben:

| Was | vorher | jetzt |
|---|---|---|
| `--abbild` | eine `.img`-Datei ab LBA 0 | **die `*.tabelle.json`**, das Verzeichnis darum, oder weiterhin eine einzelne Datei |
| `--tabelle` | deklariert, nie gelesen | wird gelesen; eine Einzeldatei plus Tabelle geht denselben Weg |
| `--vendor VERZ` | — | **neu**: fertige Ausgabe von `hy310-extract` |
| `--arbeitskopie` | — | **neu**: wohin die gefüllte Kopie geht (Vorgabe `<sicherung>/abbild-gefuellt.img`) |
| `abbild_schreiben` | schrieb immer ab LBA 0 | `lba0=` — ein Abzug ist ein Stück ab 0, unser Abbild sind drei Stücke |
| `pruefe_abbild` | dito | dito |
| Extraktion (Plan 110 §1 Schritt 4) | fehlte | `extrahieren()` ruft `hy310-extract` auf den Vollabzug auf |

Der neue Ablauf `_paket_schreiben()` hält die Reihenfolge ein, die im Docstring von `platzhalter_fuellen` begründet steht:
**erst am PC fertig machen, dann einmal schreiben.**

1. Teile prüfen: Größe **und** sha256, bevor irgendetwas geschrieben wird. Dazu der Abgleich, dass das Loch der Tabelle
   und `SPERRE_ERSTER/LETZTER` dasselbe meinen und die Sektorzahl passt — eine Tabelle aus einer anderen Welt fliegt hier
   raus.
2. Vendor-Dateien besorgen: `--vendor`, sonst Extraktion aus dem Vollabzug. Fehlt beides, **bricht es ab** mit dem Satz,
   dass die 30 Dateien nur auf dem eigenen Gerät stehen.
3. Arbeitskopie von Teil B anlegen, füllen, zurücklesen. Das verteilte Abbild bleibt unangetastet — es enthält danach
   Vendor-Material und gehört nicht weitergegeben.
4. Getippte Bestätigung (`bestaetigen()`, unverändert), dann alle drei Teile an ihre Sektoren.
5. Stichproben je Teil, und zum Schluss der **Secure Storage byteweise gegen `secure-storage.bin` aus dem kleinen Abzug**.
   Weicht er ab, bricht es mit Rückgabe 10 und der Bitte, nichts weiter zu tun.

**Was bewusst nicht geändert wurde:** die Sperre selbst, `bestaetigen()`, die Abzugswege, `stock_zurueck`. `S46` hat sie
durchgerechnet; hier war kein Anlass, sie anzufassen.

---

## 7. Testläufe

Alles gegen **Dateien**, nichts gegen das Gerät. Am Gerät wurde ausschließlich gelesen.

### 7.1 Bauen

```
[2] Teil A -- Boot-Kette (LBA 0..12287)      6291456 Byte (6 MiB)
[3] Teil C -- Sicherungskopie (LBA 15269855, 33 Sektoren)   16896 Byte
    GPT nachgerechnet: CRCs, FirstUsable 16, 26 Eintraege, sechs Partitionen, Sicherungskopie stimmt
[4] Teil B -- System (LBA 14336 ...)      1209008128 Byte (1153 MiB)
[5] hy310-boot.ext4    Blockgroesse 4096, 19 Datei(en) am Stueck, Gegenprobe gleich
    hy310-rootfs-platz.ext4 Blockgroesse 4096, 11 Datei(en) am Stueck, Gegenprobe gleich
    30 Platzhalter, zusammen 2806825 Byte
    alle 30 Offsets in Teil B gegengeprueft
[6] kein Teil beruehrt LBA 12288..14335
```

**2,8 s** auf dem Host.

### 7.2 Prüfmodus

`hy310-mkimage.py --pruefen out/hy310-v0.1.tabelle.json` → Rückgabe 0:

| Prüfung | Ergebnis |
|---|---|
| drei Teile: Größe und sha256 | stimmen |
| kein Teil berührt LBA 12288…14335 | bestätigt |
| GPT: CRCs, `FirstUsableLBA` 16, 26 Einträge, sechs Partitionen | stimmen |
| Sicherungskopie am Plattenende vorhanden und gleich | ja (**B7 erledigt**) |
| 30 Platzhalter | 30 unbefüllt (Muster steht), 0 gefüllt |

Wird ein Abbild geprüft, dessen Platzhalter schon gefüllt sind, sagt der Prüfmodus das und warnt, dass diese Datei
Geräte-Daten trägt und nicht weitergegeben gehört.

### 7.3 Der ganze Weg ohne Gerät (`mkimage-selbsttest.py`)

| # | Schritt | Ergebnis |
|---|---|---|
| 1 | Sperre und Sektorzahl in `hy310-install` gegen die Tabelle | 12288…14335, 15269888 — gleich |
| 2 | `platzhalter_fuellen()` mit den **echten** Vendor-Dateien | 30 Dateien in **0,54 s**; `platzhalter_pruefen`: alle 30 stimmen |
| 3 | Gegenprobe **über das Dateisystem**, nicht am Rohoffset | 30/30 byteidentisch zur Quelle |
| 3b | `h713-kernel.fit` unverändert | 7.987.476 B, Kennung `d00dfeed`, sha256 `5b2d173cd1087abf…` = Quelle |
| 3c | `/etc/fstab` im Rootfs unversehrt | 1518 B, enthält `hy310-rootfs` |
| 4 | drei Teile per `dd` auf eine Attrappe (sparse, 15.269.888 Sektoren) | 1,0 s |
| 4b | Secure Storage der Attrappe vorher mit Marke gefüllt | **sha256 vorher = nachher** |
| 5 | Attrappe als Datenträger lesen | GPT erkannt, sechs Partitionen, CRCs stimmen, Sicherungskopie stimmt |
| 5b | `eGON.BT0` bei LBA 16 | steht dort |
| 5c | `hy310-env` bei LBA 14336 | leer, wie geplant |
| 5d | beide ext4 aus der Attrappe lesbar | Label `hy310-boot` / `hy310-rootfs`, 20 bzw. 720 Einträge |

### 7.4 Der Installerweg gegen eine Attrappe

`hy310-install._arbeiten()` vollständig durchlaufen, Ziel eine 7,28-GiB-Datei statt `/dev/sda`:

```
[3] Abzug ziehen (klein)  -> secure-storage.bin, private.bin, reserve0-a/b.bin, MANIFEST.json, LIESMICH.txt
[4] Abbild pruefen        -> drei Teile, sha256 ok; Loch bei LBA 12288..14335 bleibt unberuehrt
[5] 30 Dateien aus r2-extract/out-hy310; Arbeitskopie 1153 MiB; 30 Platzhalter gefuellt und zurueckgelesen
[6] getippte Bestaetigung, alle drei Teile geschrieben in 1 s
[7] Stichproben stimmen
    Secure Storage unveraendert (byteweise gegen den Abzug verglichen)
RUECKGABE: 0
```

Anschließend aus der **beschriebenen Attrappe** gelesen: **30/30 Vendor-Dateien byteidentisch** über das Dateisystem, und
`e2fsck -fn` im Container über beide Partitionen:

```
hy310-boot:   32/32768 files (3.1% non-contiguous), 8608/32768 blocks
hy310-rootfs: 7302/65536 files (0.2% non-contiguous), 62711/262144 blocks
```

Keine Beanstandung. Das ist der Beweis, auf den es ankommt: nach `mke2fs` → Offsets finden → roh hineinschreiben → `dd`
sind die Dateisysteme **konsistent** und die Dateien stehen richtig drin. (Erwartbar, aber nicht selbstverständlich: ext4
prüfsummt Metadaten, nicht Dateidaten — deshalb ist Hineinschreiben in vorhandene Datenblöcke unbedenklich. Jetzt ist es
auch gemessen.)

### 7.5 Byte-Vergleich gegen das Gerät

`/dev/sda`, nur gelesen. Ergebnis in §2: **LBA 0…8 alle neun Sektoren identisch.** Die Sicherungskopie weicht ab, weil auf
dem Gerät bei LBA 15269855…15269861 noch Reste der Android-Tabelle stehen; die eigentliche Sicherungstabelle
(15269880…15269886) und der Sicherungskopf (15269887) sind identisch.

---

## 8. Was nicht geprüft werden konnte

- **Windows.** Es steht keines hier — dieselbe Lage wie in `S46` §B9. Geprüft ist nur, dass sich alle drei Werkzeuge
  **als Python 3.9 übersetzen lassen** (`ast.parse(..., feature_version=(3,9))`) und dass im Abbild-Bauer kein externes
  Programm, kein `os.O_*`-Linuxismus und keine Pfadannahme steckt: Trennzeichen über `os.sep`, Dateien über `open()`.
  Der ext4-Leser aus `hy310-extract` ist laut dessen Kopf ausdrücklich windowsfähig, aber ebenfalls dort nicht gelaufen.
  **Der `_get_osfhandle`-Fehler aus `S46` §B9 steckt weiterhin in `hy310-install.Platte._groesse`** — er ist nicht Teil
  dieses Auftrags und bleibt offen.
- **Kein Schreibzugriff auf das Gerät.** Ob das Abbild ein echtes HY310 bootet, ist **ungeprüft**. Belegt ist: die
  Partitionstabelle ist byteweise die des Geräts, das mit genau diesem Layout kaltstartet (`109` §5/§12), und die
  Bausteine sind dieselben Dateien.
- **Die FEL-Kette und die Laufwerksfreigabe** wurden nicht gefahren; sie hätten das Gerät angefasst.
- **`hy310-extract` gegen einen Vollabzug** ist in diesem Lauf nicht ausgeführt worden — `extrahieren()` ist Code, der
  `ex.main([abzug, "--out", …])` aufruft, und der Aufrufweg ist geprüft, der Lauf nicht. Getestet wurde mit `--vendor` auf
  die vorhandene Extraktion.
- **Ein zweites Gerät / eine zweite Firmware.** Alle Größen stammen von einem HY310 mit einem Firmwarestand.

---

## 9. Was offen bleibt

1. **Andere Firmware, andere Größen.** Die 30 Platzhalter haben feste Größen. Ist eine Vendor-Datei auf einem fremden
   Gerät **größer**, bricht `platzhalter_fuellen` ab (gut). Ist sie **kleiner**, wird der Rest genullt — die Datei im
   Dateisystem behält dann die Platzhaltergröße. Für `.ini`- und `.TSE`-Dateien ist das vermutlich harmlos, bewiesen ist
   es nicht. `vendor_quellen()` **warnt** jetzt in diesem Fall. Die saubere Lösung wäre, die Dateilänge im Inode
   mitzukorrigieren — dafür bräuchte es doch einen kleinen ext4-Schreiber (nur `i_size`, kein Blockmanagement). Das ist
   die erste Stelle, an der es einer werden könnte.
2. **Platzbedarf.** Der Weg braucht beim Nutzer jetzt 7,3 GB (Vollabzug) + 1,2 GB (Abbild) + 1,2 GB (Arbeitskopie) ≈
   **9,7 GB**. Plan `110` §1 nennt 8 GB. Entweder die Zahl korrigieren oder die Arbeitskopie sparen, indem Teil B in
   Stücken gelesen und beim Schreiben gefüllt wird — das wäre möglich, kostet aber die Eigenschaft „am PC fertig machen,
   dann einmal schreiben".
3. **Geräteerkennung** (`110` §8) und **`hy310-scan-protected`** (`109` §9) fehlen weiterhin. Der Abbild-Bauer setzt sie
   nicht voraus, aber der Installer sollte sie vor dem ersten Schreibzugriff haben.
4. **Die Umgebung ist leer.** `hy310-env` enthält nichts; U-Boot legt sie beim ersten `saveenv` an, die Vorgaben kommen
   aus `board/sunxi/hy310.env`. Das ist so gewollt (`109` §3.1), heißt aber: ein Gerät ab Abbild hat die
   Umgebungsvorgaben des mitgelieferten U-Boot und keine gespeicherten. Ob das für den Erststart reicht, ist am Gerät zu
   sehen.
5. **Reproduzierbarkeit.** Zwei Läufe von `mkimage-eingaben.sh` erzeugen wegen der ext4-UUID und der Zeitstempel nicht
   dieselben Bytes; die **Offsets** waren in den Läufen dieser Sitzung stabil, garantiert ist das nicht. Wer ein Abbild
   nachbauen will, braucht die Bausteine, nicht das Rezept. Die Prüfsummen aller vier Bausteine stehen deshalb in der
   Tabelle.
6. **`--restore-stock` und B8** sind unverändert offen; nicht Teil dieses Auftrags.

---

## 10. Aufräumen

`r0-fel/tmp/` ist leer. Gelöscht wurden die beiden ext4-Eingaben (1,2 GB, in ~1 min mit `mkimage-eingaben.sh` neu zu
bauen), die beiden Attrappen, die Arbeitskopie und die Testsicherung. Liegen geblieben ist `r0-fel/out/` mit dem
fertigen Abbild (1,22 GB) — wie im Auftrag vorgesehen.

**Nichts außerhalb von `r0-fel/` und dieses Berichts wurde geschrieben.** Das Gerät wurde nur gelesen.
