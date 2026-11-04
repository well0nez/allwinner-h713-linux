# 229 HY320: 7.3.1-Release mit CONFIG_RUST und h713_drm als Normalstart, beide Anzeigestapel

Datum: 05.11.2026 (Gerätezeit falsch, April 2026). Gerät: der HY320 des Besitzers. Augen: **keine** - der Besitzer war
nicht da, alles über Logs, Registerlesungen und Abzüge. Zweig `hy320`: Merge `kernel-7.3` (`138d9ec5`), Kern-Reihe
`0355`-`0358` und Defconfig (`871fc0c2`). Rohdaten auf dem Gerät `/data/release73/`, Kopie neben dem Repo
(`notes/release73/`). Gerätesperre `/tmp/h713-device.lock` für die ganze Phase.

## 1 Der Kern

- `kernel-7.3` ohne Konflikt in `hy320` gemischt; `docs/kernel-rust.md`: `boot_rustbench73` endet jetzt wie `boot_rust`
  mit `${h713_display_args}`.
- `0355`-`0357`: die Reihe aus `cleanroom-h713` (`drivers/h713-drm/patches/`, Quellstand `5fd6cd6`) auf den
  7.3.1-Baum dieser Reihe gelegt und daraus neu erzeugt. Abweichung nur im Kconfig-Haken: 7.3 listet die `source`-Zeilen
  ohne Leerzeilen, die Zeile steht wie in der v6.18-Fassung hinter `sun4i`. `MAINTAINERS` mit Versatz 388 und Fuzz 1.
  `drivers/gpu/drm/h713/` des Baums = Ausgabe von `stage.sh` (`diff -r` leer). Kein Treibercode geändert, keine
  Compilerfehler.
- `0358`: der Knoten des HY320-Overlays (`dts/sun50i-h713-hy320-display.dtso`) im HY320-Baum, `status = "disabled"`.
  Grund: der DT-Weg des Treibers (Takte, Reset, Power-Domains gehalten, CCU-Wörter dem Taktreiber überlassen) ist auf
  keinem Gerät gelaufen (impl-drm Schritt 8, Q-DT-1/Q-DT-2 offen, darunter zwei Knoten mit `ppu` 1/2); ein
  eingeschalteter Knoten wäre auf dem Herstellerstapel ein Verbraucher von `ccu`/`ppu` ohne Treiber. Ein abgeschalteter
  Knoten ist kein Gerät und kein Verbraucher; `h713-display load` sieht keinen *eingeschalteten* Knoten und gibt
  `bench=1` - die Form, die seit dem 03.11. auf dem Gerät läuft. Deshalb `CONFIG_DRM_H713_BENCH=y` im Release.
- Defconfig: `CONFIG_RUST=y`, `CONFIG_DRM_H713=m`, `CONFIG_DRM_H713_BENCH=y`. `.config` gegen den bisherigen
  7.3.1-Releasebaum (`d96694ee`): nur die Rust-Zeilen und diese. Module: genau eines mehr, `h713_drm.ko`
  (`vermagic=7.3.1 SMP preempt mod_unload aarch64`, `depends=sun50i-h713-arisc`). Größe: `Image.gz` 7 848 526 ->
  8 055 416 Byte (+206 890), FIT 7 885 192 -> 8 092 728.
- Gebaut auf normalem Weg (`BOARD=hy320 build.sh kernel`, dann `aic8800` mit 0011): Baum
  `linux-7.3.1-78707904...`, `modroot.78707904`. Hashes: FIT `fd3c882f6cf4aba2`, `h713_drm.ko` `c10f5ded8e2c9d92`,
  `aic8800_bsp.ko` `d93bca9036fd56d6`, `aic8800_fdrv.ko` `f49037072c763948`, `aic8800_btlpm.ko` `4eeaa7f35d0cdcf9`.
  h713-tv `14c1744c`, h713-warp `ab85c264` aus `hy320` neu gebaut (`make -B cross` mit `sysroot-arm64`): bitgleich
  mit den Binärdateien von §34a in `doku/228`.

## 2 Einbau

- Erst ein Einmalstart: neues FIT als `h713-kernel-7.3-next.fit`, `boot_73next` (Watchdog 16 s, `h713_boot` vor dem
  Laden zurück auf `emmc`), Module als `/lib/modules/7.3.1`, die alten als `/lib/modules/7.3.1.prev` (das ältere
  `.prev` nach `/data/release73/before/`), `depmod -a 7.3.1`. Ergebnis: neuer Kern (`#1 SMP PREEMPT Wed Nov 4 17:27:14
  UTC 2026`), gleiche Modulmenge wie vorher, Wi-Fi-AP, `running`, keine fehlgeschlagenen Units, 426
  `rust_helper`-Symbole.
- Dann Normalstart: `h713-kernel-7.3.fit` -> `h713-kernel-7.3-prev.fit`, das neue FIT als `h713-kernel-7.3.fit`.
- Umgebung, je ein `fw_setenv NAME WERT` mit Rücklesen (`r73env.py`): `bootcmd` = die HY320-Zeile des Abbilds
  (`h713_display`-Zweig, dann `h713_conlog`); `${h713_display_args}` am Ende der `bootargs` von `boot_emmc`, `boot_net`,
  `boot_618`, `boot_rust`, `boot_rustbench73`, `boot_k73`; neu `boot_73prev` (Einmalstart des vorigen FIT);
  `h713_display=vendor`. Entfernt: die zwei Schlüssel mit Leerzeichen im Namen (`boot_618 ...`, `boot_emmc if ...`, aus
  einem früheren `fw_setenv -s`), die Laufzeitvariablen der Einmalstarts. `fw_printenv` gegen vorher unterscheidet sich
  nur darin.
- Rootfs-Teile aus `hy320`: `h713-display`, `h713-display.service` (+ `sysinit.target.wants`), `h713-drm.conf`,
  `/lib/firmware/h713-mips -> /boot/mips`, h713-tv, h713-warp, `99-h713-tv.rules`; für `h713-hdcp-key`,
  `h713-tv-rescue`, `h713-sleep-pre`, `h713-sleep-post` je ein Drop-in `h713-display-stack.conf` mit
  `ConditionKernelCommandLine=!h713.display=clean` (die Units des Geräts unterscheiden sich von denen des Repos nur in
  dieser Zeile).

## 3 Nachweise auf dem Normalstart

Keine HDMI-Quelle mit Signal während des ganzen Fensters: `signal no signal`, `QUERY_DV_TIMINGS: Link has been
severed`, auch nach `h713-tv ctl replug` (die Quelle war aus). Alles, was ein Quellbild braucht, ist offen (§4).

- **(a) vendor**: `/proc/cmdline` = vorher + ` module_blacklist=h713_drm`; gleiche Modulmenge wie vorher, `h713_drm`
  nicht geladen; `h713-display status`: vendor, afbd geladen, `h713_drm on this kernel (7.3.1): loadable`;
  `h713-display` übersprungen, `h713-hdcp-key` aktiv (HDCP-2.2-Schlüssel übergeben); conlog: MIPS gestartet und
  `READY`; h713-tv mit `sun50i-h713-hdm`/afbd, Seite „No signal on HDMI“; Ton: Karten `Codec` und `hy310hdmi`,
  MSP `running`, Quelle `present=0` (kein Signal).
- **(b) clean**: `h713-display set clean` auf 7.3.1 angenommen (rc 0). Erster sauberer Start abgesichert über
  `boot_73clean` (derselbe Kern und dieselben `bootargs`, Watchdog, `h713_display` vor dem Laden auf `vendor`), danach
  der echte Normalstart über `boot_emmc` mit `h713_display=clean`: `h713.display=clean module_blacklist=...`; weder
  afbd noch hdmirx, cpu_comm, mips, msp geladen, kein MIPS-Plattformtreiber; conlog `MIPS held in reset (noboot)`;
  `h713_drm loaded after sun50i-h713-arisc (bench=1: no enabled device tree node ...)`; `h713-mips/database.TSE loaded`,
  `h713-hdmirx-clean registered as video1`, EDID über den Provider auf Port 1; `h713-tv@video1` von der Regel
  gestartet: `stack clean: h713-drm + h713-hdmirx-clean`, `display /dev/dri/card1 (h713-drm)`; Startseite offen
  (`h713-keys: launcher open: 5 entries`, `cover an opaque page`); hdcp-key/tv-rescue übersprungen. Ohne Quelle läuft
  der Empfänger alle 10 s die Sequenz ohne TMDS (wie in 50 §8/§9 vorgesehen).
  Trapez über warp: `launcher close`, `h713-desktop` als Wayland-Client -> `warp on`, Mali-G31 zeichnet auf die
  Videoebene, Kern `commit: 0, 1151 ops, ... 0 read-back mismatches (video plane: full enable)`. `h713-warp ctl test
  grid` + `keystone set tl x 80`: erste helle Spalte der Zeile 2 im Abzug 154 (80 ‰ von 1920 = 153,6), zurück auf 0:
  Spalte 1. Werte danach wie vorher, Desktop gestoppt, Quelle `auto`.
  `h713-display set vendor`, Neustart: vendor, cmdline/lsmod wie (a).
- **(c) Sicherheitsnetz**: `install h713_drm /bin/false` in `/etc/modprobe.d/` (nur für diesen Start), `fw_setenv
  h713_display clean`, Neustart: `h713-display.service` failed, `the clean stack cannot run on 7.3.1: modprobe h713_drm
  bench=1: exit 1 ...; h713_display set back to vendor`; Datei entfernt, Neustart: vendor wie (a).

## 4 Offen

- Bild und Ton von einer HDMI-Quelle auf beiden Stapeln auf diesem Kern (vendor: Bild über den Kanal, 48 kHz; clean:
  `capturing`, `video_source hdmi`, Trapez auf dem HDMI-Bild). Auf 7.3.1-rustbench mit gleichem Modulquellstand
  belegt (`doku/228` §34a).
- Der DT-Weg von `h713_drm` (Knoten `okay`, ohne `bench=1`).

## 5 Ende

Normalstart = das neue 7.3.1 (`fd3c882f`), `h713_display=vendor`, `h713_boot=emmc`, RUN1, keine fehlgeschlagenen
Units; Umgebung gesichert in `/data/release73/env-final`; Sperre frei.
