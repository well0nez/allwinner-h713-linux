# h713-fel - into FEL without touching the device

FEL is the BootROM's USB recovery mode: with the device in FEL, your PC can load and run code on it
without anything on the eMMC being involved. The usual way in is the reset button - hold it, apply power.
`h713-fel` is the other way: it asks the *running* Linux to come back up in FEL, so you can recover a
device that sits somewhere you cannot reach.

```bash
h713-fel            # asks first
h713-fel --yes      # no question
```

About ten seconds later the device appears on the PC as `1f3a:efe8`, with no network, no console and no
Linux. From there, `sunxi-fel` or the installer takes over.

## How it works

It writes the vendor's own "efex" flag into RTC general-purpose register 2 (`0x07090108`) and reboots.
Our SPL reads that flag first thing on the next start, clears it, and jumps into the BootROM's FEL entry
point instead of continuing to boot. Identical to `run fel` at the U-Boot prompt, and to what the vendor
firmware does for its own recovery mode.

Two details that come from the hardware and are worth knowing:

- The RTC registers sit on a slow clock. A single write can be lost - measured once in four attempts -
  so the tool writes in a loop until the value reads back, then waits a second before resetting.
- The flag does **not** survive a power cycle. If you end up in FEL by accident, unplug the device and
  plug it back in: it boots normally again.

## Getting back out

Either give the device something to run -

```bash
sunxi-fel uboot mainline/build/out/u-boot-installer.bin   # from your PC
```

- or cut the power and start again. There is nothing to repair: the flag is one word in the RTC, and the
BootROM cannot be overwritten from software.

## When you need it

Mostly when a change to the boot chain leaves a device that no longer reaches Linux - except then you
cannot run this tool any more, which is exactly why it is worth knowing the button as well
([FLASHING.md](../../FLASHING.md)). Its real use is the reverse case: the device works, it is mounted on
a ceiling, and you want to install a new image without a ladder and a screwdriver.

Details: `doku/nachtlog/S48-fel-aus-uboot.md`, `doku/20-flashen-und-recovery.md`.
