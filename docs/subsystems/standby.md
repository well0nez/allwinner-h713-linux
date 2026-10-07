# Standby

The HY310 knows two ways to be "off", and a third state that only looks like one. This page says which
is which, what the standby through crust does, what wakes it, what a failed wake looks like and how to
get out of it. Status: the standby has run on the HY310 in test images (`doku/165` - `doku/167`); a
release image does **not** offer it until the picture comes back after a wake (TODO 3.3).

| State | What runs | Power | How you get there | How you leave |
|---|---|---|---|---|
| **off (the gate)** | the SoC in U-Boot's [power-on gate](../uboot/power-gate.md); fan, lamp, panel unpowered (PB5, PL3 low); LED red | about 4 W, measured 09.09.2026 before crust; with crust running in the gate not measured | `poweroff`, the power key on an image without standby, a cold start | the power key |
| **standby** | crust on the ARISC, everything else asleep: the ARM cluster off, the DRAM in self-refresh | not measured | a short press of the power key on an image with standby (`h713-power`), `systemctl suspend` | the power key, the remote's IR code, a wake timer |
| `h713-tv` idle | everything; the HDMI input has no signal | full | no source | a source |

The last row is not a power state at all; `h713-tv` calls it STANDBY in its own log. "Standby" on this
page always means suspend to RAM.

## How a standby runs

crust is our own firmware for the ARISC ([arisc.md](arisc.md), [crust-h713/](../../crust-h713/README.md)).
BL31 starts it at every boot from the FIT, and on the HY310 Linux keeps that running image instead of
loading the vendor's. A standby is then:

1. `systemctl suspend`: systemd freezes userspace; `/etc/systemd/sleep.conf.d/10-h713.conf` allows only
   `mem` with `MemorySleepMode=deep`, never s2idle (which would power the display domains down under the
   running display MIPS). By hand, `echo freeze > /sys/power/state` still asks for s2idle: the display
   driver refuses it while the MIPS runs, and an s2idle sleep has no watchdog at all - the kernel stops the
   SoC watchdog for every suspend, and crust takes no part in this one.
2. The arisc driver checks that crust is alive and of contract version 5, arms the wake sources and asks
   crust to take the standby; Linux suspends its devices.
3. PSCI `SYSTEM_SUSPEND` in BL31 sends crust the "cpu op" request. crust turns the ARM cluster off, puts
   the DRAM into self-refresh and stops its clock, and waits for a wake source.
4. On a wake crust brings the DRAM back, releases CPU0 into BL31, and BL31 puts the system counter
   forward by the time crust counted asleep. Linux resumes; the driver confirms the cycle to crust.

Measured on the HY310 on 07.10.2026, in FEL test images with the arisc driver loaded by hand: the full
cycle with DRAM self-refresh and a 5 s wake timer in three runs, each in its own boot; all four cores back
online and Linux running on for the minute and a half each run watched (`doku/166`, `doku/167`). Not measured: the release image, a wake by the
key or by IR, a sleep longer than 5 s, the power draw, many cycles in one boot.

## What wakes it

| Source | Status |
|---|---|
| power key (PL4) | built in crust; not measured as a wake source |
| IR remote | crust compares against the 19 codes of the vendor device trees and the board's own (`CONFIG_CIR_WAKE_CODE`); whether the shipped remote sends one of them over IR while its Bluetooth link is down is not measured |
| wake timer | measured (`rtcwake`-style, 5 s; `doku/165` - `doku/167`) |
| RTC alarm | the kernel side computes it; whether a release should wake on it is the owner's decision |
| CEC | not supported |
| Bluetooth remote | not a wake source: Bluetooth is down in standby |

After a wake by the power key Linux sees a `KEY_POWER` - the press that woke it. On an image with standby
[h713-power](../tools/h713-power.md) ignores it; without h713-power logind would power off.

## When something goes wrong

A standby that does not come back looks like this: **dark, red LED, no network, the key does nothing.**
The LED follows PB5, so it is red whether the board sleeps, hangs or sits in the gate; it says nothing
about which.

What happens then depends on the watchdogs. Under Linux `systemd` can feed the SoC watchdog
(`RuntimeWatchdogSec`, not set in the image yet; TODO 2.25). For a standby the kernel feeds it itself
until its devices are suspended and then stops it; from there crust's net on the second watchdog would
watch the sleep (`H713_SLEEP_NET`), which a release does not carry until that watchdog's register layout
is measured - until then nothing watches the sleep itself. A watchdog reset finds the gate's RTC word on
"running" and boots straight through, lamp on, unless the owner decides it should go to the dark gate.
None of this has been measured in a standby yet.

By hand, as always: pull the USB cable if one is plugged in (the board keeps running from it), switch off
at the socket for 15 s, switch on, press the key.

**What to collect.** The journal lives in RAM (`Storage=volatile`), so the lines before a failed wake are
gone after the reset unless `h713-logs persistent` was set beforehand. After the next boot the arisc
driver prints one warning with crust's last phase, step, cause and error bits when the previous boot
ended in a standby - if the record survived; whether SRAM A2 survives a warm reset is not measured.

```
cat /sys/bus/platform/drivers/sun50i-h713-arisc/*/state      # ready, phase, wake, slept_ms, err, ...
cat /sys/bus/platform/drivers/sun50i-h713-arisc/*/wake_reason
grep . /sys/power/suspend_stats/*                             # success / fail per boot
h713-power status                                             # what the key would do now, and why
```

## The HDMI input in standby

crust leaves the hot-plug pin and the EDID it serves as they were when the box went to sleep (read from
the code): a connected source sees a live sink and may keep sending. Whether the pin should drop in
standby is the owner's decision. On a related note, the physical address crust writes into the HDMI
vendor block differs from the vendor firmware's on port 0 (1.0.0.0 against 0.0.0.0, measured 07.10.2026,
`doku/163`); it matters only to CEC and to AV receivers in a chain, and it is open in TODO.

## Building it

`release/build-all.sh --standby` offers the standby, and only for a verified board whose `board.env`
names a `CRUST_DEFCONFIG`: BL31 with `SYSTEM_SUSPEND`, the sleep file above, h713-power on the key.
Without `--standby` BL31 has no `SYSTEM_SUSPEND`, the sleep file says `AllowSuspend=no`, and the key
powers off as it always did; crust still runs the HDMI front end. `release/check-crust.py` (step 10)
refuses an image whose parts disagree about it ([build-container.md](../build-container.md) for the
compiler).

The variant is DRAM self-refresh. Deeper sleep (PLLs off, root clocks on the 24 MHz oscillator) is ported
and built but has never run, and the release refuses it. A design limit stays even then: crust polls at
24 MHz on the oscillator, so the oscillator never stops; whether that matters is a question for the first
power measurement.

Details: `doku/162` - `doku/168`, [arisc.md](arisc.md), [h713-power](../tools/h713-power.md),
[the power-on gate](../uboot/power-gate.md).
