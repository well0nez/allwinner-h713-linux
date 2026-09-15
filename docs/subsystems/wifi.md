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

12.09.2026, on the v0.8 acceptance image: an access point named `h713` running under the `DE` domain
on the self-managed phy, firmware loaded from the extracted placeholders (`doku/60-offen.md`, the v0.8
acceptance run). Station mode has not been tried on this build.

## Bluetooth is missing

Not a driver problem - it is the same `aic8800` chip and the same module family. The Bluetooth
firmware (`fmacfwbt_*`) does not exist in the vendor dump, only in an SDK-sourced set carried in
another tree under an unclear license; without firmware, `bluez` would be a daemon with no radio
behind it. Reasoning kept next to the package list itself:
`rootfs/packages.txt`.

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
(MCS 7 / MCS 5), **5.7 MB/s** of real throughput over SSH, DHCP and WPA2 without complaint. Ping times in
the same session swung between 3 ms and 2 s - throughput is unaffected, and the cause is unexamined; power
saving on the radio is the obvious suspect.

Details: `doku/60-offen.md` (§WLAN und Bluetooth, §WLAN vor dem Release),
`analyse/boot/wlan-aic8800-messung-20260912.txt`.
