# crust changes for the H713 (the ARISC firmware)

**The patch files here are generated, not maintained** - the same rule as
[`uboot-h713/`](../uboot-h713/README.md) and [`tfa-h713/`](../tfa-h713/README.md):
`git format-patch --no-signature 499a362645e6..<head>` in a checkout of the crust fork (branch `h713`,
base is upstream crust's `master` after v0.6). `SERIES.txt` names base, head and count and is the only
thing that says which fork commit this mirror stands on. Whoever wants to change something changes the
fork and has the mirror generated again.

Verified the way a mirror should be: applying all 34 patches onto the base produces a tree with the same
hash as the fork head (`12f593ac4c2a`, 07.10.2026).

**Not published yet.** The fork has no public repository so far, and there is no submodule
`mainline/external/crust`; `release/build-all.sh` takes the checkout from `CRUST_SRC=<dir>` until there
is one, and its stamp says so. The contract-v5 work of the release design (watchdog net, standby phases,
counters) is a second set of commits on the same branch and comes into this mirror when it is merged;
`SERIES.txt` will then name the new head.

## What it is

[crust](https://github.com/crust-firmware/crust) is free firmware for the small OR1K core ("ARISC",
"AR100") of Allwinner SoCs, BSD-3-Clause or GPL-2.0 at the user's choice. This series ports it to the
H713 and gives it the vendor firmware's message contract, so the Linux driver and BL31 can talk to it as
they did to the vendor's `scp.bin`:

- **`0001`** the platform with the vendor's contract: the HDMI front end (hot plug, EDID store) and the
  contract page in SRAM A2 that Linux and BL31 read. **`0002` - `0008`** the first fixes, the IR wake
  codes and the display MIPS's frames.
- **`0009`, `0011`, `0012`, `0014` - `0016`** the standby: DRAM self-refresh ported from the vendor's
  DRAM standby driver, the cluster down and up, the wake timer, the CIR pin, the steps into the contract
  page.
- **`0017` - `0032`** fixes from the reviews and from the device, the contract versions 3 and 4 with
  the build word among them; `0029` - `0032` ran on the HY310 on 07.10.2026 (`doku/163` - `doku/167`).
- **`0010`, `0013`, `0033`, `0034`** deep sleep and the HY300 Pro images: built, deep sleep compared
  with the vendor firmware's traces; no deep sleep has run on a device, and none is a release variant.

Which variant a release carries is `CRUST_DEFCONFIG` in `boards/<id>/board.env`, and
`release/check-crust.py` refuses a build whose `.config` carries one the release must not have (deep
sleep, its steps, a test build; the sleep net until `CRUST_RELEASE_ALLOW` in `mainline/config/versions.env`
names it). The compiler is built from pinned GNU sources by
`mainline/tools/or1k-toolchain/build-or1k-toolchain.sh`.
