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
register; `ctl mute` uses the DSP's mute bit directly. Measured against a calibrated microphone: volume
60 sits at −18.4 dBFS, 40 at −33.6 dBFS - about 15 dB of range across that stretch of the scale
(08.09.2026). Audio follows the picture automatically: it comes up when `h713-tv` shows a source and goes
quiet on the console, with no separate switch to operate.

## Acceptance

Acceptance testing completed **08.09.2026, 22:05** (kernel patch series 110): a cold start patches and
runs the DSP with zero mailbox timeouts; all three source rates play and volume/mute are measurable; a
source on/off, a resync, and a 720p↔1080p switch all bring sound back within a few seconds with no manual
step; 20 audio on/off cycles and 20 kernel-module reload cycles ran clean, each reload re-patching the DSP
in about 1.7 s; a 28.7-minute continuous tone showed no dropout and no self-healing event. Lip
synchronisation was judged **by ear, against a YouTube video: "perfect, synchronous"** - a subjective
judgement, not an instrument measurement.

## What is missing: mixing device sounds with HDMI

The codec's DAC accepts exactly one input at a time - the DSP's I2S output, or the ordinary Linux PCM
device - never both. A PC source that keeps its HDMI audio stream open (as most do, even on silence) can
therefore block device sounds entirely; the vendor stack avoided this by mixing both streams inside the
DSP's own graph before the codec ever sees them. That mixing path is understood in outline (a second DSP
graph, an audio "bridge" block that would carry the Linux PCM stream into it) but **not started** -
planned as its own piece of work, not a gap in what shipped.

Details: doku/100-plan-hdmi-audio.md, doku/101-plan-audio-treiber.md, doku/102-plan-audio-mischung.md,
doku/00-STATUS.md
