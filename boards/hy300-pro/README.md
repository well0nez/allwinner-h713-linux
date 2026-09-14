# HY300 Pro

The first foreign device this project ever met: reported in
[issue #1](https://github.com/well0nez/allwinner-h713-linux/issues/1) on 13.09.2026 by its owner
(GitHub `fightforlife`). He ran the installer in dump-only mode (`--nur-abzug`) and `h713-extract` over the dump.
Nothing was written to his device, and no image of his firmware exists here.

| | |
|---|---|
| Status | **partial** — the description itself is incomplete |
| Verified by | nobody |
| Profile | `installer/h713/profiles/hy300_pro.py` |
| Image | never built (`STATUS` is not `verified`) |
| Kernel DTB | none |
| U-Boot base | `hy300-pro_defconfig` (does not exist yet) |
| DRAM | DDR3 (type 3), **636 MHz**, 1 GiB — from his UART log, nothing else measured |
| Panel | declared project id `0x34`; resolution unknown |
| eMMC | 7.28 GiB, 15 269 888 sectors — the same size as the HY310 |
| Stock | Android 10 (32-bit, ARMv7 kernel 5.4.99), ADT-3 build 6245789 |

## What we actually know, and from where

Everything comes from his serial log and his `h713-extract` run, quoted in
`analyse/issues/issue-1-hy300pro-20260913.md` and `doku/120-plan-hy300pro.md` §1:

- **DRAM**: `DRAM CLK = 636 MHz`, `Type = 3`, `ZQ 0x7b7bfb`, `SIZE = 1024 M`. Four numbers. The other
  21 words of a DRAM block were never posted.
- **Our installer U-Boot ran on his hardware.** The SPL trained with *our* values (the HY310 set at
  792 MHz) and `ums` served his eMMC for 17 minutes under load. That proves "enough for a dump", not
  "stable in operation" — and his board's own clock is 636, not 792.
- **The device check refused to write**, which is what it is for: unknown firmware → dump only.
- **Partitions**: 25 entries, a single `Reserve0` at LBA 5 358 592 (+32 768), `media_data` at
  4 932 608 (+425 984, 208 MiB). The HY310's constants point at his `UDISK`; that is defect 2 of the
  issue and the reason the small dump read the wrong region (read-only, so harmless).
- **Display firmware**: `display.bin` 1 253 136 bytes,
  `cf9649bcc84a111ce590fc7acde723c25557fd2332abbb9fd10225905aae13a2` — a revision no table of ours
  declares, so no HDCP wait site and no panel entry for it.
- **Project id `0x34`** (`ProjectID_0x0034.TSE`), the same id cstenger's HY200 bench board declares —
  while his stock system renders 1080p and the other `0x34` board we know is 1280×720. The project id
  selects a panel entry; it is not itself a resolution.
- **Motor**: `motor-phase-num 4`, `motor-step-num 8`, close to the HY310's.

## What we do not know

- 21 of the 24 DRAM words, `para2` and `tpr13` among them; the fragment borrows them and says so
- whether 636 MHz or 792 MHz is the right clock for *sustained* operation on this board
- the panel: resolution, timings, port count, backlight — only the declared project id is known
- the boot package contents, the stock `sunxi_version`, the exact build fingerprint
- nothing about it is unique enough to identify it: its `display.bin` digest is not one of the
  identification features, and it shares the ADT-3 fingerprint with two other images. The profile's
  `strong_features` is deliberately empty, so the matcher can never claim this board.

## What it would take to move this board forward

From the issue, in order:

1. installer: a recognition entry for this firmware, and the small dump's offsets read from the GPT
   instead of HY310 constants — **before** any write path to such a device is unlocked at all;
2. `h713-extract`: reference hashes from his extraction (vendor file hashes are not secret);
3. board: a DRAM profile at 636 MHz — or proof under load that 792 holds — `h713_project=0x34`, and a
   DTS comparison (fan, motor, key; the panel comes through TSE from his own dump);
4. an image for this board **and a test by its owner — do not flash before that**.

Steps 1–3 can happen here. Step 4 cannot: it needs a person with the device. Until he reports a green
run, this board stays below `verified` and gets no image (`boards/README.md`, honesty rule).
