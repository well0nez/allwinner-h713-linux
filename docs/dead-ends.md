# Dead ends

Explanations that were tried and ruled out on real hardware, so nobody spends another session on them.
Most of these come from one investigation: why the picture was dark (the last section is the standby). That question is **solved** - the
cause was a bad panel clock, not any of the things below - found by comparing registers against a running
stock system rather than by reasoning about the driver (`doku/90-stock-referenz.md`). Each entry here was a
plausible cause that the measurement ruled out.

## The actual cause, for contrast

The PLL ran at N+1 = 43 instead of 41 and without spread spectrum, the mixer totals were 2200×1125 instead
of 2128×1120 minus one, and the porches were derived wrong. The panel received a timing grid it could not
drive cleanly and passed correspondingly little light. None of this was visible from source code review; it
took a register-by-register diff against a working stock boot to find. A related, later symptom - a bar
down the right edge of the picture - turned out to be the same class of bug: `h713_disp_clear_layer_xoff()`
forced the layer's X-origin register to zero (board B's value) on every DE replay, overwriting the 55 this
board actually needs.

## PWM channels

**PWM2 on PB4, the "stock dimmer", is not the brightness control**, despite being the strongest-looking
candidate: pin and mux match the vendor devicetree, and it is the channel a stock backlight driver would
use. Measured twice, once with the panel correctly powered - the counter runs, the enable bit is set,
`PERIOD` steps cleanly through all six duty levels from 100 % to 0 %, and the picture's brightness does not
move at all. cstenger measured the identical result on his own board: the counter runs, the duty steps, and the
brightness does not change.

**PH17 and PH18, the other two PWM-capable pins in the vendor tree, are not spare lighting controls
either.** PH17 is the fan tachometer input - driving it as an output would fight the tachometer signal it
already carries. PH18 appears only in the bootloader devicetree, in no kernel tree and no note; taken
together with the tachometer next to it, a fan-drive line is the more likely reading than a light control.

## Firmware protocol candidates

**The two `cpu_comm` backlight calls (`BacklightLevel`, `BacklightWorkMode`) are not the missing step.**
They looked promising - a real handoff to the display firmware with real routine IDs - but the stock boot
logo is already bright *before* either call is ever sent. The firmware's own default is bright; it does not
wait to be told a level.

**The DLPC3435 light engine does not answer on I²C.** This was the strongest candidate - reverse-engineered
vendor code says outright that U-Boot initializes it, with a reconstructed register sequence - but scanning
the bus it should be on (PH2/PH3) gets an ACK from the accelerometer at `0x18` and nothing from `0x1b`. The
bus itself works; the chip does not respond on it. cstenger measured the same silence. This is not fully
closed: only PH2/PH3 was scanned, and which I²C controller the DLPC3435 node actually hangs off in the
kernel devicetree was not checked - if it is a different bus, the test does not rule anything out.

## Standby and the picture after it

Measured on the HY310 on 07. - 09.10.2026 ([standby](subsystems/standby.md)), and not the cause:

- **CPU hot plug** for the stall after the first wakes: CPU_OFF/CPU_ON through TF-A ran clean; the cause lay in the display path (MIPS, afbd) running through the sleep (`doku/164`, `doku/165`).
- **Feeding the SoC watchdog by switching MODE off and on**: the count does not restart; a write of 0x14af to CTRL does (`doku/164`, `doku/170`).
- **Clearing crust's EINT status right after it switches PL4 back**, against the phantom power key after a wake: the flag arrives after later samples of the debounce clock, so crust waits first (`doku/167`).
- **Fault B** (about every second wake the DMA masters get no DRAM): not the HDMI source, `THal_Vp_Deinit`, stopping `h713-tv` and the warp, the PB5 rail, the DRAM contents, the CPU count, nor the state of U-Boot, BL31, crust and kernel. A stopped INCAP capture does not cure it (it cures C1, below). A display-bus reset over the sleep hangs afbd's resume, because it loses what the parked MIPS set up; gating the five display clocks works (`doku/171`).
- **DRAM controller COM+0x004** for the hang when the MIPS restarts after a standby (bits 21:16 read 0x10 after the sleep, 0x20 before): putting 0x20 back hung the same; the TV-top words the sleep resets were it (`doku/172`).
- **A TV-top power-off step** does not prevent the hang going to sleep (C1), and stopping the capture in the noirq window is impossible - even a read of INCAP stopped the box. It stops before the freeze: no C1 in 50 sleeps against 5 in 111, a hint, not a proof (`doku/173`).

## A measurement tool that does not apply here

`h713_disp scanrate` reports nonsensical numbers on this panel - its own output admits a 10-bit counter
ceiling of 1023, and this panel's timing (HT 2200, VT 1125) does not fit in that range. The apparent 79 MHz
result is aliasing, not a real clock, and chasing it nearly led to reprogramming the PLL to the wrong value.
The clock was correct the whole time; the tool just cannot measure this timing.

## A non-result

Leaving the MIPS firmware running instead of parking it before probing (`h713_disp init 0x30` without
`quiesce`) leaves the screen black - but that is not evidence of anything, because that init path never
publishes a source or an OSD layer to begin with. Black is the correct output there, and the test cannot
distinguish a working state from a broken one.

Details: `doku/70-sackgassen.md`, `doku/90-stock-referenz.md`, `doku/80-vergleich-baeume.md`.
