# HDCP: handing a projector its own licence back

Both HDCP versions on this board work the same way in the end: a key set that belongs to
*your* device is handed to the receiver, and the receiver does the protocol itself. Neither
key is ever shipped with this project. They are read out of the device they belong to, at
run time, and nothing is written back.

The two differ in who does the handing and when:

| | key set | where it is read | who hands it over | when |
|---|---|---|---|---|
| **HDCP 1.4** | 288 bytes (of a 320-byte record) | secure storage, eMMC | the boot loader, through our own EL3 service | before the display firmware is released |
| **HDCP 2.2** | 912 bytes | secure storage, eMMC | `h713-hdcp-key.service` in userspace | after boot, and again by `h713-hdcp-key --bind` whenever the display firmware is restarted (below) |

HDCP 1.4 has to happen in the boot loader because the display firmware polls the sink's
"key loaded" bit in `Rx_HDCP14_LoadKey` and gives up early. By the time userspace could act,
that loop has already failed (`doku/112`, `doku/145`).

## What the hardware allows, and what it does not

The 1.4 key set never becomes readable. It is decrypted by the Crypto Engine with a key that
exists only inside the SoC - key-select 3, the hardware key - and the engine enforces two
rules about it:

* **Never towards readable memory.** A task with key-select 3 and a destination in DRAM is
  refused with `ESR 0x11`. That is not a bug to work around; it is the whole point. Such a
  task would be key export.
* **Only out of the protected window.** The DMA *source* must lie in the Trusted OS window
  (`0x48600000`-`0x48afffff`). Otherwise the engine refuses as well - which stops anyone from
  feeding a foreign device's key set into the sink.

So the path is: stage the stored bytes inside that window, then run one engine task with
key-select 3 and the key sink at `0x03041400` as its destination. The key set goes from the
engine straight into the receiver. Nothing in software ever sees it.

This cost a long night to work out, because the second rule is invisible: the engine answers
the same refusal whether the key slot or the source region is the problem. For a while our own
code also gated the push on a probe that could never pass - the probe tried key-select 3 into
DRAM, which the engine refuses *by design*, and the gate read that as "this device cannot do
it" (`doku/147`, `doku/148`).

## No unwrapping needed

The vendor's key box only decrypts an item when its "encrypted" flag is set, and on these
devices it is not: the vendor's own `op 1` builds no decrypt task at all. Measured against
live memory, the stored 288 bytes are **byte-identical** to the source of the vendor's own
engine task - 0 of 288 differ. So the stored bytes go to the sink unchanged, and the 16-byte
wrapping key that earlier drafts read out of the stock Trusted OS image is not needed for
anything. That removed the most awkward part of the installer by deleting it.

## Where the key sits, and how it is found

Secure storage starts at LBA 12288 and is 1 MiB. It holds slots of 4096 bytes, every item
stored **twice** - original and copy. Our layout declares the region as its own partition
(`hy310-keys`), so an install leaves it alone, and `h713-install` compares it byte for byte
after writing and stops with exit 10 if anything changed.

An item is self-describing, and both the boot loader and the installer read it that way -
by magic, name and length, never by a constant offset:

```
0x00  u32   magic 0x17253948
0x08  char  name[0x40]            NUL-terminated
0x60  u32   payload length
0x64  u8    payload
      short items (snum, *_hash, wifiBleDatas) keep their data right here
      blob items (hdcpkey, hdcpkeyV22) nest a second header:
0x64  char  name[0x40]
0xa4  u32   inner length           320 for 1.4, 912 for 2.2
0xa8  u32   flags 0x10000001
0xb0  u8    the key material
```

The outer length is `0x4c + inner`, which for 1.4 is `396 = 76 + 320` exactly. Both copies
must agree; if they do not, the boot loader refuses rather than push a damaged key set into
the sink.

`hdcpkeyV14_hash` ("581b62") matches no checksum over the stored ciphertext - the vendor
computes it over the plaintext, which only the TEE sees. It is therefore unused here.

## The two key sets behave differently across devices

Measured on two devices with two different serial numbers:

| | HY310 | HY300 Pro |
|---|---|---|
| HDCP 1.4 (288 B) | `d743dcf4…` | `d743dcf4…` - **the same** |
| HDCP 2.2 (912 B) | `59598951…` | `fa0a8bd8…` - **different** |

The 1.4 key set is shared across the product line; the 2.2 key set is device-bound. Two
consequences follow, and both are implemented:

* A foreign secure-storage region must **never** be restored onto a device - it would
  overwrite that device's own 2.2 key set, its serial number and its MAC addresses.
* The 1.4 key set is a shared DRM secret, so publishing it would hand everyone the means to
  circumvent. It stays out of this repository, and
  [`installer/tests/no_key_material.py`](../../installer/tests/no_key_material.py) fails the
  build if key material ever appears in a tracked file. What may be stored, and is, are
  SHA-256 fingerprints: one-way, and enough to say "this is the key set we know".

## After a restart of the display firmware

A standby parks the display MIPS and Linux starts it again (`h713-mips-restart`, [standby](standby.md)); the HDMI receiver is unbound and bound around it. The two key sets fare differently.

* **HDCP 2.2.** The receiver's probe is what asks for the key (`request_firmware()`), and `h713-hdcp-key.service` deleted it after the boot, so a plain bind would run the init sequence without it. `h713-mips-restart` therefore binds through `h713-hdcp-key --bind hdmi-rx`: the tool finds the key in secure storage as it does at boot, writes it to a file only root can read in a tmpfs directory (`/run/hy310/firmware`), points the firmware search path there, binds the receiver, and deletes the file and clears the path afterwards. Exit 0 is bound with the key; 3 is bound without it because none was found (a picture rather than none, logged as a warning); 1 is not bound. Nothing is stored or sent. **Not measured:** HDCP 2.2 from a source after such a restart (`doku/172`, `doku/173`).
* **HDCP 1.4.** The boot loader writes the key once per boot, before the display firmware is released, and nothing in the restart path writes it again: the restart driver loads `display.bin` with the "key loaded" wait defused, as U-Boot does at boot (kernel `0231`), and `h713-mips-restart` knows only the 2.2 key. It does not need to: the sink keeps the 1.4 key through the standby. Measured on the HY310 on 09.10.2026 with a ThinkPad (i915, HDCP 1.4 only): after six standbys with a restart each in one boot, and again after a seventh, `h713-tv ctl hdcp` said `key-1.4: loaded` and `Undesired` -> `Desired` stood at `Enabled` within 2 s, with no write since the boot (`doku/175` §3). One sink write per boot is therefore enough on an image with standby too. Where the sink lies is not measured, only that it holds.

## Tools

```bash
# What HDCP key material does this device have, and where? Searches rather than assumes,
# so it also answers for a board nobody has measured yet - and prints the lines to paste
# for anything it does not recognise.
installer/h713-hdcpkey <dump.img | secure-storage.bin | backup-directory>

# On the device: check the 2.2 key, writing nothing; or bind the receiver while the key lies in a tmpfs
# (what h713-mips-restart calls)
h713-hdcp-key --check
h713-hdcp-key --bind hdmi-rx
```

In U-Boot:

```
h713_hdcp14              read the stored key set and put it into the receiver's sink
setenv h713_hdcp14 0     skip it entirely
setenv h713_hdcp14_wipe 1   push 288 zero bytes instead, clearing the sink
```

## Measuring it honestly

**The sink survives a warm reset.** An "Enabled" measured after an earlier push says nothing
about the current one - a control run with no push at all still authenticated, which produced
one retracted claim before it was understood. So a measurement only counts as a pair, with
nothing in between:

1. `h713_hdcp14_wipe=1`, boot, and confirm the source falls back to **Desired**. This proves
   two things at once: the sink is empty, and our push mechanism works at all.
2. boot again with the default, and confirm the source reports **Enabled**.

On 08.10.2026 the 1.4 pair was repeated on the R1 test image, where crust is the ARISC firmware: two warm starts, `h713_hdcp14_wipe=1` and then the default, the source went `Desired` and then `Enabled`, the sink's key-loaded register 0x93 read 0x41 and then 0x45 (`doku/170`, A0).

### HDCP 2.2, measured with a real 2.2 source

05.10.2026, Fire TV stick on the HY310's HDMI input, mainline 6.18 with the U-Boot key push:

```
$ h713-tv ctl hdcp
version:       2.2 (session stands)
authenticated: yes (2.2 session)      READY 0, REAUTH_REQ 0
key-1.4:       loaded (LINK 0x93=0x45)
key-2.2:       handed over at probe (THal_Vp_SetHDCP22Key accepted; 2.2 advertised to the source)
firmware:      ... MsgHandle_SKE_SEND_EKS ... HDCP Process cost tick:108
```

`SKE_SEND_EKS` is the source handing over the encrypted session key, which it only does after it
has verified the receiver certificate against the DCP root - so the line is the source's verdict,
not ours. Eight mode switches (1080p60 <-> 720p50/60) each re-authenticated within the firmware's
poll; no fallback to 1.4. Protected content was not needed for this: the handshake is mutual, and
a failed one does not leave a standing session.

## Limits

* A source that asks for HDCP 1.4 at once, in the mode switch (a ThinkPad with i915), stayed on `Desired` for 40 s in two runs on the R1 test image; a request 2, 4 or 6 s after the lock stood at `Enabled` within 5 s. `doku/170` reads it as the receiver not being ready in the first moment and i915 not asking again; crust is not involved (the hot-plug pin stays up). Not measured with the vendor's ARISC firmware or with the Fire TV stick.
* The boot loader's own watchdog guard around the push is armed only if nobody else is
  driving the watchdog. U-Boot's driver stays off on this board; if that changes, the guard
  steps aside rather than fight over the register.
* A device whose key set is missing, blank, singly stored or damaged boots normally and says
  so on the console. Only HDCP-protected sources stay dark. `h713-install` reports the same
  verdict at install time, so it is known before anything is missed.
* HDCP 2.2 remains unproven in one respect: whether those 912 bytes are plaintext or a
  TEE-side ciphertext is still open (`ROADMAP.md`).
