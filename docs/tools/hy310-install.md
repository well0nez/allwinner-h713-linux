# hy310-install

`hy310-install` turns a stock HY310/L018 into this system, running entirely on the user's PC — nothing
proprietary needs to be downloaded, and nothing needs to run on the device itself beyond U-Boot. It talks
to the eMMC as a plain USB block device, so it needs Python 3.9+ and no other package, on Linux or
Windows.

## The path

1. **FEL.** Hold reset, plug in power. No case to open, no pads, no soldering.
2. **`hy310-install` loads U-Boot over USB** (`sunxi-fel uboot`, a few seconds, no byte written to the
   eMMC yet) and has it export the eMMC as a USB mass-storage drive. From here on there is no way back to
   FEL except cutting power — that is not a limitation, it is the point: once writing is done, the next
   step is a cold start anyway.
3. **A dump of the eMMC is pulled first**, always, before any write: the small dump (49 MiB — Secure
   Storage, `private`, `Reserve0` — the parts no firmware image can replace) or the full 7.3 GB dump.
   There is no flag to skip it; the choice is which size, not whether.
4. **The proprietary parts are extracted from that dump** with `h713-extract` — not from a downloaded
   firmware image.
5. **The image's placeholders are filled** with the extracted files and, if given, the user's SSH public
   key, then **written** to the eMMC.
6. **Verified**: a checksum over the dump before extraction starts, and byte-for-byte spot checks (GPT,
   Secure Storage, a random region) after writing. A mismatch at either point is reported as a clear
   failure — "do not restart, ask first" — never as a quiet success.

Power off and back on afterward; the device no longer boots by itself on power-up, by design
([docs/uboot/power-gate.md](../uboot/power-gate.md)).

## Options

| Flag | What it does |
|---|---|
| `--abbild TABLE\|DIR\|FILE` | the image to write: the `.tabelle.json` from `hy310-mkimage`, its directory, or a single `.img` |
| `--vendor DIR` | a finished `h713-extract` output; without it, the tool extracts from the full dump itself |
| `--authorized-key FILE` | public SSH key for `/root/.ssh/authorized_keys`; without one there is no SSH access, only the serial console |
| `--abzug klein\|voll` | pick the dump size without being asked |
| `--nur-abzug` | dump only, write nothing |
| `--restore ABZUG` | write a previous full dump back |
| `--restore-stock UPDATE.IMG` | reconstruct the stock partition table and write the vendor firmware back |
| `--env-neu` | do **not** carry `h713_gate`/`h713_boot` over from the old U-Boot environment (see below) |
| `--ohne-erkennung` | skip device recognition — development only, disables the guard against writing to an unrecognised firmware |
| `--dry-run` | plan the run without writing |

## Safety nets

Before the first byte is written, the tool prints the beta warning and requires **`JA` typed out** —
not a `[y/N]` prompt — because a fast keypress is exactly the failure mode a full write should not allow.

The GPT partition names decide what the tool is looking at: names starting `hy310-` mean the device
already runs this system, anything else with a stock `bootloader_a`/`super` layout means stock Android.
Anything else is refused outright rather than guessed at. On a reinstall over our own layout, the intent
keys `h713_gate` and `h713_boot` are copied from the old U-Boot environment into the new one — everything
else in the environment comes from the image being installed, unchanged, so a stale setting from a much
older install can't silently survive an upgrade.

The Secure Storage region (LBA 12288–14335: HDCP keys, Wi-Fi/Bluetooth MAC addresses, serial number) is
never written, whatever you pass — the image itself has a gap there, so even a raw `dd` from someone
bypassing this tool cannot reach it (see `hy310-mkimage`).

## `--restore-stock`

Rebuilds the original GPT and writes the vendor `update.img` back byte-for-byte, for returning a device
to Android. Like every other write path it leaves the Secure Storage region untouched and asks for the
typed `JA` confirmation first.

Details: doku/110-plan-installationsweg.md.
