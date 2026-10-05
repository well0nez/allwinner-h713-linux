# TF-A changes for the H713 (BL31)

**The patch files here are generated, not maintained** — the same rule as
[`uboot-h713/`](../uboot-h713/README.md):
`git format-patch --no-signature 347d1c1641384..<head>` in the submodule checkout
`mainline/external/arm-trusted-firmware` (branch `sun50i-h713`, base is ARM's `master`).
`SERIES.txt` names base, head and count and is the only thing that says which fork commit
this mirror stands on. Whoever wants to change something changes the fork and has the
mirror generated again.

Verified the way a mirror should be: applying all 7 patches onto the base produces a tree
with the same hash as the fork head (`67cf7997a540`), so these files and the fork say the
same thing.

**Why this directory exists at all.** It was missing until 05.10.2026, and that absence was
actively misleading: U-Boot had its mirror, the kernel had `mainline/patches/kernel/`, so
TF-A looked as if it were covered too. It was not — the EL3 service that makes HDCP 1.4
work lived as uncommitted changes in a working tree and in no repository at all. Three
source trees, three different degrees of being tracked, and nothing in the repository said
so. Now all three are treated alike.

## What is in it

**`0001`–`0005` the platform itself.** `sun50i_h713` as an Allwinner platform, the
key-protected watchdog in `SYSTEM_RESET` (writes without the key are ignored, which made
a reset look like a hang), PSCI `CPU_ON` and `CPU_SUSPEND` on the native power ops, and
`SYSTEM_OFF` entering the boot gate instead of halting — that is what makes the projector's
power key behave like a power key ([`docs/uboot/power-gate.md`](../docs/uboot/power-gate.md)).

**`0006` the HDCP 1.4 key path.** One EL3 service: it starts a Crypto Engine task that moves
this device's own key set from the protected window into the receiver's key sink. The key
set never becomes readable — the engine decrypts it with a key that exists nowhere software
can reach and writes the result straight into the receiver. Three measured rules are written
into the source and must not be "simplified" away; the one that cost two days is that the
DMA *source* has to lie inside the protected window, because the engine answers the same
refusal whether the key slot or the source region is wrong. Details and the measuring rule:
[`docs/subsystems/hdcp.md`](../docs/subsystems/hdcp.md).

The workbench probes in that service — engine tasks with caller-chosen key slots, lengths and
addresses, descriptor dumps, eFuse reads — compile only with `H713_HDCP_RESEARCH=1` and are
absent from a release build. `release/check-hdcp-artifacts.sh` refuses an image that carries
them.

**`0007` our own secure payload at S-EL1, kept as evidence and not shipped.** It works, and
it is unnecessary because BL31 can do the transfer itself. It stays because it cost findings
worth keeping — an execute-never blanket mapping, a generic timer that is unusable at S-EL1
here, and a dispatcher whose return convention differs from our own service's. The honest
trade-off of shipping the EL3 route instead is that our HDCP code runs at the highest
privilege level, so a bug in it is an EL3 bug.

## Building

`release/build-all.sh` step 1 builds BL31 from the submodule; nothing here is applied by
hand. For a build with the workbench probes:

```bash
make PLAT=sun50i_h713 DEBUG=0 H713_HDCP_RESEARCH=1 bl31
```

and never ship that image. TF-A does not track changes to `BL31_CPPFLAGS`, so remove
`build/sun50i_h713` whenever a flag changes — stale objects produced findings that were not
real.
