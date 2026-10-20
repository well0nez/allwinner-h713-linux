# 216 Lizenzen: die offenen Teile von TODO 7.20 (a, b, c, d, e, g) - Protokoll

Datum: 20.10.2026 (abends). Zweig `versuch/lizenz-abschluss` auf `medien` `4dc41dc`, nicht gepusht, nicht in `main`. Vorgeschichte:
[`doku/210`](210-entflechtung-unlizenzierte-dateien-aus-dem-subtree-20261013.md) (die 70 Dateien). Arbeitsweise wie bei a
(13./14.10.): eine Sitzung las die Originale und schrieb eine Beschreibung ihrer Funktion, eine zweite schrieb die
neuen Dateien nur danach, ohne die Originale je zu öffnen; die Ausgaben wurden gegen einen Bau mit den alten Dateien
verglichen.

## 1 Was sich geändert hat

| Teil | Commit | was |
|---|---|---|
| c | `ea4b91d` | `versuch/entflechtung` gemergt: die 70 Dateien aus cstengers Baum ohne Lizenzangabe sind fort, `sperr-scan` Regel 9 |
| g | `92bcf48` | `BUILDING.md`: `build.sh uboot` baut die Board-Basis ohne Rolle; die bl31-Variante war schon `ddd7329` |
| e | `4e680d2`, `c713776` | Lizenzhinweise im Abbild unter `/usr/local/share/doc/h713-linux/`; der Quelltext geht mit dem Abbild (Quellarchive daneben, das Repository am Commit aus `SOURCES`), kein schriftliches Angebot (Marco 20.10.) |
| a | `bacfdbc` | `build.sh` und `uboot-build.sh` aus dem Reinraum (`3220575`), dazu das Wiederholen von Downloads aus `550cde0` |
| b | `3de2e85` | `mainline/config/versions.env` und `toolchain.md` neu, tote Schlüssel weg |
| d | `e9b75ff` | Kernel-`series`, Defconfig, beide READMEs neu; die Fragmente `iommu`, `kasan`, `builtin-drivers` und `mainline/modules/aic8800/` entfernt |

## 2 Gemessen

- **a:** die 44 Prüfsummen der Referenzschritte L1-L15 (bl31 dreimal, U-Boot je Rolle samt SPL und `.config`,
  `savedefconfig`, `build.sh uboot`, Baumnamen, Kernel-`.config`, `Image`, `Image.gz`, DTBs, FIT, Module, aic8800,
  `SHA256SUMS`, FIT für `ddr3`, netboot, Baumlisten) bytegleich zu den alten Skripten auf demselben Stand, gleiche Uhr
  (`SOURCE_DATE_EPOCH=1792508151`). Ein Fehlschlag beim Laden: Status 1 nach 21 s, vier Wiederholungen, nichts bleibt
  liegen. `uboot-build.sh` mit relativem Ausgabeordner und Rolle: alt scheitert (make legt den Ordner im U-Boot-Baum
  an), neu baut bytegleich zum absoluten Aufruf.
- **b und d in einem Kernelbau:** neuer Baumname `4d27b5a5…` wie vorab gerechnet; `.config`, `Image`, `Image.gz`, die
  drei DTBs, der FIT und die installierten Module bytegleich zur Referenz, `aic8800_bsp.ko` und `aic8800_btlpm.ko`
  gleich, `aic8800_fdrv.ko` 551 Byte anders, nur wo es den Namen des Kernelbaums trägt (gleiche Größe); die `.config`
  der Fragmente `debug` und `netboot` gleich. Die aic8800-Serie ist neun Dateinamen und nichts sonst, ihr Neuschrieb
  also dieselben Bytes (aic8800-Baum `44e143cf…` unverändert).
- **e:** voller `build-all.sh`-Lauf HY310 mit `--standby`: alle Tore grün, die 14 Lizenzprüfungen der Rootfs-Abnahme
  grün, 14 Hinweisdateien im Tar. Am Rootfs vom Morgen: jedes der 622 Debian-Pakete hat seine `copyright`-Datei, 13
  über einen Link nach Debian Policy 12.5, nur die fünf Mesa-Attrappen nicht.
- **Gesamtprobe:** `release/build-all.sh --profile media,desktop --standby` für den HY310 und den G-EU
  (`--board hy200-qz713df-a1 --variant projector05061226`) auf einem Vergleichs-Commit mit derselben Uhr wie die Referenz
  (gleicher Baum wie `e9b75ff`): beide Läufe grün (23 und 31 min), HDCP-, crust- und Lizenz-Tor grün,
  `reproducible: yes`. Gegen die Läufe mit den alten Dateien bytegleich: `bl31.bin`, `scp.bin`, SPL, U-Boot,
  Umgebung, Installer- und Probe-U-Boot, `Image.gz`, FIT, die DTBs, `aic8800_bsp.ko`, `aic8800_btlpm.ko`,
  `sunxi-fel`. Anders, erwartet: `aic8800_fdrv.ko` (Baumname), der Mesa-Tar (nur sein README nennt jetzt die
  Revision), der libva-Tar (seine Quellnotiz und die GNU-Build-ID des Moduls, 20 Byte, die am Bauort hängt), das Rootfs
  und die Abbilder. `release/tor.sh --tests` und `boards/check.sh` grün.

## 3 Befunde

- `aic8800-0003` setzt den SDIO-Takt auf 0 (der Treiber behält, was der MMC-Kern aushandelt), nicht auf 25 MHz, wie
  die Beschreibung aus dem alten README sagte; das neue README folgt dem Patch.
- Ein Bau mit den alten Skripten hinterlässt Logs und `.its`, die deren Text spiegeln; für einen Reinraum zählen sie zu
  den gesperrten Dateien. Die Patches dieses Pakets sind mit `git format-patch -B10%/10% -D` erzeugt, damit sie den
  alten Text nicht in ihren Minuszeilen tragen.
- TF-A baut nicht neu, wenn nur `SOURCE_DATE_EPOCH` sich ändert und der Standby-Schalter gleich bleibt: der erste
  Abnahmeschritt nahm die Objekte eines früheren Laufs mit dessen Uhr (`build-all.sh` löscht den Bauordner selbst,
  `build.sh bl31` allein nicht).

## 4 Offen

- Am Gerät (Aufsicht): `aic8800_fdrv.ko` lädt am G-EU, der FIT bootet (Warmstart).
- Der Release-Ablauf muss die Quellarchive neben das Abbild legen (das README sagt es zu): die Repository-Fassung am
  Commit, Linux 6.18.38, die Fork-Stände, Mesa, libva, die Debian-Quellpakete aus `DEBIAN-SOURCES`.
- Marco: Hinweise für die schon veröffentlichten Releases; 7.20 f (Historie).
- TODO 5.17 (Weiterbauen) ist zurückgestellt; ein ungemessener Entwurf liegt auf `versuch/weiterbauen`.
