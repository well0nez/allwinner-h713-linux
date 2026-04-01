# HY310 Audio Subsystem

## Status: PARTIAL — ARM codec working, speaker path blocked by MIPS DSP

## Hardware

- **Internal codec**: `0x02030000`
  - Register window 1: `0x02030000` / `0x32c`
  - Register window 2: `0x02031000` / `0x7c`
- **Audio bridge (TridentALSA)**: `0x0203042C`, compatible `"vs,trid-audio-bridge"`

## Drivers (out-of-tree)

- `snd-soc-sunxi-h713-codec.c`
- `cpudai.c`
- `machine.c`

## ALSA Card 0 ("audiocodec")

- 14 mixer controls
- Speaker PA GPIO: **PB2**
- PLL-Audio SDM working: 98.304 MHz
- codec-dac / codec-adc clock: 24.576 MHz

## Known Register Issue

- `HP_REG` (offset `0x324`):
  - Stock value: `0x80808F8C`
  - Mainline value: `0x0000038C`
  - BIT31 / BIT23 / BIT15 likely control analog power — investigate before enabling headphone output

## CCU / Clock Note

- `bus-audio-hub` (CCU offset `0xA5C`) **cannot be written** on H713 — register is non-functional; do not attempt to gate/ungate it

## BLOCKER: Speaker Path

Speaker audio on this board does **not** go through the ARM codec output directly. The stock path is:

```
AudioServer
  -> audio.primary.ares.so
    -> libmspsound.so
      -> MIPS DSP (TridentALSA card 4 in stock firmware)
        -> speaker
```

- MIPS audio DSP requires `msp_download_sxl()` firmware load — **not yet implemented** in the mainline driver
- Stock ALSA card 4 corresponds to the MIPS-side audio engine
- Stock libs dumped for reverse engineering: `libmspsound.so`, `libUtility.so`, `audio.primary.ares.so`

## Next Steps

1. Reverse `libmspsound.so` to understand `msp_download_sxl()` firmware protocol
2. Implement firmware download from ARM side (requires CPU_COMM IPC — see `CPU_COMM.md`)
3. Determine HP_REG analog power bits before enabling headphone output
