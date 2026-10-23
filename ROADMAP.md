# Roadmap

What this port cannot do yet, why, and what it would take. Nothing here is a promise with a date; it is an honest list,
kept next to [STATUS.md](STATUS.md) so the two never drift apart. "Not measured" is a statement about our evidence, not
about a feature's chances.

## Missing stock features

| | State | What it would take |
|---|---|---|
| **Standby, and a quiet power supply** | The release runs the vendor's ARISC firmware and offers no standby; off is U-Boot's gate at 2.9 W, silent. Our own ARISC firmware, crust, suspends to RAM (2.0 W on the HY300PRO-G-EU, 2.4 W on the HY310) and powers off to 0.3 W - and with it the power supply hums or whines. A night of measurements with a microphone moved the tone with no crust change at the same power (`doku/218`; the owner's decision of 22.10.2026). crust stays in the image as an experiment: `h713-arisc set crust`. | Either a cause for the hum that a firmware can remove (the supply runs in burst mode below about 2.5 W, the candidates are in `TODO.md` 2.42), or a power-off the way stock does it - the vendor's own ARISC firmware holding the rails off at 0.3 W, which would need BL31 to find that firmware on the device (`TODO.md` 2.140, the large way). A standby without DRAM self-refresh was quiet to the microphone but drew 2.4 W and still whined to the owner's ear. |
| **The flicker** | Marco and a tester see the picture flicker faintly during output, at key presses and program starts. Measured on the HY310 (`doku/213` §3): the lamp's light follows the current the SoC draws, +1.2 % per burst of computing at 1296 MHz, with the picture chain and the lamp control ruled out - a hardware coupling between the LED boost and the CPU supply. That the CPU load is the cause of the flicker the eye sees is a **hypothesis, not proven** (`TODO.md` 2.99). | An oscilloscope at VIN, 5 V, VDD_CPU and the LED current during a CPU burst, with the owner at the device (`TODO.md` 9.3n); less idle load of the clients; the same measurement on the HY300PRO-G-EU, whose lamp is an LCD backlight driven by the display firmware's PWM. |
| **The HY300 (Pro) of issue #1** | The tester's older model boots our test images, but its infrared remote does nothing yet (`TODO.md` 2.134). A retrofit (`test11`, 22.10.2026) applies the infrared pin after the vendor firmware's start and loads the original remote's key table; it was checked on the HY300PRO-G-EU in his state and sent to him. | His report, and his raw infrared log if the retrofit does not help. |
| **AV1 decode** | cstenger's AV1 driver decoded bit-exact on the HY310 (13.10.2026, `doku/211` §5). It is switched off since kernel `0310`: next to a decoding AV1 core the video engine cannot recover from a damaged H.265 stream, and with it on the engine runs at 432 MHz. | A reset guard that lets both live side by side, or the decision to run AV1 alone at the lower clock (`TODO.md` 9.3b). |
| **Autofocus** | Built since `v0.95-beta`: the vendor's search with the built-in camera, turns round at the ends of the travel, sharp at a wall twice at the same position (`doku/134` A4). | More walls and evenings; the metric's span was small in the measured runs. |
| **Reloading the display firmware at run time** | Works since `v0.96-beta` (`h713-mips-restart`); used after a standby. | Nothing; the picture is black, not the console, while it runs (`doku/215`). |
| **The vendor display stack (`ge2d`), `tvtop`, `tvfe`** | **Not needed.** Inventoried against the HY310's own modules (26.09.2026); the display firmware configures the receive side itself. | - |
| **Device sounds** | The DSP mixes the box's own sounds into HDMI (`hw:hy310hdmi,0`, `v0.96-beta`); Kodi, mpv and Firefox play through it. Nothing in the base image makes a sound of its own - no click on the settings page. | Something that plays them. |
| **CEC** | Not supported: the ARISC's physical address in the HDMI vendor block differs between crust and the vendor firmware (`TODO.md` 2.28), and nothing reads CEC. | A source that speaks CEC and one evening. |

## Not proven on this build

- **A release image built from `main` after the documentation round** (`TODO.md` 1.0 (5b)): the images of 22.10.2026
  came from the `medien` branch at the commit `main` now carries; the final build repeats it from `main` and is installed
  on both boards before the tag.
- **The Windows path of the installer**: written, never run.
- **Modes beyond the measured list**: the driver locks on the display firmware's own mode table and refuses anything
  else by name. 1080p100/120 lock with EDID block 1 (`h713-tv ctl edid block1`); under the warp a 120 Hz source draws
  about 19 frames a second (02.10.2026), not explained.

## Quality of the thing itself

| | Where it stands |
|---|---|
| **Installation** | `install <release folder>` finds the table, `u-boot-installer.bin` and `sunxi-fel` next to each other, unpacks `.img.zst` itself, needs neither dump nor `--vendor` on a device that already runs this layout. Open: `--keep-env` took `h713_gate=0` out of a dump's environment instead of the device's (`TODO.md` 2.137); the installer does not yet carry `/etc/h713` over (settings, Wi-Fi, the remote's bond). |
| **Reproducible builds** | Since `v0.96-beta` the build clock is the commit's date and the stamp says `reproducible: yes` or why not; the `v0.97-beta` stamps say yes for both boards. The libva tar differed between the two board builds (`TODO.md` 2.136, probably the build path in the result). |
| **A second pair of eyes** | The gate, the recovery path and the installer's refusals deserve someone who did not write them trying to break them. So does all of the code, written by AI: the disclaimer at the top of the README is meant. |
| **English tooling** | Done for everything a user sees; the device tools, units and the overlays are English. `h713-focus` keeps two German switches on purpose. |
| **Pictures** | The menus, pages and overlays are pictured in the guides since this round (rendered from the real code on a PC, over a synthetic backdrop). Still missing: photographs of the board, the UART pads and the projected picture, and a recording of an install. |

## Upstreaming

Some of what we fixed is not projector-specific: the pinctrl interrupt-bank fix (`0143`/`0144`), the U-Boot environment
offset (`0022`), the `cpu_comm` register and IRQ correction (`0024a`), the v4l2-core fix for `VIDIOC_QUERY_DV_TIMINGS`
(`0136w`), the build-script change that lets a patch series carry comments. Those go to cstenger first, and where they are
his upstreams' bugs, onwards from there.

## How to help

Hardware and honesty. Hardware: a second unit of any board in the table, an HDCP-mandatory source, an oscilloscope at the
lamp, a Windows machine. Honesty: run the parts marked not measured and say what happened - a negative result written
down is worth as much here as a fix, and [docs/dead-ends.md](docs/dead-ends.md) exists because of that.
