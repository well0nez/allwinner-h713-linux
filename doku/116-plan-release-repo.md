# Plan 116 — Vom Arbeitsverzeichnis zum Repo, vom Repo zum Release v0.1

Stand 12.09.2026, nach dem Gespräch über Repo-Struktur, U-Boot, Patches und Doku. Löst den Teil R3/R4/R6 aus
[`105`](105-plan-release.md) ab; die Punkte dort gelten weiter, wo sie hier nicht widersprochen werden. Offene
Punkte: [`61-todo.md`](61-todo.md). Handoff mit Pfaden und Befehlen: [`115`](115-handoff-20260912.md).

## 1. Ausgangslage — gemessen, nicht gemeint

- Das Arbeitsverzeichnis hat 37 GB: `re/` 27 GB, `mainline/build` ~20 GB, `analyse/` 6,5 GB, Abzüge 2,4 GB. Was
  ins Repo gehört (`doku`, `userspace`, `patches`, `tools`, Installer, Rootfs-Rezept), sind **rund 30 MB**. Das
  Repo existiert noch nicht — es muss herausgeschnitten werden.
- Unsere Kernel-Serie (127 Patches) ist ein **Superset** von cstengers (46): 45 byteidentisch, einer umbenannt
  (`0009` keystone → focus), **drei seiner Basis-Patches in-place editiert** (`0014`, `0015`, `0024`), 82 eigene
  darüber. Von den 127 ändern **rund 100 bestehende Mainline-Dateien**; ~22 fügen Treiber hinzu.
- cstengers `main` steht seit `8860991` still; er arbeitet auf `h713-display-video-path` und
  `wip/crypto-ce-tooling` an einem anderen Produkt (Desktop-Linux mit Video-Runtime). Wir bauen ein
  HDMI-Eingangsgerät. Derselbe Kernel, verschiedene Ziele.
- Die Submodul-Zeiger unter `mainline/external/` zeigen auf **cstengers** Forks (U-Boot, TF-A, sunxi-tools). Unsere
  Commits darauf liegen nur lokal (U-Boot `4091ea68c06`, 33 Patches in `uboot-h713/`).
- Mehrere Bausteine des Abbilds sind **von Hand** abgelegt (`tftp/spl-release.bin`, `tftp/hy310-env-release.bin`,
  `r2-extract/out-hy310-20260912`). Aus einem frischen Klon lässt sich v0.9 heute nicht bauen.
- Das alte Repo `well0nez/allwinner-h713-linux` hatte die **Leserführung**, die wir übernehmen: README mit
  ehrlichem Status und Leseordnung, `STATUS.md` als Tabelle, `docs/subsystems/*.md`, `known-issues`,
  `FLASHING`/`BUILDING`/`ROOTFS`. Es hatte keinen reproduzierbaren Bau und keinen Nutzerweg.

## 2. Entscheidungen (Marco, 12.09.)

| Frage | Entscheidung |
|---|---|
| Treiber als Quellverzeichnisse oder als Patches? | **Patches, eine Serie, ein `build.sh`** (cstengers Modell). Lesbarkeit über Abschnitte in `series` und eine Tabelle im README — nicht über eine zweite Ablage. Begründung: ~100 von 127 sind ohnehin echte Änderungen; ein zweiter Baumechanismus hat uns bei aic8800 zwei Löcher gekostet |
| cstengers Repo als Submodul (Plan 105 R3)? | **Nein — `git subtree`** nach `mainline/`, mit seiner Historie. Kein Klon hängt an seinem GitHub; `subtree pull` holt seine Fixes; `format-patch` liefert PRs zurück |
| U-Boot, TF-A, sunxi-tools | **Eigene Forks unter `well0nez`**, als Submodule. `uboot-h713/*.patch` bleibt als *erzeugte* Leseansicht |
| Partitionsnamen `hy310-*` | **bleiben** |
| `h713_ce_test` lädt automatisch | **bleibt drin** |
| `analyse/hdcp-keys/` | **nicht löschen** — nach `re/hdcp-keys/` verschieben; `re/` bleibt vollständig lokal |
| Abbild- und Tag-Namen | intern v0.9 → öffentlich **`h713-hy310-v0.1-beta`**, Tag `v0.1-beta`; „hy713" verschwindet |
| Windows | **v0.1 Linux-only.** Windows steht als *ungetestet, keine Gewähr, auf Rückmeldungen angewiesen* in der Anleitung; `sunxi-fel.exe` liefern wir nicht |
| Sprache der Doku | **Englisch für Werkzeuge, Installer, Tests, Sackgassen, Status, Anleitung.** `doku/` bleibt deutsch und wird verlinkt. Das **Destillieren** des deutschen Wissens in eine englische Wissensdatenbank kommt **nach dem Release** — bedacht, nicht per grep (§6) |
| Deutsch in Modulen und Werkzeugen (Kommentare, Meldungen) | **TODO nach dem Release** |
| Testskripte veröffentlichen | **TODO**, wird in späteren Sitzungen entschieden — welche ohne unseren Tisch laufen, welche RE sind |
| Zweite Person für die Generalprobe | **Nein.** Marco setzt das Gerät auf Stock zurück, Claude geht den Nutzerweg aus dem veröffentlichten Klon. Der Verlust von `Reserve0`/`private` ist akzeptiert; der Installer muss anschlagen, sobald etwas nicht stimmt |
| Veröffentlichen | **Noch nicht.** Erst wenn P1–P6 stehen. Bis dahin gilt: der Sperr-Scan läuft vor jedem Export, und trotzdem schaut ein Mensch drauf |

## 3. Ziel-Layout des Repos

```
allwinner-h713-linux/  (well0nez; main neu, alter Stand als Tag legacy-arm32-2026-08 + Branch legacy)
├── README.md  STATUS.md  FLASHING.md  BUILDING.md  LICENSE*  PROVENANCE.md      Englisch
├── docs/                 Englisch: tools/ (h713-tv, -pq, -focus, -cam, -wifi, -extract, -install), installer,
│                         tests, dead-ends, subsystems (kurz, mit Verweis nach doku/)
├── doku/                 Deutsch, das Arbeitsjournal, unverändert (115 Dateien + nachtlog/)
├── mainline/             git subtree von cstenger/allwinner-h713-mainline@8860991
│   ├── patches/kernel/   unsere Serie (Superset), series mit Abschnitten
│   ├── patches/aic8800/
│   ├── external/{u-boot,arm-trusted-firmware,sunxi-tools}   Submodule → well0nez-Forks
│   └── build/build.sh
├── uboot-h713/           erzeugt aus dem Fork (format-patch), nur zum Lesen
├── userspace/            h713-tv  h713-pq  h713-focus  h713-cam
├── installer/            hy310-install.py  h713-extract  hy310-mkimage.py  mkimage-selbsttest.py
│                         mkimage-eingaben.sh  installer-fahren.py            (heute analyse/release/arbeit/{r0-fel,r2-extract})
├── rootfs/               build-rootfs.sh  install-projekt.sh  packages.txt  overlay/  tests/   (heute analyse/release/arbeit/rootfs)
├── tools/                uart-*.py, regdiff, …
├── tests/                (§6: Auswahl steht noch aus)
└── release/build-all.sh  EIN Einstieg: frischer Klon → bl31 → U-Boot + Env → Kernel → aic8800 → Rootfs
                          → ext4-Eingaben → Abbild → Selbsttest „ALLES GRÜN"
```

**Draußen bleibt:** `re/` (inkl. `hdcp-keys`), `mainline/build/`, `hy310-sicherung*`, `tftp/`,
`patches-snapshots/`, `agenten/`, `legacy/` (→ Branch), und aus `analyse/` alles außer dem, was nach `installer/`
und `rootfs/` zieht. **`analyse/` wird nicht ausgedünnt** (Marco, 12.09.): es wird beim Destillieren in die
englische Wissensdatenbank (§6) ohnehin neu kategorisiert, zusammengeführt und umgeschrieben — Ausdünnen vorher
wäre doppelte Arbeit. Bis dahin ist `analyse/` *nicht* Teil des Exports, außer den genannten Umzügen. Die
Testskripte darin sind eine eigene Frage (§6, Testskripte).

## 4. Phasen

| | Was | Bedingung | Aufwand |
|---|---|---|---|
| **P1** Serie bereinigen | Unsere Edits an `0014`/`0015`/`0024` als eigene Patches ausgliedern (cstengers 46 werden byteidentisch); `series` in Abschnitte: Basis (cstenger) · Treiber · Fixes · Board; Bau danach identisch (Image-Hash vergleichen) | — | ½ Tag |
| **P4** `release/build-all.sh` | **zuerst nach P1, dringend.** Vom frischen Klon bis „ALLES GRÜN", im Container, mit Versionsstempel (Git-Hash → Tabelle, LIESMICH, Abbildname). Erzeugt auch `hy310-env-release.bin` aus dem U-Boot-Bau und den Extrakt-Schritt **nicht** (der kommt vom Nutzer). Beweis: v0.9 funktional gleich | P1 | 1 Tag |
| **P2** Forks | `well0nez/u-boot` (h713), `…/arm-trusted-firmware`, `…/sunxi-tools`; Submodul-Zeiger umbiegen; `uboot-h713/` aus dem Fork erzeugen | — | ½ Tag |
| **P3** Skelett | Lokal als neues Git aus dem Export aufbauen (Skript, wiederholbar): Tag/Branch legacy, `main` neu, subtree, Umzüge, `.gitignore`, **Sperr-Scan** (`re/`, Schlüssel, Blobs, Abzüge, `tvconfig`, Hashes bekannter Vendor-Dateien) als Skript **und** als Pflicht vor jedem Push. Diff gegen das alte Repo. **Kein Push in dieser Phase** | P1, P2 | 1 Tag |
| **P5** Doku Englisch | README (Leseordnung wie früher, Beta-Warnung, Linux-only, Windows ungetestet), STATUS-Tabelle mit Beleg je Zeile, FLASHING = Nutzerweg, BUILDING = `build-all`, `docs/tools/*` je Werkzeug, `docs/dead-ends.md` aus `70`, `docs/subsystems/*` kurz mit Verweis. Namen geradeziehen. **Pflichtabschnitt „the device waits for the power key“**: nach dem Einspielen startet das Gerät beim Einstecken nicht von selbst — das ist Absicht (`CONFIG_H713_POWER_GATE=y` + `h713_gate=1`), wer es nicht weiß, hält das Gerät für tot. Dazu: `fw_setenv h713_gate 0` schaltet es ab, `reboot` aus Linux geht durch, FEL-/Installer-U-Boot fragt nie (§2) | P4 | 2 Tage |
| **P6** Generalprobe | Marco: Gerät auf Stock (`--restore-stock`, Android bootet). Claude: **aus dem Klon** `build-all` → Nutzerweg (FEL, voller Abzug, Extraktion, Abbild) → Abnahme nach [`61-todo`](61-todo.md) A.1/A.3 + `analyse/boot/abnahme-*`. **Dabei mitschneiden:** Terminalsitzung des ganzen Nutzerwegs (`script`/asciinema) als Beleg und als Grundlage für ein Einspielvideo. Dazu die offenen Gerätetests: Telefon am AP, `mode=sta`, Kamera hell, Env-Übernahme | P3, P5 | 1 Tag |
| **P7** Release | Push, Tag `v0.1-beta`, Release-Assets: drei Abbildteile + Tabelle + `installer/` als Zip, Beta-Text | P6 | ½ Tag |
| **P8** PRs an cstenger | Die generischen: `0022` Env-Offset, pinctrl-IRQ `0143`/`0144`, die Ausgliederungen aus P1 | P7 | ½ Tag |

Summe **sieben bis acht Arbeitstage** plus die Gerätetests. Reihenfolge: **P1 → P4** (ohne Rückfrage startbar),
dann P2/P3 parallel, P5, P6, P7, P8.

## 4a. Fortschritt — wird während der Arbeit gepflegt (Haken = am Baum bewiesen, nicht „gemacht")

**Sicherheitskopie vor P1:** ☑ `/opt/Projekte/h713-backups/20260912-vor-p1/` (752 MB, Prüfsummen ok; u-boot.bundle
mit den 33 lokalen Commits; sunxi-tools-Falltür liegt **uncommitted** als `.diff` — P2 muss sie committen).

### P1 Serie bereinigen
- ☑ P1.1 Vermessen: es waren **vier**, nicht drei — `0014` (cpu_comm-Umbau 04.09., +3194/−782), `0015`+`0024`+`0009` (keystone→focus-Umbenennung, dazu in `0024` der cpu_comm-Fix reg 0x1000/IRQ 46 und `&cpu_comm okay`), und `0078` aus cstengers **Zweig** (Probe-Zusicherung ohne 1280×720)
- ☑ P1.2 Fünf Nachträge, je direkt hinter dem Original: `0014a` (cpu_comm-Stand, 5894 Zeilen), `0024a` (reg/IRQ — PR-Kandidat), `0024b` (Umbenennung über Treiberdatei, Kconfig, Makefile, DTS — PR-Kandidat), `0024c` (Board: `cpu_comm okay`), `0078a`. Erzeugt aus Baum-Diffs (`diff -ruN` zweier gepatchter Bäume), nicht von Hand; Löschung mit `+++ /dev/null`, sonst bleibt eine leere Datei stehen
- ☑ P1.3 **0 von 46** abweichend zu `origin/main` (`cmp` gegen `git show`), **0 von 16** Zweig-Patches abweichend zu `origin/h713-display-video-path`. Achtung: `git diff origin/main -- pfad` log wegen einer alten Index-Löschung — `cmp` gegen `git show` ist der belastbare Vergleich
- ☑ P1.4 `series` mit 13 Abschnitten (Herkunft + Thema, mit doku-Verweisen); `build.sh` überliest `#`/Leerzeilen jetzt in allen vier Serienschleifen (Kernel + aic8800, Digest + Anwenden) — vorher wäre jede Kommentarzeile ein Dateiname gewesen. `0152` zu Abschnitt 9, `0155` hinter 11 gezogen (unabhängige Dateien; Identität danach erneut bewiesen)
- ☑ P1.5 Baum-Identität **bewiesen**: alte Serie (Snapshot `20260912-1432-vor-p1`, 127) und neue (132) auf je einen frischen Tarball → `diff -rq` = **0 Unterschiede** (dreimal, nach jeder Änderung). Nebenbefund: 19 `.orig`-Dateien durch Fuzz — in beiden Bäumen gleich, auch im echten Baubaum; kein `.rej` → Kleinkram D. **Bau mit `build.sh` durchgelaufen:** `applied 132 series patches`, Baum `b8969983`, Quellen identisch zu `f7dd06d0` (nur `Image` = Zeitstempel). ☑
- ☑ P1.6 `115` §2, `61-todo` A.6/P8/D nachgezogen; Snapshots `20260912-1432-vor-p1` und `-nach-p1`. **P1 abgeschlossen 12.09., 15:15.**

### P4 `release/build-all.sh`
- ☑ P4.1 Inventar der Eingaben (12.09.) — **sieben** Stellen, an denen heute Handarbeit oder der Entwicklungsrechner steckt:

  | Eingabe | heute | woher in `build-all` |
  |---|---|---|
  | `bl31.bin` | `build.sh bl31` ✓ | unverändert |
  | SPL + U-Boot proper | `uboot-build.sh`, dann **von Hand** `head -c 32768`/`tail -c +32769` nach `tftp/*-release.bin` | Schritt im Skript, Ausgabe nach `build/out/`, `hy310-mkimage --spl/--uboot` explizit |
  | U-Boot-Umgebung | **von Hand**: `make u-boot-initial-env`, `awk`-Dedup, `tools/mkenvimage` → `tftp/hy310-env-release.bin` | Schritt im Skript, direkt nach U-Boot |
  | Kernel + FIT | `build.sh kernel` ✓; `modules_install` **von Hand** mit Baum-Hash | Skript ermittelt den Baum und installiert nach `build/modroot.<hash>` |
  | aic8800-Module | `build.sh aic8800` ✓ (muss **nach** dem Kernel laufen) | Reihenfolge erzwungen |
  | **Debian-Keyring für trixie** | `rootfs/out/keyring/…gpg` — **kopiert aus der NFS-Wurzel `/srv/h713-rootfs`** des Entwicklungsrechners (der Container hat nur 2023.4/bookworm) | `debian-archive-keyring`-.deb von deb.debian.org holen, `sha256` gepinnt in `config/versions.env`, `.gpg` extrahieren |
  | **`h713-tv` quer bauen** | `make cross SYSROOT=/srv/h713-rootfs` — **gegen die NFS-Wurzel** (2,5 GB, nur auf diesem Rechner); die Binärdatei liegt im Baum | Sysroot aus `mmdebstrap --variant=extract --include=libdrm-dev,libasound2-dev` (~30 MB) nach `build/sysroot-arm64`, dann `make cross` dagegen |
  | Rootfs, ext4-Eingaben, Abbild | drei Skripte, drei Aufrufe, `FIT=` per Umgebung | eine Kette; Selbsttest ohne `--vendor` nur als `--pruefen`, mit `--vendor` voll |
- ☑ P4.2 `release/build-all.sh` geschrieben (elf Schritte, treibt den Container; `--version` Pflicht, `--vendor`, `--wifi-env`, `--skip-*`, `--dry-run`; Pfadblock oben für P3). Dazu `release/sysroot-fix.py`. **Schritt 6 einzeln bewiesen:** Sysroot aus `mmdebstrap --variant=extract` (104 MB, `libc6-dev,libgcc-14-dev,libdrm-dev,libasound2-dev`), merged-usr-Links fehlen ohne Maintainer-Skripte, der Helfer legt sie an; `h713-tv` baut dagegen (293 240 B, `libdrm.so.2`/`libasound.so.2`/`libc.so.6`). **Schritt 5 bewiesen:** `debian-archive-keyring_2025.1_all.deb` (sha256 `9ea7778e…`) liefert den byteidentischen Keyring
- ☑ P4.3 Stempel `out/<name>.BUILD.txt` (Serie-Hash, defconfig-Hash, Kernelbaum, HEADs der drei Forks mit "+uncommitted", U-Boot-Kennung, sha256 aller Bausteine); Name `h713-hy310-vX.Y`. Im Skript; Beweis mit P4.4
- ☑ P4.4 **Erster Lauf 12.09., 15:00:** `release/build-all.sh --version v0.10 --vendor r2-extract/out-hy310-20260912` → elf Schritte, **9 min 58 s** (Kernelbaum `b8969983` wiederverwendet), `--pruefen` ok, **Selbsttest mit Vendor-Dateien ALLES GRÜN**, Stempel `out/h713-hy310-v0.10.BUILD.txt`. Bausteine gegen v0.9: Kernelquellen identisch, U-Boot derselbe Commit, **Umgebung byteidentisch** (`b3b463f2…`), Rootfs aus demselben Rezept, `h713-tv` erstmals gegen den reproduzierbaren Sysroot. Noch kein Klon-Lauf (P3 fehlt), aber keine Eingabe stammt mehr aus `tftp/` oder `/srv/`
- ☑ P4.5 `115` §4 zeigt jetzt auf `build-all`; `61-todo` A.6 P4 abgehakt. **P4 abgeschlossen 12.09., 15:05.** Offen bleibt der Beweis vom frischen Klon; der kommt mit P3

### P2 Forks (12.09., 15:30)
- ☑ P2.1 Bestand: `well0nez/u-boot` existiert seit 31.08. als **öffentlicher** Fork (PR-Zweige `h713-usb-host`, `h713-display` alt); TF-A und sunxi-tools fehlten. Ein Fork lässt sich bei GitHub nicht privat schalten.
- ☑ P2.2 sunxi-tools: die S44-Falltür war **uncommitted** (61 Zeilen in `fel.c`, `soc_info.[ch]`) → Commit `269dfa2` auf Zweig `h713`.
- ☑ P2.3 TF-A: unser Gate-Commit `dfa9fab44` auf Zweig `sun50i-h713` (war losgelöst).
- ☑ P2.4 **Private** Repos `well0nez/sunxi-tools` (h713 = 269dfa2, master) und `well0nez/arm-trusted-firmware` (sun50i-h713 = dfa9fab44, master) angelegt und gepusht; Standardzweige gesetzt. Inhalt vorher auf IPs/Schlüssel/Pfade geprüft: nichts. Push mit `-c credential.helper='!gh auth git-credential'` — keine globale Git-Konfiguration angefasst.
- ☐ P2.5 **U-Boot nicht gepusht** (Fork ist öffentlich = Publizieren). Lokal Zweig `h713-hy310` = `4091ea68c06` angelegt. **Push bei P7**, dann auch `.gitmodules`-Zeiger auflösbar. Bis dahin scheitert `git submodule update` in einem frischen Klon am U-Boot — bekannt, internes Stadium.
- ☑ P2.6 Erkenntnis für P3: cstengers `.gitmodules` benutzt **relative URLs** (`../u-boot.git`) — unter `well0nez/allwinner-h713-linux` zeigen sie von selbst auf `well0nez/*`. Umzubiegen ist nichts; die Repos müssen nur existieren und die gepinnten Commits tragen. Zweignamen dort: `h713` (u-boot, sunxi-tools), `sun50i-h713` (TF-A). **Nachtrag P3:** Git liest nur die `.gitmodules` an der **Wurzel** — die im Subtree unter `mainline/` wirkt nicht. Das Skelett schreibt darum eine eigene an die Wurzel (Pfade `mainline/external/*`, dieselben relativen URLs, U-Boot-Zweig `h713-hy310`).
- ☑ P2.7 `uboot-h713/*.patch` aus dem Fork **erzeugt** — Schritt 5 von `release/repo-skelett.sh` (`git format-patch 8fe568cdfc4..4091ea68c06`, dazu `SERIES.txt` mit Basis/Kopf/Anzahl). **33 von 33 inhaltsgleich** mit den von Hand gepflegten (Vergleich über den Betreff; die Handnummerierung hatte 0017/0018 vertauscht). Die Handkopien `configs/`, `drivers/` vom 31.08. entfallen im neuen Repo.

### P3 Skelett (12.09., 18:40 — nach einem Stromausfall um ~17:45; alle Dateien waren vollständig)
Skript: **`release/repo-skelett.sh [--ziel DIR] [--neu]`** → `repo-neu/` (unter der Projektwurzel, damit der Container es sieht). Läuft in 5 s, wiederholbar, verändert nichts im Arbeitsbaum, **pusht nicht**. Log: `analyse/release/arbeit/logs/repo-skelett-*.txt`.
- ☑ P3.1 **Pfad-Unabhängigkeit** der Werkzeuge: `build-rootfs.sh`, `install-projekt.sh`, `mkimage-eingaben.sh`, `hy310-mkimage.py` finden die Wurzel über den Marker `mainline/build/build.sh`; `build-all.sh` erkennt beide Layouts (`installer/`+`rootfs/` an der Wurzel gewinnt, sonst `analyse/release/arbeit/…`) und leitet `WORK` aus den Container-Mounts ab. Vorgaben für SPL/U-Boot/Env/FIT zeigen auf `mainline/build/out/` (tftp/ nur Rückfall).
- ☑ P3.2 **Lücke im Nutzerweg geschlossen:** `build-all` baute weder den **Installer-U-Boot** (`hy310_installer_defconfig`, FEL→ums) noch **`sunxi-fel`** mit der Falltür — beides kam bisher aus Handablagen. Jetzt Schritte **2b** (`out/u-boot-installer.bin`, Prüfung auf `ums 0 mmc 1`) und **2c** (`out/sunxi-fel`, Prüfung auf `FEL trap door`; Container hat libusb). Im Stempel.
- ☑ P3.3 `legacy`: Branch aus dem alten `master` (19c7a78, 110 Commits), Tag **`legacy-arm32-2026-08`**, alter Tag `pre-overhaul-2026-05-25` bleibt.
- ☑ P3.4 `main` setzt auf `legacy` auf (Historie bleibt verbunden): Commit „tree: retire the arm32 layout" räumt 416 Dateien aus, dann **`git subtree add --prefix=mainline` von cstenger `8860991`** ohne Squash (Herkunft jedes Patches per `git log` lesbar; cstengers Historie ist 6,5 MiB gepackt), dann unsere Auflage (Serie 132 Patches — **byteidentisch zur Arbeitskopie bewiesen**, `build.sh`, defconfig + `debug.config`/`netboot.config`, aic8800 series + 0007, `gles-play.c`, `zurueckgenommen/`, `vorschlaege/`) mit den **Fork-Pins** als Gitlinks (u-boot `4091ea68c06`, TF-A `dfa9fab44`, sunxi-tools `269dfa2`). `mainline/local/` (497 MB Vendor-Material, bei cstenger gitignored) ausgeschlossen.
- ☑ P3.5 Umzüge: `installer/` (5 Skripte + `h713-extract` + `README-h713-extract.md` + `metadata-leer-16m.ext4.gz`; die FEL-Forschung `s44-*` bleibt in `analyse/`), `rootfs/` (ohne `out*/`, ohne persönliche `wifi.env`; die **öffentliche Vorgabe** `overlay/etc/h713/wifi.env` wird geprüft — `.gitignore` dort war `wifi.env` und hätte sie mit ausgeschlossen, jetzt `/wifi.env`), `userspace/` (ohne gebaute Binaries, ohne `hy310-*`-Symlinks und `hy310-tv.vor-audio-*`), `tools/`, `release/`, `analyse/{boot,beamer-cam}`, `doku/` (173 Dateien inkl. `nachtlog/`), `README.md`. `.gitignore` an der Wurzel (Bauausgaben, Abzüge, Abbilder, `re/`, persönliche Dateien).
- ☑ P3.6 **Sperr-Scan auf dem Ergebnis: 786 Dateien, 37 Referenz-Hashes, keine Funde.** Dabei zwei Scanner-Korrekturen: die zwei Bauskripte unter `mainline/build/` sind erlaubt (`ERLAUBT`), und die PuTTY-Kennung steht geteilt im Quelltext, damit der Scanner sich nicht selbst findet; `__pycache__/` wird übersprungen.
- ☑ P3.7 **`build-all --dry-run` aus dem Klon** läuft (Wurzel `repo-neu`, Container erkannt, Layout `installer/`+`rootfs/`).
- ☑ P3.8 Submodule im Klon aus den **lokalen Checkouts** gefüllt (Schritt 12a, `submodule.<pfad>.url` → Arbeitsbaum, `protocol.file.allow=always`) — der Platzhalter, bis P7 den U-Boot-Fork erreichbar macht; alle drei Pins stehen (`git submodule status`). **Nicht** rekursiv: TF-A hat selbst vier Submodule (`contrib/{libeventlog,libtl,libtpm,mbed-tls}`), die im Klon leer bleiben. Geprüft (12.09.): für `PLAT=sun50i_h713` spielt das keine Rolle — beide Bauten übersetzen dieselben **119** Objekte, das Makefile greift nur für `MBEDTLS_DIR` darauf zu (bei uns ungenutzt). Wer messbaren Start oder TPM will, braucht `--recursive`.
- ☑ P3.9 **Voller Bau aus dem Klon** (12.09.; dreimal gelaufen, zuletzt 19:40–19:58, **18 min 34 s**): elf Schritte aus `repo-neu/` heraus, **Selbsttest mit Vendor-Dateien ALLES GRÜN**, Abbild `h713-hy310-v0.0-beta` (drei Teile, 1159 MiB) + Stempel (`repo repo-neu: 4bcfb93`, bl31 sauber gebaut). Logs `analyse/release/arbeit/logs/build-all-klon-20260912.txt` (erster Lauf, Schritte 1–9, ~23 min mit Tarball-Download), `…-teil2.txt` und `…-klon2-20260912.txt` (der grüne Lauf). **Ein Fehler dabei:** Schritt 10 brach ab, weil `installer/tmp/` im Klon vom Container als root angelegt worden war und der Selbsttest dort seine Probe ablegen will → `build-all` legt `tmp/` jetzt vorher als Nutzer an. Zwei Kleinigkeiten: der Stempel schrieb „mainline: …", obwohl er im Repo-Layout das ganze Repo meint (jetzt „repo repo-neu: …"), und das Skelett legt den Kernel-Tarball, das aic8800-Archiv und das Keyring-`.deb` aus dem Arbeitsbaum in den Cache des Klons (Schritt 12b) — sonst kostet jeder `--neu`-Lauf 147 MB Download.
  **Der Vergleich Klon gegen Arbeitsbaum hat einen echten Fehler aufgedeckt** (12.09., 19:40). Die Bausteine waren nicht gleich; das Nachgehen ergab drei verschiedene Ursachen:
  1. **`bl31.bin`: 49 260 Byte im Arbeitsbaum, 45 164 im Klon — ein alter Stand, kein Zeitstempel.** Im Arbeitsbaum lag ein TF-A-Bau vom **10.09. 19:52** mit **eingeschalteten Zusicherungen** (`ASSERT: %s:%u` steckt in `libc/assert.o`, jedes Objekt größer). `build.sh bl31` ruft nur `make`; make sah alles aktuell und hat nie neu übersetzt — seit dem 10.09. hat **jeder** Lauf dieses alte bl31 nur weiterkopiert. Es steckt damit in v0.8, v0.9 und v0.10, also auch in dem, was am Gerät läuft. Nach `rm -rf external/arm-trusted-firmware/build` liefert derselbe Baum **45 164** Byte, und der unterscheidet sich vom Klon-bl31 in **genau vier Byte**: `Built : 17:31:53, Sep 12 2026` gegen `17:25:29` — die Uhrzeit des Bauens. **Behoben:** `build-all` löscht die Bauverzeichnisse von TF-A und beiden U-Boot-Bauten, bevor es sie baut (Schritte 1, 2, 2b). Belegkopie des alten Standes: `analyse/release/arbeit/logs/bl31-1009-49260.bin`.
  2. **SPL und U-Boot proper** unterschieden sich in 4 096 Byte Größe — genau die Differenz des eingebetteten bl31 (U-Boot trägt bl31 in seinem FIT); dazu die eigene Baukennung `U-Boot 2026.07-rc5-g4091ea68c06f (Sep 12 2026 - 12:51:07 +0000)` gegen `17:25:37`.
  3. **`h713-kernel.fit`** trägt eine `timestamp`-Eigenschaft (mkimage), im Arbeitsbaum `1789217498` = 12.09. 12:51:38Z. **`aic8800_fdrv.ko`** trägt drei Kopfdateipfade des Kernelbaums (`/work/mainline/build/linux-…/include/net/cfg80211.h` gegen `/work/repo-neu/…`) — `WARN`/`BUG` legen `__FILE__` ab; `aic8800_bsp.ko` hat keine solchen Zeichenketten und ist deshalb byteidentisch.

  **Arbeitsbaum ebenfalls sauber nachgezogen** (Marco, 12.09., 20:05): `build-all --version v0.11 --vendor …` → **ALLES GRÜN in 9 min 32 s**, bl31 jetzt auch dort 45 164 Byte. Ausgabe `analyse/release/arbeit/r0-fel/out/h713-hy310-v0.11.*`, Log `…/logs/build-all-arbeitsbaum-v011-20260912.txt`. Damit ist v0.10 der letzte Stand mit dem alten bl31; **v0.11 (Arbeitsbaum) und v0.0-beta (Klon) sind die ersten sauberen**. Nebenbefund: `sunxi-fel` ist zwischen beiden Bäumen **byteidentisch** (kein Zeitstempel im Binärprogramm), `aic8800_bsp.ko` ebenfalls, `h713-tv` hängt nur am Sysroot-Pfad.

  **Für das Gerät heißt das:** die nächste Auslieferung bringt ein anderes bl31 als das, was heute auf dem Gerät liegt (Zusicherungen aus, EL3 leiser). Das ist der beabsichtigte Auslieferungsstand — aber es ist eine Änderung an der Bootkette und gehört in die Generalprobe P6.
  **Was bleibt:** gleiche Quellen liefern weiterhin verschiedene Bytes, weil Bauzeit und Baupfad eingebettet werden. Echte Bitgleichheit wäre `KBUILD_BUILD_TIMESTAMP`, `-ffile-prefix-map` und ein festes `mkimage -t`; eigenes Todo (B), nicht v0.1.
- ☑ P3.11 Zwei Fallen beim Wiederholen, beide notiert: (a) einen laufenden `build-all` **nicht** mit `pkill` abschießen — der halb gebaute Kernelbaum bleibt mit `.cmd`-Dateien zurück, die Objekte behaupten, die es nicht gibt (`llvm-strip: 'kaslr.o': No such file or directory`); Heilung ist `rm -rf mainline/build/linux-<digest>` im Klon, verloren geht nichts (Baum = Tarball + Serie). (b) `--neu` musste nach einem Bau im Klon auf `podman unshare rm -rf` ausweichen, weil Teile dem Container-root gehören.
- ☑ P3.10 **Sichtprüfung Marco 12.09., 20:05: „sieht soweit okay aus“.** `git -C repo-neu log --first-parent --oneline legacy..main` (9 Commits), `git ls-files` (790 Dateien; mainline 417, doku 173, userspace 33, rootfs 31, tools 18, installer 8), `.git` 16 MB ohne Submodule, keine Datei über 1 MB. **P3 abgeschlossen.**
- Befund für P7: die Commit-Texte sind Englisch (Marco 12.09.: Werkzeuge/Repo Englisch, `doku/` Deutsch). Der Subtree bringt cstengers 270 Commits als zweiten Elternstrang mit — `git log --first-parent` zeigt nur unsere.
- Aus `legacy` ist **keine Datei** an gleichem Pfad mit gleichem Inhalt übernommen (nur `README.md`, `.gitignore`, `tools/README.md`, `userspace/README.md` existieren an beiden Stellen, alle neu geschrieben). Was aus dem alten Baum sachlich weiterlebt, steht in `doku/116` §3 und wird in P5 (PROVENANCE) benannt.

### P5 Doku Englisch (12.09., 20:20–21:50) — Plan und Befunde: [`117`](117-plan-p5-doku.md)
- ☑ **33 Seiten**, ~2600 Zeilen: sechs an der Wurzel (README, STATUS, FLASHING, BUILDING, PROVENANCE, ROADMAP, RELEASES), 13 Teilsysteme, 9 Werkzeuge, 4 U-Boot, dazu `hardware`, `architecture`, `known-issues`, `dead-ends`, `kernel-patches`, `services`, `build-container`, `usage/first-hour`.
- ☑ Neun Agenten schrieben Entwürfe (nie direkt nach `docs/`), ich habe jeden gegen die Quelle gelesen. **Drei Prüfläufe** danach fanden 13 + 8 + ~12 Punkte; alles Substanzielle ist behoben, die Liste steht in `117`.
- ☑ Dabei ein **echter Fund am Gerät**, nicht nur in der Doku: der Notaus bei Lüfterstillstand war seit `0141` ausgebaut. Marco: wieder scharf schalten → Patch **`0159`**, Abbild **v0.12 ALLES GRÜN**. Serie jetzt 133 Patches in 14 Abschnitten.
- ☑ Skelett neu gebaut, **Sperr-Scan ohne Funde** (830 Dateien), 99 interne Verweise, keiner tot.
- ☐ Marco liest README und FLASHING gegen. Bilder trägt er nach; das Einspielvideo entsteht bei P6 aus dem Terminalmitschnitt.

### P6 Generalprobe (12.09., 21:30–23:20) — Protokoll: `analyse/boot/p6-abnahme-20260912.txt`
- ☑ P6.1 Gerät auf **Stock-Android** zurückgespielt (2423 MiB in 6 min, rc=0), Sicherung `hy310-sicherung-20260912-vor-stock`. Der Installer erkannte unser Layout und zog vorher den kleinen Abzug.
- ☑ P6.2 **Bau aus dem Klon**: `repo-neu` @ `b6e35f4`, „0 lokale Änderungen", `--version v0.5-beta` **ohne** `--vendor` — genau der Nutzerweg. 21 min 34 s.
- ☑ P6.3 **Einspielen aus dem Klon**: FEL → ums → kleiner Abzug → 43 Platzhalter + Schlüssel → schreiben → zurückvergleichen. 3 min, Secure Storage byteweise unverändert.
- ☑ P6.4 Abnahme: erster Start mit dem **sauberen bl31**, Bild 1920×1080p, Ton ohne HDMI, Kamera hell (Y = 88,7), Fokusmotor, WLAN als AP (−50 dBm, 5,7 MB/s) **und** als Station gegen ein echtes Netz.
- ☑ P6.5 **Notaus ausgelöst** (PB5 aus → Abschaltung), sauberes Aushängen beim nächsten Start bewiesen. Beleg `p6-notaus-luefter-20260912.txt`.
- ☑ P6.6 **Env-Übernahme bewiesen** — dreifach: der Installer las `h713_gate=0, h713_boot=net`, mischte sie ins Abbild (Abbild bringt 1/emmc), die eMMC trug sie danach mit gültiger CRC, und das Gerät startete ohne Tastendruck.
- ☑/☐ P6.7 **Gate**: funktioniert (den ganzen Abend wartete das Gerät nach jedem Kaltstart auf die Taste). Die 20er-Reihe mit gemessenem Ruhefenster ist **nicht** gelaufen — mein Skript konnte „kam von allein" und „Marco hat gedrückt" nicht trennen. Nachzuholen mit vereinbartem 30-Sekunden-Fenster.
- ☑ P6.8 Vier Mängel gefunden und dokumentiert: `ctl replug` nach dem Einstecken; `/dev/video3` statt `video1` (Doku korrigiert, „never assume a number"); `ping`/`curl`/`wget`/`nc` fehlen im Abbild (Todo); ssh-Hostschlüssel ändert sich nach jeder Neuinstallation (gehört in FLASHING).
- ☐ P6.9 Terminalmitschnitt als Grundlage fürs Einspielvideo — **versäumt**: ich habe die Sitzung nicht mitgeschnitten. Beim nächsten vollen Durchlauf nachholen.

### P7 vorbereitet (12.09. nachts) — der Push selbst wartet auf Marcos Wort
- ☑ P7.0 **Arbeitsadresse aus allem entfernt.** Marcos Arbeitsadresse stand in vier Kernel-Patches **und in fünf Commits des U-Boot-Forks**. Die Patches per `sed`, der Fork per `git filter-branch --env-filter` über `8fe568cdfc4..HEAD` — 33 Commits neu geschrieben, **Tree-Hash unverändert** (nur Metadaten), neuer Kopf **`4091ea68c06`** statt `df35eded879`. Alle Verweise in Skripten und Doku nachgezogen. Das ging nur, **weil der Fork noch nie gepusht war**.
- ☑ P7.1 Entscheidung Standardzweig U-Boot-Fork: **`h713-hy310` wird Standard, kein Merge nach `master`.** Grund: `master` bleibt die saubere Upstream-Spiegelung, sonst wird der nächste Rebase zur Fummelei und die Trennlinie „von uns / von Denx" verschwindet. Bei `sunxi-tools` (`h713`) und TF-A (`sun50i-h713`) ist es schon so.
- ☑ P7.2 **Lizenzen** (Marco: „das sinnvollste für die community, aber mein Name muss dranbleiben"): Code **GPL-2.0** (`LICENSE`, für die Patches zwingend geerbt, für unsere Werkzeuge bewusst gleich), Doku **CC BY-SA 4.0** (`LICENSE.docs`). Die NC-Klausel wurde erwogen und verworfen — sie hält genau die Leute fern, die zurückgeben würden, und schützt den Namen nicht besser als die Namensnennung, die beide Lizenzen erzwingen. Urheber: **well0nez**, cstengers Anteil in `PROVENANCE.md` benannt.
- ☐ P7.3 **Sichtbarkeit**: `well0nez/arm-trusted-firmware` und `well0nez/sunxi-tools` sind **privat** und müssen zeitgleich mit dem Push öffentlich werden — sonst kann ein Fremder die Bootkette nicht bauen (relative Submodul-URLs).
- ☐ P7.4 Push: `legacy` + Tag `legacy-arm32-2026-08` + `main` nach `well0nez/allwinner-h713-linux` (kein Force nötig, `main` sitzt auf dem alten Stand auf), danach **Standardzweig auf `main`**. U-Boot-Fork `h713-hy310` pushen, Standardzweig setzen.
- ☐ P7.5 Vor dem Push: **neu bauen**, damit die eingebaute U-Boot-Kennung wieder zum Commit passt (`-g4091ea68c06`), Sperr-Scan, Tag `v0.5-beta`, Assets (drei Abbildteile, Tabelle, Installer).



## 5. Der Installer — was am Nutzerweg noch fehlt

- **Bedienung vereinfachen** (Marco: „das Komplizierteste"): heute sieben Parameter. Ziel: `hy310-install` ohne
  Argumente findet `sunxi-fel`, Installer-U-Boot, Abbild und Extraktor **neben sich** (Release-Zip), fragt nur den
  SSH-Schlüssel und den Abzug ab, und sagt vor jedem Schritt, was passiert. Die Parameter bleiben für Sonderfälle.
- **Beta-Warnung** in README, Release-Text und Installer-Ausgabe ([`110`](110-plan-installationsweg.md) §9).
- **Pflichtabzug überspringbar machen** (Marco, 12.09. beim Stock-Flash): der kleine Abzug holt geräteeigene Bereiche — Secure Storage, `private`, `Reserve0`. Die **ändern sich durch unsere Abbilder nicht**: ob v0.9 oder v0.12 draufliegt, ist für ihren Inhalt egal. Wer einen Abzug dieses Geräts hat, braucht keinen zweiten. Kriterium ist also nicht das Layout, sondern: liegt ein Manifest zu **diesem** Gerät vor? Dann überspringen und sagen, welcher Abzug gilt; sonst ziehen. Ein `--abzug erneut` bleibt für den einen Fall, in dem sich doch etwas geändert haben kann — wenn zwischendurch Stock-Android lief und in `private`/`Reserve0` geschrieben hat.
- **Gate ansagen**: Installer-Ausgabe und LIESMICH des Abbilds sollen am Ende sagen, dass das Gerät nach dem Einspielen auf die Ein-Taste wartet (heute steht `h713_gate=1` nur in der Prüfzeile des Abbild-Bauers).
- **Layout-Unterscheidung Stock/unser** ist drin (12.09.); die Env-Übernahme am Gerät beweisen (P6).
- **GPT-Vergleich** `sunxi_gpt.fex` gegen `sys_partition.fex` ([`60`](60-offen.md) Punkt 12).
- `--restore-stock` ist Marcos Weg zurück — vor P6 einmal im Trockenlauf ansehen.
- **Namen im Release-Zip** (seit P3): `build-all` legt `out/u-boot-installer.bin` und `out/sunxi-fel` ab; die vom Abbild-Bauer erzeugte LIESMICH sagt noch `--uboot u-boot-sunxi-with-spl.bin`. Mit der Bedienungsvereinfachung angleichen (Vorschlag: `hy310-install` sucht `u-boot-installer.bin` neben sich).

## 6. Nach dem Release — damit es nicht wieder nur im Gespräch existiert

| Thema | Was gemeint ist |
|---|---|
| **Wissensdatenbank** | Das deutsche `doku/` (115 Dateien, nachtlog) **und `analyse/`** bedacht destillieren — neu kategorisieren, zusammenführen, umschreiben; je Teilsystem: was gilt, was widerlegt ist, wo der Beleg liegt. Nicht per grep, nicht per Stichwort; eine Datenbank, die wir selbst wieder benutzen. Englisch. `analyse/` wird dafür nicht vorab ausgedünnt |
| **Deutsch in Code** | Kommentare, Meldungen, Variablennamen in Modulen und Werkzeugen (`h713-tv`, `h713-focus`, `h713-wifi`, Patches ab `0146`) → Englisch. Ein Durchgang, kein Nebenbei |
| **Testskripte** | Auswahl: was ohne unseren Tisch läuft (`h713-wifi-check`, `mkimage-selbsttest`, Motor-Attrappe, `kaltstart-serie`), was Messaufbau braucht (`analyse/hdmi-seq`, elog, Registervergleiche), was RE ist. Später ausklamüsern |
| **Installer-Bedienung** | §5, erster Punkt |
| **Windows** | nach Rückmeldungen; `sunxi-fel` bauen, wenn jemand testet |
| **ge2d / Desktop** | der Stock-Display-Stack ([`60`](60-offen.md) §Altbestand), Helligkeitsregler, und die Frage, ob ein Desktop auf dem Gerät überhaupt Ziel ist |
| **Cedrus / GPU im großen Stil** | Panfrost und Cedrus sind gebaut, aber nie systematisch geprüft (der KASAN-Fall in `kasan.config` steht noch); Testmatrix Decoder × Auflösung × Ausgabe |
| **Verwaltungsoberfläche** | Ein Weg für Nutzer, WLAN (`wifi.env`), Presets, Startmodus, Updates zu setzen, ohne SSH — Web/GUI auf dem Gerät. Zuschnitt offen |

Diese Zeilen stehen ab jetzt auch in [`61-todo.md`](61-todo.md) Abschnitt B/C.

## 7. Regeln, die für diesen Plan gelten

- **Kein Push, bevor der Sperr-Scan läuft und ein Mensch den Export angesehen hat.** Auch wenn wir „erstmal nichts
  publishen": was einmal im Netz war, bleibt es.
- Der Bau, der veröffentlicht wird, ist der aus `build-all` vom frischen Klon — nicht der aus `/opt/Projekte/h713`.
- Was am Gerät abgenommen wird, ist das Abbild aus P6, nicht v0.9.
- Agentenregeln unverändert ([`115`](115-handoff-20260912.md) §7).

### Wo P7 stehengeblieben ist (12.09., 23:50 — Rechner wird abgeschaltet)

**Nichts ist veröffentlicht.** Kein Push, kein Tag, keine Sichtbarkeit geändert. Der Release-Bau lief
seit 23:33 und stand beim Kernel; ich habe ihn sauber beendet und den halb gebauten Baum gelöscht
(`repo-neu/mainline/build/linux-6.18.38-286ad979…`), damit der nächste Lauf nicht auf `.cmd`-Dateien
ohne Objekte trifft — die Falle von heute Nachmittag.

**Was fertig vorbereitet ist:**
- `repo-neu` frisch erzeugt (rc=0), 843 Dateien, Sperr-Scan leer, alle drei Submodule aufgelöst
- Arbeitsadresse aus Patches **und** Fork-Historie entfernt, U-Boot-Kopf `4091ea68c062…dad`
- `LICENSE` (GPL-2.0) und `LICENSE.docs` (CC BY-SA 4.0) liegen und werden mit exportiert
- Release-Notes geschrieben: `analyse/release/arbeit/logs/` … (Entwurf im Sitzungs-Scratchpad, bei
  Bedarf neu schreiben — Inhalt: was drin ist, Vollabzug-Warnung, was läuft/fehlt, Credits)
- `gh` ist als well0nez angemeldet; `repo-neu` hat **absichtlich noch kein Remote**

**Die vier Schritte, die noch fehlen (Marcos Go liegt vor):**
1. `release/build-all.sh --version v0.5-beta --vendor …/out-hy310-20260912` aus `repo-neu` — voller
   Kernelbau, ~20 min, danach im Stempel `-g4091ea68c06` prüfen
2. `well0nez/arm-trusted-firmware` und `well0nez/sunxi-tools` **öffentlich** schalten
3. U-Boot-Fork: `git push fork h713-hy310`, Standardzweig darauf (kein Merge nach `master`)
4. Hauptrepo: `legacy` + Tag `legacy-arm32-2026-08` + `main` pushen, Standardzweig `main`,
   dann Release `v0.5-beta` mit den drei Abbildteilen, Tabelle, sha256 und `.BUILD.txt`
   (im Stempel vorher `repo repo-neu:` → `repo:` korrigieren, falls der Bau noch die alte Zeile schreibt)

### P7, 13.09. nachts — Release-Abbild gebaut und am Gerät gestartet
- ☑ Skelett neu erzeugt (843 Dateien, Sperr-Scan leer, Arbeitsadresse nirgends), dann **Release-Bau aus dem
  Klon**: 20 min 30 s, **Selbsttest mit Vendor-Dateien ALLES GRÜN**, Stempel `repo: 150d70c (0 lokale
  Änderungen)`, U-Boot `-g4091ea68c062`, bl31 45 164 Byte. Assets gesichert nach `analyse/release/arbeit/p7-assets/`.
- ☑ **Genau dieses Abbild** über FEL (Reset-Taste, fremdes Netz — kein Heimnetz nötig) eingespielt, rc=0 in
  184 s, Secure Storage unverändert, **mit Aufnahme** (`analyse/release/arbeit/p7-aufnahme/`, 178 s, abspielbar
  mit `scriptreplay`).
- ☑ Nach Stromzyklus + Taste über den **eigenen AP des Beamers** geprüft (Rechner-WLAN mit `never-default`,
  Kabelnetz unberührt): Kernel vom 12.09. 23:35 UTC, U-Boot auf der eMMC `2026.07-rc5-g4091ea68c062`,
  `h713_gate=1`, `h713_boot=emmc`, `fan_stall_shutdown=Y`, `h713-tv` läuft. **Das veröffentlichte Abbild ist
  am Gerät gestartet.**
- ☑ Nachtrag-Commits auf `150d70c` obenauf (`3863ebe` Doku/Transkript, `48f2108` FLASHING-Dateiablage), damit
  der Commit aus dem Stempel in der veröffentlichten Historie steht.
- ☑ **Veröffentlicht, 13.09. ~02:40:** TF-A und sunxi-tools öffentlich; U-Boot-Fork `h713-hy310` gepusht und
  Standard; Hauptrepo `legacy`, Tag `legacy-arm32-2026-08`, `main` gepusht, Standard `main` (`master` bleibt);
  alle drei Submodul-Pins von außen als Zweigköpfe erreichbar. **Release `v0.5-beta`** (Vorabversion) auf Tag
  → `150d70c`: https://github.com/well0nez/allwinner-h713-linux/releases/tag/v0.5-beta
- ☑ **Beinahe-Panne beim Upload, und was daraus wurde:** Marco erschrak („da wären doch meine Keys drin") —
  ich habe das Release sofort auf Entwurf zurückgestellt und die hochgeladenen Dateien geprüft: Secure Storage
  liegt im Loch (in keiner Datei), einziger `hdcpkey`-Treffer ist der Quelltext von `h713-hdcp-key`, SSH-Schlüssel
  0 Treffer, **0 von 34** Vendor-Dateien im Abbild. Dabei zwei echte Mängel gefunden und behoben:
  (1) **1,15 GB roh, 94 % Nullen** → Abbilder als `.zst` (56 MiB), Rundreise gegen die Prüfsummen belegt;
  (2) **ein Nutzer hätte nicht installieren können** — `u-boot-installer.bin` und das Falltür-`sunxi-fel` fehlten
  im Release, und nirgends stand, wohin die Dateien gehören. Beide jetzt als Assets, FLASHING hat einen Abschnitt
  „Getting the files together" mit Ordner und genauem Befehl. Hochgeladene `.zst` per Download gegengeprüft.
- Lehre: ein Release-Artefakt zuerst **aus Sicht eines Fremden** durchgehen, der nur die Release-Seite sieht —
  nicht aus Sicht dessen, der den Baum kennt.

### P8 — an cstenger (13.09.)
- ☑ **Issue statt PRs** — cstenger ist seit dem 22.08. still, bei ihm liegen drei Issues und zwei U-Boot-PRs von
  Marco ohne Reaktion. PRs hätten einen Fork, übersetzte Patchköpfe und Zurechtschneiden auf seinen Stand
  gekostet, für etwas, das liegen bleibt. Ein Issue macht die Fehler für Nutzer seines Baums auffindbar:
  https://github.com/cstenger/allwinner-h713-mainline/issues/4 — pinctrl-IRQ-Bänke (`0143`/`0144`),
  cpu_comm-Knoten (`0024a`), U-Boot-Env-Offset ≥ 2 GiB (`uboot-h713/0022`), dazu `0024b`, `0078a`,
  `build.sh`-Kommentarzeilen. Angebot, sie auf Wunsch als PRs aufzuteilen. Text: `analyse/release/arbeit/p8-issue-cstenger.md`.
