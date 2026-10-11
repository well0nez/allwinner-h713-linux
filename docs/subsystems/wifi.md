# Wi-Fi: AIC8800D80 over SDIO

The AIC8800D80 gives the projector an access point or a station, chosen and configured in
`/etc/h713/wifi.env` and brought up by `h713-wifi.service` - nothing to build for a channel or
password change. The driver is out-of-tree: two modules (`aic8800_bsp`, `aic8800_fdrv`), built and
vermagic-checked against the running kernel, installed next to the in-tree modroot rather than in it.

## Driver

Carried as a patch series against a pinned vendor tarball (`radxa-pkg/aic8800`, rebased onto release
`2026_0123`) the same way the kernel itself is carried - `mainline/patches/aic8800/series`, and never
applied to the kernel tree. On top of the upstream rebase it adds the mainline-sunxi build target, the
H713 power-on sequencing (`wlan_regon`, hardcoded to GPIO 385 - PM1 on the R_PIO bank, confirmed
correct for this board after a false lead on 12.09.), SDIO-clock and chip-up-timeout tuning, and a
guard so the 1.9 MB proprietary firmware-as-C-array blob is never built in. Since `aic8800-0007` the
number comes from the device tree instead, with the module parameter kept as an override; the patch is in
the series and builds, but the Wi-Fi run that proved the radio predates it, so that particular path has
not been exercised on hardware.

## Firmware

Never shipped in the image. `h713-extract` pulls the 13-file SDIO firmware set from **the user's own**
device dump (`vendor:/etc/firmware/aic8800d80/`) into `/lib/firmware/aic8800_fw/SDIO/aic8800D80/`, the
same way it pulls the HDCP keys and the display firmware. No dump directory means no Wi-Fi chip on
that unit - not an error. Measured 12.09.: this stock set brings the chip up with the rebased driver
(`wlan0`, `phy0`); the differently-sourced firmware set that used to live in this repo's legacy tree
is not needed. That closed the licensing question that had kept Wi-Fi out of the release rootfs
(`analyse/boot/wlan-aic8800-messung-20260912.txt`).

## Regulatory domain

The wiphy is self-managed, so cfg80211's `regulatory.db` never governs it. The driver carries its own
table (185 countries) and selects from it with a `default_ccode` module parameter, exposed by patch
`aic8800-0006` - before that patch it was compiled in as `"00"`, a permissive world entry wide enough
to cover DFS and weather-radar spectrum with no DFS restriction. `h713-wifi` now sets the domain at
load time from `country=` in `wifi.env`; the shipped default is `DE` - a real domain, even if it turns
out to be the wrong one for wherever the device actually is, is judged safer than that permissive
fallback.

## What was measured

12.09.2026, on that week's acceptance build: an access point named `h713` running under the `DE` domain
on the self-managed phy, with the firmware the installer copied in from the user's own dump
(`doku/60-offen.md`, the acceptance run of that day). Station mode was verified the same day against a
real network (DHCP address, internet through `wlan0`).

## Bluetooth

The same chip, the same module family, one more UART. What ships:

- **Firmware.** The Bluetooth patch set (`fw_patch_8800d80*.bin`, `fw_adid_8800d80*.bin`) is part of the
  Wi-Fi firmware in the owner's dump; the SDIO driver uploads it at every boot (`aicbt_patch_table_load`
  in `dmesg`) and power-cycles the chip on the way. There is no separate Bluetooth firmware file and no
  Bluetooth-only power or reset line - which is why Bluetooth needs Wi-Fi's modules loaded (`h713-wifi`
  with `mode=sta` or `mode=ap`; `mode=off` switches both off).
- **Host side.** `h713-bluetooth.service`: `hciattach` on the 8250 port of `2500400.serial` (UART1,
  1500000 Bd, hardware flow control), bluez on top. `/etc/bluetooth/main.conf` narrows the LE scan window
  (96/16) so a scanning controller does not starve the Wi-Fi radio it shares the antenna with: measured on
  the HY310 with the remote connected, 97 of 97 1400-byte pings and 8 MiB in 3.5 s over Wi-Fi.
- **The stock remote.** BLE HID (`1d5a:c081`). `h713-remote-pair` pairs it: hold Left + Right until the
  LED blinks, the unit `h713-remote-pair.service` scans and bonds. After that it reconnects on any key
  press, also after a reboot. It remembers one box only: paired with another box since, it no longer
  reconnects here and its keys come over IR - `h713-remote-pair forget`, then Left + Right (measured on the
  HY300PRO-G-EU, `doku/195`). The kernel's `hid-h713-remote` fixes the remote's consumer report (its
  report 3 is one byte shorter than the descriptor says) and maps Home and the two focus keys.
- **`h713-bt-reset`.** The controller keeps its state across attaches: the kernel's `hci_uart` sends no
  HCI_Reset at init and its close-time reset never reaches the wire once `hciattach` has exited (that is
  the `hci0: Opcode 0x0c03 failed: -110` line in the journal on every stop - harmless). Without a reset the
  next attach inherits the old LE scan and stops at `Opcode 0x2010 failed: -16` (Command Disallowed). The
  helper sends HCI_Reset as a raw H4 frame on the bare UART before `hciattach` and after it exits, as the
  vendor's `libbt-aic` does around every session, and the unit only counts as started once `hci0` is UP.
  Details and the device log: working journal `FB-BTRESET/REPORT.txt` in the working tree, not in this repo.

Known and open: after a warm reboot the first HCI command sometimes goes unanswered (the helper retries;
the cause is not found). **In `main` since 11.10.2026** the IR receiver works too (kernel `0252`-`0254`, `doku/193`): all 14
keys; the mouse key and the microphone key both send `0x66` over IR because over IR they only ask for the Bluetooth
pairing - their own functions (the air mouse, the voice stream) run over Bluetooth only. *Superseded 11.10.2026:* "The IR
receiver is not used: the same remote sends the same NEC code for the mouse key and the microphone key, so the infrared
path is parked." On the HY300PRO-G-EU the first attach after
a cold start stalled at HCI command 0x1003 before `h713-bt-reset` existed; with it, that board has not been
tried yet. The remote's keys arrive as input events; in `v0.96-beta` nothing acts on them except Power, which logind turns
into a shutdown - in `main` [h713-keys](../tools/h713-keys.md) does (volume, mute, focus) and [h713-osd](../tools/h713-osd.md)
shows it.

## Using it

Set `mode`, `ssid`, `password`, `channel` and `country` in `/etc/h713/wifi.env`, before or after the
build. See [`docs/tools/h713-wifi.md`](../tools/h713-wifi.md) for the file format and the service.

## Limits, honestly

- Station mode joined a real WPA2 network on 2026-09-12 (DHCP, internet through `wlan0`). It picked the 2.4 GHz BSS of a dual-band network; whether it prefers 5 GHz when both are visible is untested.
- The SDIO clock runs at 25 MHz, downclocked from the vendor's 150 MHz by a patch carried forward
  from an earlier tree without a confirmed reason on this chip; **unverified** whether it is still
  needed now that the driver has FIFO/DMA-reset recovery.
- `wireless-regdb` ships for a correct global regulatory database, but the self-managed aic8800 never
  consults it.

## Measured

Access point, 2.4 GHz channel 6, one client at −50 dBm (2026-09-12): link 72.2 MBit/s tx / 52.0 MBit/s rx
(MCS 7 / MCS 5), **5.7 MB/s** of real throughput over SSH, DHCP and WPA2 without complaint.

Latency (2026-10-06, the shipped `wifi.env`, a laptop as the client at −47 dBm, 72.2 MBit/s, the radio's
power saving on as shipped): 100 pings every 0.2 s 1.2-124 ms, 60 pings every second 2.6-14 ms (median
3.4 ms) - no spike. In station mode on a home network 1-59 ms.
*Superseded (2026-10-06):* on 2026-09-12 ping times in the AP session swung between 3 ms and 2 s; that
did not come back with today's image.

Details: `doku/60-offen.md` (§WLAN und Bluetooth, §WLAN vor dem Release), `doku/134` (remote and coexistence tests, 03.10.2026),
`analyse/boot/wlan-aic8800-messung-20260912.txt`.
