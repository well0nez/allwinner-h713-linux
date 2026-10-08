# h713-power - the power key on an image that offers standby

Without standby the power key powers the projector off: logind's default `HandlePowerKey=poweroff`, and
TF-A turns the power-off into the [power-on gate](../uboot/power-gate.md). An image built with
`release/build-all.sh --standby` adds this service and lets it decide instead
([standby.md](../subsystems/standby.md)):

| Press | Does |
|---|---|
| short (released before `long_s`, 3 s) | standby, if `/sys/power/mem_sleep` offers `[deep]`, crust reports `ready=1` and `power.conf` says `short = standby`; otherwise power-off, as before |
| held for `long_s` | power-off, without waiting for the release |
| within `ignore_s` (2 s) after a resume the key itself woke | nothing: it is the press that woke the box |

The action comes on the release, so the key is up when the box goes to sleep. The last rule is why a
policy is needed at all: gpio-keys reports a key that woke the system as a `KEY_POWER`, which logind
would read as "power off" the moment the box is back. Measured so far only as the stray event of a timer
wake, which crust 0032 removed (`doku/165`, `doku/167`); a wake by the key itself has not been measured.
h713-power reads the event's `CLOCK_BOOTTIME` stamp and compares it with `wake` and `resume_ns` in the
arisc driver's `state` file.

```
h713-power status        # what a short press would do now, and why; the devices it listens on
h713-power run           # what the unit runs
```

**Why it cannot take the key away by accident.** The unit runs the tool under `systemd-inhibit
--what=handle-power-key:handle-suspend-key --mode=block`: logind keeps its own power-off and only steps
back while the lock is held. If h713-power dies, the lock goes with it, and the key powers off again.
That is the reason for a lock instead of `HandlePowerKey=ignore`, which would leave a dead key behind a
crashed service.

It listens on every input device that can send `KEY_POWER` - the key on the case (`gpio-keys`) and the
paired Bluetooth remote - and picks up a remote that connects later. `remote = off` in
`/etc/h713/power.conf` leaves the remote's key without any effect. `refused = poweroff | log` says what
a short press does when the kernel refuses the standby after all. Refused means `fail` in
`/sys/power/suspend_stats` moved, or neither counter did within 30 s. The 30 s start again when the tool
comes back from the freezer, and the counters are read before the time is judged: a slow freeze or resume
never turns a standby that happened into a power-off. A refusal and a power-off for a short press are
logged as warnings.

**The picture after a standby.** The standby parks the display MIPS (cpu_comm, `suspend_late`), and
nothing in the kernel starts it again: after the resume the wall would stay on the console. When the
projector stays on after a standby - or after a refused one with `refused = log`, the park may have come
before the refusal - and the driver `sun50i-h713-mips` says `parked`, h713-power starts
`h713-mips-restart`. It runs beside the key loop; until it ends a short press does nothing (it is logged),
a press held for `long_s` still powers off. A MIPS that is `running` is left alone; with no driver bound
the tool says so as a warning.

```
h713-mips-restart [FIRMWARE]   # FIRMWARE: /boot/mips/display.bin
```

It stops `h713-warp` and `h713-tv@*`, unbinds the HDMI receiver, writes FIRMWARE to the driver's
`restart` file (from the park: load and start like U-Boot; from a running MIPS: halt, load and start like
the vendor), binds the receiver, waits up to 60 s for its video node, and starts `h713-tv@` on it and
`h713-warp` again. The receiver is unbound only when no process holds its node, and bound again only on a
running MIPS. Whatever ends the run, the services come back as far as the MIPS allows. Exit 0 picture
path back, 1 the driver did not bring the MIPS up, 2 refused (MIPS untouched), 3 the MIPS runs but the
receiver, its node or a service did not come back, 4 ended by a signal. Each outcome is a journal line
(`journalctl -t h713-mips-restart`; run by hand also on stderr). The sequence brought
the picture back at the HY310 on 08.10.2026 from a running MIPS and from the park registers set by hand;
after a real standby it is not measured yet.

**Not measured yet.** The window after a key wake (`ignore_s`) is provisional; the device stage K
measures it with the owner at the key. Whether the remote's power key should suspend too, and whether a
refused standby should power off or only log, are the owner's decisions; the
defaults are on and power-off. Ignoring a short press while the picture comes back is provisional too.
`$H713_POWER_ROOT` replaces `/`, `$H713_SYSTEMCTL` the `systemctl` and `$H713_MIPS_RESTART` the
`h713-mips-restart` it calls; `$H713_ROOT` and `$H713_WAIT` do the same for h713-mips-restart (the tests,
`userspace/h713-power/tests/`, part of `release/tor.sh --tests`).
