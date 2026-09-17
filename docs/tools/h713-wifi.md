# h713-wifi

`h713-wifi` brings the device's Wi-Fi radio up the way `/etc/h713/wifi.env` describes it - access point,
client, or off - once at boot and again on every `systemctl restart h713-wifi`. It is the only supported
way to change how the AIC8800D80 chip is used: editing `hostapd`/`wpa_supplicant` files by hand does not
survive a restart, because the service regenerates them from `wifi.env` every time.

## `/etc/h713/wifi.env`

One `key=value` per line, no quotes, no backslashes in `ssid` or `password`. The file is parsed, never
sourced, so a typo is an error message, not an executed command.

| Key | Meaning |
|---|---|
| `mode` | `ap` (own network, the default), `sta` (join another network), or `off` (radio stays powered down) |
| `ssid` | The access point's own name, or the name of the network to join in `sta` mode |
| `password` | WPA2 passphrase, 8-63 characters. `ap` refuses to start without one; `sta` accepts an empty value for an open network |
| `band` | `2.4` (longer range, every client supports it) or `5` (about three times the throughput - 13 vs. 5 MB/s, measured on the device - over a shorter range, only the DFS-free channels). `ap` only |
| `channel` | 1-13 on `band=2.4`, one of 36/40/44/48 on `band=5`. `ap` only |
| `country` | ISO-3166 regulatory domain (`DE`, `US`, `GB`, …); sets which channels and transmit power the radio may use for the country the device actually stands in |
| `ap_ip` | The device's own address on the network it opens |
| `ap_dhcp_start`, `ap_dhcp_end` | The address range handed to clients by the built-in DHCP server; must share `ap_ip`'s /24 |

**The shipped default is public.** Every device with this image starts as an access point named `h713`
with the password `magcubic` until someone changes it - the same two values are printed in this
document. Anyone within radio range can reach the device's SSH server until `password` is changed in
`/etc/h713/wifi.env`; do that before the device stands anywhere it isn't only you.

## Subcommands

| | |
|---|---|
| `up` | read and validate the file, load the driver, start the access point or the client |
| `down` | stop the running daemons, take `wlan0` down |
| `status` | show what is currently running: driver, interface, daemons, DHCP leases |
| `check [FILE]` | validate only, no side effects - the same check `build-rootfs.sh` runs on a custom `wifi.env` before it goes into an image |

The parser's edge cases - control characters, an injected shell command in a value, a wrong DHCP subnet,
CRLF line endings from a Windows editor - are covered by an automated suite of good and bad files
(`rootfs/tests/h713-wifi-check.sh`), run on the same code path used on the device.

`h713-wifi.service` is a oneshot unit with `RemainAfterExit`: `up` on start, `down` on stop, no restart on
failure. A broken `wifi.env` is a configuration error for whoever edited it to fix and re-trigger, not a
loop to retry.

`country` also gates the driver itself: `aic8800_fdrv` loads with `default_ccode=<country>`, and if a
loaded module's domain differs from the file, the module is unloaded and reloaded rather than changed
live - the self-managed wiphy only takes the domain at load time.

## Limits

Access point mode with `country=DE` and station mode against a real network are both verified on
hardware, 12.09.2026. Still open: whether a phone accepts the access point's DNS behaviour (STATUS.md).
The AIC8800D80 firmware is not shipped: the image carries only its target directory, and `h713-install`
copies the files out of your own dump (or off a device already running this layout) into it. A board
without the chip is told so and the group is left out, and a device missing that firmware fails with a
clear error instead of a silent non-start.

Details: doku/60-offen.md.
