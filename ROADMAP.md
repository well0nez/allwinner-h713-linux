# Roadmap

What this port cannot do yet, why, and what it would take. Nothing here is a promise with a date; it is
an honest list, kept next to [STATUS.md](STATUS.md) so the two never drift apart. If a line says
"unverified", nobody has proven it on hardware - that is a statement about our evidence, not about the
feature's chances.

## Missing stock features

Things the projector does with the vendor firmware and does not do with ours yet.

| | State | What it would take |
|---|---|---|
| **Autofocus** | Built, not proven to converge. `h713-autofocus` puts a chessboard on the panel, takes frames from the internal camera and runs the vendor's sharpness metric in C, so a run takes seconds and the motor moves ([docs/tools/h713-autofocus.md](docs/tools/h713-autofocus.md)). A run no longer ends at an edge: the search turns round there, as the vendor's does, and on 23.09.2026 runs on the bench ended at a peak (positions -2 to +31). Since 26.09.2026 (package FB-AFWAIT, tested on the HY310 over the LAN, not in main yet) a run first waits until the chessboard is really on the wall - two picture-level probes at or above 3227, the camera woken by an exposure write, exit 3 after 4 s with the motor untouched. The wait held on both runs of that evening (2 probes, 1.27 s); the first run after the boot still failed, for another reason: from +32 the metric fell monotonically to -400 and the coarse search never turned round, then flipped in the flat region until its cap, and `return_to_best` tripped over the same spent cap. The second run found its peak at -24 in 148 msteps. On 27.09. the fixed tool of package FB-AFSEARCH ran on the device: no more bouncing between the edges and `return_to_best` walks back, but the metric was flat because the set-up had changed (projector moved, the laptop's HDMI asleep), so the reversal fix is not proven yet. Manual focus works as before ([docs/tools/h713-focus.md](docs/tools/h713-focus.md)). | The coarse state's reversal rule held against the vendor's, and a return that cannot flip, with the 26.09. log as the fixture (package FB-AFSEARCH, whose return works on the device since 27.09.; the reversal itself still needs the evening's set-up); then a wall at one to three metres and a handful of runs. |
| **Keystone correction** | Built, in the source, not in a release. There is no second motor on this board - the device-tree node called "keystone motor" is the focus motor (patch `0024b`) - so the correction is geometric: [`h713-warp`](docs/tools/h713-warp.md) warps the picture on the Mali-G31 with the vendor's own homography and `h713-tv` commits it as NV12 on the video plane, the channel the firmware's nine picture controls act on, and [`h713-keystone`](docs/tools/h713-keystone.md) drives the eight corner values from the accelerometer. On the HY310 on 22.09.2026 a corner set by hand moved that corner on the wall, and a 25-degree nose-up tilt pulled the top edge in by itself. On 26.09.2026 the automatic's reference was measured: the sensor reads 18.9 degrees of pitch with a phone on the housing reading 18.9, so the sensor's mounting offset is about 0 degrees in pitch and under 1 degree in roll - the ideal pose (0, 0, 1 g) can be the default and a hand-taken reference becomes a fine adjustment (package FB-KSREF; with its follow-up FB-KSREFb of 27.09., which makes a refused reference file a warning instead of a restart loop, it is integrable in full). | Four things before it is more than beta: an hour-long soak with a live source (the one run that exists found a bug in the audio path and was not repeated); the throw ratio measured with a tape instead of taken from the optics' ini (0.8176 - a wrong ratio makes every automatic correction too strong or too weak by that factor); the projection-mode mirror RPC (ceiling, rear), designed and not built; and the write-back self-test as a second opinion on the identity warp (the ordinary check is `h713-warp ctl check N`, which needs no debug kernel). The vendor's edge-blend pass is left out entirely. |
| **Bluetooth, including the remote control** | Driver builds, radio does not come up. The AIC8800D80's Bluetooth firmware is not in the stock firmware image - only in a vendor SDK package with an unresolved licence, so we cannot ship or extract it. | Either a licence answer, or a firmware split that pulls the BT blob from a device that has one. The remote control depends on this (and on an IR or BLE input path afterwards). Until it exists, every setting is on the projector's own page, `http://<projector>:8080/` ([docs/guides/settings-page.md](docs/guides/settings-page.md)). |
| **Standby below 4 W** | Standby today is the power gate: the SoC runs, everything else is dark, about 4 W ([docs/uboot/power-gate.md](docs/uboot/power-gate.md)). | Deep sleep means handing the board to the ARISC: it holds the rails, watches IR and CEC, and wakes the SoC. The reverse engineering for that is done (`doku/104`); the implementation is not, and it needs our TF-A to speak the vendor's SCPI protocol to the ARISC - which it currently does not. The display half turned out to be the cheap one: the vendor **never re-uploads the firmware across a sleep**. Linux never writes into the reserved MIPS window, the power-down path saves the two share-memory registers and the resume path restores them, and the core comes back paused until one start ioctl. So this needs the reset and clock ladder, those two registers, and one restart - not a firmware reload ([docs/subsystems/mips.md](docs/subsystems/mips.md)). |
| **Reloading the display firmware at runtime** | Not built. U-Boot uploads `display.bin` once and starts the core; from Linux there is no way to replace it or to restart it, so a firmware that has gone wrong costs a power cycle. | Known end to end from the vendor stack, and it needs no U-Boot: write the image into the reserved-memory window (the vendor does it with `mmap` on `/dev/mipsloader`; our own driver can `memcpy`), flush the whole 42 MiB window to DRAM, write the boot address to `0x03061030`, then the ioctl pair - stop, then start at `0x4b100000`. Unverified on our build. A cheap first experiment: re-assert only bit 18 of `0x0200160C` after rewriting the boot address, leaving the clocks and bits 16/17 alone. |
| **HDCP 1.4** | Missing. Confirmed on the chip: the keys never reach DRAM; the Crypto Engine decrypts them into a key sink. | One measurement first - may the non-secure world use key-select 3 at all? It costs a power cycle and has not been run (`doku/112`). After that, less than it sounds: the HDCP 1.4 sink state machine lives inside `display.bin`, and the only per-resume HDCP action in the whole vendor stack is **one SMC** - `sunxi_smc_refresh_hdcp()`, function id `0xB2000010 \| offset` with argument 5, issued from the `.complete` PM callback of the vendor's `tvtop` driver, not from the mipsloader and not from userspace. So the job is to reproduce that one SMC (or what it does) and to get the key bytes to the MIPS, not to implement the protocol. |
| **HDCP 2.2 - the last proof** | Works in practice: the 912-byte key comes out of *your* device's secure storage at boot. What is unproven is whether those bytes are plaintext or a TEE-side ciphertext. | An HDCP-mandatory source on the input - a streaming stick, a console, a Blu-ray player - and one observation. |
| **The vendor display stack (`ge2d`)** | **Not needed.** Inventoried on 26.09.2026 against the HY310's own `ge2d_dev.ko` (179 functions, `umbau/work/FB-GE2D`): nine of its thirteen groups are Android plumbing or done by our KMS driver and U-Boot - our panel configuration fires more of the vendor's patch list than the vendor kernel does on a stock device tree. The DLPC3435 light-engine code is dead (project 0x33 only). The one candidate left, an LVDS FIFO watchdog (0x05880FE0 read every 300 ms), never fired under Linux: 2,000 reads over ten minutes on the HY310, all zero. Brightness was never a missing control (`doku/70`); the lamp dimmer is the display firmware's own PWM on boards that wire it (kernel `0166`). | Nothing here. What the stack had that we lack are small items of their own: the projection-mode mirror (about 40 lines in `h713-warp`, no kernel) and three suspend facts for the standby plan (`doku/104`). |
| **`tvtop` / `tvfe` / `nsi` - the vendor TV blocks** | Not brought up as drivers. The HDMI input does **not** need them: the MIPS firmware configures the receive side itself, and the power domains and clocks they would claim are already switched on by U-Boot (`doku/71`). | Bring each one up on its own, at a point where the picture path is otherwise stable, and find out what it adds on this device - possibly nothing, possibly analog inputs or standby wake-up. |
| **Device sounds mixed with HDMI audio** | HDMI audio works; the DAC takes one source at a time, so system sounds and HDMI cannot both play. | A software mixer in front of the codec, plus a decision about who owns the card (`doku/102`). |

## Not proven on this build

Present in the tree, working in the tree it came from, not re-tested in the image you can install:

- **Hardware video decode (cedrus) and the IOMMU.** These are cstenger's patches, measured on his board
  with a zero-copy path to the panel. Our image ships them, our boot chain changed since, and nobody
  re-ran the measurements. Details and the open memory-corruption case:
  [docs/subsystems/video.md](docs/subsystems/video.md). **The Mali GPU has left this group:** Panfrost
  renders in this image since 22.09.2026, with its own operating points, a cooling map and ten minutes of
  load behind it - in the source, not in a release, and with nothing decoded through cedrus in those runs.
- **AV1 decode.** The H713 is the first Allwinner chip with AV1 hardware. Whether the existing reverse
  engineering describes a working decoder or only a register map is unresolved.
- **Modes beyond the verified list.** Since v0.9-beta the driver locks on the firmware's own mode table (the
  records in your `database.TSE`) and refuses anything else by name, so the question is no longer which modes
  the EDID unlocks but which of the enabled records the firmware really follows. 1600×900 is in neither block
  of the device's EDID and not in the table either, so the driver refuses it after about seven seconds (by name once kernel patch 0136za is in),
  and without editing the vendor's `database.TSE` it cannot be had. 1080p100 and 1080p120 lock once block 1 of
  the EDID is published (package FB-EDID, HY310, 26.09.2026: 297 MHz, plane on, the picture looks normal, the
  firmware drops frames to the 60 Hz panel); block 1 also adds 1080i and 4K50/60, which the table has disabled.
  The 120 Hz path under the warp is untested. Not in main yet.

## Quality of the thing itself

Less exciting, and the part that decides whether anyone else can use this.

| | Where it stands |
|---|---|
| **Simpler installation** | Mostly done: `install <release folder>` finds the table, `u-boot-installer.bin` and `sunxi-fel` next to each other, unpacks `.img.zst` itself, and needs neither dump nor `--vendor` on a device that already runs this layout. What is left: saying before each step what it is about to do. The parameters stay for the unusual cases. |
| **Windows** | The installer is written to run there and refuses nothing, but nobody has ever run the Windows path. Until someone does, it is untested, not supported. |
| **Reproducible builds** | Two builds of the same source differ: TF-A, U-Boot and the FIT embed a build time, the Wi-Fi module embeds kernel header paths. Fixable with `KBUILD_BUILD_TIMESTAMP`, `-ffile-prefix-map` and a fixed `mkimage -t`. |
| **A second pair of eyes on the safety paths** | The fan-stall poweroff is armed (see STATUS). The gate, the recovery path and the installer's refusals deserve someone who did not write them trying to break them. |
| **U-Boot's firmware debugging per board** | `h713_disp commdev`, `commcall`, the elog dump and the comm reader's self-test read the display firmware's structures at the HY310's addresses. On the HY300 Pro they land elsewhere (its firmware keeps its tables 0xC00 lower, A12) and the reader says "firmware not up" while the logo is on the wall (23.09.2026). The kernel side already takes the addresses from the board file (`allwinner,elog`); U-Boot has to do the same - a table per firmware identity, or the values from the board's environment - before anyone can debug a second board from its prompt. Not urgent, not to be forgotten |
| **English tooling** | Done for everything a user sees: the PC tools since v0.6-beta, the device tools since v0.8-beta, `ctl` answers `ok`/`error`. Left over: `h713-focus` keeps `--trocken`/`--schritt` on purpose (a note in the field is written from them), and the hidden German aliases go out after `v0.9`. |
| **Pictures** | There is a video of the HDMI input running (linked from the README). Still photographs - the projected picture, the board, the UART pads - will follow. A recording of the install from FEL to first boot is still missing. |

## Upstreaming

Some of what we fixed is not projector-specific and belongs in other people's trees: the pinctrl
interrupt-bank fix (`0143`/`0144`), the U-Boot environment offset (`0022`), the `cpu_comm` register and
IRQ correction (`0024a`), and the build-script change that lets a patch series carry comments. Those go
to cstenger first, and where they are his own upstreams' bugs, onwards from there.

## How to help

The two things that would move this fastest are hardware and honesty. Hardware: an HDCP-mandatory
source, a second H713 device to test the installer against, a reference tachometer, a Windows machine.
Honesty: run the parts marked unverified and say what actually happened - a negative result written
down is worth as much here as a fix, and [docs/dead-ends.md](docs/dead-ends.md) exists because of that.
