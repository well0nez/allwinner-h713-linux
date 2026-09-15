# h713-extract

`h713-extract` pulls the proprietary blobs our Linux needs - display firmware, EDID, audio patch, picture
tables, Wi-Fi firmware - out of a device's own stock Android firmware, with structure checks and a
manifest. Nothing proprietary lives in this repository; the tool produces it on the user's own machine
from the user's own device, which is also why installing needs no licence beyond the one that came with
the projector.

## Inputs and outputs

| Input | Recognised as |
|---|---|
| `update.img` | Allwinner IMAGEWTY firmware container |
| a raw eMMC dump | GPT + `boot0` + the `sunxi-package`/TOC1 boot package at their fixed LBAs |
| `--part NAME=FILE` | one partition or `.fex` file at a time: `boot_package`, `super`, `vendor`, `bootloader_a`/`bootloader_b`/`boot-resource`, `emmc` |
| `--fex-dir DIR` | a directory of already-unpacked `.fex` files |

```
installer/h713-extract update.img -o out                              # full IMAGEWTY container
installer/h713-extract emmc-dump.bin -o out                           # raw eMMC dump
installer/h713-extract --part bootloader_b=bootloader_b.img -o out    # only the FAT16 vendor partition -> boot/mips/*
installer/h713-extract --part super=super.img -o out                  # only super -> EDID, audio patch, picture tables
```

`h713-install extract` is the same tool under a second name: everything behind the word `extract` is
handed to it unchanged, so the installer needs no second copy. `--no-pq`, `--no-mips` and `--no-wlan`
each leave one group out; `-q` prints result lines only.

Output under `--out` (default `./h713-extract-out`): `lib/firmware/h713-arisc.bin` (ARISC coprocessor
firmware), `lib/firmware/hy310-edid.bin`, `lib/firmware/h713/msp-patch.bin` (audio DSP patch), `pq/*`
(the picture-quality tables `h713-pq` reads), `boot/mips/*` (the 19 display artifacts U-Boot loads by
name), `boot/bootlogo.bmp` (the vendor boot logo, added 15.09.2026),
`lib/firmware/aic8800_fw/SDIO/aic8800D80/*` (Wi-Fi firmware, added 12.09.2026, `--no-wlan` to skip
it), plus `MANIFEST.json` and `REPORT.txt`. The report is also written as `BERICHT.txt`, byte-identical,
for one more release - the German name goes away with the next one.

The boot logo is the one file that does not come from `mips/` but from the ROOT of the same FAT,
because that is where U-Boot looks for it: `h713_disp init <id> logo` reads `bootlogo.bmp` at the root
of whichever partition the display artifacts come from, which on our layout is `/boot/bootlogo.bmp`.
It is checked like the rest - BMP signature, one plane, 24 bpp, uncompressed, and the geometry against
the board profile's panel - but a finding there is reported, never fatal: U-Boot takes width and height
from the file's own header, and a missing logo costs a picture during boot, not the boot.

**Deliberately not extracted**, although they lie in the same partition: `fastbootlogo.bmp` (the
fastboot-mode logo - our U-Boot has no such mode), `font24.sft`/`font32.sft` (the vendor bootloader's
text fonts), `magic.bin` (512 bytes of ASCII, purpose unknown), `bat/` (battery icons of a tablet
template - a projector has no battery) and `wavefile/` (that same template's e-paper waveforms). None of
them is read by our chain and none stands for a stock behaviour we lack; the report names them, and the
full device dump keeps them anyway.

## Structure checks and the manifest

Every artifact is checked, not just copied: the boot package's own checksum and item table, the EDID
header and its per-block checksums, the ELF symbol table and patch-block chain for the audio patch, an
INI/XML/SQLite parse for the picture tables, and - for the display artifacts - long-filename FAT
directory entries plus each file's 16-byte `TSE` header. The display firmware itself is checked against a
table of known revisions (size and sha256); an unrecognised revision is reported plainly rather than
accepted silently, and every `ProjectID_0x*.TSE` file is still extracted so the right one can be chosen at
runtime. `MANIFEST.json` and `REPORT.txt` record path, size, sha256, where each file came from, and
whether it matched its reference.

The manifest keys are English since stage 3 of doku/121: the artifact list is `files` (entries carry
`path`, `size`, `sha256`, `origin`, `checks`, `error`, `reference_ok`, `reference_device`), the input is
`input`, and the summary lists are `not_extracted`, `deviations`, `warnings` and `observations`. The
structure is otherwise unchanged; the complete old → new table is in `installer/tests/TEXTS-extract.md`.

## Device profiles

Two H713 projectors share the same Allwinner reference design (`h713_tuna_p3`) but ship their own
firmware:

| Profile | Device | Stock build |
|---|---|---|
| `hy310` | HY310 | 2025-07-24 (`Projector07241019`) |
| `l018` | L018 | 2025-05-14 (`Projector05141211`) |

The device is recognised two ways: a sha256 of the whole input file against known images, or - for
`--part`/`--fex-dir` runs and unseen images - a bundle of content signatures (boot-package hash, U-Boot
and ARISC version strings, vendor build fingerprint, and the one MIPS artifact that differs between the
two devices, `mips/database.TSE`). A profile is accepted when at least one strong signature matches and
none contradicts; contradicting signatures leave the device **unknown**, and the tool then falls back to
best-effort extraction against the closest profile, with every deviation listed in the report rather than
silently accepted.

## Exit codes and limits

Exit 0: known device, everything checked and reference-identical. Exit 1: unknown image (best-effort,
with a deviation list) or a known device with missing/mismatched parts - the output is still written.
Exit 2: a hard error, including an `--out` directory that already belongs to a different device.

Pure Python standard library, including its own read-only ext4 and FAT reader - no `debugfs`, no
`e2fsprogs`, so it runs the same on Windows (`--use-debugfs` is the counter-check and needs `e2fsprogs`).
It only reads its input: HDCP/DRM keys are never touched even when present, and the fonts, the
fastboot logo and the battery-animation files from the same vendor partition are deliberately left out
(the list is above). It compares against the
two profiles above and no others - the project carries board profiles for more H713 projectors, and
`h713-install identify` uses all of them, but the extractor's reference table is the pair.

Details: doku/108-plan-vendordaten.md, doku/nachtlog/S42-r2-extract.md.
