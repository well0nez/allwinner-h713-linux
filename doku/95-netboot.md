# Netboot: Kernel per TFTP, Wurzelverzeichnis per NFS

Stand 31.08.2026, läuft. Auf dem Gerät liegt **nur U-Boot**. Kernel und
Userland kommen bei jedem Start über die Leitung, beides liegt auf dem PC.

Damit entfällt das Flashen für jeden Test: Datei ändern, Gerät neu starten,
fertig.

## Die Hardware dazwischen

An der USB-A-Buchse des Beamers hängt ein **USB-Hub mit Ethernet**. Der ist
nicht eingebaut, sondern angesteckt. `usb tree` zeigt:

```
Bus 0 (EHCI0)   Hub → USB2.0 HUB → Realtek USB 10/100/1000 LAN
                                 → Kingston DataTraveler   (der Stick)
Bus 1 (EHCI1)   Hub → Generic HD camera
```

Der Realtek ist ein RTL8152/8153. In U-Boot bedient ihn `USB_ETHER_RTL8152`,
im Kernel `r8152`.

Die Kamera an Port 1 gehört zum Gerät, vermutlich für Autofokus und Keystone.

## Auf dem PC

Adresse: **192.168.8.104** (per DHCP, `enp9s0`). Sie steht fest im
Environment des Geräts — ändert sie sich, bootet nichts mehr. Eine feste
Zuordnung im Router wäre die saubere Lösung.

### TFTP starten

```bash
sudo dnsmasq --port=0 --enable-tftp --tftp-root=/opt/Projekte/h713/tftp \
     --no-daemon --log-queries
```

`--port=0` schaltet DNS ab, damit dnsmasq dem Router nicht ins Gehege kommt.
Läuft im Vordergrund, Strg-C beendet ihn. **Schließt du das Fenster, ist er
weg und das Gerät bootet nicht mehr.**

Inhalt von `/opt/Projekte/h713/tftp/`:

```
h713-kernel.fit           der normale Kernel (r8152 als Modul)
h713-kernel-netboot.fit   der für Netboot (r8152 fest eingebaut)
```

### NFS

`nfs-kernel-server` ist installiert. Export in `/etc/exports`:

```
/srv/h713-rootfs 192.168.8.0/24(rw,sync,no_subtree_check,no_root_squash,insecure)
```

`no_root_squash` ist zwingend, sonst darf root auf dem Gerät nichts schreiben.
`insecure` erlaubt Anfragen von unprivilegierten Ports.

Nach Änderungen: `sudo exportfs -ra`.

Das Wurzelverzeichnis liegt entpackt unter `/srv/h713-rootfs`, rund 970 MB,
und **muss root gehören** — sonst stolpert das Zielsystem über `/etc` und die
setuid-Binaries.

## Im Gerät gespeichert

Alles mit `saveenv` auf der eMMC, überlebt Neustarts:

```
serverip = 192.168.8.104
bootfile = h713-kernel-netboot.fit
autoload = no
bootargs = console=ttyS0,115200 earlycon root=/dev/nfs rw
           nfsroot=192.168.8.104:/srv/h713-rootfs,vers=3,tcp ip=dhcp rootwait
           clk_ignore_unused pd_ignore_unused cma=128M
bootcmd  = h713_disp auto 0x30 logo; dhcp;
           tftpboot 0x60000000 192.168.8.104:${bootfile}; bootm 0x60000000
```

Vier Dinge daran sind teuer gelernt:

**`autoload=no`.** Ohne das zieht `dhcp` sofort selbst eine Datei nach und
scheitert.

**Die Server-IP steht literal in `bootcmd`, nicht als `${serverip}`.** `dhcp`
überschreibt `serverip` mit dem, was der DHCP-Server anbietet — hier der
Router unter 192.168.8.1. Die Variable zeigt danach auf die falsche Adresse.

**`clk_ignore_unused pd_ignore_unused` sind nicht optional.** Ohne sie nimmt
Linux beim `clk_disable_unused` PLL_VIDEO2, die Display-Modtakte und den
MIPS-Coprozessor mit — das Panel verliert seinen Pixeltakt, das Bild wird
schwarz, und jeder Atomic-Commit läuft in einen 10-Sekunden-Timeout. Sie
stehen im `chosen`-Knoten des Devicetree, aber die U-Boot-Env überschreibt
den, und beim Umstieg auf Netboot sind sie verlorengegangen. Im Kernel-Log
sichtbar an `clk: Not disabling unused clocks`. Ganze Geschichte in
[61-plan-vblank.md](61-plan-vblank.md).

**`h713_disp auto 0x30 logo` gehört vor den Rest.** Der KMS-Treiber im Kernel
richtet nichts selbst ein, er übernimmt nur, was U-Boot hinterlässt. Ohne
diesen Schritt meldet er `display is not running`. Seine Fehlermeldung nennt
`0x34` — das ist **seine** ProjectID, unsere ist `0x30`.

## Der Build

`hy310_netboot_defconfig` = `hy310_host_defconfig` plus:

```
CONFIG_NET / CMD_NET / CMD_DHCP / CMD_PING / CMD_NFS
CONFIG_USB_HOST_ETHER + CONFIG_USB_ETHER_RTL8152
CONFIG_NET_RANDOM_ETHADDR
```

**Andere Sektorenzahl:** `0x6bb` statt `0x688`, weil der Netzwerkstack das
Image um 26 KB wachsen lässt.

Der Kernel braucht die Treiber **fest eingebaut**, nicht als Modul — das Netz
muss stehen, bevor das Wurzelverzeichnis da ist, und die Module liegen genau
darauf. Dafür gibt es `patches/kernel/board/netboot.config`:

```
CONFIG_USB_USBNET=y
CONFIG_USB_RTL8152=y
```

Gebaut mit `KERNEL_CONFIG=netboot build/build.sh kernel`, Ergebnis
`build/out/h713-kernel-netboot.fit`.

## Über UART flashen, ohne Stick

`tools/uart-send.py` schickt eine Datei per YMODEM an U-Boots `loady`.
9,7 KB/s bei 115200 Baud, also gut anderthalb Minuten für das große Image.

```
# in U-Boot nichts vorbereiten, das Skript setzt loady selbst ab
tools/uart-send.py 0x50000000 mainline/build/flash-netboot/uboot-proper.bin
# dann in U-Boot:
mmc write 0x50000000 0x49ac00 0x6bb
```

Drei Eigenheiten von U-Boots `loady`, alle am Gerät herausgefunden:

- **128-Byte-Blöcke.** Mit 1K-Blöcken (STX) antwortet es endlos mit `C`.
- **Der Batch-Abschlussblock ist Pflicht**, sonst bleibt es bei `C` hängen.
- **Er muss aus Nullbytes bestehen**, nicht mit `0x1a` gefüllt — sonst
  "download aborted", obwohl alle Daten schon übertragen waren.

## Das Rootfs bauen

`tools/rootfs/build.sh` in seinem Baum, aber es setzt sechs Dinge voraus, die
es nirgends nennt. Auf einem Debian-Abkömmling:

| | |
|---|---|
| `pacman` in der Werkzeugprüfung | wird nur gebraucht, wenn das Debian-Keyring fehlt — verlangt wird es trotzdem immer. Platzhalter in den PATH legen. |
| `binfmt`-Dateiname | er will `qemu-aarch64-static.conf`, Debian/Ubuntu nennen sie `qemu-aarch64.conf`. Symlink. |
| `/etc/subuid` | `unshare --map-auto` braucht passende Bereiche. Im Container `root:1:65536`. |
| Container ohne `--userns=keep-id` | sonst kein verschachtelter Namensraum |
| `build.sh aic8800` vorher | sonst fehlt `aic8800_bsp.ko` |
| `local/allwinner-h713-linux` | erwarteter Pfad zu unserem Repo. Relativer Symlink auf `../../legacy`. |

Dazu fehlten in unserem Repo zwei Firmware-Blobs, `fmacfw_8800d80_h_u02.bin`
und `fmacfwbt_8800d80_h_u02.bin`. Sie liegen in
`re/vendor/HY310-DEV/aic8800_port_workspace/radxa-aic8800/src/SDIO/driver_fw/fw/aic8800D80/`
und sind SHA-256-identisch mit seinen gepinnten Summen. Inzwischen nach
`legacy/drivers/wifi/firmware/aic8800_sdio/aic8800D80/` kopiert, dort aber
noch **nicht committet**.

Das Projekt wird als Overlay in den Container gemountet (`-v ...:/work:O`),
damit die Bauartefakte nicht im Projektbaum landen.

## Wenn nichts mehr bootet

Das Gerät hat kein eigenes Betriebssystem mehr. Wenn `dnsmasq` oder NFS
stehen, kommt es nur bis U-Boot. In U-Boot einbrechen: Strg-C wiederholt
senden, das bricht die TFTP-Schleife ab.

**Aus Linux heraus geht das nicht** — dort landet Strg-C in der Shell des
Geräts, nicht in U-Boot. Dann hilft nur ein Neustart.
