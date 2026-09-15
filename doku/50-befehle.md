# Befehlssammlung

> **Stand 08.09.2026.** Der Abschnitt *Betrieb* ist der tägliche Weg; alles darunter (U-Boot-Prompt, UART, FEL,
> Stock-Umschaltung, RE) gilt weiter, wird aber im Normalbetrieb nicht mehr gebraucht.

## Betrieb (Stand 08.09.2026)

**Gerät erreichen, starten, ansehen**

```bash
ss -ulnp | grep ':69 '                                   # TFTP da? sonst bleibt das Board in U-Boot (nur Marco kann es loesen)
sonoff_ctl restart --host 192.168.8.179 --wait 5         # Kaltstart ueber die Steckdose; ssh nach 35-90 s
ssh root@192.168.8.141 'h713-tv ctl status'             # Programm-, Kernel- und cpu_comm-Zeilen
ssh root@192.168.8.141 "journalctl -u 'h713-tv@*' -f"   # Journal des Dienstes
ssh root@192.168.8.141 'cat /sys/kernel/debug/sun50i-h713-hdmirx/status; cat /sys/kernel/debug/cpu_comm/watch'
python3 analyse/hdmi-seq/wandcheck.py shot NAME          # Foto der Wand -> re/captures/weltneuheit/wand-aktuell/NAME.jpg (ansehen!)
```

**Bild steuern** (alles über den Dienst; `h713-tv ctl help` listet es)

```bash
h713-tv ctl off | auto | console            # Konsole erzwingen / Bild folgt dem Signal / Konsole entblanken
h713-tv ctl list | get REGLER | set REGLER WERT   # brightness contrast saturation hue sharpness tnr snr dci black range mode
h713-tv ctl preset standard|cinema|vivid|game|computer|hdr   # Bildmodus + neun Regler der Hersteller-INI
h713-tv ctl aspect auto|proportional|full|16:9|4:3|zoom      # Einpassung (Descriptor-Wort 35), Bild wird neu aufgebaut
h713-tv ctl resync                          # Quelle neu waehlen (SetSource HDMI-1)
h713-tv ctl rpc NAME [ARG...]               # roher Firmware-RPC, nur Diagnose
```

Startoptionen der Unit (`/etc/systemd/system/h713-tv@.service`): `-p PRESET` (Vorgabe `standard`, `none`),
`-g LUT` (Vorgabe `/usr/local/share/h713-tv/gamma-standard.bin`, `none`).

**Zuspieler (Laptop, HDMI-2) umschalten** - Rate ist Pflicht, sonst nimmt xrandr 120-Hz-Varianten:

```bash
bash analyse/hdmi-seq/wechsel.sh 1280x1024 NAME 60.02    # eDP aus, HDMI-2 auf Modus, Register + Ring + Foto
ssh user@192.168.8.162 'DISPLAY=:0 xrandr --output eDP-1 --auto --output HDMI-2 --mode 1920x1080 --rate 60.00 --same-as eDP-1'
```

**Kernel ändern, bauen, einspielen**

```bash
cp -a mainline/patches/kernel patches-snapshots/$(date +%Y%m%d-%H%M)-vor-NNNN     # immer zuerst sichern
#  neue Datei mainline/patches/kernel/NNNN-….patch (diff -u, Pfade a/ b/), Zeile in .../series anhaengen
patch -p1 -d "$(ls -dt mainline/build/linux-6.18.38-*/ | head -1)" --dry-run < mainline/patches/kernel/NNNN-….patch
podman exec -e KERNEL_CONFIG=netboot -e JOBS=16 h713-build bash -lc 'cd /work/mainline && build/build.sh kernel'   # ~2,5 min
T=$(ls -dt mainline/build/linux-6.18.38-*/ | head -1); H=$(basename $T | sed 's/linux-6.18.38-//' | cut -c1-8)
podman exec h713-build bash -lc "cd /work/mainline/build/$(basename $T) && make -s ARCH=arm64 INSTALL_MOD_PATH=/work/mainline/build/modroot.$H modules_install"
rsync -a --delete mainline/build/modroot.$H/lib/modules/6.18.38/ /srv/h713-rootfs/lib/modules/6.18.38/
cp mainline/build/out/h713-kernel-netboot.fit tftp/h713-kernel-netboot.fit && cp mainline/build/out/h713-kernel-netboot.fit tftp/h713-kernel-netboot.fit.$H
#  Kaltstart (TFTP pruefen!), abnehmen, dann: mv tftp/….fit.$H tftp/….fit.GUT-$H; mv mainline/build/modroot.$H mainline/build/modroot.GUT-$H
```

Nur die Module werden vom NFS-Root geladen; das Kernelabbild kommt per TFTP. Ein Treiber-Rebind ohne Kaltstart
(`echo hdmi-rx > /sys/bus/platform/drivers/sun50i-h713-hdmirx/unbind` bzw. `bind`) lädt **kein** neues Modul.

**`h713-tv` ändern, bauen, einspielen** (NFS-Root ist root-owned → vom Board aus)

```bash
make -C userspace/h713-tv cross                                         # Host-Clang gegen /srv/h713-rootfs
ssh root@192.168.8.141 'systemctl stop h713-tv@video1'                   # sonst "text busy"
scp userspace/h713-tv/h713-tv.aarch64-linux-gnu root@192.168.8.141:/usr/local/sbin/h713-tv
scp userspace/h713-tv/h713-tv@.service root@192.168.8.141:/etc/systemd/system/    # bei Unit-Aenderung, dann daemon-reload
scp userspace/h713-tv/99-h713-tv.rules root@192.168.8.141:/etc/udev/rules.d/      # bei Regel-Aenderung, dann udevadm control --reload
scp userspace/h713-tv/README.md root@192.168.8.141:/usr/local/share/doc/h713-tv/
ssh root@192.168.8.141 'cp /usr/local/sbin/h713-tv /root/h713-tv; systemctl start h713-tv@video1'
```

**Messen am Board** (Skripte liegen unter `/root/`, Quellen in `analyse/hdmi-seq/`)

```bash
python3 /root/rd.py 06940824 06940928 05180008 05600044        # Register lesen (ICSC, Capture-Freigabe, Scaler, Chroma-Stride)
python3 /root/ringstat.py 1920 1080 [PITCH]                      # Y/Cb/Cr je Band der Ring-Slots; Cb/Cr 128 = sauber
python3 - <<'EOF'                                                # elog der MIPS-Firmware auf Stufe 5 (bleibt bis zum Kaltstart)
import os,mmap
def wb(a,v):
    fd=os.open("/dev/mem",os.O_RDWR|os.O_SYNC); b=a&~0xfff; m=mmap.mmap(fd,0x1000,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=b)
    w=(a-b)&~3; sh=(a&3)*8; x=int.from_bytes(m[w:w+4],"little"); m[w:w+4]=((x&~(0xff<<sh))|(v<<sh)).to_bytes(4,"little"); m.close(); os.close(fd)
wb(0x4b48be98,0); wb(0x4b48bd9c,5)
EOF
nohup python3 /root/elog_tail.py --hb 0 --poll 1 --kmsg-exclude '.*' > /root/elog-NAME.txt 2>/dev/null &
```

`ringstat.py` und `wechsel.sh` gehen von einem Pitch = Breite auf 16 aufgerundet aus (INCAP `0x924`).
Firmware-Shell: [`98-mips-shell.md`](98-mips-shell.md). Betriebswissen und Fallen: [`97`](97-handoff-20260908.md) §4.

## Bauen

Alles läuft im Wegwerf-Container `h713-build` (Ubuntu 24.04, `/opt/Projekte/h713`
ist dort als `/work` gemountet, `--userns=keep-id`, also bleiben die Dateien
host-owned).

```bash
podman run -d --name h713-build --userns=keep-id \
  -v /opt/Projekte/h713:/work docker.io/library/ubuntu:24.04 sleep infinity
```

Toolchain darin:

```bash
podman exec -u root h713-build apt-get install -y --no-install-recommends \
  clang lld llvm device-tree-compiler swig flex bison u-boot-tools \
  build-essential bc kmod libssl-dev libelf-dev python3-dev git curl \
  ca-certificates xz-utils cpio rsync libgnutls28-dev uuid-dev \
  libncurses-dev pkg-config libusb-1.0-0-dev libfdt-dev python3-capstone \
  python3-setuptools python3-pyelftools
```

(`python3-setuptools` braucht U-Boots pylibfdt-Bau - fehlte im Rezept, 10.09. ergänzt. Nach jedem Neuerzeugen des Containers gehört
auch der LLVM-20-Schritt unten wieder dazu; ein frischer Container hat nur LLVM 18 und bricht bei `u-boot.srec` ab.)

**LLVM 18 reicht nicht** - `llvm-objcopy` kann erst ab 19 SREC ausgeben, U-Boot
bricht bei `u-boot.srec` ab. LLVM 20 aus `apt.llvm.org` genügt, seine gepinnte
22 ist nicht nötig:

```bash
podman exec -u root h713-build bash -c '
  curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key -o /usr/share/keyrings/llvm.asc
  echo "deb [signed-by=/usr/share/keyrings/llvm.asc] http://apt.llvm.org/noble/ llvm-toolchain-noble-20 main" > /etc/apt/sources.list.d/llvm20.list
  apt-get update -qq && apt-get install -y clang-20 lld-20 llvm-20
  for t in clang ld.lld llvm-objcopy llvm-ar llvm-nm llvm-objdump llvm-readelf llvm-strip; do
    ln -sf /usr/bin/$t-20 /usr/local/bin/$t; done'
```

Bauen:

```bash
podman exec h713-build bash -lc 'cd /work/mainline && build/build.sh bl31'
podman exec h713-build bash -lc 'cd /work/mainline && build/build.sh kernel'
podman exec h713-build bash -lc 'cd /work/mainline && \
  build/uboot-build.sh /work/mainline/build/uboot-host hy310_host_defconfig'
```

Image aufteilen und Sektorenzahl bestimmen:

```bash
cd /opt/Projekte/h713/mainline/build/flash-hy310
head -c 32768 host-usb.bin > spl.bin
tail -c +32769 host-usb.bin > uboot-proper.bin
SZ=$(stat -c%s uboot-proper.bin); echo "$(( (SZ+511)/512 )) Sektoren = 0x$(printf %x $(( (SZ+511)/512 )))"
```

## U-Boot-Prompt

### USB

```
usb start                 Bus initialisieren
usb reset                 neu aufsetzen
usb tree                  Baum mit Geschwindigkeiten
usb info                  Geräteklassen und Deskriptoren
ls usb 0:1                FAT-Partition auflisten
fatload usb 0:1 0x50000000 datei.bin
```

### eMMC

```
mmc dev 1                 eMMC wählen
mmc info
mmc part
mmc read  0x48000000 <lba> <blocks>
mmc write 0x48000000 <lba> <blocks>
```

### GPIO

```
gpio status PB5           Zustand lesen
gpio set PB5              auf high - Lüfter und Backlight
gpio set PL3              auf high - USB-/Kameraversorgung
```

**Niemals `gpio clear PB5`.** Der Lüfter stoppt.

### Speicher

```
md 0x04101810 1           Wort lesen
mw.l 0x0709011c 0         Wort schreiben
```

Nützliche Adressen:

```
0x04100420   REG_PHY_OTGCTL, Bit 0 = PHY0 ans MUSB
0x04101054   ehci0 PORTSC, Bit 0 = Gerät angeschlossen
0x04200054   ehci1 PORTSC
0x04101810   pmu0 + REG_HCI_PHY_CTL, Bit 3 = SIDDQ
0x04200810   pmu1 dito
0x0709011c   RTC GP7, die Reboot-Marke
```

### Panel-Leitungen

Die sechs, die der Vendor-Bootloader fährt. Vier davon sind seit dem Build vom
31.08. in der Power-Sequenz; von Hand geht es so:

```
gpio set PH19    panel_power_en
gpio set PH15    panel_gpio_1
gpio set PH8     panel_gpio_2
gpio set PH9     panel_gpio_3
```

PB5 und PH16 setzt U-Boot ohnehin. **`gpio clear` auf keinem davon**, und auf
PB5 schon gar nicht.

### I²C

```
h713_i2c scan                    PH2/PH3, die TWI1-Pins des Vendor-DT
h713_i2c scan <scl> <sda>        andere PH-Pins
h713_i2c read <addr> <count>     lesen ohne Registerschreiben
```

Bitgebangt, ohne CCU-Gate und ohne Devicetree-Knoten - läuft unabhängig vom
Display-Zustand. `0x18` ist der stk8ba58 und der Beweis, dass der Bus geht.

### Display

```
h713_disp init 0x30              hochfahren und anhalten
h713_disp auto 0x30 logo         mit Vendor-Bootlogo
h713_disp auto 0x30 logo x.bmp   mit eigenem BMP, ohne Hash-Prüfung
h713_disp teardown               Scanout stoppen, MIPS parken, Panel-Rail ab
h713_disp scanrate               Zeilen-/Bildrate und echten DCLK messen
h713_disp commstate              CPU_COMM-Transporte lesen
h713_disp calltable              die lebende CPU_COMM-Call-Tabelle
h713_disp fwmd <mips-va> [n]     Firmware-Speicher dumpen, cache-sicher
h713_disp dump                   alle Display-Registerblöcke
```

Testbilder über `panel-test <id> <modus>`:

```
fb-quad          vier Vollton-Quadranten - übersteht Unschärfe, zählt die Kachelung
fb-grid          Rand, Diagonalen, Ecken - braucht ein scharfes Foto
fb-vprobe        acht waagerechte Farbbänder, nur die vertikale Ordnung
fb-hprobe        acht senkrechte Bänder, isoliert die waagerechte Achse
bl-sweep         Weißbild, PWM2/PB4-Duty 100..0 (wirkungslos, siehe 70-sackgassen)
vendor-logo-chroma   das Stock-Logo, hell->rot dunkel->blau
```

`init` ohne `quiesce` lässt die Firmware laufen, veröffentlicht aber **keinen
Inhalt** - Schwarz ist dort das erwartete Ergebnis und kein Befund.

**Vor einem zweiten Lauf Strom ziehen.** Sonst läuft die MIPS weiter und
schreibt in das frisch geladene Image.

### Kernel booten

```
usb start
fatload usb 0:1 0x60000000 h713-kernel.fit
bootm 0x60000000
```

Das FIT **nicht** nach `0x48000000` laden - dorthin wird der Kernel entpackt,
er überschreibt sich beim Auspacken selbst. `inflate() returned -5` und
„Image too large" sind dann irreführend, `CONFIG_SYS_BOOTM_LEN` ist mit 128 MiB
reichlich.

## UART fernsteuern

```bash
tools/uart-capture.py                      Standardsatz Display-Register
tools/uart-capture.py -c 'md.l 0x058c0000 12' -c bdinfo -o /tmp/x.txt
tools/regdiff.py a.txt b.txt               zwei Mitschnitte adressweise vergleichen
```

Spricht den ESP32-Proxy direkt an, ohne pyserial. **Eine laufende `tio`-Sitzung
vorher beenden** (`Strg-t` `q`), sonst teilen sich beide die Leitung.

`-i <sek>` erhöht die Stille, nach der ein Befehl als fertig gilt - nötig für
lang laufende Befehle wie `bl-sweep` oder `h713_disp auto`.

### Am U-Boot-Prompt arbeiten, ohne den Kernel zu starten

```bash
tools/uart-uboot.py catch            Strg-C hammern, am '=> ' anhalten
                                     (Rückgabe 2 = Prompt stand schon, kein Kaltstart)
tools/uart-uboot.py run -c 'h713_disp commdev'
tools/uart-uboot.py chanpid          chan/pid/id für commcall herausziehen
tools/uart-uboot.py elog -o /tmp/e.txt    MIPS-elog über fwmd holen
tools/uart-uboot.py fwdump 0x8b272d9c 4096 -o /tmp/ring.bin
tools/uart-uboot.py vpinit           THal_Vp_Init, Trockenlauf; --go sendet
```

Alle Unterbefehle prüfen zuerst, ob wirklich U-Boot antwortet, und verweigern
den Dienst an einem Linux-Prompt. `elog` liest die Modus-1-Zeiger und holt nur
den beschriebenen Teil des Rings - Adressen aus [63-mips-elog.md](63-mips-elog.md).

**Nach einem von Hand abgesetzten `h713_disp init` nicht `run bootcmd`
benutzen** - darin steckt ein zweites `init`, und es gilt ein Start pro
Stromzyklus. Stattdessen nur den Netboot-Teil:

```
dhcp; tftpboot 0x60000000 192.168.8.104:${bootfile}; bootm 0x60000000
```

## Zwischen Stock und uns umschalten

```
fatload usb 0:1 0x50000000 stock-boot0.bin   → Stock
fatload usb 0:1 0x50000000 spl.bin           → unser
md.l 0x50000000 4                            PRÜFEN, siehe unten
mmc write 0x50000000 0x10 0x40
```

**Die eMMC hat verschiedene Nummern:** Stock `mmc dev 2`, unser `mmc dev 1`.

**Immer den RAM prüfen, bevor geschrieben wird.** Ein `fatload` kann
fehlschlagen und `mmc write` schreibt trotzdem - dann landet uninitialisierter
Speicher im Bootsektor. Erwartete erste Wörter:

```
spl.bin            ea000016 4e4f4765 3054422e …    ("eGON.BT0")
uboot-proper.bin   edfe0dd0 310f0d00 38000000 …    (FDT-Magic)
```

Rettungsanker, falls es doch passiert: boot0 liegt **doppelt**, LBA 16 und
LBA 256. Das BROM weicht auf die zweite Kopie aus.

## Gerät

```bash
ssh root@192.168.8.142    root, id_ed25519
uart                      UART über den ESP32-Proxy auf /dev/ttyACM0
```

**Die Adresse wandert.** `CONFIG_NET_RANDOM_ETHADDR` gibt dem r8152 bei
jedem Start eine neue MAC, also eine neue DHCP-Adresse. Der Eintrag `hy310`
in `~/.ssh/config` zeigt auf die alte `.141`. Aktuelle Adresse findet man
über die offene NFS-Verbindung:

```bash
ss -tn | grep :2049
```

`hexdump` gibt es auf dem Gerät nicht, `dd` und `sha256sum` schon.

## FEL

```bash
cd /opt/Projekte/h713/mainline/build/fel
./sunxi-fel version
./sunxi-fel -p spl /opt/Projekte/h713/mainline/build/uboot-felmmc/spl/sunxi-spl.bin
```

Auf ein FEL-Gerät warten:

```bash
for i in $(seq 1 200); do
  ./sunxi-fel version >/dev/null 2>&1 && { ./sunxi-fel version; break; }
  sleep 3
done
```

## Reverse Engineering

Vendor-U-Boot ist **Thumb-2**, Basis `0x4a000000`, kein Header. `armdis.py` im
RE-Baum disassembliert wortweise und löst Literal-Pools auf:

```bash
podman exec h713-build bash -lc 'python3 /work/re/armdis.py <datei-offset-hex> <anzahl>'
```

Strings mit Adresse finden und ihre Referenzen:

```python
import re, struct
d = open("u-boot.fex","rb").read(); BASE = 0x4a000000
o = d.find(b"config usb clk ok")
refs = [m.start() for m in re.finditer(re.escape(struct.pack("<I", BASE+o)), d)]
```

IDA-Datenbank zu ihrem Binary zuordnen - der Input-md5 steht in der `.i64`:

```python
import re
TAG = b'\x01\x00\x16\x10\x00'
blob = open("datei.i64","rb").read()
m = re.search(re.escape(TAG), blob)
print(blob[m.end():m.end()+16].hex())
```

## RE-Baum prüfen

```bash
python3 /opt/Projekte/h713/re/verify.py          Integrität und Vollständigkeit
/opt/Projekte/h713/re/check-boot0.py <datei>     eGON-Prüfsumme und Zuordnung
```
