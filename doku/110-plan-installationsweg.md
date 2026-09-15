# Plan 110 - der Installationsweg für Nutzer

> ## ⚠ Was jedem Nutzer vor dem ersten Schritt gesagt werden muss
>
> **Das hier ist eine Beta.** Nicht im Sinne von „ein paar Ecken sind unrund", sondern: es kann schiefgehen, und dann steht
> ein Gerät da, das nicht mehr startet.
>
> Deshalb gilt, ohne Ausnahme und in dieser Reihenfolge:
>
> 1. **Mach einen Vollabzug.** Nicht den kleinen - den vollen, 7,3 GB, 17 Minuten. Damit spielst du dein Gerät genau so
>    zurück, wie es war.
> 2. **Oder** halte die passende Herstellerfirmware bereit, **bevor** du anfängst. Nicht danach suchen, wenn es klemmt.
> 3. Erst dann loslegen.
>
> Wer beides überspringt, riskiert ein Gerät ohne Rückweg. Der FEL-Modus rettet die Boot-Kette, aber er stellt keine Daten
> wieder her, die niemand gesichert hat.
>
> **Dieser Absatz gehört wörtlich in die README, in die Ausgabe des Installers vor dem ersten Schreibzugriff und in jede
> Release-Ankündigung.** Nicht kleingedruckt.


**Status: Plan, 10.09.2026.** Löst [`105`](105-plan-release.md) R0/R1 in der Frage ab, **wie** ein fremdes Gerät zu unserem
System kommt. Anlass ist Marcos Einwand: der Installer muss nicht auf dem Gerät laufen, und der Nutzer braucht kein
Firmware-Image aus dem Netz - beides liegt auf seiner eigenen eMMC.

## 1. Der Weg in sechs Schritten

| # | Was der Nutzer tut | Was dabei geschieht |
|---|---|---|
| 1 | Reset-Taste halten, Strom einstecken | Gerät ist im FEL-Modus (kein Gehäuse, kein Pad, kein Löten) |
| 2 | `hy310-install` starten | lädt U-Boot flüchtig über USB (`sunxi-fel uboot`, ~3 s, **kein Byte auf die eMMC**) und lässt es die eMMC als USB-Laufwerk freigeben |
| 3 | - | **Vollabzug der eMMC** auf den PC, 7,3 GB, mit Prüfsumme. **Pflicht, nicht wählbar** (§2) |
| 4 | - | Extraktion der proprietären Teile **aus dem Abzug** (§3) |
| 5 | - | Layout v3, Boot-Kette, Rootfs, Artefakte auf das Laufwerk schreiben ([`109`](109-plan-layout-v3.md)) |
| 6 | Strom aus und an | Das Gerät bootet in unser System |

Der Nutzer braucht: einen Linux-PC, ein A-auf-A-Kabel mit getrennter VBUS-Ader, 8 GB Plattenplatz und rund 15 Minuten.
**Kein Firmware-Image, kein USB-Stick, kein TFTP/NFS, kein Netz am Gerät.**

## 2. Der Abzug - zwei Größen zur Wahl (Marco, 10.09.)

**Gemessen am Gerät (10.09.): 7,6 MB/s lesen, 7,7 MB/s schreiben.** Die Blockgröße ändert nichts (1, 4 und 16 MiB liefern
denselben Wert, mit und ohne Puffer) - das ist die Grenze des MUSB-Gadget-Controllers, nicht des Protokolls. Damit:

| Wahl | Inhalt | Größe | Dauer |
|---|---|---|---|
| **klein** | nur das, was **nur** auf diesem Gerät existiert: Secure Storage (LBA 12288…14335), `private` (4891648), `Reserve0_a/b` (5489664 / 5522432) | **49 MiB** | **~7 s** |
| **voll** | die ganze eMMC, 15.269.888 Sektoren | 7,3 GB | **~17 min** |

**Warum die Wahl vertretbar ist:** alles außer dem Kleinen steht im Firmware-Image des Herstellers, und das ist online zu
haben (Marco, 10.09.). Wer den Vollabzug nimmt, kann sein Gerät 1:1 zurückspielen, ohne irgendetwas herunterzuladen. Wer
den kleinen nimmt, spart 17 Minuten und lädt sich im Fall der Fälle das Stock-Image.

**Was für beide gilt:**

- **Vor dem ersten Schreibzugriff.** Das Skript beginnt nicht, bevor der Abzug steht und geprüft ist. Kein `--skip-backup`;
  die Wahl ist *welcher* Abzug, nicht *ob*.
- **Der kleine Abzug ist nicht verhandelbar.** Was dort liegt, bringt kein Image zurück - der Fall vom 10.09.
  (`109` §9.1) ist genau daran entstanden.
- **Geprüft.** sha256 über den Abzug, zweite Lesung stichprobenweise verglichen (GPT, Secure-Storage-Block, ein zufälliger
  Bereich). Weicht etwas ab, bricht es ab - dann stimmt etwas mit der Verbindung oder der eMMC nicht.
- **Einspielbar.** Derselbe Weg rückwärts, ein dokumentierter Befehl: `hy310-install --restore <abzug>` schreibt ihn zurück.
  **Dieser Weg wird getestet, bevor v0.1 herausgeht** - ein ungetesteter Rückweg zählt nicht.
- **Beschrieben.** Neben dem Abzug landet eine Textdatei: Gerät, Datum, Prüfsumme, Sektorzahl, und in zwei Sätzen, wie man
  ihn zurückspielt. In einem Jahr weiß niemand mehr, was `hy310-emmc-20260910.img` war.

**Platz:** 7,3 GB für den Vollabzug, 49 MiB für den kleinen. Komprimiert wird **nicht** beim Schreiben (ein Abzug, den man erst
auspacken muss, ist im Notfall ein Schritt zu viel); wer Platz sparen will, komprimiert ihn danach selbst.

## 3. Extrahiert wird aus dem Abzug, nicht aus einem Download

`h713-extract` liest rohe eMMC-Abzüge bereits - belegt in [`S42`](nachtlog/S42-r2-extract.md) §3 mit
`re/device-dumps/emmc-first-300mb.bin`. Damit entfällt die Auflage aus `105` §1, dass der Nutzer sich ein Firmware-Image
besorgen muss.

Das ist auch lizenzrechtlich die sauberste Lage: **der Nutzer liest aus seinem eigenen Gerät.** Wir verteilen kein
Vendor-Material und er lädt keines herunter.

| Was | Woher im Abzug |
|---|---|
| `mips/*` - 19 Anzeige-Artefakte | `bootloader_b` (FAT16, LBA 139264) |
| `h713-arisc.bin` | `sunxi-package` roh bei LBA 24576 / 32800 |
| `hy310-edid.bin`, `msp-patch.bin`, PQ-Dateien | `super` → LP-Metadaten → `vendor_a` (ext4) |

**Das Gerät wird nie „unbekannt":** die Artefakte stammen aus genau der Firmware, die auf diesem Gerät lief. Der
Abweichungs-Fall aus `S42` tritt nur noch bei beschädigten Abzügen auf.

## 4. Warum der Installer auf den PC gehört

Bisher lief er auf dem Gerät und verlangte dort ein Linux - über Netzstart oder USB-Stick. Das war eine Erblast: er ist
dort entstanden, weil das Gerät ohnehin per Netz startete.

Nötig ist es nicht. Er arbeitet auf einem **Blockgerät**, und das liefert U-Boot über die Laufwerksfreigabe am selben
USB-Kabel, das schon für FEL steckt. Auf dem PC hat er außerdem alles, was auf dem Gerät fehlt: `sgdisk` wäre da,
`rsync`, Python-Bibliotheken, Plattenplatz für den Abzug - und er kann nicht das System zersägen, auf dem er selbst läuft.

**Was sich am Installer ändert:** wenig. Er hat `--device` und arbeitet ohnehin gegen ein Blockgerät. Zwei Prüfungen
entfallen (läuft das System vom Ziel? ist etwas eingehängt?), der Abzug kommt als erster Schritt dazu, und die Extraktion
liest aus dem Abzug statt aus einem mitgegebenen Verzeichnis.

## 5. Was zu bauen ist

| # | Teil | Stand |
|---|---|---|
| 1 | U-Boot-Bau mit Laufwerksfreigabe | ✓ **`hy310_installer_defconfig` gebaut und am Gerät bewiesen** (10.09.): FEL lädt es, das Gerät meldet sich als `Direct-Access Linux UMS disk`, alle sechs Partitionen sichtbar. Drei Dinge waren nötig: `ums` (Gadget, schließt Host-Modus aus), **`CONFIG_ENV_IS_NOWHERE=y`** - sonst gewinnt die gespeicherte Umgebung des Geräts und es bootet normal statt in die Freigabe - und `BOOTDELAY=0` ohne Gate |
| 2 | Messung: Durchsatz der Freigabe | ✓ **7,6 MB/s** (10.09., blockgrößenunabhängig) → Vollabzug 17 min, kleiner Abzug 7 s |
| 3 | `hy310-install` als PC-Skript | ✓ **gebaut und am Gerät getestet** (FEL, Freigabe, Abzug klein/voll, `--restore`, `--restore-stock` mit nachgebauter Stock-GPT). Kritisch geprüft ([`S46`](nachtlog/S46-kritische-pruefung.md)), sieben Befunde behoben (§5 dort). **Offen: der Abbild-Bauer** - `--abbild` hat noch keine Quelle |
| 4 | Rückspielweg getestet | **Pflicht vor v0.1** (§2) |
| 5 | Windows-Weg | offen. Das Herstellerwerkzeug spielt Allwinner-Images ein; ob sich unser Ergebnis so verpacken lässt, ist ungeprüft. **Nicht v0.1** |

## 6. Entschieden

- **Vollabzug ist Pflicht** und nicht abwählbar (Marco, 10.09.).
- **Kein Firmware-Image als Voraussetzung** - alles kommt aus dem Abzug.
- **Der Installer läuft auf dem PC**, nicht auf dem Gerät.
- **Nicht komprimiert schreiben.** Im Notfall zählt, dass der Abzug direkt einspielbar ist.
- **Der Rückspielweg wird getestet**, bevor v0.1 herausgeht.

## 7. Das Einspielen ist dasselbe wie das Abziehen (10.09. gemessen)

**Die Laufwerksfreigabe geht in beide Richtungen.** Damit ist der ganze Weg symmetrisch, und es braucht kein eigenes
Einspielwerkzeug:

```bash
dd if=/dev/sda of=hy310-backup.img    # sichern
dd if=hy310.img of=/dev/sda           # einspielen -- egal ob unser Abbild oder sein eigener Abzug
```

| Vorgang | Größe | Dauer bei 7,7 MB/s |
|---|---|---|
| kleiner Abzug | 49 MiB | 7 s |
| Vollabzug | 7,3 GB | 17 min |
| **unser Abbild einspielen** | **1,2 GB** | **~2,6 min** |
| eigenen Vollabzug zurückspielen | 7,3 GB | 17 min |

**Aus der Freigabe kommt man nicht heraus** - sie läuft, bis der Strom weg ist. Das ist kein Mangel, sondern der natürliche
Abschluss: nach dem Schreiben folgt ohnehin ein Kaltstart. Strom ziehen, wieder einstecken, fertig.

**Damit ist auch die Abbild-Frage beantwortet** (Marcos ursprünglicher Wunsch): der Nutzer bekommt eine Datei und schreibt
sie mit `dd`, wie bei einem Einplatinenrechner. Unser Abbild ist 1,2 GB statt 7,3 GB, weil das Wurzeldateisystem klein
gebaut ist und beim ersten Start per `x-systemd.growfs` auf die volle Partition wächst.

**Belegt am 10.09.:** Vollabzug dieses Geräts gezogen (`re/device-dumps/emmc-voll-HY310-dev-20260910.img`,
7.818.182.656 B = 15.269.888 Sektoren, sha256 `3c159da13eb603aa…`), sechs Stichproben gegen das laufende Gerät byteweise
gleich (GPT, SPL, U-Boot, Secure Storage, Umgebung, Rootfs-Anfang), und 128 MiB daraus fehlerfrei zurückgeschrieben.

## 8. Geräteerkennung vor dem ersten Schreibzugriff (Marco, 10.09.)

**Der Installer muss wissen, womit er es zu tun hat, bevor er etwas anfasst.** Nicht nur, um die richtigen Fundstellen zu
wählen, sondern um bei einer unbekannten Firmware **abzubrechen statt zu raten** - dieselbe Regel wie beim Secure Storage
([`109`](109-plan-layout-v3.md) §9).

**Es braucht keine Suche über die eMMC.** Der Weg zur Kennung ist ein gezielter Pfad, jede Stufe zeigt auf die nächste:

| Schritt | gelesen |
|---|---|
| GPT (Kopf + Tabelle) → wo liegt `super`? | 17 KiB |
| `super`: LP-Metadaten → wo liegt `vendor`? | 1 MiB |
| `vendor`: ext4-Superblock + Gruppendeskriptoren | 128 KiB |
| Wurzelverzeichnis + Inode von `build.prop` | 64 KiB |
| `build.prop` | 8 KiB |
| **zusammen** | **1,2 MiB → 0,2 s** |

Zum Vergleich: die ganze eMMC zu lesen dauert 17 Minuten.

**Was dabei herauskommt** (`ro.vendor.build.fingerprint`):

```
Allwinner/h713_tuna_p3/h713-tuna_p3:11/RP1A.201005.006/Projector07241019:user/release-keys
                                    ^^                                ^^^^^^^^
                                 Android 11                        Build 24.07.2025
```

HY310 trägt `07241019`, L018 `05141211` - beide sind dasselbe Referenzdesign `h713_tuna_p3` mit Android 11, nur zwei Monate
auseinander gebaut. `h713-extract` führt die Kennung bereits als Erkennungsmerkmal je Gerät (`GERAETE`-Tabelle).

**Der Android-Boot-Kopf taugt nicht** als billigere Abkürzung: das Feld `os_version` im `ANDROID!`-Header ist beim Hersteller
leer (`0.0.0`, Patch `2000-00`), geprüft an `boot_a.img` und `new-boot.img`.

**Verhalten des Installers:**

1. Kennung lesen (0,2 s), im Klartext melden: Gerät, Android-Version, Build-Datum.
2. Gegen die Tabelle bekannter Stände vergleichen.
3. **Bekannt** → weiter mit den für diese Version hinterlegten Fundstellen.
4. **Unbekannt** → abbrechen, Kennung ausgeben, um einen Fehlerbericht bitten. Kein `--trotzdem`: die Fundstellen einer
   fremden Version zu raten, kostet im schlimmsten Fall den Secure Storage.
5. **Kein Stock-Layout** (das Gerät wurde schon umgebaut) → sagen, was gefunden wurde, und nur den Abzug anbieten.

So wächst die Tabelle mit jedem gemeldeten Gerät, und für jede Version lassen sich eigene Fundstellen hinterlegen, ohne
dass ältere brechen.

## 9. Die Beta-Warnung ist Teil des Produkts (Marco, 10.09.)

Der Kasten oben ist keine Formsache und darf nicht wegredigiert werden. Er erscheint an drei Stellen:

| Wo | Wie |
|---|---|
| README des Repos | ganz oben, vor der Anleitung |
| `hy310-install`, vor dem ersten Schreibzugriff | als Abfrage, die eine getippte Bestätigung verlangt - nicht `[j/N]` |
| Release-Ankündigung | im ersten Absatz |

**Begründung, kurz:** Wir bauen eine Boot-Kette von Grund auf neu und überschreiben die Partitionstabelle eines Geräts, das
der Nutzer bezahlt hat. Wir haben bei genau einem Gerätetyp mit genau zwei Firmwareständen gemessen. Was bei einer dritten
Firmware an anderer Stelle liegt, wissen wir nicht - der Fall vom 10.09. ([`109`](109-plan-layout-v3.md) §9.1) zeigt, wie
schnell etwas unwiederbringlich weg ist, das niemand auf dem Schirm hatte.
