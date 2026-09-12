# H713-Projekt — Status

**Stand 11.09.2026, abends.** Einstiegsseite: was läuft, wie man es bedient, wo was liegt, was offen ist.
Der letzte Übergabestand steht in [`111-handoff-20260910-abend.md`](111-handoff-20260910-abend.md); was seitdem
passiert ist, steht hier im Kopf und in [`60-offen.md`](60-offen.md). **Wer neu einsteigt, liest 111 und dann 60.**

**Neu am 11.09. — der ganze Nutzerweg ist einmal durchlaufen.** Stock-Android mit unserem eigenen Installer
zurückgespielt (vier Anläufe: `metadata` braucht ein fertiges ext4, `super.fex` ist sparse, alles ohne Quelldatei
muss genullt werden), dann Abzug → Extraktion → unser Abbild geschrieben → Gerät bootet, Netz, Bild, Ton. Dabei
gefunden und behoben: `bestaetigen()` gab immer Nein zurück (jeder Schreibpfad des Installers war unbenutzbar),
Automounter-Konflikte, `--device` erzwang den FEL-Zweig, veralteter U-Boot im Abbild (kein `eth0`),
`h713_mips_dev=1:2` statt `1#hy310-boot` (MIPS-Firmware nie gefunden). U-Boot-Patches `0026`–`0032`.
Dazu: **FEL aus Software** — `run fel` am U-Boot-Prompt und `h713-fel` unter Linux ([`S48`](nachtlog/S48-fel-aus-uboot.md));
**HDCP 2.2 kommt vom Gerät** (`h713-hdcp-key.service` liest `hdcpkeyV22` aus `hy310-keys`, nichts wird ausgeliefert);
**Bildwerte zur Laufzeit** und `ctl save` (Plan [`113`](113-plan-pq-laufzeit-und-speichern.md), am Gerät geprüft);
**Werkzeuge heißen `h713-*`**; Installer erkennt das Gerät und nimmt `--authorized-key`. **Kamera läuft**
(`uvcvideo` fehlte schlicht, [`analyse/beamer-cam/`](../analyse/beamer-cam/README.md)). **Altbestand abgeglichen:**
vier Lücken — board-mgr gebaut (Patches `0141`/`0142`, drei Fehler im Vendor-Knoten, Stock-Kernel gegengelesen), Crypto
Engine entschieden ([`114`](114-plan-crypto-engine.md): aus für Krypto, gebraucht nur für den RSSK), tvtop/nsi und
AV1 auf der Liste. **Am Gerät läuft weiter der Kernel vom 10.09.** — die Bäume `61d37af9` (board-mgr) und
`e88af5af` (+ Kamera) sind gebaut, aber nicht eingespielt; das ist ein Flash plus Kaltstart.

**Fertig und am Gerät abgenommen:** HDMI-Bildpfad; **HDMI-Audio** (Plan [`101`](101-plan-audio-treiber.md), Serie 110, ein Regler
`h713-tv ctl volume`, Lippensync ok); **Einschalt-Gate** (Plan [`103`](103-plan-einschaltgate.md), Serie 112/`GUT-bad2f16b`: Netz an →
Bereitschaft 4 W rote LED, Taste → Start, `poweroff` → Bereitschaft; am Dev-Gerät per `h713_gate=0` **aus**).

**Neu am 10.09.: der Beamer bootet vollständig von sich selbst.** Kein Netz, kein Host, kein Android mehr.
Layout v3 liegt auf der eMMC ([`109`](109-plan-layout-v3.md)), das Rootfs ist 228 MiB groß ([`107`](107-plan-rootfs.md)),
**20 von 20 Kaltstarts** sauber. Dazu: **FEL-Boot funktioniert** ([`S44`](nachtlog/S44-fel-boot.md)) und U-Boot kann die
eMMC als **USB-Laufwerk** am PC freigeben (7,6 MB/s lesen, 7,7 MB/s schreiben) — damit braucht der Nutzerweg weder
Linux auf dem Gerät noch ein Firmware-Image aus dem Netz ([`110`](110-plan-installationsweg.md)).

**In Arbeit: Release** als Entwickler-Vorschau v0.1 (Plan [`105`](105-plan-release.md)) — Repo `well0nez/allwinner-h713-linux`.
R1 (Boot vom Gerät) und R2 (Extraktion) sind fertig. Der **PC-Installer** `analyse/release/arbeit/r0-fel/hy310-install.py`
läuft unter Linux und Windows: Abzug (klein 49 MiB / voll 7,3 GB), Abbild schreiben, Stock zurückspielen mit byteidentisch
nachgebauter Hersteller-GPT. Eine kritische Gegenprüfung ([`S46`](nachtlog/S46-kritische-pruefung.md)) hat 5 kritische und
13 ernste Befunde gefunden; acht sind behoben. **Das Abbild ist gebaut** (`hy310-mkimage`, [`S47`](nachtlog/S47-abbild-bauer.md)):
1,22 GB, 30 Platzhalter für die Vendor-Teile, geprüft. Es besteht aus **drei Dateien mit einer Lücke genau über dem
Secure Storage**, damit ihn auch ein `dd` von Hand nicht nullen kann. **Offen:** `sunxi-fel` als Windows-Programm,
Repo und README (`105` R3/R4), Windows-Pfad ungetestet.

**Vor jeder Auslieferung merken:** Das ist eine **Beta**. Wer sie einspielt, braucht **vorher** einen Vollabzug oder
ein passendes Firmware-Image, sonst ist ein Fehlschlag nicht heilbar ([`110`](110-plan-installationsweg.md) §9).

**Geparkt/Folge:** Plan [`102`](102-plan-audio-mischung.md) Gerätetöne mit HDMI mischen; Plan [`104`](104-plan-standby-stufe2.md) ARISC-Deep-Sleep
(<1 W, IR/CEC-Wecken), RE-Vorarbeit S39/S40 fertig.

Belege und Verlauf stehen in den verlinkten Dokumenten; diese Seite nennt nur Ergebnisse. Die Vorgängerfassung
(Schichtung von Kopfblöcken über einem Rumpf vom 07.09.) liegt als
[`nachtlog/STATUS-bis-20260908.md`](nachtlog/STATUS-bis-20260908.md).

## 1. Was läuft — der HDMI-Eingang als Teil des Systems

Der Beamer HY310 läuft mit Mainline-Linux 6.18.38 (arm64, Debian 13 per Netboot) und zeigt den HDMI-Eingang
**vollständig aus Kernel und Userspace**, ohne `/dev/mem`-Pokes, ohne Stock-Daemons:

| Baustein | Was er tut | Beleg |
|---|---|---|
| U-Boot (eigene Patches) | Boot-Chain, Display-Pfad, legt den SMM-Heap für die MIPS-Firmware an (`SetSource`-Absturz gelöst 07.09.) | [`30`](30-uboot-aenderungen.md), [`74`](74-setsource-ursache-nullzeiger.md) |
| `sun50i-h713-arisc` (`0091`) | lädt die ARISC-Firmware, fährt HPD/EDID am Port (17,65 s, kein Doorbell-Puls) | [`82`](82-arisc-treiber.md) |
| `cpu_comm` (In-Kernel-API, `0124`/`0125`) | RPC zur MIPS-Displayfirmware und Rückrufe von ihr; Slot-Leck behoben (vorher Hänger nach 19 Rückrufen) | [`83`](83-cpu-comm-api.md), [`nachtlog/S11`](nachtlog/S11-gruenstich-ursache-und-callback-slots.md) |
| `sun50i-h713-hdmirx` (`0094`…`0132`) | `/dev/video1`: Signal, Timings (`QUERY_DV_TIMINGS`, `SOURCE_CHANGE`), Bildregler als V4L2-Controls, Quellenwechsel, Freigabe der Capture nach jedem Descriptor-Neubau samt Farbwandler, Ring-Pitch aus INCAP | [`88`](88-v4l2-hdmirx.md), [`96`](96-anzeigekette.md) |
| `sun50i-h713-afbd` (`0093`, `0095`, `0107`, `0133`) | KMS `card1`: Plane 38 zeigt den Capture-Ring (`hdmi-ring`), Eigenschaft `aspect`, `GAMMA_LUT`/`CTM` am CRTC 36 | [`86`](86-video-plane-nv16.md), [`87`](87-gamma-ctm-kms.md) |
| fbcon (`0127`) | Cursor blinkt nach dem Rückschalten weiter | [`nachtlog/S12`](nachtlog/S12-hy310-tv-review.md) |
| **`h713-tv`** (`userspace/h713-tv`) | Template-Unit `h713-tv@video1` (udev, `BindsTo`): Bild auf die Plane, bei Signalverlust Konsole mit Cursor; sendet beim Start Preset und Gammakurve; Steuerkanal `h713-tv ctl …` | [README](../userspace/h713-tv/README.md), [`nachtlog/S12`](nachtlog/S12-hy310-tv-review.md), [`S13`](nachtlog/S13-restpunkte.md) |
| `h713-pq` (`userspace/h713-pq`) | rechnet Stock-PQ-Daten in RPC-Argumente und Gamma-LUTs (kein Daemon) | [README](../userspace/h713-pq/README.md), [`81`](81-pq-datenmodell.md) |

**Abgenommen am Gerät (08.09.):** 1920×1080, 1280×720, 1024×768, 1440×900, 1280×1024 (proportional mit
Balken), 1366×768 — jeweils 60 Hz, farbrichtig (BT.709, Ring-Chroma 128), über beliebig viele Wechsel; HDMI
aus/an; Kaltstart ohne Handgriff; Konsole mit blinkendem Cursor zurück; Bildmodus/Regler/Presets/Einpassung/
Gamma aus dem Userspace ([`99`](99-plan-restpunkte-20260908.md), [`nachtlog/S13`](nachtlog/S13-restpunkte.md)).

**Guter Stand am Gerät:** Kernel-Serie **112** (bis `0140`, gesichert `patches-snapshots/20260909-2130-serie112-gate/`),
Abbild `GUT-bad2f16b` (Audio + Einschalttaste + EINT-Fix `0140`), Module `mainline/build/modroot.GUT-bad2f16b`.
**Serie ist inzwischen bei `0142`** (board-mgr, gesichert `patches-snapshots/20260911-1837-nach-0142/`), Bäume
`61d37af9` und `e88af5af` (+ `uvcvideo`) gebaut, **am Gerät ungeprüft**; vorige gute Stände `GUT-d5fd82a7` (Serie 110, Audio), `GUT-a3097ce7`
(Serie 102) und `GUT-e2f6be7c` (Serie 98). **U-Boot am Gerät seit 09.09.:** Gate-U-Boot + BL31 (`tftp/uboot-proper.GUT-gate-v2-20260909.bin`,
`uboot-h713/0018`, TF-A `3b3fb35fa`); Env `h713_gate=1` → Netz an = Bereitschaft (rote LED), Taste = Start; `setenv h713_gate 0; saveenv`
schaltet zurück auf Direktstart.
`h713-tv` mit Audio-Automat md5 `63f844f9…` (Original vor Audio: `userspace/hy310-tv.vor-audio-20260908/`).
**Sicherung dieses Stands:** `/opt/Projekte/h713-backups/h713-entwicklungsstand-20260908-2245.tar.gz` (338 MB) + `h713-captures-weltneuheit-20260908-2245.tar.gz`
(21 MB) + `stand-20260908-2245-beilagen/` (Git-Stände, Gedächtnis, GUT-Module, Board-`/root`, Board-Dateien, MSP-Firmware); Umfang und
Wiederherstellung in `h713-backups/README.md`. `re/` (7,9 GB) ist weiterhin nur einmal vorhanden.
Ältere Abbilder: `tftp/alt/`, `mainline/build/modroot-alt/`.

## 2. Bedienen

Kurzfassung; die vollständige Befehlssammlung mit Bau- und Installationsweg steht in
[`50-befehle.md`](50-befehle.md), Abschnitt **Betrieb**.

| Was | Wie |
|---|---|
| Board | `ssh root@192.168.8.141` (Hostname `hy310`, Rootfs auf der eMMC; die Adresse vergibt der Router nach der MAC des USB-Adapters, nicht wir). Netz-Rückfall: NFS-Root `/srv/h713-rootfs` auf diesem Rechner, dort root-owned → vom Board aus installieren |
| FEL | Reset-Taste halten, Strom einstecken. Kein Gehäuse, kein Pad. `sunxi-fel version` prüft, `sunxi-fel uboot …` startet U-Boot flüchtig |
| eMMC am PC | FEL-U-Boot aus `hy310_installer_defconfig` laden → eMMC erscheint als `/dev/sda`. Herauskommen nur durch Stromabschalten |
| FEL ohne Taste | am U-Boot-Prompt `run fel`, oder unter Linux `h713-fel` → Gerät meldet sich in ~10 s als FEL (seit 11.09., [`S48`](nachtlog/S48-fel-aus-uboot.md)). **A-zu-A-Kabel muss stecken**, und am USB versorgt bootet das Gerät bei Stromabschaltung nicht neu |
| Zuspieler | `ssh user@192.168.8.162`, HDMI-2; Modus **immer mit `--rate 60`** (`analyse/hdmi-seq/wechsel.sh WxH NAME RATE`) |
| Kaltstart | **erst** `ss -ulnp \| grep ':69 '` (TFTP), dann `sonoff_ctl restart --host 192.168.8.179 --wait 5`; ssh nach 35–90 s |
| Zustand | `h713-tv ctl status`, `journalctl -u 'h713-tv@*' -f`, `cat /sys/kernel/debug/sun50i-h713-hdmirx/status` |
| Bild/Regler | `h713-tv ctl off\|auto\|list\|set REGLER WERT\|preset NAME\|aspect NAME\|resync\|help` |
| Foto (PC-Webcam) | `python3 analyse/hdmi-seq/wandcheck.py shot NAME` → `re/captures/weltneuheit/wand-aktuell/NAME.jpg` (ansehen!) |
| Foto (Beamer-Kamera) | `analyse/beamer-cam/camgrab.py /dev/video2 AUS.ppm` am Gerät; Knoten per `grep -l "HD camera" /sys/class/video4linux/*/name` ([README](../analyse/beamer-cam/README.md)) |
| Kaltstart-Steckdose | `192.168.8.179` ist die **Sonoff**, nicht der Beamer |
| UART | `/dev/ttyACM0` gehört Marco — nie öffnen |

## 3. Wo was liegt

```
/opt/Projekte/h713/
├── doku/               Dokumentation (diese Seite = Einstieg; nachtlog/ = Protokolle und Archiv)
├── mainline/           Kernel/U-Boot-Baum (cstenger) + patches/kernel/series (unsere Serie) + build/
├── userspace/          h713-tv (Dienst + ctl), h713-pq (PQ-Rechner)          → userspace/README.md
├── analyse/            Messwerkzeuge und Rohdaten je Thema                      → analyse/README.md
│   └── release/arbeit/ die Release-Werkzeuge: r0-fel/hy310-install.py (PC-Installer),
│                      r0-fel/hy310-mkimage.py (Abbild-Bauer) + r0-fel/out/ (das fertige Abbild),
│                      r2-extract/h713-extract (Blob-Extraktion), rootfs/ (Bau des Rootfs)
├── tools/              UART-, Disassembler- und Parser-Skripte                  → tools/README.md
├── tftp/               das Netboot-Abbild + die zwei guten Stände; alt/ = Ablage
├── patches-snapshots/  Sicherungen der Patch-Serie vor jeder Änderung
├── re/                 RE-Material (Stock-Firmware, IDA-Datenbanken, Captures, Fotos) — **nie öffentlich**
│   └── device-dumps/  Abzüge dieses Geräts, u. a. der Secure Storage (Modus 600) und die volle eMMC
├── legacy/             unser altes arm32-Repo — nur Referenz (alte Daemons hy310-hdmird/-pqd)
├── uboot-h713/         U-Boot-Änderungen als Patch
└── agenten/            abgegrenzte Nebenprojekte (Fokusmotor)
```

## 4. Stand der Pläne

| Plan | Stand |
|---|---|
| [`77`](77-plan-hdmi-integration.md) HDMI-Integrationsplan, Pakete A–J | **erledigt** (A–I am Gerät abgenommen; J-Pflichtliste in [`nachtlog/J-pflichtliste.md`](nachtlog/J-pflichtliste.md) abgearbeitet). Abweichung zum Plan: die Plane liest den Ring direkt (`hdmi-ring`) statt dma-buf-Import — funktional gleichwertig, im Treiber als „transitional" markiert |
| [`78`](78-nachtplan-hdmi-switch.md) / [`79`](79-nachtlog-20260907.md) Nachtplan + Nachtlog | erledigt / Protokoll |
| [`91`](91-plan-drei-punkte.md), [`92`](92-plan-de-scaler.md), [`93`](93-todo-scaler-und-720p.md) Umschalter, Scaler, 720p | erledigt ([`nachtlog/S1`–`S8`](nachtlog/)) |
| [`99`](99-plan-restpunkte-20260908.md) Restpunkte 08.09. | erledigt ([`nachtlog/S13`](nachtlog/S13-restpunkte.md)) |
| [`73`](73-plan-setsource-absturz.md), [`76`](76-plan-ch0-de.md) | historisch (gelöst 07.09.) |
| [`102`](102-plan-audio-mischung.md) Gerätetöne mit HDMI mischen | **TODO** (08.09. 21:50), nicht begonnen |
| [`103`](103-plan-einschaltgate.md) Einschalt-Gate | **abgenommen** (09.09.): Kaltstart → Bereitschaft (4 W, rote LED), Taste → Start, `poweroff`/Taste → Bereitschaft, `reboot` direkt; U-Boot **v5** (eMMC-Boot, Env-Offset-Fix `0022`, Artefakt-Umschalter `0023`) geflasht 10.09., GUT. Gate am Dev-Gerät **aktiv** (Marco, 11.09.; die frühere Angabe „aus“ war überholt) — nach jedem Stromzyklus braucht es die Einschalttaste |
| [`104`](104-plan-standby-stufe2.md) Standby Stufe 2 (ARISC-Deep-Sleep, IR/CEC) | **geparkt, niedrige Priorität** (Marco); RE-Vorarbeit S39/S40 fertig, Protokoll dekodiert. Nutzen: <1 W statt 4 W, Sofort-an. Nach dem Release |
| [`110`](110-plan-installationsweg.md) Installationsweg | **Plan steht, Installer und Abbild gebaut** (10.09.): FEL → U-Boot flüchtig → eMMC als USB-Laufwerk am PC → **Abzug (Pflicht, das Failsafe des Nutzers; Wahl klein 49 MiB / voll 7,3 GB)** → Extraktion daraus → Abbild schreiben → Strom aus/an. Kein Firmware-Image, kein Stick, kein Netz am Gerät. Einspielen und Abziehen sind dasselbe mit vertauschten Seiten. **Geräteerkennung ist da** (11.09., §8) und der ganze Weg ist einmal durchlaufen inkl. Rückweg auf Stock. Merken: das Abbild sind **drei** Dateien, und der Platzbedarf am PC ist rund 9,7 GB statt der dort genannten 8 GB |
| **FEL-Boot** ([`S44`](nachtlog/S44-fel-boot.md)) | **läuft** (10.09.): `sunxi-fel uboot` bringt das Gerät zum U-Boot-Prompt, kein Byte auf die eMMC. EL3-Falltür per `smc` statt RMR; `env_init()`-Hänger behoben. Das PC-Skript ist da (`hy310-install.py`); fehlt nur `sunxi-fel` als Windows-Programm |
| [`107`](107-plan-rootfs.md) Rootfs / [`108`](108-plan-vendordaten.md) Vendor-Daten + Layout v2 **108 umgesetzt, [`109`](109-plan-layout-v3.md) geplant, 107 offen** (10.09.): Layout v2 ist am Gerät (vier Partitionen, kein Android mehr, Anzeige-Firmware aus `mmc 1#hy310-boot`); **Layout v3 ist am Gerät, das Gerät bootet vollständig von sich selbst** (10.09.): SPL 16 → U-Boot 2048 → Umgebung 7 MiB → `hy310-boot` → `root=PARTLABEL=hy310-rootfs`. Sechs Partitionen, HDCP-Block als eigene geschützte Partition. Rootfs 228 MiB, Bild und Ton laufen. Kompletter Installerlauf über Netboot bestanden (`109` §12), `hy310-keys` auf 1 MiB erweitert, Secure Storage nachweislich unverändert. zram läuft (461,8 MiB), `net.ifnames=0` in der Vorgabe (`0025`). **20/20 Kaltstarts sauber** (`analyse/boot/r5-20-kaltstarts-20260910.txt`). **Gerät unter 192.168.8.141** (Router-Lease, Hostname `hy310`). Offen: Dump von `Reserve0`/`private` von einem fremden Gerät (`109` §9.1) |
| [`116`](116-plan-release-repo.md) Repo und Release v0.1 | **P1 ☑ P2 ☑ P3 ☑ P4 ☑** (U-Boot-Push bei P7) (12.09. abends): `release/repo-skelett.sh` baut das neue Repo als `repo-neu/` (legacy-Branch + Tag, `main` mit subtree von cstenger, Umzüge, `.gitignore`, Sperr-Scan leer, `--dry-run` aus dem Klon). **Voller Bau aus dem Klon: ALLES GRÜN** (Abbild `v0.0-beta`, 18 min). Danach P5 englische Doku, P6 Generalprobe, P7 Release, P8 PRs |
| [`105`](105-plan-release.md) Release (Entwickler-Vorschau v0.1) | **in Arbeit**: Repo `well0nez/allwinner-h713-linux`, Freimachen per FEL. **R0 fertig** (FEL-Boot + Laufwerksfreigabe + PC-Installer, ersetzt den Env-Patcher-Ansatz). **R1 fertig** (Layout v3 am Gerät, Rootfs 228 MiB, 20/20 Kaltstarts). **R2 fertig** (`h713-extract` 0.4 mit eigenem ext4-Leser, ohne `debugfs`, Profile HY310 + L018). **Abbild-Bauer fertig** (`hy310-mkimage`, S47). **Offen:** R3 Repo, R4 README + englische Funktionsmatrix, R6 PRs an cstenger, `sunxi-fel` für Windows |
| [`113`](113-plan-pq-laufzeit-und-speichern.md) Bildwerte zur Laufzeit + Umbenennung | **beide Pakete umgesetzt und am Gerät geprüft** (11.09.): `h713-tv` rechnet Presets und Gamma beim Start aus `/etc/h713/tvconfig` (acht statt sechs Presets), `ctl save` merkt Nutzerwerte über den Neustart, Werkzeuge heißen `h713-*`. Start dauert dafür 400 ms länger. Ursprünglicher Plan: A = Presets und Gamma aus `/etc/h713/tvconfig` statt einkompiliert, Nutzerwerte über `ctl save` gemerkt, drei Schichten mit klarer Herkunft. B = Werkzeuge auf `h713-*`, Abbild und Bauer bleiben gerätespezifisch, Partitionsnamen bleiben empfohlen |
| [`112`](112-plan-hdcp14-crypto-engine.md) HDCP 1.4 über die Crypto Engine | **zurückgestellt** (11.09.): Weg per RE geklärt ([`S49`](nachtlog/S49-hdcp14-schluesselpfad.md)), Auftrag vollständig formuliert, nach dem Release. HDCP 2.2 läuft seit 11.09. vom Gerät (`h713-hdcp-key.service`) |
| [`114`](114-plan-crypto-engine.md) Crypto Engine | **Messlauf bestanden** (11.09., `0148`–`0150`): Das Messmodul hat am Gerät einen Task im **Vendor-Deskriptorformat** abgesetzt — AES-128-ECB, Key-Select 0, Ziel DRAM, gegen den FIPS-197-Vektor. `ERGEBNIS: bestanden … ESR sauber, KAT stimmt (65 µs)`. Damit ist **S49s Rekonstruktion aus OP-TEE am Silizium bestätigt** und cstengers Sackgasse als reines Deskriptorformat-Problem belegt. `sun8i-ce` bleibt aus. Offen: ob NS den RSSK (Key-Select 3) darf und ob CE_S sichtbar ist — beides bewusst nicht angefasst |
| **board-mgr** (`0141`–`0147`, `0152`) | **am Gerät abgenommen** (11.09.): Tacho per GPIO-Interrupt, **4860 RPM gemessen und bewiesen** (PB5 aus → 0 RPM → wieder an → 4770). Der Aufhänger beim ersten eMMC-Boot lag nicht am board-mgr, sondern in der pinctrl (`0143`/`0144`, siehe unten). **Temperatur: dieses Gerät hat keinen NTC** — der Hersteller sagt `ntc_num = 0`, unser Treiber hat das übergangen und aus einem offenen ADC-Eingang 0/60/71 °C erfunden; `0152` respektiert es jetzt. **Notaus wieder scharf** (Marco, 12.09.): Patch `0159` schaltet die Abschaltung bei **Lüfterstillstand** wieder ein — unter `fg-warn-speed` (1000 U/min) für `fg-warn-cnt` (8) Sekunden ruft der Treiber `orderly_poweroff(true)`. Der Tacho ist der Schutz, den dieses Gerät hat, und er ist belegt (PB5 aus → 0, an → 4770). Abschalten zum Messen: `fan_stall_shutdown=0`. `thermal_shutdown` bleibt aus — ohne NTC gibt es nichts zu messen. Details [`60`](60-offen.md) |
| **pinctrl-IRQ-Fehler** (`0143`/`0144`) | **behoben und abgenommen** (11.09.): `0004` hatte die `interrupts`-Liste des `pio` nach Hardware-Bank statt nach IRQ-Bank indiziert. Weil dem H713 die Bank PE fehlt, landete PHs Handler auf SPI 61 und auf PHs echter Leitung SPI 60 der Handler, der sich für PG hielt — der löschte nie etwas, die Leitung blieb oben, CPU 0 stand. Lag seit `0004` latent im Baum; board-mgr war nur der erste Nutzer eines GPIO-Interrupts am Haupt-PIO. Rückbau auf Mainline- und Hersteller-Semantik |
| **Altbestand** (`legacy/`) | **abgeglichen** (11./12.09.): tvtop+nsi, AV1-Dekoder, `display/ge2d/` (sehr spät) → Liste ([`61`](61-todo.md)); board-mgr und CE → siehe oben. Gegenüber cstenger fehlt uns nichts |
| **WLAN** (aic8800, `0155`, `aic8800-0007`) | **läuft auf dem Release-Abbild** (12.09.): Firmware aus dem Abzug des Nutzers (`h713-extract`, 13 Platzhalter im Abbild). Betrieb über `/etc/h713/wifi.env` + `h713-wifi` (`mode=ap\|sta\|off`, Vorgabe AP `h713`/`magcubic` mit Warnung); `country=` wirkt als `default_ccode`. Bluetooth bleibt draußen: Firmware nicht im Abzug |
| **Abbild v0.9** (12.09.) | **am Gerät**: Kernel `f7dd06d0` (defconfig allein, kein debugfs, `loglevel=4`), U-Boot v7 mit gültiger Umgebung ab Werk, Rootfs 242 MiB mit WLAN, `h713-focus`, `h713-cam`, `fw_printenv`. Zweimal über den Nutzerweg eingespielt (v0.8, v0.9). Details [`115`](115-handoff-20260912.md), Beleg `analyse/boot/abnahme-v08-20260912.txt` |
| [`94`](94-fokusmotor-endschalter.md) Fokusmotor | **läuft** (12.09.): PH14 ist ein Bereichswächter, am Gerät vermessen (`raw` kippt bei step −206). `0153`–`0157`: Bias frei, Rohpegel in `motor_limit`, `homing` standardmäßig aus, Knoten aktiv. Bedienung `userspace/h713-focus` (ein Skript). Autofokus nur mit Testbild — später |
| [`100`](100-plan-hdmi-audio.md) / [`101`](101-plan-audio-treiber.md) HDMI-Audio | **abgenommen** (08.09. 22:05, inkl. Lippensynchronität): Treiberstapel Serie 110 = GUT `d5fd82a7`; offen Gerätetöne-Mischung (Plan 102) |

Handoffs in zeitlicher Folge: [`69`](69-handoff-20260905.md) → [`75`](75-handoff-20260907.md) → [`97`](97-handoff-20260908.md) → [`106`](106-handoff-20260910.md) → [`111`](111-handoff-20260910-abend.md) → [`115`](115-handoff-20260912.md) (aktuell: **wo was liegt, Gerätezustand, Befehle**).

## 5. Was offen ist

**Die Liste steht in [`61-todo.md`](61-todo.md)** — eine Zeile je Punkt, nach Dringlichkeit sortiert (35 offen, Stand
12.09. mittags). [`60-offen.md`](60-offen.md) trägt die Begründungen und die Geschichte dazu; [`115`](115-handoff-20260912.md)
sagt, wo was liegt und mit welchen Befehlen es weitergeht. Die Kurzfassung: keine Blocker im Bildpfad, A.1/A.3/A.4
sind am Gerät durch. **Nächstes vor v0.1:** Beta-Warnung (A.2), zwei Entscheidungen von Marco (`h713_ce_test`-
Autoload, `analyse/hdcp-keys/`), R5-Reste, dann Repo/README/PRs (R3/R4/R6). Am Gerät offen: Telefon am AP,
`mode=sta`, Kamera mit hellem Bild, Env-Übernahme bei Neuinstallation. Danach die Liste aus dem Altbestand
(tvtop/nsi, AV1, ge2d), HDCP 1.4 (`112`/`114`), EDID, Gerätetöne (`102`), Standby (`104`).

## 6. Regeln, die teuer waren

1. **Was am Gerät wirkt, steht in `series`.** Kein Patch außerhalb der Serie, kein Bau außerhalb des
   Containers `h713-build`, keine Host-Umgehung ([`97`](97-handoff-20260908.md) §4).
2. **Ein Kriterium, das nicht scheitern kann, prüft nichts.** Vor jeder Messung: Positivkontrolle; Fotos
   ansehen, nicht nur Mittelwerte lesen.
3. **Agenten ändern keine Datei unter `mainline/patches/kernel/` und fassen das Board nicht an.**
4. **Vor jedem Kaltstart TFTP prüfen**, sonst steht das Board in U-Boot und nur Marco kann es lösen.
5. **Board-Läufe in kurzen Schritten** (20–30 s Timeout), Hänger sofort melden — kein Watchdog.
6. **Zwischen `tftpboot` und `mmc write` immer `crc32` vergleichen.** Ein fehlgeschlagenes `tftpboot` lässt den alten
   Speicherinhalt stehen; wer ihn trotzdem schreibt, zerstört den Bootloader (passiert am 10.09.).
7. **LBA 12288…14335 nie beschreiben.** Dort liegt der Secure Storage mit HDCP-Material, WLAN-/BT-MACs und
   Seriennummer — gerätespezifisch, in keinem Image, nicht wiederherstellbar. Der Installer sperrt den Bereich hart.
8. **Vor dem Schreiben auf ein Blockgerät: aushängen und `O_EXCL`.** Ein eingehängtes Dateisystem schreibt seinen
   Zwischenspeicher über frische Daten zurück, und die Rückleseprobe merkt es nicht.
9. **HDCP-Material wird nie extrahiert, nie ins Repo gelegt, nie in ein Manifest geschrieben.** `re/` bleibt privat.
