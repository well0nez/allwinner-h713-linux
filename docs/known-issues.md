# Known issues

This is what still gets in your way, and what to do about it. "open" means nobody has fixed it yet;
"by design" means it will not change because something else depends on the current behaviour; "fixed in
git, not in the image" means the source has the fix but the image you can currently install does not yet.

## Not built, or not proven yet

| Issue | Why | Workaround |
|---|---|---|
| No Bluetooth | The driver builds, but the AIC8800D80's Bluetooth firmware (`fmacfwbt_*`) is not in the stock firmware - only in a separate SDK package with an unresolved licence. Wi-Fi is unaffected; it ships its own firmware set. | none |
| No AV1 decode | The H713 is the first Allwinner chip with AV1 hardware, and it is not yet clear whether the existing reverse-engineering covers a working driver or only the register layout. | none |
| No HDCP 1.4 | Confirmed on this chip: HDCP 1.4 keys live in hardware, decrypted by the Crypto Engine straight into a key sink (`0x03041400`) that DRAM never sees. A Linux driver would have to program that engine with key-select 3 (RSSK) before the MIPS starts - untested whether the non-secure world is allowed to do that at all. That test costs a power cycle and is deferred past the first release. | Use an unprotected source, or one that only needs HDCP 2.2 |
| HDCP 2.2 - one proof outstanding | Works: the 912-byte key is pulled from your device's own secure storage at boot and handed to the display firmware (verified 2026-09-11, key load at 6.4 s, driver sequence complete at 6.5 s). What is **unverified** is whether those 912 bytes are plaintext or a TEE-side ciphertext - that needs an actual HDCP-mandatory source (streaming stick, console, Blu-ray player) on the HDMI input to observe. | none needed unless the source refuses to negotiate |
| Hardware video decode, IOMMU, Mali GPU | Unverified **in this image** - these come from cstenger's tree and are proven working there, not re-tested here. That tree also has an open memory-corruption case under `mpv` (KASAN work in progress) - unverified, not reproduced by us. | none |
| EDID modes incomplete | The 512-byte EDID blocks go to the display firmware unchanged; which modes that unlocks is not worked through. Known gaps: 1600×900 and any 120 Hz mode. | Use one of the six verified modes (see STATUS.md) |

| No picture after plugging a source in | Fixed 16.09.2026 (kernel patches 0136a, 0136c): the driver used to switch the firmware's source away and back after the first publication, and that switch kills any HDMI port that was not locked a moment ago - the firmware reported no signal until the cable was pulled and put back. The first publication now releases the capture directly, like every later one. Verified on the HY310: a source plugged in after boot, a boot with the source plugged in, `ctl auto` 30 s after boot, and an unplug and replug. | Nothing to do on an image from 16.09. on. On an older image, `h713-tv ctl replug` brings the picture. |

| Latency spikes on the access point | A client at −50 dBm, linked at 72 MBit/s, sees ping times jumping between 3 ms and 2 s while throughput is fine (5.7 MB/s measured 2026-09-12 over SSH). It looks like power saving on the radio rather than the link itself; not investigated. | Bulk transfers are unaffected. For interactive work over Wi-Fi, or if it bothers you, use the wired path or `mode=sta` on an existing network. |

## By design

| Behaviour | Reason |
|---|---|
| No desktop in the shipped image | The image runs `h713-tv`, a fixed HDMI-input service, not a compositor - the projector's job here is the HDMI input. The KMS device (`card1`) is a normal DRM device underneath; nothing stops you from running a compositor on it instead ([docs/subsystems/display.md](subsystems/display.md)). |
| No temperature reading | This unit has no NTC: both of the device's own decompiled device trees say `ntc_num = 0`, and the vendor code treats that as binding rather than fabricating a value (confirmed 2026-09-11, `doku/60` "Der NTC war ein Phantom", patch `0152`). Heat protection runs off the **tachometer** instead - a stalled fan powers the device off (patch `0159`), the same trigger the vendor firmware uses, and the one signal here that is verified (PB5 off → 0 RPM, on → 4770 RPM). A board variant that does carry an NTC picks it up automatically through `ntc_num`. A device that overheats with a *turning* fan is covered by nothing, so keep the vents clear. |
| The projector waits for the power key after being plugged in | Same as with the stock firmware, and deliberate: [docs/uboot/power-gate.md](uboot/power-gate.md). `fw_setenv h713_gate 0` makes it boot on power instead. |

## Untested paths

| Path | State |
|---|---|
| Installer on Windows | Not tried for this release; the documentation says so explicitly. `sunxi-fel.exe` for Windows is planned after feedback from Linux users (decision 2026-09-12, `doku/116` §2). Since layout v4 (2026-09-16) `install` is Linux-only in any case: it mounts the image's own file systems to copy your device's files into them, and says so in one sentence. `identify`, `dump` and `extract` mount nothing. |
| The image's files are copied in through a mount | Layout v4 (2026-09-16, after issue #1): the installer no longer writes the proprietary files into placeholders of a measured size but mounts `hy310-boot` and `hy310-rootfs` and copies them in as ordinary files, so a firmware whose files are bigger than the HY310's fits. Covered by tests that mount a real ext4 and read every file back, including through this project's own ext4 reader - but **no device run** has gone through it yet. An image built for the old layout is refused by this installer with one sentence, and a v4 image likewise by the installer of its own release; use the installer that ships with the image you have. |
| Wi-Fi station mode - two corners | Both modes are verified (2026-09-12): access point with a laptop, station against a real network. Still untried: whether Android accepts the access point's DNS behaviour (it answers only for the device's own name, `REFUSED` otherwise) without flagging "no internet", and how `dhclient` in station mode interacts with a second DHCP client on `eth0` (two default routes, metric not decided). |
| Bright-image camera test | The internal camera is confirmed working as a V4L2 device, and a grab succeeds in 3.4 s - but every capture so far was of a dark room with nothing projected on the wall. A bright, in-focus picture from the camera has not been produced yet (2026-09-12, `analyse/boot/abnahme-v08-20260912.txt`). |

## Feature gaps

| Missing | Detail |
|---|---|
| No audio mixing with HDMI | The internal DAC accepts only one source at a time, and a PC connected over HDMI holds that source open continuously - device sounds (UI, alerts) cannot currently be mixed in (`doku/102`). |
| Standby is one stage only | Standby draws 4 W with the front LED red; a deeper sleep (under 1 W, instant-on, using the ARISC co-processor and IR/CEC wake) is designed but not implemented (`doku/104`). |
| No autofocus | Focus is manual only, with a range watcher that stops before the mechanical limit. Autofocus needs a test pattern to measure against - running it against an arbitrary dark scene produces nonsense - so it is planned as a separate tool, not a mode of `h713-focus`. |

## The image on your device may not match a fresh build

Everything built before 2026-09-12 20:00 - including what ships as `v0.8` through `v0.10` - carries a BL31
(TF-A firmware) from 2026-09-10 with debug assertions still compiled in (49,260 bytes). The build script
never rebuilt it because `make` considered the existing binary current; a clean build produces the intended
release BL31 at 45,164 bytes, four bytes of which are just the embedded build time. `release/build-all.sh`
now wipes the TF-A and U-Boot build directories first, so this is fixed in the source - but the fix has not
yet been through a device acceptance run, and any image built before it is patched still has the old BL31.
Nothing is expected to behave differently (same source, minus assertions), but treat that as unverified
until the next device run confirms it (STATUS.md "Boot chain"; `doku/116` §4a P3.9).

Details: `doku/61-todo.md`, `doku/60-offen.md`.
