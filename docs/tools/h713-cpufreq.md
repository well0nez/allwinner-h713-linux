# h713-cpufreq - the CPU clock under the warp's load

A POSIX shell script run once per boot by `h713-cpufreq.service` (`userspace/h713-cpufreq/`), in
every image since 11.10.2026. It sets two things and never fails the boot; it waits up to 30 s for
each to appear, because cpufreq-dt and panfrost probe after the root file system.

1. **schedutil may change the clock every 20 ms** (`rate_limit_us`). The kernel derived 462 us from
   the declared transition latency, and the clock then followed every burst of work; each change is a
   PWM regulator ramp and a PLL relock, carried out by the thread `sugov:0`. Set here and not by
   tmpfiles, which ran before the governor had its sysfs directory (three boots in a row with 462 us).
2. **A real-time task asks for no minimum clock.** The GPU's job interrupts are threaded handlers at
   SCHED_FIFO 50 and fire four times a frame with the warp on, and schedutil asks for the maximum
   clock whenever a real-time task is runnable: the clock swung between 480 and 1296 MHz forty times a
   second, whatever the rate limit. With `CONFIG_UCLAMP_TASK` in the kernel the script sets
   `sched_util_clamp_min_rt_default` to 0 and the threads keep their class; on a kernel without it
   the three `irq/*-panfrost` threads are moved to SCHED_OTHER instead.

Measured on the HY300PRO-G-EU on 11.10.2026, warp on, 1080p60 source, 20 s each (`doku/201`):

| irq threads | rate limit | time at 1296 MHz | changes/s | `sugov:0` | all four cores | fps |
|---|---|---|---|---|---|---|
| FIFO 50 | 462 us | 13 % | 14 | 18.0 % | 10.7 % | 59.8 |
| FIFO 50 | 20 ms | 43 % | 40 | 2.5 % | 4.2 % | 59.7 |
| SCHED_OTHER | 20 ms | 2 % | 1.6 | 0.1 % | 4.6 % | 59.7 |
| SCHED_OTHER | 462 us | 0 % | 0.3 | 0.1 % | 4.4 % | 59.7 |

The clock then stays at 480 MHz under the warp and rises with real load, up to 1296 MHz; a job
completion still runs at once, since the cores are idle. On the HY310 the four cores went from 5.9 %
busy with the warp on to 2.9-3.1 %, together with `h713-tv` counting its late frames instead of
logging each one ([h713-warp](h713-warp.md)). Not measured: the uclamp variant against the thread
variant on a device, and the effect on Kodi's or the decoders' load.

Details: [hardware](../hardware.md), [GPU](../subsystems/gpu.md), `doku/196`, `doku/201`.
