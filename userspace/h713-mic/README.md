# h713-mic - the stock remote's microphone (prototype)

One script, `h713-mic`, Python 3, without dependencies. It turns what the stock Bluetooth LE remote (1d5a:c081)
sends while its microphone key is held into a standard SBC stream; any SBC decoder makes PCM of that:

```
h713-mic info                       # the remote's HID device, its hidraw node, whether report 0x1E gets through
h713-mic record -o voice.sbc        # one press: from the first voice report until the key is let go
ffmpeg -f sbc -i voice.sbc voice.wav    # 16 kHz mono (ffmpeg is in the image's media profile)
h713-mic convert capture.txt out.sbc    # a capture, one report per line ([time] hex), e.g. from btmon
```

## The format (TODO 2.51)

| What | Is |
|---|---|
| report | HID input report ID `0x1E`, 60 bytes, every 8 ms (125/s) while the key is held; the key itself sends `KEY_VOICECOMMAND` (consumer `0x0c00cf`, report 3) |
| the 60 bytes | three pieces of 20 bytes, each scrambled on its own: a chain over the bytes in a fixed order with the key 50 (`unscramble()`) |
| unscrambled | one SBC frame without its 4-byte header: 4 bytes of scale factors (8 x 4 bit) and 56 bytes of samples (16 blocks x 28 bit) |
| the header put in front | `9C 31 1C crc`: 16 kHz, 16 blocks, mono, loudness, 8 subbands, bitpool 28; the CRC-8 over config, bitpool and the scale factors |
| start | the remote sends by itself, no start command; the first ~10 frames of a press are SBC silence |
| end | no voice report for 40 ms (5 frame times) |

Read out of the stock firmware's audio HAL (`libhbgdecode.so`, which reads `/dev/hidrawN` and decodes the same way);
checked against both captures of 11.10.2026 (HY310, HY300PRO-G-EU): unscrambled, the SBC code "all bits 1", which an
encoder never writes, appears 0 times in 122 096 samples (4-9 % in any wrong reading), and the decoded audio is speech.

## What it needs on the device

- `CONFIG_HIDRAW=y` (the board defconfig had it off): without it there is no `/dev/hidraw*`.
- Report 0x1E must be described in the remote's report descriptor no longer than the 60 bytes it sends: since 6.18 the
  HID core drops a report shorter than its description before hidraw sees it (the trap of report 3, kernel 0169).
  `h713-mic info` reads the descriptor from sysfs and says so - it works without hidraw, so it can be checked first.

Not measured on a device yet. `make test` runs the host tests (no device, no recording: the remote's start packet and a
bit-exact round trip through ffmpeg's SBC encoder, whose 64 kbit/s frames are exactly the remote's).
