# Alle offenen Punkte auf einer Seite

Angelegt 12.09.2026, weil es das nicht gab. `60-offen.md` ist 850 Zeilen, in denen Erledigtes und Offenes
durcheinanderliegen; `00-STATUS.md` §5 ist ein Absatz Fließtext. **Hier steht nur, was noch zu tun ist** — eine
Zeile je Punkt, mit Zeiger auf die Begründung. Was hier fehlt, ist erledigt.

**Pflege:** Wer einen Punkt abschließt, streicht ihn hier und schreibt die Begründung dort, wo sie hingehört.
Diese Datei sammelt keine Geschichte.

---

## A — vor dem Release v0.1

### A.1 Rootfs — am Gerät (v0.8, 12.09.)

| | Was | wo es steht |
|---|---|---|
| ☑ | **WLAN-Pakete** in `packages.txt`: `wpasupplicant`, `hostapd`, `dnsmasq-base` (nicht `dnsmasq`: kein Dienst auf Port 53), `iw`, `rfkill`, `wireless-regdb`. `bluez` bleibt draußen, Begründung ersetzt | `rootfs/packages.txt` |
| ☑ | **`wifi.env`** — auf dem **Gerät** ausgewertet, nicht beim Bau: `/etc/h713/wifi.env` + `h713-wifi.service`. `mode=ap\|sta\|off`, `ssid`, `password`, `band`, `channel`, `country`, AP-Adressen. Vorgabe AP `h713`/`magcubic` mit Warnblock. Beim Bau: `--wifi-env DATEI` oder `rootfs/wifi.env`, geprüft mit demselben Skript (`h713-wifi check`), 17 Testfälle | `overlay/etc/h713/wifi.env`, `overlay/usr/local/sbin/h713-wifi` |
| ☑ | **`h713-cam`**: ein Skript, `probe`/`controls`/`get`/`set`/`grab` (PNG ohne PIL), sucht den Knoten statt zu raten. Am Host gegen eine C920 (`uvcvideo`) durchgeprüft | [`userspace/h713-cam`](../userspace/h713-cam/README.md) |
| ☑ | **Nachgefunden und geschlossen:** die aic8800-Module lagen in `build/out/modules/`, in keinem `modroot` — der Installer kopiert nur den modroot. Jetzt Schritt 2: `bsp`+`fdrv` nach `extra/`, vermagic-Prüfung, dann depmod | `rootfs/install-projekt.sh` |
| ☑ | **Am Gerät (v0.8):** `h713-wifi status` → AP `h713` steht, hostapd + dnsmasq, 192.168.4.1, `country DE: DFS-ETSI` auf dem self-managed phy; Firmware aus den Platzhaltern geladen. `h713-cam grab` läuft (3,4 s), Bild dunkel weil nichts an der Wand | `analyse/boot/abnahme-v08-20260912.txt` |
| ☐ | **Bootkette ändert sich zur nächsten Auslieferung**: bis v0.10 steckte ein bl31 vom 10.09. mit eingeschalteten Zusicherungen im Abbild (make hat es nie ersetzt, 12.09. gefunden). Der Auslieferungsstand baut jetzt sauber (45 164 statt 49 260 Byte). **Am Gerät neu abnehmen** — gehört in P6. Dazu seit 12.09. der wieder scharfe Notaus bei Lüfterstillstand (`0159`, Abbild v0.12): einmal mit abgeklemmtem Lüfter auslösen lassen und den Weg zurück prüfen | [`116`](116-plan-release-repo.md) §4a P3.9 |
| ☑ | **AP und Station am 12.09. bewiesen**: Rechner am AP (−50 dBm, 5,7 MB/s, DHCP, SSH), danach `mode=sta` gegen ein echtes Netz (`192.168.8.131`, Internet über `wlan0`). Latenzspitzen am AP als bekannter Mangel notiert | `analyse/boot/p6-abnahme-20260912.txt` |

**Ungeprüfte Annahmen, die der Gerätetest klären muss:** hostapd-Stanza ist cstengers gemessene (2,4 HT40 / 5 VHT80), aber mit `utf8_ssid=1` und HT40±-Wahl nach Kanal dazu; `dnsmasq --no-resolv --address=/h713/…` antwortet auf `h713`, sonst REFUSED — ob Android damit „kein Internet" meldet und das Netz fallen lässt, zeigt nur der Versuch; STA-Modus mit `dhclient -nw` neben `eth0`-DHCP → zwei Default-Routen, Metrik ungeklärt.

### A.2 Abbild und Installer

| | Was | wo es steht |
|---|---|---|
| ☑ | **v0.9 am Gerät:** `Loading Environment from MMC... OK` einmal, `fw_printenv` liest die Umgebung, `fw_env.config` auf `0x700000`, Env-Partition byteidentisch mit dem Abbild | [`60`](60-offen.md) §Die U-Boot-Umgebung im Abbild |
| ☑ | **Env-Übernahme bewiesen** (12.09.): vorher `h713_gate=0`, `h713_boot=net` gesetzt, Installer übernahm beide ins Abbild, eMMC trug sie mit gültiger CRC, Gerät startete ohne Tastendruck | `analyse/boot/p6-abnahme-20260912.txt` |
| ☐ | **Netzwerkwerkzeuge ins Rootfs** (P6, 12.09.): im Abbild fehlen `ping`, `curl`, `wget`, `nc` — die Erreichbarkeitsprüfung musste ich mir in Python zusammenbauen. Mindestens `iputils-ping`, dazu abwägen: `curl` (oder `wget`), `netcat-openbsd`, `ethtool`, `tcpdump`? Jedes Paket kostet Platz im 228-MiB-Rootfs und Angriffsfläche — Liste in `rootfs/packages.txt` mit Begründung je Zeile, so wie die anderen | [`107`](107-plan-rootfs.md) §2 |
| ☐ | **Beta-Warnung** in README, Release-Text **und** Installer-Ausgabe: Vollabzug oder passendes Firmware-Image sind Pflicht, sonst ist ein Fehlschlag nicht heilbar | [`110`](110-plan-installationsweg.md) §9 |
| ☐ | **Alle Werkzeuge ins Englische** (entschieden Marco, 13.09.): Schalter, Meldungen, Rückfragen und Kommentare in `hy310-install`, `h713-extract`, `hy310-mkimage`, `h713-tv` (inkl. `ctl`-Antworten `ok`/`fehler`), `h713-focus`, `h713-cam`, `h713-wifi`, `h713-fel`, `build-all`, `repo-skelett`. Die Doku ist schon englisch und zeigt heute deutsche Ausgaben (z. B. das Installer-Transkript in FLASHING). Vorgehen: deutsche Schalter als Aliasse **behalten**, damit unsere Skripte und die Belege im Journal gültig bleiben; neue englische Namen werden Standard. Nach der Umstellung das Transkript in FLASHING neu aufnehmen (`H713_AUFNAHME`) | [`117`](117-plan-p5-doku.md), ROADMAP „English tooling" |
| ☐ | **Mitgelieferte GPT gegen die errechnete prüfen.** `sunxi_gpt.fex` und `sys_partition.fex` widersprechen sich bei `media_data` und allem dahinter — beide lesen, vergleichen, Abweichung melden | [`60`](60-offen.md) Punkt 12 |
| ☑ | **Windows: v0.1 Linux-only**, in der Anleitung als *ungetestet, keine Gewähr, auf Rückmeldungen angewiesen* (Marco, 12.09.). `sunxi-fel.exe` später nach Rückmeldung | [`116`](116-plan-release-repo.md) §2 |

### A.3 Kein Debug im Release (Marco, 12.09.) — am Gerät bestätigt

| | Was | wo es steht |
|---|---|---|
| ☑ | **`CONFIG_DEBUG_FS` und `DYNAMIC_DEBUG` aus** im Release-defconfig. Schließt `cpu_comm/call`, `tx_delay_*` und die Schreibseite von `watch` **ohne eine Zeile im Treiber** (alles unter `#ifdef CONFIG_DEBUG_FS`). Entwickler: `KERNEL_CONFIG=debug` | `board/hy200_qz713df_a1_defconfig`, `board/debug.config` |
| ☑ | **U-Boot `0033`**: eMMC-Pfad ohne `earlycon`, mit `loglevel=4`; Netboot behält `earlycon`. **Ändert nur den eingebauten Vorgabewert** — das Dev-Gerät hat eine gespeicherte Env und braucht `env default -a; saveenv` | `uboot-h713/0033` |
| ☑ | **Kernel `0158`**: Rückfall-Bootargs im DTS gleichgezogen | `patches/kernel/0158` |
| ☑ | elog-Intensität = `ELOG_LEVEL`, von U-Boot übergeben — Release-`bootcmd` setzt nichts, Vorgabe **1 = nur Fehler**. Nichts zu tun | [`63`](63-mips-elog.md) |
| — | `MIPS elog BEFORE/AFTER`-Zeilen und der zurückgenommene Mode-2-Umbau in `cpu_comm_dev.c` **bleiben** — Marco, 12.09.: „ich will nicht, dass du cpu_comm patchst". Mit `loglevel=4` erreichen sie die Konsole ohnehin nicht mehr | [`60`](60-offen.md) §Kein Debug |
| ☑ | **Am Gerät (v0.8):** `cmdline` ohne `earlycon`, mit `loglevel=4`; `printk 4 4 1 7`; `/sys/kernel/debug` existiert nicht; Konsole beim Start still, `dmesg` vollständig | `analyse/boot/abnahme-v08-20260912.txt` |
| ☑ | `h713_ce_test` lädt per DT-Match automatisch — **bleibt drin** (Marco, 12.09.: „mir wurst") | dito |

### A.4 Neuen Kernel aufs Gerät — ERLEDIGT 12.09. (Abbild v0.8)

| | Was | wo es steht |
|---|---|---|
| ☑ | v0.8 per FEL + ums eingespielt (3 min, Secure Storage unverändert), Kaltstart, Taste, Login < 60 s. board-mgr 4770 rpm, Motor `raw=1 step=0` ohne Homing, Kamera erkannt, WLAN-AP steht, `h713-tv` läuft, keine gescheiterte Unit | `analyse/boot/abnahme-v08-20260912.txt`, [`60`](60-offen.md) §Abbild v0.8 |
| ☐ | Kleinkram aus dem Journal: `regulatory.db` „load failed -2" (cfg80211 eingebaut, fragt vor dem Rootfs; global bleibt `00`, aic8800 unberührt); `r8152` will `rtl8153b-2.fw` (läuft ohne); board-mgr meldet fehlenden PWM als Warnung statt Info | dito |

### A.5 R5 Qualität

| | Was |
|---|---|
| ☐ | 20 Gate-Zyklen |
| ☐ | HDMI-Modustabelle vollständig |
| ☐ | Recovery-Weg **von einer zweiten Person** gegangen |

### A.6 Repo und Release — Plan [`116`](116-plan-release-repo.md)

| | Was | wo es steht |
|---|---|---|
| ☑ | **P1** Serie bereinigt (12.09.): fünf Nachträge `0014a`/`0024a`/`0024b`/`0024c`/`0078a`, cstengers 46 + 16 byteidentisch, `series` mit 13 Abschnitten, `build.sh` überliest `#`. Baum-Identität mit `diff -r` bewiesen (0 Unterschiede); Bau läuft | [`116`](116-plan-release-repo.md) §4a |
| ☑ | **P4 `release/build-all.sh`** (12.09.): elf Schritte, 10 min, ALLES GRÜN, Stempel; Keyring gepinnt, Sysroot reproduzierbar, `tftp/` keine Eingabe mehr. Klon-Beweis folgt mit P3 | [`116`](116-plan-release-repo.md) §4a |
| ☑/☐ | **P2** Forks: `sunxi-tools` und `arm-trusted-firmware` als **private** Repos unter `well0nez` (12.09.), Falltür committet. **U-Boot offen** — Fork ist öffentlich, Push erst bei P7; Zweig `h713-hy310` lokal bereit, dort in den Standardzweig mergen (Marco). `uboot-h713/` wird seit P3 aus dem Fork erzeugt (P2.7 ☑) | [`116`](116-plan-release-repo.md) §4a |
| ☑ | **P3** Repo-Skelett: **`release/repo-skelett.sh`** baut `repo-neu/` in 5 s (12.09.): `legacy`-Branch + Tag `legacy-arm32-2026-08`, `main` darauf, `mainline/` per **subtree** von cstenger `8860991`, unsere Auflage (Serie byteidentisch bewiesen) + Fork-Pins, `uboot-h713/` erzeugt, Umzüge `installer/` `rootfs/`, `.gitignore`, **Sperr-Scan leer**. **Voller Bau aus dem Klon: ALLES GRÜN** (Abbild `v0.0-beta`, 1159 MiB). Dabei gefunden und geschlossen: `build-all` baute weder Installer-U-Boot noch `sunxi-fel` (jetzt 2b/2c), `installer/tmp/` war root-eigen. Sichtprüfung Marco 12.09. Kein Push (kommt mit P7) | dito |
| ☑/☐ | **P5** Doku Englisch (12.09.): **33 Seiten** — README, STATUS, FLASHING, BUILDING, PROVENANCE, **ROADMAP**, **RELEASES**, 13 Teilsysteme, 9 Werkzeuge, 4 U-Boot, dazu services/build-container/usage. Drei Prüfläufe, alles Substanzielle behoben (Plan [`117`](117-plan-p5-doku.md)). Offen: Marco liest README + FLASHING gegen, Bilder trägt er nach | [`117`](117-plan-p5-doku.md) |
| ☑/☐ | **P6** Generalprobe (12.09.): Stock → Bau aus dem Klon → Einspielen → Abnahme. Bild, Ton, Kamera, Fokus, WLAN (AP **und** STA), **Notaus ausgelöst**, **Env-Übernahme bewiesen**. Offen: 20er-Gate-Reihe mit Ruhefenster, Terminalmitschnitt | [`116`](116-plan-release-repo.md) §4a P6, `analyse/boot/p6-abnahme-20260912.txt` |
| ☑ | **P7** Release (13.09.): `v0.5-beta` als Vorabversion, Abbilder als `.zst` (56 MiB), dazu `u-boot-installer.bin` und `sunxi-fel`; Forks öffentlich, Standardzweige gesetzt | https://github.com/well0nez/allwinner-h713-linux/releases/tag/v0.5-beta |
| ☑ | **P8** an cstenger (13.09.): statt PRs ein Issue mit allen generischen Fehlern, weil er seit dem 22.08. nicht reagiert — cstenger/allwinner-h713-mainline#4 | [`116`](116-plan-release-repo.md) §4a P8 |
| ☐ | **Kleiner Abzug aus der GPT statt aus Konstanten** (B2 in [`119`](119-plan-fremdgeraete-und-installer-fixes.md)): `private`/`Reserve0` per Partitionsnamen suchen, nicht per HY310-LBA. Auf dem HY300 Pro las der Installer die falsche Region und beschriftete sie als `reserve0` — nur lesend, aber ein falsch beschrifteter Abzug ist schlimmer als keiner. Braucht Gegenprobe am Gerät (unser Abzug muss byteidentisch bleiben) | Issue #1 |
| ☐ | **Fremdgeräte-Profile** (HY300 Pro als erster Fall): `h713-extract`-Profil aus den Hashes des Melders, Erkennungseintrag, Abbild mit 636-MHz-DRAM und `h713_project=0x34`; Test nur durch den Besitzer | [`119`](119-plan-fremdgeraete-und-installer-fixes.md) §A |
| ☐ | **Installer-Bedienung vereinfachen**: ohne Argumente alles neben sich finden, nur Schlüssel und Abzug fragen. Dazu (Marco, 12.09.): den **Pflichtabzug überspringen dürfen**, sobald ein Abzug mit Manifest zu diesem Gerät vorliegt — der Inhalt (Secure Storage, private, Reserve0) hängt nicht daran, welches Abbild gerade draufliegt | [`116`](116-plan-release-repo.md) §5 |
| ☐ | **Installer liest `.zst` direkt und findet `u-boot-installer.bin`/`sunxi-fel` neben der Tabelle** — heute muss der Nutzer entpacken und drei Pfade angeben (seit dem Release 13.09.) | FLASHING „Getting the files together" |

### A.7 Entscheidungen, die nur Marco treffen kann

| | Was | wo es steht |
|---|---|---|
| ☐ | **`analyse/hdcp-keys/` nach `re/hdcp-keys/` verschieben** (entschieden 12.09.: nicht löschen, nur aus dem Export halten — `re/` bleibt lokal). Nicht mehr dringend: der Export (P3) nimmt aus `analyse/` nur `boot/` und `beamer-cam/`, und der Sperr-Scan kennt beide Pfade. Bleibt Marcos Handgriff, weil Doku-Verweise mitziehen müssen | [`116`](116-plan-release-repo.md) §2 |
| ☑ | **Partitionsnamen bleiben `hy310-*`** (Marco, 12.09.) | dito |

---

## B — bekannt, aber nicht vor v0.1

| | Was | wo es steht |
|---|---|---|
| ☐ | **HDCP 1.4 über die Crypto Engine — jetzt fällig, das Release ist draußen (Marco, 14.09.).** Weg ist geklärt und am Silizium bestätigt; offen ist der Vorabtest, ob die Non-Secure-Welt CE_S/RSSK (Key-Select 3) benutzen darf — kostet einen Stromzyklus | [`112`](112-plan-hdcp14-crypto-engine.md), [`114`](114-plan-crypto-engine.md) |
| ☐ | **Der HDCP-1.4-Warteschleifen-Patch muss am Ende weg** (Marco, 14.09.). Er unterdrückt keine Meldung, er verhindert, dass die MIPS-Firmware in `Rx_HDCP14_LoadKey` hängen bleibt (Interrupts sind so früh gesperrt, der Timeout kann nie ablaufen) — und genau deshalb lädt bei uns nie ein 1.4-Schlüssel. Stock lädt ihn **vor dem MIPS-Start** (U-Boot → SMC → OP-TEE → CE → Senke `0x03041400`), dann nimmt die Firmware den Zweig „schon geladen". Zu klären: in unserem U-Boot vor dem MIPS-Start laden (dann Patch zurücknehmen, Abnahme: kein `time out!` mehr) oder später über den MIPS-Nachladepfad; die Senke ist flüchtig mit der TV-Domäne, der Vendor-Kernel lädt nach jedem Resume nach. Erst messen, ob eine 1.4-Quelle heute überhaupt ein Bild bekommt | [`112`](112-plan-hdcp14-crypto-engine.md) §1, §4 Schritt 7; [`S49`](nachtlog/S49-hdcp14-schluesselpfad.md) |
| ☐ | **HDCP 2.2 — der letzte Beweis**: ob die 912 Byte Klartext sind oder ein TEE-Chiffrat. Braucht eine HDCP-pflichtige Quelle am Kabel (Streaming-Stick, Konsole, Blu-ray) | [`60`](60-offen.md) §HDCP und EDID |
| ☐ | **EDID 1.4/2.2 durcharbeiten.** Welche Modi der 512-B-Block freigibt, ist ungeklärt; bekannte Lücken bei 1600×900 und 120 Hz | dito |
| ☐ | **Gerätetöne mit HDMI mischen** — der DAC nimmt nur eine Quelle, ein PC hält den Strom dauerhaft offen | [`102`](102-plan-audio-mischung.md) |
| ☐ | **Standby Stufe 2** (ARISC-Deep-Sleep, IR/CEC): <1 W statt 4 W, Sofort-an. RE-Vorarbeit fertig | [`104`](104-plan-standby-stufe2.md) |
| ☐ | **Preset beim Start wählbar** (`preset = NAME \| zuletzt` in `/etc/h713/tv.conf`) und die einzelnen Regler über den Neustart merken | [`60`](60-offen.md) §Bildpfad |
| ☐ | **`h713-tv` Startmodus `auto\|manuell`** merken; heute startet der Dienst immer in `auto` | dito |
| ☐ | **`sunxi-tvtop` + `tvfe` + `sunxi-nsi`** einzeln hochfahren, an einem Punkt wo der Bildpfad sonst stabil ist. Hängt mittelbar an Standby-Rückkehr und HDCP 1.4 | [`60`](60-offen.md) §Module aus dem Altbestand |
| ☐ | **AV1-Dekoder**: erst feststellen, ob das RE-Stand oder lauffähiger Stand ist, dann einreihen. H713 ist der erste Allwinner mit AV1-Hardware | dito |
| ☐ | **Bitgleiche Bauten**: derselbe Stand aus zwei Verzeichnissen liefert verschiedene SPL/U-Boot/FIT/`aic8800_fdrv.ko` — eingebettete **Bauzeit** (TF-A `Built : …`, U-Boot-Kennung, FIT-`timestamp`) und **Baupfad** (`__FILE__` in `aic8800_fdrv.ko`); gemessen 12.09., P3.9. Mittel: `KBUILD_BUILD_TIMESTAMP`, `-ffile-prefix-map`, `mkimage -t` fest. Erst nach v0.1 | [`116`](116-plan-release-repo.md) §4a P3.9 |
| ☐ | **Autofokus** — darf nur mit Testbild laufen, sonst misst er auf einer dunklen Szene Unsinn. Eigenes Werkzeug, nicht in `h713-focus` | [`h713-focus/README`](../userspace/h713-focus/README.md) |
| ☐ | **`Reserve0_a/b` und `private`** von einem **unangetasteten** Gerät abziehen. Bei uns ohne Sicherung überschrieben; ob dort je etwas Einmaliges lag, ist unbewiesen | [`109`](109-plan-layout-v3.md) §9.1 |
| ☐ | **Bluetooth** — kein Treiberproblem: die Firmware (`fmacfwbt_*`) ist **nicht im Vendor-Abzug**, nur im SDK-Satz. Lizenzfrage offen | [`60`](60-offen.md) §WLAN und Bluetooth |
| ☐ | **Wissensdatenbank**: `doku/` **und** `analyse/` bedacht nach Englisch destillieren — neu kategorisieren, zusammenführen, umschreiben; je Teilsystem, was gilt, was widerlegt ist, wo der Beleg liegt. Nicht per grep. `analyse/` wird vorher **nicht** ausgedünnt (Marco, 12.09.) — das passiert in diesem Schritt. Testskripte sind davon getrennt | [`116`](116-plan-release-repo.md) §6 |
| ☐ | **Deutsch in Code** (Kommentare, Meldungen in Modulen, Werkzeugen, Patches ab `0146`) → Englisch, ein Durchgang | dito |
| ☐ | **Testskripte veröffentlichen** — Auswahl, was ohne unseren Tisch läuft / Messaufbau braucht / RE ist. In späteren Sitzungen | dito |
| ☐ | **Cedrus / GPU im großen Stil** prüfen: Testmatrix Decoder × Auflösung × Ausgabe; der KASAN-Fall steht noch | dito |
| ☐ | **Verwaltungsoberfläche** fürs Gerät (WLAN, Presets, Startmodus, Updates ohne SSH) — Zuschnitt offen | dito |
| ☐ | **Windows-`sunxi-fel`** nach Rückmeldungen | dito |

---

## C — sehr spät (Marco, 12.09.)

| | Was | wo es steht |
|---|---|---|
| ☐ | **`display/ge2d/`** — der Stock-Display-Stack, ~3.000 Zeilen, nichts portiert. Kostet einen Helligkeits**regler** aus Linux; die Helligkeit selbst ist gelöst und war nie ein fehlender Regler | [`60`](60-offen.md) §Module aus dem Altbestand, [`80`](80-vergleich-baeume.md) |

---

## D — Kleinkram, der sonst vergessen wird

| | Was | wo es steht |
|---|---|---|
| ☐ | `h713-pq` gibt bei `brightness` „ohne Wirkung" aus — **widerlegt am 07.09.**, gehört korrigiert | [`60`](60-offen.md) §Bildpfad |
| ☐ | Presets `computer` (Schärfe 0), `game`, `hdr` am Gerät nie geprüft | dito |
| ☐ | Gammakurve 2,2: Sichtprüfung gegen das Stock-Bild steht aus | dito |
| ☐ | `h713-tv`: `replug` (S_EDID blocks=0) fehlt; die Plane liest den Ring direkt statt per dma-buf-Import | dito |
| ☐ | Weißabgleich/CTM am CRTC vorhanden, aber ohne Stock-Vergleich | dito |
| ☐ | An cstenger noch nicht zurückgemeldet: Composition-Befund ([`89`](89-composition-block.md)), D1-CCU-Tabelle Port 1, fehlendes SIDDQ-Löschen, Doorbell im MIPS-Sendepfad, `Archived/`-Falle | [`60`](60-offen.md) §Gegenüber cstenger |
| ☐ | **Drei tote defconfig-Zeilen** `CONFIG_SND_SOC_SUNXI_H713_{CODEC,CPUDAI,MACHINE}=m` — die Symbole gab es nur im nie eingereihten `0050` (jetzt in `zurueckgenommen/`). Bei der nächsten defconfig-Änderung entfernen (ändert den Bau-Digest, deshalb nicht nebenbei) | Befund P1, 12.09. |
| ☐ | **19 Patches der Serie greifen mit Fuzz/Versatz** (`.orig`-Dateien im Baubaum: iommu/Kconfig, pwm, sunxi-mmc, cedrus, hdmirx, afbd, dtsi …). Kein `.rej`, Bau korrekt — aber vor den PRs an cstenger (P8) gehören die betroffenen Patches gegen den aktuellen Baum aufgefrischt | Befund P1, 12.09. |
| ☐ | Platzhalter-Sonderfall im Abbild-Bauer: ist eine Vendor-Datei kleiner als der Platzhalter, wird genullt statt `i_size` korrigiert. Bei unseren 30 Dateien tritt das nicht auf | [`60`](60-offen.md) Punkt 13 |
