# S46 - Kritische Prüfung der Release-Werkzeuge vor dem scharfen Lauf

**Auftrag:** Befundbericht vor dem Rücksetzen auf Herstellerfirmware und der anschließenden Neuinstallation auf Marcos Gerät.
Prüfen und bewerten, **nicht reparieren**.
**Regeln eingehalten:** keine Quell-, Doku- oder Konfigurationsdatei geändert; gearbeitet wurde in einem eigenen
Temp-Verzeichnis. Kein Netz, keine Git-Operationen, keine Agenten. Am Gerät **nur gelesen** - jeder `dd` in diesem Bericht
ist `if=/dev/sda`, kein einziges `of=`.
*Eine Nebenwirkung, der Vollständigkeit halber:* die Trockenläufe haben `r0-fel/__pycache__/hy310-install.cpython-312.pyc`
neu erzeugt (Python-Bytecode-Cache, entsteht beim Importieren von selbst). Keine Quelldatei berührt.
**Stand:** 10.09.2026, nach `S45`. Geprüfte Fassungen: `hy310-install.py` (10.09. 22:22), `hy310-extract` (10.09. 22:01),
`hy310-install.sh` 0.4 (10.09. 17:28), `build-rootfs.sh`/`install-projekt.sh` (10.09.).

**Die drei Sätze vorab:**

1. **Die Sperre um den Secure Storage hält.** Kein Schreibpfad erreicht LBA 12288…14335 - durchgetestet über alle
   sektorausgerichteten Randfälle, nicht nur behauptet (§3.1).
2. **Der Rückweg auf Herstellerfirmware ist kaputt**, an einer Stelle von zwei Zeichen: die nachgebaute Stock-GPT trägt in
   **jedem** Partitionsnamen einen Wagenrücklauf. Nachgewiesen durch Byte-Vergleich gegen den echten Stock-Abzug (§B3).
3. **Der Installationsweg existiert nicht.** Es gibt kein Abbild, keinen Abbild-Bauer und keine Offsettabelle; die Funktionen,
   die die gerätespezifischen Teile einsetzen sollen, werden nie aufgerufen (§B6).

---

## 1. Was geprüft wurde - und was nicht

| Geprüft | Wie |
|---|---|
| `r0-fel/hy310-install.py`, 841 Zeilen | Zeile für Zeile gelesen; Sperre mit einem Eigenschaftstest durchgerechnet; `stock_zurueck` als Trockenlauf gegen das echte `re/vendor/HY310/update.img` gefahren; `stock_gpt_bauen` byteweise gegen `re/device-dumps/emmc-first-300mb.bin` verglichen |
| `r2-extract/hy310-extract`, 3066 Zeilen | gezielt: ext4-Merkmalsprüfung, Verzeichnisleser, IMAGEWTY-Leser, Schreibpfade. **Nicht** vollständig gelesen |
| `r1-installer/hy310-install.sh`, 1573 Zeilen | gezielt: Sperre, GPT-Planer, `mkfs`-Pfade, Abgleich gegen den neuen Installer. **Nicht** vollständig gelesen |
| `rootfs/build-rootfs.sh`, `install-projekt.sh` | überflogen auf Schreibpfade, SSH-Schlüssel, Manifest |
| Pläne `107`, `108`, `109`, `110`, `20` | gegen den Code gelesen; Zahlen nachgerechnet |
| Berichte `S41`…`S45` | auf Widersprüche zum Code gelesen |
| Gerät `/dev/sda` | nur lesend: Partitionstabelle, Einhängezustand, drei Stichproben |

**Ausdrücklich nicht geprüft** - das gehört genannt, damit niemand mehr Deckung annimmt, als da ist:

- **Nichts wurde ausgeführt, was schreibt.** Kein Probelauf des Installers gegen eine Attrappe, keine Loop-Datei mit
  15 269 888 Sektoren. Alle Schreib-Befunde sind aus dem Code abgeleitet oder im Trockenlauf beobachtet.
- **Windows wurde nicht ausgeführt.** Die Befunde in §B9 sind Code-Lesung, kein Testlauf. Es steht hier kein Windows.
- **`sunxi-fel` wurde nicht gegen das Gerät gefahren.** Die FEL-Kette (`S44`) ist ungeprüft geblieben; sie hätte das Gerät
  angefasst.
- **Der ext4-Leser wurde nicht neu gegen `debugfs` verglichen.** `S45` hat das getan; ich habe nur die Grenzen der
  Merkmalsprüfung nachgesehen.
- **`hy310-extract` ist zu 3066 Zeilen nicht vollständig gelesen.** FAT-Leser, LP-Metadaten, Sparse-Quellen: nur
  angeschaut, nicht durchgerechnet. Der Extraktor hat **keinen** Schreibpfad auf ein Blockgerät (einziges `open(…, "wb")`
  in `materialisiere`, Zeile 480) - das war die Frage, die mich am Extraktor am meisten interessiert hat, und sie ist
  sauber beantwortet.
- **Der Bash-Installer 0.4 wurde nicht neu getestet.** `S41` hat das getan.

---

## 2. Befunde

Drei Stufen: **kritisch** = kann Hardware oder unwiederbringliche Daten kosten. **ernst** = Installation schlägt fehl oder
hinterlässt einen halben Zustand. **Anmerkung** = Unschönheit, Doku-Lücke, unbelegte Annahme.

Alle Zeilenangaben ohne Dateinamen beziehen sich auf `analyse/release/arbeit/r0-fel/hy310-install.py`.

---

### K1 - Das Ziellaufwerk wird allein an der Sektorzahl erkannt · **kritisch**

**Wo:** Zeilen 165-195 (`finde_laufwerk`), 479-484 (Vorlauf), 519-527, 535-538.

**Was:** `finde_laufwerk()` nimmt jedes Blockgerät unter `/sys/block`, dessen Name mit `sd` oder `vd` beginnt und dessen
`size` genau `15269888` ist. Das Merkmal `removable` wird in Zeile 176-177 **gelesen** und in Zeile 181 in den Treffer
gelegt - und danach **nirgends ausgewertet**. Es gibt keinen Abgleich mit dem Inhalt: keine GPT wird gelesen, kein
Partitionsname, keine Kennung. Die Plausibilitätsprüfung in Zeile 535-538 vergleicht wieder nur dieselbe Sektorzahl und ist
damit tautologisch.

**Warum es zählt:** `sd*` schließt interne SATA-Platten ein. Wer eine zweite Platte mit exakt dieser Sektorzahl am Rechner
hat - ein zweites HY310, eine baugleiche eMMC im Kartenleser, ein per `losetup` eingehängter Klon eines Vollabzugs - bekommt
sie ohne weitere Frage als Ziel. Die Bestätigungsabfrage in Zeile 605 lautet wörtlich
`"  Das ueberschreibt die eMMC. Weiter? [ja/NEIN] "` und **nennt den Gerätepfad nicht**. Der Pfad steht nur weiter oben in
einer `OK`-Zeile, die zu diesem Zeitpunkt längst weggescrollt ist.

**Wie es sich zeigt:** Zeile 479-484 macht es schärfer. Läuft das Skript ein zweites Mal, während die Freigabe noch steht,
wird der ganze FEL-Schritt übersprungen und `treffer[0]` ohne Rückfrage als Ziel genommen:

```python
schon_da = finde_laufwerk()
if schon_da and not args.device:
    K.schritt(1, "eMMC haengt bereits als Laufwerk")
    ...
    return _arbeiten(args, schon_da[0][0])
```

Bei mehreren Treffern bricht nur der **normale** Weg ab (Zeile 521-524). Der Vorlauf tut es nicht: er nimmt schlicht
`schon_da[0][0]`, also alphabetisch das erste. Ein `/dev/sdb` mit passender Größe gewinnt gegen ein `/dev/sdc`, das das
Gerät wäre.

**Wie schwer:** kritisch. Der Schaden trifft eine Platte, für die es keinen Abzug gibt, und ist nicht rückgängig zu machen.
Auf Marcos Rechner ist die Lage heute unkritisch - `nvme0n1` hat 2 000 409 264 Sektoren, `sda` 15 269 888, kein zweiter
Kandidat. Aber die Prüfung, die das absichert, findet im Code nicht statt.

---

### K2 - Kein Schutz gegen eingehängte Zielpartitionen - und der Rückvergleich meldet trotzdem „stimmt" · **kritisch**

**Wo:** Zeilen 103-109 (`Platte.__init__`), 346-370 (`pruefe_abbild`), 609-613. Gegenstück im Plan:
`doku/110-plan-installationsweg.md` §4.

**Was:** Das Blockgerät wird mit `os.O_RDWR` geöffnet, **ohne `O_EXCL`**. Es gibt kein `umount`, keine Prüfung auf
eingehängte Partitionen, kein `BLKRRPART` nach dem Schreiben. `grep -c "O_EXCL\|umount\|mount\|BLKRRPART"` auf die Datei
liefert `0`.

**Warum es zählt:** Auf einem Desktop-Linux hängt `udisks2` die Partitionen eines erscheinenden Wechseldatenträgers
automatisch ein. Schreibt man dann am Blockgerät vorbei, hält der Kernel die alten Metadaten des eingehängten Dateisystems
weiter im Seitencache und schreibt sie beim nächsten Rückschreiben oder beim Aushängen **über das frisch geschriebene
Abbild**. Das Ergebnis ist ein Dateisystem, das an zufälligen Stellen den alten Stand trägt.

Das Bittere ist die zweite Hälfte: `pruefe_abbild` liest über **denselben** Seitencache und über **denselben** Dateideskriptor
zurück. Sie sieht also nicht, was auf der eMMC steht, sondern was der Cache vorhält - und meldet in Zeile 613
`K.ok("Stichproben stimmen")`. Eine stille Beschädigung wird als geprüft ausgewiesen.

**Wie es sich zeigt - jetzt, an diesem Rechner:**

```
$ mount | grep sda
/dev/sda5 on /media/user/hy310-boot type ext4 (rw,nosuid,nodev,relatime,errors=remount-ro,uhelper=udisks2)
/dev/sda6 on /media/user/hy310-rootfs type ext4 (rw,nosuid,nodev,relatime,errors=remount-ro,uhelper=udisks2)
```

Beide Zielpartitionen sind in diesem Moment **schreibbar eingehängt**. Ein Start des Installers ginge über den Vorlauf aus
K1 direkt in `_arbeiten` - mit `schreiben=True`, gegen ein eingehängtes `sda6`.

**Der Plan hat diese Prüfung ausdrücklich gestrichen.** `110` §4, wörtlich: *„Zwei Prüfungen entfallen (läuft das System vom
Ziel? ist etwas eingehängt?)"*, begründet mit *„und er kann nicht das System zersägen, auf dem er selbst läuft"*. Die
Begründung stimmt für das **eigene** System des Installers und ist für das **Ziel** genau falsch herum: auf dem Gerät gab es
keinen Automounter, auf einem PC gibt es einen.

**Wie schwer:** kritisch. Nicht wegen des Datenverlusts auf der eMMC - die wird ohnehin überschrieben - , sondern weil die
einzige Kontrolle, die zwischen dem Nutzer und einem stillen Fehlschlag steht, dabei ein falsches „OK" liefert. Wer darauf
den Strom zieht, hat ein halb beschriebenes System und einen Bericht, der Entwarnung gab.

---

### B3 - `--restore-stock` baut eine GPT mit Wagenrücklauf in jedem Partitionsnamen · **ernst**

**Wo:** Zeile 690 (der Regex in `stock_plan`), Wirkung in Zeile 795 und 797 (`stock_gpt_bauen`).
**Das ist der Weg, den Marco als Nächstes gehen will.**

**Was:** `sys_partition.fex` aus dem IMAGEWTY-Container hat **CRLF-Zeilenenden**:

```
$ file re/vendor/HY310/extracted/sys_partition.fex
… Unicode text, UTF-8 text, with CRLF line terminators
$ sed -n '37p' … | cat -A
name=bootloader_a^M$
```

Der Regex in Zeile 690 lautet

```python
d = dict(re.findall(r"^\s*(\w+)\s*=\s*\"?([^\"\n]+)\"?\s*$", block, re.M))
```

Die Wertegruppe `[^\"\n]+` schließt `\r` nicht aus. Bei einem **gequoteten** Wert (`downloadfile="boot-resource.fex"`)
beendet das schließende Anführungszeichen den Treffer, der Wert bleibt sauber. Bei einem **ungequoteten** Wert
(`name=bootloader_a`) gibt es keinen solchen Anschlag - der Wagenrücklauf landet im Namen. `size` überlebt es, weil
`int("65536\r")` funktioniert.

**Warum es zählt:** Zeile 797 schreibt `name.encode("utf-16-le")` als GPT-Partitionsnamen. Jeder der 26 Namen bekommt damit
ein zusätzliches `U+000D`. Android findet seine Partitionen über `/dev/block/by-name/<name>`; `boot_a\r` ist nicht `boot_a`.
Nebenbei greift auch Zeile 795 nicht mehr, denn `name == "frp"` ist für `"frp\r"` falsch - das Attributbit 47, das laut
Kommentar am Stock-Dump nachgemessen wurde, wird nie gesetzt.

**Wie es sich zeigt:** Byte-Vergleich der von `stock_gpt_bauen` erzeugten Tabelle gegen die echte Stock-GPT in
`re/device-dumps/emmc-first-300mb.bin` (Abzug vom 31.08., vor dem Umbau):

```
wie im Code     LBA0:OK LBA1:DIFF LBA2:DIFF
mit .strip()    LBA0:OK LBA1:OK   LBA2:OK
```

Erste Abweichung in LBA 2 bei Byte 80 - das ist das 13. UTF-16-Zeichen des Namens `bootloader_a`, `0d` statt `00`.
Im Kopf (LBA 1) weichen genau die Bytes 16-19 und 88-91 ab: die Kopf-CRC und die CRC über das Eintragsfeld, also
Folgeschäden derselben Ursache.

**Damit ist auch der Kommentar in Zeile 766-773 widerlegt**, der sagt, die Werte seien am Gerät abgelesen und die Tabelle
entspreche dem Stock byteweise. Sie tut es an LBA 0, an LBA 1 und 2 nicht.

**Wie schwer:** ernst. Kein Hardware-Schaden, das Gerät bleibt über FEL erreichbar. Aber der Rückweg auf Android, den Marco
als Absicherung vor dem riskanten Schritt einplant, liefert in dieser Fassung ein Gerät, das nicht startet - und zwar genau
dann, wenn man ihn braucht. Der Fund ist gut: es sind zwei Zeichen, und danach stimmt die Tabelle byteweise.

---

### B4 - `--restore` und `--restore-stock` laufen ohne jeden Abzug · **ernst**

**Wo:** Reihenfolge in `_arbeiten`: Zeile 541 (`args.restore_stock`), Zeile 563 (`args.restore`), Abzug erst ab Zeile 577.
Gegenstück: `110` §2.

**Was:** Beide Rückspielzweige stehen **vor** dem Abzugsschritt und kehren mit `return` zurück. Wer
`--restore-stock update.img` aufruft, überschreibt die eMMC, ohne dass je ein Byte gesichert wurde - auch nicht der kleine
Abzug mit dem Secure Storage.

**Warum es zählt:** `110` §2 sagt wörtlich: *„Vor dem ersten Schreibzugriff. Das Skript beginnt nicht, bevor der Abzug steht
und geprüft ist. Kein `--skip-backup`; die Wahl ist welcher Abzug, nicht ob."* Und weiter: *„Der kleine Abzug ist nicht
verhandelbar."* Der Code hält das im Installationszweig ein und im Rückspielzweig nicht.

**Wie es sich zeigt:** `hy310-install --uboot u.bin --restore-stock update.img` → Rückfrage, „ja", schreiben. Kein
`hy310-sicherung/`-Verzeichnis entsteht.

**Wie schwer:** ernst. Auf einem schon umgebauten Gerät ist der letzte Stand danach weg, wenn der Nutzer keinen eigenen
Abzug hat. Der Secure Storage selbst bleibt unberührt (§3.1) - das ist der Grund, warum es nicht kritisch ist.

---

### B5 - Der Vollabzug wird nie zurückgelesen · **ernst**

**Wo:** Zeilen 271-294 (`abzug_voll`), 581-587.

**Was:** `abzug_voll` bildet `sha256` **über dieselben Bytes, die es gerade geschrieben hat**. Eine zweite Lesung gibt es
nicht, und `pruefe_abbild` wird nur im `--abbild`-Zweig aufgerufen (Zeile 609).

**Warum es zählt:** Die Prüfsumme beweist damit nur, dass Speicher und Datei übereinstimmen. Liefert die USB-Strecke oder
die eMMC fehlerhafte Daten, bekommt der Nutzer einen beschädigten Abzug mit einer korrekten Prüfsumme darüber - und ein
`MANIFEST.json`, das ihm Sicherheit vorspiegelt. `110` §2 verlangt ausdrücklich das Gegenteil:
*„sha256 über den Abzug, zweite Lesung stichprobenweise verglichen (GPT, Secure-Storage-Block, ein zufälliger Bereich).
Weicht etwas ab, bricht es ab"*. Diese zweite Lesung ist nicht implementiert.

Der einzige echte Schutz im Abzugspfad ist Zeile 283 (`"nur %d von %d Byte gelesen"`), und der greift nur bei einer
**kurzen** Lesung, nicht bei einer falschen.

**Wie schwer:** ernst. Der Abzug ist die einzige Rückversicherung des Nutzers; ein ungeprüfter Abzug ist keine.

---

### B6 - Es gibt kein Abbild, keinen Abbild-Bauer und keine Offsettabelle · **ernst**

**Wo:** Zeile 455 (`--tabelle`), Zeilen 375-406 (`platzhalter_fuellen`), 408-416 (`platzhalter_pruefen`).

**Was:** `args.tabelle` wird deklariert und **nie gelesen**. `platzhalter_fuellen` und `platzhalter_pruefen` werden
**nirgends aufgerufen** - beide sind toter Code:

```
$ grep -n "tabelle\|platzhalter" r0-fel/hy310-install.py
375: def platzhalter_fuellen(…)      # Definition
388,392,393:                         # nur innerhalb der Funktion
408: def platzhalter_pruefen(…)      # Definition
412:                                 # nur innerhalb der Funktion
455: p.add_argument("--tabelle", …)  # deklariert, nie benutzt
```

Und es gibt nichts, was ein `--abbild` erzeugen würde. Eine Suche über `analyse/release/` und `doku/` nach einem
Abbild-Bauer, nach `--abbild` oder nach `--tabelle` findet **nur** diese Datei selbst. In `rootfs/out/` liegt ein
`hy310-rootfs.ext4` (1 GiB) - ein Dateisystem, kein Datenträgerabbild mit GPT und Boot-Kette.

**Warum es zählt:** `110` §1 Schritt 5 („Layout v3, Boot-Kette, Rootfs, Artefakte auf das Laufwerk schreiben") und §1
Schritt 4 („Extraktion der proprietären Teile aus dem Abzug") haben im PC-Installer **keine Entsprechung**. Der Docstring in
Zeile 384-386 beschreibt, wie das Abbild Platzhalter enthält, die der Installer füllt - der Mechanismus ist beschrieben,
begründet und nicht angeschlossen. Ohne ihn schriebe ein `--abbild` das Abbild **mit den Platzhaltern**, also ein System
ohne EDID, ohne `msp-patch.bin`, ohne PQ-Dateien.

Der Bash-Installer 0.4 kann diese elf Schritte (`precheck, gpt, uboot, mkfs, rootfs, mips, firmware, kernel, config, env,
report`) - er läuft aber laut eigenem Kopf „als root **auf dem Board**, aus dem laufenden Netboot-Linux". `110` §5 nennt den
PC-Installer einen *„Umbau des vorhandenen Installers (0.4)"*; tatsächlich ist er eine Neuschrift, die von den elf Schritten
zwei mitgenommen hat.

**Wie schwer:** ernst. Die Neuinstallation nach dem Zurücksetzen hat mit dem PC-Werkzeug allein keinen Weg. Praktisch heißt
das: entweder es kommt noch ein Abbild-Bauer, oder die Installation läuft weiter über den Netboot und `hy310-install.sh` 0.4.

---

### B7 - Die Backup-GPT am Plattenende wird beim Schreiben eines Abbilds nicht mitgeschrieben · **ernst**

**Wo:** Zeilen 299-329 (`abbild_schreiben`).

**Was:** Es werden genau `os.path.getsize(datei)` Bytes ab LBA 0 geschrieben. Das geplante Abbild ist laut `110` §7
**1,2 GB** groß, die eMMC 7,28 GiB. Die Sicherungskopie der GPT gehört an LBA 15 269 887 (und das Eintragsfeld ab
15 269 880) - außerhalb dessen, was ein 1,2-GB-Abbild abdeckt.

**Warum es zählt:** Nach dem Schreiben zeigt der primäre GPT-Kopf auf eine Sicherungskopie, an deren Stelle noch der alte
Stand liegt (die Android-Tabelle oder Reste des Rootfs). `sfdisk`, `gdisk` und `gparted` melden das als beschädigt und
bieten an, die primäre Tabelle **aus der Sicherung wiederherzustellen** - womit ein Nutzer, der die Warnung „repariert",
die Android-Partitionierung über das frische Layout zurückholt.

Zum Vergleich: `stock_zurueck` macht es richtig - Zeilen 827-833 liefern beide Seiten, und Zeile 721-723 schreibt sie.
Nur der Abbild-Pfad hat es nicht.

**Wie schwer:** ernst. Kein sofortiger Ausfall, aber ein Zustand, der Werkzeuge zu einer falschen Reparatur einlädt.

---

### B8 - `--restore-stock` lässt jede Partition ohne Quelldatei unberührt · **ernst**

**Wo:** Zeilen 739-741 (`if not quelle: continue`).

**Was:** Von 26 Partitionen haben 18 einen `downloadfile`-Eintrag; die übrigen bleiben unangetastet. Der Trockenlauf gegen
das echte `update.img` zeigt genau, was geschrieben würde - und was nicht:

```
26 Partitionen laut sys_partition.fex
OK sys_partition.fex      -> GPT (Schutz-MBR, Kopf, Tabelle, Sicherungskopien)
OK boot0_sdcard.fex       -> LBA 16 / 256          0,03 MiB
OK boot_package.fex       -> LBA 24576 / 32800     1,19 MiB
OK boot-resource.fex      -> bootloader_a / _b    20,74 MiB
OK env.fex, boot.fex, vendor_boot.fex, super.fex (1537,59 MiB), misc.fex,
   vbmeta*.fex, dtbo.fex, mediadata.fex, Reserve0.fex
== 1718,4 MiB
```

Nicht geschrieben und damit im alten Zustand: `env_b`, `boot_b`, `vendor_boot_b`, `vbmeta_b`, `vbmeta_system_b`,
`vbmeta_vendor_b`, `dtbo_b`, `Reserve0_b`, `frp`, `empty`, `metadata`, `private`, **`UDISK`**.

**Warum es zählt:** `UDISK` beginnt bei LBA 5 555 200 und reicht bis zum Plattenende - auf einem umgebauten Gerät liegt dort
das Debian-Rootfs. `metadata` (LBA 4 858 880) trägt bei Android die Verschlüsselungs-Metadaten für `userdata`. Ein Android,
das dort ein fremdes ext4 mit gültigem Superblock vorfindet, mountet es entweder oder kommt in eine Startschleife -
jedenfalls ist das kein sauberer Werkszustand. `109` §11 hat die Frage gestellt („bringt das Firmware-Image alles zurück?")
und für diese Partitionen mit *„werden vom Flashtool angelegt"* beantwortet. Unser Code legt sie nicht an und löscht sie
auch nicht.

**Wie schwer:** ernst. Ein Rücksetzen, das nicht zurücksetzt.

---

### B9 - Der Windows-Pfad kann nicht laufen · **ernst**

**Wo:** Zeilen 112-124 (`Platte._groesse`), 182-192 (`finde_laufwerk`), 138-153 (`Platte.schreib`).
Nicht ausgeführt - Code-Lesung.

Vier Punkte, jeder für sich hinreichend:

1. **Zeile 117:** `ctypes.windll.kernel32._get_osfhandle` - `_get_osfhandle` ist eine Funktion der C-Laufzeit
   (`msvcrt`/`ucrtbase`), **nicht** von `kernel32.dll`. Der Zugriff auf ein nicht vorhandenes Symbol wirft in ctypes einen
   `AttributeError`. In `finde_laufwerk` steht darum herum ein `except OSError` (Zeile 189) - das fängt ihn nicht. Der
   erste Schleifendurchlauf bricht das Programm ab. Richtig wäre `msvcrt.get_osfhandle(self.fd)`.
2. **Zeile 120-121:** `DeviceIoControl` wird ohne `argtypes` aufgerufen. ctypes bildet einen Python-`int` dann auf `c_int`
   ab - auf 64-Bit-Windows wird das Handle abgeschnitten. (Der Steuercode `0x0007405C` selbst ist richtig:
   `CTL_CODE(FILE_DEVICE_DISK, 0x17, METHOD_BUFFERED, FILE_READ_ACCESS)`.)
3. **Kein Volume-Lock.** Seit Vista weist Windows Schreibzugriffe auf Sektoren zurück, die zu einem eingehängten Volume
   gehören, solange der Aufrufer nicht `FSCTL_LOCK_VOLUME`/`FSCTL_DISMOUNT_VOLUME` gesetzt hat. Der Code tut das nicht.
   Die Windows-Entsprechung von K2 - dort scheitert es wenigstens laut.
4. **Rohzugriff braucht Administratorrechte**, und Schreibzugriffe müssen ein Vielfaches der Sektorgröße sein. Das letzte
   Stück einer Datei mit nicht durch 512 teilbarer Größe (Zeile 310) verletzt das.

**Warum es zählt:** Der Modulkopf (Zeile 6) behauptet *„Laeuft unter Linux und Windows"*. `110` §5 Punkt 5 sagt dagegen
korrekt: *„Windows-Weg: offen … Nicht v0.1"*. Der Code beansprucht mehr als der Plan verspricht.

**Wie schwer:** ernst - für einen Nutzer, der es glaubt. Für Marcos Lauf am Linux-PC ohne Belang.

---

### B10 - `sunxi-fel` liegt nicht unter dem Namen, den der Installer sucht · **ernst**

**Wo:** Zeilen 200-214 (`fel_werkzeug`), 217-225 (`fel_da`), 500-502.

**Was:** `fel_werkzeug` sucht `sunxi-fel` (a) neben dem Skript, (b) im `PATH`. Im Verzeichnis `r0-fel/` liegt aber nur
`sunxi-fel.vor-tuer-patch`, und im `PATH` ist nichts (`which sunxi-fel` → leer). Der Installer bricht in Zeile 213 ab.

**Warum es zählt:** Zusätzlich prüft Zeile 500 `if "H713" not in kennung`. Diese Kennung stammt aus `sunxi-fel version`,
und der H713 meldet dieselbe SoC-ID wie der H616 - die Zeichenkette `H713` kommt **nur** aus einer gepatchten
`soc_info.c`. Ein Standard-`sunxi-fel` aus der Distribution würde `H616` melden und den Lauf mit *„Das ist kein H713.
Abbruch."* beenden. Umgekehrt braucht der FEL-Boot zwingend den Tür-Patch aus
`r0-fel/patches/0002-sunxi-tools-h713-fel-door.patch` (`fel_door_addr = 0x48000000`), sonst hängt der Kern statt zu booten
- der Patch sagt das in seinem eigenen Kommentar.

**Wie schwer:** ernst. Es scheitert laut und früh, kostet also nichts außer Zeit - aber ein Release, dessen erster Schritt
ein nicht mitgeliefertes Werkzeug verlangt, ist kein Release. Für Marcos Lauf: `--sunxi-fel <pfad>` auf die **gepatchte**
Binärdatei zeigen lassen und vorher `sunxi-fel version` von Hand prüfen.

---

### B11 - Geräteerkennung und Schutzbereichs-Suche fehlen vollständig · **ernst**

**Wo:** Zeilen 43-48 (`EINMALIG`), 242-268 (`abzug_klein`). Gegenstücke: `110` §8, `109` §9.

**Was:** `110` §8 beschreibt in einer Tabelle, wie der Installer in 1,2 MiB Lesearbeit (0,2 s) über GPT → `super` →
LP-Metadaten → `vendor` → `build.prop` den Firmware-Fingerabdruck ermittelt, und legt fünf Verhaltensregeln fest,
darunter Punkt 4: *„Unbekannt → abbrechen … Kein `--trotzdem`: die Fundstellen einer fremden Version zu raten, kostet im
schlimmsten Fall den Secure Storage."* Punkt 5: *„Kein Stock-Layout (das Gerät wurde schon umgebaut) → sagen, was gefunden
wurde, und nur den Abzug anbieten."* `109` §9 verlangt zusätzlich ein `hy310-scan-protected`, das die Schlüsselblöcke
**sucht statt annimmt**.

**Nichts davon ist im Code.** Statt zu suchen, stehen die Fundstellen als Konstanten in Zeile 43-48 - übernommen aus der
Stock-Tabelle dieses einen Geräts.

**Wie es sich zeigt:** Auf dem Gerät, das gerade angeschlossen ist, ist das Stock-Layout längst weg. Die drei LBAs liegen
jetzt mitten im Debian-Rootfs:

```
$ sudo dd if=/dev/sda bs=512 skip=4891648 count=32768 | tr -d '\000' | wc -c   → 0
$ sudo dd if=/dev/sda bs=512 skip=5489664 count=32768 | tr -d '\000' | wc -c   → 0
```

Hier greift die Leer-Heuristik in Zeile 256 (`daten.count(0) == len(daten)`) und warnt - das ist gut gebaut. Aber die
Warnung ist **nicht bindend**: Zeile 264-267 gibt sie aus, und der Lauf geht weiter. Und sie unterscheidet nicht zwischen
„schon umgebaut" und „diese Firmware nutzt den Bereich nicht". Läge dort auf einem fremden Gerät irgendetwas Nicht-Null,
würde es kommentarlos als `private.bin` gesichert, egal was es ist.

**Wie schwer:** ernst. Für Marcos Gerät, dessen Layout bekannt ist, folgenlos. Für jedes fremde Gerät ist es genau der
Fall, gegen den `109` §9 geschrieben wurde.

---

### B12 - Kein `--authorized-key`; das gebaute Rootfs hat keinen Schlüssel · **ernst**

**Wo:** `grep -ci "authorized\|ssh"` auf `hy310-install.py` → `0`. Gegenstück: `rootfs/out/hy310-rootfs.manifest`
(`ssh_key_eingebaut=nein`), `109` §10, `107` §3.

**Was:** Der Bash-Installer 0.4 hat `--authorized-key` (Zeile 1413-1414 dort). Der PC-Installer hat die Option nicht. Das
gebaute Rootfs trägt sie ebenfalls nicht.

**Warum es zählt:** `109` §10 hält den Fall schon fest: *„Das Release-Abbild hat bewusst keinen SSH-Schlüssel (107 §3).
Nach dem Umzug vom Netboot war das Gerät deshalb nur über die serielle Konsole erreichbar. Der Installer hat dafür bereits
`--authorized-key` - die Option war beim Umbau nur nicht benutzt worden. **Beim scharfen Lauf mitgeben.**"* Mit dem
PC-Installer gibt es nichts mitzugeben.

**Wie schwer:** ernst, aber sauber umgehbar: der Schlüssel muss dann beim Bau des Rootfs hinein (`build-rootfs.sh` kann es,
Zeile 512-513), nicht beim Installieren. Wer es vergisst, braucht die serielle Konsole.

---

### B13 - `stock_gpt_bauen` und `stock_plan` sind auf genau eine Firmware zugeschnitten · **ernst**

**Wo:** Zeile 687 (`lba = 73728`), Zeile 782 (`nent, entsz = 26, 128`), Zeile 790 (`ende`), Zeile 784 (`last_usable`).

Vier Annahmen, die nirgends geprüft werden:

1. **Erste Partition bei LBA 73728**, hart eingetragen mit dem Kommentar *„wie im Stock gemessen"*. Der Wert steht in
   `sys_partition.fex` **nicht** - dort steht `[mbr] size=16384` (KiB), und das wird ignoriert. Eine Firmware mit anderem
   MBR-Bereich verschiebt **alle** Partitionen; die Daten landen dann durchgehend am falschen Ort.
2. **26 Einträge**, hart. `for i in range(nent)` in Zeile 787: hat eine `sys_partition.fex` mehr als 26 Partitionen, werden
   die überzähligen still übergangen - die Schleife ab Zeile 739 schreibt ihre Daten aber trotzdem. Ergebnis: beschriebene
   Bereiche ohne Tabelleneintrag, ohne eine einzige Meldung. Für das vorliegende `update.img` stimmt 26 exakt (nachgezählt),
   für ein anderes ist es geraten.
3. **Andere eMMC-Größe:** `last_usable = disk_sektoren - 34` und Zeile 790 setzen eine Partition ohne `size` bis
   `last_usable`. Es gibt **keine Prüfung**, ob die Summe der Partitionen überhaupt auf die Platte passt. Auf einer
   kleineren eMMC würden Partitionen jenseits des Plattenendes eingetragen; auf einer größeren bliebe der Rest ungenutzt.
   Zum Vergleich: der Bash-Installer prüft genau das (`hy310-install.sh` Zeilen 437-447: kürzt und meldet).
4. **`size = 0` nur als letzter Eintrag richtig.** Zeile 694 addiert `sekt` auf `lba`; bei `sekt = 0` bleibt `lba` stehen,
   und **alle folgenden Partitionen bekommen denselben Start-LBA**. Im vorliegenden `update.img` hat nur `UDISK` (der
   letzte Eintrag) kein `size`, also fällt es nicht auf. Die `.fex`-Doku (Zeile 28 der Datei) erlaubt es aber ausdrücklich
   an beliebiger Stelle: *„size = 0, 将创建一个无大小的空分区"*.

**Wie schwer:** ernst. Für die eine geprüfte Firmware belanglos. Für die im Plan vorgesehene Nutzung („der Nutzer lädt sich
im Fall der Fälle das Stock-Image", `110` §2) ist es eine Reihe stiller Fehlschläge.

---

### B14 - `--restore` prüft den Abzug nicht · **ernst**

**Wo:** Zeilen 563-575.

Geprüft wird nur, ob die Datei existiert (Zeile 565) und ob sie größer als die eMMC ist (Zeile 303, in
`abbild_schreiben`). Nicht geprüft wird: ob sie **kleiner** ist als die eMMC, ob die Prüfsumme zu dem daneben liegenden
`MANIFEST.json` passt, ob sie von **diesem** Gerät stammt, ob es überhaupt ein Vollabzug ist. Ein abgebrochener,
halb geschriebener Abzug wird kommentarlos zurückgespielt und hinterlässt genau das, was `--restore` verhindern soll.
`_manifest_schreiben` (Zeile 621-647) legt die Prüfsumme sauber ab - sie wird nur nie wieder gelesen.

Dazu: `pruefe_abbild` läuft nach `--abbild` (Zeile 609), aber **nicht** nach `--restore` (Zeile 571) und nicht nach
`--restore-stock` (Zeile 556). Ausgerechnet die beiden Wege, die im Notfall benutzt werden, prüfen ihr Ergebnis nicht.

---

### B15 - Abbruch mitten im Schreiben bleibt unkommentiert · **ernst**

**Wo:** Zeilen 617-618 (`finally: platte.close()`), 836-841.

Bei `Strg-C` während `abbild_schreiben` fängt Zeile 839 den `KeyboardInterrupt`, `platte.close()` ruft `sync()`, und das
Programm endet mit `„Abgebrochen."` und Rückgabewert 130. Auf der eMMC steht dann ein halb geschriebenes System. Der Nutzer
erfährt nicht, dass er **nicht** neu starten darf und dass FEL der Weg zurück ist. Dieselbe Lücke bei einem `OSError`, wenn
das Gerät mitten im Schreiben verschwindet: die Ausnahme fliegt ungefangen bis nach oben und liefert einen Traceback.

Zum Vergleich: Zeile 611 macht es für den Prüffehler richtig - *„nicht neu starten, nachfragen."* Genau dieser Satz fehlt
in allen anderen Abbruchfällen.

Ebenfalls ungefangen: `subprocess.run([fel, "uboot", args.uboot], check=True, timeout=120)` in Zeile 510. Scheitert der
FEL-Boot, sieht der Nutzer einen `CalledProcessError`-Traceback statt einer Meldung.

---

## 2.2 Anmerkungen

**A1 - `_um_sperre` verwirft eine nicht sektorausgerichtete Restlänge stillschweigend** (Zeilen 332-343). `n = len(daten) // SECT`
schneidet ab; ein angebrochener letzter Sektor fällt aus beiden Teilstücken heraus. Gemessen:

```
Restlaenge +1   Byte: 1024 von 1025 Byte weitergereicht
Restlaenge +511 Byte: 1024 von 1535 Byte weitergereicht
```

Praktisch unerreichbar, weil `abbild_schreiben` in 4-MiB-Stücken liest und nur das **letzte** Stück angebrochen sein kann -
das läge bei einem Abbild von mehr als 14 MiB weit hinter der Sperre. Trotzdem: stiller Datenverlust ohne Fehlermeldung.

**A2 - Der Secure Storage wird ausgelesen und offen abgelegt** (Zeilen 44, 247-251). `109` §2.3 formuliert die Regel als
*„dieser Bereich wird **nicht beschrieben und nicht ausgelesen**"* und legt für die vorhandene Kopie
`re/device-dumps/secure-storage-…bin` ausdrücklich **Modus 600** fest. `110` §2 verlangt dagegen, dass der kleine Abzug
genau diesen Block enthält. Die beiden Pläne widersprechen sich; der Code folgt `110` und legt
`hy310-sicherung/secure-storage.bin` mit der Standard-umask (in der Regel 0644) im Arbeitsverzeichnis ab, dazu die sha256
im `MANIFEST.json`. `LIESMICH.txt` (Zeile 641-644) fordert den Nutzer auf, die Datei aufzuheben - ohne ein Wort dazu, dass
sie nicht in einen Fehlerbericht, eine Cloud-Sicherung oder ein Issue gehört. `109` §9 Punkt 4 verlangt für den
Fehlerbericht genau das Gegenteil: *„aber ohne den Blockinhalt"*.

**A3 - Der Abzug hat keinen Rückweg.** Es gibt keinen Schalter, der `secure-storage.bin`, `private.bin` oder
`reserve0-*.bin` je wieder auf das Gerät schreibt - die Sperre verböte es für den ersten sogar. `LIESMICH.txt` nennt als
Rückspielbefehl `hy310-install --uboot … --restore emmc-voll.img`, und der lässt die Sperrzone aus. Das ist inhaltlich
richtig (der Block ist ja unverändert), aber der Text erweckt den Eindruck, die `.bin`-Dateien wären einspielbar.

**A4 - Nachgerechnete Zahlen.** Die meisten stimmen; drei nicht:

| Behauptung | Rechnung | Urteil |
|---|---|---|
| kleiner Abzug 49 MiB | 2048+32768+32768+32768 = 100 352 Sekt. = 49,0 MiB | ✓ |
| Vollabzug 7,3 GB / 17 min | 15 269 888 × 512 = 7 818 182 656 B; ÷ 7,6 MB/s = 17,1 min | ✓ |
| unser Abbild 1,2 GB / 2,6 min | ÷ 7,7 MB/s = 2,6 min | ✓ |
| `--restore-stock` Dauer | 1718,4 MiB ÷ 7,7 MB/s ≈ **3,9 min** | **nirgends dokumentiert** |
| kleiner Abzug „rund 10 Sekunden" (Zeile 437) | `110` §2 sagt **~7 s**; 49 MiB ÷ 7,6 MB/s = 6,8 s | Code widerspricht dem Plan |
| Stock-GPT: 26 Partitionen, UDISK endet bei 15 269 854 | `gpt-stock-20260910.txt` und `last_usable` stimmen überein | ✓ |

**A5 - `110` widerspricht sich selbst beim Abzug.** §1 (Schritt 3) sagt *„Vollabzug der eMMC … **Pflicht, nicht wählbar**"*,
§6 sagt *„**Vollabzug ist Pflicht** und nicht abwählbar (Marco, 10.09.)"* - §2 desselben Plans sagt *„zwei Größen zur
Wahl"*. Der Code folgt §2 und setzt in Zeile 446 als **Vorgabe `klein`**; bei nicht-interaktivem Aufruf (Zeile 422) wird die
Vorgabe ohne Nachfrage genommen. Das ist die schwächste der drei Lesarten.

**A6 - `109` §2.4 nennt eine engere Sperrzone als §2.3.** §2.4: *„die Sektoren 12288 … **12399** werden nie beschrieben"*
(112 Sektoren, der belegte Teil). §2.3 und beide Installer sperren 12288…**14335** (2048 Sektoren, die ganze Partition).
Der Code ist strenger als die schwächste Doku-Stelle - richtig herum, aber die Doku sollte einheitlich sein.

**A7 - Die Beta-Warnung fehlt im Installer.** `110` §9 verlangt den Warnkasten an drei Stellen, darunter *„`hy310-install`,
vor dem ersten Schreibzugriff - als Abfrage, die eine getippte Bestätigung verlangt"*. `grep -ci beta` auf
`hy310-install.py` → `0`. Die getippte Bestätigung (`[ja/NEIN]`, Zeile 553/569/605) ist da; der Text nicht.

**A8 - `--device` zusammen mit einem schon freigegebenen Laufwerk führt ins Leere** (Zeile 480). Die Bedingung lautet
`if schon_da and not args.device`. Wer `--device /dev/sdb` angibt, während die Freigabe steht, landet im FEL-Zweig, findet
kein FEL-Gerät (es ist ja im Massenspeicher-Modus) und bekommt `„Immer noch nichts. Steckt das A-auf-A-Kabel?"`. Zeile 527
gibt außerdem `treffer[0][1]` aus, auch wenn `--device` etwas anderes gewählt hat.

**A9 - `stock_zurueck` lädt jede Quelldatei am Stück in den Speicher** (Zeilen 732, 746: `d.read(0, d.size)`). Für
`super.fex` sind das 1537,59 MiB in einem Rutsch, plus die Kopie beim Schreiben. Spitzenbedarf grob 1,6-3 GiB. Auf Marcos
Rechner unkritisch, auf einem 4-GB-Notebook nicht.

**A10 - ext4-Leser: die Merkmalsprüfung ist eine schwarze Liste** (`hy310-extract` Zeilen 1229-1236). Abgewiesen werden
`compression`, `encrypt`, `inline_data`, `meta_bg` und `bigalloc` - sauber und mit Verweis auf `--use-debugfs`. **Nicht**
abgewiesen wird alles, was der Autor nicht vorhergesehen hat; unbekannte `INCOMPAT`-Bits laufen durch. Der praktisch
relevante Fall wäre `INCOMPAT_DIRDATA` (0x1000), das den Verzeichnisleser stillschweigend falsch lesen ließe. Eine weiße
Liste („alles außer diesen bekannten Bits wird abgelehnt") wäre die robustere Grenze.

**A11 - `INCOMPAT_RECOVER` und `s_state` werden nicht geprüft**, entgegen dem Klassen-Docstring
(`hy310-extract` Zeilen 1164-1166): *„Kann nicht … Journal-Wiedergabe … Jeder dieser Fälle wird erkannt und **laut
gemeldet**, nicht stillschweigend falsch gelesen."* Für das Journal stimmt das nicht - `grep -n "RECOVER\|s_state"`
liefert nichts. **`S45` benennt das selbst** (§ Restpunkt 3: *„Der Leser sagt das derzeit nicht laut; eine Warnung bei
`INCOMPAT_RECOVER` wäre eine Zeile Aufwand"*) und stellt in §4.3 fest, dass der eMMC-Vollabzug genau dieses Flag trägt. Der
Befund ist also bekannt; nur der Docstring ist zu selbstbewusst.

**A12 - `metadata_csum` wird nicht verifiziert**, ebenfalls in `S45` (Restpunkt 2) offen benannt. Für einen Nur-Leser kein
Korrektheitsproblem - der Leser bemerkt eine Beschädigung des Abbilds aber auch nicht. Positiv: der Verzeichnisleser
überspringt Einträge mit Inode 0 (`hy310-extract` Zeile 1469: `if kind and 8 + nl <= rec_len`) und behandelt damit sowohl
die `dir_index`-Hashknoten als auch den `ext4_dir_entry_tail` von `metadata_csum` korrekt.

**A13 - `doku/20-flashen-und-recovery.md` kennt den Weg nicht, den Marco gehen will.** Das Dokument beschreibt vier
Flash-Wege, die FEL-Rettung und den Rückweg zum Vendor-`boot0`. `grep -n "restore-stock\|Herstellerfirmware\|update.img\|IMAGEWTY"`
darauf → leer. Der Weg „zurück auf Android" existiert nur als undokumentierter Schalter in einem Skript, das in keinem
einzigen Dokument des Projekts erwähnt wird (`grep -rn "hy310-install.py" doku/` → leer).

**A14 - `hy310-keys` trägt den Typ „Linux filesystem data".** Am Gerät nachgelesen:

```
/dev/sda3 : start=12288, size=2048, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name="hy310-keys"
```

`109` §2.4 begründet den Tabelleneintrag damit, dass *„`lsblk`, `fdisk`, `gparted` und jedes andere Werkzeug ab sofort
**sehen**, dass die Bereiche belegt sind"*. Das stimmt - aber der Typ sagt ihnen zugleich „hier gehört ein Linux-Dateisystem
hin", und `udisks`/`gparted` bieten für eine 1-MiB-Partition dieses Typs ohne erkennbares Dateisystem bereitwillig
„Formatieren" an. Ein Typ, der nach Reserve aussieht, würde die Absicht besser tragen. Kein Code-Fehler, eine
Layout-Entscheidung mit unwiderruflicher Kehrseite.

**A15 - Der als Beleg genannte Vollabzug ist kein Stock-Abzug.** `110` §7 führt
`re/device-dumps/emmc-voll-HY310-dev-20260910.img` als Beleg an. Der Eintrag bei LBA 2 dieses Abbilds lautet `hy310-spl` -
es ist ein Abzug des **schon umgebauten** Geräts. Der Satz aus `waehle_abzug` (Zeile 443-444), ein Vollabzug spiele *„dein
Geraet 1:1 zurueck, Android eingeschlossen"*, gilt für diese Datei nicht. Der Stock-Stand liegt in
`emmc-first-300mb.bin` (31.08.) - und der umfasst nur die ersten 300 MB.

---

## 3. Was gut ist

Nicht aus Höflichkeit - das sind die Stellen, auf die man sich stützen kann.

### 3.1 Die Sperre um den Secure Storage hält

Das war die wichtigste Frage, und die Antwort ist sauber. Die Prüfung in `Platte.schreib` (Zeilen 141-147) sitzt an der
**einzigen** Stelle, an der geschrieben wird, und rechnet mit dem letzten berührten Sektor, nicht mit dem ersten:

```python
ende = lba + (len(daten) + SECT - 1) // SECT - 1
if lba <= SPERRE_LETZTER and ende >= SPERRE_ERSTER:
    raise RuntimeError(…)
```

Ich habe `_um_sperre` gegen jeden sektorausgerichteten Fall durchgerechnet: alle Startsektoren von 12285 bis 14339, mit
Längen 1-6 Sektoren und mit dem echten 4-MiB-Stück. Geprüft wurde beides - **kein Sektor der Sperrzone wird geschrieben**
und **kein Sektor außerhalb geht verloren**:

```
Sperre: 0 Faelle fehlerhaft
```

Die Randfälle stimmen einzeln: ein Stück, das genau bei 12287 endet, läuft durch die normale Schreibroutine; eines, das bei
12288 beginnt, verliert nur den vorderen Teil; eines, das bei 14336 beginnt, wird unverändert geschrieben; eines, das
vollständig innerhalb liegt, ergibt eine leere Teileliste und schreibt nichts.

Dazu kommt, dass **kein einziger Schreibpfad überhaupt in die Nähe zielt.** GPT: LBA 0, 1, 2, 15 269 880, 15 269 887. Roh:
16, 256, 24576, 32800 (letzteres endet bei 35 237). Partitionen: ab 73 728. Der Abstand zur Sperrzone ist an keiner Stelle
knapp. Die Sperre ist der Gürtel zu einem Hosenträger, der schon sitzt.

### 3.2 Der Nachbau der Stock-GPT ist bis auf B3 richtig

Mit `.strip()` auf dem Namen ist die erzeugte Tabelle an LBA 0, 1 und 2 **byteweise identisch** mit dem echten Stock-Abzug.
Die Feinheiten, an denen ein Nachbau üblicherweise scheitert, sind alle getroffen: das reservierte Feld bei Kopf-Offset +20,
das der Hersteller entgegen der UEFI-Spezifikation auf 1 setzt (Zeile 809-810); die 26 Einträge à 128 Byte statt der
üblichen 128; die `0xFFFFFFFF` als Größe im Schutz-MBR (Zeile 823-826); die durchnummerierten Unique-GUIDs. Das ist
sorgfältige Arbeit - der Wagenrücklauf ist ein Ausrutscher, kein Missverständnis.

### 3.3 Der Rückspielweg findet, was er braucht

Der Trockenlauf gegen das echte `update.img` (1,9 GB) läuft durch, ohne eine einzige fehlende Quelle. Der IMAGEWTY-Leser
erkennt Kopfversion `0x0415`, liest alle 53 Dateien, meldet die 512-Byte-Abweichung zwischen `image_size` im Kopf und der
Dateigröße als **Beobachtung, nicht als Fehler** - genau die richtige Tonlage. Die Größenprüfung gegen die Partitionsgröße
(Zeilen 747-749) ist vorhanden und würde eine zu große Quelldatei abfangen, bevor sie in die Nachbarpartition liefe.

### 3.4 Die Lesewege fassen nichts an

`--nur-abzug` und `--dry-run` öffnen das Gerät über Zeile 532 (`schreiben = not (args.dry_run or args.nur_abzug)`)
nur lesend; ein späterer Schreibversuch scheitert dann an Zeile 139-140. Der Extraktor hat überhaupt keinen Pfad auf ein
Blockgerät. Die Bestätigungsabfragen verlangen ein getipptes `ja`, und `frage()` gibt bei nicht-interaktivem Aufruf die
Vorgabe zurück - die für alle drei Schreibabfragen `"nein"` lautet (Zeilen 553, 569, 605). Ein versehentlicher Aufruf aus
einem Skript schreibt nichts.

### 3.5 Der Bash-Installer 0.4 ist an den Schutzstellen strenger

`hy310-install.sh` prüft, was der PC-Installer annimmt: Zeilen 452-456 lehnen jede Partition ab, die die Sperrzone auch nur
berührt, ohne sie exakt zu treffen; Zeilen 437-447 kürzen und melden, wenn eine Partition über `LastUsableLBA` hinausreicht;
Zeile 439-441 fängt Überlappungen mit dem Vorgänger. Zusammen mit dem Rückvergleich der geschriebenen Tabelle (`S41` §2.1)
ist das die höhere Messlatte. Wo die beiden Installer sich widersprechen, hat 0.4 recht.

### 3.6 `S45` ist ehrlich über die eigenen Grenzen

Der Bericht listet fünf Restpunkte, darunter die beiden, die ich unabhängig gefunden habe (fehlende `metadata_csum`-Prüfung,
fehlende `INCOMPAT_RECOVER`-Warnung), und schreibt in §4.3 sogar auf, dass der eigene Vollabzug das `recover`-Flag trägt.
Das ist die Art Bericht, gegen die man prüfen kann.

---

## 4. Vor dem Flash auf Marcos Gerät zwingend zu klären

Abhakliste. Die Reihenfolge ist die des Ablaufs, nicht die der Schwere.

- [ ] **Aushängen.** `udisksctl unmount -b /dev/sda5` und `-b /dev/sda6`, danach `mount | grep sda` → leer. Am besten
      `udisks` für die Dauer des Laufs stilllegen. (**K2**)
- [ ] **Ziel benennen und nachsehen.** `lsblk -o NAME,SIZE,RM` prüfen, dass genau **ein** Gerät 15 269 888 Sektoren hat,
      und den Installer mit explizitem `--device /dev/sdX` fahren, statt ihn suchen zu lassen. (**K1**)
- [ ] **`sunxi-fel` klären.** Welche Binärdatei? Trägt sie den Tür-Patch (`fel_door_addr`)? `sunxi-fel version` von Hand
      laufen lassen und prüfen, dass `H713` in der Ausgabe steht - sonst bricht Zeile 500 ab. Pfad per `--sunxi-fel`
      mitgeben. (**B10**)
- [ ] **Vollabzug zuerst, und zwar von Hand geprüft.** `--abzug voll`, danach die Datei ein zweites Mal gegen `/dev/sda`
      vergleichen (`cmp` reicht), weil das Skript es nicht tut. Erst dann weiter. (**B5**, **B4**)
- [ ] **Entscheiden, was mit `secure-storage.bin` geschieht.** Nach dem Abzug `chmod 600` und einen Ort außerhalb des
      Repos. Nicht in Issues, nicht in Sicherungen, die das Haus verlassen. (**A2**)
- [ ] **Vor `--restore-stock`: den Wagenrücklauf entscheiden.** Entweder der Fix in Zeile 690 (ein `.strip()`), oder der
      Rückweg auf Android ist keiner. Danach den Byte-Vergleich gegen `emmc-first-300mb.bin` wiederholen - er ist in
      §B3 als Rezept beschrieben und dauert Sekunden. (**B3**)
- [ ] **Klären, ob `--restore-stock` überhaupt der Weg ist**, oder ob `--restore` mit dem eigenen Vollabzug genügt.
      `--restore` hat den CRLF-Fehler nicht. Wenn das Ziel „wieder Android" ist, kommt zusätzlich **B8** dazu:
      `UDISK`, `metadata`, `frp`, `private` und die B-Slots bleiben mit Debian-Resten stehen und sollten vorher
      genullt werden. (**B8**)
- [ ] **Klären, womit neu installiert wird.** Ein `--abbild` gibt es nicht, und die Platzhalter-Funktionen sind nicht
      angeschlossen. Entweder der Bash-Installer 0.4 über Netboot (dann gilt `S41`), oder es fehlt noch ein
      Abbild-Bauer. Diese Frage sollte **vor** dem Zurücksetzen beantwortet sein, nicht danach. (**B6**)
- [ ] **SSH-Schlüssel.** Das gebaute Rootfs hat keinen (`ssh_key_eingebaut=nein`), der PC-Installer kann keinen
      nachreichen. Entweder Rootfs mit `--authorized-key` neu bauen oder eine serielle Konsole bereitlegen. (**B12**)
- [ ] **Backup-GPT.** Falls doch ein 1,2-GB-Abbild geschrieben wird: hinterher prüfen, ob die Sicherungstabelle am
      Plattenende stimmt (`sfdisk -V /dev/sda`), und **nicht** auf ein Reparaturangebot eines Werkzeugs eingehen - das
      würde die Android-Tabelle zurückholen. (**B7**)
- [ ] **Abbruchregel vorher festlegen.** Wenn während des Schreibens etwas schiefgeht: **nicht** den Strom ziehen und neu
      starten, sondern in FEL zurück. Das Skript sagt es nur an einer Stelle (Zeile 611); an allen anderen nicht.
      (**B15**)

---

## 5. Nachtrag: was daraufhin behoben wurde (10.09., Hauptsitzung)

Der Bericht wurde von einem Prüfer geschrieben, der ausdrücklich **nicht** reparieren sollte. Hier steht, was danach
tatsächlich geändert wurde - jeweils mit dem Befundkürzel aus §2.

| Befund | Was war | Was jetzt gilt |
|---|---|---|
| **B3** Wagenrücklauf | `sys_partition.fex` hat CRLF; der Ausdruck zog `\r` in jeden ungequoteten Wert, alle 26 GPT-Namen trugen ein unsichtbares `U+000D` | Ausdruck schneidet `\r` ab, zusätzlich `.strip()` je Wert. **Gegenprobe wiederholt: Schutz-MBR, GPT-Kopf und alle 26 Einträge byteidentisch mit `emmc-first-300mb.bin`**, keine unsichtbaren Zeichen mehr |
| **K2** kein `O_EXCL`, keine Einhänge-Prüfung | die Zielpartitionen waren **in diesem Moment** beschreibbar eingehängt (`/media/user/hy310-boot`, `…-rootfs`) | neue Funktion `eingehaengt()`; `Platte(schreiben=True)` prüft `/proc/self/mounts`, bricht mit Klartext ab und öffnet mit `O_EXCL`; `EBUSY` wird als „belegt" gemeldet. Die beiden Einhängungen wurden ausgehängt |
| **K1** Laufwerk nur an der Sektorzahl | `removable` wurde gelesen und verworfen, bei mehreren Treffern still der erste genommen | `removable` wird jetzt gefordert; neue Funktion `ist_unser_geraet()` liest die GPT und verlangt **unser Layout** (`hy310-*`) oder das **Stock-Layout** (`bootloader_a` + `super`); mehrere Treffer ⇒ Abbruch mit Aufforderung zu `--device`; fehlende Leserechte werden als solche gemeldet, nicht als „kein Beamer" |
| **B5** Vollabzug nie zurückgelesen | ein ungeprüfter Abzug ist kein Failsafe | `pruefe_abzug()` vergleicht acht Stellen gegen das Gerät (Anfang, LBA 16, 2048, 12288, 14336, 16384, Ende, dazu Zufall). Weicht etwas ab, bricht der Lauf ab, **bevor** irgendetwas geschrieben wird |
| **B2** `--restore`/`--restore-stock` ohne Abzug | widersprach Plan 110 §2 | beide ziehen jetzt zwingend den kleinen Abzug samt Manifest, bevor sie schreiben |
| **B15** Abbruchregel nur an einer Stelle | | neue Funktion `bestaetigen()`: an **jeder** Schreibstelle dieselbe Warnung, die Beta-Ansage und die Regel „nicht den Strom ziehen, sondern zurück in FEL". Verlangt getipptes `JA`, kein `[j/N]` |
| **A2** Schlüsselmaterial mit Standardrechten | | `secure-storage.bin` und die übrigen Rohabzüge werden mit `chmod 600` abgelegt |

**Bewusst offen, weil es Entscheidungen sind und keine Fehler:**

- **B6** Der Installationsweg fehlt weiterhin: `--tabelle` wird nicht gelesen, `platzhalter_fuellen()` nicht aufgerufen,
  einen Abbild-Bauer gibt es nicht. Das ist der nächste Bauschritt (Plan 110 §5, Punkt 3), nicht ein Versehen. Der
  Installer sagt jetzt ausdrücklich, dass es ihn noch nicht gibt.
- **B8** `--restore-stock` lässt `UDISK`, `metadata`, `frp`, `private` und die B-Slots stehen. Für „wieder Android" gehört
  das genullt - die Entscheidung, ob das Werkzeug das tun soll, steht aus.
- **B10** `sunxi-fel` wird unter seinem Namen gesucht; welche Binärdatei mit welchen Patches mitgeliefert wird, ist Teil
  des Release-Pakets und noch nicht entschieden.
- **B7** Backup-GPT am Plattenende beim 1,2-GB-Abbild: hängt am Abbild-Bauer.
- Der **Windows-Pfad** ist unverändert ungetestet (`_get_osfhandle` liegt nicht in `kernel32`). Er bleibt als Entwurf
  stehen, bis jemand ihn dort ausführt.

**Nicht angetastet:** die Sperre um den Secure Storage. Der Prüfer hat sie gegen alle Startsektoren von 12285 bis 14339
mit Längen 1-6 und dem echten 4-MiB-Stück durchgerechnet - 0 Fehler. Daran wurde nichts geändert.
