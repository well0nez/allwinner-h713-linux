# Standby

The HY310 knows two ways to be "off", and a third state that only looks like one. This page says which
is which, what the standby through crust does, what wakes it, what a failed wake looks like and how to
get out of it. Status: the standby has run on the HY310 in test images (`doku/165` - `doku/167`), and since
09.10.2026 the picture comes back after a wake in the R2 test image (`doku/171`, `doku/172`); on 10.10.2026 the
same ran on the HY300PRO-G-EU (board HY200 QZ713DF A1, test image `geucrust2`, `doku/184`: woken by the RTC, the
power key and the remote's IR key, picture and sound back after each). A release image does **not** offer it
yet (TODO 3.3: the hang going to sleep, C1, is open).

**Lamp and fan go off in standby on both boards.** The board manager switches the fan rail off late in suspend
and on again at resume, but only when the board's device tree hands it the rail (`0211`). PB5 carries the lamp's
enable and the fan together, on the HY310 and on the HY300PRO-G-EU alike (the G-EU's stock tree names it as
`panel_bl_en` and as the fan's `fan-power-gpio`). Until kernel `0249` the G-EU tree kept PB5 as a gpio-hog, the
board manager said `fan power rail not ours, left as it is`, and the fan kept turning in standby; since
`0249` it says `fan power rail off` and `on` (10.10.2026, `doku/185`).

| State | What runs | Power | How you get there | How you leave |
|---|---|---|---|---|
| **off (the gate)** | the SoC in U-Boot's [power-on gate](../uboot/power-gate.md); fan, lamp, panel unpowered (PB5, PL3 low); LED red | 2.9 W (09.10.2026, `doku/181`; 4 W on 09.09.2026, before crust) | `poweroff`, the power key on an image without standby, a cold start | the power key |
| **standby** | crust on the ARISC, everything else asleep: the ARM cluster off, the DRAM in self-refresh | **2.4 W**, less than off (09.10.2026, `doku/181`) | a short press of the power key on an image with standby (`h713-power`), `systemctl suspend` | the power key, the remote's IR code, a wake timer |
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

## The picture after a wake

The display MIPS does not survive a standby as it is: before the sleep cpu_comm parks it (`suspend_late`,
through the driver `sun50i-h713-mips`), and two things go with the park.

- **The display clocks.** The pipeline the MIPS set up (deinterlacer, panel, video processing, scanout) keeps
  running without it. Left running through the DRAM self-refresh it cost the DMA masters their way to the DRAM
  after about every second wake (camera -110, Wi-Fi "cmd timed-out", a hung resume; `doku/171`). cpu_comm gates
  its five clocks right after the park and puts the saved words back in `resume_early`; no reset, which would
  lose what the parked MIPS set up.
- **The TV top.** genpd powers the TVFE and TVCAP domains off for the sleep and on again, and the TV top's clock
  and reset words at `0x06e00000` come back at their defaults. U-Boot sets them before it starts the MIPS; a
  MIPS started without them stalls the whole SoC within 200 ms (`doku/172`).

After the resume the wall shows the last picture until [h713-power](../tools/h713-power.md) starts
`h713-mips-restart`: the driver repeats U-Boot's TV top step where the standby lost it, loads `display.bin`
and starts the MIPS as U-Boot does; the HDMI receiver is bound again and `h713-tv` and `h713-warp` start.
Measured on 09.10.2026 in the R2 test images: six standbys in one boot, each with the picture back 3.9-5.2 s
after the wake (`doku/172`), and 30 of 30 in a fast loop on r2test3 (`doku/173`).

- **The capture stops before the sleep.** hdmirx clears the two output enables of INCAP in its suspend, while the
  MIPS still runs, and waits two frames; from the park on INCAP no longer answers the CPU. Without it genpd
  powered TVCAP off under the running write DMA, and that is where the hang going to sleep (C1, below) stood.
- **The audio comes back after the picture.** The audio DSP sits in TVFE and loses its power in the sleep;
  msp then reports `error` and leaves the dead block alone (its message still says "until a reboot", which is
  no longer true). Once the picture path is back, `h713-mips-restart` rebuilds the DSP through msp's `reset`
  file, up to three times: twelve rebuilds measured, eleven at the first attempt and one at the second, none
  failed (with the tool alone eight of eight at the first), and the HDMI audio was audible again after a standby
  without a reboot (`doku/174` §2, `doku/177` §3).

Measured with Marco at the box (09.10.2026, r2test3): wake by the power key and by the remote's IR power key,
sleeps of 3.5 and 8.4 minutes, the long press (a power-off; with `h713_gate=0` in the environment the board
boots straight back). Not measured: HDCP 2.2 from the source after the restart. The power draw was measured on the same evening: 2.4 W in standby, 2.9 W off (`doku/181`).

## What wakes it

| Source | Status |
|---|---|
| power key (PL4) | measured: "wake key (0x95)", and the waking press does not count as a new press (`doku/174` §1) |
| IR remote | crust compares against the 19 codes of the vendor device trees and the board's own (`CONFIG_CIR_WAKE_CODE`); measured with the shipped remote's power key: "wake ir (0x9b)" (`doku/174` §1) |
| wake timer | measured (`rtcwake`-style, 5 s; `doku/165` - `doku/167`) |
| RTC alarm | the kernel side computes it; whether a release should wake on it is the owner's decision |
| CEC | not supported |
| Bluetooth remote | not a wake source: Bluetooth is down in standby. Its power key **starts** a standby once it is paired (`h713-power` listens on it; HY300PRO-G-EU, 10.10.2026); asleep it falls back to IR, which wakes the box |
| IR remote, going to sleep | not possible yet: Linux has no keymap on the IR receiver (`rc-empty`), so its power key never reaches `h713-power` (TODO 2.35) |

After a wake by the power key Linux sees a `KEY_POWER` - the press that woke it. On an image with standby
[h713-power](../tools/h713-power.md) ignores it; without h713-power logind would power off.

## When something goes wrong

**Going to sleep can hang (C1).** A standby can stop right after the arisc driver's line `standby N: net none`
and before the watchdog's; crust waits 15 s for the sleep, then resets the board, and it boots again. Breadcrumbs
put it into the PPU power-off of TVCAP under the running HDMI capture (five of five). With the capture stopped
first (r2test3) it did not happen in 50 sleeps, against 5 in 111 before - a strong hint, not a proof
(`doku/173`).

A standby that does not come back looks like this: **dark, red LED, no network, the key does nothing.**
The LED follows PB5, so it is red whether the board sleeps, hangs or sits in the gate; it says nothing
about which.

What happens then depends on the watchdogs. Under Linux `systemd` feeds the SoC watchdog
(`RuntimeWatchdogSec=16s` and `RebootWatchdogSec=16s` in `/etc/systemd/system.conf.d/10-h713-watchdog.conf`;
measured in stage W2, doku/170; until 08.10.2026 the image set neither). For a standby the kernel feeds it
itself until its devices are suspended and then stops it; from there crust's net on the second watchdog would
watch the sleep (`H713_SLEEP_NET`). That watchdog's register layout is measured (stage S0, doku/170), the
net in a sleep is not yet, so a release does not carry it - until then nothing watches the sleep itself. A reset out of a standby
that did not finish - crust's budget going to sleep (15 s) or waking up (60 s), the watchdog - finds the gate's
RTC word on "STBY", which `sun50i-h713-mips` writes at the start of a standby and takes back once the display
core runs again (kernel `0245`). U-Boot then waits in the gate, dark, as after a power-off, and the power key
starts the board; a `reboot` asked for from Linux still boots. Measured on 09.10.2026 with hangs provoked by a
test module, going to sleep and waking up ([power-gate.md](../uboot/power-gate.md), `doku/179`); with
`h713_gate=0` the board boots straight through instead. Not caught: crust itself hanging asleep.
*Superseded (09.10.2026):* "A watchdog reset finds the gate's RTC word on "running" and boots straight
through, lamp on, unless the owner decides it should go to the dark gate. None of this has been measured in a
standby yet."

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
names a `CRUST_DEFCONFIG` - or, since 10.10.2026, for a `--test-image` of such a board (the HY300PRO-G-EU's
`geucrust2`): BL31 with `SYSTEM_SUSPEND`, the sleep file above, h713-power on the key.
Without `--standby` BL31 has no `SYSTEM_SUSPEND`, the sleep file says `AllowSuspend=no`, and the key
powers off as it always did; crust still runs the HDMI front end. `release/check-crust.py` (step 10)
refuses an image whose parts disagree about it ([build-container.md](../build-container.md) for the
compiler).

The variant is DRAM self-refresh. Deeper sleep (PLLs off, root clocks on the 24 MHz oscillator) is ported
and built but has never run, and the release refuses it. A design limit stays even then: crust polls at
24 MHz on the oscillator, so the oscillator never stops; whether that matters is a question for the first
power measurement.

Details: `doku/162` - `doku/168`, `doku/171` - `doku/174`, [arisc.md](arisc.md), [h713-power](../tools/h713-power.md),
[the power-on gate](../uboot/power-gate.md).
