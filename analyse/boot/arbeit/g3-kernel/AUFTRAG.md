# G3 — Kernel: Einschalttaste als `gpio-keys` (Plan 103 §2.4), Bericht S38

Lies zuerst `../REGELN.md`. Original nur lesen: `mainline/build/linux-6.18.38-d5fd82a7*/` (gebauter Baum mit unserer Serie bis `0138`),
`mainline/patches/kernel/` (Serie, `series.txt` hier kopiert). Kopien: `kopie/sun50i-h713.dtsi`, `kopie/sun50i-h713-hy200-qz713df-a1.dts`.

## Zu liefern
1. DTS: Knoten `gpio-keys` mit **PL4** (`&r_pio 0 4 GPIO_ACTIVE_LOW`), `linux,code = <KEY_POWER>`, `debounce-interval = <50>`, `wakeup-source`,
   Label `power`. Prüfe, ob `r_pio` in unserem Baum als GPIO-Controller nutzbar ist (Pinctrl `pinctrl-sun50i-h713-r.c`, Patchserie) und ob PL4 frei
   ist (nicht von `standby_param`/anderem Knoten als GPIO reserviert). Kein Pull (extern vorhanden); falls die Pinctrl einen Pinconf-Knoten braucht,
   `bias-disable`.
2. Kein LED-Knoten (LED folgt PB5).
3. Prüfe `CONFIG_KEYBOARD_GPIO` in `mainline/patches/kernel/board/hy200_qz713df_a1_defconfig` bzw. dem Defconfig-Patch der Serie; wenn nicht gesetzt,
   in den Patch aufnehmen (`=y`).
4. systemd: Standard `HandlePowerKey=poweroff` in logind — prüfe, ob unser Netboot-Rootfs (`/srv/h713-rootfs/etc/systemd/logind.conf`, nur lesen)
   etwas anderes setzt; empfiehl ggf. eine Drop-in-Datei (nur als Datei im Paketordner liefern, nicht installieren).
5. Patch `patches/0139-arm64-dts-h713-power-key-on-pl4.patch` im Stil der Serie (unified diff gegen `a/arch/arm64/boot/dts/allwinner/…`, mit
   Kopftext wie die Nachbarn `0138`), Bericht `doku/nachtlog/S38-kernel-power-key.md` mit Testrezept (`evtest`/`libinput`-frei: `cat /dev/input/event*`
   oder `hy310-tv`-unabhängig per `/sys/class/input`), offene Annahmen.
