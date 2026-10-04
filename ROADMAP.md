# Roadmap

What this port cannot do yet, why, and what it would take. Nothing here is a promise with a date; it is
an honest list, kept next to [STATUS.md](STATUS.md) so the two never drift apart. If a line says
"unverified", nobody has proven it on hardware - that is a statement about our evidence, not about the
feature's chances.

## Missing stock features

Things the projector does with the vendor firmware and does not do with ours yet.

| | State | What it would take |
|---|---|---|
| **Autofocus** | Built, since `v0.95-beta`. `h713-autofocus` puts a chessboard on the panel, takes frames from the internal camera and runs the vendor's sharpness metric in C, so a run takes seconds and the motor moves ([docs/tools/h713-autofocus.md](docs/tools/h713-autofocus.md)). A run turns round at an edge, as the vendor's does; since `v0.96-beta` it first waits until the chessboard is really on the wall (two picture-level probes, exit 3 after 4 s with the motor untouched), a long fall no longer ends at the cap, and the way back to the best position counts the motor's reported motion. On 02.10.2026 on the HY310 two runs ended `stopped: peak`, and a run against a wall ended sharp at the same motor position as the run before (`doku/134` A4). Manual focus works as before ([docs/tools/h713-focus.md](docs/tools/h713-focus.md)). | A handful of runs at one to three metres on other evenings and other walls; the metric's span, which was only +11 % on 02.10. (the camera's exposure is the suspect); and a run on any board but the HY310. |
| **Keystone correction** | Built, since `v0.95-beta`. There is no second motor on this board - the device-tree node called "keystone motor" is the focus motor (patch `0024b`) - so the correction is geometric: [`h713-warp`](docs/tools/h713-warp.md) warps the picture on the Mali-G31 with the vendor's own homography and `h713-tv` commits it as NV12 on the video plane, the channel the firmware's nine picture controls act on, and [`h713-keystone`](docs/tools/h713-keystone.md) drives the eight corner values from the accelerometer. On the HY310 on 22.09.2026 a corner set by hand moved that corner on the wall, and a 25-degree nose-up tilt pulled the top edge in by itself. The sensor's mounting offset measured about 0 degrees (26.09.2026), so since `v0.96-beta` the automatic corrects against the ideal level pose and a hand-taken reference is a fine adjustment; the four projection modes (front, rear, ceiling, rear-ceiling) and the vendor's soft edge are built and were judged on the wall on 02.10.2026, with the projector upright on the bench (`doku/134` A1, A2). | Before it is more than beta: an hour-long soak with a live source (the one run that exists found a bug in the audio path and was not repeated); the throw ratio measured with a tape instead of taken from the optics' ini (0.8176 - a wrong ratio makes every automatic correction too strong or too weak by that factor); the ceiling modes with the projector really upside down; and the write-back self-test as a second opinion on the identity warp (the ordinary check is `h713-warp ctl check N`, which needs no debug kernel). |
| **Bluetooth, including the remote control** | Ships (03.10.2026): the chip's Bluetooth patch comes with the Wi-Fi firmware from the owner's dump and the Wi-Fi driver loads it; `hciattach` and bluez on UART1; the stock remote pairs with Left+Right, all keys and the mouse mode; `h713-bt-reset` around the attach ([docs/subsystems/wifi.md](docs/subsystems/wifi.md#bluetooth)). | Open: the first HCI command lost after some warm reboots (retried; cause unknown), Bluetooth on the HY300PRO-G-EU after a cold start, the IR receiver (parked - two keys share one code). |
| **Standby below 4 W** | Standby today is the power gate: the SoC runs, everything else is dark, about 4 W ([docs/uboot/power-gate.md](docs/uboot/power-gate.md)). A deep-sleep test build reached suspend on the HY310 on 03.10.2026 and never woke up, so it is parked and not in the image. | Deep sleep means handing the board to the ARISC: it holds the rails, watches IR and CEC, and wakes the SoC. The reverse engineering for that is done (`doku/104`); the implementation is not, and it needs our TF-A to speak the vendor's SCPI protocol to the ARISC - which it currently does not. The display half turned out to be the cheap one: the vendor **never re-uploads the firmware across a sleep**. Linux never writes into the reserved MIPS window, the power-down path saves the two share-memory registers and the resume path restores them, and the core comes back paused until one start ioctl. So this needs the reset and clock ladder, those two registers, and one restart - not a firmware reload ([docs/subsystems/mips.md](docs/subsystems/mips.md)). |
| **Reloading the display firmware at runtime** | Built for a test and parked. U-Boot uploads `display.bin` once and starts the core; a firmware that has gone wrong costs a power cycle. The reload path (write the image into the reserved window, flush it, write the boot address to `0x03061030`, stop, start at `0x4b100000`) was built on 02./03.10.2026: the kernel oopses of the first try are gone and the core comes back ready, but the picture stays black after the reload (HY300PRO-G-EU), so it is not in the image. | Understand the black picture - the panel and TCON handover after the restart is the suspect - and only then take the reload in. |
| **HDCP 1.4** | Missing, and an open question. The keys never reach DRAM; the crypto engine decrypts them with key-select 3 into a key sink. On the maintainer's HY310 that key-select was refused from Linux and from EL3 alike (03.10.2026), and a read-only eFuse read from EL3 says the key flags are not burned on that unit (04.10.2026) - which the maintainer's memory of a working HDCP 1.4 test contradicts ([docs/known-issues.md](docs/known-issues.md)). | Two tests decide it: the same eFuse read on a second unit, and a real HDCP 1.4 source against the stock firmware and against this one. If the fuses are burned somewhere, the parked kernel and TF-A work comes back; the protocol itself lives in `display.bin`, and the only per-resume HDCP action in the vendor stack is one SMC, `sunxi_smc_refresh_hdcp()` (function id `0xB2000010 \| offset`, argument 5, from the `.complete` PM callback of the vendor's `tvtop` driver). |
| **HDCP 2.2 - the last proof** | Works in practice: the 912-byte key comes out of *your* device's secure storage at boot. What is unproven is whether those bytes are plaintext or a TEE-side ciphertext. | An HDCP-mandatory source on the input - a streaming stick, a console, a Blu-ray player - and one observation. |
| **The vendor display stack (`ge2d`)** | **Not needed.** Inventoried on 26.09.2026 against the HY310's own `ge2d_dev.ko` (179 functions, `umbau/work/FB-GE2D`): nine of its thirteen groups are Android plumbing or done by our KMS driver and U-Boot - our panel configuration fires more of the vendor's patch list than the vendor kernel does on a stock device tree. The DLPC3435 light-engine code is dead (project 0x33 only). The one candidate left, an LVDS FIFO watchdog (0x05880FE0 read every 300 ms), never fired under Linux: 2,000 reads over ten minutes on the HY310, all zero. Brightness was never a missing control (`doku/70`); the lamp dimmer is the display firmware's own PWM on boards that wire it (kernel `0166`). | Nothing here. What the stack had that we lacked are small items of their own: the projection-mode mirror (in `h713-warp` since `v0.96-beta`, no kernel) and three suspend facts for the standby plan (`doku/104`). |
| **`tvtop` / `tvfe` / `nsi` - the vendor TV blocks** | Not brought up as drivers. The HDMI input does **not** need them: the MIPS firmware configures the receive side itself, and the power domains and clocks they would claim are already switched on by U-Boot (`doku/71`). | Bring each one up on its own, at a point where the picture path is otherwise stable, and find out what it adds on this device - possibly nothing, possibly analog inputs or standby wake-up. |
| **Device sounds mixed with HDMI audio** | Built, since `v0.96-beta`: a playback PCM, `hw:hy310hdmi,0` and ALSA's default, that the DSP mixes into HDMI (kernel `0176` - `0178`); HDMI and device sounds measured within 0.07 dB of each other over 20 rounds (03.10.2026, [docs/subsystems/audio.md](docs/subsystems/audio.md)). | Something that plays them: no service in the image makes a sound yet (a click on the settings page, a confirmation tone). |

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
  of the device's EDID and not in the table either, so the driver refuses it and names it (kernel `0171`),
  and without editing the vendor's `database.TSE` it cannot be had. 1080p100 and 1080p120 lock once block 1 of
  the EDID is published (`h713-tv ctl edid block1`; HY310, 26.09. and 02.10.2026: 297 MHz, plane on, the picture
  looks normal, the firmware drops frames to the 60 Hz panel); block 1 also adds 1080i and 4K50/60, which the
  table has disabled. Under the warp a 120 Hz source draws about 19 frames a second (02.10.2026: the GPU is
  busy and frames are dropped) - not explained yet.

## Quality of the thing itself

Less exciting, and the part that decides whether anyone else can use this.

| | Where it stands |
|---|---|
| **Simpler installation** | Mostly done: `install <release folder>` finds the table, `u-boot-installer.bin` and `sunxi-fel` next to each other, unpacks `.img.zst` itself, and needs neither dump nor `--vendor` on a device that already runs this layout. What is left: saying before each step what it is about to do. The parameters stay for the unusual cases. |
| **Windows** | The installer is written to run there and refuses nothing, but nobody has ever run the Windows path. Until someone does, it is untested, not supported. |
| **Reproducible builds** | Since `v0.96-beta` the build clock is the commit's date (`SOURCE_DATE_EPOCH`, through every step), and the stamp says `reproducible: yes` or why not. The building blocks repeat from any checkout path (proven for `v0.96-beta`: working tree and fresh clone, every block equal), the rootfs tar only against the same Debian mirror state, and the system image's checksum not yet - its two ext4 containers carry random UUIDs and the times of their creation ([RELEASES.md](RELEASES.md)). Two builds of one commit compared block by block are part of every release check. |
| **A second pair of eyes on the safety paths** | The fan-stall poweroff is armed (see STATUS). The gate, the recovery path and the installer's refusals deserve someone who did not write them trying to break them. |
| **U-Boot's firmware debugging per board** | Done in the fork (`a830902`, in `v0.96-beta`): `commdev` and `elog` take the `cpu_comm` cells from the board's identity row instead of the HY310's literals - on the HY300 Pro the firmware keeps its tables 0xC00 lower (A12), and the reader used to say "firmware not up" while the logo was on the wall (23.09.2026). Tested at the HY310's prompt on 04.10.2026 (`doku/134` C1); on a second board not yet. After an interactive `h713_disp init` at the prompt, continue with `run boot_emmc`, not `boot`: a second init breaks the handover until the next reboot |
| **English tooling** | Done for everything a user sees: the PC tools since v0.6-beta, the device tools since v0.8-beta, `ctl` answers `ok`/`error`. Left over: `h713-focus` keeps `--trocken`/`--schritt` on purpose (a note in the field is written from them), and the hidden German aliases are still accepted, each with one line naming its new spelling. Since `v0.96-beta` the device scripts, the units and the kernel drivers' log lines are English too (`0180`). |
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
