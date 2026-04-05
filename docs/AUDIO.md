# HY310 Audio Subsystem

## Status: WORKING — Speaker output via internal codec

## Architecture

The H713 has an internal audio codec at 0x02030000 with DAC, ADC, and analog
mixer. Speaker output uses the **Audio Hub** path (APB DMA → DAC → Analog Mixer
→ PA Amplifier → Speaker), NOT the I2S path and NOT the MIPS co-processor.

Previous assumption that audio required the MIPS DSP was **incorrect** for basic
playback. The TridentALSA Audio Bridge is only needed for DSP effects.

## Signal Chain



## Drivers (out-of-tree modules)

| Module | Compatible | Function |
|--------|-----------|----------|
| snd-soc-sunxi-h713-codec.ko | allwinner,sunxi-internal-codec | Codec + analog mixer |
| snd-soc-sunxi-h713-cpudai.ko | allwinner,sunxi-dummy-cpudai | DMA platform driver |
| snd-soc-sunxi-h713-machine.ko | allwinner,sunxi-codec-machine | ALSA sound card |

Auto-loaded at boot via /etc/modules-load.d/audio.conf.

## ALSA Controls

| Control | Range | Default | Function |
|---------|-------|---------|----------|
| digital volume | 0-63 (inverted: 63=max) | 32 (50%) | Master volume |
| Speaker | on/off | on | PA amplifier enable (GPIO PL2) |

## Key Register Configuration (set in sunxi_codec_init)

| Register | Value | Purpose |
|----------|-------|---------|
| DAC_DPC bit0 | 1 | Audio Hub Output ON (required!) |
| DAC_DPC bit29 | 0 | DAC Src = APB (not I2S) |
| DAC_VOL_CTRL[15:8] | 90 | Calibrated DAC volume (max without clipping) |
| HP_REG | HP_EN_L + HP_EN_R + HP_AMP_EN | HP amp drives internal mixing bus |
| DAC_REG 0x310 | 0x0B15FC7F | Full analog output path enabled |

## Critical Findings

- **Audio Hub Output = ON is mandatory** for speaker sound via APB path
- **Headphone amp must be ON** even without headphones — it drives the internal
  mixing bus that feeds the speaker. Without it, volume is ~50% reduced.
- **DAC Volume > 90 causes no additional gain** but values < 68 reduce output.
  Capped at 90 to prevent clipping.
- **DAC Src Select must be OFF (APB)** — the I2S path does not produce sound
  (stock uses it differently with 3-clock setup we don't replicate).

## GPIO

- PL2 (R_PIO): PA amplifier enable (active HIGH)
- Controlled by Speaker on/off ALSA control
- 160ms delay after enable for amplifier settle

## Known Limitations

- No HDMI audio (separate subsystem, not implemented)
- No microphone/capture tested
- TridentALSA DSP effects not available (would need MIPS IPC)
- Stock audio_mixer_paths.xml partially implemented (Speaker + HP paths only)
