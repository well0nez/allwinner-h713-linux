# 148 — Plan: HDCP-1.4-Bootkette produktionsreif (Stand 05.10.2026, 08:xx)

Auftrag (Marco, 05.10. ~07:40): die neue Bootloader-Kette inklusive Installer
produktionsreif machen, Fehlerabfang auf Qualitätsniveau, die Lehren aus der Nacht fest
verdrahten, auf dem HY310 verifizieren, Repo-Dokus nachziehen — **noch nicht pushen**,
HY300-Test kommt danach.

## 0. Was vorher geklärt wurde (Messungen, nicht Annahmen)

| Befund | Beleg |
|---|---|
| Eigene Kette authentisiert HDCP 1.4, kein Herstellercode | `doku/147` Kap. 7; `bl31-solo.bin` hat 0 `opteed`-Referenzen |
| Senke nimmt key-select 3 nur aus dem TEE-Fenster an | `ESR 0x11` nach DRAM, `0x0` ab `0x48a00000` |
| op 1 entschlüsselt auf diesem Gerät nicht | gespeicherte 288 B byteidentisch zur Hersteller-Task-Quelle |
| Item-Struktur ist selbstbeschreibend | Magic/Name/Länge dekodiert, s. §1 |
| **Der HDCP-Schlüssel ist NICHT gerätegebunden** | 3 Regionen, 2 Seriennummern, 1 Schlüssel (`sha256(288)=d743dcf4…`) |
| Backups sichern ihn korrekt, `abbild-gefuellt.img` nicht | `secure-storage.bin` 0600 root; „gefüllt"-Abbild hat die Lücke genullt |

## 1. Die Item-Struktur des Secure Storage (gemessen, zwei Geräte)

Region ab LBA 12288 (0x3000), 2048 Sektoren = 1 MiB, Slots à 4096 B, jedes Item doppelt
(Original + Kopie). Es gibt **zwei Item-Arten**:

```
gemeinsamer Kopf
  0x00  u32   magic 0x17253948
  0x08  char  name[0x40]          NUL-terminiert
  0x60  u32   Länge der Nutzlast
  0x64  u8    Nutzlast[Länge]

kurze Items (snum, hdcpkeyV14_hash, hdcpkeyV22_hash, wifiBleDatas)
  Nutzlast liegt direkt auf 0x64, roh.      Beispiel snum: Länge 15, "(Seriennummer, nicht abgedruckt)"

Blob-Items (hdcpkey, hdcpkeyV22)
  Nutzlast ist selbst ein Item:
    +0x00 (0x64)  char name[0x40]   nochmals derselbe Name
    +0x40 (0xa4)  u32  innere Länge 0x140 = 320   (V22: 912)
    +0x44 (0xa8)  u32  0x10000001   Typ/Flags
    +0x48 (0xac)  u32  0x00000001
    +0x4c (0xb0)  u8   Daten[innere Länge]   ← 288 B für die Engine + 32 B Anhang
  äußere Länge = 0x4c + innere Länge  (396 = 76 + 320, geht exakt auf)
```

Prüfbar ohne Herstellerwissen: Magic, beide Namen, `0x4c + innen == außen`,
`0xb0 + innen <= 4096`, Original == Kopie, Nutzlast nicht ganz Null/0xff.
`hdcpkeyV14_hash` („581b62") passt zu **keinem** Prüfwert über den Chiffretext — der
Hersteller summiert über den Klartext, den nur das TEE sieht. Wird daher nicht verwendet.

## 2. Arbeitspakete

### A — Bootkette (U-Boot + BL31)
* **A1** Schlüsselquelle über einen **selbstbeschreibenden Leser** statt fester LBA/Offsets:
  Slots durchgehen, `hdcpkey` am Namen finden, Struktur nach §1 prüfen, Kopie vergleichen.
  Jeder Fehlerfall: Meldung, **weiterbooten ohne HDCP**, nie hängen.
* **A2** Der `raw`-Pfad wird der Normalweg. Entpack-Pfad (FID 0x82000018) und die
  Wickelschlüssel-Abhängigkeit entfallen — op 1 entschlüsselt nicht.
* **A3** Quittierungsfolge (`0x06840002`/`0x06840093`) raus, nachweislich Rauschen.
* **A4** Watchdog als Netz **um den HDCP-Schritt**: vorher scharf, nachher entschärft, damit
  ein Hänger im Push sich selbst heilt statt das Gerät zu parken.
* **A5** `BL32 at …`-Ausgabe hinter `H713_WITH_BL32`.
* **A6** Rollen/Defconfigs: HDCP-Teile in allen Release-Konfigurationen, für alle sechs
  Boards; `boards/check.sh` erweitern, damit ein Release ohne die Teile auffällt.
* **A7** Kein `h713_hdcp14_wait` dauerhaft speicherbar (hängt ohne Schlüssel).

### B — Installer
* **B1** `h713-extract`: Item nach §1 lesen, validieren, als `0600`-Datei ablegen, im
  Manifest **nur** Länge + sha256 vermerken, nie den Schlüssel. Fingerabdruck gegen den
  bekannten Satz prüfen und benennen („bekannter Herstellersatz" / „unbekannt, bitte melden").
* **B2** Restore **itemweise**, nicht pauschal: `snum` und `wifiBleDatas` sind gerätegebunden
  und dürfen nie von einem Fremdgerät überschrieben werden. Verweigern mit klarer Meldung.
* **B3** Repo-Wächter: ein Test, der fehlschlägt, sobald Schlüsselmaterial (bekannter
  Fingerabdruck, oder ein `hdcpkey`-Item in irgendeiner Datei) im Baum liegt.
* **B4** Warnung vor der Falle: `abbild-gefuellt.img` ist **kein** vollständiges Backup.

### C — Verifikation auf dem HY310
* **C1** Nach jeder Änderung: Löschen → `Desired`, Push → `Enabled`, **im selben Boot**
  (Regel aus `doku/147`; alles andere zählt nicht).
* **C2** Negativtests, jeder muss **booten** und darf nicht hängen:
  Slot genullt · Magic kaputt · Länge unplausibel · Kopie abweichend · Region ganz fehlt.
* **C3** Alle Rollen booten, Logo bis Login.

### D — Dokumentation in `repo-neu` (nicht pushen)
HDCP-Kapitel, Item-Struktur, die Messregel, der Nicht-Gerätebindung-Befund, die
Backup-Falle, und was der Installer verspricht.

## 3. Was bewusst NICHT gemacht wird
* Kein Schlüsselmaterial und kein Wickelschlüssel ins Repo — nur Fingerabdrücke.
* Op 10 des Hersteller-TEE (irreversibles eFuse-Brennen) wird nie aufgerufen.
* Kein eigenes S-EL1-Payload im Release (FB-HDCP14i funktioniert, ist aber unnötig: BL31 genügt).

---

# Durchführung (05.10., 08:0x–08:4x)

## A — Bootkette: erledigt und auf der Hardware bestätigt

`h713_hdcp14.c` neu geschrieben (315 → 337 Zeilen), und zwar nicht kosmetisch:

* **A1 Selbstbeschreibender Leser.** Der Schlüsselsatz wird über Magic, Name und Länge
  gefunden, nicht über feste Offsets; beide gespeicherten Kopien müssen übereinstimmen.
  Jeder Fehlerfall druckt eine Zeile und bootet weiter — hängen kann er nicht mehr.
* **A2** Der `raw`-Pfad ist der **Normalweg**. Entpack-Pfad, Wickelschlüssel, TSP-Fallback
  und die drei dafür nötigen Dateizugriffe sind weg: op 1 entschlüsselt nicht.
* **A3** Die Quittierungsfolge ist entfernt — nachweislich Rauschen.
* **A4 Watchdog um den Push**, 6 s, und **nur** wenn ihn gerade niemand sonst fährt
  (U-Boots eigener Treiber bleibt auf diesem Board aus). Doppelt gefahren wäre schlimmer
  als kein Netz.
* **A5** `BL32 at …` hinter `H713_WITH_BL32`.
* **A7** `h713_hdcp14=0` steigt sauber aus und **sagt es**.

### Zwei Fehler, die dabei auffielen

1. **Doppelte Logik an der Aufrufstelle.** `h713_mips.c` prüfte `h713_hdcp14` *auch* selbst,
   also wurde die Funktion bei `=0` nie betreten und es stand **nichts** im Log — ein Log, in
   dem „absichtlich übersprungen" und „dieser Build hat keinen HDCP-Code" gleich aussehen.
   Jetzt entscheidet eine Stelle, und sie redet.
2. **`__builtin_popcount` → `__popcountdi2`** zerlegte den Forschungsbau beim Linken, weil das
   compiler-rt-Objekt mit LTO nicht in den Link kommt. Von Hand gezählt.

## Härtung des EL3-Dienstes (neu, war nicht im Plan)

Im SiP hingen **13** Dienste, die meisten davon Werkbank: Engine-Tasks mit frei wählbarem
Schlüsselslot, Länge und Adresse, Deskriptor-Dumps, eFuse-Lesen. Das ist Angriffsfläche ohne
Gegenwert. Ein Release trägt jetzt nur noch **zwei**: `SVC_VERSION` und `PUSH_FROM`. Alles
andere steht hinter `H713_HDCP_RESEARCH=1`.

    Release   41076 Byte, 0 Forschungsstrings
    Werkbank  53372 Byte

Was erreichbar bleibt, ist bewusst beschränkt: eine Quelladresse im TEE-Fenster, feste Länge,
Ziel immer die Senke. Schlimmstenfalls installiert ein Aufrufer einen Satz, der nicht
authentisiert — auslesen kann er nichts, weil die Engine den Hardwareschlüssel nach lesbarem
Speicher verweigert.

## B — Installer: anders gelöst als geplant, und besser

Der Plan wollte den Schlüssel extrahieren. Richtig ist, ihn **nicht** anzufassen: U-Boot liest
ihn direkt aus dem Secure Storage, der Installer muss ihn nur überleben lassen — und das tat
er schon, inklusive Byte-Vergleich nach dem Schreiben und Abbruch mit Exit 10. `h713-extract`
bleibt bei „Never touched: HDCP/DRM keys".

Neu ist deshalb die **positive Aussage**, die niemand hatte:

* `installer/h713/hdcpkey.py` (352 Zeilen) liest dieselbe Struktur wie der C-Code und sagt beim
  Installieren, ob der Satz heil ist — oder warum nicht.
* `installer/h713-hdcpkey` **sucht** die Items, statt die Region zu unterstellen. Für ein
  unbekanntes Board ist „kein Schlüssel an LBA 12288" sonst nur eine Lüge über die eigene
  Blickrichtung. Was es nicht kennt, gibt es als Fingerabdruck samt den Zeilen zum Eintragen
  aus. 64 MiB in 0,089 s.
* `installer/tests/no_key_material.py` bricht den Build, sobald Schlüsselmaterial in einer
  verfolgten Datei liegt. 1131 Dateien in 6 s.

### Befund: 1.4 ist geteilt, 2.2 ist gerätegebunden

| | HY310 | HY300 Pro |
|---|---|---|
| HDCP 1.4 (288 B) | `d743dcf4…` | `d743dcf4…` — **gleich** |
| HDCP 2.2 (912 B) | `59598951…` | `fa0a8bd8…` — **verschieden** |

Drei Regionen, zwei Seriennummern. Daraus folgt beides: der 1.4-Satz darf erst recht nicht ins
Repo (geteilter Schlüssel einer Produktlinie), und eine **Fremdregion darf nie** auf ein Gerät
zurückgespielt werden — sie würde dessen eigenen 2.2-Satz, Seriennummer und MACs überschreiben.

### Falle, die bleibt
`abbild-gefuellt.img` / `image-filled.img` sind **kein** vollständiges Backup: der Secure
Storage liegt in einer Lücke zwischen Partitionen und ist dort genullt. Die Regionsdatei
`secure-storage.bin` (0600 root) trägt ihn — die Manifeste belegen es für beide Geräte.

## Tests

* Parser des **ausgelieferten C-Codes** auf dem Host, 12 Fälle, gegen synthetische Slots und
  gegen alle vier echten Regionen: nimmt alle vier an, lehnt das genullte Abbild ab.
* `test_hdcpkey.py` 23 Fälle, `test_no_key_material.py` 6 Fälle — beide mit synthetischen
  Fixtures, weil der echte Schlüssel dafür nicht ins Repo darf.
* **Volle Suite: 326 Tests OK**, 52 übersprungen (brauchen lokale Hersteller-Fixtures).

## Das Release-Tor, und zwei Fehler darin

`release/check-hdcp-artifacts.sh` urteilt über die **Artefakte**, nicht über die Quellen — dort
passiert der Fehler, den Marco befürchtet: ein Stück, das nicht im wirksamen Defconfig steht,
kompiliert sich lautlos weg. Zwei eigene Fehler im Tor fielen dabei auf:

1. **`set -o pipefail` + `grep -q`.** `grep -q` steigt beim ersten Treffer aus, `strings` stirbt
   an SIGPIPE mit 141, und das wird der Status der Pipeline — ein **vorhandener** String wurde
   als fehlend gemeldet. Das Tor hätte jedes Release blockiert. Jetzt `grep -c`.
2. **Falsch-Alarm auf `h713_hdcp14_wait=1`.** Der Treffer war die Diagnosemeldung aus
   `h713_mips.c`, die den Namen im Klartext nennt. Ein Env-Eintrag steht als eigene Zeile:
   `grep -x` unterscheidet das.

Danach: **green: may be released.**

## C — Verifikation auf dem HY310, mit dem Produktions-Image

Gebaut über den **Produktionsweg** (`mainline/build/uboot-build.sh`, Board `hy310`, Rolle
`release`) — damit ist auch A6 beantwortet: `CONFIG_H713_MIPS_BOOT=y` steht in der Rolle.

| Lauf | gesetzt | Konsole | Quelle |
|---|---|---|---|
| A | `h713_hdcp14_wipe=1` | `sink overwritten with zeros (0x0)` | **Desired** ✓ |
| B | nichts (Default) | `1.4 key set handed to the receiver` | **Enabled** ✓ |
| D | `h713_hdcp14_wipe=1` | `sink overwritten with zeros (0x0)` | **Desired** ✓ |
| E | `h713_hdcp14=0` | `skipped on request (h713_hdcp14=0)` | **Desired** ✓ |
| A' | `h713_hdcp14_wipe=1` | `sink overwritten with zeros (0x0)` | **Desired** ✓ |
| B' | nichts (Default) | `1.4 key set handed to the receiver` | **Enabled** ✓ |

A'/B' sind die Wiederholung mit dem **endgültigen** Image (nach der Entdopplung an der
Aufrufstelle) — damit gehört die Messung zu genau dem Artefakt, das ausgeliefert würde.
Drei Paare, alle drei erfüllt.

Lauf B lief über den **neuen Standardpfad** — der selbstbeschreibende Parser hat den Schlüssel
selbst gefunden. Die Messregel ist in beiden Paaren erfüllt.

Ein eigener Fehlschlag gehört dazu: der erste Negativtest (Lauf C) setzte `h713_hdcp14=0`
**ohne** vorher zu löschen und meldete „Enabled" — genau die kontaminierte Messung, vor der die
Regel warnt, denn die Senke hielt noch den Schlüssel aus Lauf B. Mein Testaufbau war falsch,
nicht der Code; D+E ist die richtige Form.

## Anbindung ans Release-Repo

Der Commit liegt als `FB-HDCP14h/patches/0083-sunxi-h713-hand-the-projector-its-own-HDCP-1.4-key-set.patch`
und **passt sauber** auf den Submodul-Stand (`git apply --check`: nur Zeilenversatz).

**Offen, und Marcos Entscheidung — hier ist ein vorgefundener Versatz:**

    da74b89   SERIES.txt (Spiegel, count 82)
      +7      ->  4cecddd   mainline/external/u-boot, detached HEAD
      +5      ->  6fb736c   FB-HDCP14h/uboot (HY300PRO-G-EU-Arbeit u.a.)
      +1      ->  4c293e6   dieser HDCP-Commit

Die Patchdateien in `uboot-h713/` sind **generiert, nicht gepflegt** (README, P3). Ein
Neuerzeugen würde also 13 Commits in den Spiegel ziehen, von denen 12 nichts mit HDCP zu tun
haben. Das von Hand als `0083` abzulegen würde die Regel brechen. Darum: Patch bereitgestellt,
Entscheidung über Fork-Kopf und Neuerzeugung nicht eigenmächtig getroffen.

## Nicht gemacht, mit Grund

* **Kein `BUILDING.md`-Eintrag für gnutls.** Mein Direktbau am Host brach an fehlenden
  `libgnutls28-dev`-Headern ab, und ich hielt das zuerst für einen Produktionsmangel. Falsch:
  `docs/build-container.md` installiert das Paket, und laut `BUILDING.md` wird „nothing built
  on your host". Der Release-Bau ist nicht betroffen.
* **FB-HDCP14i** (eigene S-EL1-Nutzlast) bleibt liegen: funktioniert, ist aber unnötig.
  `CONFIG_SUNXI_TEE` ist im Release `n`, der Code also nicht einmal kompiliert.
* **Kein beschädigter Schlüsselsatz auf der Hardware erzwungen.** Dafür müsste in den Secure
  Storage geschrieben werden; die Fehlerfälle prüfen die Host-Tests.

## Endstand der Prüfungen

    release/check-hdcp-artifacts.sh    green: may be released
      (auch auf der Artefaktform, die build-all.sh uebergibt: U-Boot proper ohne SPL)
    boards/check.sh                    green (0 failures, 0 notes)
    installer/tests/run.sh             326 Tests OK, 52 uebersprungen
    Hardware HY310                     3 Paare nach der Messregel, alle erfuellt

Das Tor hängt jetzt in `release/build-all.sh` Schritt 10 — ein Tor, das niemand ruft, ist
keines. Ein Release mit fehlendem HDCP-Teil, mit Werkbank-Diensten oder mit Schlüsselmaterial
bricht den Bau ab.

## Geänderte Dateien

**Bootkette** (`FB-HDCP14h/`)
    uboot/arch/arm/mach-sunxi/h713_hdcp14.c          neu geschrieben, 337 Zeilen
    uboot/arch/arm/mach-sunxi/h713_mips.c            Aufrufstelle entdoppelt
    tfa/plat/allwinner/sun50i_h713/sunxi_h713_sip.c  Forschungsdienste hinter den Schalter
    tfa/plat/allwinner/sun50i_h713/platform.mk       H713_HDCP_RESEARCH verdrahtet
    tfa/plat/allwinner/common/sunxi_bl31_setup.c     BL32-Ausgabe hinter H713_WITH_BL32
    bauen.sh                                         reproduzierbarer Bau, beide Varianten
    patches/0083-...-HDCP-1.4-key-set.patch          serienreif, passt auf 0082

**Release-Repo** (`repo-neu/`)
    installer/h713/hdcpkey.py                 neu, 352 Zeilen
    installer/h713-hdcpkey                    neu, Werkzeug fuer unbekannte Boards
    installer/h713/install.py                 positive HDCP-Aussage beim Installieren
    installer/tests/no_key_material.py        neu, Waechter
    installer/tests/test_hdcpkey.py           neu, 23 Faelle
    installer/tests/test_no_key_material.py   neu, 6 Faelle
    release/check-hdcp-artifacts.sh           neu, Artefakt-Tor
    release/build-all.sh                      Tor in Schritt 10
    docs/subsystems/hdcp.md                   neu, 138 Zeilen
    docs/subsystems/crypto-engine.md          querverlinkt
    docs/services.md, docs/README.md          nachgezogen
    STATUS.md, ROADMAP.md, README.md          "HDCP 1.4 missing" -> works
    boards/hy310/README.md                    dito

Nichts ist gepusht.
