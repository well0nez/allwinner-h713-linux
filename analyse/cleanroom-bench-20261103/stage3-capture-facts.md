## Capture path fact inventory (INCAP → DRAM ring → scanout channel 0)

**Summary.** Every capture fact comes from runs with the display firmware running. The only firmware-free reads are passive bench-boot dumps from doku/228's logs: there the capture block is empty, and nobody has tried to program or start a capture without the firmware. Two corrections to the brief:
- **Who rewrites the slots each frame.** Channel 0's slot words `0x05600070..0x090` and `VCH_ADDR_LATCH` are rewritten every frame by the project's own Linux display driver, 2.8–3.1 ms after each panel vsync (doku/198 §1, doku/200 §4). The firmware does not do it.
- **The ring is not at `0x06940000`.** That address is the INCAP register block; the ring itself is in DRAM.

FW column: **with** = firmware running, **without** = firmware never started, **static** = data or arithmetic only.

### 1. Blocks and bases
| # | fact | source | FW |
|---|---|---|---|
| B1 | The capture block CAP/INCAP sits at `0x06940000`; the whole window `0x000..0xffc` reads without a hang in the normal boot. The project tree maps it as a `0x1000` window. | measured: 2026-11-03 HY320 doku/228 (logs/r2-normal.log) | with |
| B2 | Live word groups: `0x000..0x008` top; `0x100/0x104` status and frame/line; `0x400` path word; `0x540..0x560` input timing; `0x584..0x620` change with the signal (statistics); `0x800..0x8ac` format, convert, scaler, crop; `0x8f0`/`0x930` slot tables; `0x920..0x92c` luma output channel; `0x960..0x96c` chroma output channel; `0x970..0x978`; `0xa00..0xa30` status, including the write index `0xa0c`. | measured: 2026-11-03 HY320 doku/228 (diff-sig-nosig-client.txt) | with |
| B3 | The file's tables write `0x400`, `0x440..0x4e8`, `0x800..0x8a0` (the input colour converter at `0x824..0x848`, the 4:2:2/4:4:4 converter at `0x84c..0x854`), `0x8a4..0x8ec`, `0x8c0/0x8c8` [2:0], `0x8d0` [17:0] = `0x300`, and `0x970 = 0x0c000000`, `0x974 = 0x01000100`, `0x978 = 3`. | vendor-data (database.TSE, doku/84 §2.5) | static |
| B4 | The firmware's code writes `0x858..0x880` (capture downscaler), `0x440..0x448`, `0x464/0x468`, `0x920..0x96c`, and only reads `0xa0c`. | binary-derived (held) | — |
| B5 | `TVTOP` at `0x06e00000` holds 3 words (`+0`, `+4`, `+8`), the clock/reset words of the TV blocks. On the HY320 a 4th word `+0x1c` also changes across a standby. | measured: 2026-10-09 HY310 doku/172; 2026-11-03 HY320 doku/227 §9 | both |
| B6 | Display top `0x05700000`, 7 words, set by the boot loader: `+00 0xfff11111`, `+04 1`, `+40 0x00011111`, `+44 0x11111111`, `+80 0x1111`, `+84 0xfff000ef`, `+88 0x11111111`. The firmware does not rewrite them. | measured: 2026-09-05 HY310 doku/71; 2026-11-03 HY320 | both |
| B7 | TVFE router word `0x06700000` reads 0 with the bus-demod clock off and `0x7ff` with it on. | measured: 2026-09 HY310 (patch 0138 note, journal S17) | with |
| B8 | The vendor writes `0x003003ff` to `0x06700000`. | binary-derived (held) | — |
| B9 | Power controller at `0x07001000`: domain 1 = TV front end (`+0x80`), domain 2 = TV capture (`+0x100`). Both read 1 at boot; the OS shows TVFE/TVCAP "on". | vendor-data (stock DTB); measured: 2026-09-05 HY310 doku/71 | with |
| B10 | All five power domains read wait `0x8`, delays `0x00080808`, ctrl 1, status `0x00010000` (= on). | measured: date not stated, patch 0024 | with |
| B11 | Domain register layout (base + offset + domain × `0x80`, control `+0x20`: 1 on, 2 off; status `+0x24`), bus gate/reset `0x070101ac` bits 0/16, and "vendor writes `0x06940000 = 1` after powering the capture domain". | binary-derived (held 90 Q6) | — |
| B12 | `0x068b0000` ("TVTOP-A") is on the hard block list: an ARM read wedges the SoC. The original observation is not in doku/71. | measured: before 2026-09-05 HY310 doku/71 | with |
| B13 | Stock device tree: no node maps `0x06940000`; `tvcap@6800000` is an IOMMU node only; `tvtop@5700000` reg = `0x05700000`, `0x06e00000` (tvcap), `0x06700000` (tvfe), with no interrupts. The only display-area interrupt is SPI 110 (id 142) on the scanout node. | vendor-data (stock DTS, doku/84 §3.2, doku/71) | static |
| B14 | CCU gates named for the capture side: `0x02001d74` bit 31 (vincap-dma), `0x02001d80` bit 1 (cap-300m), `0x02001d88` bit 0 gate / bit 16 reset (bus-tvcap), `0x02001d20` (tvfe-1296m). These are from the project's clock table; no measurement exists. | binary-derived (held) | — |
| B15 | Capture-related interrupt sources exist only on the co-processor's own interrupt controller. | binary-derived (held) | — |

### 2. Ring and slots
| # | fact | source | FW |
|---|---|---|---|
| R1 | Three NV16 slot pairs. Y: `0x4c3ef000`, `0x4c5ee000`, `0x4c7ed000`. C: `0x4c9ec000`, `0x4cbeb000`, `0x4cdea000`. | measured: 2026-09-06/07 HY310 doku/86, doku/88; 2026-11-03 HY320 doku/228 | with |
| R2 | Y slot spacing is `0x1ff000` (2 093 056 B); C slot i = Y slot i + `0x5fd000`. So the three Y slots are contiguous, then the three C slots. The ring spans `0x4c3ef000..0x4cfe8fff`. | measured (R1); arithmetic | static |
| R3 | One slot (`0x1ff000`) holds 1920 × 1080 = 2 073 600 B plus 19 456 B, so at most 1090 lines at a 1920 pitch. [INFERENCE: arithmetic] | static | static |
| R4 | Ring content is NV16: luma W×H, chroma W×H interleaved Cb/Cr; grey reads Cb ≈ Cr ≈ 128 (e.g. Y 219 / Cb 128 / Cr 128). | measured: 2026-09-08 HY310 doku/96 §7 (journal S11) | with |
| R5 | The ring lies in the reserved region `0x4bf41000`, size `0x1a00000` (26 MiB, no-map, the firmware's frame buffer per `display_cfg.xml`), at offset `0x4ae000`. | vendor-data; measured address inside | static |
| R6 | Luma table `0x8f0..0x904` = six entries, address >> 4: `04c3ef00 04c5ee00 04c7ed00 04c7ed00 04c7ed00 04c7ed00` ([A,B,C,C,C,C]). Chroma table `0x930..0x944` = `04c9ec00 04cbeb00 04cdea00` ×4 likewise. | measured: 2026-11-03 HY320 doku/228; 2026-09-05 HY310 doku/71 (`0x900 = 0x04c7ed00`) | with |
| R7 | The hardware uses 3 entries only. Writing 4 into entry 4 (`0x8fc`/`0x93c`) and the counters `0x8c0`/`0x8c8` is accepted, but the pointer stays on A,B,C. `0x978` = 6 or 4 had no effect. `0x8d0` = `0x600` destroyed the picture (21/s). | measured: 2026-10-11 G-EU doku/198 §2 | with |
| R8 | The slot addresses come from a memory plan in the owner's file (module key `DynamicMemory_1024M_1024M_PROJECTOR`, field = offset << 8). With 6 distinct buffers the firmware programmed all 6; the capture kept 3 and the noise-reduction stage read entries 4–6, giving a wrong picture. | measured: 2026-10-11 G-EU doku/198 §2 (vendor-data file) | with |
| R9 | The noise-reduction block holds the ring addresses too: `0x05000400..0408` = `04c3ef00`, `04c5ee00`, `04c7ed00` (`0x40c..0x414` repeat the third); `0x05000500..` holds the chroma ones. Its own buffers are at `0x4d028000..` and `0x4d35a000..`. | measured: 2026-11-03 HY320 spec/20 §5.1, spec/12 | with |
| R10 | The NR write channels `0x05000178/01b8/0278/02b8` have bit 31 set in the HDMI state (`0x050001b8 = 0xe0020438`, `0x05000278 = 0xe002021c`). The owner's init table leaves them at `0x60020000`. | measured: 2026-11-03 HY320 spec/20 | both |
| R11 | Writer behaviour, checked against slot content (CRC, moving source): strict A→B→C, never the same slot twice in a row, and a finished slot stays untouched for two more frame periods. | measured: 2026-10-11 G-EU doku/200 §1 | with |

### 3. Write index, counters and sizes
| # | fact | source | FW |
|---|---|---|---|
| W1 | `0xa0c` [2:0] = index of the slot being written (0 = A, 1 = B, 2 = C, in table order). It steps by one at each source frame boundary together with `0x104`, about 59.9 changes/s at 60 Hz. | measured: 2026-10-11 G-EU doku/200 §2 | with |
| W2 | Timing at 1080p60 scaled to 720 lines: writing starts 1.6 ms after the index step, top first; line 400 at about 9 ms, line 700 at about 16 ms; done before the next boundary. | measured: 2026-10-11 G-EU doku/200 §1 | with |
| W3 | After some standbys the bits above [2:0] are set (`0x4b0..0x4b2`, `0x4c0..0x4c2`; [11:4] mirror `0xa08`; `+0x004` bit 8 and `0xa24` bytes 1/3 differ). Seen after 9 of 25 standbys; [2:0] still steps; only a warm start clears them. At 7 of 25 resumes `0x80200d00` reads for 11–16 ms before the index is valid. | measured: 2026-10-15 HY310 patch 0314 | with |
| W4 | The vendor reads `0xa0c` masked to 3 bits. | binary-derived (held) | — |
| W5 | HDMI 1080p60: `0xa0c` = 2 at the sample time. No signal: `0xa0c` = 0, and `0xa00 = 0x110`, `0xa04 = 0x08000800`, `0xa20 = 0x00400780`, `0xa24 = 0x00440044`, `0xa28 = 0x00080200` (with signal `0x484`, `0x086407c0`, `0x00540780`, `0x0064005c`, `0x20080200`). | measured: 2026-11-03 HY320 doku/228 | with |
| W6 | `0x104` = (frame << 16) \| line of the source. It keeps counting with the capture outputs disabled. Without a signal it stood: `0x7f6b01f4` at 564 s and again at 622 s. | measured: 2026-09-07 HY310 doku/84 §2.0; 2026-11-03 HY320 doku/228 | with |
| W7 | `0x100` stays constant (`0x407` HY320; `0x427`/`0x407` HY310); nothing seen that behaves like interrupt status. | measured: 2026-09-07 HY310 doku/84; 2026-11-03 HY320 | with |
| W8 | `0x874` = active (W << 16 \| H): 1080p `0x07800438`, 720p `0x050002d0`. `0x548` = total (V << 16 \| H): `0x04650898` = 1125×2200, 720p `0x02ee0672` = 750×1650. | measured: 2026-09-08 HY310 doku/96; 2026-11-03 HY320 | with |
| W9 | At 1080p60: `0x540 = 0x18000464`, `0x54c = 0x00290461`, `0x550 = 0x00c00840`, `0x554 = 0x052c0208`, `0x558 = 0x04650898`, `0x55c = 0x0023045b`, `0x560 = 0x00b50835`. | measured: 2026-11-03 HY320 doku/228 | with |
| W10 | Reading of W9: `0x54c`/`0x55c` span 1080 lines and `0x550`/`0x560` span 1920 pixels; `0x550` starts at 192 = H sync 44 + back porch 148 of the 1080p60 timing. [INFERENCE] | public (CEA-861 1080p60 timing) | — |
| W11 | Row bytes `0x924` (luma) / `0x964` (chroma) = width/16, the same in both halves: `0x00780078` at 1920, `0x50` at 1280. Widths that are not a multiple of 16 round up (852 → 864). | measured: 2026-09-08 HY310 doku/96; 2026-11-03 HY320; 2026-09 G-EU patch 0136g | with |
| W12 | Output control `0x928`/`0x968` = `0x60020000` \| height, plus bit 31: `0xe0020438` (1080), `0xe00202d0` (720), `0x600200f0` (no signal, HY310). | measured: 2026-09-05/08 HY310 doku/71, doku/96 | with |
| W13 | Capture-scaler output = `0x86c` (width) × `0x870` (height) on the 720p-panel G-EU. 1920×1080 → 1280×720 (row bytes `0x50`, factor `0x864 = 0xaaaa`); 1280×1024 → 900×720 (`0x39` = 912 B/line, `0xb400`); 1024×768 → 960×720 (`0x3c`, `0xf000`); 1360×768 → 1274×720; 1366×768 → 1280×718; 800×600 → unscaled (`0x32`). | measured: 2026-10-12 G-EU doku/206, patch 0260 | with |
| W14 | Check of W13: the last written byte of a slot at 1280×1024 is 656 639 = 720 lines × 912 B; 1366×768 fills 717.99 lines; 800×600 fills 600. The scaler keeps the aspect and is bounded by both panel sides. | measured: 2026-10-12 G-EU doku/206 | with |
| W15 | `0x864` and `0x87c` are both factors (`0xb400`/65536 = 720/1024). At 1:1 on the HY320 they read `0x42010000` / `0x08010000`; the low 22 bits = `0x10000` = 1.0. [INFERENCE on the field split] | measured: 2026-10-12 G-EU doku/206; 2026-11-03 HY320 | with |
| W16 | Running state: `0x858 = 0x0c020000`, `0x85c = 0x0c020c02`, `0x84c = 0x04000c00`, `0x880 = 0x20`, `0x884 = 0x04000001`, `0x888`/`0x8a8 = 0x07800000`, `0x88c`/`0x8ac = 0x04380000`, `0x8a4 = 0x000f0101`. | measured: 2026-09-07 HY310 doku/84; 2026-11-03 HY320 | with |
| W17 | INCAP follows a source mode change only when the firmware rebuilds its capture chain, sometimes seconds later, with no event. Its words change one after another, so a mid-change read is inconsistent. | measured: 2026-10-12 G-EU doku/206, patch 0260 | with |
| W18 | Without that rebuild, new geometry lands in a ring that still has the old pitch: the picture tears, repeated three times side by side. | measured: 2026-09-07 HY310 doku/88 §0 | with |
| W19 | 3840×2160p24 is captured and scaled. 4K50/60 never locks in INCAP; 1600×900 does not lock (INCAP keeps the previous mode, enable off). | measured: 2026-11-01 HY320 doku/225; 2026-09-08 HY310 doku/96 §7 (journal S11) | with |
| W20 | Window/zoom requests never moved `0x874` or `0x924`. | measured: 2026-09-22 HY310 docs display.md | with |

### 4. Output enables and what stops the capture
| # | fact | source | FW |
|---|---|---|---|
| E1 | Bit 31 of `0x928` (luma) and `0x968` (chroma) = the capture writes. Cleared: `0x104` still counts, nothing is written, and the wall holds the last frame. So "counter runs" is not proof of capture. | measured: 2026-09-07 HY310 doku/84 §2.0, doku/96 | with |
| E2 | Good-capture criteria: bit 31 set, `0x104` counting, `0x320/0x324` moving, and a stimulus at the source changing the ring content (e.g. Y 118.5 → 61.5). | measured: 2026-09-07 HY310 doku/84 §4.4 | with |
| E3 | **Descriptor quirk.** Writing the scanout's descriptor-pointer words `0x05600098..0a4` cleared both enables at once (`0xe0020438` → `0x60020438`). It also moved `0x400` from `0x21` to `0x61` and `0x824` from `0x0000000b` to `0x8000000b`. | measured: 2026-09-07 HY310 doku/84, doku/86 §4 | with |
| E4 | After E3, a source switch away and back released the capture, 536–544 ms after the firmware's answer. Re-selecting the already active source did not (3 tries). A hot-plug cycle gave no release in 20 s. | measured: 2026-09-07 HY310 doku/84 §4.3–4.4 | with |
| E5 | Setting bit 31 of both enables from the ARM brought the capture back; the bits stayed set and the pointers moved. After some rebuilds the firmware cleared them again within 100 ms. Repeating the write until 3 reads over 150 ms held took 159–223 ms. | measured: 2026-09-07/08 HY310 patches 0121/0122, doku/96 §6 | with |
| E6 | Conflicting earlier observation: a hand-set bit 31 gave exactly one frame, then all three slots identical while `0x104` kept counting. | measured: 2026-09-06 HY310 doku/76 §13 | with |
| E7 | No signal: the firmware leaves bit 31 clear (HY310 `0x600200f0`; HY320 with hot-plug held low `0x60020438`). | measured: 2026-09-05 HY310 doku/71; 2026-11-03 HY320 spec/10 §6.2 | with |
| E8 | Input colour converter `0x824`: with `0x8000000b` and the capture writing, the RGB source landed unconverted (grey Cb ≈ Cr ≈ Y, e.g. 40/43/40). With `0x0000000b` it is YCbCr (40/129/127). Order capture off → converter fix → capture on gives a YCbCr first frame. | measured: 2026-09-08 HY310 doku/96 §7 (journal S11) | with |
| E9 | `0x400` = `0x21` while capturing; `0x61` only in the stopped state; never seen needed for capture. The file's capture init writes `0x40`, and the data-path reset writes bits [6:5] to 0, then 3. | measured: 2026-09-07 HY310 doku/84; vendor-data spec/40 §4.4 | both |
| E10 | Standby stop: clear bit 31 of both enables and wait 40 ms (two frames) in suspend, while the co-processor still runs. A sleep aborted before the park re-enables. | measured: 2026-10-09 HY310 doku/173 §2, patch 0240 | with |
| E11 | **The C1 hang.** Hang on the way into sleep (crust resets after 15 s). Breadcrumbs: 5 of 5 stopped between TVCAP PRE_OFF and TVCAP OFF, with the TVCAP domain status `0x00010000` ("on and idle") while INCAP was still writing. | measured: 2026-10-09 HY310 doku/173 §2 | with |
| E12 | C1 statistics: with E10, 0 of 50 (20 of 20 test module, 30 of 30 image); without it, 5 of 111 (p ≈ 0.15, a hint, not a proof). A TV-top off step before power-off made no difference. | measured: 2026-10-09 HY310 doku/173 | with |
| E13 | Bench hazard: NRC write channels on with an address word set to 0 hung the SoC; channels on without addresses DMA'd into system RAM. INCAP output channels presumably carry the same risk. [INFERENCE] | measured: 2026-11-03 HY320 doku/228 §6, §8 | without |

### 5. How a captured frame reaches channel 0
| # | fact | source | FW |
|---|---|---|---|
| P1 | Channel 0 reads the ring directly: `VCH_YADDR[0..3]` = Y slot, `VCH_CADDR[0..3]` = C slot (all four equal), `VCH_SRCSEL 0x122`, format code 0, `VCH_CSTRIDE` = 2 × pitch (`0xf00`), `VCH_CCROP` at half height (spec/10 T2). | measured: 2026-09-06/07 HY310 doku/86; 2026-11-03 HY320 | with |
| P2 | The per-frame slot rewrite plus `VCH_ADDR_LATCH` comes from the project's Linux display driver, 2.8–3.1 ms after each panel vsync stamp. `VCH_LATCH` is not pulsed per frame (reads 0). | measured: 2026-10-11 G-EU doku/198 §1, doku/200 §4; 2026-11-03 HY320 spec/10 §6.1 | with |
| P3 | Addresses written during a frame take effect from the next vsync. The slot being written is complete by then (about 8 ms reserve; worst case the fetch starts 120 lines behind the writer). | measured: 2026-10-11 G-EU doku/200 §4 | with |
| P4 | Slot choice used now: plane = index (slot in progress); consumer = index − 1. A slow source (source frames/vsyncs < 0.8 over 32 vsyncs) gives the plane index − 1. Result: 1080p60 → 59.70/60 shown, 0.30 skips/s; 1080p50 50.00; 1080p30 30.00; 720p60 59.75. | measured: 2026-10-11 G-EU doku/200 §4 | with |
| P5 | Older method: read `0x05600320/0x324` once per vsync (three reads against tearing). 287 vsync events, 60 of 60 frames, rebuilt frame = pixel-exact screenshot of the source. | measured: 2026-09-07 HY310 doku/86, doku/88 | with |
| P6 | `0x320/0x324` always name the same slot index pair and ignore writes. At 1:1 they name the slot being filled, a few hundred lines behind (flip at line 340 of 750 at 720p60). | measured: 2026-09-01 HY310 doku/64; 2026-10-11 G-EU doku/198 | with |
| P7 | When scaling down, `0x320/0x324` move at the panel rate (0.975 order), name a slot 1–3 frames old, hold every 4th–5th frame and skip the next: 43–57 of 60 shown, falling to 34/s over an hour; the pointer moves 41–47 times/s against 60 source frames. A mode change resets the loss. | measured: 2026-10-11 G-EU doku/197, 198, 200 | with |
| P8 | No firmware code and no file table writes `0x320/0x324`. | binary-derived (held) | — |
| P9 | `0x300/0x304/0x310` move by themselves and ignore writes. With HDMI, `0x310` cycles `0x00800210/0x00900210/0x00a00210/0x00b00210` (bit 21 clear only 7–10 % of the time); `0x300 = 0x00804258`, `0x304 = 0x00804000`. They also move with a DRAM frame and no signal, so they follow channel 0, not the capture. | measured: 2026-09-01 HY310 doku/62; 2026-11-03 HY320 spec/10 §6.2–6.3 | with |
| P10 | `0x05600328` reads 0 throughout. | measured: 2026-09-07 HY310 doku/84 §3.4 | with |
| P11 | No ARM-side capture-done interrupt is known; frames were picked on the scanout vsync SPI 110. | measured (P5); vendor-data (B13) | with |
| P12 | HY320 HDMI state: `VCH_GATE 0x1` (HY310 `0x11`), `VCH_ARMED` `0x6a`/`0x4c` changing, `0x0c4 = 1`, chroma gain `0x05140508 = 0x04400000` (HY310 `0x144c0000`). | measured: 2026-11-03 HY320 spec/10 §6.1, spec/12 | with |
| P13 | Hot-plug low (no signal): `VCH_CTRL 0x03000200`, slots 0. doku/228 attributes this to the firmware; the Linux driver's disable was not separated from it. [INFERENCE] | measured: 2026-11-03 HY320 doku/228 §5 | with |
| P14 | 1280×720 source on a 1080p panel: ring at source size (row bytes `0x50`). Channel 0: `VCH_SIZE 0x02cf04ff`, `VCH_BLOCKS 0x002c004f`, `0x500`/`0xa00` strides. Scaler `0x05180008 = 0x3200aaaa`, `0x0518003c = 0xaaaa`, `0x05180014` bit 27 = 0. Full panel. | measured: 2026-09-08 HY310 doku/96 §6 | with |
| P15 | 1080p panels (HY310, HY320): the ring equals the source (no capture scaling). The 720p G-EU: INCAP downscales into the ring (W13). The plane itself cannot downscale: the picture smears and stays smeared. | measured: 2026-09-22 HY310 docs display.md; 2026-10-12 G-EU | with |
| P16 | Pitfall: a source repeating frames (19–21 identical every 11.0 s) looked like a capture stall while the index never stood. Measure the ring content, not the pointer. | measured: 2026-10-11 G-EU doku/201 §5 | with |

### 6. Timing and frame lock
| # | fact | source | FW |
|---|---|---|---|
| T1 | Panel rates: G-EU 1360×760 at 61.71 MHz = 59.71 Hz; HY310 59.42 Hz; HY320 65.538 Hz (2200×1125, 162.21 MHz, the same with and without firmware); stock HY350 59.46 Hz. | measured: 2026-10-11 G-EU doku/197; 2026-10-12 HY310 doku/207; 2026-11-03 HY320 doku/228 R3–R4 | both |
| T2 | Source vs panel: source 60.00 (HY310 measured 60.02). Skip rates: G-EU 0.30/s; HY310 0.57/s in bypass; HY350 stock 0.6/s. | measured: doku/200, 207, 197 | with |
| T3 | At a 65.5 Hz panel a 60 Hz source must repeat about 5.5 frames/s. [INFERENCE; not measured on the HY320 with HDMI] | — | — |
| T4 | `PROC_LOCK 0x0514fe00` and `PNL_LOCK 0x051cfe00` have the same layout. `fe08` = (V total − 1) << 16 \| (H total − 1): boot value `0x08c9112f`, programmed `0x04640897` → video vsync every 15.267 ms. `PNL_LOCK` with the boot totals ticks at 16.5/s. | measured: 2026-11-03 HY320 spec/10 §6.2–6.3 | both |
| T5 | `fe64` = input vsync stamp: it moves only with an input signal and latches at source lines 4–32. `fe68` = panel vsync stamp (65.5/s on the HY320). | measured: 2026-10-11 G-EU doku/197; 2026-11-03 HY320 | with |
| T6 | `fe74` [31:16] = live V total; it shows the boot value `0x08c9` when the raster stalled. `fe50`, `fe8c`, `fe90` and `PNL_LOCK fe64/fe68/fe78/fe7c` differ between signal and no signal. | measured: 2026-11-03 HY320 doku/228 | with |
| T7 | Firmware no-signal values: `fe0c 0x0240042b`, `fe10 0x00898005`, `fe14 0x00010000`, `fe24 0x03e80000`, `fe2c 0x04190a0a`, `fe30 0x10000104`, `fe34 0x00a008e1`, `fe38 0x006008b2`, `fe40 0x05a00000`, `fe48 0x04530465`; `PNL_LOCK fe00/04/08 = 0x00110449/0x00a40824/0x08c9112f`. | measured: 2026-11-03 HY320 spec/12 | with |
| T8 | On the bench, writing `fe30 = 0x10000104` and `fe0c..fe50` had no effect. | measured: 2026-11-03 HY320 | without |
| T9 | `fe30` [30:28] = coupling mode: 0 fixed totals (file work mode 2), 1 V-total tracking (work mode 0), 2 H-total tracking (work mode 1). It is off on the G-EU and the stock HY350. | measured: 2026-10-11 G-EU doku/197, doku/199 | with |
| T10 | The firmware rewrites `fe08` every vsync. Coupled: V total dithers 755/756 (also 756/757); panel period = input period; the phase is random at lock (11 locks at lines 70..1098). Phase near line 815 gave 1.3 skips/s, near 8–250 gave 7–9.5. | measured: 2026-10-11 G-EU doku/199 | with |
| T11 | Coupling side effects: visible flicker (the dither); H-total mode made the picture darker and darker. A V total below 742 (720 + 20 + 2) stopped the panel timing generator until reboot. | measured: 2026-10-11 G-EU doku/199 §3, §6–7 | with |
| T12 | One 1080p60 input frame lasts 2 474 980 clocks of the 148.5 MHz input pixel clock (≈ 2200×1125) in a lock-block time stamp. Which stamp register: not stated. | measured: 2026-10-11 G-EU doku/199 §1 | with |
| T13 | The panel pixel clock comes from 24 MHz × N / 14, integer N only (61.71 or 63.43 MHz): no fine trim to 60.00 Hz. | measured: 2026-10-11 G-EU doku/199 §7, doku/200 §5 | both |
| T14 | Not the cause of the downscale loss: co-processor clock (`0x02001600 = 0x80000002`, 400 MHz), descriptor rate words, noise reduction / picture enhancers, bus and DRAM settings. | measured: 2026-10-11 G-EU doku/197 §3 | with |

### 7. Power, clock and standby
| # | fact | source | FW |
|---|---|---|---|
| S1 | `TVTOP` after a boot that ran the firmware: `0x00111111`, `0x01111117`, `0x00000504`. Boot-loader / bench state: `+8 = 0x404`. | measured: 2026-09-05/10-09 HY310 doku/71, doku/172; 2026-11-03 HY320 doku/228 | both |
| S2 | On the bench, `0x06e00008 = 0x504` written by hand reads back and changed nothing visible in the channel-0 registers. | measured: 2026-11-03 HY320 doku/228 | without |
| S3 | The file's capture init table also writes `0x06e00008`, `0x06940000`, `0x06940104 = 0`, `0x06940800` bit 0, `0x920..0x96c`, `0x06980028/2c/30`. The values were not in the sources read. | vendor-data (doku/84 §4.2) | static |
| S4 | After a standby (TVFE/TVCAP powered off and on by the kernel) `TVTOP` reads `0x10, 0, 0`. On the HY320 `+0x1c` also goes 1 → 0. | measured: 2026-10-09 HY310 doku/172; 2026-11-03 HY320 doku/227 §9 | with |
| S5 | The co-processor restarted without TVTOP restored stalled the whole SoC within 200 ms (3 of 3). | measured: 2026-10-09 HY310 doku/172 | with |
| S6 | The boot-loader step restores TVTOP: `+4 0x01111117`, `+8 0x404`, `+0 0x00111111`, then all 0, then again, 12 ms apart. The firmware was ready 290–300 ms after start, picture back after 3.9–5.2 s, 6 of 6. Where the sequence's values come from is not established. | measured: 2026-10-09 HY310 doku/172 | with |
| S7 | HY320: restarting the co-processor from the standby park still hangs (5 of 6, 13 of 15 lost), even with `+0x1c = 1`; sleeping without a restart worked 8 of 8. Cause open; not pursued. | measured: 2026-11-03 HY320 doku/227 §9 | with |
| S8 | With the TVFE/TVCAP domains off (bring-up node missing) the whole INCAP block read 0, the ring stayed empty and the wall was uniformly green. | measured: 2026-09-07 HY310 patch 0096 | with |
| S9 | Bus hangs: an INCAP `0x928` read in the noirq phase stopped the box. INCAP reads on resume before the co-processor restart hung the bus (G-EU 3 of 3, watchdog at 16.4 s). Every HDMI link read `0x0684xxxx` hung after self-refresh with the co-processor parked. | measured: 2026-10-09 HY310 doku/173; 2026-10-12 G-EU doku/203; 2026-10-12 HY310 doku/207; 2026-10-08 HY310 doku/176 | with |
| S10 | Sleep order: capture stop → scanout idle → park + display clocks gated → TVFE/TVCAP off. The gated clocks are the CCU words saved from `0x02001db0` (deint, panel, svp-dtl, afbd bit 31; bus-disp bit 0), not reset; a reset made the scanout resume hang the bus. A pipeline left running through self-refresh cost every DMA master its DRAM access ("fault B"). | measured: 2026-10-09 HY310 doku/171 | with |
| S11 | The audio-top word `0x0614a000` (TVFE domain) reads `0x700` after a boot and 0 after a standby. | measured: 2026-10-09 HY310 doku/173 §3 | with |

### 8. No-firmware observations
| # | fact | source | FW |
|---|---|---|---|
| N1 | Bench boot: the boot loader brings up the display with the co-processor held in reset. The IPC, receiver, loader, DSP and scanout drivers are blacklisted, and the command line has `clk_ignore_unused pd_ignore_unused`. `0x02001600 = 0` and `0x0200160c = 0`. | measured: 2026-11-03 HY320 doku/228 §1 (q1-run2.log cmdline) | without |
| N2 | INCAP readable with no hang: `0x000 = 1` and `0x004..0x9fc` all 0 (including `0x104`, `0x548`, `0x874`, the slot tables, `0x924/0x928/0x964/0x968`). `0x400 = 0`, and `0x60` after the data-path reset table. | measured: 2026-11-03 HY320 doku/228 (r2-bench1..8.log) | without |
| N3 | INCAP `0xa00..0xa30` is non-zero on the bench and differs between boots. Often `0x110`, `0x08000800`, …, `0xa10 = 0x006300ad`, `0xa14 = 0x000a0021`, `0xa1c = 0x04380000`, `0xa20 = 0x00400780`, `0xa24 = 0x00440044`, `0xa28 = 0x00080200`, `0xa2c = 0x898`, `0xa30 = 0x465`, equal to the firmware's no-signal values. Other boots: `0x330/0x07ec0808`, `0x484/0x086007c0`; one boot looks random. Meaning unknown. | measured: 2026-11-03 HY320 doku/228 logs | without |
| N4 | `TVTOP` = `0x00111111/0x01111117/0x404` (the boot loader sets it even when the firmware never runs). | measured: 2026-11-03 HY320 doku/228 §2 | without |
| N5 | `0x320/0x324` = 0 until channel 0 is latched; `0x300/0x304/0x310` stand still; `fe64` stands. After the NRC latch words, `0x320` read an address, so the pointer tracks channel 0, not only the capture. [INFERENCE] | measured: 2026-11-03 HY320 spec/10 §6.1–6.2 | without |
| N6 | A DRAM frame does not need the capture side: with the firmware running, no-signal vs no-signal-plus-client states differ only in channel-0 words. Signal vs no signal changes only INCAP status and output-channel words. | measured: 2026-11-03 HY320 spec/10 §6.2 | with |
| N7 | Without the firmware, the scanout vsync (SPI 110) comes only with the video raster running and channel 0 on. No capture-related interrupt was seen. | measured: 2026-11-03 HY320 doku/228 §7 | without |
| N8 | Never tried: programming INCAP, setting its enables, or capturing any frame without the firmware. | — | — |

### 9. Unknowns and conflicts (for doc 59)
- **INCAP programming.** No register semantics exist for programming INCAP without the firmware. Its input from the receiver, the clock words it needs, and whether `TVTOP +8` bit 8 (`0x504`) or `0x06940000 = 0x3a7b` (vs bench 1) matter are all unknown.
- **INCAP interrupt.** Whether INCAP has any interrupt line to the ARM GIC is unknown. None is known; the stock DTS shows none.
- **Flip pointers.** Who advances `0x320/0x324` (hardware), and what they show with a running capture and no firmware, is unknown.
- **`0xa0c` upper bits.** The meaning of the bits above [2:0] after a standby, and of `0xa08`/`0xa24`, is unknown.
- **`0x824` polarity.** doku/84 §2.2 leaves it open, but journal S11 / doku/96 §7 measured bit 31 = 1 → RGB passes unconverted. Treat the S11 row as the measured one.
- **Hand-set enables.** doku/76 §13 (one frame, then stuck) conflicts with patches 0121/0122/0240 (works and sticks). The preconditions differ and are not separated.
- **Memory-plan layout.** The entry layout of the file's memory plan is open (spec/40 Q-TSE-4), so slot addresses cannot yet be derived from the data file alone.
- **Address encoding.** spec/20 says the NRC words `0x05000400..` hold addresses ">> 8"; the values (`0x04c3ef00` for `0x4c3ef000`) give >> 4. Fix spec/20.
- **`0x050c0000`.** It is the deinterlacer in spec/00/40, but the project's TV-capture bring-up node uses reg `0x050c0000` and doku/71 labels it "HDMI-RX". The conflict is unresolved.
- **HY320 at 60 Hz in.** Shown/repeated frames at the 65.5 Hz panel with a 60 Hz HDMI source were never measured. Whether the lock blocks can bring the HY320 panel to 60 Hz is unknown; `fe30 = 0x10000104` there, meaning unclear.
- **Mechanisms behind the hangs.** C1 (DMA running under the domain power-off) is inferred from breadcrumbs, not proven. Why INCAP reads hang after a park / clock gate but read 0 with the domains off is unknown.
- **No-signal writer.** Who writes channel 0 to `0x03000200` at no signal (firmware or the Linux driver) was not separated.
- **HY320 restart hang.** The cause of the co-processor restart hang after a standby on the HY320 is open. A firmware-free driver never restarts the co-processor, so it never meets this.
- **Descriptor quirk.** It needs the firmware: a firmware-free driver has no descriptor protocol. [INFERENCE]

### Files
- `doku/84-re-capture-ring.md` — INCAP words, enable mechanics, descriptor stop and release.
- `doku/86-video-plane-nv16.md` §1–4, `doku/88-v4l2-hdmirx.md` §0/§4 — slots, NV16 on channel 0, flip-pointer reading.
- `doku/96-anzeigekette.md` §2/§6/§7 — INCAP active/total/row-byte/enable at 1080p and 720p, upscale state, green-tint (`0x824`).
- `doku/71-tvtop-noetig.md` — power domains, display top, INCAP live values, the `0x068b0000` block rule.
- `doku/171`, `172`, `173`, `176` — standby, TVTOP loss and restore, C1.
- `doku/197`–`200`, `206`, `207`, `201` §5, `203` — rates, ring rotation, write index, capture scaler, lock blocks, resume hangs.
- `doku/225`, `227` §9, `228` §2/§5–6 — HY320.
- `analyse/cleanroom-bench-20261103/{diff-sig-nosig-client.txt, logs/r2-normal.log, logs/r2-bench*.log}` — whole-block INCAP dumps.
- Patches `0096`, `0107`, `0121`, `0122`, `0240`, `0255`, `0258`, `0260`, `0314`.
- `spec/10` §2/§5/§6, `spec/12` lock blocks, `spec/20` §5.1, `cleanroom-held/90` Q2/Q6.
