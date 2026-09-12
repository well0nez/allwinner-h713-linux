# Offene Punkte

**Stand 11.09.2026, abends.** Der Bildpfad hat keine Blocker mehr; was hier steht, sind Randpunkte,
Infrastruktur und Rückmeldungen. Die Fassung vom 07.09. mit der vollständigen Vorgeschichte liegt in
[`nachtlog/60-offen-bis-20260907.md`](nachtlog/60-offen-bis-20260907.md).

## HDMI-Audio — Treiber abgenommen, Folgepaket offen

Plan [`101-plan-audio-treiber.md`](101-plan-audio-treiber.md) (§5 Abnahmetabelle), Protokoll [`nachtlog/S16`](nachtlog/S16-hdmi-audio.md).
Stand 08.09. 21:00: **Treiberstapel am Gerät** — Serie 110 (`0134`–`0138`, Baum `d5fd82a7`), `h713-tv` mit Audio-Automat. HDMI-Ton läuft
ohne `/dev/mem`, Rate folgt 32/44,1/48 kHz, Lautstärke/Stumm gemessen, Zyklen/Reset/Modus/Stecker/Resync bestanden, 0 Mailbox-Timeouts
(verlorene Leseanfragen werden wiederholt, `mbox_reissues`). Dauerlauf 29 min und Modul 20× neu laden bestanden; **GUT-Stand `d5fd82a7`** (21:40). Lippensynchronität von Marco abgenommen (22:05, YouTube: „perfekt, synchron“). **Offen:** **Gerätetöne bei HDMI-Quelle** — der DAC nimmt nur eine Quelle, ein PC hält den HDMI-Audiostrom dauerhaft offen → Mischung im DSP wie Stock
(Pfad `0x89`, `MIXER2`, Audio-Bridge-Treiber; **Plan [`102`](102-plan-audio-mischung.md), TODO, nicht begonnen**). Nicht nötig: DSP2-Boot (Effektkern). Merken: Zuspieler-`IEC958 Playback Switch` fällt bei jedem Beamer-Neustart und Modeset auf off.

## Release (Plan [`105`](105-plan-release.md)) — die Restarbeit

**Fertig:** R0 (FEL-Boot, Laufwerksfreigabe, PC-Installer), R1 (Boot vom Gerät: Layout v3, Rootfs 228 MiB,
20/20 Kaltstarts), R2 (`h713-extract` 0.4, eigener ext4-Leser statt `debugfs`, Profile `hy310` und `l018`),
**der Abbild-Bauer** (`hy310-mkimage`, [`S47`](nachtlog/S47-abbild-bauer.md)). Der Weg für den Nutzer steht in
[`110`](110-plan-installationsweg.md) und löst R0/R1 aus `105` ab.

**`super.fex` ist ein Android-Sparse-Abbild, kein Rohabbild** (10.09., der schwerste Fehler des Abends). Die Datei
ist 1538 MiB groß und enthält **2048 MiB** in 4964 Stücken, Kennung `0xed26ff3a` in den ersten vier Bytes. Wir haben
den Container roh auf die Partition geschrieben. In `super` liegen `system`, `vendor` und `product`; ohne gültige
LP-Metadaten findet die erste Stufe von `init` sie nicht und startet in den Bootloader zurück — **ohne jede Meldung**,
weshalb der Fehler zweimal übersehen wurde.

Behoben: `sparse_schreiben()` entpackt beim Schreiben (RAW, FILL, DONT_CARE, CRC32; `DONT_CARE` wird genullt, weil
dort sonst das Vorgängersystem stünde). Gegen die Attrappe und am Gerät geprüft: genau 2048,00 MiB, LP-Geometrie bei
Offset 4096 und 8192, Metadatenkopf bei 12288 mit `system`, `vendor`, `product`.

**Die Lehre:** eine Datei aus einem Firmware-Container ist nicht automatisch ein Rohabbild. Alle vierzehn geschriebenen
Dateien wurden daraufhin geprüft — nur `super.fex` ist gepackt, der Rest roh. Diese Prüfung gehört fest in das
Werkzeug, nicht in den Kopf des Autors.

**Warum Android nach dem Zurückspielen nicht startet, und was sonst noch fehlte.** Zwei Anläufe am 10.09. endeten in
derselben Startschleife:

```
[    1.202733] EXT4-fs (mmcblk0p19): VFS: Can't find ext4 filesystem
[    1.461814] reboot: Restarting system with command 'bootloader'
```

`mmcblk0p19` ist `metadata` (LBA 4858880, 16 MiB). Die Antwort steht in der fstab aus dem `vendor_boot`-Ramdisk
(`first_stage_ramdisk/fstab.sun50iw12p1`):

```
/dev/block/by-name/metadata  /metadata  ext4  nodev,noatime,nosuid,errors=panic
                             wait,first_stage_mount,formattable,check
```

Der Eintrag ist **`formattable` und zugleich `first_stage_mount`**. Die erste Stufe von `init` hat kein `mke2fs`, das
liegt erst in `/system`. Sie kann also nicht formatieren und startet stattdessen in den Bootloader zurück. **Auf einem
Werksgerät legt das PC-Werkzeug des Herstellers dieses Dateisystem an** — im Firmware-Image steht es nicht, weder in
`sys_partition.fex` noch in `dlinfo.fex`, und `dlinfo.fex` ist nur die Liste der 13 Dateien, die geschrieben werden.

Behoben: der Installer schreibt ein leeres ext4 nach `metadata`, mitgeliefert als
`analyse/release/arbeit/r0-fel/metadata-leer-16m.ext4.gz` (**17 KB gepackt für 16 MiB**, Merkmale bewusst konservativ,
ohne `orphan_file`, `fast_commit` und `metadata_csum_seed`, damit Kernel 5.4 es mounten kann). `UDISK` braucht das
nicht: seine Zeile ist `latemount` ohne `first_stage_mount`, die zweite Stufe formatiert sie selbst.

**Nebenbefund zur GPT.** Das Image bringt in `sunxi_gpt.fex` eine eigene Partitionstabelle mit, und die weicht vom
Auslieferungszustand des Geräts ab: dort ist `media_data` 256 MiB groß, auf dem Gerät 272 MiB, und alles dahinter
liegt 16 MiB früher. Maßgeblich ist `sys_partition.fex`, und die stimmt mit dem Abzug des Geräts vor dem Umbau
überein (`analyse/boot/gpt-stock-20260910.txt`). Unsere Nachbildung ist damit richtig. **Trotzdem gehört der
Vergleich in den Installer:** weicht die mitgelieferte Tabelle von der errechneten ab, muss das Werkzeug es sagen,
statt es zu verschweigen.

**Das Nullen war nötig, aber allein nicht genug.** Der erste Rückspiel-Versuch am
10.09. endete in einer Startschleife:

```
[    1.239793] EXT4-fs (mmcblk0p19): VFS: Can't find ext4 filesystem
[    1.494550] reboot: Restarting system with command 'bootloader'
```

`mmcblk0p19` ist `metadata` (LBA 4858880, 16 MiB). Die Partition hat im Firmware-Image **keine Quelldatei**, also hat
unser Rückspielen sie nicht angefasst, und dort stand noch unser Linux. **Die Ursache ist prinzipiell:** das Werkzeug
des Herstellers löscht die eMMC, bevor es schreibt; wir schreiben nur, was im Image steht. Dreizehn der 26 Partitionen
haben keine Quelldatei und behalten deshalb den Inhalt des Vorgängersystems.

Behoben: `stock_zurueck()` nullt jetzt jede Partition ohne Quelldatei. Bei `UDISK` reichen die ersten 64 MiB, das
tötet den ext4-Superblock samt Reserven. **Ausgenommen bleiben `private`, `Reserve0_a` und `Reserve0_b`** — die gibt
es nur auf dem einen Gerät und kein Image bringt sie zurück. Gegen eine Attrappe geprüft: `metadata`, `boot_b` und der
Kopf von `UDISK` sind danach Nullen, die drei Ausnahmen unverändert, der Secure Storage ebenfalls.

**Drei weitere Befunde aus dem ersten scharfen Lauf (10.09., spätabends).** Sie stehen unten als Punkt 8 bis 10; der dritte
war ein Blocker: `bestaetigen()` verglich die Antwort gegen `"JA"`, `frage()` gibt sie aber klein zurück. Die Funktion
lieferte damit **immer** `False` — jeder Schreibweg des Installers war unbenutzbar, `--restore-stock`, `--restore` und
das Abbild gleichermaßen. Das ist behoben (Vergleich gegen `"ja"`, ohne Terminal weiterhin `False`). **Die Lehre:**
kein Trockenlauf der Welt findet einen Fehler in dem Zweig, den er überspringt. Vor jedem Release muss jeder
Schreibweg einmal scharf gelaufen sein.

**Der Stock-Rückweg ist scharf gelaufen** (10.09., 23:15, an Marcos Gerät): 18 Schreibstellen, **1718 MiB in
4 Minuten**, Rückgabe 0. Die Partitionstabelle zeigt danach wieder die 26 Android-Partitionen. **Der Secure Storage
ist nachweislich unberührt:** der Pflichtabzug von unmittelbar vor dem Schreiben und das Gerät danach ergeben
denselben Wert `cf2805fc…` über die volle Partition, und die ersten 56 KiB stimmen byteweise mit der Sicherung vom
Vormittag um 11:44 überein. HDCP-Material, WLAN- und BT-Adressen und die Seriennummer haben den Umbau und die
Rückspielung überstanden.
Der Trockenlauf davor hatte dieselben 18 Schreibstellen angekündigt: GPT aus `sys_partition.fex`, `boot0` und
`boot_package` je zweimal, der Secure Storage ausdrücklich unberührt. **Dass `env_b`, `boot_b` und `vendor_boot_b` leer bleiben, ist kein Fehler:** in der
`sys_partition.fex` des Herstellers steht für diese Partitionen selbst kein `downloadfile`. Das Werkzeug des
Herstellers lässt sie also genauso leer, die B-Slots füllt erst ein Android-Update.

**Zwei Nachträge zum Abbild** ([`S47`](nachtlog/S47-abbild-bauer.md)):
- **Das Abbild besteht aus drei Dateien, nicht aus einer.** Zwischen Teil A (ab Sektor 0) und Teil B (ab Sektor 14336)
  klafft genau der Secure Storage. Eine durchgehende Datei würde ihn beim Schreiben nullen — auch beim `dd` von Hand,
  das [`110`](110-plan-installationsweg.md) §7 ausdrücklich vorsieht. Wer das Abbild anfasst, muss diese Lücke kennen.
- **Der Platzbedarf am PC steigt auf rund 9,7 GB**, `110` nennt noch 8 GB. Vollabzug plus Abbild plus Arbeitskopie.

**Offen, nach Dringlichkeit:**

1. **ERLEDIGT 11.09. vormittags — das Abbild v0.1 trug ein veraltetes U-Boot und eine falsche Vorgabe.**
   Zwei getrennte Fehler, beide im Abbild, beide am Gerät bestätigt:
   - **U-Boot von Patch 0023** statt 0025: `hy310-mkimage` griff auf `tftp/uboot-proper-v3layout.bin` vom 10.09.
     14:09. Es fehlte `net.ifnames=0`. **Behoben:** frisch gebaut im Container aus `hy310_qz713_v3_1_defconfig`
     beim Stand `0cab64cb95f` (`mainline/build/uboot-v6-release`), aufgeteilt nach `tftp/spl-release.bin` und
     `tftp/uboot-proper-release.bin`; der Bauer zeigt dorthin, liest die Versionskennung aus beiden, meldet sie
     in Schritt 1 und schreibt sie unter `bausteine` in die Tabelle. Nebenbefund: der alte Bau hatte
     `CONFIG_ENV_MMC_DEVICE_INDEX=0`, der Defconfig verlangt 1.
   - **`h713_mips_dev=1:2` in `board/sunxi/hy310.env`** — Partition 2 ist in Layout v3 `hy310-uboot`, ein
     Rohbereich; die Anzeige-Artefakte liegen auf Partition 5. Der Wert stammte aus dem Stock-Layout, und der
     Kommentar darüber sagte, die Installation solle ihn per `saveenv` umsetzen. Unser Abbild liefert die
     Umgebung aber **leer** aus, also blieb die eingebaute Vorgabe stehen. **Behoben:** `h713_mips_dev=1#hy310-boot`
     (Adressierung über den Partitionsnamen, vom Code ausdrücklich unterstützt, vgl. `109` §3.1), Kommentar
     angepasst. **Der Wert im U-Boot-Baum ist noch nicht committet** (siehe Punkt „Uncommittete U-Boot-Änderungen").
   - **Abbild v0.3** gebaut; nur Teil A (6 MiB) aufs Gerät, in einer Sekunde. `_paket_schreiben()` überspringt
     den Füllschritt jetzt, wenn der Teil mit den Platzhaltern nicht geschrieben wird — vorher hätte es eine
     1,15-GB-Arbeitskopie gefüllt und weggeworfen.
   - **Ergebnis am Gerät:** `eth0` da, MIPS geladen (`h713-tv` findet card1, CRTC 36, Plane 38, Gamma, Preset),
     Anzeigekette steht, wartet auf Signal. **Adresse jetzt 192.168.8.141** — vergibt der Router nach der MAC des
     USB-Ethernet-Adapters (`00:e0:fc:68:24:cb`, `r8152`); der Hostname `hy310` wird per DHCP korrekt mitgeschickt.
     Wer eine feste Adresse will, braucht eine Reservierung im Router auf diese MAC.
2. **ERLEDIGT — serielle Konsole geht.** Am 11.09. über `tools/uart-capture.py`-Portöffnung mit eigenem Prompt
   auf die gebootete Linux-Konsole gegangen: Autologin da, `/proc/cmdline` lesbar. Die Meldung von gestern Nacht
   war eine hängende Sitzung, kein Fehler im Abbild. **Merken:** kein Ethernet ≠ kein `eth0` — der
   Ethernet-Adapter hängt am USB, und den belegt FEL. Solange die Laufwerksfreigabe läuft, gibt es kein Netz.
3. **`sunxi-fel` als Windows-Programm — untersucht am 11.09., bewusst zurückgestellt.** Das Makefile von
   `sunxi-tools` **hat** einen Windows-Zweig (`ifeq ($(OS),Windows_NT)`, `-lws2_32`, Ersatz für `mmap`), und
   `mingw-w64` ist im Container verfügbar. **Es fehlen aber alle drei Bibliotheken:** für `libusb-1.0`, `zlib` und
   `libfdt` gibt es in den Paketquellen keine mingw-Varianten. Ein `sunxi-fel.exe` verlangt also, die drei erst
   quer zu bauen. **Empfehlung: nicht jetzt.** Zum einen kommt dabei eine Datei heraus, die hier niemand starten
   kann (kein Windows verfügbar, Marco 11.09.); zum anderen wäre der bequeme Weg — fertige Windows-DLLs aus dem
   Netz — genau die Sorte Abkürzung, die dieses Projekt sich verbietet.
   **Für v0.1 heißt das:** in der Funktionsmatrix steht „Windows: noch nicht unterstützt, der PC braucht Linux".
   Das ist ehrlicher als eine ungetestete `.exe`.
   **Wenn es später kommt:** libusb-1.0, zlib und dtc/libfdt mit `x86_64-w64-mingw32-gcc` bauen, deren
   `.pc`-Dateien in `PKG_CONFIG_PATH`, dann `make CC=x86_64-w64-mingw32-gcc sunxi-fel`. Prüfen lässt es sich erst
   mit einer Windows-Maschine, und zwar am ganzen Weg (FEL erkennen, U-Boot laden, Laufwerk beschreiben).
4. **Windows-Pfad im Installer ungetestet** und bis auf Weiteres nicht testbar (siehe 3). Er steht als Entwurf im
   Code; `_get_osfhandle` liegt dort nicht in `kernel32` ([`S46`](nachtlog/S46-kritische-pruefung.md)). Solange
   Punkt 3 offen ist, bringt das Ausbessern nichts — beides gehört in einen Durchgang, an einer Windows-Maschine.
5. **ERLEDIGT 11.09. — Geräteerkennung im Installer** ([`110`](110-plan-installationsweg.md) §8). Vor dem ersten
   Schreibzugriff: GPT → `super` → LP-Metadaten → `vendor_a` → `build.prop` → `ro.vendor.build.fingerprint`, dann
   Abgleich mit der Gerätetabelle des Extraktors. **Gerechnet wird nichts selbst** — GPT, LP, ext4-Leser und
   Tabelle stehen im Extraktor, eine zweite Fassung wäre die Doppelpflege, die dieses Projekt zweimal teuer
   bezahlt hat. Gegen den Stock-Abzug geprüft: **HY310 erkannt in 0,01 s**, Android 11, Stand 24.07. 10:19.
   Drei Ausgänge, alle geprüft: bekannt → weiter; **unbekannt → Abbruch** mit Kennung und Bitte um Meldung
   (kein `--trotzdem`, das Raten kostet im schlimmsten Fall den Secure Storage); umgebautes Gerät → „nur der Abzug
   ist sinnvoll". `--ohne-erkennung` gibt es nur für die Entwicklung.
6. **Offene Befunde aus [`S46`](nachtlog/S46-kritische-pruefung.md)** — der Rest ist B10 (welche
   `sunxi-fel`-Binärdatei ausgeliefert wird). **B7 erledigt** — Teil C des Abbilds schreibt die Sicherungs-GPT ans
   Plattenende. **B8 erledigt** und dabei viel wichtiger gewesen als gedacht, siehe unten.
7. **GESTRICHEN 11.09. (Marco): Scanner für geschützte Bereiche bei fremden Firmwares.** Begründung: der
   Installer bricht seit heute bei unbekannter Firmware ohnehin ab und bittet um eine Meldung (Punkt 5). Er
   schreibt also nie auf ein Gerät, dessen geschützte Bereiche er nicht kennt — ein Scanner wäre nur nötig, wenn
   wir das Schreiben trotzdem erlauben wollten, und genau das ist ausgeschlossen. Kommt ein unbekannter Stand
   herein, wächst die Tabelle über die gemeldete Kennung, nicht über Raten.
8. **ERLEDIGT 11.09. — U-Boot-Änderungen committet und als Patches exportiert.** Fünf Commits auf `h713-display`,
   `67544a2f5fd`…`1ebfc02fed0`, als `uboot-h713/0026`–`0030`: EL3-Falltür für die FEL-Rückkehr (`fel_utils.S`),
   ENVL_MMC-Rückfall bei FEL-Start (`board.c`), `CONFIG_ENV_MMC_DEVICE_INDEX=1` in vier Defconfigs, das
   Installer-Defconfig für die Laufwerksfreigabe, und `h713_mips_dev=1#hy310-boot`. Der Arbeitsbaum ist sauber.
9. **R3 Repo-Struktur** als Overlay auf cstengers Commit `8860991`, **R4 englische README mit Funktionsmatrix**,
   **R6 kleine PRs an cstenger** (der Env-Offset-Fix `0022` ist der beste Kandidat, er ist generisch).
10. **ERLEDIGT 11.09. — der Installer hängt selbst aus.** Vorher brach er ab und der Nutzer musste von Hand
    aushängen. Jetzt: `udisksctl unmount`, sonst `umount`, und zwar **in mehreren Durchgängen** — der Desktop
    hängt die Partitionen *nacheinander* ein, ein einziger Durchgang löst die erste, während die zweite gerade
    dazukommt (genau so am 11.09. passiert). Erst wenn zweimal hintereinander nichts mehr hängt, geht es weiter;
    was sich dann noch hält, benutzt wirklich jemand und führt weiter zum Abbruch.
11. **ERLEDIGT 11.09.** — `--device` schaltet die Abkürzung nicht mehr ab. Wer den Pfad ausdrücklich nennt, meint
    ihn auch; die Bedingung lautet jetzt `if schon_da` und der genannte Pfad bestimmt die Auswahl.
12. **Mitgelieferte GPT gegen die errechnete prüfen.** `sunxi_gpt.fex` und `sys_partition.fex` widersprechen sich in
    diesem Image bei `media_data` und allem dahinter. Der Installer soll beide lesen, vergleichen und die Abweichung
    melden, statt eine der beiden stillschweigend zu bevorzugen.
13. **Platzhalter-Sonderfall:** ist eine Vendor-Datei am Gerät *kleiner* als der Platzhalter, wird der Rest genullt
   statt `i_size` im Inode zu korrigieren. Bei unseren 30 Dateien tritt das nicht auf; bei einem fremden Gerät könnte
   doch noch ein kleiner ext4-Schreiber nötig werden ([`S47`](nachtlog/S47-abbild-bauer.md)).
14. **Beta-Warnung sichtbar machen.** Sie steht in [`110`](110-plan-installationsweg.md) §9 und muss in README,
   Release-Text und Installer-Ausgabe erscheinen: Vollabzug oder passendes Firmware-Image sind Pflicht, sonst ist ein
   Fehlschlag nicht heilbar. Marcos ausdrückliche Vorgabe.

## Einschalt-Gate — abgenommen, Gate am Dev-Gerät aus

Plan [`103-plan-einschaltgate.md`](103-plan-einschaltgate.md). Stufe 1 vollständig abgenommen (09.09.): Kaltstart → Bereitschaft (4 W, rote LED),
Taste → Start, `poweroff` und Taste unter Linux → Bereitschaft, `reboot` direkt, HDMI/Ton nach Bereitschaft zurück. Serie 112 = `GUT-bad2f16b`
(`0139` Taste PL4, `0140` EINT-Mux 0xe). U-Boot am Gerät: Gate + BL31; **am Dev-Gerät `h713_gate=0`** (Marco: „stört beim Boot"),
Einschalten per `setenv h713_gate 1; saveenv`. **Restpunkte (niedrig):** 20/20 Zyklen (6 fehlerfrei), IR-Wecken per Polling (103 §2.2 Option 1b).
Stufe 2 (ARISC-Deep-Sleep) = Plan [`104`](104-plan-standby-stufe2.md), geparkt, RE-Vorarbeit S39/S40 fertig.

## Paket A und B aus Plan 113 — gebaut, geprüft, zusammengeführt (11.09. nachmittags)

**Beide Agentenpakete sind im Baum**, von mir unabhängig nachgeprüft, nicht nur übernommen.

**A — Bildwerte zur Laufzeit** ([`113`](113-plan-pq-laufzeit-und-speichern.md) §A). `h713-tv` ruft beim Start
einmal `h713-pq show … --json` und bekommt acht Presets, die Firmware-Modusnummer, den Gamma-Exponenten und eine
frisch gerechnete LUT aus `/etc/h713/tvconfig`. Darüber legt es die mit `ctl save` gemerkten Werte.
**Am Gerät nachgemessen, von mir:** die LUT zur Laufzeit ist byteidentisch mit der eingecheckten; `preset vivid` +
`set sharpness 30` + `save` + Neustart ergibt im **Register** Kontrast 55, Sättigung 60, Schärfe 30, und der
Sättigungs-Gain folgt weiter `floor(60 × 1,28) = 76`; ohne `save` ist die Änderung nach dem Neustart weg; ohne
`tvconfig` warnt das Journal und es gilt die einkompilierte Tabelle, das Bild kommt trotzdem.
**Der Preis: der Start dauert statt 218–225 ms nun 609–670 ms**, also gut 400 ms mehr, überwiegend Python-Start.
Das ist mehr als die im Plan veranschlagten 200 ms und liegt weit innerhalb der Frist von 2 s. Zwei
Beschleunigungen wurden bewusst **nicht** eingebaut: ein eigener XML-Leser wäre genau die Zweitfassung, die dieses
Paket abschaffen soll, und ein Zwischenspeicher macht eine neue Fehlerfläche auf. Beides steht als Vorschlag,
falls die 400 ms je stören.

**B — Werkzeuge umbenannt.** `h713-tv`, `h713-pq`, `h713-extract`, `h713-fel`, `h713-hdcp-key`; Symlinks tragen
die alten Namen weiter. Abbild-Bauer, Installer, Defconfigs und **die Partitionsnamen** bleiben (Marcos
Entscheidung, Begründung in `113` B.3). **Am Gerät von Hand vollzogen und über einen Neustart bewiesen:** beide
Dienste aktiv, `h713-hdcp-key` übergibt den Schlüssel, kein „Schritt 20 übersprungen", `h713-tv` liest die
Bildwerte und die gemerkten Abweichungen aus `/var/lib/h713-tv/`.

**Was ich beim Nachprüfen selbst gefunden habe:**
- **`h713-hdcp-key.service` wurde im Abbild nie verlinkt** — mein Fehler vom Vormittag. Mit der `modprobe.d`-Sperre
  des Autoloads wäre das Gerät **ohne Bild** hochgekommen. Behoben in `build-rootfs.sh`, dazu zwei neue
  Abnahmeprüfungen.
- Ein `__pycache__` im Overlay wäre ins Abbild gewandert. Die Kopie filtert es jetzt.
- Fünf Fehlalarme im Prüfskript der Umbenennung, alle behoben: die Prüfung fand ihre eigenen Suchmuster, meldete
  `/srv/h713-rootfs` (die NFS-Wurzel dieses Rechners) als Partitionsnamen, hielt Messprotokolle unter
  `analyse/boot/` für offene Fundstellen und schnitt Dateipfade am Punkt ab.

**Abbild v0.6 ist gebaut und geprüft**, mit allem darin: richtige Dateibesitzer (`/etc/shadow` root:shadow 0640,
`/root/.ssh` 0700), 31 Platzhalter samt `authorized_keys`, Secure Storage unberührt. **Noch nicht eingespielt** —
das braucht FEL und damit Marco.

**Offen aus A:** die Messreihe zu `computer`, `game` und `hdr` (braucht ein Auge vor der Wand), und die
Sichtprüfung über die Kamera, die eine **stehende** Quelle braucht.
**Nebenbefund des Agenten:** nach einem Neustart bleibt die Quelle manchmal aus; `ctl replug` holt sie jedes Mal
zurück. Das trifft die Kaltstartserie — „kein Signal" ist dort von „Programmfehler" zu trennen.

## Abbild v0.7 ist eingespielt und läuft (11.09., 17:50)

Wie v0.6, dazu der umbenannte Konfigurationspfad. **Am Gerät nachgesehen:** `/etc/h713/` mit `tv.conf` und den
acht PQ-Dateien in `tvconfig/`, `/etc/hy310/` existiert nicht mehr, SSH-Schlüssel aus dem Abbild (4096 B),
beide Dienste aktiv, `bildwerte 8 Presets und Gamma 2.20 aus /etc/h713/tvconfig (h713-pq, 583 ms)`.

**`/etc/hy310` → `/etc/h713`** (Marco, 11.09.): der Pfad war das Einzige unter den verbliebenen `hy310`-Namen, das
weder gerätespezifisch noch eine Momentaufnahme ist. Mitgezogen in `h713-tv`, `h713-pq`, `build-rootfs.sh`,
`hy310-mkimage` (die 8 PQ-Zielpfade) und den lebenden Dokumenten; die Umgebungsvariable heißt jetzt
`H713_TVCONFIG` und nimmt `HY310_TVCONFIG` weiter an. **Was bewusst `hy310` bleibt:** die Partitionsnamen, die
ALSA-Karte `hy310hdmi`, die extrahierten Vendor-Dateien (`hy310-edid.bin`, `hy310-hdcp22.bin`), die alten
Hersteller-Daemons (`hy310-pqd`, `hy310-hdmird`) und die Arbeitskopien unter `analyse/*/arbeit/`.

**Zwei weitere Fehler im Installer gefunden und behoben:**
- **`O_EXCL` scheitert mit EBUSY, auch wenn nichts eingehängt ist** — der Desktop hält ein frisch erschienenes
  Laufwerk kurz offen, um es zu untersuchen. Jetzt zehn Anläufe über fünf Sekunden statt sofortigem Abbruch.
- **`h713-fel` warnt jetzt vor dem Auslösen**, dass das A-auf-A-Kabel stecken muss. Ohne es sitzt das Gerät danach
  dunkel und unerreichbar in FEL — genau so passiert. Dazu der Hinweis, dass die Steckdose allein nicht
  neu startet, solange USB Strom liefert.

**Merken für jede Prüfung nach dem Einspielen:** der Wirtsschlüssel ändert sich, weil das Dateisystem frisch ist.
Eine Warteschleife auf `ssh` meldet dann fälschlich „nicht erreichbar" — erst `ssh-keygen -R` laufen lassen.

## Abbild v0.6 ist eingespielt und läuft (11.09., 17:15)

Der erste Stand, bei dem alles zusammen stimmt. **Eingespielt ohne eine einzige Handbewegung am Gerät:**
`h713-fel` hat es aus dem laufenden Linux in FEL geschickt, der Installer hat geschrieben, danach ein Kaltstart.

| geprüft | Ergebnis |
|---|---|
| SSH mit dem Schlüssel **aus dem Abbild** | geht — kein Umweg über die serielle Konsole mehr |
| `/etc/passwd`, `/etc/shadow`, `authorized_keys` | `0:0`, `0:42` 0640, `0:0` 0600 — der uid-1000-Fehler ist weg |
| `h713-tv@video1`, `h713-hdcp-key` | beide aktiv |
| HDCP-Schlüssel | aus dem Secure Storage übergeben, **kein** „Schritt 20 übersprungen" |
| Bildwerte | 8 Presets und Gamma aus `/etc/h713/tvconfig` (`h713-pq`, 596 ms) |
| Uhr | `systemd-timesyncd` hat gestellt, sobald Netz da war |
| Bild | läuft, Preset `standard` aus den Gerätedaten |

**Zwei Betriebslehren aus dem Einspielen, beide teuer erkauft:**
- **Die schaltbare Steckdose allein startet das Gerät nicht neu, solange das USB-Kabel zum PC steckt.** Der Beamer
  zieht darüber Strom. Wer aus der Laufwerksfreigabe heraus einen Kaltstart braucht, muss **USB abziehen oder das
  Gerät von Hand** aus- und einschalten. Das gilt für jeden FEL- und `ums`-Lauf.
- **Nach einem Kaltstart wartet das Gerät auf die Taste**, weil die eingebaute Vorgabe `h713_gate=1` setzt. Auf SSH
  zu warten, bevor jemand gedrückt hat, ist sinnlos. Wer ohne Taste arbeiten will: `setenv h713_gate 0; saveenv`
  am U-Boot-Prompt.

## Rootfs-Abbild v0.5 nicht weitergeben — allen Dateien gehört uid 1000

**Selbst nachgemessen** (`debugfs -R "stat /etc/passwd"`), sowohl in der Bau-Eingabe `r0-fel/tmp/hy310-rootfs-platz.ext4`
als auch im **ausgelieferten Teil B von v0.1, der auf dem Gerät liegt**: `/etc/passwd`, `/etc/shadow`, `/root` gehören
`1000:1000` statt `root:root`. Ursache: `mkimage-eingaben.sh` lief ohne `-u root` im Container, `tar` kann als Nutzer
1000 keinen Besitzer setzen, und `mke2fs -d` übernimmt, was im Baum steht. Im `hy310-rootfs.tar` selbst stimmt alles.
Folgen: `sshd` nähme wegen `StrictModes` kein `authorized_keys` an, `passwd`/`su`/PAM sind kaputt, `unix_chkpwd` hat
sein setgid verloren. Gefunden vom Agenten, von mir unabhängig bestätigt.
**Behoben in Patch 04:** `mkimage-eingaben.sh` verlangt jetzt root und sagt warum, und `hy310-mkimage` prüft Besitz und
Modus im fertigen ext4 nach und bricht bei Abweichung ab (gegen v0.5 laufen gelassen: acht Verstöße, Abbruch).
**Erledigt mit v0.6** (11.09., 17:15, siehe oben): `/etc/passwd` `0:0`, `/etc/shadow` `0:42` 0640,
`authorized_keys` `0:0` 0600 — am Gerät gemessen. v0.7 läuft. Dieser Abschnitt bleibt als Beleg, warum v0.5 nicht
weitergegeben wird.

## Werkzeugnamen vor dem Release entscheiden (Marco, 11.09.)

Alles heißt heute nach **einem** Gerät: `h713-tv`, `h713-pq`, `h713-extract`, `hy310-install`, `hy310-mkimage`,
`h713-fel`, `h713-hdcp-key`, dazu die Partitionsnamen `hy310-boot`, `hy310-rootfs`, `hy310-keys`, `hy310-spl`,
`hy310-uboot`, `hy310-env` und die Umgebungsvariablen `h713_*`. Der Bildpfad ist aber eine Eigenschaft des **H713**,
nicht des HY310; der Extraktor kennt bereits ein zweites Gerät (Profil `l018`).

**Marcos Entscheidung:** Der **Abbild-Bauer und das Abbild dürfen gerätespezifisch bleiben** — jede Firmware gilt
ohnehin für ein bestimmtes Gerät. **Die Werkzeuge sollen umbenannt werden, und zwar vor dem Release**, weil ein
Wechsel danach an Nutzern hängt.

**Zu klären beim Umbenennen:** welcher Name (`h713-*` liegt nahe, deckt HY310 und L018); ob die **Partitionsnamen**
mitgehen — sie stecken in `board/sunxi/hy310.env` (`h713_mips_dev=1#hy310-boot`), in `bootargs`
(`root=PARTLABEL=hy310-rootfs`), im Abbild-Bauer, im Installer und in der Schreibsperre, ein Wechsel dort will in
einem Zug gemacht und einmal am Gerät bewiesen sein; ob die Defconfigs (`hy310_qz713_v3_1_defconfig`) mitgehen —
die sind board-spezifisch und dürfen bleiben. **Reihenfolge:** entscheiden, dann umbenennen, dann Repo-Umbau (R3).

## Bildpfad — Randpunkte

- **`0130`, Zweig „Signal steht, Capture bleibt aus":** die SetSource-Wiederholung mit Pause ist gebaut, aber am
  Gerät nicht betreten — jedes Neu-Einrasten heilt die Capture selbst. Bleibt als Netz für den 01:55-Fall.
  Rezept zum Erzeugen des Wartezustands: `re/captures/weltneuheit/s13-20260908/provoke.sh`.
- **Firmware-Grenzen:** 1600×900 und 120-Hz-Varianten stehen nicht in `kHalSignalID_*` → Konsole. Nur HDMI-1
  (`SetSource 3`) ist angebunden.
- **Weißabgleich/CTM** ist am CRTC vorhanden, aber ohne Stock-Vergleich (Stock-Daten neutral).
- **ERLEDIGT 11.09.: Farbton und Schärfe sind am Gerät gemessen.** Beide standen in [`81`](81-pq-datenmodell.md) §7
  als „RE belegt, am Gerät nie gemessen". Gemessen mit anliegendem 1080p-Signal, Regler gesetzt und Register über
  `/dev/mem` zurückgelesen: `hue` → `0x05001238[31:16]`, `sharpness` → `0x05001228[23:8]`, beide **eins zu eins über
  0…100**, ebenso `brightness` `0x05001234[15:0]`, `contrast` `0x05001234[31:16]`, `saturation` `0x05001238[15:0]`.
  **Sichtprüfung durch Marco am laufenden Bild:** `hue = 0` färbt ins **Magenta**, `hue = 100` ins **Grün** — eine
  saubere, symmetrische Farbtondrehung; das deckt sich mit der älteren Beobachtung am Bootlogo
  ([`nachtlog/I1`](nachtlog/I1-get-routinen.md)). `brightness = 0` lässt die dunklen Bildteile absaufen,
  `brightness = 100` hellt sie auf und macht das Bild flau — damit ist auch die Helligkeit **mit dem Auge**
  bestätigt, nicht mehr nur über die Kamera vom 07.09. Vorgabe ist 50, und das ist der Herstellerwert: in
  `pq_picturemode.ini` steht Helligkeit 50 in **allen sechs** Bildmodi, sie ist der einzige der fünf Regler, den
  der Hersteller nie verstellt. Ebenfalls bestätigt: die Firmware rechnet den Sättigungs-Gain selbst, `0x05140508[23:16]` folgt exakt
  `floor(Wert × 1,28)` über 0/25/50/75/100. Die Spalte „ohne Wirkung" bei `brightness` in der Ausgabe von
  `h713-pq` ist veraltet (widerlegt am 07.09., [`nachtlog/I0`](nachtlog/I0-helligkeit-nachgemessen.md)) und
  **gehört korrigiert**.
- **Presets am Gerät geprüft** (11.09.): `vivid` (Kontrast 55, Sättigung 60, Schärfe 60, DCI 3) und `cinema`
  (45/45/40, DCI 0, Schwarzanhebung 0) setzen alle Register wie in `pq_picturemode.ini` vorgegeben. Marco zu
  `vivid`: „sehr nice". Offen: `computer` (Schärfe 0) und ob `game`/`hdr` sich außerhalb dieser fünf Werte
  unterscheiden.
- **Gammakurve 2,2** (Stock-Wert, seit 10:25 beim Start geladen): Sichtprüfung durch Marco gegen das
  Stock-Bild steht aus; `-g none` in der Unit schaltet sie ab.
- **Preset beim Start wählbar machen** (Marco, 11.09.). Heute schickt `h713-tv` fest `standard`. Der Platz dafür
  ist seit dem 11.09. da: ein dritter Schlüssel `preset = NAME | zuletzt` in `/etc/h713/tv.conf`, dieselbe Mechanik
  wie `start`. Sinnvoll gleich mit: die einzelnen Regler merken, damit eine Nachjustierung den Neustart übersteht.
- **`h713-tv` — Bildquelle Automatik/manuell als Gate (Marco 09.09. 22:10):** heute gibt es `ctl auto` (Vorgabe, Bild folgt dem Signal),
  `ctl off` (Konsole, nie automatisch) und `ctl on` (HDMI erzwungen), aber keine Voreinstellung und kein Merken: der Dienst startet immer in
  `auto`. Zu tun: Konfigurationsdatei (`/etc/h713-tv.conf`) und Unit-Option für den Startmodus `auto|manuell`, zuletzt gesetzten Modus
  über Neustarts merken, später Bindung des manuellen Wechsels an Fernbedienung oder Taste (IR-Strecke noch nicht belastbar). Es gibt nur
  HDMI-1: „Umschalten" heißt Konsole ↔ HDMI.
- **`h713-tv`:** `replug` (S_EDID blocks=0) fehlt; die Plane liest den Ring direkt (`hdmi-ring`), ein
  dma-buf-Import wäre der KMS-konforme Weg — funktional heute gleichwertig.
- **`0128`/`0130`-Vorgeschichte:** das Kippen der Firmware nach 19 Rückrufen ist behoben (`0124`); die zwei
  anderen Altfehler in `cpu_comm` mit `0125`.

## HDCP und EDID

- **HDCP 2.2 kommt jetzt vom Gerät selbst** (11.09.). Marcos Einwand: „das liegt doch auf der eMMC, haben wir extra da
  gelassen." Stimmt — der Schlüssel liegt im Secure Storage (Item `hdcpkeyV22`, Block 6, 912 Byte Nutzdaten), und der
  Treiber wollte genau diese 912 Byte, suchte sie aber als Datei in `/lib/firmware`. **Umgesetzt ohne Kernel-Änderung:**
  `overlay/usr/local/sbin/h713-hdcp-key` findet das Item (Partition `hy310-keys`, sonst roh in den ersten 16 MiB der
  eMMC — damit auch ein anderes Board), prüft Magic, Namen, CRC (zlib-crc32 über das Objekt ohne die letzten 4 Byte,
  am Gerät bestätigt) und den inneren Kopf, legt die 912 Byte kurz nach `/run/hy310/firmware/` (tmpfs, 0600), setzt
  `firmware_class.path`, lädt den Treiber, löscht die Datei und den Pfad. `h713-hdcp-key.service` läuft in
  `sysinit.target` nach der Geräteeinheit der Partition; `modprobe.d/h713-hdcp-key.conf` sperrt den udev-Autoload des
  Treibers, damit die Init-Sequenz nicht ohne Schlüssel läuft. **Am Gerät:** Schlüssel bei Sekunde 6,4, Treiber bei
  6,5 mit vollständiger Sequenz (22 Aufrufe), kein „Schritt 20 übersprungen" mehr, Datei weg, `h713-tv` aktiv.
  Der Schlüssel verlässt das Gerät nie, kein Werkzeug von uns fasst ihn an.
  **Offen bleibt der letzte Beweis:** ob die 912 Byte Klartext sind oder ein TEE-Chiffrat (Plan 68). Der MIPS hat die
  RPC ohne Fehler angenommen; entscheidend ist eine HDCP-pflichtige Quelle am Kabel (Streaming-Stick, Konsole, Blu-ray).
- **HDCP 1.4 — der Weg ist jetzt bekannt, und er ist Hardware-Krypto** ([`S49`](nachtlog/S49-hdcp14-schluesselpfad.md)).
  Bei Stock schreibt keine CPU Schlüsselbytes in HDMI-RX-Register. U-Boot legt das Item `hdcpkey` in OP-TEEs Keybox
  (SMC `0xb2000210`, op 1) und ruft op 5; OP-TEE lässt die **Crypto Engine** über den sicheren Kanal (`0x03040800`)
  die 288 Byte AES-128-ECB mit dem Efuse-Schlüssel **RSSK** (Key-Select 3) entschlüsseln und per DMA nach
  **`0x03041400`** schreiben — eine Schlüsselsenke im CE-Adressraum, kein DRAM. Danach steht `0x06840093` Bit 0, und
  `HdmiRx_HDCP14_LoadKey` nimmt den Zweig „schon geladen". **Die 320 Byte im Secure Storage sind chipgebundenes
  Chiffrat**, das nirgends in Software entschlüsselt wird; der Klartext existiert nur in der Hardware-Senke.
  **Für uns:** ein Treiber muss die CE mit `dst = 0x03041400` und Key-Select 3 programmieren — aus Linux, falls die
  Non-Secure-Welt CE_S/RSSK benutzen darf (Vorab-Test kostet einen Stromzyklus, S49 §„Was ein Linux-Treiber tun
  müsste" Schritt 2), sonst als SiP-SMC in TF-A. Vor dem MIPS-Start und nach jedem Power-Cycle der HDMI-RX-Domäne.
  Offen: Semantik von `0x03041400` (kein Datenblatt), wer Bit 0 setzt, ob die RSSK auf diesem Gerät gebrannt ist.
  **Das ist ein eigenes Paket nach dem Release**, nicht für v0.1. Bis dahin bleibt der Warteschleifen-Patch.
  **Der vollständige Auftrag dafür steht in [`112`](112-plan-hdcp14-crypto-engine.md)** — zurückgestellt, aber so
  geschrieben, dass ein Agent ohne Gesprächsverlauf damit anfangen kann.
  Nebenbefund, der HDCP 2.2 stützt: `hdcpkeyV22` steht nicht in der Stock-Keybox-Liste, geht also nie durch diesen
  Pfad — der MIPS bekommt die 912 Byte roh, was die Klartext-Annahme strukturell bestätigt.
- **`analyse/hdcp-keys/` enthält seit dem 04.09. echtes Schlüsselmaterial dieses Geräts** (HDCP 1.4, 2.2, Hashes,
  Seriennummer). Das war vor der Regel vom 10.09.; `analyse/` gehört zum Teil des Baums, der ins Release soll.
  **Marcos Entscheidung:** nach `re/device-dumps/` verschieben oder löschen. Nicht angefasst.
- **EDID 1.4 / 2.2 noch nicht durchgearbeitet.** Heute geht ein 512-B-Block (`HDMI_EDID_14.bin` + `HDMI_EDID_20.bin`) unverändert an die
  Firmware. Welche Modi das freigibt, ist ungeklärt; bekannt sind die Lücken bei 1600×900 und 120 Hz. Eigenes Paket, Matrix „eingeschränkt".

## Rootfs und Layout — umgesetzt, ein Todo bleibt

[`107`](107-plan-rootfs.md) Rootfs und [`109`](109-plan-layout-v3.md) Layout v3 sind **am Gerät**: sechs Partitionen,
Boot-Kette in den ersten 8 MiB, Rootfs 228 MiB auf 7,15 GiB Platz, Bild und Ton laufen, 20 von 20 Kaltstarts sauber.
zram läuft (461,8 MiB, Fragment `patches/kernel/board/zram.config`), Journal flüchtig, `net.ifnames=0` in der
Vorgabe (`0025`). **Gerät jetzt 192.168.8.143**, Hostname `hy310`. Layout v2 aus [`108`](108-plan-vendordaten.md)
ist damit Geschichte.

**Die Netzwerk-Identität ist gesichert:** der Block in `hy310-keys` (LBA 12288…14335) ist der sunxi Secure Storage
mit HDCP, **`wifiBleDatas`** (WLAN-/BT-MACs) und **`snum`** (Seriennummer) — am Gerät als eigene Partition gesperrt
und kopiert nach `re/device-dumps/`. `private` trägt nur den Namen, nicht die Daten (Korrektur zu S42 §2.5).

**Offenes Todo:** Abzug von `Reserve0_a/b` und `private` von einem **unangetasteten** Gerät. Die drei wurden bei uns
ohne Sicherung überschrieben; `Reserve0.fex` im Firmware-Image ist leer, also kommt durch kein Image zurück, was dort
gestanden haben mag. Ob dort überhaupt etwas Einmaliges lag, ist unbewiesen ([`109`](109-plan-layout-v3.md) §9.1).

**Der Vollabzug dieses Geräts liegt in `re/device-dumps/`** (7.818.182.656 B) — **aber nach dem Umbau gezogen**, er
enthält kein Android mehr. Ein Abzug im Auslieferungszustand fehlt uns.

## FEL aus dem laufenden U-Boot — ERLEDIGT 11.09. ([`S48`](nachtlog/S48-fel-aus-uboot.md) mit Nachtrag)

**`run fel` am U-Boot-Prompt bringt das Gerät ohne Reset-Taste in FEL.** Mechanismus: RTC-GP2 `0x07090108` :=
`0x5aa5a55a`, Reset, unser SPL liest das Flag als erstes, löscht es und springt nach `0x20` in den FEL-Einstieg des
BROM — genau wie der Hersteller-Boot0. Das BROM selbst liest das Flag nicht (gemessen). Fünf Durchgänge ohne Stromzyklus,
je 8–10 s, `sunxi-fel uboot` läuft aus dem so erzeugten FEL. Commits `uboot-h713/0031` (SPL-Stub) und `0032` (`fel`).
**Merken:** RTC-Register brauchen Schreibschleife und Wartezeit vor dem Reset, sonst verpufft das Flag (1 von 4).
**Noch offen daraus:** (1) `doku/20` §Recovery und S44 §17 als „falsches Register GP7" markieren; (2) ein Linux-Weg
(`reboot`-Modus oder kleines Werkzeug, das GP2 schreibt), damit der Installer ein laufendes System aus der Ferne in FEL
schickt; (3) einmal `md.l 0 0x2000` aus U-Boot mitschneiden, damit ein BROM-Abbild vorliegt.
**Nie schreiben:** GP2 = `0x5aa55aa5` (Crashdump-Handshake, Boot0 hinge ohne Gegenstelle).

## Kamera als Messmittel — was am 11.09. gelernt wurde

Die Webcam vor der Wand steht ab Werk auf **Belichtungs- und Weißabgleichsautomatik**, und bei einer
formatfüllenden Projektion führt beides in die Irre. Der Weißabgleich zieht **genau die Farbe**, die gemessen
werden soll, auf Neutralweiß: ein sichtbar gelbes Bild kam weder über diese Kamera noch über Marcos Handy als gelb
an. Neu im Projekt: **`analyse/hdmi-seq/camctl.py`** schaltet die Automatik über V4L2 ab und setzt feste Werte,
ohne `v4l2-ctl` und ohne Installation.

**Am 11.09. nachmittags geeicht und belegt.** Mit fester Belichtung (150) und Verstärkung (40), ohne einen einzigen
ausgebrannten Bildpunkt, fällt das Verhältnis Blau zu Rot einsinnig mit steigender Sättigung:

| Sättigung | 0 | 25 | 50 | 75 | 100 |
|---|---|---|---|---|---|
| B/R | 1,82 | 0,62 | 0,59 | 0,57 | 0,55 |
| Deutung | keine Farbe | gelb | rot/orange | | am kräftigsten |

Bei 0 verschwindet die Farbe ganz und übrig bleibt der Eigenbias der Kamera. **Damit ist der Sättigungsregler auch
am Bild bewiesen**, nicht nur im Register, und Marcos „da ist ein gelbes Bild" ist bestätigt.

**Vier Dinge, die man dabei wissen muss:**
- **Überbelichtung zerstört die Messung, nicht der Weißabgleich.** Beim ersten Anlauf waren **37 %** der Bildpunkte
  ausgebrannt, und dann kam „Sättigung 0" auf eine höhere Buntheit als `vivid` — physikalisch unmöglich. Erst die
  Kennzahl `ausgebrannt = 0` macht eine Messreihe gültig.
- **Der Weißabgleich von Hand wirkt bei dieser Kamera nicht.** Die Farbtemperatur lässt sich setzen, das Bild
  ändert sich nicht (2000 bis 6500 K liefern denselben Wert). Nur die Automatik abschalten hilft, gegen ein
  bekanntes Weiß eichen geht mit diesem Gerät nicht. Absolute Farbnamen bleiben deshalb unsicher, Vergleiche nicht.
- Die **Verstärkung stellt sich selbst um**, auch mit abgeschalteter Belichtungsautomatik. Vor jeder Messreihe
  nachsetzen und danach gegenprüfen.
- Eine feste Farbtemperatur ist ein **Messbezug, kein Weißabgleich**. 4000 K lässt eine neutrale Projektion
  bläulich erscheinen. Für „das Bild ist gelb" muss gegen ein bekanntes Weiß geeicht werden; für den Vergleich
  zweier Einstellungen reicht, dass sich an der Kamera zwischen den Messungen nichts ändert.
- **Ein A/B-Vergleich braucht eine stehende Quelle.** Bei laufendem Video misst man den Szenenwechsel. Am 11.09.
  kam „Sättigung 0" auf eine **höhere** Buntheit als das Preset `vivid` — physikalisch unmöglich, und genau daran
  fiel der Fehler auf. Für die Abnahme von Plan [`113`](113-plan-pq-laufzeit-und-speichern.md) braucht es also ein
  Standbild.

**Nebenbei behoben:** `analyse/hdmi-seq/wandcheck.py` brauchte `numpy`, das auf diesem Rechner fehlt — ein
Messwerkzeug, das an einem fehlenden Paket scheitert, misst nie. Es rechnet jetzt notfalls selbst, mit denselben
Kennzahlen.

## Module aus dem Altbestand — Abgleich 11.09.

Marcos Frage: „mein altes repo hat schon viele module gehabt die wir jetzt nicht haben in dem kernel". Der Abgleich
in-tree/out-of-tree ist gemacht; es sind **fünf** Lücken, kein Dutzend. Zwei wurden angefasst, drei gehen auf die Liste.
(Ursprünglich vier — `ge2d/` kam am 12.09. dazu, es stand vorher nur in [`80`](80-vergleich-baeume.md).)

- **`sunxi-tvtop` + `sunxi-nsi` — TODO, nicht begonnen.** Beide sind als Patch `0011`/`0012` in der Serie, aber im
  defconfig aus (`# CONFIG_SUNXI_NSI`, `# CONFIG_SUNXI_TVTOP`). TVTOP ist **absichtlich** aus, mit Begründung in
  [`0033`](../mainline/patches/kernel/0033-misc-decd-make-tvtop-link-optional.patch): sein `probe` beansprucht
  `CLK_PANEL`, `CLK_DEINT`, `CLK_SVP_DTL`, `CLK_BUS_DISP` und `RST_BUS_DISP` — genau die Takte, die U-Boot vor
  Linux programmiert und auf deren Überleben der Bildpfad angewiesen ist. Einen zweiten Besitzer dieser Takte in
  derselben Sitzung hochzufahren, in der DECD zum ersten Mal lief, wäre nicht auseinanderzuhalten gewesen. Das
  Argument gilt weiter, aber es ist ein Reihenfolgen-, kein Dauerargument: der Hersteller liefert beide, und der
  Vendor-Kernel wiederholt in `sunxi_tvtop_complete` nach jedem Resume den HDCP-Schlüsselnachlauf (S49) — die
  Standby-Wiederkehr ([`104`](104-plan-standby-stufe2.md)) und HDCP 1.4 hängen mittelbar daran. **Zu tun:** TVTOP
  einzeln hochfahren, an einem Punkt wo der Bildpfad sonst stabil ist, und messen ob die Übergabe hält; NSI (Bus-
  Prioritäten/Bandbreite) danach, es ist die harmlosere der beiden. Danach `0033` prüfen — der Compile-Guard darf
  bleiben, die Abhängigkeit wird nur wieder echt.
- **AV1-Dekoder — TODO, nicht begonnen.** Liegt nur im Altbestand (`legacy/drivers/media/av1/`, 7 Quelldateien,
  ~58 kB, `VIDEO_SUN50I_H713_AV1`, V4L2-stateless-M2M, 10-Bit-YUV420P bis 4K) und ist **nirgends in der Serie**.
  Der H713 ist der erste Allwinner mit AV1-Hardware. Ob der Treiber je an Silizium lief, ist unbelegt — er bringt
  ein eigenes `test-av1-driver.sh` mit. **Zu tun:** erst feststellen ob das RE-Stand oder lauffähiger Stand ist
  (Registerzugriffe gegen den Vendor-Kernel prüfen), dann als Serienpatch einreihen. Unabhängig vom Bildpfad und
  vom Release.
- **`display/ge2d/` — sehr spätes TODO (Marco, 12.09.).** Nachgetragen: beim Abgleich am 11.09. fehlte dieser
  Punkt, er steht seit dem 31.08. nur in [`80`](80-vergleich-baeume.md). Zehn Dateien, rund 3.000 Zeilen, der
  komplette Stock-Display-Stack: Panel-Konfiguration aus dem Devicetree, Backlight, OSD, SVP, fbdev und die
  DLPC3435-Lichtmaschine über I²C. **Nichts davon ist portiert**, und cstenger hat auch kein Gegenstück — an
  seiner Stelle steht [`0037`](../mainline/patches/kernel/0037-drm-add-h713-afbd-scanout-kms-driver.patch), das
  ausdrücklich nur übernimmt, was U-Boot hinterlassen hat.
  **Was das praktisch kostet:** kein Helligkeitsregler aus Linux. Die *Helligkeit selbst* ist gelöst und war nie
  ein fehlender Regler (PLL N+1 = 43 statt 41, falsche Mixer-Totale — [`70`](70-sackgassen.md)); PWM2 auf PB4 ist
  zweimal gemessen **nicht** der Lichtregler. Es fehlt also eine Bedienmöglichkeit, kein Bild.
  **Einordnung:** hinter AV1 und tvtop/nsi. Wer es aufgreift, fängt bei `sunxi_ge2d_dt.c` (215 Zeilen
  Devicetree-Parsing) an, nicht bei der Lichtmaschine.
- **`hy310-board-mgr` — wird jetzt mitgenommen**, siehe eigener Abschnitt unten.
- **Crypto Engine — entschieden, siehe [`114`](114-plan-crypto-engine.md).** Generische Krypto bleibt aus
  (cstengers Befund übernommen); gebraucht wird sie nur für den RSSK in HDCP 1.4.

## `hy310-board-mgr` — Lüfter läuft, aber Temperatur und Drehzahl sieht niemand

**Stand:** Treiber ist als [`0008`](../mainline/patches/kernel/0008-misc-add-hy310-board-mgr.patch) in der Serie
(1288 Zeilen), der DT-Knoten `board_mgr: fan` steht in [`0024`](../mainline/patches/kernel/0024-arm64-dts-add-sun50i-h713-hy200-qz713df-a1-board.patch),
aber **beides ist aus**: `# CONFIG_HY310_BOARD_MGR is not set` und `&board_mgr { status = "disabled"; }`.

**Was heute schon funktioniert:** der Lüfter dreht. Nicht durch diesen Treiber, sondern weil [`0030`](../mainline/patches/kernel/0030-arm64-dts-h713-fix-fan-power-gpio-hog.patch)
den kaputten `fan_power_hog` auf PB5 repariert hat (3 Zellen `<1 5 …>` statt einer linearen Nummer). Der Lüfter ist
ein **3-Draht-Lüfter**: rot +V, schwarz GND, gelb Tacho — an/aus, **keine Drehzahlsteuerung**. Das ist am Gerät
gemessen, nicht angenommen.

**Was fehlt:** Temperatur (NTC über LRADC) und Drehzahl (Tacho auf PH17) liest niemand. Es gibt keinen
hwmon-Eintrag, also auch keine Möglichkeit zu sehen, ob das Gerät im Betrieb zu warm wird.

**Der Knoten passt so nicht auf dieses Gerät** — er ist aus dem Vendor-DT übernommen und beschreibt eine andere
Lüfterbestückung. Drei Konflikte, die vor dem Einschalten weg müssen:

1. **PH17 doppelt belegt.** Der Knoten fordert `pwms = <&pwm 0 40000 0>` (PWM-Kanal 0 → PH17 als Ausgang) **und**
   `fg-gpio = <&pio 7 17 …>` (PH17 als Tacho-Eingang). Der Treiber holt sich via `devm_pwm_get(dev, "fan0")`
   tatsächlich den PWM. Nach `0030` ist PH17 aber die **Tacholeitung mit 3,3-V-Pull-up**. Den PWM dort auszugeben
   zerstört die Drehzahlmessung und treibt einen Ausgang gegen den Open-Collector des Lüfters. → `pwms`,
   `pwm-names`, `pwm_ids`, `pwm_period_ns`, `default-duty` und die `duty-array`-Tabellen gehören für dieses Board
   raus; der Treiber muss ohne PWM auskommen (der Lüfter ist an/aus).
2. **Selbstabschaltung scharf.** `hy310_board_mgr.c` ruft bei `temp_c > temp_poweroff` über `NTC_POWEROFF_CYCLES`
   Zyklen **`kernel_power_off()`** — und der Knoten setzt `temp_poweroff = <60>`. Die `lradc-table` stammt aus dem
   Vendor-DT eines möglicherweise anders bestückten Geräts; stimmt sie nicht, schaltet sich das Gerät im Betrieb
   unvermittelt ab. Der vorhandene Modulparameter `no_rpm_shutdown` schützt davor **nicht** — er bewacht nur den
   (ohnehin auskommentierten) Lüfterstillstandspfad. → **Erst messen, dann scharf schalten.** Ein eigener Parameter
   `no_thermal_shutdown` (Vorgabe: aus = keine Abschaltung), die NTC-Kurve über Stunden gegen eine zweite Messung
   halten, und erst dann eine Schwelle setzen, die zum gemessenen Verlauf passt.
3. **Altlast in den Bootargs.** `sun50i-h713-hy200-qz713df-a1.dts` gibt seit jeher
   `hy310_board_mgr.no_rpm_shutdown=1` mit, obwohl das Modul nie gebaut wurde. Entweder der Parameter wird echt
   oder die Zeile fliegt.

**Voraussetzungen, die stehen:** `CONFIG_IIO=y` und `CONFIG_SUN50I_H713_LRADC=y` sind gesetzt, der LRADC-Treiber
([`0019`](../mainline/patches/kernel/0019-iio-adc-add-h713-lradc-driver.patch)) meldet zwei IIO-Spannungskanäle —
der NTC-Pfad ist also verfügbar. **`CONFIG_HWMON` fehlt** und muss dazu ([`0030`](../mainline/patches/kernel/0030-arm64-dts-h713-fix-fan-power-gpio-hog.patch)
hatte es mit `SENSORS_PWM_FAN` zusammen gestrichen).

**Ziel:** `/sys/class/hwmon/*` mit Temperatur und Drehzahl, lesbar, ohne dass das Gerät sich selbst ausschaltet.
Namensfrage: `HY310_BOARD_MGR`/`hy310-board-mgr` ist gerätespezifisch und darf den Namen behalten
(vgl. Abschnitt „Werkzeugnamen").

### Abgleich mit dem Stock-Kernel (11.09.)

Marcos Einwand „die temperatur wird per polling abgefragt aktuell oder? das kann ja eig nich richtig sein" hat sich
gelohnt — nur an einer anderen Stelle als vermutet. Gelesen wurde das Stock-`vmlinux`
(`re/vendor/HY310/extracted/vmlinux.fex`, ARM32, **mit Debug-Info**, Quelldatei `pwm_fan.c`), Disassemblat über
capstone. Vier Befunde:

- **Temperatur: Stock pollt auch, und das ist richtig so.** `ntc_read` ist keine sysfs-Funktion, sondern die
  Arbeitsfunktion: sie ruft `get_adc_data` → `get_temp_data` und legt sich mit `schedule_delayed_work(…, 500)`
  wieder hin — **500 Jiffies, also 2 s** (HZ ist 250, siehe nächster Punkt). Ein NTC am ADC **kann** nicht anders
  gelesen werden: es gibt keinen Interrupt für „der Widerstand hat sich geändert", und der LRADC dieses SoC hat nur
  die Tastenerkennung, keinen Temperaturkomparator. Unser Treiber pollt mit 2,5 s — praktisch dasselbe.
- **Drehzahl: Stock benutzt einen echten Interrupt** — `fg_irq_handle` zählt die Impulse, angefordert über
  `gpiod_to_irq()` + `request_threaded_irq(…, flags = 3)`, also **beide Flanken**. Genau hier lag unser Altcode
  falsch: 10 000 hrtimer-Aufwachvorgänge pro Sekunde plus eigener `ioremap` auf die PIO-Register. Mit Patch `0141`
  machen wir es wie der Hersteller.
- **Die Drehzahl war um den Faktor 2 zu niedrig.** Stock rechnet `rpm = Zählerstand × 15` bei **beiden** Flanken
  über 1 s (250 Jiffies) — das sind 4 Flanken je Umdrehung. Unser Altcode zählte nur **steigende** Flanken, teilte
  aber trotzdem durch 4. Jetzt: steigende Flanken, `pulses-per-revolution = <2>` — dasselbe Ergebnis wie Stock.
- **Stock schaltet bei Übertemperatur NICHT ab.** Über der Warnschwelle (30 Zyklen) zieht es den Lüfter auf
  Stufe 3 und schickt ein Uevent `TEMP_STATE=HIGH_TEMP_MODE`; über der Abschaltschwelle (50 Zyklen **und** Temperatur
  über `temp_poweroff`) kommt `TEMP_STATE=SHUTDOWN` plus `record_exception(1)` (schreibt eine Logdatei) — und dann
  **nichts weiter**. Die Entscheidung trifft Android. `kernel_power_off()` steht bei Stock an genau einer Stelle:
  im **Lüfterstillstands**-Pfad, und auch dort nur, wenn ein Merker nicht gesetzt ist. Unser Altcode hatte es exakt
  andersherum — Übertemperatur-Abschaltung scharf, Stillstandspfad auskommentiert. Mit `0141` melden wir beides und
  schalten nichts ab; die Zykluszahlen 30/50 stimmen mit Stock überein.

**Nebenbefund, ungeklärt:** die Stock-HY310-DTS legt `usb-power-gpio` auf **PL5**, unser Knoten auf **PL3**. PL3 ist
laut U-Boot (`board/sunxi/board.c`, `h713_poweron_lines`) die VBUS-Freigabe der USB-A-Buchse und heißt im
Stock-GPIO-Plan `cam-usb-power-gpio` — zwei verschiedene Leitungen also, und unser Knoten führt beide auf PL3.
Deshalb ist der `gpios`-Unterknoten mit `0142` erst mal raus: U-Boot treibt PB5 und PL3 ohnehin selbst, und PL5
blind aus Linux zu treiben ist nichts, was man ungeprüft tut. **Zu klären, bevor es zurückkommt.**

### Stand

**Gebaut, am Gerät ungeprüft** (11.09.): Patches `0141` (Treiber) und `0142` (DTS) hängen in der Serie,
`CONFIG_HY310_BOARD_MGR=m` und `CONFIG_HWMON=y` stehen im defconfig, Baum `61d37af9` übersetzt ohne Warnung, das
Modul liegt in `modroot.61d37af9`. **Was am Gerät zu prüfen ist** (ein Stromzyklus): bindet der Treiber, kommt
`fan1_input` mit einer plausiblen Drehzahl (der Interrupt auf der PH-Bank ist noch nie belegt worden — bisher hat
nur PL4 je einen GPIO-Interrupt ausgelöst), und ist `temp1_input` plausibel. Erst wenn die NTC-Kurve gegen eine
zweite Messung steht, darf `thermal_shutdown=1` überhaupt erwogen werden.

## Der Aufhänger beim ersten eMMC-Boot — GELÖST 11.09. (Patches `0143`/`0144`)

Beim Test von board-mgr hing das Gerät: `systemd-random-seed` lief in den 10-Minuten-Timeout, RCU-Stall auf CPU 0.
Erst als getrandom-Problem gelesen und mit den Netz-Treibern erklärt — **das war falsch**. Der Blacklist-Test hat es
entschieden: mit `modprobe.blacklist=hy310_board_mgr` kam `crng init done` bei 6,03 s und der Boot lief durch, ohne
hing er. board-mgr in ein laufendes System nachgeladen tötete es binnen Sekunden.

**Die Ursache liegt im pinctrl, nicht im board-mgr.** Patch [`0004`](../mainline/patches/kernel/0004-pinctrl-sunxi-fix-irq-mux-and-graceful-resource.patch)
hatte `platform_get_irq(pdev, i)` zu `platform_get_irq(pdev, hw_bank)` gemacht. Die `interrupts`-Liste des
`pio`-Knotens ist aber **eine Zeile je IRQ-Bank** in `irq_bank_map`-Reihenfolge, nicht je Hardware-Bank. Der H713 hat
sieben IRQ-Bänke (`{0,1,2,3,5,6,7}` = PA PB PC PD PF PG PH) mit einer **Lücke bei PE**, das es auf diesem SoC nicht
gibt. Dadurch rutscht alles hinter der Lücke eine GIC-Leitung zu hoch: der PH-Handler landet auf SPI 61 (wo nie etwas
passiert), und auf PHs echter Leitung SPI 60 sitzt der Handler, der sich für PG hält.

Sobald board-mgr die EINT-Maske von PH17 aufhob, zog die PIO SPI 60 hoch, der „PG"-Handler las PG-Status = 0 und
löschte nichts. Die GIC ist ein *fasteoi*-Chip, `chained_irq_exit()` macht nur EOI — die Leitung blieb oben, CPU 0
nahm denselben Interrupt endlos. Unsichtbar, weil IRQ 230 nie erreicht wurde (Zähler 0) und verkettete
Elterninterrupts aus `/proc/interrupts` ausgeschlossen sind.

**Beleg:** im Hersteller-`vmlinux` holt `sunxi_pinctrl_init_with_variant` den Interrupt mit dem **Schleifenzähler**
und benutzt zwanzig Befehle später für die *Registeroffsets* sehr wohl die Hardware-Bank — der Hersteller trennt die
beiden Zahlen, `0004` hatte sie verschmolzen. Nie aufgefallen, weil die bisherigen GPIO-IRQs am `r_pio` liegen, das
keine Bank-Lücke hat.

**Behoben:** [`0143`](../mainline/patches/kernel/0143-pinctrl-sunxi-index-the-bank-interrupts-by-irq-bank-not-by-hardware-bank.patch)
(Rückbau auf die Mainline- und Hersteller-Semantik) und `0144` (die `interrupts`-Liste von neun auf die sieben
existierenden Leitungen gekürzt, SPI 54…60). **Reihenfolge zählt:** `0144` allein würde `-ENXIO` erzwingen. An
board-mgr selbst ändert sich nichts.

**Am Gerät abgenommen (11.09., Kaltstart):** 0 RCU-Stalls, `crng init done` bei 6,21 s, board-mgr geladen,
**`fan1_input` = 4740 RPM** bei 5438 Tacho-Interrupts — der Tacho zählt zum ersten Mal überhaupt. Dazu `uvcvideo`
automatisch geladen, `/dev/video2` da, eth0 oben, zram 472 MB.

**Nebenbefund, der bleibt:** unser eigener defconfig-Kommentar hatte kurzzeitig eine falsche getrandom-Begründung für
`USB_RTL8152=y`; sie ist korrigiert. Der Adapter bleibt eingebaut, aber aus dem sachlichen Grund (einzige
Netzanbindung), nicht wegen Entropie.

## Der NTC war ein Phantom — dieses Gerät hat keinen Fühler (geklärt 11.09., `0152`)

`temp1_input` meldete nacheinander 0 °C, 60 °C und 71 °C. Alle drei waren falsch, und ich habe für jede eine
plausibel klingende Erklärung gebaut, statt zu fragen, ob dort überhaupt eine Temperatur sein kann. Marcos Einwand
(„70 ° ist extrem unplausibel") hat das gestoppt.

**Der Hersteller sagt es selbst:** `ntc_num = 0`, übereinstimmend in beiden vom Gerät dekompilierten Gerätebäumen
(`hy310_factory.dts` Zeile 2696, `extracted/bootpkg-full.dts` 2975). **Der HY310 hat keinen NTC bestückt.**

Und `ntc_num` ist beim Hersteller bindend, nicht dekorativ:
- `ntc_read` (c05db9a0) führt die Messschleife über `ntc_num` und springt bei 0 sofort ans Ende — es wird **kein**
  Wandler gelesen.
- `avdtemp_read` (c05d9700) und `ledtemp_read` (c05d8ef4) prüfen `ntc_num` und geben bei 0 den Wert `0x63` = **99**
  zurück, den Vendor-Code für „kein Fühler".
- Die `ntc0`/`ntc1`-Unterknoten werden nie erreicht; ihr `enable = 1` ist eine Karteileiche aus der Vorlage.

**Unser Fehler stand die ganze Zeit im Quelltext** von [`0008`](../mainline/patches/kernel/0008-misc-add-hy310-board-mgr.patch):
`/* Tolerant parsing: stock DTS has ntc_num=0 but ntc0.enable=1. */` — die Null wurde für einen Widerspruch gehalten
und bewusst übergangen. Ein wohlmeinender Workaround, der das Gerät eine Temperatur aus einem offenen ADC-Eingang
erfinden ließ. [`0152`](../mainline/patches/kernel/0152-misc-hy310-board-mgr-ntc-num-ist-bindend-dieses-geraet-hat-keinen-fuehler.patch)
respektiert `ntc_num`: ist es 0, bleibt die Auswertung aus und `temp1_input` wird gar nicht angelegt.

**Jede Messung passt dazu** (`analyse/boot/ntc-gpadc-messung-20260911.txt`):

| Eingang | Befund | Bedeutung |
|---|---|---|
| GPADC ch1 | läuft mit steigender Abtastzeit auf Vollausschlag (TACQ 2 µs → 1442, 170 µs → 1777, 2,7 ms → 4044) | offener, hochohmiger Eingang; ein Fühler würde konvergieren |
| GPADC ch1 | folgt der CPU-Last (Ruhe 1445, Volllast 1514) und springt in **2 s** zurück | keine thermische Masse; das ist die CPU-Kernspannung über DVFS |
| GPADC ch0 | `CS_EN = 0x02`, `DATA[0] = 0` | gar nicht freigeschaltet |
| LRADC ch0/ch1 | beide 63 | dieser Block ist die **Tastatur** (`allwinner,keyboard_1350mv`, 6 Tasten); Vollausschlag = keine Taste |

**Der Überhitzungsschutz funktioniert trotzdem — über den Tacho.** Stock hat zwei getrennte Pfade: der NTC-Pfad
meldet bei Übertemperatur nur per Uevent, aber `fan_io_status_read` ruft bei anhaltendem **Lüfterstillstand**
`kernel_power_off()`. Deshalb schaltet ein Stock-Gerät ab, wenn man den Lüfter entfernt — auch ohne Fühler. Genau das
war Marcos Beleg, dass „der Schutz noch funktioniert": er beweist den **Tacho**, nicht den NTC. Und der Tacho ist auf
diesem Gerät nachgewiesen (PB5 aus → 0 RPM, wieder an → 4770 RPM).

**Bereinigt:** `0145` (Kanalwechsel auf GPADC ch1) ist gegenstandslos und liegt in
`patches/vorschlaege/ntc-phantom-20260911/`. [`0146`](../mainline/patches/kernel/0146-misc-hy310-board-mgr-den-ntc-rohwert-in-millivolt-umrechnen.patch)
bleibt — die Umrechnung `mv = raw * 439 / 1000` ist aus dem Vendor-Code belegt und wäre für eine Variante **mit**
Fühler richtig, und der `-ENODATA`-Pfad ist genau das, was jetzt greift. `0147` bleibt, aber sein Patchkopf sagt
jetzt, dass seine ursprüngliche Begründung widerlegt ist: die Streuung kam vom offenen Eingang, nicht vom
Kanalwechsel.

**Was das fürs Release heißt:** board-mgr liefert Drehzahl (bewiesen) und keine Temperatur (richtig so).
`thermal_shutdown` bleibt aus — es gibt nichts zu überwachen. Ein Gerät einer Variante **mit** NTC würde über
`ntc_num` von allein richtig laufen.

## Interne Kamera — läuft seit 11.09., noch nicht im eMMC-Kernel

Marco: „wir haben da auf jeden Fall noch ein Device". Stimmt: Realtek `0bda:5803` an USB-Port 1 wurde vom Bus
immer erkannt (Schnittstellenklasse `0e` = UVC), aber **kein Treiber war gebunden** — `uvcvideo` war nie gebaut.
Behoben mit drei Schaltern im defconfig (`MEDIA_CAMERA_SUPPORT`, `MEDIA_USB_SUPPORT`, `USB_VIDEO_CLASS=m`), Baum
`e88af5af`. Kein eigener Treiber, kein Patch, kein Firmware-Blob. Am Gerät live geladen und **ein Bild geholt**
(YUYV 640×480, die Wand vor dem Gerät, [`analyse/beamer-cam/foto-e313.png`](../analyse/beamer-cam/foto-e313.png)).
Werkzeuge und Macke (schwarz bis zur ersten Steuerungsschreibung) in [`analyse/beamer-cam/README.md`](../analyse/beamer-cam/README.md).
`/dev/video3` ist kein zweites Gerät, sondern der Metadatenknoten derselben Kamera.

**Offen:** Das Gerät bootet weiter den Kernel vom 10.09. (Marco hat neu gestartet; das Modul war nur per `insmod`
drin). Dauerhaft wird es erst mit dem nächsten Einspielen: FIT aus Baum `e88af5af` nach `hy310-boot` **und** Rootfs
mit `modroot.e88af5af` — dann lädt udev `uvcvideo` von selbst. Das ist derselbe Schritt, der auch den board-mgr aufs
Gerät bringt; ein Kaltstart zur Abnahme, dann `GUT-e88af5af`. Was die Kamera danach tun soll (Autofokus wie Stock,
[`94`](94-fokusmotor-endschalter.md)), ist eine eigene Aufgabe nach dem Release.

## WLAN und Bluetooth — nächster Block nach dem CE-Modul (Marco, 11.09.)

Nur der Ist-Stand, ohne Arbeit daran (11.09. 19:20, am Gerät nachgesehen): **nichts läuft.** Kein `aic8800`-Modul
in `modroot.GUT-bad2f16b` und keins am Gerät, keine Firmware in `/lib/firmware`, **`mmc1` hat 0 Karten** — der
WLAN-Chip meldet sich am SDIO nicht, also fehlt mindestens die Einschaltsequenz (`wlan_regon`, Patch
`aic8800-0002`). Bluetooth-Kern ist im Kernel, aber kein HCI-Gerät. Es gibt die Patchreihe
`mainline/patches/aic8800/` (sechs Patches: Mainline-Sunxi-Plattform, GPIO-Einschaltsequenz, SDIO-Takt,
Firmware-Blob-Guard, Regulatory-Domain) und einen Baum `mainline/build/aic8800-df4c783b…`. Die MACs liegen im Secure
Storage (`wifiBleDatas`). **Zu klären, wenn es losgeht:** ob `mmc1` im DTS einen `sdio`-Kindknoten samt
Einschalt-GPIO hat, ob der Baum überhaupt gebaut wurde, wo die Firmware herkommt (Stock-Abzug, `h713-extract`) und
wie die MACs aus `wifiBleDatas` an den Treiber kommen.

## Welcher Bau ist der Auslieferungskernel — geklärt 11.09.

Beim board-mgr-Test fiel auf, dass es **zwei verschiedene Kernel** gab und niemand sagen konnte, welcher ausgeliefert
wird. `build/build.sh` sagt „the shipping kernel is the defconfig alone"; das Gerät fuhr aber seit dem 10.09. einen
Kernel aus `KERNEL_CONFIG=netboot,zram` (das FIT auf `/boot` war byte-identisch mit `h713-kernel-netboot-zram.fit`).
Damit unterschied sich der Kernel, der läuft, vom Kernel, der ausgeliefert werden soll — in zwei Punkten, die beide
zählen: **zram fehlte** (das Release-Rootfs bringt die zram-Unit mit, [`107`](107-plan-rootfs.md) §4.2) und die
USB-Netz-Treiber waren Module statt eingebaut.

**Aufgelöst:** die vier zram-Optionen stehen jetzt im Board-defconfig, das Fragment `zram.config` ist entfernt, und
die beiden Netz-Treiber sind angeglichen. Damit gilt wieder, was `build.sh` sagt: **der Auslieferungskernel ist das
Board-defconfig allein**, `KERNEL_CONFIG=` ist ausschließlich für Fehlersuch-Bauten (`netboot` für NFS-Root,
`kasan`, `iommu`, …). Ein Bau ohne `KERNEL_CONFIG` ist ab jetzt das, was auf das Gerät gehört.

**Merken:** der reine defconfig-Kernel war bis zum 11.09. **nie auf dem Gerät gebootet**. Die „20/20 Kaltstarts" vom
10.09. liefen mit der Entwickler-Variante. Wer einen Bau abnimmt, muss prüfen, dass er den Kernel abnimmt, der auch
ausgeliefert wird — sonst nimmt man etwas anderes ab, als man ausliefert.

## WLAN vor dem Release: Werkzeuge und eine `wifi.env` (Marco, 12.09.)

**Der Treiber laeuft** (12.09., `analyse/boot/wlan-aic8800-messung-20260912.txt`): `wlan0` und `phy0` sind da,
die Firmware laedt — **und zwar die vom Geraet selbst**, nicht der SDK-Satz aus dem Legacy-Repo. Damit fallen
**zwei** der drei Gruende weg, aus denen WLAN aus dem Release-Rootfs geflogen war (`packages.txt` Zeile 70):
„auf diesem Kernel ungeprueft" ist erledigt, und „die aic8800-Firmware hat keine Lizenzangabe" ist entschaerft —
`h713-extract` kann den Satz aus dem Abzug des Nutzers ziehen, wie bei HDCP und der MIPS-Firmware.

**Zu tun:**

1. **Pakete ins Release-Rootfs**: `wpasupplicant`, `iw`, `wireless-regdb`, `rfkill`, `hostapd`, `dnsmasq`
   (`analyse/release/arbeit/rootfs/packages.txt`, Zeile 70 — die Begruendung dort ist ueberholt und gehoert
   ersetzt, nicht geloescht).
2. **`h713-extract` um den WLAN-Firmware-Satz erweitern — ERLEDIGT 12.09.** Neue Methode `extrahiere_wlan()`
   holt `vendor:/etc/firmware/aic8800d80/` nach `lib/firmware/aic8800_fw/SDIO/aic8800D80/`, Datei fuer Datei
   unveraendert; `--no-wlan` schaltet es ab. Der Zielpfad entspricht exakt dem `CONFIG_AIC_FW_PATH` des Treibers
   (radxas `fix-sdio-firmware-path.patch`) — weichen die beiden ab, laedt der Treiber stumm keine Firmware.
   Die 13 Referenzwerte stehen im **hy310**-Profil; fuer **l018** liegt kein vendor-Abzug vor, dort laufen die
   Dateien unreferenziert durch, ohne den Exit-Code zu kippen (`bewerte()` ueberspringt Artefakte ohne
   Referenzeintrag). Fehlt das Verzeichnis ganz, ist das **kein** Fehler — nicht jedes H713-Geraet hat den Chip.
   **Gegen den echten Abzug geprueft** (`re/device-dumps/stock-20260911/emmc-voll.img`): Exit 0, 13 Dateien,
   alle **byteidentisch** mit dem Satz, der am selben Tag `wlan0` hochgebracht hat, `referenz_stimmt: true`
   im Manifest.
3. **Eine `wifi.env`, die der Nutzer VOR dem Rootfs-Bau angeben kann** — Marcos Wunsch:
   `mode=ap|sta`, `ssid`, `password`, `channel`. **Vorgabe: AP** mit SSID `h713` und Passwort `magcubic`,
   **mit deutlichem Hinweis, dass der Nutzer das aendern soll**.

**Was es davon schon gibt** — und zwar gut gemacht, nur an der falschen Stelle:
[`mainline/tools/rootfs/hotspot.conf.example`](../mainline/tools/rootfs/hotspot.conf.example) gehoert zu
**cstengers** Rootfs-Bau (`mainline/tools/rootfs/`), nicht zu unserem Release-Rootfs
(`analyse/release/arbeit/rootfs/`). Es kann SSID, Passphrase, Kanal, AP-Adresse, DHCP-Bereich und **Band**
(2,4 GHz HT40 oder 5 GHz VHT80, mit am Geraet gemessenen Durchsatzwerten: 4,85/7,65 MB/s gegen
13,25/14,41 MB/s), baut hostapd + dnsmasq ein und liegt per `local/` ausserhalb von Git, damit Zugangsdaten
nicht im Repo landen.

**Was dort fehlt** und fuer Marcos Wunsch dazu muss: ein `mode=ap|sta` (heute ist es reiner AP; ohne die Datei
gibt es gar keinen Hotspot), STA-Zugangsdaten fuer `wpa_supplicant`, und **Vorgabewerte**, damit ohne Datei
trotzdem ein AP mit `h713`/`magcubic` entsteht. Der Hinweis auf `regulatory.db` aus der Beispieldatei gilt
weiter: sie ist auf diesen Abbildern nicht installiert, der Stapel laeuft unter freizuegigen Regeln.

**Offen aus der Messung:** die Bluetooth-Firmware (`fmacfwbt_*`) liegt **nicht** im Stock-Abzug, nur im
SDK-Satz. Fuer BT waere die Lizenzfrage also weiter offen — WLAN allein ist davon nicht betroffen.

**Umgesetzt 12.09. (A.1, nicht am Geraet geprueft):**

- **Pakete** drin (`packages.txt`), Begruendung des alten Ausschlusses ersetzt. `dnsmasq-base` statt `dnsmasq`.
- **Entwurfsentscheidung: `wifi.env` wird auf dem Geraet ausgewertet**, nicht beim Bau. cstenger backt
  `hostapd.conf` ein -- dann aendert nur, wer neu baut. Unser Release ist eine Abbild-Datei; die meisten Nutzer
  bauen nie. Also `/etc/h713/wifi.env` + `h713-wifi.service` (oneshot, `up`/`down`/`status`/`check`), beim
  Bau `--wifi-env DATEI` oder `rootfs/wifi.env`, sonst die Vorgabe. **Dieselbe Pruefung** laeuft beim Bau und
  auf dem Geraet (`h713-wifi check`); die Datei wird geparst, nie gesourct. `mode=off` laedt das Modul gar nicht
  erst -- der Chip bleibt stromlos (Befund 1 der Messung).
- **`country=`** geht als `default_ccode` an `aic8800_fdrv` (Patch `aic8800-0006`); weicht der geladene Wert ab,
  laedt der Dienst das Modul neu. Vorgabe `DE` -- eine falsche echte Domaene ist weniger schlimm als `00`.
- **`aicwf_dbg_level=0x1`** per modprobe.d (cstengers Befund: ab Werk 0x40F flutet die Konsole).
- **Paket-Units `hostapd`/`wpa_supplicant` maskiert** -- ein Besitzer fuer `wlan0`.
- **Loch geschlossen:** die aic8800-Module lagen nur in `build/out/modules/`, der Installer kopierte nur den
  modroot. Jetzt `extra/` + vermagic-Pruefung. Ohne das haette das Abbild Dienst und Pakete gehabt, aber
  keinen Treiber.
- **`h713-cam`** (`userspace/`), aus den drei Skripten in `analyse/beamer-cam/`; Installer-Schritt 5.

## Die Kamerawerkzeuge gehören ins Rootfs (Marco, 11.09. — nachgetragen 12.09.)

Marcos Auftrag lautete vollständig: *„das mit der camera ist jetzt fest, das muss dann auch in dem rootfs
irgendwie verfügbar gemacht werden — treiber brauchen wir ja offensichtlich keine? aber auch in dem projekt
hinterlegt werden."* **Zwei von drei Teilen sind erledigt, der Rootfs-Teil ist durchgerutscht** — er fehlte
am 12.09. auch in der mündlichen Rootfs-Liste.

- **Treiber: erledigt.** `CONFIG_USB_VIDEO_CLASS=m` plus `MEDIA_CAMERA_SUPPORT`/`MEDIA_USB_SUPPORT` im
  defconfig. Marco lag richtig — ein eigener Treiber war nie nötig, `uvcvideo` war schlicht nie gebaut.
  Das Modul liegt damit im Modulbaum, den `install-projekt.sh` ohnehin einspielt; udev lädt es von selbst.
- **Im Projekt hinterlegt: erledigt.** `analyse/beamer-cam/` mit `camprobe.py`, `camset.py`, `camgrab.py`
  und README.
- **Im Rootfs: offen.** Die drei Werkzeuge liegen unter `analyse/` — das ist Analyse, nicht Auslieferung. Auf
  dem Gerät ist damit keine Möglichkeit, die Kamera anzusehen.

**Zu tun, klein:** die drei Skripte nach `userspace/` holen (Name `h713-cam`, ein Programm mit Unterbefehlen
`probe` / `set` / `grab` — derselbe Zuschnitt wie `h713-focus`) und in `install-projekt.sh` als eigenen Schritt
einspielen. **Keine zusätzlichen Pakete nötig:** die Werkzeuge laufen ausdrücklich mit blankem `python3`, ohne
`v4l2-ctl` und ohne `ffmpeg` (`analyse/beamer-cam/README.md`). Das ist der Grund, warum `v4l-utils` weiter
draußen bleiben kann.

**Mitzunehmen:** die Macke aus dem README — das Bild bleibt schwarz bis zur ersten Steuerungsschreibung.
Wer `grab` ohne vorheriges `set` aufruft, bekommt ein schwarzes Bild und hält es für einen Fehler.

## Abbild v0.8 — gebaut und am Gerät abgenommen (12.09., 10:30)

Alles, was seit v0.7 dazukam, in einem Abbild: board-mgr (`0141`–`0152`), Kamera (`uvcvideo`), WLAN (`0155`,
aic8800, Pakete, `h713-wifi`), Fokusmotor (`0153`–`0157`), kein Debug (`0158`, defconfig, U-Boot `0033`),
`h713-focus`, `h713-cam`.

| Baustein | Stand |
|---|---|
| Kernel | Baum `f7dd06d0`, **defconfig allein** (kein Fragment), Serie bis `0158`. FIT `tftp/h713-kernel.fit.f7dd06d0` (7 618 576 B). 34 Module → `modroot.f7dd06d0` |
| aic8800 | gegen denselben Baum gebaut, `fdrv` 842 KB (64 KB kleiner als mit debugfs) |
| U-Boot | v7 = `4091ea68c06` (`0033`), `hy310_qz713_v3_1_defconfig`, `mainline/build/uboot-v7-release`. Geteilt nach `tftp/spl-release.bin` + `uboot-proper-release.bin`; **v6 daneben als `.v6`** |
| Rootfs | 241 MiB, 171 Pakete, 35 Abnahmen grün, `out/`; v0.7 gesichert in `out.v07/` |
| Extrakt | `r2-extract/out-hy310-20260912`: 43 Dateien, alle referenzgleich (erster Extrakt **mit** den 13 WLAN-Dateien) |
| Abbild | `r0-fel/out/hy713-v0.8.*`: drei Teile, 1159 MiB, 43 + 1 Platzhalter, Selbsttest **ALLES GRÜN** |

**Drei Dinge, die dabei erst auffielen und geschlossen wurden:**

1. **Die aic8800-Module erreichten das Rootfs nicht.** `build.sh aic8800` legt sie nach `build/out/modules/`, der
   Installer kopierte nur den `modroot`. Jetzt `install-projekt.sh` Schritt 2: `bsp`+`fdrv` nach `extra/`,
   vermagic-Prüfung gegen ein In-Tree-Modul, dann depmod. `btlpm` bleibt draußen (keine BT-Firmware).
2. **Die WLAN-Firmware hatte keine Platzhalter im Abbild.** `hy310-mkimage` kannte 30 Dateien; die 13 aus
   `extrahiere_wlan()` fehlten. Jetzt 43. **Neu im Installer: eine optionale Gruppe** (`OPTIONALE_GRUPPEN`,
   Präfix `lib/firmware/aic8800_fw/`) — fehlt der *ganze* Satz im Abzug, hat das Gerät keinen Chip, die
   Platzhalter bleiben genullt; fehlt nur ein Teil, Abbruch wie sonst. `h713-wifi` prüft deshalb nicht das
   Verzeichnis, sondern liest in `fmacfw_*.bin` hinein (genullt → klare Meldung statt Treiberladen).
3. **`regulatory.db` zeigte auf die Debian-signierte Kopie**, unser Kernel kennt nur `sforshee`/`wens` und verlangt
   eine Signatur → cfg80211 hätte sie verworfen. `build-rootfs.sh` 4j biegt die Alternative auf `-upstream`, mit
   Abnahmezeile. Für den self-managed aic8800 ohne Folgen; richtig ist es trotzdem (cstengers Befund).

**Nebenbei repariert:** `mkimage-selbsttest.py` hatte die FIT-Länge `7987476` fest verdrahtet — jeder neue Kernel
hätte „beschädigt" gemeldet. Jetzt Kennung + FDT-Gesamtlänge aus dem Kopf, dazu Bytevergleich mit `tmp/boot-baum`.

**Gerätephase — was schiefging, bevor es lief:**
- Nach dem ersten Stromzyklus stand das Gerät still in **Bereitschaft**: das Gate ist am Dev-Gerät **aktiv**
  (Marco, 11.09.), `00-STATUS` sagte „aus" und war überholt. Grund, warum es aktiv ist: die U-Boot-Umgebung ist
  seit v0.7 leer (`bad CRC, using default environment`) → eingebaute Vorgabe `h713_gate=1`. **Das heißt auch:** die
  neuen Vorgaben aus U-Boot `0033` gelten sofort, ohne `env default`.
- **Falsches `sunxi-fel`.** `mainline/build/fel/sunxi-fel` ist byteidentisch mit `r0-fel/sunxi-fel.vor-tuer-patch`
  — das **ungepatchte** Werkzeug vom 31.08. Der SPL lief, kehrte nach FEL zurück, U-Boot proper kam nie. Die
  S44-Falltür braucht `mainline/external/sunxi-tools/sunxi-fel` (10.09.). Mit dem lief der Installer durch.
- **Steckdose bei gestecktem A-auf-A-Kabel** schaltet, startet aber nichts neu (USB-VBUS speist parallel). Stand
  in der v0.7-Notiz, ich habe es trotzdem getan. Marco hat das Kabel gezogen und selbst neu gestartet.

**Abnahme am Gerät:** [`analyse/boot/abnahme-v08-20260912.txt`](../analyse/boot/abnahme-v08-20260912.txt).
Kurz: U-Boot `g4091ea68c06f`, `cmdline` mit `loglevel=4` ohne `earlycon`, kein `/sys/kernel/debug`, Konsole beim
Start still, Login < 60 s; WLAN-AP `h713` mit `country DE` auf dem self-managed phy, Firmware aus den
Platzhaltern; board-mgr 4770 rpm; Motor `raw=1 step=0`, kein Homing; Kamera erkannt; `h713-tv` läuft; keine
gescheiterte Unit. **Neu gefunden:** `h713_ce_test` lädt per DT-Match automatisch (Entscheidung Marco).

## Die U-Boot-Umgebung im Abbild — „bad CRC" bei jedem Start (Marco, 12.09.)

Nach dem Einspielen von v0.8 meldete U-Boot bei jedem Start zweimal `Loading Environment from MMC... *** Warning -
bad CRC, using default environment`. Marco: *„das geht nicht, wie kann das bitte sein."* Zwei Fehler, die sich
gegenseitig verdeckt haben:

1. **Das Abbild lieferte die Umgebung als Nullen aus.** `hy310-mkimage` schrieb Teil B ab LBA 14336 mit einem
   Nullblock für `hy310-env` — „U-Boot legt sie beim ersten saveenv an". Folge: jeder Start läuft auf der
   eingebauten Vorgabe, und **jede Installation löscht die gespeicherte Umgebung.** Deshalb war das Gate am
   Dev-Gerät seit v0.7 „plötzlich" aktiv: die Vorgabe ist `h713_gate=1`, Marcos gespeichertes `0` war weg.
   (Die Doppelmeldung ist Upstream-Logik in `env_get_location`: für MMC-Boot liefert Priorität 0 und 1 dasselbe
   `ENVL_MMC`, also zwei Versuche. Nicht angefasst — mit gültiger Umgebung ist es ein einziges `OK`.)
2. **`fw_env.config` im Rootfs zeigte auf `0x500000`** (LBA 10240 — im U-Boot-Fenster, U-Boot liest dort nie),
   U-Boot hat `CONFIG_ENV_OFFSET=0x700000` (LBA 14336, Layout v3 §2.1). `fw_setenv` aus Linux hätte ins Leere
   geschrieben — und `fw_printenv` war gar nicht installiert. Die Abnahme in `build-rootfs.sh` hatte den falschen
   Wert festgeschrieben.

**Umgesetzt (v0.9):**

- **Das Abbild bringt eine gültige Umgebung mit:** `tftp/hy310-env-release.bin`, 64 KiB mit CRC, erzeugt aus
  demselben U-Boot-Bau (`make u-boot-initial-env` → Dubletten raus → `mkenvimage -s 0x10000`). Immer die
  Vorgabe des U-Boot, das mitkommt; `h713_gate=1` steht damit ausdrücklich drin. `hy310-mkimage --env`,
  Prüfung von Größe, CRC und `h713_gate`, Eintrag `bausteine.env` in der Tabelle. Selbsttest angepasst.
  **Am Gerät bewiesen** vor dem Bau: per `dd` auf `mmcblk0p4`, Reboot → `Loading Environment from MMC... OK`,
  `gate: warm start`.
- **Bewusste Folge:** die Umgebung ist ab Werk *gespeichert*, nicht mehr *eingebaut*. Ändert ein späteres U-Boot
  seine Vorgaben, gewinnt die gespeicherte — normales U-Boot-Verhalten und genau der Grund für eine gültige
  Umgebung: ein absichtlicher Zustand statt ein zufälliger.
- **Der Installer unterscheidet Stock und unser Layout** (Marco: *„sonst macht das uboot env saven kein Sinn"*).
  Entscheidend ist die GPT (`ist_unser_geraet`, hy310-*-Namen), nicht ein CRC-Zufallstreffer:
  - **Stock → unser Abbild:** bei LBA 14336 liegt Android. Nichts wird gesichert, nichts übernommen, nichts
    erwähnt. Das Abbild bringt seine Vorgabe mit.
  - **Unser Layout → unser Abbild:** die alte Umgebung wird als `uboot-env.bin` in den Abzug gesichert (im
    Manifest, mit Einträgen und Absichts-Schlüsseln). Dann wird **die Vorgabe des neuen U-Boot geschrieben, und
    nur `h713_gate` und `h713_boot` werden aus der alten übernommen** (`ENV_UEBERNEHMEN`), in der Arbeitskopie
    von Teil B, mit neu gerechnetem CRC und Rücklesen. `--env-neu` schaltet die Übernahme ab.
  - **Warum genau so:** *alles behalten* hätte heute v0.7s `bootargs_base` mit `earlycon` überleben lassen, die
    neuen Vorgaben aus `0033` wären still nie angekommen. *Alles verwerfen* zwingt jeden, der das Gate für die
    Werkbank abgeschaltet oder `h713_boot=net` gesetzt hat, es nach jedem Upgrade neu zu tun. Bootargs,
    bootcmd und Pfade sind Sache des U-Boot; Gate und Bootquelle sind Sache des Menschen.
  - Ein älteres Abbild ohne `bausteine.env` bekommt nichts erfunden: Meldung, keine Übernahme.
- **Rootfs:** `fw_env.config` → `/dev/mmcblk0 0x700000 0x10000` mit Herleitung im Kommentar,
  `libubootenv-tool` (fw_printenv/fw_setenv) in `packages.txt`, Abnahme prüft Offset und Werkzeug.

**Am Gerät bestätigt (v0.9, 12.09. mittags):** `Loading Environment from MMC... OK` einmal, aus dem Abbild;
`fw_printenv h713_gate h713_boot bootargs_base` liest die echte Umgebung; Env-Partition byteidentisch mit
`hy310-env-release.bin`; `cmdline` mit `loglevel=4`; WLAN-AP steht; keine gescheiterte Unit. Abzug in
`hy310-sicherung-20260912-v09/`.

**Noch nicht am Gerät geprüft:** die Sicherung der alten Umgebung und die Übernahme von `h713_gate`/`h713_boot`.
Beim v0.9-Lauf fehlte dem dritten `abzug_klein`-Aufruf (normaler Installationsweg, Zeile 1141) der
Layout-Parameter — nur die zwei anderen waren angepasst. Behoben nach dem Lauf; offline gegen eine Kopie von
Teil B in allen drei Fällen (unser Layout / `--env-neu` / Stock) richtig. Der Gerätebeweis kommt mit der
nächsten Installation: vorher `fw_setenv h713_boot net`, nachher muss `fw_printenv h713_boot` wieder `net` sagen.

## Kein Debug im Release — und was der MIPS-elog damit zu tun hat (Marco, 12.09.)

Marcos Vorgabe: *„elog war nicht nur der buffer gemeint, auch die aktuell — wenn überhaupt — gesetzte
Intensität. Wir wollen kein Debug in Release."* **Aufgeschrieben, nichts davon geändert.**

### Was tatsächlich an ist — nachgesehen am 12.09.

| Befund | wo | Einschätzung |
|---|---|---|
| **`/sys/kernel/debug/cpu_comm/call`** (0600) nimmt beliebige RPCs an die Anzeige-Firmware entgegen, dazu `watch` | `cpu_comm_api.c:1123–1128` | **das Schwerste.** Ein Steuerkanal in die Firmware, der nur für die Fehlersuche gedacht war |
| **`CONFIG_DEBUG_FS=y`**, `CONFIG_DYNAMIC_DEBUG=y` | Release-defconfig | trägt den Punkt darüber überhaupt erst |
| **elog-Auszug beim Booten**, rund 20 Zeilen `pr_info`, dazu `MIPS elog BEFORE/AFTER: mode=… en2=… wp2=…` | `cpu_comm_dev.c:1479, 1677, 1708, 1737` | die BEFORE/AFTER-Zeilen sind **Reste eines zurückgenommenen Umbaus** und sagen niemandem etwas |
| **`earlycon`**, kein `loglevel=`, kein `quiet`, dazu `console=tty0` | `sun50i-h713-hy200-qz713df-a1.dts` | der vollständige Kernelmitschnitt läuft **über das projizierte Bild** |
| **Die elog-Intensität: `ELOG_LEVEL` in `display_cfg.xml`** (Marco, 12.09.: „wird an U-Boot übergeben") | [`63`](63-mips-elog.md) | Drei Bytes in der Display-Konfiguration bei `0x4be01000`, die U-Boot **vor** dem Loslassen des Coprozessors schreibt — aber nur, wenn `h713_disp init … elog=<0-5>` gesagt wird. **Der Release-`bootcmd` sagt es nicht** (`hy310.env:40`, `hy310_qz713_v3_1_defconfig:67`), also bleibt die Vorgabe der Firmware: **1 = nur `E/`**. Zur Laufzeit spiegelt die Firmware den Wert nach `0x4b48bd9c`; dort haben wir bei Messungen Stufe 5 gesetzt — von Hand, nie aus dem Treiber. **Im Auslieferungszustand ist die Intensität also schon richtig.** Bleibt: sicherstellen, dass es so bleibt (kein `elog=` in einen Release-`bootcmd`; `elog=3` beim Init verhindert ohnehin die MIPS-Bereitschaft, doku/67) |

### Umgesetzt am 12.09., abends (Marco: „bring mir 3 patches")

- **defconfig:** `# CONFIG_DEBUG_FS is not set`, `# CONFIG_DYNAMIC_DEBUG is not set`, mit Begründung in der Datei.
  Kein aktives Symbol selektiert `DEBUG_FS` (gegen `lib/Kconfig.debug` und alle `select DEBUG_FS` geprüft), die
  Abschaltung hält also durch `olddefconfig`. Entwickler-Fragment `board/debug.config` schaltet beides zurück.
- **U-Boot `0033`** (`uboot-h713/`, Commit `4091ea68c06` im Fork): `bootargs_base` ohne `earlycon`; `boot_emmc`
  hängt `loglevel=4` an, `boot_net` hängt `earlycon` an. **Achtung:** das ist der eingebaute Vorgabewert. Das
  Dev-Gerät bootet mit gespeicherter Env weiter mit dem alten `bootargs_base`, bis `env default -a; saveenv`.
  Ein ausgeliefertes Gerät bekommt die Env frisch aus dem Abbild.
- **Kernel `0158`:** Rückfall-`bootargs` im Board-DTS gleichgezogen (`earlycon` → `loglevel=4`). Diese Zeile
  greift nur, wenn U-Boot keine bootargs setzt; sie trägt weiter `root=/dev/mmcblk0p26` aus dem Android-Layout —
  unverändert gelassen, weil ein funktionierender Rückfall eine eigene Entscheidung wäre.
- **cpu_comm bleibt unangetastet** (Marco: „ich will nicht, dass du cpu_comm patchst"). Die `BEFORE/AFTER`-Zeilen
  und der Mode-2-Rest stehen weiter im Treiber; mit `loglevel=4` bleiben sie im Kernelring statt auf der Konsole,
  und mit `DEBUG_FS=n` ist die `call`-Tür ohne Treiberänderung zu.

### Zu tun (Rest)

1. ~~Den Firmware-Vorgabewert feststellen~~ — **geklärt, steht in [`63`](63-mips-elog.md): Boot-Vorgabe 1 = nur
   Fehler.** Der Release-Bootpfad setzt nichts anderes. Nur im Auge behalten, dass kein `elog=` in einen
   Release-`bootcmd` rutscht.
2. ~~`call`/`watch` hinter einen Schalter~~ — erledigt über `DEBUG_FS=n`, siehe oben.
3. ~~BEFORE/AFTER-Zeilen entfernen~~ — **bleibt**, Marcos Entscheidung (cpu_comm nicht anfassen).
4. ~~`earlycon` raus, `loglevel=4` rein~~ — erledigt, U-Boot `0033` + Kernel `0158`. `console=tty0` steht nur im
   DTS-Rückfall, nicht in der U-Boot-Env — der Release-Pfad hatte es nie.
5. **Erst danach** die alte Frage: reichen 20 Zeilen? Der Ringpuffer liegt bei `0x4B272D9C` und ist rund **100 KB**
   groß, wir lesen einen Bruchteil. Das ist unabhängig von Mode 2 und die billigere Hälfte. Falls mehr gebraucht
   wird, gehört es in eine Datei (debugfs, lesend), nicht in den Kernelring.

**Warum das elog trotzdem bleiben muss:** es ist unser einziges Fenster in die MIPS-Firmware — jede HDCP-, Panel-
und Geometriefrage wurde daran entschieden ([`91`](91-plan-drei-punkte.md),
[`S9`](nachtlog/S9-re-tfd-vincap-icsc.md), [`S11`](nachtlog/S11-gruenstich-ursache-und-callback-slots.md)).
`legacy/tools/dump_mips_elog.py` liest denselben Puffer von außen. Es geht um die **Lautstärke im Auslieferungs-
zustand**, nicht darum, das Fenster zuzumauern.

## Infrastruktur

- **Netzstart bleibt als Rückfall.** Das Gerät bootet seit dem 10.09. vollständig von der eMMC; TFTP und NFS auf
  diesem Rechner (192.168.8.123, Wurzel `tftp/` bzw. `/srv/h713-rootfs`) laufen weiter, damit ein kaputtes Rootfs
  nicht das Ende ist. **Prüfungen ab jetzt vom eMMC**, nur das ist der Release-Zustand.
- **Keine gepufferte Uhr** — RTC startet 1970, TLS scheitert bis `date -u -s …`.
- **Kernelbäume:** `mainline/build/` hält nur die GUT-Bäume `a3097ce7`, `e2f6be7c`, `d5fd82a7`, `bad2f16b` (ausgedünnt 09.09., 12 GB);
  `build.sh` legt je Serienstand einen neuen Baum an → nach jeder Phase wieder ausdünnen (jeder Stand ist aus `patches-snapshots/` in 2,5 min
  neu baubar). Abgelöste Abbilder liegen in `tftp/alt/` und `mainline/build/modroot-alt/`.
- **Zweitablage:** `re/` (IDA-Datenbanken, Captures) existiert einmal, auf dieser NVMe.
- **Fokusmotor** ([`94`](94-fokusmotor-endschalter.md)): **die Stilllegung beruhte auf einem Fehler von uns**
  (12.09.). PH14 ist kein Endschalter, sondern ein **Bereichswächter** (HIGH = im Fahrbereich, `active_level = 1`);
  unser Patch `0111` hat einen Pull-down **erzwungen**, den der Herstellertreiber nie setzt — damit meldete der Pin
  an jeder Position „außerhalb". `0153` fasst das Pad nicht mehr an, `0154` zeigt den Rohpegel.
  **Gerätetest bestanden am 12.09.**: `raw` kippt beim Abwärtsfahren bei step −206 von 1 auf 0, der Treiber kehrt
  um und merkt `edge_dn` — der Geber lebt. `0156` (homing standardmäßig aus) und `0157` (Knoten aktiv) ziehen das
  nach; bedient wird mit [`userspace/h713-focus`](../userspace/h713-focus/README.md).

## Gegenüber cstenger

- PR #1 (USB-Host) und PR #2 (Display-Pfad) an `cstenger/u-boot` offen seit 31.08., keine Reaktion.
- **Crypto Engine: sein Befund ist bestätigt, sein Blocker bei uns gelöst** (11.09., Zweig `wip/crypto-ce-tooling`,
  Commit `bb44dc8`). Er hat `sun8i-ce` am Gerät durchgemessen und richtig abgeschaltet. Sein einziger offener Punkt —
  „descriptor-level RE of the vendor `allwinner,sunxi-ce` driver (source unavailable)" — ist in
  [`S49`](nachtlog/S49-hdcp14-schluesselpfad.md) aus **OP-TEE** rekonstruiert statt aus dem Vendor-Kerneltreiber, und
  sein Fehlerbild `address invalid` passt exakt zu den 5-Byte-Adressfeldern, die S49 dort gefunden hat. Umgekehrt
  sparen uns seine Messungen Stromzyklen: zweiter Interrupt (SPI 74) nötig und wirksam, NS-Kanal aus Linux
  erreichbar, keine TRNG. Einordnung und Konsequenzen in [`114`](114-plan-crypto-engine.md) §9.
- Noch nicht zurückgemeldet: Composition-Befund (`89-composition-block.md`), D1-CCU-Tabelle Port 1, fehlendes
  SIDDQ-Löschen, Doorbell im MIPS-Sendepfad des öffentlichen Repos, `Archived/`-Falle in
  `well0nez/allwinner-h713-linux`.
- Unsere Kernel-Serie (`0091`–`0140`, HDMI-Audio, Einschalttaste, EINT-Mux-Fix) ist ihm nicht angeboten; sein Baum `h713-display-video-path` läuft
  parallel ([`80`](80-vergleich-baeume.md)).

## Vorgekommen, nicht offen

- **4K-Rückkehr-Hänger, 08.09. 22:15** (einmal, Kernel `1f3614a1`): nach 4096×2160 am Zuspieler blieb die Firmware bei 720p30 stehen,
  keine `SignalChange`-Rückrufe, Bild erst nach HDMI-Neuverbinden plus Modewechsel zurück. Mit `d5fd82a7` in drei Sequenzen nicht
  reproduzierbar (22:25). Beleg und Werkzeuge: [`nachtlog/BUG-4k-rueckkehr-20260908.md`](nachtlog/BUG-4k-rueckkehr-20260908.md).
  EDID bleibt Stock (Marco, proprietär).
