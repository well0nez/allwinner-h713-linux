# HY310 Projector — Mainline Linux Port

> **⏸️ Development paused (August 2026)**
>
> The server that held the reverse-engineering notes and the cached
> research for this project was wiped — snapshots included. Rebuilding
> that groundwork isn't something I can do right now, so work on the port
> is on hold until further notice.
>
> Everything that is committed here stays as it is. The repo remains
> public; forks and pickups are welcome.

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/well0nez)

Mainline Linux 6.16.7 for the **HY310 portable projector** (Allwinner H713
/ sun50iw12p1). Built from zero — no vendor source code or documentation —
through reverse engineering of the stock Android firmware.

> **🔬 Project status: ALPHA**
>
> - ✅ ARM userland, networking, audio, IPC: **working**
> - ✅ ARM↔MIPS communication (cpu_comm + bidirectional callbacks): **working**
> - ✅ HDMI-RX signal detection (TMDS lock @ 1080p60, signal callbacks):
>   **working**
> - ⚠️ **HDMI-RX picture quality is broken**: shows up on the DLP
>   projector but as 4×1 XRGB grayscale tiling because of a display-
>   channel format mismatch. This is the main thing we're debugging.
> - ⚠️ **No working desktop right now**: Wayland / labwc / GPU acceleration
>   / video decoding are intentionally disabled. The display pipeline is
>   currently routed through the HDMI-RX path while we debug it, not
>   through a desktop compositor.
> - **The HY310 has no HDMI output port**. Only HDMI input. The DLP
>   projector itself is the only display output.
>
> The repo is public so other RE engineers can join. See
> [docs/contributing-re.md](docs/contributing-re.md) if you want to help.

## Read order

If you're new to the project:

1. **[STATUS.md](STATUS.md)** — per-subsystem status table (60-second read)
2. **[docs/hardware.md](docs/hardware.md)** — what's on the board
3. **[docs/architecture.md](docs/architecture.md)** — how the three CPUs
   (ARM + MIPS + ARISC) work together
4. **[SESSIONS.md](SESSIONS.md)** — chronological RE timeline. Read this
   before re-trying ideas, or you'll repeat dead ends we already did.
5. **[docs/known-issues.md](docs/known-issues.md)** — open bugs +
   workarounds

If you want to contribute RE work:
- **[docs/contributing-re.md](docs/contributing-re.md)** — tools,
  workflow, what's actionable now.

## Hardware quick reference

| Component | Details |
|---|---|
| SoC | Allwinner H713 (sun50iw12p1), 4× Cortex-A53 @ 1.5 GHz |
| RAM | 1 GB DDR3 |
| Storage | 7.3 GB eMMC (Samsung), **HS200 @ 200 MHz SDR** (was HS400 — downgraded for portability across boards) |
| Co-processor #1 | MIPS32 LE, runs `display.bin` (1.25 MB), owns display + PQ + HDMI-RX |
| Co-processor #2 | OR1K BE ARISC SCP (172 KB firmware), owns PMU + HPD + EDID |
| Display **input** | HDMI 1.4 via Synopsys DW-HDMI-RX, 1080p60 verified |
| Display **output** | LVDS → DLPC3435 → DLP imager. The projector is the only output. **No HDMI-out port.** |
| GPU | Mali-G31 (Panfrost) — **disabled in current build** |
| Wi-Fi | AIC8800D80 SDIO (802.11ac, dual-band, onboard) |
| Bluetooth | AIC8800 BT 5.4 via UART1 |
| Audio | Internal codec at `0x02030000`, speaker output |
| USB | 3× EHCI + 3× OHCI, one external USB-A port |

Full hardware overview: [docs/hardware.md](docs/hardware.md).

## Reverse-engineering highlights

Things that took us many sessions to figure out and aren't in any
datasheet (more in [SESSIONS.md](SESSIONS.md)):

- H713 pinctrl uses **D1-style 0x30 bank spacing**, not H6-style 0x24.
- R_PIO PM bank needs `SUNXI_PINCTRL_NEW_REG_LAYOUT`.
- USB PHY needs **bit 0 set at PMU base** (undocumented quirk).
- Msgbox has **3 user regions** with empirical write-protection map.
- H713 Msgbox is **edge-triggered**, not level-triggered. Stock IRQ TX
  pattern has 0% success — pulse-doorbell workaround in
  `sunxi_msgbox_amp.c`.
- HDMI-RX state machine has **zero progress bits** — the obvious lock
  bits are zero in stock too. The real gate is `Vp_Init` parameter 2.
- **`decd.ko` is dead code** for the HDMI-RX path. Stock uses
  `ge2d_dev.ko`, not `decd.ko`. (Cost us 5 sessions to figure out.)
- HPD pin is at **undocumented register `0x07091014`** — extracted from
  ARISC firmware RE.

## Quick start

Build:

```sh
export KDIR=/path/to/linux-6.16.7
./scripts/build_kernel_arm32.sh
```

Flash: [FLASHING.md](FLASHING.md). Rootfs: [ROOTFS.md](ROOTFS.md).
Userspace daemons: [userspace/](userspace/). Bring up HDMI input:
[docs/subsystems/hdmi.md](docs/subsystems/hdmi.md#bringing-up-hdmi-input).

## Boot architecture (one-line summary)

HY310's stock U-Boot can't easily be replaced. It only accepts **Android
Boot v3** format. The kernel cmdline is **hardcoded in DTS** (U-Boot
ignores the boot-image header cmdline). The MIPS co-processor is loaded
**by U-Boot before the kernel starts** — Linux comes up to an already-
running MIPS.

Detail: [docs/subsystems/boot.md](docs/subsystems/boot.md).

## Repository layout

```
dts/                  Device-tree source (sun50i-h713-hy310.dts)
dt-bindings/          Clock + reset ID headers for H713 CCU
config/               Kernel defconfig, module autoload
patches/              21 patches against vanilla linux-6.16.7
drivers/              Out-of-tree kernel modules
  audio/                Internal codec + CPU-DAI + machine
  cpu_comm/             ARM↔MIPS IPC driver
  decd/                 Mainline port of stock decd.ko (currently inactive)
  display/drm/          h713_drm DRM/KMS shim (active for limited scanout)
  display/ge2d/         Mainline port of stock ge2d_dev.ko (blacklisted — will become primary)
  media/av1/            H713 AV1 hw decoder (V4L2 stateless, source present, NOT in defconfig — untested)
  misc/                 Board manager (fan, NTC, GPIO)
  tvtop/                sunxi_tvtop display bus fabric + clock manager (required by display drivers)
  wifi/                 AIC8800D80 SDIO + BT
  Archived/             Read-only reference copies of pre-refactor cpu_comm/tvtop/decd. NOT compiled.
scripts/              Build, flash, module install
tools/                MIPS elog reader, env analyzer, regression tests
docs/                 Documentation (subsystems/ + re/)
reference/            Stock-Android artifacts (DTB, GPIO map, kallsyms)
firmware/             Vendor blobs (`hy310-edid.bin`, `hdcp_v22.bin`)
userspace/            HDMI-RX + picture-quality daemons (hy310-hdmird, hy310-pqd)
```

## Userspace components on the device

The kernel side is half the story. These userspace components do the
heavy lifting at runtime:

- **`hy310-hdmird`** — C++ daemon that replicates stock `tvserver`. Loads
  HDCP22 key, registers 9× `MipsHalCallback_*` routines, runs the 12-call
  init sequence, listens on `/run/hy310-hdmird.sock` for source-switch.
  Source: [`userspace/hy310-hdmird/`](userspace/hy310-hdmird/).
- **`hy310-pqd`** — picture-quality daemon. DE2 gamma works.
  Source: [`userspace/hy310-pqd/`](userspace/hy310-pqd/).
- **`/usr/local/bin/decd_submit_test`** — exercises the `decd` ioctl path
  (mostly historical at this point — see [SESSIONS.md](SESSIONS.md)).

## Contributing

The project is in alpha. Things break. PRs and issues are welcome.

- For RE work (registers, firmware, drivers): start at
  [docs/contributing-re.md](docs/contributing-re.md).
- For docs/typos/cleanup: just open a PR.
- For new subsystem ports: open an issue first so we can coordinate.

## License

GPL-2.0, matching the Linux kernel itself.
