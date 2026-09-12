# Crypto Engine

The H713 has a dedicated Crypto Engine (CE) block, and this image ships with it switched off for ordinary
use: `CONFIG_CRYPTO_DEV_SUN8I_CE` and `HW_RANDOM` are both unset in the release defconfig. That is
deliberate, not an oversight — software already does the job better, except for one thing only the CE can
do, and that one thing is not finished.

## Why it's off for everyday crypto

The four Cortex-A53 cores have the ARMv8 crypto extensions (`aes pmull sha1 sha2`) and run software AES/SHA
around 2 GB/s in-kernel — 10 to 50 times more than this device's eMMC or Wi-Fi ever need. cstenger measured
the CE itself against that baseline (`origin/wip/crypto-ce-tooling`, commit `bb44dc8`) and found it slower
to be worth wiring up at all: with real known-answer self-tests enabled, every mainline algorithm fails,
because the mainline `sun8i-ce` driver builds a 32-bit-address descriptor and this SoC's CE expects 40-bit
(5-byte) address fields in a two-register-bank layout — it reads garbage and reports `address invalid` or
`algorithm not supported`. There is also no hardware RNG here: the CE reports `algorithm not supported` for
that too. None of this is a clock, reset or interrupt-wiring problem; it is purely the descriptor format,
and reopening it for generic crypto would gain nothing. This conclusion is cstenger's and this project
adopts it unchanged.

## Why it's still needed: the RSSK, for HDCP 1.4

One key cannot be reached any other way. HDCP 1.4 support needs the RSSK, a 128-bit key burned into eFuses
that only the CE can read (`Key-Select 3`). Decrypting the chip-bound HDCP 1.4 key blob (from secure
storage, see [emmc-layout.md](emmc-layout.md)) means feeding it through the CE with the RSSK selected; the
plaintext then goes by DMA straight into a hardware key sink at `0x03041400`, never into DRAM where software
could read it. No software substitute exists at any speed — this is not a performance question.

`doku/112` reconstructed the vendor descriptor format purely by disassembling OP-TEE's key-loading routine,
since the vendor kernel driver's source was never available. On 11.09.2026 a small measurement module
(`0148`–`0150`) put that reconstructed format on the device: AES-128-ECB, `Key-Select 0`, a software key, 16
bytes, destination DRAM, checked against the FIPS-197 test vector — deliberately avoiding any device key or
key sink. It passed in 65 µs, confirming the descriptor layout at the silicon and, incidentally, confirming
that cstenger's dead end really was the format, not the hardware.

**Outstanding:** whether the non-secure world may use `Key-Select 3` (the RSSK) and the secure channel
`CE_S` (`0x03040800`) at all is not yet tested. That test needs one power cycle and can hang the bus, so it
is planned but not run. Its outcome decides where the eventual driver lives — a small Linux driver if
non-secure access is permitted, otherwise an EL3 SMC call in TF-A. HDCP 1.4 itself is deferred past v0.1
regardless of that result.

The measurement module loads automatically by device-tree match and stays in the shipped kernel — a
deliberate choice (the maintainer, 12.09.2026), not a leftover.

Details: `doku/114-plan-crypto-engine.md`, `doku/112-plan-hdcp14-crypto-engine.md`.
