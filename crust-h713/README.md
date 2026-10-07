# crust changes for the H713 (the ARISC firmware)

**The patch files here are generated, not maintained** - the same rule as
[`uboot-h713/`](../uboot-h713/README.md) and [`tfa-h713/`](../tfa-h713/README.md):
`git format-patch --no-signature 499a362645e6..<head>` in a checkout of the crust fork (branch `h713`,
base is upstream crust's `master` after v0.6). `SERIES.txt` names base, head and count and is the only
thing that says which fork commit this mirror stands on. Whoever wants to change something changes the
fork and has the mirror generated again.

Verified the way a mirror should be: applying all 75 patches onto the base produces a tree with the same
hash as the fork head (`e76287912083`, 08.10.2026).

**Not published yet.** The fork has no public repository so far, and there is no submodule
`mainline/external/crust`; `release/build-all.sh` takes the checkout from `CRUST_SRC=<dir>` until there
is one. A checkout made from this mirror:

```sh
git clone https://github.com/crust-firmware/crust crust   # a full clone: the version text needs its tags
git -C crust checkout -b h713 499a362645e6
git -C crust am ../crust-h713/0*.patch                     # tree = e76287912083, as above
CRUST_SRC=$PWD/crust release/build-all.sh --version <v> --board hy310
```

`git am` gives the commits new hashes, so crust's version text names another commit than the fork head and
the stamp says "reproducible: no"; the tree is the same. The checkout has to lie inside the directory the
build container mounts. A worktree or a `git clone --shared` works too: build-all hands the container
the git directory itself (`GIT_DIR`, `GIT_WORK_TREE`), so crust's version text names the commit and not
`v0.6.10000` with an `unknown` hash.

**Merged only as one piece.** `CRUST_DEFCONFIG` in `boards/hy310/board.env` goes into `main` only together
with three other things: the crust source (this fork as a submodule, or the mirror as above), the HY310
device tree that names `hy310-crust.bin` for the arisc node, and the U-Boot patch that stages `scp.bin` for
BL31 (`SUNXI_SCP_BASE`). Without the source `build-all` stops before step 1; without the other two, step 10
refuses the image. `release/tor.sh` and `boards/check.sh` do not see that order, so it is stated here,
in `board.env` and in `TODO.md` 3.2.

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
- **`0035` - `0075`** contract version 5, what a release needs: the page as one table in
  `platform/memory.h` with compatibility word, build word, error bits and counters (`0035` - `0037`,
  `0075`); the sleep net on the R_WDOG, the standby phases with the kernel's request and confirm, and one
  clean reset for every fatal error (`0038` - `0041`, `0072` - `0074`); bounded polls and the DRAM checks
  (`0042` - `0046`, `0070`: the DRAM checksum only in a test image); the HDMI and wake-path fixes of the
  review (`0047` - `0059`, `0071`); the first deep-sleep stage, no release variant (`0060` - `0068`); a
  build fix for the other platforms (`0069`). Built and run in emulation and against the traces; none of
  `0035` - `0075` has run on a device yet - contract version 4 (`0032`) is what ran.

Which variant a release carries is `CRUST_DEFCONFIG` in `boards/<id>/board.env`, and
`release/check-crust.py` refuses a build whose `.config` carries one the release must not have (deep
sleep, its steps, a test build; the sleep net until `CRUST_RELEASE_ALLOW` in `mainline/config/versions.env`
names it). The compiler is built from pinned GNU sources by
`mainline/tools/or1k-toolchain/build-or1k-toolchain.sh`.
