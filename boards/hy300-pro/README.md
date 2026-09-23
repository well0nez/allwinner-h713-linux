# HY300 Pro

The first foreign device this project ever met: reported in
[issue #1](https://github.com/well0nez/allwinner-h713-linux/issues/1) on 13.09.2026 by its owner
(GitHub `fightforlife`). He first ran the installer in dump-only mode and `h713-extract` over the dump;
from 16.09.2026 on he flashed TEST images built for this board, with that dump as the way back. No image
of his firmware exists here.

| | |
|---|---|
| Status | **partial** - the description itself is incomplete |
| Verified by | nobody |
| Profile | `installer/h713/profiles/hy300_pro.py` |
| Image | **TEST images** for its owner only (stage 5, `--test-image`): `hy300-pro-test7` (23.09.) is current, `test1` and `test2` are deleted. No release image until a green report |
| Kernel DTB | `sun50i-h713-hy300-pro` (patch 0161, an include of the hy200 dts) |
| U-Boot base | `hy300_pro_defconfig` (the owner's DRAM block, 636 MHz) |
| DRAM | DDR3 (type 3), **636 MHz**, 1 GiB - all 24 boot0 words from his probe run of 2026-09-14 (`uboot.config`) |
| Panel | declared project id `0x34`; resolution unknown |
| eMMC | 7.28 GiB, 15 269 888 sectors - the same size as the HY310 |
| Stock | Android 10 (32-bit, ARMv7 kernel 5.4.99), ADT-3 build 6245789 |

## What we actually know, and from where

Everything comes from his serial log and his `h713-extract` run, quoted in
`analyse/issues/issue-1-hy300pro-20260913.md` and `doku/120-plan-hy300pro.md` §1:

- **DRAM**: `DRAM CLK = 636 MHz`, `Type = 3`, `ZQ 0x7b7bfb`, `SIZE = 1024 M`. Four numbers. The other
  21 words of a DRAM block were never posted.
- **Our installer U-Boot ran on his hardware.** The SPL trained with *our* values (the HY310 set at
  792 MHz) and `ums` served his eMMC for 17 minutes under load. That proves "enough for a dump", not
  "stable in operation" - and his board's own clock is 636, not 792.
- **The device check refused to write**, which is what it is for: unknown firmware → dump only.
- **Partitions**: 25 entries, a single `Reserve0` at LBA 5 358 592 (+32 768), `media_data` at
  4 932 608 (+425 984, 208 MiB). The HY310's constants point at his `UDISK`; that is defect 2 of the
  issue and the reason the small dump read the wrong region (read-only, so harmless).
- **Display firmware**: `display.bin` 1 253 136 bytes,
  `cf9649bcc84a111ce590fc7acde723c25557fd2332abbb9fd10225905aae13a2` - a revision no table of ours
  declares, so no HDCP wait site and no panel entry for it.
- **Project id `0x34`** (`ProjectID_0x0034.TSE`), the same id cstenger's HY200 bench board declares -
  while his stock system renders 1080p and the other `0x34` board we know is 1280×720. The project id
  selects a panel entry; it is not itself a resolution.
- **Motor**: `motor-phase-num 4`, `motor-step-num 8`, close to the HY310's.

## What we do not know

- whether 636 MHz or 792 MHz is the right clock for *sustained* operation on this board
- the panel: only the declared project id 0x34 is his; the 1280x720 timing the loader drives is what every
  other 0x34 source shows (a bench board measured, three vendor inis) - likely, not measured on his board
- the boot package contents, the stock `sunxi_version`, the exact build fingerprint
- nothing about it is unique enough to identify it: its `display.bin` digest is not one of the
  identification features, and it shares the ADT-3 fingerprint with two other images. The profile's
  `strong_features` is deliberately empty, so the matcher can never claim this board.

## What it would take to move this board forward

From the issue, in order:

1. installer: a recognition entry for this firmware, and the small dump's offsets read from the GPT
   instead of HY310 constants - **before** any write path to such a device is unlocked at all;
2. `h713-extract`: reference hashes from his extraction (vendor file hashes are not secret);
3. board: a DRAM profile at 636 MHz - or proof under load that 792 holds - `h713_project=0x34`, and a
   DTS comparison (fan, motor, key; the panel comes through TSE from his own dump);
4. an image for this board **and a test by its owner - do not flash before that**.

Steps 1-3 can happen here. Step 4 cannot: it needs a person with the device. Until he reports a green
run, this board stays below `verified` and gets no image (`boards/README.md`, honesty rule).

## Where it stands, 17.09.2026

Steps 1-3 are done and step 4 is under way. Seven TEST images have existed:

| Image | What happened |
|---|---|
| `test1`, `test2` | deleted with their tags. `test2` brought U-Boot up on his board and hung in the display bring-up: the HY310's fixed LogoRegData offsets ran past the end of his container, which has 13 descriptors (14 388 B) against the HY310's 15 (15 652 B). U-Boot reads the group boundaries out of the file since then |
| `test3` | booted the kernel: Wi-Fi as access point and as station, HDCP 2.2 reported working. No boot logo (the panel stays dim white), no HDMI input, green stripes. The missing input was the ARISC not answering `ResetEDIDModule` - its firmware's SRAM addresses are not the HY310's, and the driver used the HY310's |
| `test4` | kernel patch `0091a` resolves those addresses out of the loaded ARISC image (`tools/arisc-fw-addrs.py` does the same on the host), plus a first A/B for the `0x34` panel on U-Boot branch `hy300-pro-ab` |
| `test5`, `test6` | 19. and 20.09.: the HDMI input detected (0136 series), then the picture at every resolution but skewed |
| `test7` | current (23.09., published): the picture geometry fixed (`0133d`, the window words as fractions of 30720x17280), the gamma curve out of his own TSE and the presets out of his `tvpq.db` (PQ1), built from `main` 40c6175 |

**Open: his console output for `test7`.** The panel A/B is merged into `h713-hy310` only after a green
owner report.
