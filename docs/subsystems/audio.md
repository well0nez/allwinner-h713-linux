# HDMI audio: signal to speaker

Sound from an HDMI source reaches the projector's speaker without a vendor daemon in the way: a small
on-chip DSP that the vendor stack used to drive from userspace is now brought up and fed straight from
the kernel. A standby switches the DSP's power off; the last sections say how it is rebuilt.

## The path

```
HDMI-RX (MIPS firmware, autonomous)
   --I2S-->  MSP audio DSP (on-chip "island", patched firmware)
   --I2S-->  codec I2S window  -->  DAC  -->  headphone amp  -->  speaker
```

The HDMI receiver's audio side is entirely the display firmware's own affair - Linux never touches it.
Getting sound out of the other end needs three things nothing in mainline provided for this SoC:

- **A working clock model.** The audio island hangs off `pll-periph0`; mainline's stock description of
  that PLL for this SoC used the wrong multiplier/pre-divider bits, so Linux believed it ran at half its
  real rate. Fixed to match the H616 model it turns out to share.
- **A power-up sequence for the DSP island** - bus reset, the audio clocks above, and a handful of
  audio-top control words (`0x0614a000` reads `0x700` once they are set) - followed by 300 ms for the
  DSP's own ROM monitor to boot before its mailbox will answer at all.
- **A firmware patch for the DSP itself**, loaded over that mailbox in blocks, with exactly one status
  read after each block (a read *inside* a block stops the load; the DSP needs the pause *between* blocks
  as its cue to continue). A load failure or a stuck mailbox is recovered by resetting the island and
  retrying (three attempts, then the state stays `error` until the `reset` file is written), not by
  rebooting.

Once patched, the DSP is set to the vendor's own routing graph for "HDMI straight to speaker" - minus a
fixed 2 ms delay line that exists purely for lip-sync trim; skipping it was judged lossless rather than
worth reverse-engineering the vendor's delay format. The codec side needs its own small patch: an I2S
input window the mainline codec driver never initializes, a source-select control (HDMI-I2S vs. the
ordinary Linux PCM device), and a sample rate that follows whatever the HDMI source is actually sending
(32, 44.1 or 48 kHz) rather than a fixed rate.

## The one control

`h713-tv` exposes a single knob, `h713-tv ctl volume`, mapped onto the DSP's own quarter-dB mixer
register; `ctl mute` uses the DSP's master mute. Since `v0.96-beta` the knob follows the stock volume curve
(0 = silent, 1 = -41 dB, 50 = -22 dB, 100 = -9.5 dB), and on 03.10.2026 ten points of it measured within
0.8 dB of that curve (`doku/134` D2). The first measurement, against a calibrated microphone on 08.09.2026,
had volume 60 at -18.4 dBFS and 40 at -33.6 dBFS - about 15 dB across that stretch, and nearly inaudible
below half. Audio follows the picture automatically: it comes up when `h713-tv` shows a source and goes
quiet on the console, with no separate switch to operate.

## Acceptance

Acceptance testing completed **08.09.2026, 22:05** (kernel patch series 110): a cold start patches and
runs the DSP with zero mailbox timeouts; all three source rates play and volume/mute are measurable; a
source on/off, a resync, and a 720p↔1080p switch all bring sound back within a few seconds with no manual
step; 20 audio on/off cycles and 20 kernel-module reload cycles ran clean, each reload re-patching the DSP
in about 1.7 s; a 28.7-minute continuous tone showed no dropout and no self-healing event. Lip
synchronisation was judged **by ear, against a YouTube video: "perfect, synchronous"** - a subjective
judgement, not an instrument measurement.

## Device sounds mixed with HDMI

The codec's DAC accepts exactly one input at a time - the DSP's I2S output, or the ordinary Linux PCM
device - never both. A PC source that keeps its HDMI audio stream open (as most do, even on silence) can
therefore block device sounds entirely; the vendor stack avoided this by mixing both streams inside the
DSP's own graph before the codec ever sees them. That mixing path is in `v0.96-beta` (measured on the HY310
02./03.10.2026): kernel patches 0176-0178 add a playback PCM `hw:hy310hdmi,0` (48 kHz, S16_LE,
stereo) whose DMA ring feeds the audio bridge's input stream 2 and joins the HDMI branch inside the DSP
(DECODER3 into MIXER2, the vendor's path 0x89); `h713-tv` keeps the DAC on I2S and mutes the HDMI branch
alone in silence; `rootfs/overlay/usr/share/alsa/cards/H713-MSP.conf` makes that PCM ALSA's `default`
while the card is present (a board without it keeps `plughw:0`, the codec), and `/etc/asound.conf` names
the two paths `bridge` and `codec`. On 03.10.2026 (`doku/134` D1 - D3) HDMI and the device sounds came out
within 0.07 dB of each other over 20 rounds, 20 off/on cycles and a DSP reset ran clean, and nothing
clicked at open or close. What is still missing is something that plays a sound: no service in the image
makes one. Plan and state: doku/102-plan-audio-mischung.md, section 6.

## The island loses its power in a standby

The DSP island sits in the TVFE power domain (`pd_tvfe`, named in the msp node's `power-domains`). The driver
holds a runtime-PM reference on it, but genpd switches TVFE off in the noirq phase of a system sleep whatever
that says, and the DSP loses its patch and its graph. Measured on 09.10.2026: the audio-top word `0x0614a000`
read `0x700` after a boot and `0` after a standby and the MIPS restart, while msp still reported `running`
(`doku/173` section 3). HDMI audio does not pass the ARM, so no mailbox timeout would start self-healing; the
driver has sleep callbacks of its own (kernel patches 0215, 0218, 0219, 0243).

**Why the dead island must not be touched.** The audio interface AUDIF (`0x06146000`) hung the CPU without an
abort in all three logged accesses made while `0x0614a000` read 0, and read normally once its clock bits were
set in the same run (`doku/nachtlog/S21-re-audif-zugang.md`, 08.09.2026). After a standby that is the normal
state. Before 0243 the driver kept `running`, so the first sound through the bridge PCM (the ALSA default)
would have written AUDIF with the clock down, and so would the stall timer of a stream that ran into the
sleep. That a kernel without 0243 really hangs this way was not tried.

## What msp does in a sleep

Suspend always stops the self-healing worker (the system workqueue does not freeze) and marks the island lost:
a running bridge PCM, its interrupts and its stall timer are stopped. Resume, with the default
`rebuild_after_sleep=0`, sets a DSP that was up to `error` and leaves the island alone. In `error` the bridge PCM
refuses to open (measured after a standby: `aplay` refused, nothing hung, `doku/174` section 1), and volume and
mute are only remembered, for the next bring-up to apply (from the code). The resume log line still ends "no
HDMI audio until a reboot", which is no longer true (open, `doku/174` section 3).

`rebuild_after_sleep` (bool, writable, patches 0218 and 0219) would have the wake start the rebuild itself.
It is **off**: that rebuild is the first access to the island after genpd switched the domain off and on,
whether the domain is really back is not measured (genpd marks it on even when its power-on times out), and a
hang there would pass for a standby fault. Switched on: not measured.

## Rebuilding after a standby

Once the picture path is back, `h713-mips-restart` ([h713-power](../tools/h713-power.md),
[standby.md](standby.md)) reads each msp device's `state` and, if it says `error`, writes `1` to the `reset`
file, up to three times, until `state` reads `running`; a DSP that stays down is a journal warning, not an exit
code. Measured on 09.10.2026 (`doku/174` section 2, `doku/177` section 3): twelve rebuilds, eleven at the first
attempt and one at the second, none failed (through `h713-mips-restart` alone eight of eight at the first),
and the laptop's sound over HDMI was audible again without a reboot; before the step it was not.
This supersedes `doku/173` section 3 ("only after a reboot"), whose `reset` straight after a standby, on a
kernel without 0243, ended in a mailbox timeout; whether 0243 or the timing made the difference was not
separated.

Not measured: the device-sound PCM and the volume after such a rebuild, a sleep with `rebuild_after_sleep=1`,
the duration of the rebuild.

The second and third attempts had one cause (`doku/206`, 12.10.2026): the wake-up call at a block boundary of
the patch download - one read of `0x00EE` - ran into the mailbox's 50 ms now and then, the DSP being busy with
the block it was just given, and that single timeout aborted the whole download. Since `0262` the call asks
again up to its own 500 ms; the next request was answered at once every time. 30 wakes, 30 at the first
attempt, five late calls absorbed on the way.

Details: doku/100-plan-hdmi-audio.md, doku/101-plan-audio-treiber.md, doku/102-plan-audio-mischung.md,
doku/00-STATUS.md; for the standby doku/172 - doku/174 and doku/nachtlog/S21-re-audif-zugang.md.
