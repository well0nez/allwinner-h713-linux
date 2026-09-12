# Flashen und Recovery

## Layout auf dem eMMC

Nur **32 KiB** sind umkämpft. Beide Boot-Ketten liegen gleichzeitig auf dem
Gerät, umgeschaltet wird allein über den ersten Stage.

| LBA | dezimal | was |
|---|---|---|
| `0x10` | 16 | **erster Stage** — hier entscheidet sich, wer bootet |
| `0x100` | 256 | Vendor-boot0, Zweitkopie. Ab Werk vorhanden |
| 24576 / 32800 | | Vendor-U-Boot, TOC1-Paket |
| `0x49ac00` | 4828160 | unser U-Boot proper, Start der `empty`-Partition |
| `0x49cc00` | 4836352 | SPL-Parkplatz, `empty` + 4 MiB |
| `0x49ec00` | 4844544 | unser Env, `empty` + 8 MiB — **nur mit U-Boot-Commit `0022`**; ohne den Fix landet sie bei Byte `0x65d80000` ([`30` §16](30-uboot-aenderungen.md)) |

Nichts davon liegt in einer benutzten Partition. `bootloader_a`, `env_a`,
`boot_a` bleiben unangetastet.

## Sicherungen

```
re/device-dumps/emmc-first-300mb.bin    alle acht Boot-Partitionen
re/device-dumps/lba16.bin               Vendor-boot0, 32 KiB
re/device-dumps/lba256.bin              die Zweitkopie, byteidentisch
re/git-archive/HY310-DEV-full.bundle    Git-History des alten Arbeitsbaums
```

Der 300-MB-Dump reicht bis LBA 614399 und deckt `bootloader_a/b`, `env_a/b`,
`boot_a/b` und `vendor_boot_a/b` vollständig ab.

## Weg 1 — über USB-Stick, aus dem laufenden U-Boot

Der bequemste, seit USB-Host läuft. Dateien auf die FAT-Partition des Sticks,
dann am Prompt:

```
usb start
mmc dev 1
fatload usb 0:1 0x50000000 uboot-proper.bin
mmc write 0x50000000 0x49ac00 0x688
fatload usb 0:1 0x50000000 spl.bin
mmc write 0x50000000 0x10 0x40
```

`0x688` sind 1672 Sektoren, die Zahl bei jedem Build neu ausrechnen:
`(Dateigröße + 511) / 512`. `0x40` sind die 64 Sektoren des SPL.

**Reihenfolge nicht tauschen.** Erst U-Boot proper, dann der erste Stage —
bricht es dazwischen ab, steht bei LBA 16 noch der alte, funktionierende.

## Weg 2 — über `ums`, nur mit Gadget-Modus

Geht nur mit einem Build, der MUSB enthält (`hy310_qz713_v3_1_defconfig`).
Am Prompt `ums 0 mmc 1`, dann erscheint die eMMC am PC als Blockgerät:

```bash
lsblk -o NAME,SIZE,MODEL,TRAN | grep -i "UMS disk"
sudo dd if=uboot-proper.bin of=/dev/sdX bs=512 seek=4828160 conv=fsync status=none
sudo dd if=spl.bin          of=/dev/sdX bs=512 seek=16      conv=fsync status=none
sync
```

Immer mit Rücklesung prüfen:

```bash
sudo dd if=/dev/sdX bs=512 skip=16 count=64 status=none | sha256sum
```

## Weg 3 — aus einem laufenden Linux auf dem Gerät

Solange das alte arm32-System bootet, per SSH:

```bash
dd if=/tmp/uboot-proper.bin of=/dev/mmcblk0 bs=512 seek=4828160 conv=fsync status=none
dd if=/tmp/spl.bin          of=/dev/mmcblk0 bs=512 seek=16      conv=fsync status=none
sync
```

## Recovery über FEL

**Funktioniert auf diesem Board**, über die normale USB-A-Buchse. Getestet.

### Kabel

A-auf-A, selbst gelötet. **Die rote Ader (VBUS) auf beiden Seiten offen
lassen** — beide Enden sind Hosts und würden sonst gegeneinander 5 V treiben.
Nur grün (D+), weiß (D−) und schwarz (GND) eins zu eins, nicht kreuzen.

### FEL auslösen

**Reset-Taste gedrückt halten, Strom einstecken** (Marco, 10.09.2026). Mehr ist
nicht nötig: kein Pad gegen Masse, kein Gehäuse öffnen, kein Löten.

Die frühere Beschreibung („FEL-Pad unten links an der Platinenkante gegen Masse")
stammt aus der Bring-up-Phase und ist überholt. Sie steht hier nur noch, damit
niemand sie in älteren Notizen für aktuell hält.

```bash
/opt/Projekte/h713/mainline/build/fel/sunxi-fel version
```

Erwartet: `AWUSBFEX soc=00001860(H713) ver=0001`

### U-Boot über FEL starten — der empfohlene Weg (seit 10.09.2026)

```bash
mainline/external/sunxi-tools/sunxi-fel uboot mainline/build/uboot-v3/u-boot-sunxi-with-spl.bin
```

Ein Befehl, rund drei Sekunden, **kein Byte auf die eMMC**. Das Gerät steht danach am U-Boot-Prompt.
Vorher: Reset-Taste halten, Strom einstecken.

Das ging lange nicht, und die Ursache lag tiefer als vermutet ([`nachtlog/S44`](nachtlog/S44-fel-boot.md)):
der `boot0`-Stub wechselt per RMR nach AArch64, **damit ist EL3 fortan AArch64**; die FEL-Schleife kehrt per
`eret` nach unten zurück und läuft auf EL1, wo das AArch32-RMR-Register nicht mehr erreichbar ist. Die
CPSR-Modusbits sehen dabei vorher wie nachher gleich aus (`0x13`), nur die Ausnahmestufe ist eine andere —
deshalb schlugen vier frühere Rückwege im selben Muster fehl. Die Lösung nutzt genau diesen Zustand: ein `smc`
aus AArch32-EL1 ist eine Falltür zurück nach AArch64-EL3. Der SPL legt vor dem `eret` eine minimale
EL3-Vektortabelle mit Postfach bei `0x48000000` ab, `sunxi-fel` klopft dort an. Dazu kam ein zweiter Fehler:
beim FEL-Boot ist das Bootgerät `BOOT_DEVICE_BOARD`, und `env_get_location()` fiel dann nicht auf MMC zurück —
`env_init()` blieb still stehen. Behoben mit `ENVL_MMC` als Rückfall und `CONFIG_ENV_MMC_DEVICE_INDEX=1`.

**Die frühere Warnung „Nicht `sunxi-fel uboot` benutzen" ist damit überholt** und steht hier nur noch, damit
sie in älteren Notizen niemanden in die Irre führt.

### ⚠ Adresse `0x05000000` niemals lesen

Das ist die UART-Adresse des H616. Auf dem H713 ist sie unbelegt; ein Lesezugriff hängt den Bus auf und kostet
einen Stromzyklus (10.09., zweimal passiert).

### Wiederherstellen mit eingebettetem Payload (Rückweg zum Vendor-boot0)

Für den Fall, dass eine fremde erste Stufe zurück muss, gibt es weiterhin den Restore-SPL mit **eingebettetem
Payload**, eine einzige 64-KiB-Übertragung:

```bash
# Payload erzeugen (hier: der originale Vendor-boot0)
python3 - <<'EOF'
d = open('/opt/Projekte/h713/re/device-dumps/lba16.bin','rb').read()[:32768]
with open('/opt/Projekte/h713/mainline/external/u-boot/arch/arm/mach-sunxi/h713_spl_payload.h','w') as f:
    f.write("static const unsigned char h713_spl_payload[] = {\n")
    for i in range(0, len(d), 12):
        f.write("\t" + " ".join(f"0x{b:02x}," for b in d[i:i+12]) + "\n")
    f.write("};\n")
EOF

# Restore-SPL bauen
build/uboot-build.sh "$PWD/build/uboot-felmmc" hy310_felmmc_defconfig spl/sunxi-spl.bin

# Übertragen
build/fel/sunxi-fel -p spl build/uboot-felmmc/spl/sunxi-spl.bin
```

Auf der UART erscheint `=== H713 SPL RESTORE ===` und `wrote 64/64
RESTORED-OK`. Danach Strom aus und an.

**Der Host meldet dabei `usb_bulk_send() ERROR -7: Operation timed out` —
das ist kein Fehlschlag.** Sobald der Restore-SPL läuft, kehrt er nicht ins
FEL zurück, also läuft der Nachfass-Handshake ins Leere. Die UART ist die
Wahrheit.

## Wenn gar nichts mehr geht

Die BROM sitzt im Mask-ROM, unterhalb von allem auf dem eMMC. FEL lässt sich
nicht wegflashen. Solange das Kabel funktioniert und das Pad erreichbar ist,
ist das Board nicht verloren.

## Weg 4 — per TFTP am U-Boot-Prompt, ohne Stick (seit 09.09.2026 der schnellste Weg)

Nur U-Boot proper (ab LBA `0x49ac00`); die SPL bleibt. Datei nach `/opt/Projekte/h713/tftp/`, am Prompt (Server **immer explizit**, weil
`dhcp` `serverip` auf den Router setzt). Dieser Rechner (Mini-IT11) ist **192.168.8.123**; `.104` in älteren Doku-Stellen war der vorige Rechner.
Aus der Claude-Sitzung skriptbar: `sudo python3 tools/uart-uboot.py run -t 45 -c …` — Marcos `tio` muss dabei geschlossen sein.

```
tftpboot 0x50000000 192.168.8.123:uboot-proper-gate-v4.bin
crc32 0x50000000 0xd8579                 # gegen den Host-Wert (python zlib.crc32) vergleichen: 56a6a77f
mmc dev 1
mmc write 0x50000000 0x49ac00 0x6c3       # Sektoren = ceil(Bytes/512), hier 886137 B
mmc read 0x52000000 0x49ac00 0x6c3
cmp.b 0x50000000 0x52000000 0xd8579       # "Total of 886137 byte(s) were the same"
reset
setenv h713_gate 0; setenv serverip 192.168.8.123; saveenv   # Dev-Gerät: Gate aus, Netboot-Rückfall auf diesen Rechner (die alte Env liest v4 nicht mehr)
```

Skriptbar mit `tools/uart-uboot.py run -c …` über den ESP32-S2-UART; Konsole des Neustarts mit `tools/uart-reset-catch.py` (fängt den
Prompt) oder `tools/uart-passiv.py` (nur mitlesen). Vorher die eMMC-Kopie sichern: `dd if=/dev/mmcblk0 bs=512 skip=4828160 count=1800`
aus Linux. Falle: Nach einem BL31-Bau die U-Boot-FIT in einem **frischen** Ausgabeverzeichnis bauen, sonst bleibt das alte BL31 drin.
Stand seit 09.09.: `tftp/uboot-proper.GUT-gate-v2-20260909.bin` (sha256 `25da46c6…`) = Gate-U-Boot + BL31 mit `poweroff`→Gate;
Vorgänger `mainline/build/flash-netboot-gate/emmc-proper-vorher.bin`.
**Stand seit 10.09. 08:40 (GUT):** `tftp/uboot-proper.GUT-gate-v5-20260910.bin` (890.233 B, CRC32 `be77a83a`, Sektoren `0x6cb`) =
v4 **plus `0023`** (Env-Umschalter `h713_mips_dev`/`h713_mips_path`/`h713_project`, `doku/108`). Vorgänger: `tftp/uboot-proper.GUT-gate-v4-20260910.bin` (= `uboot-proper-gate-v4.bin`, 886.137 B, CRC32 `56a6a77f`,
sha256 `9a7e0c38…`) = v3 (Gate, GP5, Default-Env `0021`) **plus Env-Offset-Fix `0022`** — erst damit liegt die Env wirklich bei `0x93d80000`.
Gebaut im Container `h713-build` (clang 20.1.8 wie v3). **Kaltstart am 10.09. abgenommen** (`analyse/boot/v4-kaltstart-20260910.txt`): Gate aus, MIPS-Firmware und Panel wie mit v2,
`display.bin`-SHA akzeptiert, MIPS-Readiness bewiesen, Panel 1920×1080 latched; `boot_emmc` scheitert still (Stock-Layout, keine FIT
auf p5), `boot_net` greift als Rückfall, Kernel und `h713-tv@video1` laufen. Geflasht über UART nach obigem Rezept, danach aus Linux bestätigt:
`hy310-install.sh --dry-run --steps precheck --uboot-bin uboot-proper-gate-v4.bin --no-backup --yes` → „U-Boot proper … byteidentisch",
„gültige Env am Release-Ort 0x93d80000 (75 Variablen, h713_gate=0)". Der alte Env-Block bei `0x65d80000` bleibt als Rest liegen (landet später
in p6). Vorgänger gesichert: `mainline/build/flash-netboot-gate/emmc-proper-vor-v4-20260910.bin` (= GUT-gate-v2).

### Falle beim Flashen über TFTP (10.09. selbst hineingelaufen)

`tftpboot` bricht nach einem frischen U-Boot-Start mit `*** ERROR: 'ipaddr' not set` ab, wenn noch kein `dhcp` gelaufen ist —
und lässt den alten Speicherinhalt an der Ladeadresse stehen. Ein direkt folgendes `mmc write` schreibt dann Müll an die
U-Boot-Stelle. Deshalb gilt ohne Ausnahme:

**Zwischen `tftpboot` und `mmc write` gehört ein `crc32`, dessen Wert mit dem Host verglichen wird.** Stimmt er nicht, nicht
schreiben. Passiert es doch, ist es reparabel, solange U-Boot noch aus dem RAM läuft: Prompt halten, `usb start`, `dhcp`,
`setenv autoload no`, neu laden, `crc32` prüfen, neu schreiben. **Nicht** vorher resetten.

`dhcp` versucht außerdem selbst eine Datei zu laden und kann dabei hängen (`EHCI timed out on TD`); `setenv autoload no` verhindert das.
