# h713-mips-restart - start the display MIPS again and bring the picture back

A standby parks the display MIPS ([cpu-comm.md](../subsystems/cpu-comm.md), `suspend_late`), and nothing
in the kernel starts it again: after the wake the wall would stay on the last picture. On an image
with standby this tool is the way back. [h713-power](h713-power.md) runs it after a wake when the
driver `sun50i-h713-mips` says `parked` ([standby.md](../subsystems/standby.md)); nobody has to type
anything. By hand it also reloads a running MIPS. It is a POSIX shell script of under 100 lines,
installed as `/usr/local/sbin/h713-mips-restart`, and needs `systemctl`, `logger` and `flock`.

```
h713-mips-restart [FIRMWARE]    # FIRMWARE: an absolute path, default /boot/mips/display.bin
```

The picture is gone while it runs. The restart is the driver's ([mips.md](../subsystems/mips.md)):
from the park it loads the firmware and starts the core like U-Boot, from a running MIPS it halts,
loads and starts like the vendor. The tool is what has to happen around that, because the restart
rebuilds the `cpu_comm` region and everything the HDMI receiver told the old firmware is gone.

## What it does, in order

1. **Refuses before touching anything** (exit 2): FIRMWARE not absolute or not readable, no
   `sun50i-h713-mips` driver bound (no `state` file), or another run holds
   `/run/h713-mips-restart.lock`.
2. Stops `h713-warp` and `h713-tv@*`, and remembers whether warp ran.
3. Looks for the receiver's video node (the one named `sun50i-h713-hdmirx`). **If a process holds
   it open, it refuses** (exit 2): an unbind under an open node frees memory the close still uses.
   Since patch `0233` the receiver's memory outlives an open handle; that is not measured with a
   handle open.
4. Unbinds the receiver `hdmi-rx` from `sun50i-h713-hdmirx`.
5. Writes FIRMWARE to the driver's `restart` file and reads `state`; a refused write or anything but
   `running` is exit 1.
6. Binds the receiver again, and waits up to 60 s for its video node (exit 3 if it does not show).
7. Resets the start limits of `h713-warp` and `h713-tv@` (3 starts in 60 s, so standbys in quick
   succession do not run into them), starts `h713-tv@<video node>` and, if it ran before, `h713-warp`.
8. Rebuilds the audio DSP (below).

| Exit | Meaning |
| --- | --- |
| 0 | picture path back |
| 1 | the driver refused the restart, or the MIPS did not come up |
| 2 | refused, MIPS untouched (the services are started again) |
| 3 | the MIPS runs, but the receiver, its node or a service did not come back |
| 4 | ended by a signal |

Every outcome is a journal line: `journalctl -t h713-mips-restart`. Run by hand it also writes to
stderr; under systemd only to the journal. The end of a good run:

```
h713-mips-restart: MIPS parked 0x02001600=0x00000000 0x0200160c=0x00000000; firmware /boot/mips/display.bin
h713-mips-restart: picture path back after <N> ms: MIPS running 0x02001600=0x80000002 ..., /dev/video2
```

**Whatever ends the run, the services come back as far as the MIPS allows.** The sysfs writes ignore
`INT`, `TERM` and `HUP`, so a write is never cut half through; a signal then ends the run with exit
4 after the cleanup. At the end the tool reads from sysfs whether the receiver is bound, so a signal
during the unbind or the bind leaves neither an unbound receiver on a running MIPS nor a second bind.
A receiver is bound again only on a running MIPS: if the core is not `running`, the receiver stays
unbound and a warning says so. After a failure the driver stays `halted` or `failed`, and the next
write starts over from there (`0231`).

```
cat /sys/bus/platform/drivers/sun50i-h713-mips/*/state     # running | halted | parked | failed
journalctl -t h713-mips-restart
```

**The HDCP 2.2 key.** A plain bind runs the receiver's init sequence without the device's HDCP 2.2
key: `h713-hdcp-key.service` deletes it after the boot, so the step `THal_Vp_SetHDCP22Key` is
skipped. The tool therefore binds through `h713-hdcp-key --bind hdmi-rx`, which puts the key into the
tmpfs for exactly that bind (exit 3 of the key tool: bound without the key, a warning). Where the
installed key tool has no `--bind`, it falls back to the plain bind. When the key tool fails in any other
way (a read error, a broken tool), the receiver is bound plainly if the tool did not bind it: the picture
without the HDCP 2.2 key rather than none until the next boot, logged as a warning with the tool's exit
(TODO 5.14, review U5). Only a plain bind that fails too ends in exit 3. Whether a source gets HDCP 2.2
after a restart is not measured (`doku/172` §5, `doku/174` §3).

**The audio DSP.** The DSP sits in TVFE and loses its power in the sleep; the `msp` driver then
reports `error` and leaves the dead block alone (patch `0243`; its message still says "until a
reboot", which is no longer true, `doku/174` §3). Once the picture path is back, the tool writes 1 to
msp's `reset` file, up to three times, until `state` reads `running` ("audio DSP rebuilt (attempt
N)"). A DSP that stays down is a warning, never an exit code, and nothing is tried if the picture
did not come back or msp is not in `error`. Measured at the HY310: eight standbys through the tool, eight rebuilds at the first attempt (twelve with
the rebuilds by hand, one of those at the second; `doku/177` §3), and the laptop's sound audible over HDMI afterwards without a reboot
(`doku/174` §2). Before this step the sound only came back after a reboot (`doku/173` §3).

## How long it takes

On the R2 test image: six standbys in one boot, the MIPS ready 300 ms after its start and the
picture back 3.9-5.2 s after each wake (`doku/172` §4); 30 of 30 in a fast loop (`doku/173` §4). With
the owner at the box: wake by the power key and by the remote's IR key, sleeps of 3.5 and 8.4 minutes,
the picture path after 3.9-5.3 s. From the wake to a picture on the wall it is about 11 s: the
restart takes 4.5 s, then `h713-tv` pulls the hot-plug pin low for 300 ms at its start, and the
laptop needs a good 4 s to send again (`doku/174` §1).

## What is not measured

The exit codes 1 to 4 run in the tests only, against a model of sysfs and `systemctl`
(`userspace/h713-power/tests/`, part of `release/tor.sh --tests`), not at the device. The press of
the real power key on the whole path was measured with the owner at the box (`doku/174` §1); the
first runs called h713-power's `suspend()` and `picture_back()` directly (`doku/172`). `$H713_ROOT`
replaces `/` in front of `/sys`, `/proc`, `/run`, FIRMWARE and the key tool, and `$H713_WAIT` the 60
s; both are for the tests.
