# S45 — `hy310-extract` ohne `debugfs`: ein ext4-Leser in reinem Python

**Auftrag:** `hy310-extract` von der externen Abhängigkeit `debugfs` (e2fsprogs) befreien, damit der Installationsweg
auch unter **Windows** läuft ([`110-plan-installationsweg.md`](../110-plan-installationsweg.md)). Vorbild und Vorgänger:
[`S42-r2-extract.md`](S42-r2-extract.md) (Aufbau, Geräteprofile, Manifest-Format, §9 Nachtrag).
**Regeln eingehalten:** kein Gerät angefasst (der HY310 hing als USB-Laufwerk am PC — es wurde nichts darauf geschrieben und
nichts davon gelesen), kein Netz, keine Git-Commits; geschrieben nur in `analyse/release/arbeit/r2-extract/` und in diesen
Bericht. `re/`, `mainline/`, `userspace/` und `/opt/Projekte/Beamer/` blieben unverändert (nur lesend geöffnet).
Zwischenstände lagen in `r2-extract/tmp/` und sind gelöscht.

**Ergebnis in einem Satz:** Der Leser liegt als `class Ext4` in `hy310-extract` (Werkzeug **0.4**), alle sieben Testläufe
sind durch, und **jede** Ausgabe ist byteidentisch mit der von Werkzeug 0.3 — auch das `MANIFEST.json` bis auf die Felder
`werkzeug` und `zeit`. `debugfs` wird nicht mehr gebraucht; der alte Weg bleibt als `--use-debugfs` erhalten und liefert
dieselben Bytes.

| Lieferung | Was |
|---|---|
| `analyse/release/arbeit/r2-extract/hy310-extract` | Werkzeug 0.4, 3 066 Zeilen (vorher 2 631); neu: `class Ext4Basis`, `class Ext4` (Python-Leser), `class Ext4Debugfs` (alter Weg), Option `--use-debugfs` |
| `analyse/release/arbeit/r2-extract/README.md` | Voraussetzungen neu („nur Standardbibliothek, keine externen Programme"), Abschnitt „Der ext4-Leser (0.4, S45)" |
| dieser Bericht | Befunde am echten Dateisystem, Aufbau des Lesers, Testläufe, Abnahme, was offen bleibt |

**Wichtigste Befunde vorab:**

1. Das Vendor-Dateisystem nutzt **ausschließlich Extents** — von 795 Inodes mit Daten hat **keines** indirekte Blöcke.
   Zwei Dateien haben einen **Extent-Baum der Tiefe 1** (`/etc/firmware/EXEC_KERNEL_IMAGE.bin` und `wcnmodem.bin`), Tiefe > 0
   kommt also wirklich vor; unsere elf Zieldateien liegen allerdings alle in Bäumen der Tiefe 0.
2. **`dir_index` trägt linear**: das Merkmal steht zwar im Superblock (`feature_compat 0x28`), aber **kein einziges**
   Verzeichnis der Vendor-Partition hat das Inode-Flag `EXT4_INDEX_FL` gesetzt. Zur Sicherheit wurde der Leser gegen ein
   Dateisystem *mit* Hash-Bäumen geprüft (unser eigenes `hy310-rootfs` im eMMC-Vollabzug, 9 Hash-Baum-Verzeichnisse):
   alle 7 424 Einträge stimmen mit `debugfs` überein. Linear reicht.
3. **Löcher sind Pflicht, nicht Kür:** ausgerechnet eine der acht PQ-Dateien ist sparse — `etc/tvconfig/tvpq.db` ist
   36 864 B groß, aber nur 28 672 B sind belegt. Ohne Lochbehandlung wäre die Datei 8 KiB zu kurz und der sha256 falsch.
4. Der Leser braucht **keine Zwischendatei** mehr. Der alte Weg musste die vendor-Partition erst als 114 372 608-B-Datei
   ablegen, weil `debugfs ?offset=` durch das Sparse-Abbild hindurch nicht funktioniert; der neue liest an Ort und Stelle
   und holt dafür nur **7,1 MB** aus der Quelle.

---

## 1. Was `debugfs` bisher tat und was ersetzt werden musste

Werkzeug 0.3 rief `debugfs -f - <dev>` mit drei Kommandos auf: `ls -p <pfad>` (Verzeichnis auflisten),
`dump -p <pfad> <ziel>` (Datei herausschreiben) und `stat <2>` (Probe, ob diese `debugfs`-Version `?offset=` kann).
Daraus gebaut waren `existiert()` und `gehe()` (Baumdurchlauf). Das Werkzeug braucht aus der vendor-Partition genau elf
Dateien plus einen vollständigen Baumdurchlauf für die Beobachtungen:

| Zweck | Pfade in der vendor-Partition |
|---|---|
| `hy310-edid.bin` | `/etc/tvconfig/HDMI_EDID_14.bin`, `/etc/tvconfig/HDMI_EDID_20.bin` |
| `msp-patch.bin` | `/lib/libmspsound.so` (Symbol `patch_msp`) |
| `pq/*` | die acht Dateien in `/etc/tvconfig/` |
| Gerätekennung | `/build.prop` |
| Projekt-ID (nur gemeldet) | `/etc/tvconfig/panel_config/panel_config.ini` |
| Beobachtungen | Baumdurchlauf `/` (Tiefe 6), `/lib/modules/*.ko`, `/etc/NOTICE.xml.gz` |

Der `?offset=`-Fall ist der Kern: die Partition liegt **nie** am Dateianfang, sondern als LP-Extent in einer
Android-Sparse-`super` in einem IMAGEWTY-Container. `Quelle.backing()` liefert dort `None`, weil der Bereich nicht
zusammenhängend in einer echten Datei liegt — deshalb legte 0.3 die Partition jedes Mal als Datei ab.

---

## 2. Befunde am echten Dateisystem

### 2.1 Superblock der vendor-Partition (HY310 `update.img`, `vendor_a`)

| Feld | Wert | Bedeutung für den Leser |
|---|---|---|
| Magic (0x438) | `0xEF53` | ext2/3/4 |
| `s_log_block_size` | 2 | Blockgröße **4096** |
| `s_blocks_count_lo` | 27 461 | 112 480 256 B Dateisystem in einer 114 372 608-B-Partition |
| `s_first_data_block` | 0 | Gruppendeskriptoren im Block 1 |
| `s_blocks_per_group` / `s_inodes_per_group` | 32 768 / 992 | genau **eine** Blockgruppe |
| `s_inodes_count` | 992 | davon 974 benutzt (46 Verzeichnisse, 749 Dateien, 179 Symlinks) |
| `s_inode_size` | 256 | `s_rev_level` 1 |
| `s_desc_size` | 0 | → **32-B-Deskriptoren** (kein `64bit`) |
| `feature_compat` | `0x28` | `ext_attr`, **`dir_index`** (siehe 2.3) |
| `feature_incompat` | `0x42` | `filetype`, **`extents`** — kein `64bit`, kein `meta_bg`, kein `inline_data`, keine Verschlüsselung |
| `feature_ro_compat` | `0x7b` | `sparse_super`, `large_file`, `huge_file`, `gdt_csum`, `dir_nlink`, `extra_isize`; **kein** `metadata_csum`, **kein** `bigalloc` |
| Label / UUID | `vendor` / `f6fef9d9-2cec-5e67-a9aa-7485e493cef0` | |

L018 unterscheidet sich nur in Größe und UUID; die Merkmalsbits sind dieselben (beide Läufe fehlerfrei, §4).

### 2.2 Extents ja, indirekte Blöcke nein

Vollständiger Durchlauf über alle 992 Inodes (`tmp/inodescan.py`, jetzt gelöscht — Zahlen hier festgehalten):

| Inode-Flags | Anzahl | Was das heißt |
|---|---|---|
| `0x80000` (`EXT4_EXTENTS_FL`) | **795** | alle Verzeichnisse und alle regulären Dateien |
| `0x0` | 179 | ausschließlich die Symlinks (alle „schnell", Ziel im Inode) |
| `0x1000` (`EXT4_INDEX_FL`) | **0** | kein Hash-Baum-Verzeichnis |

Extent-Kopf-Magic ist überall `0xF30A`. Verteilung der Baumtiefe: **793×Tiefe 0, 2×Tiefe 1**.

| Datei | Größe | Extents | Baumtiefe |
|---|---|---|---|
| `/etc/firmware/EXEC_KERNEL_IMAGE.bin` | 947 120 B | 7 | **1** |
| `/etc/firmware/wcnmodem.bin` | 947 120 B | 7 | **1** |
| `/lib/egl/libGLES_mali.so` (größte Datei) | 12 791 368 B | 1 | 0 |
| `/lib/libmspsound.so` (unsere) | 126 128 B | 1 | 0 |
| `/etc/tvconfig/pq_factory_extern.ini` (unsere) | 592 528 B | 1 | 0 |

**Der Leser kann beides** (Extents und indirekt), aber das Vendor-Dateisystem benutzt indirekte Blöcke nirgends. Der
indirekte Zweig wurde deshalb an einem eigens gebauten ext2 geprüft (§4.4).

### 2.3 `dir_index`: Merkmal gesetzt, aber nirgends benutzt

`feature_compat` hat Bit `0x20` (`dir_index`), doch **kein** Verzeichnis-Inode trägt `EXT4_INDEX_FL`. Selbst wenn es eines
täte, trägt der lineare Weg: die Knoten eines Hash-Baums tarnen sich als Verzeichniseinträge mit **Inode 0**, die ein
linearer Scan ohnehin überspringt, und die Blätter sind gewöhnliche Verzeichnisblöcke. Belegt am `hy310-rootfs` im
eMMC-Vollabzug (§4.3): 9 Verzeichnisse mit `EXT4_INDEX_FL`, 7 424 Einträge, **kein einziger Unterschied** zu `debugfs`.

### 2.4 Löcher (sparse) — 16 Dateien, davon eine von uns gebraucht

| Datei | Größe | belegt | Extents |
|---|---|---|---|
| **`/etc/tvconfig/tvpq.db`** | **36 864 B** | **28 672 B** | 1 |
| `/test/1920x1088_P010_1frame.yuv` | 6 266 880 B | 6 225 920 B | 2 |
| `/lib/optee_armtz/663d017b-….ta` | 1 619 584 B | 1 025 664 B | 3 |
| `/etc/display/mips/display.bin` | 1 256 216 B | 1 190 680 B | 2 |
| `/etc/firmware/EXEC_KERNEL_IMAGE.bin` | 947 120 B | 663 552 B | 7 |
| … 11 weitere | | | |

`tvpq.db` ist eine der acht PQ-Dateien: ihre Extent-Karte deckt nur die Blöcke 0–6, der Rest bis 36 864 B ist ein Loch und
muss als Nullen gelesen werden. Ihr sha256 `6b29d679…` stimmt mit dem Lauf von 0.3 überein — Lochbehandlung ist damit
nicht theoretisch, sondern Voraussetzung für die Abnahme.

### 2.5 Symlinks

Alle 179 Symlinks der vendor-Partition sind **schnelle** Symlinks (Ziel in den 60 Byte `i_block`, `i_blocks` = 0, Ziele
wie `toybox` mit 13 B). Für die elf Zieldateien wird kein Symlink gebraucht — der Lauf des Werkzeugs löst null Symlinks
auf. Trotzdem sind sie umgesetzt (Ziel im Inode **und** in Blöcken, relativ und absolut, `..`), sonst wäre der
Baumdurchlauf für die Beobachtungen nicht verlässlich; geprüft in §4.4/§4.5.

---

## 3. Der Leser (`class Ext4`, 400 Zeilen)

### 3.1 Aufbau

| Teil | Umsetzung |
|---|---|
| Eingang | eine `Quelle` — also **(Datei, Startoffset, Länge)**. Das ersetzt `?offset=` und funktioniert auch durch Sparse-Abbild und LP-Extent hindurch. Keine Zwischendatei, kein Mount, kein Root. |
| Superblock | bei 0x400; Magic, Blockgröße, Inodes/Gruppe, Inode-Größe, `s_desc_size`, `s_blocks_count_hi` bei `64bit`, alle drei Merkmalswörter |
| Merkmalsprüfung | `compression`, `encrypt`, `inline_data`, `meta_bg` (incompat) und `bigalloc` (ro_compat) werden **abgewiesen** statt still falsch gelesen — mit Hinweis auf `--use-debugfs` |
| Gruppendeskriptoren | Block `s_first_data_block + 1`; **32 B** normal, **≥ 64 B** bei `INCOMPAT_64BIT` (dann `bg_inode_table_hi`) |
| Inodes | Tabelle je Gruppe; `i_mode`, `i_size_lo/high`, `i_flags`, `i_blocks_lo`, `i_file_acl`, 60 B `i_block`. Größe wie `debugfs`: bei Verzeichnissen nur `i_size_lo`, sonst 64 Bit |
| Extents | Kopf-Magic `0xF30A`; Tiefe 0 = Blattextents (`ee_block`, `ee_len`, `ee_start_hi/lo`), Tiefe > 0 = Indexknoten, rekursiv. `ee_len > 32768` = **unbelegt** (fallocate) → wird wie ein Loch als Nullen gelesen |
| Indirekte Blöcke | `i_block[0..11]` direkt, `[12]` einfach, `[13]` doppelt, `[14]` dreifach indirekt, rekursiv, begrenzt durch die Dateigröße |
| Verzeichnisse | linear über alle Datenblöcke; `inode`, `rec_len`, `name_len`, `file_type`; Einträge mit Inode 0 übersprungen (das sind Polster **und** die Hash-Baum-Knoten); ohne `filetype`-Merkmal ist `name_len` 16 Bit |
| Pfade | ab Inode 2, Komponente für Komponente, `.` und `..` inbegriffen; Symlinks werden gefolgt (schnell = `i_block`, langsam = Datenblöcke), absolut wie relativ, höchstens 16 Stufen (sonst „Symlinks im Kreis") |
| Dateiinhalt | Blockläufe in einen mit Nullen vorbelegten Puffer der Dateigröße; **Löcher bleiben Nullen** — sparse fällt damit von selbst richtig aus |
| Schutz | Blöcke außerhalb des Dateisystems und eine zu kurze Quelle werden gemeldet (`self.probleme` und Protokoll), nicht verschwiegen |

Nicht umgesetzt (und nicht nötig): Schreiben, Journal-Wiedergabe, Verschlüsselung, `inline_data`, `bigalloc`, `meta_bg`.

### 3.2 Warum eine gemeinsame Oberklasse

`existiert()` und `gehe()` stehen jetzt in `class Ext4Basis`, aus der **beide** Leser erben. Grund: die Ausgabe des
Werkzeugs hängt an der Reihenfolge, in der `gehe()` läuft (`beobachtungen.aic8800_module` etwa steht in Baumreihenfolge im
Manifest). Mit einer gemeinsamen Umsetzung ist diese Reihenfolge garantiert dieselbe, egal welcher Leser darunter liegt —
was die byteidentischen Manifeste in §4.1 erst möglich macht.

Ein Eintrag ist in beiden Wegen `{'name', 'ino', 'mode', 'size', 'typ'}`; `size` ist bei Verzeichnissen 0, weil
`debugfs ls -p` das Feld dort leer lässt.

### 3.3 Ein Unterschied — zugunsten des neuen Lesers

`debugfs ls -p` gibt **leere Polstereinträge mit Inode 0** als Dateien aus. Im `hy310-rootfs` liefert
`ls -p /lost+found` drei Zeilen `/0/000000/0/0//0/`; der alte Weg hätte daraus drei Einträge mit leerem Namen gemacht.
Der neue Leser überspringt Inode 0. In der vendor-Partition kommt der Fall nicht vor (deshalb sind alle Ausgaben dort
byteidentisch), im rootfs schon — das ist der **einzige** Unterschied zwischen beiden Wegen in allen Vergleichen.

---

## 4. Testläufe (10.09.2026, Werkzeug 0.4)

### 4.1 Die Testfälle aus dem Auftrag

Verglichen wurde jeweils gegen die Ausgabe von Werkzeug 0.3 aus `out-hy310/`, `out-hy310-rooted/`, `out-l018/`,
`out-fexdir/`, `out-emmc/` — alle Artefaktdateien per sha256, dazu das `MANIFEST.json` ohne die Felder `werkzeug` und
`zeit`.

| # | Eingang | Exit | Dauer | Artefakte | Abnahme |
|---|---|---|---|---|---|
| 1 | `re/vendor/HY310/update.img` | **0** | 2,5 s | 30 | **30/30 byteidentisch**, Manifest gleich |
| 2 | `re/vendor/HY310/update_rooted.img` | **0** | 2,5 s | 30 | **30/30 byteidentisch**, Manifest gleich |
| 3 | `/opt/Projekte/Beamer/L018/update.img` | **0** | 2,5 s | 30 | **30/30 byteidentisch**, Manifest gleich |
| 4 | `--fex-dir re/vendor/HY310/extracted` | **0** | 2,1 s | 30 | **30/30 byteidentisch**, Manifest gleich |
| 5 | `re/device-dumps/emmc-first-300mb.bin` | **1** | 0,7 s | 20 | **20/20 byteidentisch**, Manifest gleich (Exit 1 wie bisher: `super` liegt nicht in den ersten 300 MiB) |
| 6 | `re/device-dumps/emmc-voll-HY310-dev-20260910.img` (7,3 GB) | **1** | 11,7 s | 1 | neuer Fall, siehe §4.3 |
| 7 | dasselbe wie #1, aber `--use-debugfs` | **0** | 2,6 s | 30 | **30/30 byteidentisch mit #1**, Manifest gleich |

Zusätzlich: `--part vendor=<rohe ext4-Datei>` → Exit 1 (kein `scp`, kein `bootloader` — wie erwartet), aber EDID
(`70d10294…`), MSP-Patch (`8e31db19…`) und alle acht PQ-Dateien referenzgleich.

**Die drei Abnahme-Hashes aus dem Auftrag**, direkt aus Lauf #1:

```
d41731fa783dace3070264397064b28e2359a27b9e4708f3f7d40f1c3d876b7e  lib/firmware/h713-arisc.bin
70d10294e3f1f1ba3aceaf684c90d2dcdcafc9ba4ed265956520bdf4adfb60ef  lib/firmware/hy310-edid.bin
8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5  lib/firmware/h713/msp-patch.bin
```

Was sich am `BERICHT.txt` ändert (bewusst, kein Fehler): die Kopfzeile mit der Werkzeugversion, die entfallenen Zeilen
über den Zwischenstand, und eine neue Zeile `ext4-Leser: …` mit der Statistik des Lesers.

### 4.2 Kein `debugfs` im Pfad — die Windows-Probe

```
$ env PATH=/nonexistent /usr/bin/python3 ./hy310-extract re/vendor/HY310/update.img -o … -q
EXIT=0
70d10294…  hy310-edid.bin      8e31db19…  msp-patch.bin      d41731fa…  h713-arisc.bin
```

Mit leerem `PATH` (kein e2fsprogs, kein externes Programm überhaupt erreichbar) läuft das Werkzeug durch und liefert die
Referenz-Hashes. Umgekehrt sagt `--use-debugfs` ohne e2fsprogs sauber ab:
`FEHLER: debugfs (e2fsprogs) nicht gefunden — nötig für --use-debugfs (ohne die Option liest hy310-extract ext4 selbst)`,
Exit 2. Damit ist die Windows-Voraussetzung aus Plan 110 erfüllt: Python ≥ 3.10 und sonst nichts.

### 4.3 Der eMMC-Vollabzug (neu) — und eine Korrektur zum Auftrag

`emmc-voll-HY310-dev-20260910.img` (7 818 182 656 B, sha256 `3c159da1…`) ist **nach** dem Umbau auf Layout v3 gezogen.
Der Auftrag nahm an, er tauge als Test für `bootloader_b` — **das trifft nicht zu**: die GPT enthält nur noch unsere
sechs Partitionen, die Android-Partitionen sind weg.

```
GPT: Kopf-CRC ok, Tabellen-CRC ok, 26 Einträge à 128 B ab LBA 2, nutzbar 16..15269854
Partitionen: hy310-spl@16+64, hy310-uboot@2048+10240, hy310-keys@12288+2048,
             hy310-env@14336+2048, hy310-boot@16384+262144, hy310-rootfs@278528+14991327
WARNUNG: bootloader_b liegt nicht (vollständig) im Dump
WARNUNG: bootloader_a liegt nicht (vollständig) im Dump
WARNUNG: 'super' liegt nicht (vollständig) im Dump — kein EDID/MSP/PQ aus diesem Eingang
Dump LBA 32800: sunxi-package @0x1004000 … Prüfsumme FALSCH (add_sum 0xa3bb16c2, gerechnet 0x0f5b6eaf)
```

Der Lauf endet mit **Exit 1** („unbekanntes Image, Best-Effort") und legt genau ein Artefakt ab: den `scp`-Blob aus dem
angeschlagenen Paket bei LBA 32800, sha256 `5abb775c…` mit „Prüfung FEHLER" (kein `CPUs`-Kopf, kein ARISC-Versionsstring,
Reset-Vektor `l.j 0x100`). Das ist richtiges Verhalten für ein Abbild, in dem der Stock-Bootbereich nicht mehr intakt ist —
also **kein** Test für `bootloader_b`, wohl aber einer für den Roh-Dump-Eingang und für ein Image, dem kein Profil passt.

**Was der Abzug stattdessen hergibt — der bessere ext4-Test:** seine `hy310-rootfs`-Partition (LBA 278528,
7 675 559 424 B) ist ein von *uns* angelegtes ext4 und damit ganz anders gebaut als das Vendor-Dateisystem:

| Merkmal | vendor (Stock) | hy310-rootfs (unser) |
|---|---|---|
| Blockgruppen | 1 | **58** |
| Gruppendeskriptor | 32 B | **64 B (`INCOMPAT_64BIT`)** |
| `feature_incompat` | `0x42` | **`0x22c6`** (`filetype`, `recover`, `extents`, `64bit`, `flex_bg`, `csum_seed`) |
| `feature_ro_compat` | `0x7b` | **`0x1046b`** (u. a. `metadata_csum`, `orphan_present`) |
| Inodes | 992 | 468 640 |
| Verzeichnisse mit `dir_index` | 0 | **9** |

Der Vergleich (Leser gegen `debugfs …?offset=142606336`, also derselbe `--offset`-Fall):

```
meine Einträge:    7424
debugfs-Einträge:  7425   (Differenz: 3 Polstereinträge mit Inode 0 in /lost+found, dazu §3.3)
Baumvergleich (Name, Typ, Größe, Inode-Nummer):  1 Unterschied — genau dieser
Inhalte: 126 Stichproben (bis 13 519 639 B) sha256-gleich, 0 ungleich
```

Damit sind der 64-Bit-Deskriptor-Zweig, mehrere Blockgruppen und Hash-Baum-Verzeichnisse belegt. Nebenbefund: das
Dateisystem trägt `recover` — das Journal ist unabgeschlossen (der Abzug entstand im laufenden Betrieb). Der Leser spielt
kein Journal zurück; `debugfs` tut es auch nicht, und beide sehen denselben Stand.

### 4.4 Gegenprobe an einem selbst gebauten ext2 (indirekte Blöcke)

Weil das Vendor-Dateisystem keine indirekten Blöcke hat, wurde ein 8-MiB-ext2 mit `mke2fs -t ext2 -b 1024 -I 128
-O ^dir_index -d …` gebaut (128-B-Inodes, 1024-B-Blöcke, `feature_incompat 0x2` — **kein** `extents`) und in eine größere
Datei eingebettet (1 234 567 B Vorlauf, 4096 B Nachlauf), damit auch der Offset-Fall mitgeprüft wird:

| Prüfling | Ergebnis |
|---|---|
| `/gross.bin` 1 500 000 B = 1 465 Blöcke | **doppelt indirekt**, sha256 gleich |
| `/mittel.bin` 300 000 B = 293 Blöcke | einfach indirekt, sha256 gleich |
| `/klein.bin` 900 B | direkt, sha256 gleich |
| `/sparse.bin` 1 000 000 B, nur ein Block belegt | **Loch über fast die ganze Datei**, sha256 gleich |
| `/unter/link-kurz` → `../../gross.bin` | relatives Ziel richtig, Lesen **durch** den Link gleich |
| `/unter/link-absolut` → `/unter/tief/liesmich.md` | absolutes Ziel richtig, Lesen durch den Link gleich |
| `/unter/tief/../../klein.bin` | löst auf denselben Inode auf wie `/klein.bin` |
| Statistik | „0 mit Extents, 8 indirekt" — der indirekte Zweig war wirklich in Betrieb |

### 4.5 Langsame Symlinks (Ziel in einem Block)

Alle Vendor-Symlinks sind schnell; für den anderen Zweig wurde ein ext4 mit einem 104 Zeichen langen Symlink-Ziel gebaut:
`Symlink-Inode 16, Größe 104, i_blocks 2, schnell? False` → Ziel richtig gelesen, Lesen durch den Link byteidentisch mit
dem Original. Statistik: „0+2 Symlinks (schnell+in Blöcken)".

### 4.6 Vollständiger Abgleich des ganzen Vendor-Dateisystems

Nicht nur die elf Zieldateien, sondern **alles**: `debugfs -R "rdump / ref"` gegen den Python-Leser.

```
Dateien:         meine 749  ref 749
Symlinks:        meine 179  ref 179     (alle Ziele zeichengleich)
Verzeichnisse:   meine  45  ref  45
Inhalte gleich:  749/749     Fehler gesamt 0     Laufzeit 0,4 s
```

### 4.7 Aufwand

| | Werkzeug 0.3 (`debugfs`) | Werkzeug 0.4 (Python) |
|---|---|---|
| Zwischendatei | **114 372 608 B** (`tmp/vendor.ext4`) | **0 B** |
| aus der Quelle gelesen | die ganze Partition | **7 098 368 B** |
| externe Programme | `debugfs` | keine |
| Laufzeit HY310 `update.img` | 2,6 s | 2,5 s (davon 2,2 s sha256 über die 1,9-GB-Eingangsdatei) |

Statistikzeile aus `BERICHT.txt` (Lauf #1), die der Leser selbst schreibt:

```
ext4-Leser: 1 Gruppe(n) à 32768 Blöcke, 992 Inodes; Inode-Größe 256, Deskriptor 32 B, 992 Inodes,
UUID f6fef9d92cec5e67a9aa7485e493cef0; gelesen: 974 Inodes (795 mit Extents, 0 indirekt), 144 Extents
in 142 Knoten, Baumtiefe max 0, 0 unbelegt, 46 Verzeichnisse (0 mit dir_index-Flag), 0+0 Symlinks
(schnell+in Blöcken), 1 Dateien mit Löchern, 7098368 B aus der Quelle geholt
```

---

## 5. Was offen bleibt

1. **Kein Windows-Lauf.** Geprüft ist nur, dass keinerlei externes Programm mehr gebraucht wird (§4.2) und dass alles über
   `pathlib`/`struct`/`hashlib` läuft. Ein echter Lauf unter Windows steht aus; verdächtig wären dort allenfalls
   Pfadtrennzeichen in der **Ausgabe** (`ablegen()` nutzt `Path`, sollte passen) und die Sonderzeichen der 8.3-FAT-Namen
   im Protokoll (Konsolen-Codepage).
2. **`metadata_csum` wird nicht geprüft.** Der Leser rechnet keine Prüfsummen über Gruppendeskriptoren, Inodes,
   Verzeichnisblöcke oder Extent-Bäume nach. Ein beschädigtes Abbild würde er stillschweigend so lesen, wie es dasteht
   (`debugfs` tut ohne `-c` dasselbe). Für unseren Zweck reicht es, weil jedes Artefakt hinterher gegen sha256-Referenzen
   fällt; als Erweiterung wäre `metadata_csum` aber die naheliegendste.
3. **Journal-Wiedergabe fehlt.** Fällt bei den Stock-Abbildern nicht auf (sauber ausgehängt); der eMMC-Vollabzug trägt
   `recover` (§4.3). Wer aus einem im Betrieb gezogenen Abzug liest, sieht den Stand **vor** dem Journal — wie bei
   `debugfs` auch. Der Leser sagt das derzeit nicht laut; eine Warnung bei `INCOMPAT_RECOVER` wäre eine Zeile Aufwand.
4. **`erofs`/`f2fs` weiterhin nicht unterstützt** (unverändert gegenüber 0.3). Beide vorliegenden Geräte haben ext4-vendor;
   ein drittes Gerät mit erofs würde sauber abgewiesen.
5. **`inline_data`, `bigalloc`, `meta_bg`, Verschlüsselung** werden erkannt und abgewiesen, nicht gelesen. Kein
   vorliegendes Abbild nutzt eines davon.
6. **Der eMMC-Vollabzug taugt nicht als `bootloader_b`-Test** (§4.3). Wer den Weg `bootloader_b` → `boot/mips/*` aus einem
   Roh-Dump prüfen will, braucht `emmc-first-300mb.bin` (Lauf #5) oder einen Abzug von vor dem Umbau auf Layout v3.

---

## 6. Dateien

| Datei | Änderung |
|---|---|
| `analyse/release/arbeit/r2-extract/hy310-extract` | 0.3 → **0.4**: `class Ext4Basis` (gemeinsame Oberfläche), `class Ext4` (neuer Leser, ~400 Zeilen), `class Ext4Debugfs` (der alte Weg, unverändert in der Sache), Option `--use-debugfs`, Statistikzeile im Protokoll, Kopfkommentar |
| `analyse/release/arbeit/r2-extract/README.md` | „Voraussetzungen" neu, Abschnitt „Der ext4-Leser (0.4, S45)", `--use-debugfs` bei den Optionen, zwei Stellen zu „ext4 über debugfs" berichtigt |
| `doku/nachtlog/S45-ext4-leser.md` | dieser Bericht |
| `analyse/release/arbeit/r2-extract/tmp/` | Zwischenstände (Vergleichsskripte, entpacktes Vendor-Abbild, Testdateisysteme) — **gelöscht** |

Unverändert: `re/`, `mainline/`, `userspace/`, `/opt/Projekte/Beamer/`, die vorhandenen Ausgabeordner `out-*` von
Werkzeug 0.3 (sie dienten als Vergleichsgrundlage und wurden nur gelesen).
