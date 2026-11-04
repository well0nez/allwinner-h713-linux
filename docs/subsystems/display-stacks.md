# Display stacks: vendor or clean, per boot

The picture can run on one of two stacks, chosen per boot by the U-Boot environment key `h713_display`:

- **vendor** (the default): U-Boot starts the vendor's `display.bin` on the display MIPS, and Linux talks to it through
  `cpu_comm` (`sun50i-h713-afbd`, `sun50i-h713-mips`, `sun50i-h713-hdmirx`, `sun50i-h713-msp`; [display](display.md),
  [MIPS](mips.md), [HDMI input](hdmi-in.md)). Everything the release offers runs here.
- **clean**: no display firmware at all. U-Boot sets the panel up and shows the logo with the MIPS held in reset, and the
  clean-room driver `h713_drm` (repository `cleanroom-h713`, [cleanroom](../cleanroom.md)) drives the planes, the picture
  controls and the HDMI receiver itself. `h713-tv` and `h713-warp` find it by its receiver node `h713-hdmirx-clean`
  ([h713-tv, "The clean stack"](../tools/h713-tv.md#the-clean-stack), which also lists what this stack still lacks:
  HDMI audio, HDCP, sources other than 1080p60, colour management, aspect and zoom, popups over the picture).

```
h713-display status                       # which stack runs, which the next boot runs, whether h713_drm can load
h713-display set clean                    # the clean stack from the next boot on (refused where it cannot run)
h713-display set clean --kernel RELEASE   # ... judged against the kernel a one-shot boot path runs next
h713-display set vendor                   # back to the vendor stack from the next boot on
```

On the device, as root. `set` writes the key with `fw_setenv`; nothing changes before the reboot.

## What each stack boots

| | vendor (`h713_display=vendor`, unset, or anything but `clean`) | clean (`h713_display=clean`) |
|---|---|---|
| U-Boot | `h713_disp init ${h713_project} logo` - as before the key existed | `h713_disp init ${h713_project} noboot logo`: the panel, its timing and the logo, the MIPS in reset ([commands](../uboot/commands.md)) |
| kernel command line | before + `module_blacklist=h713_drm` | before + `h713.display=clean module_blacklist=hy310_cpu_comm,sun50i_h713_hdmirx,sun50i_h713_mips,sun50i_h713_msp,sun50i_h713_afbd` |
| display driver | `sun50i-h713-afbd` and the rest, by the device tree, the receiver by `h713-hdcp-key.service` | `h713_drm`, loaded by `h713-display.service` after `sun50i-h713-arisc` (its EDID and hot-plug provider) |
| `h713-hdcp-key.service` | runs (the HDCP 2.2 key, then the receiver) | skipped: `ConditionKernelCommandLine=!h713.display=clean` - its `modprobe sun50i-h713-hdmirx` would pull in `cpu_comm` and start the MIPS |
| `h713-tv-rescue.service`, `h713-sleep-pre/post.service` | as before | skipped by the same condition: there is no MIPS to reload or to wake (standby is not offered on a release anyway; on a `--standby` image a clean boot loses sleep-post's Wi-Fi check with it) |
| `h713-display.service` | skipped (`ConditionKernelCommandLine=h713.display=clean`) | `h713-display load` |
| `h713-tv@` | started by the vendor receiver's node | started by `h713-hdmirx-clean`'s node (the same rule, `99-h713-tv.rules`) |

`module_blacklist=` and not a `modprobe.d` blacklist: the kernel's list refuses a module also as another one's
dependency and when a unit asks for it by name (`hdmirx` pulled `cpu_comm` in, and `cpu_comm` started the MIPS itself,
`doku/227`). `h713.display=clean` is the word userspace reads; the kernel takes it for a parameter of a module that does
not exist and ignores it.

**The vendor stack stays as it was.** With the key unset or `vendor` - every device that never ran `set clean` -
U-Boot runs the identical `h713_disp init ${h713_project} logo`, and the kernel command line is the old one plus the one
word `module_blacklist=h713_drm`, which refuses a module no release image carries. No unit, module option or file of the
vendor path changed: the only edits to its units are conditions that are true on every boot without
`h713.display=clean`. `release/check-display.py` runs the shipped `bootcmd` through a model of U-Boot's shell for every
value of the key on both boot paths and refuses an image where the two stacks' command lines differ in anything but
those words; `release/tests/test_check_display.py` holds the vendor line against the one before the key existed.

## The switch

`h713_display` lives in the U-Boot environment because U-Boot decides whether `display.bin` runs at all, before any file
of the rootfs is read. `bootcmd` puts the stack's words into `h713_display_args` at every boot, and `boot_emmc` and
`boot_net` append that variable to their `bootargs` ([environment](../uboot/environment.md)). A boot path of a device's
own (`boot_rust`, [kernel-rust](../kernel-rust.md)) has to append it too, or a clean boot gets the clean U-Boot half and
the vendor kernel half - the vendor drivers without `display.bin`.

`h713-install` carries `h713_display` over a reinstall like `h713_gate` and `h713_boot`
(`installer/h713/env.py` `ENV_CARRY_OVER`); everything else of the environment is the new image's.

**What `set clean` refuses**, each with its reason, writing nothing:

- a kernel that cannot load `h713_drm`: no `h713_drm` in `/lib/modules/<release>/modules.dep` (the release kernel has
  none until it is built with `CONFIG_RUST`, below), or one whose `vermagic` is another kernel's or differs from
  `sun50i-h713-arisc`'s (the clean repository's 7.3.1-rustbench module copied into the release tree). The kernel is the
  running one, or the one `--kernel` names for a one-shot boot path into another;
- a missing `/lib/firmware/h713-mips/database.TSE` (no picture without it; the other files only cost a feature and are
  named as notes);
- a saved environment whose `bootcmd` does not read `h713_display` (one of an older U-Boot, or a `bootcmd` set by hand,
  such as the HY320's `h713_conlog` one), or whose boot path (`boot_${h713_boot}`) does not append
  `${h713_display_args}`;
- an environment `fw_printenv` cannot read (`set vendor` refuses that one too): `fw_setenv` on it would write an
  environment of this key alone, and U-Boot would stop at its prompt.

**When the clean stack cannot run after all** - a reinstall carried `clean` onto an image whose kernel has no
`h713_drm`, or `modprobe` fails - `h713-display load` sets `h713_display` back to `vendor` and its unit fails
(`systemctl --failed`, `journalctl -u h713-display`: "the clean stack cannot run on ...: ...; h713_display set back to
vendor"). That boot shows the logo and no picture; the next boot is the vendor stack.

## Loading h713_drm

`h713-display.service` (sysinit, after `local-fs.target` and `/boot`) runs `h713-display load` on a clean boot:
`modprobe sun50i-h713-arisc`, then `modprobe h713_drm`, with `bench=1` when the device tree has no enabled node
`allwinner,sun50i-h713-display-engine` - the release trees have none yet, and the driver then registers the same
resources itself (no clocks, no reset). Its options are `/etc/modprobe.d/h713-drm.conf`:

| option | value | why |
|---|---|---|
| `fw`, `pq_fw`, `gamma_fw`, `logo_fw` | `h713-mips/database.TSE`, `h713-mips/pq_custom.TSE`, `h713-mips/ProjectID_0x0030.TSE`, `h713-mips/LogoRegData.bin` | the owner's display files where U-Boot reads them: `/lib/firmware/h713-mips` is a link to `/boot/mips` (hy310-boot). `/lib/firmware/h713/` belongs to the installer alone (the image's blob guard refuses it) |
| `edid_fw` | `hy310-edid.bin` | the installer's `/lib/firmware/hy310-edid.bin`, served through the ARISC on the HDMI socket |
| `hdmi_port`, `logo_project` | `1`, `0x30` | the HY320's socket in the provider's numbering and its project id |
| `ring_base` | `0x4b100000` | the capture ring in the no-map region `mips-firmware@4b100000`, unused without `display.bin` |
| `restore_logo` | `1` | an `rmmod` puts the boot logo back rather than a black panel |

## What depends on the kernel

The switch, the userspace half and the gate are in place; a release image still cannot run the clean stack, and
`h713-display set clean` says so on it:

- **`CONFIG_RUST` in the release kernel**, and `h713_drm` built in that tree (`CONFIG_DRM_H713=m`; the module is a C shell
  with a Rust hardware layer). Until then the module exists only for the 7.3.1-rustbench kernel (`cleanroom-h713`,
  `drivers/target/kmod/7.3/h713-drm/h713_drm.ko`, built with the bench mode) and loads only there. Once the release tree
  builds it, `release/check-display.py` also checks that its `vermagic` is the image's kernel's.
- **The device tree node** (`drivers/h713-drm/dts/sun50i-h713-hy320-display.dtso`): with it the driver holds its clocks
  and power domains and `h713-display load` passes no `bench=1`.

## Device test

On the HY320 (the only board the clean driver has run on), with a 1080p60 source on HDMI. The test boots the
7.3.1-rustbench kernel once, on the clean stack, and comes back to the release kernel on the vendor stack by itself.

**0. Before.** On the release image, vendor stack: `cat /proc/cmdline > /root/cmdline-before; fw_printenv >
/root/env-before; lsmod > /root/lsmod-before`.

**1. The pieces.** From an image built with this change, or by hand from the repository:
`rootfs/overlay/usr/local/sbin/h713-display` -> `/usr/local/sbin/`, `rootfs/overlay/etc/systemd/system/h713-display.service`
and `h713-hdcp-key.service` -> `/etc/systemd/system/`, `userspace/h713-power/h713-tv-rescue.service` ->
`/etc/systemd/system/`, `rootfs/overlay/etc/modprobe.d/h713-drm.conf` -> `/etc/modprobe.d/`; then
`ln -s /boot/mips /lib/firmware/h713-mips`, `ln -s ../h713-display.service /etc/systemd/system/sysinit.target.wants/`,
`systemctl daemon-reload`. And the environment of this U-Boot (the U-Boot binary itself is unchanged; the lines are in
`board/sunxi/hy310.env`, or `u-boot-initial-env` of a build): `fw_setenv` `bootcmd`, `boot_emmc`, `boot_net` with the new
values and `fw_setenv h713_display vendor`. For U-Boot's own record of `noboot` on this board without a UART, put
`h713_conlog 0x45000000; mmc dev 1; mmc write 0x45000000 0x2800 0x400;` after the `fi;` of `bootcmd`
([HY320](../../boards/hy320/README.md), "U-Boot's console without a UART").

**2. Vendor, unchanged.** `reboot`. Proof: `/proc/cmdline` is `cmdline-before` plus ` module_blacklist=h713_drm`;
`h713-display status` says `running: the vendor stack ..., sun50i-h713-afbd loaded`, `next boot: the vendor stack
(h713_display=vendor)` and `h713_drm on this kernel (6.18.38): no - ... CONFIG_RUST ...`; `systemctl show -p
ConditionResult h713-display` = `no`, `h713-hdcp-key` active (exited); `h713-tv@video1` shows the picture as before.

**3. The refusal.** `h713-display set clean` -> exit 1, `not clean: the kernel 6.18.38 has no h713_drm ...`; `fw_printenv
h713_display` still `vendor`. With the clean repository's module copied into the release tree for a moment
(`/lib/modules/6.18.38/extra/`, `depmod`): `... was built for the kernel 7.3.1-rustbench, this one is 6.18.38 (vermagic
mismatch)`; remove it again and `depmod`.

**4. The module and the one-shot path.** `h713_drm.ko` to `/lib/modules/7.3.1-rustbench/extra/`, `depmod -a
7.3.1-rustbench`; `ls -L /lib/firmware/h713-mips/{database,pq_custom,ProjectID_0x0030}.TSE /lib/firmware/hy310-edid.bin`.
Then

```
fw_setenv boot_rust73 'setenv h713_boot emmc; setenv h713_display vendor; saveenv; wdt dev watchdog@2051000; wdt start 16000; if ext4load mmc 1:5 0x60000000 h713-kernel-rustbench73.fit; then setenv bootargs "${bootargs_base} loglevel=4 root=PARTLABEL=hy310-rootfs rw ${h713_display_args}"; bootm 0x60000000; fi'
fw_setenv h713_boot rust73
h713-display set clean                                # refused: still judged against the running 6.18.38
h713-display set clean --kernel 7.3.1-rustbench       # h713_display = clean, from the next boot on
h713-display status                                   # next boot: the clean stack (h713_display=clean)
reboot
```

`bootcmd` has turned `h713_display` into this boot's words before `boot_rust73` runs, so resetting the key there makes
the boot after it the vendor one again, as `h713_boot`.

**5. Clean.** Proof, each line for one piece:

| piece | command | expected |
|---|---|---|
| kernel and words | `uname -r; cat /proc/cmdline` | `7.3.1-rustbench`; `... h713.display=clean module_blacklist=hy310_cpu_comm,...,sun50i_h713_afbd` |
| no firmware path | `lsmod \| grep -E 'afbd\|hdmirx\|cpu_comm\|mips\|msp'`; `ls /sys/bus/platform/drivers/ \| grep -E 'mips\|cpu_comm'` | nothing |
| U-Boot `noboot` (with `h713_conlog`) | `dd if=/dev/mmcblk0 bs=512 skip=10240 count=1024 \| strings \| grep 'H713 disp'` | `H713 disp: MIPS held in reset (noboot) ...` |
| the load | `journalctl -b -u h713-display`; `lsmod \| grep -E 'h713_drm\|arisc'` | `h713_drm loaded after sun50i-h713-arisc (bench=1: no device tree node ...)`; both modules |
| its options and files | `grep . /sys/module/h713_drm/parameters/{fw,edid_fw,hdmi_port}`; `dmesg \| grep -E 'TSE\|EDID\|provider'` | the values of `h713-drm.conf`; `h713-mips/database.TSE loaded`, `provider: EDID (hy310-edid.bin) served on port 1` |
| skipped units | `systemctl show -p ConditionResult h713-hdcp-key h713-tv-rescue`; `ls /run/hy310/firmware` | `no` for both; no such directory (the key never left the storage) |
| picture | `journalctl -b -u 'h713-tv@*' \| head`; `h713-tv ctl status` | `stack clean: h713-drm + h713-hdmirx-clean ...`; `hdmi capturing, 1920x1080 ...` - then the steps of [h713-tv, "Device test on a clean-stack boot"](../tools/h713-tv.md#device-test-on-a-clean-stack-boot) |
| the way back is set | `h713-display status`; `fw_printenv h713_boot h713_display` | `running: the clean stack ..., h713_drm loaded`, `next boot: the vendor stack (h713_display=vendor)`, `a reboot switches to the vendor stack`; `emmc`, `vendor` |

**6. The safety net** (one dark boot; optional). On the release kernel: `fw_setenv h713_display clean` (past the tool's
checks), `reboot`. The logo stays, no picture; over ssh `systemctl --failed` names `h713-display.service`,
`journalctl -u h713-display` says `the clean stack cannot run on 6.18.38: the kernel 6.18.38 has no h713_drm ...;
h713_display set back to vendor`, `fw_printenv h713_display` = `vendor`. `reboot`: the vendor stack with its picture.

**7. Back.** `reboot` onto the release kernel: step 2's proofs again, `/proc/cmdline` = `cmdline-before` plus
` module_blacklist=h713_drm`. `saveenv` in `boot_rust73` saved U-Boot's runtime variables too: `fw_setenv
h713_display_args`, then the list of [kernel-rust](../kernel-rust.md) ("One-shot boot"); `fw_printenv` against
`env-before` then differs by the new `bootcmd`, `boot_emmc`, `boot_net`, `h713_display` and `boot_rust73`.

Host tests: `rootfs/tests/test_h713_display.py` (the tool against a made-up root and environment),
`release/tests/test_check_display.py` (the gate, with the board environment and the overlay's files),
`installer/tests/test_env_from_device.py` (the carry-over). Not run on a device yet.
