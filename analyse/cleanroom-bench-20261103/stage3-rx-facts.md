I've collected the receiver-side facts below. One big gap first: none of the receiver windows (`0x0680xxxx`, `0x0684xxxx`, `0x0688xxxx`) and none of the HDMI aux block at `0x0709_1000` have ever been read with the display firmware never started. Doku/227, doku/228 and 90 Q0 only cover the TV-top words and the capture block.

Nearly everything about what the receiver's registers mean comes from reverse-engineering vendor binaries. The firmware-free measurements are limited to:
- power, clocks and the TV-top words;
- the HPD/DDC aux block driven by our own free firmware (crust) on the ARISC;
- byte reads of the audio-status bytes (LINK window, `0x06840000`, read-only) with the firmware running;
- the INCAP timing words.

Column "fw": **with** = the display firmware was running, **without** = it never started, **n/a** = a data file or a standard.

## 1. Register blocks and base addresses

| # | Fact | Source | fw |
|---|---|---|---|
| B1 | The receiver is the address range `0x0680xxxx` / `0x0684xxxx` / `0x0688xxxx`. `0x05000050/54` is not a receiver EDID interface: `0x05000000` is the noise-reduction/composition block. | measured: 2026-09-15 HY310 doku/124 | with |
| B2 | LINK ("port") window at `0x06840000`, described as a byte-wide syscon of size `0x1000`. A 32-bit read returns the byte at the aligned address four times (`0x06840040` → `0x03030303` before HDMI, `0x07070707` after; `0x0684000c` → `0x87878787`; `0x06840010` → `0x4d4d4d4d`). | measured: 2026-09 HY310 stock dumps, doku/nachtlog/S18 §4.4 | with |
| B3 | The `0x06840000` window repeats (aliases) every `0x800` bytes. | measured: 2026-09-02 third-party board, doku/124 | with |
| B4 | Control window at `0x06800800` is byte-wide: 32-bit writes are lost. | measured: 2026-09 third-party board, doku/124 | with |
| B5 | `0x068008FC` read `0x33333333`. `0x0680081C`, `0x06800840`, `0x068008F0`, `0x06800800` and `0x06840374` read 0 before the first source select. | measured: 2026-09-06 HY310 doku/72 | with |
| B6 | With the vendor firmware running, a full dump of `0x06800000`, INCAP and `0x06840000` matched the stock dump except two counter bytes (`0x06840070/74`). Stock before→after HDMI changes only configuration bytes in the port block (`+0x0c`, `+0x10`, `+0x28`, …). | measured: 2026-09-06 HY310 doku/72 run 36 | with |
| B7 | A second receiver base at `0x06841000` holds HDCP/packet registers. | binary-derived | — |
| B8 | Audio PLL block at `0x06880000` (words at `+0x00..+0x18`). Whether the ARM can read it is unmeasured. ARM byte writes there caused no hang. | binary-derived; measured (writes): 2026-09-06 HY310 doku/72 run 35 | with |
| B9 | The firmware selects a port by writing byte `0x068008F1` and `0x06840376`. The PHY reset writes `0x068008FC` bits `0xC0`/`0x10` and touches `0x06800210/220/221/230/240/2C0/137/202` and `0x068008F3`. | binary-derived | — |
| B10 | Replaying those port-select / PHY-reset writes from the ARM caused no bus hang, and the registers answered. | measured: 2026-09-06 HY310 doku/73 H1 | with |
| B11 | `0x068401B1`/`0x068401B5` are a PHY equaliser enable (`0x1B5` bit 4). | binary-derived | — |
| B12 | `0x0684037A` bits `[3:0]` are "signal valid" per port. | binary-derived | — |
| B13 | Avoid `0x068B0000..0x068C0000`: only safe with the demod bus clock on. The firmware's receiver code reads `0x068C00B8` and `0x068C038C`. `0x068C00C0..FC` hold buffer pointers. | measured (hang rule): 2026-09 HY310 doku/69; rest binary-derived | with |
| B14 | `0x068000A7` bit 0 and `0x06E00020` bit 0 are the ARC path switches. ARC is not needed for receive. | binary-derived | — |
| B15 | HDMI aux block at `0x07091000` (RTC/R domain), owned by the ARISC. Layout: `+0x014` HPD pins; `+0xB04` EDID/DDC output gate, one bit per port; `+0xC00 + 0x100·port` one 256-byte DDC RAM per port (`0x07091c00/1d00/1e00`); `+0x020`, `+0x030`, `+0x034`, `+0xB00`, `+0xB08` meaning unknown. | binary-derived; layout confirmed by measured reads, see E-rows | with ARISC fw |
| B16 | TV-top words at `0x06E00000/04/08`. | measured: 2026-11-02 HY320 (cleanroom 00 §1) | both |
| B17 | `0x050c0000` is the deinterlacer, not a receiver core. Its `0x400/0x500/0x600` are register banks, not EDID RAMs. The old guess that the receiver was a known IP block mapped there was wrong. | measured: 2026-09-15 doku/124; cleanroom 00 §3.1 | both |
| B18 | Offsets of a known foreign HDMI-RX IP (e.g. `+0x1104`, `+0x5030`) read 0 here. The register map is not a 1:1 match to any known IP. | measured: 2026-09-08 HY310 S16 | with |
| B19 | No CEC register block is known in this repository. | (unknown) | — |

## 2. Clocks, resets, power domains

| # | Fact | Source | fw |
|---|---|---|---|
| C1 | CCU `0x02001d80` reads `0xc0000000` at boot: bits 31 and 30 are two gates (HDMI-audio bus, capture 300 MHz bus). No reset sits in this word. | measured: 2026-09-06 HY310 doku/72; bit names binary-derived | with |
| C2 | CCU `0x02001d84` reads `0x80000000`: gate bit 31, mux `[24]`, M `[4:0]`. The parent is video PLL 3; `0x02001???` PLL-3 word read `0xb8002f00`, giving 1152 MHz. An earlier boot read `0xb8006300` (2400 MHz). Who reprograms the PLL between boots is unknown. | measured: 2026-09-07/08 HY310 S16, S22 | with |
| C3 | CCU `0x02001d88` reads `0x00010001`: bit 0 gate, bit 16 reset release (capture bus). | measured: 2026-09-06 HY310 doku/72 | with |
| C4 | CCU `0x02001d74` reads `0x81000001` (capture DMA, 300 MHz) and `0x02001d6c` reads `0x80000305`. | measured: 2026-09-06 HY310 doku/72 | with |
| C5 | CCU `0x02001d64`: bit 0 is the demod bus gate, bit 16 its reset. It is 0 at a HY310 boot. Any read in `0x06000000..0x067fffff` needs both bits: `0x06700000` reads 0 without them and `0x7ff` with them. | measured: 2026-09-06 HY310 (cleanroom 00 §3) | with |
| C6 | The TV front-end clock group lives at CCU `0x02001d10..0x02001d60` (bit 31 gates; `0xd20` is the 1296 MHz clock). | binary-derived (vendor CCU table) | — |
| C7 | Only three resets exist in the whole TV region: `0xd64`, `0xd88` and `0xdd8`, each bit 16. | binary-derived | — |
| C8 | Power controller at `0x07001000`. Each domain is a block of `0x80` bytes: domain 1 = TVFE, domain 2 = TVCAP. Control at `+0x20` (1 = on, 2 = off), status at `+0x24` (bit 3 busy, bit 1 done, `[17:16] = 01` on). Its own bus gate/reset is `0x070101ac` bits 0/16. | binary-derived | — |
| C9 | PPU status words `0x070010a4` (TVFE) and `0x07001124` (TVCAP) satisfy `& 0x30000 == 0x10000` in normal operation. genpd reports both domains "on". | measured: 2026-09-08 HY310 S16/S17 | with |
| C10 | With TVFE and TVCAP both off, every access to a receiver window hangs the bus: no abort, no watchdog. | measured: 2026-09-02 third-party board (doku/124, 0096a) | without |
| C11 | Receiver PHY and INCAP sit in TVCAP. The audio DSP island sits in TVFE. | binary-derived (PHY/TVCAP); measured (DSP/TVFE behaviour) 2026-10-09 HY310 doku/173 | — |
| C12 | Who powers what on our stack: U-Boot powers TVFE and TVCAP, then sets `0x2001d6c/74/84` bit 31, then `0x2001d80` bits 31+30, then `0x2001d88` bits 0+16, 12 ms apart, before the MIPS starts. A built-in kernel driver then holds both domains plus four clocks (`d88`, `d80[30]`, `d74`, `d20`) for the whole uptime. Vendor stock: its TV-top kernel driver. | measured (works): 2026-09-17 HY300 Pro, HY310 | both |
| C13 | U-Boot TV-top sequence: `+4 = 0x01111117`, `+8 = 0x404`, `+0 = 0x00111111`, then all three to 0, then the same values again, 12 ms apart. | own boot-loader code; measured values 2026-11-02 HY320 | without |
| C14 | Firmware never started: TV-top reads `0x00111111`, `0x01111117`, `0x00000404`. With the firmware running `+8` reads `0x504`. Writing `0x504` by hand read back and changed nothing visible. | measured: 2026-11-03 HY320 (00 §3.1) | both |
| C15 | Firmware never started: capture block `0x06940000` reads 1 and `0x06940400` reads 0, with no hang. Who wrote the 1 is unknown. | measured: 2026-11-03 HY320 | without |
| C16 | After a standby (genpd cycles TVFE/TVCAP) the TV-top words read `0x10, 0, 0`. Starting the firmware without restoring them stalled the SoC within 200 ms (3 of 3). | measured: 2026-10-09 HY310 doku/172 | with |
| C17 | HDMI aux block clock: R_PRCM `0x07010120` (written 0, then 5 ms, then `0x10000`, bit 16) and `0x07010124` bit 31. Until both are set an ARM access to `0x07091xxx` hangs the SoC. | binary-derived (ARISC firmware); "registers identical under crust and vendor ARISC firmware" measured 2026-10-07 HY310 doku/163 | ARISC |
| C18 | Reading `0x07091010/14` from the ARM hung the SoC 4 times. Enabling R_CCU `0x0701020c = 0x00010001` and RTC `0x07090310` bit 31 did not prevent the hang. After the ARISC initialised the block, `0x07091014` read `0x07` from the ARM. | measured: 2026-09-06/07 and 2026-09-15 HY310 doku/72, doku/124 | without (MIPS) |

## 3. EDID, HPD, DDC, ports

| # | Fact | Source | fw |
|---|---|---|---|
| E1 | The receiver has 3 ports (0..2). The board's socket is on port 0 on the HY310 and port 1 on the HY320. On the HY320 the firmware's hot-plug notification reports source id 4 when the socket is plugged; port 0 never sees a signal. | measured: 2026-11-01 HY320 doku/225 | with |
| E2 | The firmware's source ids are 3/4/5 for ports 0/1/2 (init port map pairs (3,0), (4,1), (5,2), as in the stock IPC trace). | measured: stock IPC trace HY310 doku/88 | with |
| E3 | The EDID image is 512 B: the vendor's HDMI 1.4 block followed by its HDMI 2.0 block, each 256 B with checksum 0. Monitor name "SGD SX8". Header `00 ff ff ff ff ff ff 00 5e 78`. | vendor-data (doku/82) | n/a |
| E4 | Block 0: first DTD 1920x1080p60; Basic Audio; LPCM 8 ch at 32/44.1/48 kHz; HDMI VSDB max TMDS 340 MHz; deep-colour flag byte `0xb8`. | vendor-data; deep-colour bit meaning public (HDMI 1.4 VSDB) | n/a |
| E5 | Block 1 adds 3840/4096x2160p50/60 in 4:2:0, 1080p100/120 and a Dolby Vision block. It lowers max TMDS to 300 MHz. | vendor-data | n/a |
| E6 | Block 0 byte 130 = `0x4c`, block 1 byte 130 = `0x54`. They are identical for their first 130 bytes. | measured: 2026-09-22 HY310 (PC read-back) | with |
| E7 | A port is served one 256-byte block from its own DDC RAM. Which block is a per-port bitmask in ARISC state: bit N set = port N gets block 1. The mask takes effect only at the next full EDID upload. Mask 0 = block 0 on every port. | measured: 2026-09-22 HY310 arisc.md | ARISC |
| E8 | The ARISC rewrites two bytes before serving: the physical-address byte (byte 168 = first PA byte of the HDMI VSDB, `0x10` in the file, served `0x00` on HY310 port 0) and the checksum (byte 255). | measured (difference): 2026-09 HY310; rewrite rule binary-derived; PA semantics public | ARISC |
| E9 | DDC RAMs `0x07091c00/1d00/1e00` read back from the ARM correctly only with the gate `0x07091b04` closed. With gate bits 0..2 open they read all zeros, from the ARM and from the ARISC. | measured: 2026-10-07 HY310 doku/163 | ARISC |
| E10 | With the vendor ARISC firmware, the HY320's port-1 DDC RAM was never written: reads were EDID / random / EDID for ports 0/1/2. The Xbox fell back to 640x480 with no sound. After the port table was fixed: 1080p60 and 48 kHz PCM. | measured: 2026-11-01 HY320 doku/225 | with |
| E11 | Uploading in fragments without waiting for the ARISC's ready byte corrupted the served EDID (`00 ff ff ff ff ff ff e1 fd c5 7f …`) and the PC read no EDID. | measured: 2026-09 HY310 arisc.md | ARISC |
| E12 | HPD register `0x07091014`: one bit per pin, active-low. | binary-derived (ARISC firmware) | — |
| E13 | `0x07091014` read `0x5` and stayed so while a source was plugged on HY320 port 1 (sampled every 50 ms); `0x07` after an EDID reset with nothing asserted (HY310). INFERENCE: consistent with active-low, port 1 = bit 1. | measured: 2026-11-01 HY320 doku/225; 2026-09-15 HY310 | with |
| E14 | The ARISC holds HPD low while the DDC gate is closed. | binary-derived | — |
| E15 | A 200 ms HPD low pulse is enough for a clean edge plus a full EDID re-read at the source. 200 ms is also the stock interval. | measured: 2026-09-07 HY310 doku/88, A2 | with |
| E16 | Full EDID + HPD sequence done 17.65 s after a cold start (HY310). On the HY300 Pro, booting with a source plugged: HPD pulse at 6.3 s, signal notification 7.1 s, picture 7.5 s. | measured: 2026-09-07 HY310; 2026-09-17 HY300 Pro doku/127 | with |
| E17 | Pins PL10..PL15 read function 2 (`PL_CFG1 0x07022004 = 0x2222223f` after IR repair, `0x222222ff` as the vendor ARISC leaves it). Their purpose is unknown. INFERENCE: HDMI DDC/HPD pins. | measured: 2026-10-22 G-EU/HY310/HY320 doku/219, 226 | ARISC |
| E18 | Free firmware (crust) on the ARISC, writing the same aux registers, produced HPD and EDID at a PC: 1080p60, 30 min run, source switches. | measured: 2026-10-07 HY310 doku/163 | with (MIPS) |
| E19 | EDID/HPD has never been exercised with the display firmware never started. | (unknown) | — |

## 4. Signal detect, TMDS, timing

| # | Fact | Source | fw |
|---|---|---|---|
| T1 | No ARM-visible register for TMDS clock, pixel clock or signal lock in the receiver windows is known from measurement. Detection and lock are done by the display firmware polling its PHY. | binary-derived (mechanism) | with |
| T2 | A 32-bit `/dev/mem` read of `0x0684037A` gave a bus error every time, with and without signal. INFERENCE: it is an unaligned word read, not a power problem. | measured: 2026-09-17 HY300 Pro doku/127 | with |
| T3 | INCAP `0x06940874` = active width `[31:16]` / height `[15:0]`; `0x06940548` = v_total `[31:16]` / h_total `[15:0]`. 1080p reads `0x07800438` / `0x04650898`; 720p reads `0x050002d0` / `0x02ee0672`. Sync positions were found nowhere. | measured: 2026-09-07 HY310 doku/nachtlog/E4 | with |
| T4 | `0x06940928` `[15:0]` = locked line count (`0x438` / `0x2d0` over four modes). Bit 31 clears when the firmware does not lock (1600x1200, 1920x1200); the low bits then keep the old value. | measured: 2026-09-07 HY310 doku/88 E3 | with |
| T5 | No source: INCAP total reads 0 (HY310). HY300 Pro "no signal" while audio was locked: INCAP active 0, total `0x04650898`. | measured: 2026-09-19 HY310; 2026-09-18 HY300 Pro | with |
| T6 | The input vsync stamp `0x0514fe64` moves only while HDMI is locked. It stands with HPD low and under the bench boot. | measured: 2026-11-03 HY320 doku/228 | both |
| T7 | Clearing the EDID (HPD low) makes the firmware switch video channel 0 off (`0x05600010 = 0x03000200`). | measured: 2026-11-03 HY320 doku/228 | with |
| T8 | The 44-byte per-lock record (id, rate×100, scan, colour format/space, active size, HDR, full-range, DVI) is firmware memory, not hardware. | binary-derived (layout); content measured with firmware | with |
| T9 | Mode table: a data module named THDMI_ModeList in `database.TSE` (loaded at `0x4be41000`, 1 MiB). 152 records × 54 B, 129 enabled, byte-identical on HY310 and HY300 Pro. Row 14 = 1920x1080 / 2200x1125 / 60 Hz, id `0x00020000`. Ids are `0x0002xxxx`. Ten enabled records carry no active size (frame packing). | vendor-data | n/a |
| T10 | Record fields: `+8` htotal, `+10` vtotal, `+12/+14` active (LE16); `+25` rate as an LE IEEE double; `+49` skip-rate; `+50` progressive; `+52` compare-active; `+53` enabled. Match tolerance ±5 px / ±3 lines, rate ±1.0 Hz (≥ 30 Hz) or ±0.5 Hz; first matching record wins. | binary-derived (all 152 rates decode cleanly: vendor-data) | — |
| T11 | Modes not in the table never lock: 1600x900 left INCAP at the previous geometry and the wall showed the console; 1600x1200 at 162 MHz refused. | measured: 2026-09-21 and 2026-10-02 HY310 | with |
| T12 | Verified lock and correct colour: 1080p60/50/24, 720p50, 576p50, 1366x768, 1024x768, 4K30. | measured: HY310 (STATUS, hdmi-in.md) | with |
| T13 | Xbox 3840x2160p24 was captured and scaled. With 4K50/60 records enabled in memory plus Y420 VIC 96/97 and an HF-VSDB in the EDID, the Xbox sent 4K50/60 but INCAP never locked. | measured: 2026-11-01 HY320 doku/225 | with |
| T14 | Deep colour: a source at 12 bpc 1080p60 (TMDS 222.75 MHz) still had ACR read correctly. After a port restart the source went to 12 bpc (222.8 MHz) and the box showed the console. With VSDB deep-colour bits cleared (`0xb8` → `0x80`): 7/7 renegotiations at 148.5 MHz with picture. | measured: 2026-09-08 HY310 S16; 2026-10-17 HY310 doku/215 | with |
| T15 | On the HY300 Pro a cold TVCAP domain at plug time meant the receiver never locked (once it worked with the domain still warm). HY310 firmware won that race. Fixed by holding the domains from boot. | measured: 2026-09-17/18 HY300 Pro, HY310 | with |

## 5. InfoFrames, colour, audio status

| # | Fact | Source | fw |
|---|---|---|---|
| A1 | The firmware parses AVI, SPD, VSI and Audio InfoFrames. Colour space, range and DVI come only from its record; no ARM read of an AVI register is measured. | binary-derived | with |
| A2 | Packet reader: selector `0x06840112`, data from `0x068401C0`; `0x0684001D` `[2:1]` = pixel format from AVI Y, `[0]` video mute. | binary-derived | — |
| A3 | Interrupt bytes: `0x06840005` summary, `0x06840006` enable (`0x6A`), `0x0684000F` bit 3 = Audio InfoFrame received, `0x06840010/11` audio group A enable/status (bit 6 of `0x11` = new N/CTS, write-1-to-clear), `0x06840012/13` group B. | binary-derived | — |
| A4 | `0x06840010` reads `0x4d` and `0x0684000c` reads `0x87` after HDMI starts. When a source starts sending audio, `+0x0F` bit 3 and `+0x11` bit 6 were seen set in a 1 ms poll. | measured: 2026-09-08 HY310 S16 | with |
| A5 | The audio poll reads ten bytes every 100 ms: `+0x40`, `+0x45..+0x47` (N, 20 bit), `+0x48..+0x4A` (CTS, 20 bit), `+0x56`, `+0x15F`, `+0x160`. It runs with or without a picture. | measured (driver behaviour); offsets binary-derived | with |
| A6 | `+0x40`: `0x03` before HDMI, `0x07` with picture, `0x17` with audio. `[2:0] = 7` means output on. `[7:4]` is an audio status nibble; bit 7 is guessed to mean non-PCM. | measured: 2026-09-08 HY310; meaning binary-derived | with |
| A7 | N/CTS at 1080p60: 48 kHz → N 6144, CTS 148494/148500; 44.1 kHz → N 6272; 32 kHz → N 4096. No audio or after a rebind: N = 2, CTS = 24. Reset value of `+0x48` is `0x18`. | measured: 2026-09-08 HY310 S16; formula public (HDMI ACR) | with |
| A8 | `+0x15F` `[6:4]` is the measured rate code: `0x30` = 48, `0x20` = 44.1, `0x10` = 32 kHz, `0x00` = no audio. `+0x56` `[3:0]` = 2 at 48 kHz (IEC 60958 byte 3 code). | measured: 2026-09-08 HY310; codes 4..7 (88.2..192 kHz) binary-derived; IEC table public | with |
| A9 | `+0x160` and `+0x15E` read 0 with PCM. `0xFF` meaning raw is binary-derived and not measured. | measured/binary-derived | with |
| A10 | A source that sends no audio packets leaves N = 2 and rate 0. A laptop's IEC958 switch dropped to off after every renegotiation. | measured: 2026-09-08 HY310 | with |
| A11 | Receiver audio leaves through the DSP island (I2S), not through the ARM. The audio PLL is programmed by the firmware after the first new-N/CTS event. | binary-derived; path measured working 2026-09-08 | with |

## 6. Observed behaviours and failures

| # | Fact | Source | fw |
|---|---|---|---|
| F1 | After a standby that parked the MIPS following DRAM self-refresh, every LINK byte read never completed and stopped the bus. This held whether the poll ran right after resume or was restarted 3 s later; the watchdog reset the box 16 s later. TVFE/TVCAP had been power-cycled and the TV-top words reset; that is not proven as the cause. | measured: 2026-10-08 HY310 doku/176 | parked |
| F2 | INCAP stops answering the CPU once the MIPS is parked. Powering TVCAP off under a running capture DMA hung the sleep 5 of 5 times; clearing bit 31 of `0x06940928` and `0x06940968` first fixed it (30/30). | measured: 2026-10-09 HY310 doku/173 | with |
| F3 | All 1210 HDMI-state register writes from the TSE data files, replayed from the ARM without the MIPS's runtime, did not hang the board. Those writes are all in `0x05xxxxxx`/`0x06xxxxxx` (13-byte entries, base + addr·width, big-endian mask/value). | measured: 2026-09-07 HY310 doku/72 runs 62/63; file format vendor-data | with (domains on) |
| F4 | An old in-tree driver that wrote `0x07091014` directly hung the SoC hard (twice). | measured: 2026-09 HY310 doku/68 | without ARISC init |
| F5 | The vendor ARISC firmware's start switches PL9 (IR) off; no other side effect on the receiver was seen. | measured: 2026-10-22 doku/219 | ARISC |

## 7. Excluded: HDCP

| # | Fact | Source | fw |
|---|---|---|---|
| H1 | Out of scope; listed only so it is recognised. `0x06840093` bit 0 = 1.4 key loaded: it read `0x41` on HY310 with no key loaded, so bit 0 alone proves nothing; it read `0x45` on HY320. `0x06840422` bit 0 = a 2.2 session stands (`0x01` seen on HY320). Base `0x06841000`. | measured: 2026-10-02 HY310, 2026-11-01 HY320; meanings binary-derived | with |

## 8. Unknown

- How to bring up the receiver core, PHY, TMDS clock detect, equaliser, port mux and lock without the firmware. No measured register meanings exist for `0x06800000..0x068fffff` beyond the audio-status bytes. The block sizes are unknown.
- Whether `0x0680xxxx`, `0x0684xxxx` and `0x0688xxxx` read without a hang under the bench boot. They were never read there. INFERENCE: the bench kernel had the built-in TV-domain driver, so TVFE/TVCAP were probably on, but no PPU status was logged in that boot.
- Any ARM-readable TMDS frequency, pixel clock, h/v total or sync polarity register in the receiver itself. INCAP totals exist only because the firmware's capture writes them.
- Where the AVI InfoFrame bytes can be read as hardware registers. The colour format and range readout has only ever come through the firmware's record.
- The audio PLL readout, the compressed-audio indicator, and channel count or allocation (only available from the Audio InfoFrame).
- HPD/DDC without any ARISC firmware. ARM writes to the aux block after its clock is on are untried; ARM reads work.
- What `0x07091020`, `0x07091030`, `0x07091034`, `0x07091b00` and `0x07091b08` do, and what PL10..PL15 carry.
- CEC: no register, pin or block identified.
- Whether the hardware supports deep colour at all; only the firmware's refusal is known. 4K50/60 never locked.
- Why `0x06e00008` reads `0x504` with the firmware against `0x404` from the boot loader. Who writes `0x06940000 = 1`.
- Why the LINK read hangs after a park (power state of TVCAP/TVFE after resume, unmeasured).
- Whether HDCP-only sources give a picture without negotiation (excluded, unmeasured).

**Main sources:**
- `docs/subsystems/hdmi-in.md`, `docs/subsystems/arisc.md`
- doku/72, doku/88, doku/124, doku/163, doku/172, doku/176, doku/215, doku/225, doku/227, doku/228
- `doku/nachtlog/S16`, `S17`, `S18`, `S22`
- kernel patches `0001`, `0096`, `0096a`, `0107`, `0136`, `0136b`, `0136h`, `0174`, `0179`, `0337`, `0338`
- `crust-h713/0001`, `0050`; U-Boot `arch/arm/mach-sunxi/h713_mips.c`
- `cleanroom-h713/spec/00-overview.md` §3.1; `cleanroom-held/90-open-questions.md` Q0, Q6
