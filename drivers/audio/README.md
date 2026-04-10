# HY310 Audio Drivers

## Modules

| Module | File | Description |
|--------|------|-------------|
| snd-soc-sunxi-h713-codec | snd-soc-sunxi-h713-codec.c | Internal audio codec (DAC + ADC + speaker PA) |
| snd-soc-sunxi-h713-cpudai | snd-soc-sunxi-h713-cpudai.c | CPU-DAI / DMA platform (DMA ch7) |
| snd-soc-sunxi-h713-machine | snd-soc-sunxi-h713-machine.c | Machine driver (creates ALSA card) |

## Loading

```bash
modprobe snd-soc-sunxi-h713-machine
# This auto-loads codec + cpudai as dependencies
```

## Verification

```bash
# Check ALSA card registered
aplay -l
# Expected: card 0: audiocodec [audiocodec], device 0: ...

# List mixer controls (14 controls expected)
amixer -c 0 contents

# Test playback
speaker-test -c 2 -t wav
```

## Speaker Audio

Speaker audio works directly through the internal codec via the Audio Hub path.
The MIPS DSP is **not** required for basic playback — it is only needed for
DSP effects. See [docs/AUDIO.md](../../docs/AUDIO.md) for full analysis.

## Audio Bridge

The `bridge/` subdirectory contains the TridentALSA audio bridge driver
(`snd-hy310-trid-audio-bridge`). This is the routing block between the
internal codec, I2S, and S/PDIF (OWA) for HDMI audio passthrough.

```bash
modprobe snd-hy310-trid-audio-bridge
```
