# Roadmap

What this port cannot do yet, why, and what it would take. Nothing here is a promise with a date; it is
an honest list, kept next to [STATUS.md](STATUS.md) so the two never drift apart. If a line says
"unverified", nobody has proven it on hardware — that is a statement about our evidence, not about the
feature's chances.

## Missing stock features

Things the projector does with the vendor firmware and does not do with ours yet.

| | State | What it would take |
|---|---|---|
| **Autofocus** | Not built. Manual focus works ([docs/tools/h713-focus.md](docs/tools/h713-focus.md)), and the driver deliberately never runs a homing sweep. | A sharpness measure needs a test pattern with hard edges: on a dark scene an autofocus measures noise and drives the lens away. So the tool has to put a pattern up (`h713-tv`), search, and restore what was on screen. Which pattern stock uses is unknown. |
| **Keystone correction** | Not built. The vendor's device-tree node called "keystone motor" turned out to be the focus motor (patch `0024b`); there is no second motor on this board. | Trapezoid correction would have to be geometric, in the display path, not mechanical. Whether the MIPS firmware can be asked for it is unexplored. |
| **Bluetooth, including the remote control** | Driver builds, radio does not come up. The AIC8800D80's Bluetooth firmware is not in the stock firmware image — only in a vendor SDK package with an unresolved licence, so we cannot ship or extract it. | Either a licence answer, or a firmware split that pulls the BT blob from a device that has one. The remote control depends on this (and on an IR or BLE input path afterwards). |
| **Standby below 4 W** | Standby today is the power gate: the SoC runs, everything else is dark, about 4 W ([docs/uboot/power-gate.md](docs/uboot/power-gate.md)). | Deep sleep means handing the board to the ARISC: it holds the rails, watches IR and CEC, and wakes the SoC. The reverse engineering for that is done (`doku/104`); the implementation is not, and it needs our TF-A to speak the vendor's SCPI protocol to the ARISC — which it currently does not. |
| **HDCP 1.4** | Missing. Confirmed on the chip: the keys never reach DRAM; the Crypto Engine decrypts them into a key sink. | One measurement first — may the non-secure world use key-select 3 at all? It costs a power cycle and has not been run (`doku/112`). After that, a driver that programs the engine before the MIPS starts. |
| **HDCP 2.2 — the last proof** | Works in practice: the 912-byte key comes out of *your* device's secure storage at boot. What is unproven is whether those bytes are plaintext or a TEE-side ciphertext. | An HDCP-mandatory source on the input — a streaming stick, a console, a Blu-ray player — and one observation. |
| **Device sounds mixed with HDMI audio** | HDMI audio works; the DAC takes one source at a time, so system sounds and HDMI cannot both play. | A software mixer in front of the codec, plus a decision about who owns the card (`doku/102`). |

## Not proven on this build

Present in the tree, working in the tree it came from, not re-tested in the image you can install:

- **Hardware video decode (cedrus), the IOMMU, and the Mali GPU.** These are cstenger's patches, measured
  on his board with a zero-copy path to the panel. Our image ships them, our boot chain changed since,
  and nobody re-ran the measurements. Details and the open memory-corruption case:
  [docs/subsystems/video.md](docs/subsystems/video.md).
- **AV1 decode.** The H713 is the first Allwinner chip with AV1 hardware. Whether the existing reverse
  engineering describes a working decoder or only a register map is unresolved.
- **EDID modes.** The 512-byte block goes to the firmware unchanged; which modes it unlocks was never
  worked through. Known gaps: 1600×900, anything at 120 Hz.

## Quality of the thing itself

Less exciting, and the part that decides whether anyone else can use this.

| | Where it stands |
|---|---|
| **Simpler installation** | Today the installer takes seven parameters. It should find the image, the extractor, `sunxi-fel` and the installer U-Boot next to itself, ask only for your SSH key and where to put the dump, and say before each step what it is about to do. The parameters stay for the unusual cases. |
| **Windows** | The installer is written to run there and refuses nothing, but nobody has ever run the Windows path. Until someone does, it is untested, not supported. |
| **Reproducible builds** | Two builds of the same source differ: TF-A, U-Boot and the FIT embed a build time, the Wi-Fi module embeds kernel header paths. Fixable with `KBUILD_BUILD_TIMESTAMP`, `-ffile-prefix-map` and a fixed `mkimage -t`. |
| **A second pair of eyes on the safety paths** | The fan-stall poweroff is armed (see STATUS). The gate, the recovery path and the installer's refusals deserve someone who did not write them trying to break them. |
| **English tooling** | The documentation is English; the tools still speak German on the command line (`--trocken`, `--abzug`, replies `ok`/`fehler`). Aliases or a rename — undecided. |
| **Pictures** | There is a video of the HDMI input running (linked from the README). Still photographs — the projected picture, the board, the UART pads — will follow. A recording of the install from FEL to first boot is still missing. |

## Upstreaming

Some of what we fixed is not projector-specific and belongs in other people's trees: the pinctrl
interrupt-bank fix (`0143`/`0144`), the U-Boot environment offset (`0022`), the `cpu_comm` register and
IRQ correction (`0024a`), and the build-script change that lets a patch series carry comments. Those go
to cstenger first, and where they are his own upstreams' bugs, onwards from there.

## How to help

The two things that would move this fastest are hardware and honesty. Hardware: an HDCP-mandatory
source, a second H713 device to test the installer against, a reference tachometer, a Windows machine.
Honesty: run the parts marked unverified and say what actually happened — a negative result written
down is worth as much here as a fix, and [docs/dead-ends.md](docs/dead-ends.md) exists because of that.
