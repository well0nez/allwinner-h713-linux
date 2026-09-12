# S42 — R2 `hy310-extract`: proprietäre Teile aus dem Firmware-Image ziehen

**Auftrag:** `analyse/release/arbeit/r2-extract/AUFTRAG.md`, Plan [`105`](../105-plan-release.md) §1.1/§2 (R2).
**Regeln eingehalten:** kein Board, kein Netz, kein Kernelbau; geschrieben nur in `analyse/release/arbeit/r2-extract/` und in diesen Bericht.
Keine APKs, kein Android-System kopiert; HDCP-/DRM-Material nicht angefasst, aic8800-Firmware nur benannt.
**Stand 10.09.2026, Ende der 90 Minuten:** Werkzeug liegt und ist gegen alle vier Eingänge gelaufen. HY310 `update.img` liefert die drei
Referenz-Hashes, `update_rooted.img` byteidentische Ausgaben, der Roh-Dump den referenzgleichen `scp.bin`, L018 eine Abweichungsliste.
**Nachtrag 10.09. 01:10 (§8):** L018 ist ein **eigenes Gerät** (Profil `l018`, Werkzeug 0.2) — L018 endet jetzt mit Exit 0; die
Aussagen zu L018 in §2.3, §3 und §4 beschreiben das Werkzeug 0.1.

Lieferung:

| Datei | Zweck |
|---|---|
| `analyse/release/arbeit/r2-extract/hy310-extract` | das Werkzeug: Python 3, Standardbibliothek, `debugfs` für ext4 (1 730 Zeilen inkl. Kommentare) |
| `analyse/release/arbeit/r2-extract/README.md` | Nutzung, Voraussetzungen, was es nicht kann, Formatnotizen |
| `analyse/release/arbeit/r2-extract/out-hy310/`, `out-hy310-rooted/`, `out-l018/`, `out-emmc/`, `out-fexdir/`, `out-parts-l018/` | die Testläufe: `lib/firmware/…`, `pq/…`, `MANIFEST.json`, `BERICHT.txt` (Protokoll jedes Laufs) |
| dieser Bericht | Formatbefunde, Entscheidungen, Testausgaben, L018, Beobachtungen, Risiken, offene Fragen |

**Wichtigste Befunde vorab:**

1. Die IMAGEWTY-Dateitabelle ist **nicht** RC6-verschleiert. Was ab 0x60 „nicht nach Klartext aussah", ist ein Füllmuster (n² mod 256);
   die Tabelle beginnt bei 0x400 im Klartext. Das Skript liest direkt aus `update.img`, die alten `extracted/`-Ordner braucht es nicht.
2. `scp.bin` (`d41731fa…`), `hy310-edid.bin` (`70d10294…`) und `msp-patch.bin` (`8e31db19…`) kommen **alle drei** aus `update.img` heraus,
   `scp.bin` außerdem referenzgleich aus dem Roh-Dump (dort zweimal, LBA 24576 und 32800, identisch).
3. **L018 ist dasselbe Allwinner-Referenzdesign** (`h713_tuna_p3`, Android 11 `RP1A.201005.006`), nur zwei Monate älter gebaut
   (14.05. statt 24.07.2025). EDID, MSP-Patchstrom, `libmspsound.so` und alle acht PQ-Dateien sind **byteidentisch** mit HY310;
   verschieden sind nur `scp` (gleiche Version `00.00.00.09`, anderes Build-Datum), `u-boot` und `dtb` (73 216 statt 73 728 B).
4. Zur **aic8800-Firmware** gibt es im ganzen Vendor-Abbild **keine Lizenzangabe** (weder Notice-Datei noch String in der Firmware);
   nur die Kernelmodule tragen `license=GPL`. Damit bleibt sie „nicht enthalten" (§5).

---

## 1. Formatbefunde

### 1.1 IMAGEWTY-Container — Dateitabelle ist Klartext

Befund an `update.img` (HY310) und `update.img` (L018):

- Kopf 0x60 Byte, Klartext: `IMAGEWTY`, `header_version` = **0x0415** (HY310) bzw. **0x0300** (L018), `header_size` 0x60,
  `ram_base` 0x04d00000, `version` 0x00100234, **`image_size` als u64** bei 0x18, `image_header_size` 0x400, `pid` 0x1234, `vid` 0x8743,
  `hardware_id`/`firmware_id` 0x100, `num_files` bei 0x3c (**53** bzw. **50**).
- Bereich 0x60–0x3ff: Füllmuster `n² mod 256` (0,1,4,9,16,25,…) plus Konstante je Byteposition mod 4 — **kein Chiffrat**, keine Nutzdaten.
- Dateitabelle ab **0x400**, 1024 B je Eintrag, Klartext (v3-Layout wie in `awimage`): `filename_len` (0x100), `total_header_size` (0x400),
  `maintype[8]`, `subtype[16]`, u32, `filename[256]` ab 0x24, **`stored_length` @0x124, `original_length` @0x12c, `offset` @0x134**
  (mein erster Versuch las 0x120/0x128/0x130 — die Nullen davor sind Polster, die Tabelle endet bei 0x124).
- Die `_imagewty_meta.bin` im `extracted/`-Ordner ist derselbe Kopf mit **genullten** Längen/Offsets; deshalb liest das Skript nur aus dem Image.
- Dateiinhalte unverschlüsselt: `boot_package.fex` aus dem Image ist byteidentisch mit `extracted/boot_package.fex`.
- HY310: `image_size` im Kopf ist um **+512 B** größer als die Datei; die Nutzdaten enden exakt an der Dateigröße (0x71bac600). Nur Beobachtung,
  nichts fehlt. L018: Kopf und Datei stimmen überein.
- Einträge, die uns interessieren: `boot_package.fex` (`12345678/BOOTPKG-00000000`), `super.fex` (`RFSFAT16/SUPER_FEX0000000`),
  `toc1.fex`/`toc0.fex` sind **8-Byte-Platzhalter** (kein Secure-Boot-TOC), `arisc.fex` 6 B (Platzhalter).

### 1.2 TOC1-Bootpaket = `sunxi-package`

`boot_package.fex` (1 245 184 B) und im Roh-Dump die Bereiche **LBA 24576 (0xC00000) und LBA 32800 (0x1004000)** — byteidentisch:

```
name[16] "sunxi-package"   magic 0x89119800   add_sum 0xa3bb16c2   items_nr 5   valid_len 0x130000   end "MIE;"
Item (0x170 B): name[64], data_offset, data_len, encrypt, type, run_addr, index, reserved[69], end "IIE;"
  u-boot  0x000800 638976   monitor 0x09c800 66060   scp 0x0acc00 176132   optee 0x0d8000 275328   dtb 0x11b400 73728
```

Prüfsumme: Summe aller u32 über `valid_len`, `add_sum` durch den Stempel `0x5F0A6C39` ersetzt — ergibt `0xa3bb16c2`, **stimmt** (bei allen
Eingängen). `scp` daraus: 176 132 B, sha256 `d41731fa…` = **Referenz**.

**Korrektur zu `analyse/arisc/BEFUND.md`:** dort heißt es, das Paket liege in `bootloader_a.bin` bei +0x4000. Im Roh-Dump des Geräts ist
p1 `bootloader_a` (LBA 73728) ein **FAT16-Dateisystem** (wie p2), das Paket liegt dort nicht bei +0x4000. Das Paket steht **roh vor der
ersten Partition** an den beiden LBAs oben (105 §1.1 hatte das schon richtig). Die März-Datei `bootloader_a.bin` war offenbar ein Dump des
Rohbereichs, nicht der Partition.

### 1.3 `super.fex` = Android-Sparse mit LP-Metadaten

- Sparse-Kopf: Magic `0xed26ff3a`, v1.0, Kopf 28 B, Chunk-Kopf 12 B, Block 4096, **524 288 Blöcke = 2 GiB** logisch;
  HY310 4964 Chunks (RAW 2483, FILL 2477, DONT_CARE 4), L018 5006 Chunks.
- Logisches Abbild: LP-Geometrie bei 4096 (Magic `gDla`, 52 B, sha256 ok), Backup bei 8192, Metadaten bei 12288 (Magic `0PLA`, **v10.2**,
  `header_size` 256, `metadata_max_size` 65536, 3 Slots), Kopf- und Tabellen-sha256 stimmen. Sechs Partitionen, drei belegt (A/B-Layout,
  `_b` leer):

| LP-Partition | HY310 | L018 | Extent (512-B-Sektoren in `super`) |
|---|---|---|---|
| `system_a` | 980 652 032 B | 978 923 520 B | 2048 + 1 915 336 / 1 911 960 |
| `vendor_a` | **114 372 608 B** | **114 466 816 B** | 1 918 976 + 223 384 / 1 914 880 + 223 568 |
| `product_a` | 538 517 504 B | 508 526 592 B | 2 144 256 + 1 051 792 / 2 140 160 + 993 216 |

- `vendor_a`: ext4, Block 4096, Label `vendor`, `feature_incompat 0x42` (filetype, extents). `debugfs` liest es ohne Mount.

### 1.4 EDID

`vendor/etc/tvconfig/HDMI_EDID_14.bin` + `HDMI_EDID_20.bin`, je 256 B; Hersteller-Kennung `WSX`, Monitorname `SGD SX8`; alle vier
128-B-Blöcke summieren zu 0; Block 0 beginnt mit `00 ff ff ff ff ff ff 00`, Erweiterungszähler 1, Block 1 mit CEA-Tag `02`.
Aneinandergehängt: 512 B, sha256 `70d10294…` = **Referenz**. Byte 168 ist `0x10` (1.4-Datei) — die Firmware patcht es selbst (doku/82 §11).

### 1.5 MSPM-Patchstrom

`patch_msp` ist ein **exportiertes Symbol** in `vendor/lib/libmspsound.so` (arm32, 126 128 B, sha256 `61f34944…` — gleich der Datei aus
`re/vendor/HY310-DEV/stock_audio_libs/`): `.rodata`, Dateioffset 0xb644, `st_size` 2896. Blockkopf 12 B:
`'MSPM' | u16 0 | u16 0x01TT (TT 00 = DSP1, 02 = DSP2) | u32 BE, Länge = Wert >> 8`. Acht Blöcke (Nutzlast 4, 4, 84, 16, 1128, 1416, 92,
56 B = 724 Paare), Köpfe + Nutzlast = exakt 2896 = Symbolgröße. sha256 `8e31db19…`, md5 `235be48f…` = **Referenz**.

### 1.6 Fingerabdrücke der Eingänge (sha256)

| Eingang | sha256 | Kennung |
|---|---|---|
| HY310 `update.img` | `c518251a00b5cc7b0404e0bb479dc4f18a7558af6df97e9e999d81b31ef3c25d` | `sunxi_version.fex` 2025-07-24 10:31:23, Vendor-Fingerprint `Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/Projector07241019:user/release-keys` |
| HY310 `update_rooted.img` | `64c629b15538f897f40caf446a52862a92234797328fbb17bc9fd073354a50d6` | 13 850 321 Bytes anders, **alle in `boot.fex`** (Image-Offset 152 409 088–219 517 952) plus die 4 B `Vboot.fex` (dessen Prüfsumme) — `super.fex` (ab 253 074 432) und `boot_package.fex` unberührt |
| L018 `update.img` | `812392c7d3de68433b0716aa94155c38d87898956b9fc7e4998cb12b9e111066` | `sunxi_version.fex` 2025-05-14 12:19:36, Fingerprint `…/Projector05141211:user/release-keys` |
| `emmc-first-300mb.bin` | `5d2c5e1d2c4a3af6accfdcb6f5fdff8d88aec055743ffe29b82ceccff0c74851` | GPT 26 Einträge, boot0 an LBA 16 und 256, Pakete an LBA 24576/32800 |

---

## 2. Entscheidungen

### 2.1 Eigene Leser für IMAGEWTY, Sparse und LP; `debugfs` für ext4

`lpunpack`/`simg2img` fehlen am Host, `debugfs` ist da (1.47.0). Deshalb: Container, Sparse-Chunk-Karte und LP-Metadaten sind im Skript
selbst implementiert (je ~60–100 Zeilen, alle Prüfsummen werden nachgerechnet), ext4 wird über `debugfs -f -` gelesen (Befehle über stdin,
`ls -p` zum Auflisten, `dump` zum Lesen — kein Mount, kein Root). Zwei Wege in die ext4:

- Liegt die vendor-Partition **zusammenhängend in einer echten Datei** (rohe `super`, roher vendor-Dump, ext4-Datei), bekommt `debugfs`
  `datei?offset=N` — ohne Zwischenkopie. Der Weg wird vorher mit `stat <2>` geprobt (Antwort `Inode: 2   Type: directory`);
  getestet mit `--part vendor=<vendor.ext4>`: keine Zwischenkopie, EDID und MSP-Patch referenzgleich.
- Kommt sie aus einem **Sparse**-Abbild, wird sie einmal als Datei zwischengespeichert (Löcher für Nullen, 114 MB, 0,2 s) und am Ende
  gelöscht (`--keep-tmp` behält sie).

Eine reine Python-ext4-Implementierung wäre unabhängig von e2fsprogs, aber ein zweiter Fehlerquellenherd; der Auftrag erlaubt `debugfs`.

### 2.2 Fingerabdruck: sha256 der ganzen Eingangsdatei, bei Einzelteilen Referenzgleichheit

Bekannt sind die vier Eingänge aus §1.6. Bei `--part`/`--fex-dir` gibt es kein Image; dann werden die Teildateien einzeln gehasht, und
der Lauf gilt als HY310 (Exit 0), **wenn alle drei Pflichtausgaben referenzgleich sind** — das ist die stärkere Aussage. Unbekannte Images
werden laut gemeldet („UNBEKANNTES IMAGE … Best-Effort") und mit der Abweichungsliste (§2.4) versehen.

### 2.3 Exit-Codes wie im Auftrag, „Abweichung" ist weit gefasst

0 nur, wenn bekanntes Image **und** alle Prüfungen ok **und** alle drei Referenzen stimmen **und** nichts fehlt **und** keine Abweichung
zum HY310-Stock. Alles andere 1 (Ausgabe liegt), Abbruch 2 (`MANIFEST.json`/`BERICHT.txt` werden auch dann geschrieben). Folge: der
Roh-Dump endet mit 1, weil `super` nicht in den ersten 300 MiB liegt — das ist richtig so, denn EDID/MSP/PQ fehlen dann.

### 2.4 Was geprüft wird — und was „hart" ist

| Artefakt | Strukturprüfung | hart (→ `fehler`) |
|---|---|---|
| `h713-arisc.bin` | Paketname/Magic/`MIE;`/`IIE;`, Item-Grenzen in `valid_len`, `encrypt`=0, Additionsprüfsumme; Blob: entspiegelter Reset-Vektor @0x100 ist `l.j`, `CPUs` @0x4004, Versionsstring `TV-303 ARISC …`, Zahl wortausgerichteter `l.nop` | Prüfsumme, Tabellenfehler, kein `l.j`, kein `CPUs`, leerer Blob |
| `hy310-edid.bin` | je Datei 256 B, EDID-Kopf, Blockprüfsummen 0, Erweiterungszähler 1, CEA-Tag; Summe 512 B | jede dieser Bedingungen |
| `msp-patch.bin` | Symbol in `.dynsym`/`.symtab` (Abbildung über die Sektion), MSPM-Kette lückenlos bis zur Symbolgröße, Ziel DSP1/DSP2, Länge % 4 | Kettenbruch, Rückfall auf Suche ohne Symbol |
| `pq/*` | INI-Parser wie `hy310_pq/quellen.py` (doppelte Schlüssel, `,\`-Fortsetzung): `[CONFIG] picture_mode`, `[HDMI1..3]` mit 13 Werten je Modus, `[PQ_ENABLE]`, `PICTURE_CURVE_SETTINGS[1..5]` mit 5 Stützstellen, `[COLOR_TEMP_HDMI]` STANDARD/COOL/WARM/USER mit 6 Werten, `[HDMIOverscanSetting]`; XML wohlgeformt, `gamma level0..4`; SQLite-Tabellen `Picture_Mode`/`White_Balance_Mode`/`Gamma_Point` nicht leer; `portmap.cfg` dreispaltig mit HDMI | jeder fehlende Pflichtschlüssel |

Zusätzlich eine **Abweichungsliste gegenüber HY310** (Item-Größen und -Hashes des Pakets, vendor-Größe, `libmspsound.so`-Hash, ARISC-Version,
Vendor-Fingerprint). Bei fremden Images heißt die Überschrift „hier drohen Probleme".

### 2.5 Was absichtlich nicht passiert

- HDCP: `hdcp_1.bin`, `hdcp_v22.bin`, die `private`-Partition werden **nur benannt** (§5), nie gelesen oder kopiert.
- aic8800-Firmware: nur Pfade, Größen, Modul-Lizenzstrings, NOTICE-Prüfung; kein Byte davon in der Ausgabe.
- Keine APKs, kein `system`/`product`, keine MIPS-Dateien (bleiben in `bootloader_b`), kein Schreiben außerhalb `--out`/`--tmp`.
- Zwischenstände: nur die vendor-Kopie (114 MB) und `dump`-Dateien; werden gelöscht, Größe wird protokolliert.

### 2.6 Roh-Dump: beide Pakete, Bytesuche statt `grep`

Im Dump werden die bekannten LBAs 24576/32800 geprüft **und** der ganze Dump byteweise nach `sunxi-package\0` + Magic abgesucht (8-MiB-Chunks
mit Überlappung — `grep` auf Binärdaten findet nichts, doku/105 §6). Alle Treffer werden geparst, ihre `scp`-Blobs verglichen; unterscheiden
sie sich, wird das gemeldet, der erste gewinnt.

---

## 3. Testläufe

Alle Läufe am 10.09.2026 am Host, je ≈ 2,5 s (sha256 des 1,9-GB-Images 1,7 s aus dem Seitencache, vendor-Kopie 0,2 s, ~40 `debugfs`-Aufrufe).
Vollständige Protokolle in `out-*/BERICHT.txt`, Rohdaten in `out-*/MANIFEST.json`.

> **Nachtrag (§8):** Diese Tabelle zeigt das Werkzeug **0.1**, das L018 als „abweichendes HY310" wertete. Seit 0.2 ist L018 ein
> eigenes Gerät: die Zeilen „L018" und „`--part` L018" enden mit **Exit 0** (Tabelle §8.3); HY310, rooted, Roh-Dump und `--fex-dir`
> sind unverändert. Die `out-*`-Ordner wurden mit 0.2 neu erzeugt.

| Fall | Aufruf | Exit | `h713-arisc.bin` | `hy310-edid.bin` | `msp-patch.bin` | PQ (8) |
|---|---|---|---|---|---|---|
| HY310 | `./hy310-extract re/vendor/HY310/update.img -o out-hy310` | **0** | `d41731fa…` ✓ | `70d10294…` ✓ | `8e31db19…` ✓ | alle ok |
| HY310 rooted | `… update_rooted.img -o out-hy310-rooted` | **0** | ✓ | ✓ | ✓ | alle ok — **alle 11 Ausgabedateien byteidentisch** mit `out-hy310` (`cmp`) |
| L018 | `… /opt/Projekte/Beamer/L018/update.img -o out-l018` | **1** (0.1) → **0** (0.2, §8) | `d4b4a0b9…` (anders, Struktur ok) | `70d10294…` ✓ | `8e31db19…` ✓ | alle ok, byteidentisch mit HY310 |
| Roh-Dump | `… re/device-dumps/emmc-first-300mb.bin -o out-emmc` | **1** | `d41731fa…` ✓ (LBA 24576 = LBA 32800) | — (`super` nicht im Dump) | — | — |
| `--fex-dir` | `… --fex-dir re/vendor/HY310/extracted -o out-fexdir` | **0** | ✓ | ✓ | ✓ | alle ok (als HY310 erkannt über Referenzgleichheit) |
| `--part` L018 | `… --part boot_package=… --part super=… -o out-parts-l018` | 1 (0.1) → **0** (0.2, §8) | wie L018 | ✓ | ✓ | alle ok |
| Negativ | `README.md` als Eingang; `--part foo`; kein Eingang | 2 / 2 / 2 | „Eingang nicht erkannt" bzw. argparse-Fehler | | | |

### 3.1 HY310 `update.img` (Auszug `out-hy310/BERICHT.txt`)

```
== Fingerabdruck Eingang: re/vendor/HY310/update.img (1908065792 B)
  sha256 c518251a00b5cc7b0404e0bb479dc4f18a7558af6df97e9e999d81b31ef3c25d
  BEKANNT: HY310 update.img (Stock)
== IMAGEWTY-Container
  IMAGEWTY header_version 0x0415 (v3), header_size 0x60, image_size 1908066304 B (Datei 1908065792 B), image_header_size 0x400,
  pid 0x1234 vid 0x8743 hw 0x100 fw 0x100, 53 Dateien
  Bereich 0x60..0x3ff: Füllmuster n² mod 256 (kein Chiffrat, keine Nutzdaten)
  letzte Nutzdaten enden bei 0x71bac600 (1908065792 B); Kopf image_size 1908066304, Datei 1908065792
  boot_package.fex im Image: sunxi-package @0x0, 5 Items, valid_len 0x130000, Prüfsumme ok: u-boot@0x800+638976,
  monitor@0x9c800+66060, scp@0xacc00+176132, optee@0xd8000+275328, dtb@0x11b400+73728
== super → LP-Metadaten → vendor
  Sparse v1.0, Block 4096, 524288 Blöcke = 2147483648 B logisch, 4964 Chunks (RAW 2483, FILL 2477, DONT_CARE 4, CRC 0)
  LP-Geometrie @4096 gültig (sha256 ok) · LP-Metadaten primär @12288: v10.2, header_size 256, 6 Partitionen, 3 Extents
    vendor_a   114372608 B  attrs 0x1  Gruppe sb_a  [linear Sektor 1918976+223384]
== h713-arisc.bin (= scp aus dem sunxi-package)
  Struktur: Reset-Vektor @0x100 = l.j 0x12b18 (OR1K, plausibel) · Parameterkopf @0x4000: 'CPUs' vorhanden
  Struktur: Versionsstring: 'TV-303  ARISC  00.00.00.09 Date:Jul 24 2025 Time: 10:17:18' · 445 wortausgerichtete l.nop
  -> lib/firmware/h713-arisc.bin: 176132 B, sha256 d41731fa783dace3070264397064b28e2359a27b9e4708f3f7d40f1c3d876b7e, Prüfung ok, Referenz ja
== vendor-Dateisystem
  vendor: ext4, Block 4096, 27461 Blöcke = 112480256 B, Label 'vendor', feature_incompat 0x42
  build.prop ro.vendor.build.fingerprint = Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/Projector07241019:user/release-keys
  -> lib/firmware/hy310-edid.bin: 512 B, sha256 70d10294e3f1f1ba3aceaf684c90d2dcdcafc9ba4ed265956520bdf4adfb60ef, Prüfung ok, Referenz ja
== h713/msp-patch.bin (= Symbol patch_msp aus libmspsound.so)
  /lib/libmspsound.so: 126128 B, sha256 61f349440c08dd28ef1289f463a7934b3213b15518113ff1044f881bf237e8c4
  -> lib/firmware/h713/msp-patch.bin: 2896 B, sha256 8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5, Prüfung ok, Referenz ja
== PQ-Quellen: tvpq.db 36864 B · pq_picturemode.ini 10216 B · pq_factory_extern.ini 592528 B · pq_colortemp.ini 865 B ·
   pq_overscan_config.ini 10877 B · pqcontrol_config_setting.xml 1055 B · pqcontrol_custom_setting.xml 1326 B · portmap.cfg 312 B — alle „Pflichtschlüssel ok"
== Ergebnis: Exit 0 — bekanntes Image, alles geprüft und referenzgleich
```

Die PQ-Dateien sind byteidentisch mit `re/vendor/HY310/extracted/vendor_a/etc/tvconfig/` (Quelle, die `hy310-pq` heute liest).

### 3.2 `update_rooted.img`

Gleiche Ausgaben, Exit 0. `cmp` über alle elf Ausgabedateien: **gleich**. Das Rooting hat `boot_package.fex` und `super.fex` nicht
berührt: die 13 850 321 verschiedenen Bytes liegen **ausschließlich in `boot.fex`** (Image-Offset 152 409 088–219 517 952, das Android-Boot-Image
mit der gepatchten Ramdisk) und in den 4 B `Vboot.fex` unmittelbar dahinter (Allwinners Prüfsumme des Eintrags). `super.fex` beginnt erst bei
253 074 432 — daher selbe LP-Tabelle, selbe vendor-Dateien.

### 3.3 Roh-Dump `emmc-first-300mb.bin`

```
  GPT: Kopf-CRC ok, Tabellen-CRC ok, 26 Einträge à 128 B ab LBA 2, nutzbar 73728..15269854, Backup-Kopf LBA 15269887
  LBA 16: eGON.BT0 (boot0/SPL) — Länge 32768 B · LBA 256: eGON.BT0 (boot0/SPL) — Länge 32768 B
  Dump LBA 24576: sunxi-package @0xc00000, 5 Items, valid_len 0x130000, Prüfsumme ok: … scp@0xacc00+176132 …
  Dump LBA 32800: sunxi-package @0x1004000, 5 Items, valid_len 0x130000, Prüfsumme ok: … scp@0xacc00+176132 …
  bootloader_a: Dateisystem FAT16 · bootloader_b: Dateisystem FAT16 — MIPS-Dateien, bleiben am Gerät
  private@4891648+32768: Secure Storage (HDCP-Keys laut doku/68) — wird nicht gelesen
  WARNUNG: 'super' liegt bei LBA 599040+4194304, nicht (vollständig) im Dump — kein EDID/MSP/PQ aus diesem Eingang
  scp identisch in: Dump LBA 24576, Dump LBA 32800
  -> lib/firmware/h713-arisc.bin: 176132 B, sha256 d41731fa783dace3070264397064b28e2359a27b9e4708f3f7d40f1c3d876b7e, Prüfung ok, Referenz ja
== Ergebnis: Exit 1 — unbekanntes Image oder Abweichungen — Ausgabe liegt, aber prüfen
```

**Nebenbefund für R1/S41 §2.3:** die Stock-GPT hat **26 Einträge** à 128 B, die Tabelle belegt LBA 2–8 (3 328 B) — sie reicht **nicht** bis
LBA 16. Die primäre Tabelle kollidiert also nicht mit unserer SPL; `FirstUsableLBA` ist 73 728. (Dump vom 31.08., vor dem SPL-Flash gezogen;
die Live-Tabelle sollte das bestätigen, `sudo ./hy310-install.sh --dry-run --steps precheck` zeigt es.)

---

## 4. L018 — was anders ist

Abweichungsliste des Skripts (Exit 1, `out-l018/BERICHT.txt`):

```
== Abweichungen vom HY310-Stock — hier drohen Probleme
  - Paket-Item u-boot: Inhalt anders als HY310 (sha256 8c690dddd2d98edd…)
  - Paket-Item scp: Inhalt anders als HY310 (sha256 d4b4a0b9da4f061a…)
  - Paket-Item dtb: 73216 B statt 73728 B (HY310)
  - Paket-Item dtb: Inhalt anders als HY310 (sha256 2d05339fa4fe65ed…)
  - vendor-Partition 114466816 B statt 114372608 B (HY310)
```

| Teil | HY310 | L018 | Bewertung |
|---|---|---|---|
| IMAGEWTY `header_version` | 0x0415, 53 Dateien | 0x0300, 50 Dateien (kein `mediadata.fex`, `vmediadata.fex`, `windows`) | Packwerkzeug-Version, unkritisch |
| `sunxi_version.fex` / Vendor-Build | 2025-07-24 / `Projector07241019` | 2025-05-14 / `Projector05141211` | gleiche Codebasis `h713_tuna_p3`, Android 11 `RP1A.201005.006`, Kernel 5.4.99 |
| `scp` (ARISC) | `d41731fa…`, `TV-303 ARISC 00.00.00.09 Date:Jul 24 2025` | `d4b4a0b9…`, `… 00.00.00.09 Date:May 14 2025`; 27 692 Bytes verschieden ab 0x100, Reset-Sprung `l.j 0x12b28` statt `0x12b18` | **gleiche Firmware-Version, neu gelinkter Build** — vermutlich lauffähig, am Gerät nicht geprüft (→ §6) |
| `u-boot` | `b8f40b86…` | `8c690ddd…` | anderer Build; für uns irrelevant (eigener U-Boot) |
| `monitor` (BL31), `optee` | gleich | gleich | — |
| `dtb` | 73 728 B | 73 216 B | anderer Vendor-DTB; wird von uns nicht benutzt, aber Hinweis auf Board-Unterschiede (Pins, Panel?) |
| `vendor_a` | 114 372 608 B | 114 466 816 B | `audio_config.ini` 4356 statt 4395 B; sonst alle geprüften Dateien identisch |
| EDID, `libmspsound.so`, `patch_msp`, PQ (8 Dateien) | — | **byteidentisch** | L018 braucht keine eigenen Werte für diese drei Blobs |
| `/etc/firmware/`, aic8800-Module | 91 Dateien | 91 Dateien, Module minimal größer (anderer Kernel-Commit `g56544b93c5eb`) | — |

**Was für ein L018-Nutzer folgt:** `hy310-edid.bin`, `msp-patch.bin` und PQ kann er nehmen wie HY310. Bei `h713-arisc.bin` liefert das
Skript den L018-eigenen Blob (strukturell einwandfrei, gleiche Version). Ob unser Treiber-Handshake (doku/82) damit läuft, muss am Gerät
geprüft werden; das HY310-`scp.bin` ist die sichere Rückfallebene (gleiche ARISC-Version, gleiche Board-Familie).

---

## 5. Beobachtungen: aic8800 und HDCP (nichts angefasst)

### 5.1 aic8800 — Herkunft und Lizenz

Im Vendor-Abbild (beide Images gleich): **91 aic8800-bezogene Dateien**.

- Firmware unter `/vendor/etc/firmware/` (flach **und** in `aic8800d80/`, `aic8800dc/`): `fmacfw_8800d80*.bin` (261–329 KB),
  `lmacfw_rf_8800d80*.bin` (257–302 KB), `fw_adid_8800d80*.bin`, `fw_patch_8800d80*.bin`, `fw_patch_table_8800d80*.bin`,
  `aic_userconfig_8800d80.txt`, dazu die komplette `8800dc`-Familie (`fmacfw_patch_8800dc*`, `fmacfw_calib_8800dc*`, `lmacfw_rf_8800dc.bin` …)
  und generische `fmacfw*.bin`/`fw_patch*.bin` (BT). Das Netboot-Root hat unter `/lib/firmware/aic8800_fw/SDIO/aic8800D80/` **dieselben
  Dateinamen** (`fmacfw_8800d80_u02.bin`, `fw_adid_8800d80_u02.bin`, `fw_patch_8800d80_u02.bin`, `fw_patch_table_8800d80_u02.bin`,
  `lmacfw_rf_8800d80_u02.bin`) — das ist cstengers Paket; ob byteidentisch, habe ich nicht verglichen (nicht Teil des Auftrags).
- Treiber: `/vendor/lib/modules/aic8800_bsp.ko` (`author=Copyright(c) 2015-2020 AICSemi`, **`license=GPL`**, `version=1.0`),
  `aic8800_fdrv.ko` (`author=Copyright(c) 2015-2017 RivieraWaves S.A.S`, `license=GPL`, `version=20250225-004-6.4.3.0`), `aic8800_btlpm.ko`
  (`license=GPL`); `vermagic=5.4.99-00046-g…-dirty SMP preempt mod_unload modversions ARMv7`. HALs: `libwifi-hal-aic.so`, `libbt-aic.so`,
  `/etc/bluetooth/aicbt.conf`.
- **Lizenz der Firmware: nirgends angegeben.** `/vendor/etc/NOTICE.xml.gz` (118 Dateieinträge) nennt keine aic-Datei; in den
  Firmware-Blobs findet sich kein `license`/`copyright`-String (nur RivieraWaves-Assert-Texte wie `mdm_major_version_getf() …`, was auf den
  RivieraWaves-/CEVA-Stack hinweist). `/odm/etc/NOTICE.xml.gz` ist leer (75 B).
- **Folge für das Release:** Treiber ist GPL (kann als Quelle referenziert werden — cstengers Paket), Firmware ohne erkennbare Lizenz →
  **nicht mitliefern**, in der Matrix „WLAN/BT: ungetestet, Firmware nicht enthalten; aus dem eigenen Stock-Image unter
  `/vendor/etc/firmware/aic8800d80/` zu holen". `hy310-extract` könnte sie auf Wunsch (`--aic8800`) kopieren — bewusst **nicht** eingebaut,
  solange die Lizenzfrage offen ist.

### 5.2 HDCP — nur Beobachtung

Dateien, die auf HDCP-Aushandlung deuten (nicht gelesen, nicht kopiert):

- `/vendor/etc/firmware/hdcp_1.bin` (368 B) und `/vendor/etc/firmware/hdcp_v22.bin` (960 B) — in HY310 und L018 gleich groß. Das
  Netboot-Root trägt eine `hdcp_v22.bin` mit ebenfalls 960 B und `hy310-hdcp22.bin` (912 B) — beides Altlasten aus doku/68/88, die nach
  105 §1.1 **nicht** ins Release gehören.
- `private`-Partition (LBA 4 891 648 + 32 768) im Roh-Dump = Secure Storage mit `hdcpkey`/`hdcpkeyV22` (doku/68: Items bei 0x602000/0x606000).
  Das Skript nennt sie nur.
- Im Vendor-DTB/U-Boot des Pakets stecken die bekannten Strings (`smc_tee_hdcp_key_encrypt`, doku/68) — nicht ausgewertet.
- **Status bei uns:** doku/88 §HDCP: der V4L2-Treiber lädt `hy310-hdcp22.bin` (912 B) per `request_firmware`; ohne die Datei kein HDCP-2.2-Key,
  HDCP 1.4 war schon im Stock mit Timeout (`HdmiRx_HDCP14_LoadKey(), time out!`). Für v0.1 gilt: **kein HDCP** — Zuspieler mit
  HDCP-Pflicht (Streaming-Sticks, Blu-ray) zeigen dann kein Bild; das gehört als bekannte Einschränkung in R4. Nichts davon wird extrahiert.

---

## 6. Risiken, offene Fragen

1. **L018-`scp.bin` ungetestet.** Strukturell einwandfrei, gleiche Version, aber am Gerät nie geladen. Test: L018-Blob als `h713-arisc.bin`
   ins Netboot-Root, Handshake und EDID-Folge nach doku/82 §10. Bis dahin: Hinweis im Bericht des Skripts („Referenz nein").
2. **Fremde Firmwares.** Erkannt werden nur die vier Fingerabdrücke. Andere H713-Images (andere Hersteller, andere Packwerkzeug-Version, RC6)
   laufen als „unbekannt" mit Abweichungsliste; ein RC6-verschleierter Container wird abgewiesen (`--fex-dir` als Ausweg). Weitere Images
   sollten in `BEKANNTE_IMAGES` eingetragen werden, sobald sie vorliegen.
3. **erofs-vendor.** Neuere Allwinner-BSPs bauen vendor als erofs; dann hilft `debugfs` nicht. Das Skript meldet „kein ext4-Superblock" und
   bricht ab (Exit 2). Für v0.1 kein Problem (beide Images ext4).
4. **`debugfs`-Abhängigkeit.** Auf Nicht-Debian-Systemen heißt das Paket anders; Windows-Nutzer bräuchten WSL. Alternative wäre ein reiner
   Python-ext4-Leser (~150 Zeilen) — bewusst nicht in den 90 Minuten.
5. **Sparse-`super` wird 114 MB zwischengespeichert.** Auf einem Rechner mit wenig Platz in `--out` kann das scheitern; `--tmp` erlaubt ein
   anderes Ziel. Bei roher `super` (Partitions-Dump vom Gerät) entfällt die Kopie (`?offset=`-Pfad, getestet).
6. **Symbol `patch_msp` könnte in anderen Builds gestrippt sein.** Dann greift die MSPM-Kettensuche (längste lückenlose Kette) — die ist als
   `fehler` markiert, damit niemand einen geratenen Blob für geprüft hält.
7. **Lizenz der PQ-Daten und abgeleiteter Tabellen** (105 §5 Todo hy310-pq): das Skript kopiert die Vendor-INIs nur auf den Rechner des
   Nutzers; nichts davon ins Repo. Bleibt offen.
8. **aic8800-Firmware-Lizenz** (§5.1): nicht auffindbar → nicht enthalten. Nachfrage bei AICSemi/cstenger wäre der nächste Schritt.
9. **`toc1.fex`/`toc0.fex` sind Platzhalter** — Secure Boot ist im Image nicht aktiv; unser eigener SPL bootet (bekannt). Ändert sich das in
   einer künftigen Stock-Version, gilt das ganze Konzept „eigene Bootkette" nicht mehr.
10. **BEFUND.md-Korrektur** (§1.2): `bootloader_a.bin` ≠ Partition p1. Wer nach dem Paket in p1 sucht, findet FAT16.

## 7. Dateien

| Pfad | Inhalt |
|---|---|
| `analyse/release/arbeit/r2-extract/hy310-extract` | Werkzeug (ausführbar) |
| `analyse/release/arbeit/r2-extract/README.md` | Nutzung, Grenzen, Formatnotizen |
| `analyse/release/arbeit/r2-extract/out-hy310/` | HY310-Lauf: `lib/firmware/h713-arisc.bin`, `hy310-edid.bin`, `h713/msp-patch.bin`, `pq/` (8), `MANIFEST.json`, `BERICHT.txt` |
| `analyse/release/arbeit/r2-extract/out-hy310-rooted/`, `out-l018/`, `out-emmc/`, `out-fexdir/`, `out-parts-l018/` | die übrigen Läufe, gleiche Struktur |
| `analyse/release/arbeit/r2-extract/AUFTRAG.md` | Auftrag |

Zwischenstände (`tmp/`) sind gelöscht. Kein Blob liegt in einem Git-Baum (`analyse/` ist außerhalb von `mainline/`, `userspace/`, `re/`).

---

## 8. Nachtrag (10.09., 00:40–01:10): L018 als eigenes Gerät

**Korrektur von Marco (AUFTRAG.md, Ende):** L018 ist kein „abweichendes HY310", sondern ein eigenes Gerät mit eigenem Profil und
eigenen Referenzwerten. Umgesetzt als Werkzeug **0.2**; Regeln wie im Hauptauftrag (kein Board, kein Netz, nur `r2-extract/` und dieser
Bericht geschrieben, HDCP nicht angefasst, `tmp/` gelöscht).

### 8.1 Was war falsch

- Das Werkzeug 0.1 kannte **eine** Referenz (HY310-Netboot-Root) und **einen** Sollwertsatz (`HY310_ERWARTUNG`). L018 wurde am sha256
  zwar erkannt, aber als „keine Referenzwerte" geführt: sein eigener `scp.bin` (`d4b4a0b9…`) galt als „Referenz weicht ab", und jeder
  Unterschied zum HY310-Stock (`u-boot`, `dtb`, vendor-Größe) landete unter „Abweichungen — hier drohen Probleme" → **Exit 1** für ein
  vollständiges, korrektes Ergebnis.
- Bei Einzelteilen (`--part` L018) war es noch schiefer: ohne Image-Fingerabdruck griff nur die Regel „alle drei Ausgaben referenzgleich →
  HY310"; die scheiterte am L018-`scp`, `image_typ` blieb `None`, das Manifest nannte gar kein Gerät.
- Die Doku (§2.3, §2.4, §4) übernahm diese Sicht („Abweichung ist weit gefasst", „was für einen L018-Nutzer folgt").

### 8.2 Was ist neu (Werkzeug 0.2)

| Bereich | 0.1 | 0.2 |
|---|---|---|
| Referenz | `REFERENZ` (HY310), `HY310_ERWARTUNG` | **`GERAETE`** mit Profilen `hy310` und `l018`: je `referenz` (drei Pflicht-Hashes) und `erwartung` (Paket-Item-Größen und -sha256, U-Boot-Kennung, dtb-`compatible`, ARISC-Versionsstring, vendor-Größe, `libmspsound.so`, Vendor-Fingerprint, `sunxi_version`). L018-Referenz = Werte des ersten Laufs (§4): ARISC `d4b4a0b9…`; EDID `70d10294…`, MSP `8e31db19…`, PQ = HY310-Werte, weil byteidentisch |
| Fingerabdruck | sha256 → `HY310`/`L018` | sha256 → Profilschlüssel (`BEKANNTE_IMAGES`); bleibt der stärkste Weg |
| inhaltliche Erkennung | Regel „alle drei referenzgleich → HY310" | **Merkmale** werden im Lauf gesammelt (`merkmale` im Manifest): scp-/u-boot-/dtb-Hash, U-Boot-Kennung, ARISC-Version, Vendor-Fingerprint (**stark**, legen das Gerät fest) sowie `sunxi_version` und vendor-Größe (schwach, bestätigen oder widersprechen nur). Ein Profil passt, wenn ein starkes Merkmal zutrifft und keines widerspricht; widersprechen sich die Teile, wird ein schon gesetztes Gerät **zurückgenommen** (Warnung, Exit 1). Damit werden `--part`, `--fex-dir` und `--no-hash` einem Gerät zugeordnet |
| neue Kennungen | — | U-Boot-Versionsstring aus dem `u-boot`-Item (`U-Boot 2018.05-00024-gc128a2c-dirty (Jul 24 2025 …)` HY310 / `00025-gf362927 … May 14 2025` L018) und Wurzel des Vendor-DTB über einen kleinen FDT-Leser: `model "sun50iw12"`, `compatible "allwinner,tv303" "arm,sun50iw12p1"` — auf beiden Geräten gleich, dient als Familienprüfung, nicht als Unterscheidung |
| Referenzabgleich | in `ablegen()`, sofort, gegen HY310 | in **`bewerte()` am Ende**, gegen das Profil des erkannten Geräts — bei Einzelteilen steht das Gerät oft erst nach `build.prop` fest. Die Zeile `-> … Prüfung ok` trägt kein „Referenz ja/nein" mehr; stattdessen der Abschnitt `== Gerät und Referenzabgleich` |
| „Abweichung" | jeder Unterschied zum HY310-Stock | nur bei **unbekanntem** Image (kein Profil passt): Best-Effort, Abgleich gegen das ähnlichste Profil, Überschrift „hier drohen Probleme", Exit 1. Bei erkanntem Gerät muss die Liste leer sein — ist sie es nicht, Warnung „trotz erkanntem Gerät" und Exit 1 (Sicherheitsnetz gegen Profilfehler) |
| Manifest / Bericht | `image_typ`, `abweichungen_von_hy310` | **`device`** (`hy310`/`l018`/`null`), `device_name`, `device_beschreibung`, `device_erkennung` (`ueber`: `sha256`/`Inhalt`, `merkmale`, `hinweise`, `stimmen`), `referenzgeraet`, `merkmale`, `abweichungen`; je Artefakt `referenzgeraet`. `BERICHT.txt` bekommt die Zeile `Gerät:`. Ausgabepfade unverändert (`lib/firmware/…`, `pq/…`) |
| Ausgabeverzeichnis | — | liegt in `<out>` schon ein `MANIFEST.json` eines **anderen** Geräts (auch 0.1-Manifeste über `image_typ`), bricht der Lauf ab, sobald das Gerät feststeht — **Exit 2, nichts geschrieben**, altes Manifest bleibt |
| Exit-Codes | 0 bekannt+referenzgleich · 1 unbekannt/Abweichung · 2 Fehler | **0** bekanntes Gerät, alles geprüft und referenzgleich mit dessen Profil · **1** unbekanntes Image (Best-Effort) oder — bei erkanntem Gerät — fehlende/fehlerhafte/abweichende Teile · **2** Fehler, auch „falsches `--out`" |

Umfang: 1 730 → 2 030 Zeilen; Laufzeit unverändert (≈ 2,1–2,4 s je Image, Roh-Dump 0,6 s).

### 8.3 Testläufe (10.09., 00:54–01:00, Werkzeug 0.2)

Alle Läufe in `analyse/release/arbeit/r2-extract/`, Protokolle in `out-*/BERICHT.txt`; Zusatzfälle liefen nach `tmp/` (gelöscht).

| Fall | Aufruf | Exit 0.1 → **0.2** | Gerät (erkannt über) | `h713-arisc.bin` | `hy310-edid.bin` | `msp-patch.bin` | PQ (8) |
|---|---|---|---|---|---|---|---|
| HY310 | `update.img -o out-hy310` | 0 → **0** | `hy310` (sha256; bestätigt durch alle 8 Merkmale) | `d41731fa…` Referenz hy310 ✓ | `70d10294…` ✓ | `8e31db19…` ✓ | alle ok |
| HY310 rooted | `update_rooted.img -o out-hy310-rooted` | 0 → **0** | `hy310` (sha256) | ✓ | ✓ | ✓ | alle ok — **alle 11 Dateien byteidentisch** mit `out-hy310` (`cmp`) |
| **L018** | `/opt/Projekte/Beamer/L018/update.img -o out-l018` | 1 → **0** | **`l018`** (sha256; bestätigt durch alle 8 Merkmale) | `d4b4a0b9…` **Referenz l018 ✓** | `70d10294…` ✓ | `8e31db19…` ✓ | alle ok — 10 von 11 Dateien byteidentisch mit `out-hy310`, nur `h713-arisc.bin` anders; **keine Abweichungen** |
| Roh-Dump | `re/device-dumps/emmc-first-300mb.bin -o out-emmc` | 1 → **1** | `hy310` (sha256; bestätigt durch scp/u-boot/dtb-Hash, U-Boot-, ARISC-Kennung) | `d41731fa…` ✓ (= `out-hy310`) | — (`super` nicht im Dump) | — | — |
| `--fex-dir` HY310 | `--fex-dir re/vendor/HY310/extracted -o out-fexdir` | 0 → **0** | `hy310` (**Inhalt**: scp/u-boot/dtb-Hash, U-Boot-Kennung, dann ARISC, Fingerprint, vendor-Größe) | ✓ | ✓ | ✓ | alle ok |
| `--part` L018 | `--part boot_package=… --part super=… -o out-parts-l018` | 1 → **0** | **`l018`** (Inhalt, 7 Merkmale) | `d4b4a0b9…` ✓ | ✓ | ✓ | alle ok — byteidentisch mit `out-l018` |
| `--fex-dir` L018 (neu) | `--fex-dir /opt/Projekte/Beamer/L018/extracted -o out-fexdir-l018` | — → **0** | `l018` (Inhalt, 7 Merkmale) | ✓ | ✓ | ✓ | alle ok — byteidentisch mit `out-l018` |
| `--no-hash` L018 (neu) | `--no-hash …/L018/update.img` | — → **0** | `l018` (Inhalt — Fingerabdruck übersprungen) | ✓ | ✓ | ✓ | alle ok, byteidentisch |
| nur `super` HY310 (neu) | `--part super=…/HY310/extracted/super.fex` | — → 1 | `hy310` (Inhalt: Vendor-Fingerprint, vendor-Größe) | — (fehlt: kein Paket) | ✓ | ✓ | alle ok |
| nur `boot_package` L018 (neu) | `--part boot_package=…/L018/extracted/boot_package.fex` | — → 1 | `l018` (Inhalt: scp/u-boot/dtb-Hash, U-Boot-Kennung) | `d4b4a0b9…` ✓ | — (keine vendor) | — | — |
| gemischt (neu) | `--part boot_package=` **L018** `--part super=` **HY310** | — → 1 | **unbekannt**: erst `l018` (Paket), nach `vendor_a` „Gerät l018 wieder zurückgenommen — Eingangsteile passen nicht zu einem Gerät" | ✓ (l018) | ✓ | ✓ | alle ok; Abweichungen vom L018-Stock: vendor 114 372 608 statt 114 466 816 B, Fingerprint `Projector07241019` statt `05141211` |
| falsches `--out` (neu) | L018 `update.img` in ein Verzeichnis mit HY310-`MANIFEST.json` | — → **2** | `l018` (sha256) → „enthält schon Ergebnisse für Gerät 'hy310' … Anderes --out wählen" | nichts geschrieben, `MANIFEST.json` unverändert (mtime) | | | |
| Negativ | `README.md` als Eingang | 2 → 2 | — | „Eingang nicht erkannt" | | | |

Auszug `out-l018/BERICHT.txt` (Kopf und Abgleich):

```
Eingang: /opt/Projekte/Beamer/L018/update.img (IMAGEWTY)
sha256:  812392c7d3de68433b0716aa94155c38d87898956b9fc7e4998cb12b9e111066
Bekannt: L018 update.img (Stock)
Gerät:   l018 — L018 — Allwinner H713, Referenzdesign h713_tuna_p3, Stock-Build 2025-05-14 (Projector05141211)
         (erkannt über sha256, bestätigt durch scp_sha256, uboot_sha256, dtb_sha256, uboot_version, arisc_version,
         build_fingerprint, sunxi_version, vendor_size)
Ergebnis: Exit 0 — bekanntes Gerät l018, alles geprüft und referenzgleich
…
  U-Boot-Kennung: U-Boot 2018.05-00025-gf362927-dirty (May 14 2025 - 12:09:44 +0800) Allwinner Technology
  dtb-Wurzel: model 'sun50iw12', compatible 'allwinner,tv303 arm,sun50iw12p1'
  sunxi_version.fex: 2025-05-14 12:19:36
…
== Gerät und Referenzabgleich
  lib/firmware/h713-arisc.bin: Referenz l018 stimmt
  lib/firmware/hy310-edid.bin: Referenz l018 stimmt
  lib/firmware/h713/msp-patch.bin: Referenz l018 stimmt
```

### 8.4 Was sich an den Aussagen von §2–§6 ändert

- §2.2/§2.3: Die Regel „alle drei referenzgleich → HY310" ist ersetzt durch die Merkmalerkennung; „Abweichung" ist nicht mehr weit gefasst,
  sondern gibt es nur noch für unbekannte Images. Der Roh-Dump endet weiterhin mit 1 (`super` fehlt) — das ist kein Gerätethema.
- §4: Die Abweichungsliste dort ist die **Profilbeschreibung** von `l018` geworden (`u-boot`, `scp`, `dtb` 73 216 B, vendor 114 466 816 B).
  Ein L018-Nutzer bekommt jetzt Exit 0 und ein Manifest mit `device: l018`.
- §6.1 bleibt: „Referenz l018 stimmt" heißt **gleich dem ersten Lauf vom 10.09.**, nicht „am Gerät bewiesen". Der L018-`scp.bin` wurde
  nie geladen; das HY310-`scp.bin` ist weiter die sichere Rückfallebene (gleiche ARISC-Version `00.00.00.09`).
- §6.2: Ein drittes Gerät braucht ein eigenes Profil in `GERAETE` (drei Referenz-Hashes, Paket-Hashes, Kennungen) plus seinen sha256 in
  `BEKANNTE_IMAGES`; bis dahin läuft es als „unbekannt" gegen das ähnlichste Profil.

### 8.5 Dateien des Nachtrags

| Pfad | Inhalt |
|---|---|
| `analyse/release/arbeit/r2-extract/hy310-extract` | Werkzeug 0.2 (Geräteprofile, Merkmalerkennung, `bewerte()`, Verzeichnis-Schutz) |
| `analyse/release/arbeit/r2-extract/README.md` | neuer Abschnitt „Geräteprofile und Erkennung", Exit-Codes, Grenzen |
| `analyse/release/arbeit/r2-extract/out-hy310/`, `out-hy310-rooted/`, `out-l018/`, `out-emmc/`, `out-fexdir/`, `out-parts-l018/` | mit 0.2 neu erzeugt (`MANIFEST.json` mit `device`) |
| `analyse/release/arbeit/r2-extract/out-fexdir-l018/` | neuer Lauf `--fex-dir` L018 |

`tmp/` (Zusatzläufe, Protokolle, 3 MB) ist gelöscht.

## 9. Nachtrag (10.09., Werkzeug 0.3): die MIPS-/Display-Artefakte aus den Vendor-Partitionen

**Auftrag:** [`108`](../108-plan-vendordaten.md) §4.2/§4.5 — `hy310-extract` soll auch das holen, was heute nur in
`bootloader_a`/`bootloader_b` liegt und was U-Boot mit `h713_disp_read("mips/…")` liest. Regeln wie in §1–§8: kein Board,
kein Netz, geschrieben nur in `analyse/release/arbeit/r2-extract/` und in diesen Bericht; HDCP-Material nicht angefasst.
Die Abschnitte §1–§8 bleiben, wie sie sind; hier steht nur, was 0.3 hinzufügt.

### 9.1 Was neu ist

| Punkt | 0.2 | 0.3 |
|---|---|---|
| Ausgabe | `lib/firmware/*`, `pq/*` | zusätzlich **`boot/mips/*`** — 19 Dateien, 1,7 MB |
| Dateisysteme | ext4 (`debugfs`) | zusätzlich **FAT12/16/32 mit Langnamen (VFAT LFN)**, eigener Leser, keine Fremdwerkzeuge |
| Eingänge | IMAGEWTY, eMMC-Dump, `--part`, `--fex-dir` | dieselben; neu erkannt: `boot-resource.fex` im Container/`--fex-dir`, GPT-Partitionen `bootloader_a`/`bootloader_b`, `--part bootloader_b=…`, ein FAT-Abbild als direkte Eingangsdatei |
| Projekt-ID | — | benutzte (aus `display.bin`), deklarierte (aus `panel_config.ini`) und alle vorhandenen im Manifest und im Berichtskopf |
| Geräteerkennung | 8 Merkmale | 9 — `mips_database_sha256` ist das einzige MIPS-Artefakt, das HY310 und L018 unterscheidet |
| Optionen | `--no-pq` | zusätzlich `--no-mips` |

Extrahiert wird genau die Liste aus Plan 108 §1: `display.bin`, `display_cfg.xml`, `LogoRegData.bin`, `database.TSE`,
`pq_custom.TSE`, `projecttable.TSE` und **alle** `ProjectID_0x*.TSE`. Nicht extrahiert werden `bootlogo.bmp` (6,2 MB),
`fastbootlogo.bmp`, `font24/32.sft`, `magic.bin`, `bat/` und `wavefile/` — zusammen rund 18 MB, die unsere Kette nicht
nutzt; sie stehen im Bericht unter „Dieselbe Partition enthält …", werden aber nicht kopiert.

### 9.2 FAT16-Befunde

- Die Quelle ist in allen Eingangsformen **dasselbe Abbild**: `sys_partition.fex` gibt für `bootloader_a` *und*
  `bootloader_b` `downloadfile="boot-resource.fex"` an. Im Container und in `--fex-dir` heißt es so, auf dem eMMC sind es
  die GPT-Partitionen bei LBA 73728 und 139264 (je 65 536 Sektoren = 32 MiB).
- BPB: 512 B/Sektor, 4 Sektoren/Cluster (2048 B), 1 reservierter Sektor, 2 FATs à 256 Sektoren, 512 Wurzeleinträge,
  Label `Volumn`. **Der BPB behauptet 262 144 Sektoren (128 MiB)**, die Partition hat aber nur 32 MiB und `boot-resource.fex`
  ist mit 21 746 688 B hinter den Nutzdaten abgeschnitten. Belegt sind nur die ersten ~21 MB, also folgenlos; der Leser
  meldet die Diskrepanz und liest nur, was vorhanden ist.
- **Die 8.3-Namen sind unbrauchbar**, und zwar nicht durchgehend, sondern sprunghaft: neben `PROJEC~2.TSE` stehen
  `PR§÷pð~1.TSE`, `PR§÷` + Steuerzeichen + `~1.TSE`, `PRý0ô~1.TSE`. Erst die LFN-Einträge (Attribut `0x0F`, je 13 UTF-16-Zeichen in den
  Feldern 1–10/14–25/28–31, rückwärts vor dem 8.3-Eintrag, Folgenummer in Byte 0 mit `0x40` am letzten) ergeben
  `ProjectID_0x0032.TSE` usw. — also genau die Namen, die U-Boot erwartet. Ein 8.3-Leser hätte hier still das Falsche geliefert.
- **In `mips/` liegen 13 ProjectID-Dateien, nicht 15** (Plan 108 §1 sagt „15 Stück“): `0x0001, 0x0012, 0x0013, 0x0014,
  0x0015, 0x0016, 0x0020, 0x0030, 0x0031, 0x0032, 0x0033, 0x0034, 0x0035`, zusammen 396 kB. Die Aussage „rund 400 kB“
  aus dem Plan stimmt, die Stückzahl ist zu korrigieren.
- **`bootloader_a` auf dem Dev-Gerät ist keine saubere Kopie von `bootloader_b`** (Plan 108 §1 nennt p1 „Kopie von p2“).
  Im Dump unterscheiden sich `display.bin` (32 Bytes ab Offset 708) und `display_cfg.xml` (`mode 2`/`level 5` statt
  `mode 1`/`level 1` im `elog_init_setting`), und in `mips/` von p1 liegen zusätzlich `display-shifted.bin` und
  `display.bin.backup-20260528-2354`. Das ist unsere eigene Bastelspur vom Mai; **p2 ist der unberührte Stand**. Das
  Werkzeug nimmt darum immer `bootloader_b`, liest `bootloader_a` nur zum Vergleich und schreibt den Unterschied in den
  Bericht. Im Auslieferungs-Image (`update.img`, `boot-resource.fex`) sind beide Partitionen naturgemäß identisch.
- Zwischen HY310 und L018 unterscheidet sich von den 19 Artefakten **genau eines**: `database.TSE`
  (`133bbec3…` gegen `002ad401…`). Alles andere, `display.bin` eingeschlossen, ist byteidentisch. Das ist als
  neues starkes Erkennungsmerkmal `mips_database_sha256` in die Profile eingetragen — damit ist auch eine reine
  `bootloader_b`-Partition ohne Bootpaket und ohne `super` einem Gerät zuzuordnen.
- `display_cfg.xml` endet auf ein Null-Byte hinter `</root>`. Der XML-Parser stolpert darüber; das Werkzeug schneidet
  für die Prüfung ab, kopiert die Datei aber unverändert und meldet die Eigenart.

### 9.3 Projekt-ID: drei Angaben, eine Entscheidung (Plan 108 §4.5)

| Angabe | Woher | HY310 `update.img` | L018 `update.img` |
|---|---|---|---|
| **benutzt** | sha256 der `display.bin` in `h713_mips_fw_revs[]` (`h713_mips.c` ab ~324) | `16c74a28…` → `0x30`, „HY310 (QZ713 V3.1)“, Panel 1920×1080, Sollgröße 1 256 216 B ✓ | dieselbe `display.bin` → `0x30` |
| **deklariert** | `ProjectID` aus `panel_config.ini` im vendor-Dateisystem | `0x30` (`ProjectID = 48`) | `0x30` (`ProjectID = 48`) |
| **vorhanden** | alle `ProjectID_0x*.TSE` in `mips/` | 13 | 13 |

Alle drei stehen im Manifest (`mips`) und im Kopf von `BERICHT.txt`. Die deklarierte wird **gemeldet, nie benutzt** —
so verlangt es der Plan, und das Werkzeug hält sich daran, auch wenn beide hier übereinstimmen.

**Befund, der Plan 108 §3 präzisiert:** Die Zeile „this board declares project 0x34 (panel_config.ini ProjectID = 52)“ im
Kaltstart-Log kommt **nicht** aus der `panel_config.ini` des HY310. Sie druckt die Übersetzungskonstante
`H713_DISP_BOARD_PROJECT_ID` (`h713_mips.c`), die aus der `panel_config.ini` von **Board B** (HY200 QZ713DF_A1,
`Reserve0_a`, sha256 `7bffff88…`) stammt. Die eigene `panel_config.ini` dieses Geräts sagt `ProjectID = 48` = `0x30` —
gemessen an zwei Stellen, die byteidentisch sind (`vendor:/etc/tvconfig/panel_config/panel_config.ini` und
`Reserve0.fex`, beide sha256 `b024f6e0…`); die L018-Fassung sagt dasselbe (`2f20edbc…`). **Gerät und Wahrheit gehen also
nicht auseinander**; auseinander gehen eine fest einkompilierte Fremdkonstante und die Wahrheit. Für den Betrieb ändert
das nichts (benutzt wird weiter die ID aus `display.bin`), aber der offene Punkt in Plan 108 §6 „Projekt-ID: Gerät und
Wahrheit gehen auseinander“ ist damit anders zu fassen: zu klären ist die Herkunft der Konstante in U-Boot, nicht das
Verhalten des Boards.

Ist die `display.bin` **keine bekannte Revision**, sagt das Werkzeug das laut (Warnung + eigener Absatz im Bericht),
listet die bekannten Revisionen mit Board/ID/Panel/Größe und weist darauf hin, dass alle ProjectID-Dateien in der Ausgabe
liegen und die Wahl zur Laufzeit bleibt (`setenv h713_project 0x…; saveenv`). Nachgestellt mit einem Bit-Dreher in
`display.bin`: Projekt-ID `UNBESTIMMT`, alle 19 Dateien trotzdem extrahiert, Exit 1.

Strukturprüfungen: `display.bin` gegen Größe **und** sha256 der Revisionstabelle; TSE-Kopf (Magic `TSE`, ID bei Offset 14
als u16 LE — bei `ProjectID_0x*.TSE` muss sie zum Dateinamen passen, sonst Warnung); `display_cfg.xml` parsebar
(Wurzel `<root>`, 10 Kinder). Gegenprobe gegen die am Gerät gemessenen Werte: alle acht Sollgrößen stimmen
(`display.bin` 1 256 216, `database.TSE` 282 464, `pq_custom.TSE` 15 016, `projecttable.TSE` 1 384, `display_cfg.xml` 4 766,
`LogoRegData.bin` 15 652, `ProjectID_0x0030.TSE` 19 992, `ProjectID_0x0034.TSE` 17 328), und
`ProjectID_0x0030.TSE` beginnt mit `545345021a0001b09118844ef6663000` — Zeichen für Zeichen wie am Gerät gemessen.

### 9.4 Testläufe (10.09., Werkzeug 0.3)

| Fall | Aufruf | Exit 0.2 → **0.3** | MIPS-Quelle | `boot/mips` | Projekt-ID benutzt / deklariert |
|---|---|---|---|---|---|
| HY310 | `re/vendor/HY310/update.img -o out-hy310` | 0 → **0** | `boot-resource.fex` im Image | 19 Dateien, alle referenzgleich | `0x30` / `0x30` |
| HY310 rooted | `update_rooted.img -o out-hy310-rooted` | 0 → **0** | dito | 19, **byteidentisch mit `out-hy310`** | `0x30` / `0x30` |
| L018 | `/opt/Projekte/Beamer/L018/update.img -o out-l018` | 0 → **0** | dito | 19, nur `database.TSE` anders als HY310 | `0x30` / `0x30` |
| Roh-Dump | `re/device-dumps/emmc-first-300mb.bin -o out-emmc` | 1 → **1** (weiter wegen fehlender `super`) | Partition `bootloader_b` (LBA 139264) | 19, **byteidentisch mit `out-hy310`**; `bootloader_a` weicht ab (siehe §9.2) | `0x30` / — (kein `super` im Dump) |
| `--fex-dir` HY310 | `--fex-dir re/vendor/HY310/extracted -o out-fexdir` | 0 → **0** | `boot-resource.fex` | 19, byteidentisch mit `out-hy310` | `0x30` / `0x30` |
| `--fex-dir` L018 | `--fex-dir /opt/Projekte/Beamer/L018/extracted -o out-fexdir-l018` | 0 → **0** | `boot-resource.fex` | 19, byteidentisch mit `out-l018` | `0x30` / `0x30` |
| `--part` L018 | `--part boot_package=… --part super=… --part bootloader_b=boot-resource.fex -o out-parts-l018` | 0 → **0** | `--part bootloader_b` | 19, byteidentisch mit `out-l018` | `0x30` / `0x30` |
| nur bootloader_b (neu) | `--part bootloader_b=…/HY310/extracted/boot-resource.fex` | — → 1 (kein Paket, kein `super`) | `--part bootloader_b` | 19, alle referenzgleich; Gerät **allein an `mips/database.TSE`** als `hy310` erkannt | `0x30` / — |
| fremde `display.bin` (neu) | wie oben, ein Bit in `display.bin` gedreht | — → 1 | `--part bootloader_b` | 19 extrahiert, `display.bin` als FEHLER markiert | **UNBESTIMMT**, alle 13 IDs angeboten / — |

Alle Läufe in `analyse/release/arbeit/r2-extract/out-*`; die beiden Zusatzfälle liefen nach `tmp/` und sind gelöscht.
`--part`-Läufe ohne bootloader-/`boot-resource`-Quelle enden jetzt mit **1** statt 0 (`boot/mips/*` steht unter „Nicht
extrahiert“) — wer das nicht will, nimmt `--no-mips`.

### 9.5 L018: fehlt eine `bootloader_b.fex`?

Nein — und auch keine `bootloader_a.fex`, weder bei L018 noch bei HY310. Beide entpackten Ordner enthalten
`boot-resource.fex` (je 21 746 688 B), und genau das ist die Datei, die der Flasher nach `bootloader_a` **und**
`bootloader_b` schreibt (`sys_partition.fex`, `downloadfile="boot-resource.fex"` in beiden Abschnitten). Das L018-Profil
hat damit eine vollständige Referenz für alle 19 MIPS-Artefakte; nichts bleibt ohne Sollwert. Was für L018 fehlt, ist
etwas anderes und war schon in §6.1 vermerkt: die Werte sind **am L018 nie geladen worden**, sie sind referenzgleich mit
dem ersten Lauf, nicht am Gerät bewiesen.

### 9.6 Was offen bleibt

- Die extrahierten Dateien sind gegen die am Gerät gemessenen Größen und den TSE-Kopf geprüft, aber **noch nicht aus der
  neuen Quelle geladen**. Das ist Schritt 3 der Reihenfolge in Plan 108 §5 und braucht ein Board.
- Ein byteweiser Vergleich „extrahiert gegen die Dateien in p2 des Dev-Geräts" (Plan 108 §5 Schritt 2) ist für den
  Roh-Dump erbracht (`out-emmc/boot/mips` = `out-hy310/boot/mips`, byteidentisch), für ein laufendes Gerät nicht.
- `h713_mips_fw_revs[]` kennt zwei Revisionen. Ein drittes Gerät mit eigener `display.bin` landet bei „UNBESTIMMT";
  das ist gewollt, kostet aber einen Handgriff (Tabelle in U-Boot ergänzen, dann hier nachziehen).
- Die Herkunft der U-Boot-Konstante `H713_DISP_BOARD_PROJECT_ID = 0x34` gehört nach dem Befund in §9.3 neu bewertet
  (Plan 108 §6).

### 9.7 Dateien des Nachtrags

| Pfad | Inhalt |
|---|---|
| `analyse/release/arbeit/r2-extract/hy310-extract` | Werkzeug 0.3: `class Fat` (FAT12/16/32 + LFN), `tse_kopf()`/`pruefe_tse()`, `fw_rev_zu()`, `pruefe_display_cfg()`, `panel_config_id()`, `Lauf.extrahiere_mips()`, `H713_MIPS_FW_REVS`, `_MIPS_REF`/`_MIPS_REF_L018` in beiden Profilen |
| `analyse/release/arbeit/r2-extract/README.md` | neuer Abschnitt „Die MIPS-/Display-Artefakte", Projekt-ID-Tabelle, FAT16-/TSE-Formatnotizen, `--no-mips`, Exit-Codes |
| `analyse/release/arbeit/r2-extract/out-*/boot/mips/` | die 19 Artefakte je Testlauf, `MANIFEST.json` mit `mips`-Block, `BERICHT.txt` mit Projekt-ID-Kopf |

`tmp/` (Zusatzläufe, Prototyp des FAT-Lesers, Protokolle) ist gelöscht.

## 10. Korrektur (Hauptsitzung, 10.09.): `private` ist nicht das Secure Storage

§2.5 und die Berichtszeile „`private@4891648+32768`: Secure Storage (HDCP-Keys laut doku/68)" sind **falsch zugeordnet**.
Das echte sunxi Secure Storage liegt **roh bei LBA 12288** (Byte `0x600000`), genau wie [`68`](../68-stock-extraktion-arisc-hdcp.md)
es beschreibt — nicht in der gleichnamigen Partition. Am 10.09. dekodiert: 7 Items à 4 KiB, jedes doppelt, Magic `0x17253948`:
`hdcpkey` (396 B), `hdcpkeyV14_hash` (6), `hdcpkeyV22` (988), `hdcpkeyV22_hash` (6), **`wifiBleDatas` (240, MAC-Adressen)** und
**`snum` (15, Seriennummer)**.

Für das Werkzeug ändert sich nichts — es liest weder das eine noch das andere. Für das Layout ändert sich alles: der Block bei
12288 ist als eigene Partition `hy310-keys` geschützt ([`109`](../109-plan-layout-v3.md) §2.3), während `private` beim Umbau
überschrieben wurde.
