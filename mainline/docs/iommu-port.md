# Porting the H713 IOMMU

The H713 has a working IOMMU that mainline does not drive. Nothing translates
DMA on this board today, which is why a decoder bug that every other Allwinner
SoC contains harmlessly (cedrus keeps writing after its buffers are freed —
`docs/vaapi-scope.md`) instead corrupts arbitrary kernel memory here. This
records what has been verified about the block, so the port starts from measured
facts rather than from the H6 driver's assumptions.

## Verified against board B's own eMMC, 2026-08-17

Everything below is read out of `local/h713-lab/captures/board-b/`, the
pre-modification capture of *this* unit, not from the retail OTA. The kernel DTB
lives at offset `0x00d1b400` in the capture (second copy at `0x0111f400`; the
boot package is stored twice) and is **byte-identical** to the retail image's
`sunxi.fex` — that file is simply the same 69380-byte blob zero-padded to 73728.
So the retail firmware and this board agree, and either can be used as reference.

```
mmu_aw: iommu@2010000 {
        compatible = "allwinner,sunxi-iommu";
        reg = <0x0 0x2010000 0x0 0x1000>;
        interrupts = <0 0x47 4>;        /* SPI 71 */
        interrupt-names = "iommu-irq";
        clocks = <&ccu 0x30>;           /* index 48 */
        clock-names = "iommu";
        #iommu-cells = <2>;
};
```

### The masters, as wired on this board

| device | node | `iommus` | notes |
| --- | --- | --- | --- |
| `ve` | `ve@1c0e000` | `<&mmu_aw 0 1>` | **our cedrus** |
| `ve1` | `ve1@1c0e000` | `<&mmu_aw 1 1>` | second VE view |
| `ge2d` | `ge2d@5240000` | `<&mmu_aw 2 0>` | |
| `dec` | `dec@5600000` | `<&mmu_aw 2 0>` | **our AFBD display** |
| `tvdisp` | `tvdisp@5000000` | `<&mmu_aw 3 1>` | |
| `tvcap` | `tvcap@6800000` | `<&mmu_aw 4 1>` | |
| `av1` | `av1@1c0d000` | `<&mmu_aw 5 1>` | AV1 decoder |
| `audbrg`, `demux`, `dtmb` | | `<&mmu_aw 6 1>` | |

### The second cell means "translate this master" — read from the vendor driver

`sunxi_iommu_of_xlate` allocates a 20-byte per-device struct, stores `args[0]`
as a word (the master ID) and **booleanises `args[1]`** into a byte at +0x04
(`adds r3, r3, #0; movne r3, #1; strb`). `sunxi_iommu_add_device` then reads
that byte and passes it as the second argument to the exported
`sunxi_enable_device_iommu(master, enable)`, which indexes a per-master bitmask
table and:

- `enable != 0` → `bic` — **clears** the master's bits
- `enable == 0` → `orr` — **sets** them

…before writing register `#48` = `0x30` = `IOMMU_BYPASS_REG`. So **cell 1 = 1
means translate; 0 means leave bypassing**, and that matches the `0x7F` (all
seven masters bypassing) read out of the hardware at rest.

**Correction to an earlier claim in this project's notes:** it is *not* true
that both engines are translated in the vendor stack. `dec@5600000` and `ge2d`
are both `<&mmu_aw 2 0>` — **bypass**. The vendor translates the video engine
and leaves the display untranslated. That does not weaken the case for the port
(the VE is the engine that corrupts memory here), but the display must not be
switched into translation just because it appears in the master list.

## The block is register-compatible with mainline's H6 driver

From the vendor `vmlinux` — extracted from `update.img` member `vmlinux.fex` at
offset 2877440, length 105860275, bzip2 → tar → a 220 MB ARM 32-bit 5.4.99
image **with full symbols**. Disassembling `sunxi_iommu_irq` shows it reading
`[base+0x108]`, `[base+0x180]` and `[base+0x184]`, which are mainline's
`IOMMU_INT_STA_REG`, `IOMMU_L1PG_INT_REG` and `IOMMU_L2PG_INT_REG` exactly.
Across the whole driver the offsets touched are:

| offset | mainline `sun50i-iommu.c` name | |
| --- | --- | --- |
| 0x010 | `IOMMU_RESET_REG` | ✓ |
| 0x020 | `IOMMU_ENABLE_REG` | ✓ |
| 0x030 | `IOMMU_BYPASS_REG` | ✓ |
| 0x040 | `IOMMU_AUTO_GATING_REG` | ✓ |
| 0x060 / 0x070 / 0x080 | TLB enable / prefetch / flush | ✓ |
| 0x098 / 0x0a8 | `TLB_IVLD_ENABLE` / `PC_IVLD_ENABLE` | ✓ |
| 0x108 | `IOMMU_INT_STA_REG` | ✓ |
| 0x180 / 0x184 | `L1PG_INT` / `L2PG_INT` | ✓ |
| 0x160–0x174, 0x1c0, 0x1dc, 0x1f0 | — | **not in the H6 map** |

So this is the same IP with extensions, not a different block. The port is
therefore an extension of `drivers/iommu/sun50i-iommu.c` rather than a new
driver. The 0x160–0x174 run is most likely the per-master `INT_ERR_DATA`
window widened for seven masters (H6 has fewer); 0x1c0/0x1dc/0x1f0 are
unidentified and should be treated as must-preserve until they are.

## The block answers on hardware — measured 2026-08-17

Done in the order patch 0024 demanded, because probing an ungated block hangs
this interconnect.

**1. The gate, read first.** Our CCU driver already carries it:
`bus_iommu_clk` at CCU offset `0x7bc` bit 0 (`CLK_BUS_IOMMU` = 42), so the
register is `0x020017bc`. It read **`0x00000000`** — the IOMMU is clocked
*off*. That is the confirmation that reading `0x2010000` blind would have been
the dangerous thing, not a theoretical worry. There is no reset line, matching
the vendor DT, which declares only a clock.

**2. With the gate on, the block responds.** A write/read-back on
`IOMMU_TTB_REG`: wrote `0xdeadb000`, read back **`0xDEAD8000`**. It answers,
and it masks bits [13:12] — the table base must be **16 KiB aligned**, which is
exactly mainline's H6 behaviour (its directory table is 4096 × 4 bytes = 16 KiB).
Restored to 0 afterwards, and the gate put back to 0; the board was left as
found.

**3. The register block, read out:**

| offset | value | reading |
| --- | --- | --- |
| +0x000 | `0x00000014` | non-zero, and **not in the H6 map** — ID/version |
| +0x010 `RESET` | `0x8003007F` | low byte `0x7F` = **7 masters, 0–6** |
| +0x030 `BYPASS` | `0x0000007F` | **all 7 masters bypass translation today** |
| +0x040 `AUTO_GATING` | `0x00000001` | already 1, which is what mainline writes |
| +0x060 `TLB_ENABLE` | `0x0003007F` | same 7-master pattern |
| +0x080, +0x100, +0x108, +0x180, +0x184 | `0` | idle, no pending faults |
| +0x1c0, +0x1dc, +0x1f0 | `0` | the extension offsets are idle at rest |

Three things fall out of that. The **master count is 7 and the hardware agrees
with the device tree** — `0x7F` is masters 0–6, exactly the set the vendor DTB
wires up. `BYPASS = 0x7F` states plainly why DMA is untranslated right now:
every master is in bypass, so enabling translation is a matter of programming
this block rather than of missing silicon. And the `0x8003007F` / `0x0003007F`
pattern shows bits 16–17 carry something beyond the per-master field, which the
H6 driver does not know about and which must be preserved rather than
overwritten.

## Tested on hardware 2026-08-17 — it works, with one caveat

```
platform 1c0e000.video-codec: Adding to iommu group 0
```

`/sys/class/iommu/2010000.iommu` exists, group 0 holds the video codec,
`ENABLE` reads 1 with a real `TTB` (`0x42048000`), and **`BYPASS` reads
`0x0000007C`** — masters 0 and 1 translated, the rest bypassing, exactly as
intended. **The full M1/VA1 ladder is 5 of 5 bit-exact through translation**, so
the page tables are right and nothing about decode regressed.

Two failures on the way there, both worth keeping because both looked like
something else:

**The reset line.** Mainline requires one; the H713's node has none, so probe
died with `Couldn't get our reset line` / `-2` and cedrus quietly fell back to
dma-direct (`deferred probe timeout, ignoring dependency`). Fixed by making the
reset optional — `reset_control_assert/deassert` are no-ops on a NULL control.

**One master port is not enough, and it fails silently.** Attaching only
`<&iommu 0 1>` produced an IOMMU that probed, enabled, installed a page table
and reported **no faults at all**, while every vector came out corrupt.
`BYPASS` read `0x7E`: port 0 translated, port 1 still emitting physical
addresses. The stock tree says why — `ve@1c0e000` and `ve1@1c0e000` are the
same block declared twice, as masters 0 and 1, because the engine issues
traffic through two ports. Half the traffic followed the IOVAs the DMA layer
handed out and half went straight to memory, and nothing ever touched an
unmapped IOVA, so there was nothing to fault on. `iommus = <&iommu 0 1>,
<&iommu 1 1>` fixes it and `BYPASS` becomes `0x7C`.

### Does it contain the cedrus bug? Partly, and not yet explained

With `sunxi_cedrus.stop_reset=0` — patch 0040's fix deliberately disabled, so
the use-after-free is live again — the workload that killed this board five
times (113 s to 848 s, always kernel corruption) ran **~6,500 frames and left
the kernel intact**. That is the result the port was for.

But it is not a clean win, and the honest reading is:

- **mpv died with SIGSEGV** after roughly four minutes. Userspace, not kernel.
- **No IOMMU fault was logged.** A write to an unmapped IOVA should fault, and
  the domain is in strict invalidation mode, so the absence needs explaining.

The most likely story is that the stray writes now land inside IOVA space that
is still mapped — hitting another live buffer rather than a hole — so they
corrupt userspace-visible data instead of kernel structures, with nothing to
fault on. That would be containment in the sense that matters (the kernel is no
longer at risk) without being detection.

**Confirmed by re-running with the fix on.** The segfault is not a second bug;
it is the same use-after-free with somewhere else to land. Same kernel, same
workload, one runtime toggle:

| | cedrus fix off (`stop_reset=0`) | cedrus fix on (`stop_reset=1`) |
| --- | --- | --- |
| **no IOMMU** | kernel corrupted — six different structures, 113–848 s | clean, 450 s / 13,338 frames |
| **IOMMU on** | **mpv SIGSEGV** after ~6,500 frames, kernel intact | **clean, 450 s / ~13,400 frames** |

So there is nothing extra to fix: patch 0040 removes the segfault, and it is
already the default. The IOMMU's contribution is that the *same* bug, left
unfixed, can no longer reach kernel memory — it degrades from a panic to a
crashed player. Both arms of the bottom row are one run each; a longer soak is
still owed before calling either closed.

## The port — written, compiles, tested

Three pieces, all in the series:

- **`patches/kernel/0041`** extends `drivers/iommu/sun50i-iommu.c`: a variant
  struct carrying master count and DT cell count, runtime per-master masks
  instead of the fixed six-master constants, `of_xlate` honouring the second
  cell, and a `bypass` shadow that starts all-bypass on two-cell variants so a
  master is only translated once its DT asks. H6/H616 behaviour is unchanged.
- **`patches/kernel/0042`** moves the DT node to `0x2010000` with the new
  compatible, SPI 71, two cells and no `resets`, and gives the VE
  `iommus = <&iommu 0 1>` — master 0, translation on, matching stock. The
  display and ge2d are deliberately left alone.
- **`patches/kernel/board/iommu.config`** turns the driver on for a debug
  kernel (`KERNEL_CONFIG=iommu`), leaving the shipping defconfig untouched.

Verified in the built artifacts rather than the source: `CONFIG_SUN50I_IOMMU=y`,
`drivers/iommu/sun50i-iommu.o` compiled, and the DTB contains `iommu@2010000`
with `#iommu-cells = <0x02>` and the VE's `iommus = <phandle 0 1>`.

**Tested on hardware — see above.**

## Still open

1. **`DM_AUT_CTRL` layout for seven masters.** H6's driver computes
   `0x0b0 + (d/2)*4`, indexed by *domain* rather than master, so seven masters
   should not change it — but that reasoning is untested.
2. **Bits 16–17** in `RESET` (`0x8003007f`) and `TLB_ENABLE` (`0x0003007f`), and
   the meaning of `+0x000` (`0x14`), `+0x1c0`, `+0x1dc`, `+0x1f0`. The driver
   never writes `TLB_ENABLE`, so those survive; anything that starts writing
   them must read-modify-write rather than assume zero.
3. **Whether translating the VE alone is coherent** when the display shares CMA
   with it. The vendor's answer is yes — it translates the VE and bypasses the
   display — but the vendor is not running our KMS driver.

## Why this is worth doing

Beyond correctness: with the IOMMU on, a stray write from the VE becomes an
IOMMU fault naming the offending master, printed once, instead of six different
kernel structures corrupted across five reproductions and a session spent
bisecting. It converts this entire class of bug from archaeology into a log
line.
