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

**Not measured yet.** The window after a key wake (`ignore_s`) is provisional; the device stage K
measures it with the owner at the key. Whether the remote's power key should suspend too, and whether a
refused standby should power off or only log, are the owner's decisions; the
defaults are on and power-off. `$H713_POWER_ROOT` replaces `/` and `$H713_SYSTEMCTL` the `systemctl` it
calls (the tests, `userspace/h713-power/tests/`).
