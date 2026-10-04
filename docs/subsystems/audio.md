# HDMI audio: signal to speaker

Sound from an HDMI source reaches the projector's speaker without a vendor daemon in the way: a small
on-chip DSP that the vendor stack used to drive from userspace is now brought up and fed straight from
the kernel.

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
  audio-top control words - followed by 300 ms for the DSP's own ROM monitor to boot before its mailbox
  will answer at all.
- **A firmware patch for the DSP itself**, loaded over that mailbox in blocks, with exactly one status
  read after each block (a read *inside* a block stops the load; the DSP needs the pause *between* blocks
  as its cue to continue). A load failure or a stuck mailbox is recovered by resetting the island and
  retrying, not by rebooting.

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

Details: doku/100-plan-hdmi-audio.md, doku/101-plan-audio-treiber.md, doku/102-plan-audio-mischung.md,
doku/00-STATUS.md
