# The firmware's UART shell: it starts, and it is on UART4 (2026-08-07)

Static analysis of `display.bin`, no bench time. Both questions the item asked
are answered, and one of its premises is wrong.

## The threads start unconditionally

`shell_thread_uart` and `shell_thread_monitor` are constructed at exactly one
site each, in a spawner at `0x8b1834c4`:

```
0x8b1834c4  addiu $sp, $sp, -32
0x8b1834d8  addiu $6, $6, 0x1bc8   ; a2 = "shell_thread_uart"
0x8b1834d4  addiu $7, $7, 0x33a4   ; a3 = entry 0x8b1833a4
0x8b1834e8  jal   0x8b15c894       ; thread create
0x8b1834ec  addiu $4, $zero, 4     ; a0 = 4
0x8b183500  addiu $6, $6, 0x1bdc   ; a2 = "shell_thread_monitor"
0x8b18350c  jal   0x8b15c894       ; a0 = 5, entry 0x8b183434
0x8b183518  jr    $ra
```

**Straight-line. No branch, no flag, no config test.** Its single caller is
`0x8b153608`, in the main startup path, immediately after the config at
`0xabe01000` is parsed -- and `0xabe01000` is the uncached alias of ARM
`0x4be01000`, the `display_cfg.xml` window we load ourselves.

So **in our configuration the shell is already running**, every time the MIPS
reaches readiness. Nothing needs enabling.

## It is UART instance 4, not our console

The shell's input and output routines resolve to one register block:

| MIPS VA | offset | DesignWare register |
| --- | --- | --- |
| `0xb7501000` | +0x00 | RBR / THR -- read and written |
| `0xb750107c` | +0x7c | USR, polled before every byte |
| `0xb75010a4` | +0xa4 | HALT |

`USR` at `0x7c` and `HALT` at `0xa4` are **DesignWare-specific**, which
identifies the IP: the same `snps,dw-apb-uart` the H713 DTs use. It is a full
putc/getc pair -- poll USR, then read or write THR.

H713 UARTs are `0x400` apart (`serial@2500000`, `serial@2500400`), so an
instance at window `+0x1000` is **instance 4, ARM `0x02501000`**. That is
**inference, not proof**: the MIPS-to-ARM window base register has not been
found, and the DRAM offset does not apply here (DRAM is uncached = physical +
`0x60000000`, which would put this in the middle of DRAM). What is solid is the
`+0x1000` offset against `0x400` spacing, and that only offsets of `n * 0x400`
can be UART bases.

**It is not UART0**, which is our console on PH0/PH1 -- consistent with never
having seen a byte of it in three days of logs.

Our pin table gives UART4 two routes: **PH6/PH7/PH8/PH9 at mux 2**, or
**PD8..PD11 at mux 3**.

## What the shell actually is

Not a log stream. A full interactive console: `Command List:` / `Var List:` /
`User List:` / `Key List:`, `help [cmd]`, line editing (backspace, left, right,
up, down), `Warning: Command is too long`, `Command not Found`, and a
`Please input password:` / `password error` gate.

And, from `./reg_access.c`:

```
regw   write register
regr   read register
       Invalid Address: 0x%x        IsInvalidRegAddr
```

**Register read/write from the coprocessor's own side of the fabric**, with an
address validator. That is a materially different instrument from anything we
have: every register result in this log so far is an ARM-side view.

## The premise that was wrong

The item said *"`display_cfg.xml` references 'How to use elog command.md'"*. **No
`display_cfg.xml` on this system contains the string `elog` at all** -- not the
board-B copy, not board A, not the research extraction. The elog help text lives
in `display.bin`, which also carries the full option set:

```
Usage: cmd [-o on/off] [-r uart/net] [-m sync/async/buf] [-l tag level] ...
  -r, --route    set elog output route: uart/net
```

The attribution was wrong; the capability is real and larger than claimed.

## The password: static derivation points at `default user`, UNCONFIRMED

The check is plaintext -- that much is solid. The prompt handler at `0x8b1831dc`:

```
lw    $2, 0($4)        ; $4 = runtime list node -> record pointer
lw    $4, 16($4)       ; a0 = the text the user typed
jal   strcmp           ; 0x8b1bdbc0, the word-at-a-time strcmp
lw    $5, 8($2)        ; a1 = record+8  (branch-delay slot)
beqzl $2, ...          ; strcmp == 0 -> authenticated; else "password error"
```

`0x8b1bdbc0` is a plain `strcmp` (the `0x01010101`/`0x7f7f7f7f` zero-detect
idiom, not a digest), so **whatever string is at `record+8`, you type it
verbatim**. No hash, no salt.

What is at `record+8` is a static inference, not a proof. The only `"default
user"` string in the binary (`0x8b201bb0`) is pointed to from exactly one place:
the `+8` field of a single table entry at `0x8b20dee0`, whose flags `0x2000`
distinguish it from the commands (`0x800`) and key bindings around it:

```
+0x10ded0  8b201ba8  8b1825b8  8b201ba0  0800   "setVar" {name, code, "set var"}   a COMMAND
+0x10dee0  8b201bc4  8b201bc0  8b201bb0  2000   "VS"     {name, "",   "default user"}  flags 0x2000
+0x10def0  8b206e30  8b19fe00  8b206e18  0000   "win"    {name, code, "for window debug"}
```

So the derivation is: the compare reads `record+8`; the runtime record is very
likely this `0x2000` entry (nothing else holds `"default user"`); therefore the
password is `"default user"`.

**Two gaps keep this from being fact:**

1. **The runtime-vs-static link is inferred.** The strcmp walks a runtime list
   node; I did not trace the user list's construction to prove its nodes point
   at this static table. The `0x8b20dee0` base is referenced by no stored word,
   so the list is built by iterating the array at run time -- plausible, unproven.
2. **The field semantics are unproven.** For this entry `+4` is an empty string
   and `+8` is `"default user"`. If the layout is `{user, password, display}`
   the password would be the *empty string* and `"default user"` a label; the
   code reads `+8` regardless, but that makes `"default user"` either the
   password or a mislabelled compare. Only typing it settles which.

**The definitive test is to type it, and that needs the bench** -- there is no
way to reach the shell from this side. It reads UART4's RX register, which is
filled by the pin, not by any ARM MMIO write (writing `0x02501000` hits THR, the
transmit side). So this stays a derivation until someone types `default user`
at the prompt and, if that fails, an empty line.

## There is no pin to reach, so the item is PARKED

The shell binds UART4, whose only routes are `PH6/PH7` (mux 2) or `PD8/PD9`
(mux 3). Those pins carry nothing else broken out on this board -- besides GPIO
they are `uart4`, `gmac` and `twi0`, and the projector has no ethernet -- and
the operator confirms there are no serial pads beyond the existing console
(UART0). So UART4 does not surface anywhere probeable; physical access would
mean microsoldering to the SoC ball or a via, if it exists at all.

**The wire-free alternative is a firmware redirect, not a wire.** The shell
takes input through a function pointer -- the getc at `0x8b19d344` that polls the
UART -- and we load `display.bin` ourselves. Patching getc/putc to read and
write a ring in the CPU_COMM shared memory would let the ARM drive the shell
entirely through DRAM. That is a real feature, not an opportunistic one: a
`display.bin` patch (which breaks the SHA-256 the loader verifies, so the
expected hash moves with it), a ring getc/putc, and an ARM-side pump.

## Feasibility for DECD: there is a second, memory-driven shell (2026-08-07)

Asked before starting video decode, since DECD is the trigger named below. The
answer upgrades the item.

**Two shell threads are spawned, not one.** `shell_thread_uart` polls the UART
directly (`0xb7501000`). `shell_thread_monitor` does not -- its getc/putc/avail
(`0x8b19d3b4/bc/64`) tail-call a shared trio (`0x8b155f2c` getc, `0x8b155f78`,
`0x8b155e08`) that reads and writes a **ring buffer in DRAM** through a device
object: a global pointer at `0x8b232c20`, an `enabled` byte at object `+0`, and
ring head/tail at `+0x6c`/`+0x70`. Same command parser, so driving that ring is
driving a shell -- `regr`/`regw` included.

**The ring is ARM-reachable.** The MIPS addresses are kseg0 (`0x8b232c20` ->
kseg-phys `0x0b232c20`), and the firmware the ARM loads at `0x4b100000` is
kseg-phys `0x0b100000` -- a **+0x40000000 window**. So `0x8b232c20` is system
`0x4b232c20`, inside the image we stage, and the object it points at
(another kseg0 address) converts the same way. The ARM already writes this
region.

**So the wire-free route needs no firmware patch after all**, if that ring is
writable and the device is registered. That is a strict improvement on the
"patch getc/putc + move the SHA-256" estimate above: the vendor built the
mailbox.

**The confirming probe is read-only and cheap**, and it is the next step rather
than any patch. With the MIPS running: `md.l 0x4b232c20` to get the device
pointer, convert `0x8b..`->`0x4b..`, and read the object -- `+0` enabled, ring
indices at `+0x6c/+0x70`, and the buffer -- to learn whether the monitor stream
is registered, where the ring is, and whether it is the CPU_COMM channel or a
separate device. No patch, no risk.

**This recon has dual payoff.** Pinning the MIPS->system window and the ring
layout is exactly what DECD needs anyway, since the decoder moves frames through
buffers the ARM must locate. Two open questions survive it: cache coherency of a
cached-kseg0 ring the ARM writes (CPU_COMM already crosses this boundary, so a
known class of problem), and whether the exact UART *peripheral* address matters
at all now that the monitor route avoids it.

**Verdict: feasible, and cheaper than the firmware-patch estimate.** Worth the
one read-only probe when the board is next up with the MIPS running -- ideally
folded into DECD bring-up, not as a separate errand.

## Confirmed on hardware, 2026-08-07

The read-only probe ran. `h713_disp init 0x34` to bring the MIPS up, then:

```
md.l 0x4b232c20 4   -> abd01000 00000001 00000000 00000000
md.l 0x4bd01000 ..  -> a "Terminal" device: name, two SysView ring-streams
md.l 0x4bd43000 ..  -> all zero (the 512 KB stream is idle, not a passive log)
```

- The device global holds `0xabd01000` (kseg1) -> system **`0x4bd01000`**, the
  start of the 1 MB `debug_buffer`. **The `+0x40000000` window is now measured,
  not inferred.**
- The object is a C++ `Terminal` (RTTI type-name at `0x8b1fb914`) built from
  `SysView` ring-streams (vtable `0x8b1fb850`, methods at
  `0x8b1547dc/824/870/834/860`). Buffers at `0x4bd01200` (256 B), `0x4bd01300`,
  `0x4bd42f00` (256 B) and `0x4bd43000` (**512 KB**), all in the debug region.
- **All buffers are kseg1/uncached**, so the ARM and MIPS see the same bytes
  with no cache flush. The one open risk from the feasibility note is closed.
- Ring indices read `0/0` and the 512 KB stream is all-zero: registered but
  idle, nothing sent, no passive log to read for free.

**Verdict, upgraded from feasible to confirmed:** the wire-free path needs no
firmware patch, no pin, and no cache workaround. Driving it is the remaining
work -- push a command into the input SysView ring, advance the write index,
poll the output ring -- and the SysView methods are all in the file image, so
that is static work for DECD time, not another bench trip.

**Parked, deliberately.** The payoff is `regr`/`regw` -- the MIPS's own view of
the fabric -- and it has never been needed: every register result in this
project came from the ARM side, and the display path is done. The trigger to
revisit is DECD/video bring-up, if the MIPS firmware turns out to do things the
ARM side cannot observe. Not before. The password derivation above stands as the
one thing already in hand should that day come.

# The pre-run FAT read never killed the display -- REFUTED (2026-08-07)

Three probes, each isolating one candidate, each followed by the identical
`fill_pattern(0)` and run a working path uses. **All three lit the panel.**

| probe | what it isolates | duration | result |
| --- | --- | --- | --- |
| `preread-read` | the second FAT read | **178 ms** | panel lit |
| `preread-hash` | SHA-256 CPU/cache traffic | **42 ms** | panel lit |
| `preread-delay` | time alone | 3000 ms | panel lit |

Two more candidates were dead before the bench: it is not "writing the
framebuffer before run" (the working path calls `fill_pattern(0)` in that exact
slot), and it is not "touching FAT before run" (`h713_disp_load()` reads ~1.5 MB
off the same filesystem immediately beforehand, on every path that works).

## "Seconds of work" was wrong by a factor of fifteen

This log has said since 2026-08-04 that the pre-run work is *"seconds of work,
and a lot of cache traffic, in a window where nothing else does any."* Measured:
**220 ms** for read and hash together. That was an estimate written down as a
characteristic, and it has been steering the hypothesis ever since -- "seconds"
makes a timing story plausible, 220 ms does not. The `preread-delay` probe ran
3000 ms, **thirteen times** the real figure, and still lit the panel.

## The likelier explanation is that the fault was never about ordering

The five blank `vendor-logo` runs are described here as: *"The panel stayed dark
with every register dump byte-identical to a working run, fbcheck proving the
framebuffer correct, and the TCON marker equally absent."*

This same page describes the missing-teardown bug as: *"each mode ended holding
the MIPS in reset, so a second run initialised into a torn-down state and **the
panel stayed dark while the console looked perfect**. That cost at least four
results."*

**That is the same signature, and the counts nearly match.** Teardown did not
exist when those five runs were taken. The bisection that "settled" the load
ordering changed the ordering *and* ran from a different starting state, so the
two variables were never separated.

If that is right, then: the load-ordering rule is an artifact, `vendor-logo-early`
does not reproduce anything, and the three probes above were testing a fault
that had already been fixed by something else -- which is exactly what three
clean passes look like.

## The control settles it: the fault does not exist

```
h713_disp panel-test 0x34 vendor-logo-early
```

First command after a power cycle, so teardown could not be involved. The 2.7 MB
FAT read, the SHA-256 and the BMP conversion all ran before `h713_disp_run()`,
and **it rendered correctly** -- both chroma markers, `fbcheck` bounds
343..378 / 367..912, frame committed, operator confirms no problem.

So the rule this log has carried since 2026-08-04 -- "the logo must be loaded
after the display sequence, not before it" -- is **false**, and the reproducer
kept to chase it reproduces nothing.

The five blank runs remain unexplained in their own right, but the missing
teardown is the obvious candidate: its signature is "the panel stayed dark while
the console looked perfect", it cost "at least four results" elsewhere in this
log, and it had no fix on 2026-08-04. The bisection that produced the ordering
rule changed the ordering *and* the starting state together, so it never
separated them. That is inference. What is demonstrated is only that the rule is
false today.

**Testing the control cost one run and closed the item.** Three probes were
built to explain a mechanism, and the thing that settled it was asking whether
there was still anything to explain -- which should have come first.

# 0x05280084[31:16] is the layer height, and the omission was right (2026-08-07, test_38)

The last of the two sites `h713_disp_panel_patch` left out, owed a two-sided
perturbation since 2026-08-04. `fb-vsize`: four red/blue horizontal stripes of
180 rows, boundaries at 25/50/75 %, five steps.

| step | write | result |
| --- | --- | --- |
| 1 | control, nothing | 4 stripes, edges at **26.3 / 50.8 / 74.1 %** |
| 2 | `0x05280084[31:16]` = **0** | **layer gone.** Uniform white field; measured contrast collapses 195 -> 21 |
| 3 | = **360** | **cropped to the top half.** Red 0-25 %, blue 25-50 %, blank below |
| 4 | = **1080** | identical to baseline -- the panel is only 720 tall |
| 5 | `0x05280080[31:16]` = 360 (control) | **identical to step 3** |

**`0x05280084[31:16]` is the layer's display height**, and `0x05280080[31:16]`
is a second one that crops the same way. Both are live and load-bearing. Step 4
behaving exactly like the baseline is the confirmation: a height cannot show
more rows than the panel has.

## The omission was correct, and the caution that produced it was right

The argument that left this site out was:

> stock's literal zero at `0x05280084[31:16]` and `0x0528008c[15:0]` "may be a
> decode artefact rather than a real store; writing a zero we cannot justify is
> worse than leaving the vendor default in place."

For `0x0528008c` that was wrong, and it was the entire framebuffer fault. **For
`0x05280084[31:16]` it was right.** Writing the zero blanks the layer -- step 2
is a white screen. So stock's apparent zero cannot be a real store at this point
in the sequence: either the static read is the decode artefact the caution
suspected, or stock writes it somewhere the value is replaced before it matters.

**Had this been "restored" by analogy with `0x0528008c` -- which is what this log
has been inviting since 2026-08-04 -- the display would have gone blank.**

## The method point, and a correction to how this run was framed

Going in, this was described as testing "a discredited justification". That was
wrong, and the run says so: the justification was **correct here**. An argument
that fails once is not discredited, it is *unreliable* -- which is a different
thing and demands exactly what was done, a measurement per site rather than a
verdict carried from one site to another.

The two sites were adjacent, in the same register block, omitted in the same
sentence for the same reason. One was a catastrophe and one was correct. Nothing
short of driving each one and watching could have separated them.

Also worth keeping: the run was designed expecting a null, and the console said
so before it ran -- "ALL FIVE IDENTICAL is the likely outcome and is a real
result". Predicting the boring outcome in advance is what makes the interesting
one credible when it arrives.

# The vendor's shutdown, compared with ours (2026-08-07)

Our teardown was written from first principles against a boot log. The vendor's
*shutdown* was captured during the Android boot session, and comparing them
produced one change worth making.

The vendor's entire display shutdown is five lines:

```
[209.567628] ge2d 5240000.ge2d: acquire tvdisp clock on emergency shutdown
[210.210128] Invalid pin          <- 643 ms gap
[210.212881] Invalid pin
[210.215651] Invalid pin
[210.218428] ge2d 5240000.ge2d: ge2d suspend
[210.454291] reboot: Power down
```

| | vendor | ours |
| --- | --- | --- |
| display clock | **acquires** `tvdisp` in order to shut down | left running; teardown *refused* if the block was not already clocked |
| MIPS | never parked -- no `mipsloader` line at shutdown at all | parked, reset asserted |
| panel rails | not sequenced; they die at `Power down` | PH16 then PF6, with the panel's declared 20/75/250 ms off timings |
| LVDS PHY / route | not restored | returned to cold values |
| backlight | never touched | never touched |

## What we took: the clock acquire

**The vendor turns the display clock on in order to turn the display off.**

That is the answer to a problem our teardown had and that the first version of
the single-exit work papered over. `h713_disp_teardown()` opens by *reading* the
AFBD control register, and those blocks wedge the interconnect when read gated,
so it could only run after a completed sequence. The guard added earlier that
day refused otherwise -- which left the exact case it existed for, a failure
part-way through the sequence with the panel powered and the MIPS live,
uncleaned. **Ungating is the fix; refusing was not.**

**The clocks alone were not enough, and that cost a hang.** The first attempt
called only `h713_display_clocks_on()` -- the module clocks and their video2
parent. On a cold boot `h713_disp teardown` printed its first line and hung on
the very next AFBD read.

`h713_display_prepare()` had the answer in a comment that predated the whole
attempt: *"the initial SPL values open only part of the display fabric"*. The
TVTOP routing at `0x05700000` is part of what makes those blocks **reachable**,
not merely part of configuring them.

So teardown calls the whole of `prepare()` when the sequence has not run. That
is evidence rather than a third guess: **every normal run calls `prepare()` cold
before any display access**, so it is the one primitive already proven safe from
exactly this state. The warm path is untouched.

**Verified on hardware 2026-08-07**, cold boot, nothing run first:

```
H713 teardown: requested from the prompt
H713 MIPS: display clocks/routing prepared
H713 teardown: panel down (PF_DAT=00000000 PH_DAT=00000000), PHY 18000000/00000030, route 40000000, MIPS reset=00000000
```

The middle line only appears on the cold path, so it doubles as a marker for
which branch ran. Both guards -- in `h713_disp_fail()` and on the standalone
`teardown` command -- are gone.

**A second latent hang turned up while bisecting this.** `h713_disp scanrate` on
a cold boot wedged the board: `h713_disp_scan_rate()` reads `0x05880000` three
times unguarded. `regscan` defaults to the same base and `clkfind` watches the
same witness. All three now refuse rather than hang -- deliberately a refusal
and not the ungate teardown got, because they only *measure*, and everything
they measure is driven by the display PLL, so an ungated read with no sequence
run would return a confident number that means nothing.

## What we are deliberately keeping that the vendor does not do

The vendor's teardown is thin because **it only ever tears down on the way to
losing power.** It never re-initialises a panel it just shut down, so it does not
need the hardware left re-initialisable.

Ours does. The whole acceptance test for `h713_disp_teardown()` is that a second
`panel-test` in the same boot renders correctly, which is why we park the MIPS,
restore the PHY and route, and honour the panel's off timings. The vendor's
silence on all three is not a gap in ours -- it is the difference between
shutdown and teardown, and reading it as a gap would have been the wrong lesson.

## Incidental

Three `Invalid pin` errors inside the vendor's display shutdown, and
`mipsloader 3061000.mipsloader: request pins failed: -19` at boot. Its pin
configuration is broken in more places than the pwm5 group already recorded.
And it confirms once more that stock never touches the backlight on the way
down -- so what we do about PB5 in teardown is a decision to make, not a
behaviour to copy.

# The U-Boot frame survives into Linux (2026-08-07)

`panel-test 0x34 vendor-logo-chroma`, then `boot`. **The logo stayed on the
panel through the entire Linux boot, was still there at the login prompt, and
remained after it.** All twelve registers that would have to survive for that to
be true read back their U-Boot values from userspace: `0 of 12 changed`.

Milestone 2b established only that Linux *reaches userspace*, and it passed
before any of the framebuffer fixes existed. This is the first time the picture
itself has been checked, and the two are not the same claim.

## The registers, read from the target

| register | value | what |
| --- | --- | --- |
| `0x058c0014` | `b8002300` | display PLL, N+1 = 36 |
| `0x0525c000` | `02f80550` | mixer H/V total |
| `0x0524c000` | `00fc0202` | DE/OSD control |
| `0x0528008c` | `00000000` | layer X origin |
| `0x05280084` | `02d00500` | layer size |
| `0x05600140` | `03001901` | AFBD control |
| `0x05600170` | `00001400` | AFBD stride |
| `0x05600178` | `6c100000` | AFBD source address |
| `0x05140054` | `40000080` | display route |
| `0x051c0014` | `18000005` | LVDS PHY |
| `0x051c0028` | `1f300030` | LVDS PHY mid |
| `0x05700000` | `fff11111` | TVTOP |

The register read is confirmatory rather than primary: every one of these would
corrupt the image visibly if it moved -- a wrong PLL is the uniform blur that
started this whole investigation, a wrong X origin brings back the band and
shear, a wrong source address shows different content, gated clocks go dark. An
intact picture already implied they held. What the readback adds is the
*absence* of a latent change that has not surfaced yet.

## The dependency worth knowing about

`clk_ignore_unused` and `pd_ignore_unused` are on the kernel command line, and
the boot log confirms both took effect: `clk: Not disabling unused clocks`,
`PM: genpd: Not disabling unused power domains`. Without them the clock
framework would gate the display PLL as an unclaimed clock and the panel would
go dark at exactly that point in boot. **This result depends on them**, which is
not obvious from the outcome and is easy to break while tidying a command line.

Panfrost probed, Cedrus registered, the DRM module loaded and
`systemd-backlight@backlight` ran, and none disturbed the image.
`Console: colour dummy device` -- nothing claimed a console framebuffer.

## What this did not cover

The kernel under test carried the **4 MiB** `uboot-scanout` reservation, so this
validates the front buffer at `0x6c100000` -- the one a boot logo uses. The
8 MiB version covering the `fb-anim-db` back buffer at `0x6c500000` is built but
was not flashed; until it is, that region is ordinary allocatable memory and the
kernel log shows it inside `node 0: [mem 0x6c500000-0x7fffffff]`. A handoff
after a double-buffered run would be allocated over.

## You cannot read MMIO with od or dd on arm64

Recorded because it cost a bench round-trip and looks exactly like a hardware
failure. `read()` on `/dev/mem` is gated by `valid_phys_addr_range()`, which on
arm64 requires `memblock_is_region_memory() && memblock_is_map_memory()`.
Registers are not memory, so every read returns `-EFAULT` -- and a first version
of `handoff-check.sh` duly reported all twelve registers `UNREADABLE` on a
perfectly healthy board.

`CONFIG_STRICT_DEVMEM` *does* permit MMIO, but it governs `mmap()`, not
`read()`. The two were conflated. Only mmap works.

The shipping rootfs had no `busybox`, no `devmem2` and no `python3`, so nothing
on the target could do it at all. Two fixes: `tools/display/devmem32.c` is a
freestanding aarch64 reader, no libc and about 3 KB, which is small enough to
base64 onto the board over the serial console when there is no network -- that
is what produced the table above. And `busybox` is now in the rootfs package
list so the next session just has `devmem`.

The guard that made this cheap rather than expensive: the script refused to
report a pass when reads failed, and said the result meant nothing until access
was fixed. A tool that had printed twelve zeros and compared them unequal would
have looked like twelve register faults.

# Double buffering fixes the tear, and the obvious metric measured the camera (2026-08-07, test_37)

`fb-anim` against `fb-anim-db` on one boot, filmed at 4K30
(`local/lcd-photos/test_37/`). Analysed with `tools/display/tear-measure.py`.

| | rows with **no bar** |
| --- | --- |
| `fb-anim`, single-buffered | median **5.97 %**, mean 5.41 %, worst 11.12 % |
| `fb-anim-db`, double-buffered | median **0.00 %**, mean 0.15 %, worst 4.95 % |

55 and 54 frames respectively. **More than half of all double-buffered frames
are perfectly clean.** The fix works.

## Why "rows with no bar" is the right observable, and the step is not

The instinctive metric is the size of the horizontal step in the bar. It is
worthless here, and two runs were spent finding that out.

A 30 fps rolling-shutter camera against a 59.75 Hz panel sees **about one
panel-frame boundary cross the sensor per readout**, so a 16 px step appears in
essentially every camera frame whether or not the panel tears. Measured that
way the two videos are indistinguishable -- largest step, median 5.88 px against
6.03 px, worst 14.73 against 13.51. That is not evidence of no difference; it is
the camera's own sampling artefact swamping the signal, and reporting it as a
verdict would have been the luminance mistake again in a new costume.

What the camera *can* see is a row carrying **no bar at all**. Rolling shutter
shifts the bar; it cannot delete it. The single-buffered fill blues the whole
surface and draws the bar afterwards, so a raster passing through mid-fill finds
no bar anywhere on those rows -- and the console already reports how long that
window is.

**The prediction was there before the measurement.** The fill is 1.95 ms of a
16.75 ms frame, so about **11.7 %** of rows should lose the bar. Measured 5.97 %
median, 11.12 % worst. The shortfall is the camera's exposure integrating over
part of a frame, so a row that lost the bar for only part of its exposure still
records some red; 5.97 % is therefore a lower bound on a fault predicted at
11.7 %. Right order, right sign, and it goes to zero when the cause is removed.

## What this also settles

The flip assumed the AFBD source address at `0x05600178` is shadowed in hardware
and latched at the ready write. **It is.** Had AFBD been re-reading the address
mid-scan, pointing it at a different surface each frame would have torn at least
as badly as the single-buffered case, not cleared it to a 0.00 % median. The
vblank-write fallback recorded as the alternative is not needed.

## Method note

Three metrics were tried. The first was confounded by the bar wrapping -- rows
where the bar sits at both screen edges averaged to a centre in the middle of
the screen where there is no bar, producing "steps" of 400 px and a
peak-to-peak of 2032 px on a 1280 px panel. Numbers that absurd are a broken
instrument announcing itself, and the fix was to accept only rows containing
exactly one contiguous red run.

The second was correctly measured and still meaningless, because it measured the
camera. The third works because it is specific to the fault's mechanism rather
than to its appearance, and because its magnitude was predicted from timing the
console already prints. **Prefer an observable the fault must produce over one
the fault merely looks like.**

# Sustained commits work, completion is vsync-locked, and the path tears (2026-08-07, fb-anim)

First animated test signal in this bring-up. 600 frames, a 64 px red bar on blue
stepping 16 px/frame, committed continuously.

```
H713 anim: complete after 600 frame(s) in 10042 ms
H713 anim: committed 600, timeouts 0 -- sustained commits OK
H713 anim: commit wait min/mean/max 6800/14620/14800 us; fill min/mean/max 1949/1954/1969 us
```

## 1. Sustained commits work -- 600/600, no timeouts

The open worry was that `h713_disp_commit_osd_frame()` hand-manages what stock
does in an IRQ handler, and that without an ARM IRQ handler the old completion
would remain pending forever. At most six chained commits had ever been run.

**600 committed, zero timeouts.** The manual write-one-to-clear of the channel-1
IRQ status before each submission is sufficient; nothing accumulates. The
missing ARM IRQ handler is not a blocker for sustained single-buffer output.

## 2. Completion is vsync-locked -- established, not suggested

The old note said observed waits of 600..16400 us "suggest vsync-locked
completion but do not establish it". 600 samples settle it two independent ways:

| quantity | value |
| --- | --- |
| 600 frames in 10042 ms | **16.7367 ms/frame = 59.749 Hz** |
| panel timing, computed from the PLL | 16.747 ms = **59.71 Hz** |
| fill mean + wait max (1.954 + 14.800) | **16.754 ms** |
| frame period | **16.747 ms** |

The achieved rate matches the panel's computed refresh to **0.07 %**, and
fill-plus-wait matches one frame period to **0.007 ms -- 0.04 %**. The commit
does not return until the raster reaches its completion point, so the wait is
exactly "the rest of the frame after the fill". That is what vsync-locked means,
and it is now a measurement rather than an inference.

The `min` of 6800 us is the first frame, which starts at an arbitrary raster
phase. Every subsequent frame lands in the 14700..14800 us band.

## 3. The path is single-buffered, and it tears

**Operator observation: the bar is broken during motion, and complete top to
bottom once the animation stops.**

That is tearing, and it is the expected consequence of what this path is: the
AFBD streams live from `0x6c100000` during scanout while the CPU rewrites the
same buffer. The fill takes 1.954 ms of a 16.747 ms frame -- about 12 % of the
frame height -- and it begins immediately after the previous commit completes,
so it races the top of the new scanout. The last frame is never overwritten,
which is why the static bar is whole.

**This also tells us the commit does not latch or snapshot the surface.** Had
AFBD captured the frame at submission, rewriting the buffer afterwards could not
have torn it. It streams.

Two consequences worth carrying forward:

- **A static boot logo is unaffected.** Nothing in the shipping use of this path
  animates, which is why this never showed up before.
- **Anything animated needs double buffering**, and the lever exists:
  `0x05600178` is the AFBD source address, already known and already carrying
  `0x6c100000`. Write a second surface, point that register at it, then commit.
  Since completion is vsync-locked (section 2), the flip lands on a frame
  boundary and the tear goes away. That is the next piece of work, and it is now
  a well-specified one rather than a worry.

## Method note

The instrument was designed so a pass and a failure both measure. It returned a
pass on its primary question *and* two facts nobody asked it for -- the refresh
lock and the tear -- because it reported fill and commit-wait separately instead
of a single frame time. A single "frames per second" number would have shown
59.7 Hz and hidden both.

Deliberately not decoded video, for the reason recorded when it was built: a
decoder would have contributed its own buffers, format conversion and timing, so
the tear would have had five candidate causes instead of one. Video is the
integration test now that this is the reference.

# Project 0x34 renders exactly as 0x33, and the delta is one register (2026-08-06)

Booting the vendor stack established that this board selects project id **0x34**
(`Project id:0x34 version:25-1-6-3`, then `mips/ProjectID_0x0034.TSE`), while
every bring-up run in this project has used `panel-test 0x33`. That put a
question mark over the whole display log: if 0x34 drove different tables, no
0x33 result described the vendor's behaviour.

**It does not. Every 0x33 result stands.** Predicted statically, then confirmed
on hardware in a back-to-back A/B.

## The blob analysed is the blob the board runs

`LogoRegData.bin` word 1 is a packed version: `[31:24]` year, `[23:20]` month,
`[19:12]` day, `[11:0]` build. `local/mips-display/board-b-mips/LogoRegData.bin`
carries `0x1940a09d` -> **25-4-10-157**, which is exactly what the vendor
firmware printed on the bench. So the static analysis below and the hardware run
are about the same bytes.

Do **not** analyse against `local/mips-display/research/bootloader_fat/` or the
board-A capture. Both are `0x18603052` -> 24-6-3-82, 13 descriptors, `0x382c`
bytes -- and DE block 6 (`0x361c..0x39a4`) runs off the end of that file.

## The two ids share everything except the DE block

Board B's table carries 15 descriptors:

| project | prologue | timing | de |
| --- | --- | --- | --- |
| 0x33 | 3 | 6 | **5** |
| 0x34 | 3 | 6 | **6** |

Prologue and timing are shared outright, so the display PLL, the LVDS lane map,
the panel timing and every `h713_disp_panel_patch` site outside the DE block are
bit-identical between the two. Only the DE/mixer table differs.

Walking both DE blocks with `h713_logo_walk`'s exact framing rules gives 55
records for block 5 and 56 for block 6, differing in **four**:

| register | de5 | de6 | after our patch |
| --- | --- | --- | --- |
| `0x0525c004` | `00001003` | `00000404` | both -> `00001402` |
| `0x0525c01c` | `05000054` | `05000014` | both -> `0500003c` |
| `0x0525c034` | `05000054` | `05000014` | both -> `0500003c` |
| `0x0525c038` | *absent* | `00000040` | **not patched -- survives** |

Three of the four sit at sites the patch table overwrites and converge on the
same value. The fourth is `H713_DISPLAY_MIXER_CTRL_REG`, which our sequence
writes `0x100` to before the DE walk; under 0x34 the vendor's own table
overwrites that with `0x40` immediately afterwards.

**So the entire predicted difference was one register.**

## The hardware agrees, to the offset

`panel-test 0x33 vendor-logo-chroma` then `panel-test 0x34 vendor-logo-chroma`,
same boot, teardown between (the second run tore down first, as designed).

| observable | 0x33 | 0x34 |
| --- | --- | --- |
| triple | prologue 3, timing 6, de 5 | prologue 3, timing 6, de 6 |
| patched / guarded | 22 / 12 | **22 / 12** |
| DE records applied | 55 | **56** |
| `0x0528008c` | `7b -> 0` at `+0x3584` | `7b -> 0` at `+0x390c` |
| `0x0525c038` | `00000100` | **`00000040`** |
| fbcheck | rows 343..378, cols 367..912 | **identical** |
| panel | legible logo | **no visible difference** (operator) |

All eleven DE-block patch offsets landed where the static walk put them, and
both differing pre-patch values appeared as predicted -- the console shows
`00000404 -> 00001404 -> 00001402` under 0x34 against
`00001003 -> 00001403 -> 00001402` under 0x33.

**A corollary worth keeping.** Our explicit `writel(0x100, 0x0525c038)` ahead of
the DE walk is **not load-bearing**: 0x34 overwrites it with `0x40` and the panel
renders identically. Whatever that field selects, it does not change the output
in this configuration.

## Two differences this run cannot explain

Recorded because they are real, not because they mean anything yet.

- **`afbd-mux +0x20` moved**: `4c5ee000 4cbeb000` -> `4c7ed000 4cdea000`, both by
  exactly `+0x1ff000`. These are firmware allocations and they differ in the
  *first* dump, i.e. after the MIPS read the TSE, so the smaller
  `ProjectID_0x0034.TSE` plausibly drives a different buffer layout. The shift is
  not the TSE size delta (`0xa80`), so that is inference, not a finding.

  > **Refuted the same day. It was the TSE load order, not the project id.**
  > Re-running 0x34 with stock's order returns `4c5ee000 4cbeb000` -- the values
  > 0x33 produced. Same id, same TSE files, only the placement changed. The
  > guess above named the right cause family and the wrong member, which is what
  > "inference, not a finding" was there to flag. See the section below.
- **`ready=00000000` vs `ready=00000001`** on the commit line, with `wait=5700us`
  against `4700us`. One sample each, against an observed commit-wait range of
  600..16400 us, so this is not separable from sampling. Still unresolved: the
  vendor-order run reads `ready=00000000` at `wait=9700us`, a third distinct
  pair, which is what sampling noise looks like.

Neither changed the render. `0x05880000` and the `scan=` values also differ, and
those are the free-running counter doing what it always does.

## Our TSE load order does not match the vendor's

Visible for the first time from the vendor's own bench log, and unrelated to the
project id:

```
vendor:  database -> pq_custom -> projecttable -> ProjectID
         0x4be41000  0x4be85f60   0x4be89a08     0x4be89f70
ours:    database -> projecttable -> ProjectID -> pq_custom
         0x4be41000  0x4be85f60     0x4be864c8   0x4be8a860
```

Both sets of addresses are confirmed -- the vendor's from its fastlogo log, ours
from today's console. `h713_disp_load_tse()`'s comment says "project file last",
which is what the **vendor** does and what our code does not.

Each blob is self-describing (`TSE` magic, a type byte -- database `0x00`,
ProjectID `0x02`, pq_custom `0x05`, projecttable `0x06` -- and, for three of the
four, an accurate total size at `+0x12`), and `ProjectID_0x0034.TSE` carries
`34 00` at `+0x0e`. That supports the MIPS chaining on the headers rather than on
placement, which would make the order harmless. **It is not proof**, and the
display path would not expose it either way, since the ARM's LogoRegData replay
is what renders.

**Changed to the vendor's order and confirmed on hardware the same day.** All
four addresses now print byte-identical to stock's -- `0x4be41000`,
`0x4be85f60`, `0x4be89a08`, `0x4be89f70` -- and every readiness observable
passes: `status=0x00000001`, `firmware execution proven`,
`CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005`,
`firmware readiness proven by MIPS READY`, `application readiness proven`, plus
the render and `fbcheck` at rows 343..378 / columns 367..912.

**And it was not cosmetic.** The `afbd-mux` addresses the previous run could not
explain move with the order:

| run | `afbd-mux +0x20` |
| --- | --- |
| 0x33, old order | `4c5ee000 4cbeb000` |
| 0x34, old order | `4c7ed000 4cdea000` |
| 0x34, **stock order** | `4c5ee000 4cbeb000` |

Same project id, same TSE files, only the placement changed -- so **the old
order perturbed the firmware's own allocations.** "Probably harmless" was too
generous; what is true is that it changed firmware behaviour without breaking
the display.

The mechanism is visible in the layout. Our old order put the **variable-sized**
ProjectID file third, so `pq_custom.TSE` landed at `0x4be8b2e0` under 0x33 and
`0x4be8a860` under 0x34 -- a shift of exactly `0xa80`, the ProjectID size delta.
Stock puts the fixed-size databases first and the variable file last, so every
fixed blob has a stable address whatever project is selected. That is very
likely *why* stock orders them that way, and our order defeated it.

This does not establish that the MIPS parses by placement rather than by header
-- the display rendered correctly under both orders, and the allocation delta
is not itself a fault. It does retire the argument that the order could not
matter.

## Method note

The static pass predicted the descriptor triple, all eleven patch offsets, both
differing pre-patch values, the 55/56 record counts, the 22/12 patch counts and
the one surviving register -- everything the run then printed. That is what a
transcribed vendor table is *for*, and it is the opposite of the failure recorded
below in "The framebuffer fault was our own omission", where the static analysis
was right and got overruled by caution. The difference is that this time the
prediction was written down as numbers **before** the board was powered, so the
run could only confirm or refute it.

# The vendor firmware says the backlight is channel 5, and Linux never touches it (2026-08-05)

Recovered from the retail OTA package,
`~/Documents/projector_firmware/H713 Magcubic projector.20250922.093247/update.img`
(1.9 GB, `IMAGEWTY`, 53 entries). Header layout, derived empirically rather than
guessed: filename at `block+0x24`, stored length `+0x124`, original length
`+0x12c`, offset `+0x134`, blocks of 1024 bytes from offset 1024.

## The vendor kernel has no backlight at all

`vmlinux.fex` is bzip2 -> tar -> a **220 MB ARM 32-bit `vmlinux` with DWARF and
full symbols**: `Linux version 5.4.99-00049-g34f0974adef4-dirty`, built
2025-09-22, `arm-linux-gnueabi-gcc`. Note 32-bit -- our port is arm64.

| probe | result |
| --- | --- |
| `backlight_device_register` / backlight class | **0 symbols** |
| `panel_pwm_ch`, `panel_backlight`, `panel_bl_en`, `panel_pwm_freq`, `panel_pwm_pol` | **0 string references** |
| `Thal_Vp*` / `SetBacklight*` | **0 strings** |
| `pwms =` consumers in the shipping DTB | exactly one -- the CPU regulator on `s_pwm` |
| PWM sysfs (`pwmchip_sysfs_export`) | present |

So stock Android exposes no `/sys/class/backlight`, and the kernel never reads a
single panel backlight property. **Booting the vendor OS to look for a
brightness control would not have answered the question** -- there is nothing in
the kernel to find. That was worth establishing before spending a bench day on
it.

## Stock U-Boot is the only thing that sets the backlight

`u-boot.fex` from the package is **sha256-identical** to
`local/mips-display/board-b-stock/u-boot-stock.bin`, so everything below is
about the real shipping bootloader. It is **Thumb**, load base **`0x4a000000`**
(recovered by matching literal-pool words against known string offsets; all five
probe strings agree).

It contains the whole backlight implementation:

```
pwm_request   sunxi_pwm_pin_set_state   Pwm enable fail:%d   backlight enable fail:%d
Create backlight instance fail!   Display fastlogo finish!
Error backlight parameter:pwm_ch:%d pwm_freq:%u max_duty_ratio:%d min_duty_ratio:%d
```

And it has **two parameter sources**, which is where this project's long-running
"channel 2 or channel 5" contradiction actually comes from -- both are real, in
one binary:

| source | keys | literal pool |
| --- | --- | --- |
| `panel_config.ini` `[PWMSetting]` | `pwm_channel` `pwm_freq` `pwm_polarity` `pwm_min` `pwm_max` `default_backlight` | `0x23bec`..`0x23c18` |
| device tree | `panel_pwm_ch` `panel_pwm_freq` `panel_pwm_pol` `panel_backlight` `panel_pwm_min` `panel_pwm_max` | `0x23c20`..`0x23c34` |

Both branches populate the same registers and converge on the same
backlight-create call at `0x4a0255a0` (the DT branch literally jumps into the
INI branch's tail at `0x4a023ae0`). The selector is at **`0x4a0239e0`**:

```
ldr r0, [pc, #0x210]   ; -> "pwm_freq"        (the INI key)
bl  0x4a0258ec         ; ini_get()
cmp r0, #0
bne 0x4a023a8e         ; found -> INI branch
ldr r1, [pc, #0x20c]   ; -> "Get pwm freq fail!"
b   0x4a023a50         ; else -> log and abort
```

Board B's `panel_config.ini` has `[PWMSetting]` with `pwm_freq = 40000` and
`pwm_channel = 5`, which for a while looked like it settled the question in
favour of channel 5. **It does not, and the shipping DTB overrules it.**

## The shipping DTB settles it: channel 2, and channel 5 is unroutable

`sunxi.fex` from the OTA package -- the device tree the retail unit actually
boots -- carries a complete, self-consistent backlight configuration:

```
panel_pwm_ch   = <0x02>      channel 2
panel_pwm_freq = <0x61a8>    25000 Hz
panel_pwm_pol  = <0x00>      active high
panel_backlight= <0x4b>      75
panel_bl_en    -> PB5
```

and pin groups for **pwm0..pwm4 only**. `pwm5` has a controller node
(`pwm5@2000c15`) and **no pin group anywhere in the file**. Stock calls
`sunxi_pwm_pin_set_state`, which needs one, so channel 5 can never be muxed on
the retail unit.

Therefore stock either uses channel 2 -- matching that DT block exactly -- or
asks for channel 5 and fails. **Either way the only configuration stock can
successfully apply is channel 2 / PB4 / 25 kHz / active high**, which is exactly
what this project has now run with a hardware-verified counter, and which does
not change brightness.

`panel_config.ini` appears to be a vendor build artifact rather than a runtime
input: our own bring-up loads `display.bin`, `display_cfg.xml` and the `.TSE`
files from `mmc 1:2` and **never loads `panel_config.ini`**.

**Booting stock is therefore unnecessary** -- the shipping DTB answers the
question that boot was meant to answer. `docs/flash.md` "Method 5" is retained
for the eMMC-layout facts it records, but its premise turned out false (stock's
boot package is not present at any sector `boot0` references) and it should not
be run without a real backup and a better reason.

**Method note, worth keeping.** The channel question flipped twice in one
session because the reasoning kept starting from board-A and board-B
*development* trees. The shipping DTB is the artifact that governs the retail
unit and should have been the first source consulted, not the last.

## Package inventory (what is now available)

Extracted to `local/stock-boot/` (do not commit -- proprietary):

| file | offset | size | magic |
| --- | --- | --- | --- |
| `boot0_sdcard.fex` | 175104 | 32768 | `eGON.BT0` |
| `u-boot.fex` | 207872 | 638976 | `uboot` |
| `boot_package.fex` | 864256 | 1245184 | `sunxi-package` |
| `env.fex` | 145324032 | 131072 | env |
| `sunxi.fex` | 68608 | 73728 | `d00dfeed` |

Also in the package and not yet extracted: `boot.fex` (64 MB Android boot),
`super.fex` (1.6 GB), `vendor_boot.fex`, `dtbo.fex`, `misc.fex`, `vbmeta*.fex`,
`sys_partition.fex` (the authoritative partition table), `sunxi_gpt.fex`,
`sunxi_mbr.fex`, `arisc.fex`, `boot-resource.fex`.

**There is no full eMMC backup on this machine.** `docs/flash.md` claims one
exists in `local/h713-lab`; it does not, and nothing over 200 MB is there. The
OTA package is now the only source of stock images, which is why it is worth
recording where it came from.

# PB4's pwm2 is mux 3, and that is why every backlight test failed (2026-08-05)

**One transcription error explains both null results, across two years of
tooling and two different software stacks.**

`patches/kernel/0002-pinctrl-sunxi-add-h713-pio-driver.patch` gives PB4 the
`pwm2` function at **mux 2**. It is mux **3**. Three independent sources say so:

| source | PB4 / pwm2 mux |
| --- | --- |
| board B's own stock U-Boot DTB, `pwm2@0 { allwinner,pins = "PB4"; allwinner,muxsel = <0x03>; }` | **3** |
| upstream mainline H616 pinctrl table | **3** |
| patch 0018 | **3** |
| patch 0002 -- *the table the kernel actually binds* | 2 |

Patch 0002 additionally invents `PB4 mux 5 = twi2`, which upstream does not
have. That row is simply wrong.

**What it cost.** The sweep of 2026-08-05 ran with a verifiably correct PWM --
`CLK_CFG=00000080`, `PERIOD=03c003c0 -> 02d003c0 -> 01e003c0 -> 00f003c0 ->
000003c0`, `EN=00000004`, 25 kHz, duty stepping exactly as asked, against a
full-white field on an initialised and rendering panel -- and changed brightness
not at all, because the waveform was driven into a pad muxed to a different
function. The console printed `PB4 mux=2` and that was checked against patch
0002, the same wrong source, so the read-back confirmed the error rather than
catching it.

The Linux `pwm-backlight` run of 2026-07-24 had the identical fault. Its
debugfs line -- `pin 36 (PB4): device backlight function pwm2` -- was true at
the pinctrl abstraction level and wrong at the register level, because the
function-to-mux mapping underneath it is patch 0002's. So the two independent
negatives that made this look like a panel-side problem were one bug, in our own
pin table, seen twice.

**Fixed** in U-Boot: `H713_BL_PWM_MUX` 2 -> 3, rebuilt and verified in the
image. **Patch 0002 still needs the same correction for Linux**, and every
other row in that table is now suspect until checked against board B's stock
DTB -- it is a transcription, and this is the second load-bearing error found
in it.

Retest:

```
h713_disp panel-test 0x33 bl-sweep
```

### Result: the first clean negative, and what is still unverified

Run of 2026-08-05 with everything correct at once, for the first time:

```
PB4 mux=3  BGR=00010001  PCCR=00000000  CTL=00000100
PERIOD=03bf03c0 -> 03bf02d0 -> 03bf01e0 -> 03bf00f0 -> 03bf0000
GATE=00000004  EN=00000004  CNT advancing +176/7us, wrapping at 960
```

Channel 2, PB4, mux 3, HOSC/1, 25.0 kHz proven by the counter wrap, duty
stepping 960/720/480/240/0 against a fixed entire of 960, channel gated,
enabled and demonstrably counting, panel initialised and rendering a full-white
field. **No brightness change at any step.**

Every earlier null had at least one of these wrong, so this is the first result
that is evidence about the panel rather than about our code.

**One thing is still not verified: that the waveform reaches the pad.** The
counter proves the channel generates internally; it says nothing about PB4
itself. The PIO data register cannot answer this -- it reports the output latch,
not the pin, as PC's data register reading `00000000` for an active eMMC bank
shows. The instrument for this is a **DMM on PB4 in DC mode** during the sweep:
at 25 kHz it averages, so 100% reads ~3.3 V, 50% ~1.65 V, 0% ~0 V.

- PB4 tracks duty -> the pin is driven correctly and the panel genuinely ignores
  it. The ARM-side PWM route is then exhausted and the serial-panel-init
  hypothesis of 2026-07-24 is what remains.
- PB4 sits flat -> the waveform is not reaching the pad, and mux 3 vs 2 becomes
  an A/B test with the DMM as the judge.

Do not spend another bench run on register reads before this measurement. Three
separate register-level readings in this session turned out not to mean what
they appeared to -- the enable bit at `0x080`, the PIO data register, and the
`pwm-sun8i` field order -- and the physical measurement is worth more than a
fourth.

**The method point, and it is the same one as `0x0528008c`.** A read-back
checked against the source that produced the value cannot detect an error in
that source. `PB4 mux=2` was printed, read, and approved three separate times.
What was never done until now was to check the mux against the *vendor's* table
rather than ours -- and board B's own stock DTB had been sitting in
`local/mips-display/board-b-stock/u-boot-stock.bin` the whole time, with the
answer in it.

Two further corrections fell out of reading it:

- Board B's `lcd1@1` node gives `panel_pwm_ch = <0x02>` and `panel_bl_en` on
  PB5, confirming channel 2 and PB4 from **board B's own** device tree. Every
  earlier citation of `panel_pwm_ch = 2` in this log came from board A's
  `tv303` DTB and was a cross-board inference.
- Board B's `panel_backlight` is `<0x64>` = **100**, not board A's `<0x4b>` =
  75. Commit `7b0a75f` set our DT to 75 from board A's capture.

`panel_config.ini`'s `pwm_channel = 5` remains unexplained and now
*contradicts* board B's own DTB. Its comment reads `#map to hardware PWM
channel 0~7`, so it is not a firmware-internal index. Board B's DTB has no
pwm5 pin group and defines pin groups only for pwm0/pwm1/pwm2. Treat the INI
field as unresolved rather than authoritative; the DTB is the stronger source
because it names a pin.

# The backlight: the firmware cannot drive it, and the PB4 null was ours (2026-08-05)

Two findings, from one bench session and a disassembly of `display.bin`. The
first stands. The second was **right that our PWM register map was broken and
wrong that fixing it was sufficient** -- see the section above, which supersedes
its conclusion. The register-map analysis below is still correct and still
needed; it simply was not the only fault.

## 1. The firmware HAL backlight route is closed

`h713_disp commcall 51ad877e chan=0 pid=8b8f32b0 64` and the same with `0`
both returned `nret=1 ret[0]=00000001`. Neither number means anything.

**The arguments were not what the handoff intended.** `commcall` parses with
`hextoul`, so `64` is 0x64 = 100 and the pair was max and zero, not 100 and 0.

**The return is a hardcoded constant.** The worker behind
`Thal_Vp_SetBacklightLevel` is at `0x8b148ca4` (file offset `0x48ca4`; the
firmware maps 1:1, MIPS `0x8b100000` = file 0 = ARM `0x4b100000`). It contains
no conditional branch at all and ends:

```
0x8b148d50: addiu $v0, $zero, 1
0x8b148d54: jr    $ra
```

`THal_Vp_SetBacklightWorkMode` (`0x8b148acc`) and `Thal_Vp_SetBacklightPwmInfo`
(`0x8b148b80`) have the identical shape. All three return 1 unconditionally, so
identical returns for different levels were guaranteed before the call was made.

**What the call actually does.** Each worker logs `ENTER` (the strings confirm
it: `'./thal_display_backlight.cpp'`, `'Thal_Vp_SetBacklightLevel'`), packs
`{opcode, arg}` on the stack -- WorkMode 0, PwmInfo 1, Level 2 -- calls
`0x8b106bec`, logs `LEAVE`, returns 1. That dispatcher is a C++ virtual call:

```
lw   $v0, 0x3570($v0)   # service pointer at 0x8b253570
beqz $v0, ->return 0    # NULL: silently do nothing
lw   $v1, ($v0)         # vtable
lw   $t9, 0xc($v1)      # slot 3
jr   $t9
```

Slot 3 (`0x8b106a70`) calls `0x8b15c460` -- a queue send whose third argument is
a timeout, `-1` meaning block -- with **0**. So the HAL call is a *non-blocking
post to another thread*, and it reports success before the message is dequeued.
The vtable is at `0x8b1eb07c`, immediately preceded by the RTTI names
`7IThread` and `10CAppBottom` and the module string `app_bottom`.

**And the consumer cannot reach the hardware.** An exhaustive effective-address
scan over all 240,266 instructions finds **zero** loads or stores resolving into
`0x02000000`-`0x02002000` -- no PIO, no PWM, no CCU. The scan was run twice, the
second time preserving callee-saved registers across `jal` so a base held in
`$s0`-`$s7` could not hide. All 13 `lui 0x0200` sites are constants (12 into
argument/temp registers; spot checks show them in `jal` delay slots, passing
0x02000000 as a value). The only MMIO the firmware touches is display blocks --
`0x0500`, `0x0504`, `0x0508`, `0x050c`, `0x0514`, `0x051b`, `0x051c`, `0x0520`,
`0x053e`, `0x0555`, `0xa54f` -- and those are ARM physical addresses, the same
ones we dump from the ARM side, so the peripheral map is 1:1 and `0x02000c00`
would be the PWM for the MIPS too.

Either leg closes it on its own. **`Thal_Vp_SetBacklightLevel` cannot dim this
panel with any argument, and cannot report that it didn't.**

One correction worth keeping, because it is the project's own rule biting: the
static scan found *no writer* for `0x8b253570` and predicted NULL. A runtime
read disproved that -- `md.l 0x4b253540 0x20` shows `8b8ae340 8b89df8c 8b8c8ecc`,
three live service objects. A static write map is a lower bound, never an
inventory. The conclusion survives only because it never depended on that.

## 2. "PWM2/PB4 does not dim this panel" was a test artifact

The pin was right. The code never drove it.

### The stock DTB settles the pin, and it is not channel 5

From the stock U-Boot DTB (`local/mips-display/research/uboot_dtb.dts`):

| property | value | meaning |
| --- | --- | --- |
| `panel_pwm_ch` | `<0x02>` | the panel backlight is channel 2 |
| `pwm2_pin_a` | `pins = "PB4"; function = "pwm2"` | channel 2 is PB4 |
| `panel_backlight` | `<0x4b>` | default brightness 75, not a phandle (0x4b resolves to an SD pinctrl node) |
| pwm5/6/7 | controller nodes only | **no pin group exists for channel 5** |

So `panel_config.ini`'s `pwm_channel = 5` is not a SoC PWM channel, and the rule
this log has carried since 2026-07-29 -- *"Do not return to PB4/PWM2"*, on the
grounds that the INI overrides `panel_pwm_ch=2` -- has been aiming away from the
correct pin. Withdraw it.

This also resolves the parked pinctrl disagreement in patch 0002's favour. The
stock DTB gives PH17/pwm0 muxsel 3, PH18/pwm1 muxsel 3, PB5/pwm3 muxsel 2 and
PA12 = **pwm4**, all matching patch 0002. Patch 0018's `PA12 = pwm5` and
`PB4 = mux 3` are upstream *H616* values and do not apply to H713. (PA12 is a
gmac0 pin on this board in any case.)

### The register map was NOT wrong -- this subsection is retracted (2026-08-05)

**Everything in the rest of this subsection is wrong and was reverted the same
day.** The original map is mainline's `pwm-sun20i-d1`, and it is **proven
correct on this hardware**.

Two pieces of evidence, in order. First, switching to patch 0007's map produced
a full block dump reading `0x02000c40 = 0` and `0x02000c80 = 0` -- under the
`sun20i-d1` map the per-channel CLK_GATE and ENABLE, both clear -- with `CNT(2)`
at `0x02000d48` reading `0`, so the channel was configured but not running.
Under patch 0007's map every field had been set correctly and the counter should
have been counting.

Second, and decisive: with the map reverted, the counter runs. Every sweep step
advanced by **exactly 176** counts across a 7 us window, and the last step
wrapped `0x315 -> 0x005`, i.e. +176 modulo **960**. That fixes both unknowns at
once -- a ~24 MHz count rate, and an entire-cycle count of exactly 960, which is
25.0 kHz. It also confirms the field order directly: `PERIOD = 0x03bf03c0` with
a wrap at 960 means `[31:16] = 959` is **entire - 1**, not an active count.

The evidence originally cited for patch 0007 does not hold. Its "verified from
live hardware" capture, `PERIOD2 = 0x03BF03C0`, is **degenerate**: 0x3bf = 959
and 0x3c0 = 960, so it reads as 25 kHz at ~100% duty under *either* field order.
It cannot discriminate between the two layouts and must never be cited as proof
of one again.

Whether patch 0007 is also wrong for the `r_pwm` instance it was DMM-validated
against is open -- that block may be a different generation. Nothing in the
backlight work depends on the answer.

The counter check is now permanent: `h713_disp_backlight_set()` samples `CNT`
twice per step and prints `counter is static` if it does not move, so a dead
channel can never again be mistaken for a panel result.

Kept below because the reasoning is a good example of how a plausible
cross-check can be degenerate without looking like it.

### (RETRACTED) The register map was wrong in four places

`h713_disp_backlight_set()` did not match patch 0007, the H713 PWM driver:

| | patch 0007 | what we had |
| --- | --- | --- |
| ENABLE | `0x060` | `0x080` -- that is CAPTURE |
| PERIOD fields | `[31:16]` active, `[15:0]` entire | `(period-1)<<16 \| duty` -- inverted |
| pair clock gate | CLK_CFG `BIT(7)` | mask `0x18f`, which **clears** bit 7 |
| CTL | ACT_HIGH `BIT(1)`, CLK_SRC_EN `BIT(5)` | `BIT(8)`, an undefined bit |
| `0x040` | dead-zone control | used as a clock gate |

Patch 0007's map is hardware-validated twice: the CPU DVFS regulator runs on the
same driver and the same `allwinner,sun50i-h713-pwm` compatible and was
DMM-checked across 480..1416 MHz, and the driver carries a live capture of this
very channel, `PERIOD2 = 0x03BF03C0` -- entire 960 (25 kHz), active 959 (~100%
duty), which is the stock backlight state and matches a lit panel at full
brightness. Caveat: the DMM validation exercised the `r_pwm` instance at
`0x07020c00`, not the main block; same driver and compatible, but the transfer
is inference.

### The parked run's own numbers explain its null

Re-reading the values that run logged, under the validated field order:

| asked | register written | what the hardware had |
| --- | --- | --- |
| 100% | `0x03bf03c0` | 99.9% duty at 25.0 kHz |
| 75% | `0x03bf02d0` | active 959 >= entire 720 -- saturated, stuck on |
| 50% | `0x03bf01e0` | active 959 >= entire 480 -- saturated, stuck on |
| 25% | `0x03bf00f0` | active 959 >= entire 240 -- saturated, stuck on |
| 0% | `0x03bf0000` | entire 0 -- reads as never configured |

Every step was either ~100% duty or saturated on. Never anything dimmer. And
`EN=00000004` was read back from `0x080`, the capture register the enable bit
was written to -- the real ENABLE at `0x060` was never touched, and `CTL=0x100`
set neither polarity nor the pair clock. **The channel was never enabled**, and
"no brightness change at any step" is precisely what that configuration
produces. The reconstruction reproduces all five logged words exactly.

### Fixed -- but do not expect this to be the whole answer

`h713_disp_backlight_set()` now writes CLK_CFG gate, `(active << 16) | entire`,
`CLK_SRC_EN | ACT_HIGH`, then ENABLE at `0x060`. The read-back guard now tests
this channel's bit rather than the whole register, which any other enabled
channel would satisfy. Retest with:

```
h713_disp panel-test 0x33 bl-sweep
```

Six steps, 100/75/50/25/0/100 at four seconds each against a full-white field.

**There is a prior correct-map negative, and it must not be forgotten.** Patch
0007's map was corrected in `aebd67a` on 2026-07-21, three days *before* the
Linux bench test of 2026-07-24. That test drove PB4 through the kernel
`pwm-backlight` path with debugfs showing duty scaling 0/20000/40000 ns for
brightness 0/50/100, `actual == requested`, pinmux `pin 36 (PB4): function
pwm2` -- and the panel did not change. So it was a valid test of a correctly
programmed PWM, and it still came back null.

What separates the two runs is the panel:

| run | register map | panel state | result |
| --- | --- | --- | --- |
| 2026-07-24, Linux | correct | **not initialised** (display path did not work until 2026-08-04) | no dimming -- valid null |
| 2026-08-05, U-Boot | **wrong** | initialised and rendering | no dimming -- void, channel never enabled |
| next | correct | initialised and rendering | **never yet tested** |

That third row is the whole point of the retest. The standing hypothesis from
2026-07-24 -- that the panel's LED driver ignores PWM until its own serial init
has run, and stock fastlogo runs that init before Linux -- survives untouched
and is still the best explanation if the sweep comes back null again. What has
changed is that the panel now *is* initialised, so the hypothesis is finally
testable, and the instrument driving it is finally correct.

### The method point

The parked result was not a measurement failure and not a wrong pin. It was a
correct measurement of an instrument that had been misconfigured in a way its
own read-back could not reveal -- because the read-back read the same wrong
addresses the writes went to. The previous session added a read-back precisely
to catch a dead instrument, and it did catch the gated block; it could not catch
a wrong register map, because every value read back exactly as written.

A read-back proves writes land. It does not prove they land *somewhere useful*.
When a null result rests on one, check the map against an independently
validated consumer of the same block before recording the null.

# PWM2/PB4 verifiably does not dim this panel (2026-08-05) -- SUPERSEDED

**Superseded by the section above.** The null recorded here is real as an
observation and wrong as a conclusion: the pin is correct and the PWM register
map was not, so the channel was never enabled. Kept for the register captures,
which are what proved it.

The parked result -- "a running 25 kHz PWM on PB4 changed brightness not at
all" -- now stands on evidence it never had. It took two runs to get there, and
the first was worthless.

## Run one was a null from a dead instrument

Every PWM register read back zero:

```
CTL=00000000 PERIOD=00000000 EN=00000000
```

The PWM block is gated and held in reset out of cold boot and nothing in the
display path ungates it, so every write went nowhere. CCU 0x7ac carries both:
BIT(0) is bus-pwm's gate, BIT(16) is RST_BUS_PWM.

Only the register read-back caught this. Without it the run would have read as
"PWM drives the panel and nothing happens", which is the conclusion the parked
note already recorded -- and possibly for the same reason.

## Run two: the instrument is on, and the answer is still no

```
BGR=00010001   gate and reset both released
CTL=00000100   bit 8 active-high, prescaler 0
PERIOD=03bf03c0 -> 03bf02d0 -> 03bf01e0 -> 03bf00f0 -> 03bf0000
EN=00000004    channel 2 enabled
```

960 cycles a period from the 24 MHz HOSC, so 25 kHz, duty tracking 100/75/50/
25/0 exactly as asked, against a full-white field, with the panel initialised
and rendering. No brightness change at any step.

Everything about the configuration matches the stock runtime DTB's tvtop panel
block: channel 2, PB4 at mux 2, 25 kHz, active high. The mux is the value from
the h713 pinctrl driver our DT actually binds, and the vendor DT independently
supports it by giving pwm3 on the neighbouring PB5 muxsel 2.

## So what is left

The panel is lit and rendering, so the light engine is on and something is
driving it. PWM2 is provably not that something, on this board, in this state.

The next candidate is the firmware. Its HAL exposes
`Thal_Vp_SetBacklightLevel` (0x51ad877e) and `Thal_Vp_SetBacklightPwmInfo`
(0xb46ce545), CPU_COMM works, and `commcall` already passes parameters --
`p[n++] = hextoul(argv[k], NULL)`. That needs no new code, only a run with the
MIPS left alive.

Note also that PB5, which the DT calls panel_bl_en and warns is shared with fan
power, is only ever driven by h713_disp_panel_control_test. Nothing in the
normal display path touches it, so during the sweep it sat wherever boot left
it.

## The method point

Two runs, and the difference between them was one register read-back. A test
that cannot tell "the thing I am driving is off" from "the thing I am driving
does not work" produces the same output either way, and this bring-up has now
been caught by that pattern four separate times: the dark panel that was a load
ordering bug, the ERROR-only log that was a source_id, the blank vendor logo
that was neither of the things proposed, and this.

# Teardown works, and the power-cycle rule is retired (2026-08-04)

`panel-test 0x33 vendor-logo-chroma` twice in one boot. The second run tore down
first and rendered correctly -- both chroma markers and the red SMART PROJECTOR
on blue. That is task 2's acceptance test, met.

```
H713 teardown: second run this boot, tearing down first
H713 teardown: panel down (PF_DAT=00000000 PH_DAT=00000000), PHY 18000000/00000030,
               route 40000000, MIPS reset=00000000
```

PF6 low, PH16 low, LVDS PHY and display route back at the cold values every
probe in this bring-up records, MIPS reset asserted -- `0x00000000` is the
asserted state, per `H713_MIPS_RESET_ASSERTED`.

The second bring-up then re-ran the whole sequence and re-reached `firmware
execution proven`, `CPU_COMM magic=deadbeef/deadbeef` and `application readiness
proven`. It could not have re-released the MIPS from an unrecoverable state.

## What the rule actually was

"Power-cycle between every run" was never a property of the hardware. It was the
absence of a teardown. Every mode ended by abandoning the panel powered and the
MIPS in reset, so the next run initialised into a torn-down state and stayed
dark behind a console that looked perfect.

The mechanism is visible in the teardown line. The bring-up powers the panel by
driving PF6 high and pulsing PH16; with the panel still powered from the
previous run, that "power on" was a no-op and the panel never re-ran its own
init. Dropping the rail properly is what makes a second bring-up behave like a
first.

That rule cost at least four results in this project -- two recorded in the
handoff, plus the vendor-logo runs where a dark panel was chased as a
framebuffer fault while `fbcheck` was simultaneously proving the framebuffer
correct.

## Scope

Implemented ARM-side, because the firmware cannot do it: `THal_Vp_Deinit` was
tested and changes four words inside AFBD, leaving LVDS, the PHY, the display
PLL, the mixer and the DE byte-identical.

Order is stop scanout, park the MIPS, signal off, then the panel rail -- the
general LVDS rule of signal before VCC, because that is the part with real
hardware risk.

Two deliberate gaps, both commented in the source:

- **The backlight is not touched.** Which PWM drives it is unresolved:
  `display_cfg.xml` says channel 0, `panel_config.ini` says channel 5, and the
  dimmer we implemented drives PWM2 on PB4, matching neither. Correct ordering
  puts backlight off *first*, so this wants revisiting once that is settled.
- **The PLLs and mod clocks are left running.** Disabling a clock while
  something still reaches for the block is the documented way to wedge this
  interconnect, and the bring-up rewrites that state absolutely. The acceptance
  test passes without touching them.

The off-timing *assignment* -- Off0 after signal, Off2 between reset and power,
Off1 as discharge -- is symmetry with the confirmed on-side mapping, not
knowledge. It works. That is not the same as being right, and the source says
so.

## Consequence

Repeatability testing just got cheap: what needed five power cycles now needs
one boot.

# The firmware HAL is not a teardown lever (2026-08-04)

CPU_COMM calls work. They just do not do what task 2 needed.

## What was tested

Three argument-free routines, on a live firmware with the panel lit and the MIPS
left running (`h713_disp panel-test 0x33`, which proves readiness and does not
quiesce):

```
commcall a30d4c6b   THal_Vp_EnableBlackScreen   clean round trip, nret=0
commcall b66041d8   THal_Vp_DisableBlackScreen  clean round trip, nret=0
commcall eaaa24c9   THal_Vp_Deinit              CALL_ACK + RETURN, nret=0
```

The protocol is proven: published, CALL_ACK, RETURN, ReturnCmd queued and
consumed, FreeReturn recycled, ring advancing correctly across calls. That
capability is real and reusable.

## Why it does not help

**The black-screen calls have no visual effect at all.** The firmware's own log
said why, before we ever called them:

```
I/crtc (crtc_cfg/crtc_cfg.cpp 192) panel crtc is NOT enabled!
I/crtc (crtc_ctrl/crtc_base.cpp 37)  crtc is NOT eabled !
```

The firmware never enables its own CRTC in our configuration. We light the panel
from the ARM side -- LogoRegData replay into DE/mixer/AFBD/LVDS, plus our own
frame commits. `THal_Vp_*` is the video-processing HAL, and with its CRTC
disabled and no source bound, blanking its video window changes nothing.

**`THal_Vp_Deinit` changes four words, all inside AFBD:**

```
0x05600058  00000000 -> 00000045
0x0560005c  00000000 -> 0000003a
0x05600300  00800210 -> 00804218   (xor 00004008)
0x05600304  00800000 -> 00804000   (xor 00004000)
```

LVDS, LVDS PHY, display PLL, mixer, DE, de-layers, vblender, tvtop,
display-route and disp-modclk are byte-identical before and after. It stops no
clock, disables no PHY, blanks nothing. The panel stays lit.

**And it is a one-way door within a boot.** After Deinit the RETURN_ACK
publication went unconsumed for 100 ms and the tooling preserved unreconciled
ReturnCmd and FreeReturn state -- the firmware's low-level handler stopped
servicing the protocol. So Deinit does tear something down: its own messaging,
not the display.

## The conclusion, and the cost of not having it earlier

Teardown has to be implemented ARM-side, exactly as first scoped. The firmware
is not the owner of the path we light, so its HAL cannot release it.

Worth being precise about what the detour bought, because it was not nothing:
CPU_COMM calling is now proven for argument-free routines, the full call table
is documented, and the reason the firmware cannot help is understood rather than
assumed. But the register route was the answer from the start, and the signal
that would have said so -- "panel crtc is NOT enabled!" -- was sitting in the
first good firmware log, read and not acted on.

## Diffing dumps

The four-word result came from diffing two `h713_disp dump` outputs
programmatically rather than by eye. On dumps this size that is not optional:
the changed words were four out of several hundred, three of them differing in a
single nibble, in a block that also contains a free-running counter that changes
every read.

# The firmware talks, and it exposes a teardown HAL (2026-08-04)

`h713_disp test 0x33 1` produced the first full firmware narrative. The command
already existed; what was missing was the **source id**.

## The logger was never the problem

`h713_disp test` defaults `source_id` to 2 (Image). The file default is 1
(VideoDecoder). With 2 the firmware logs

```
E/src_mgr [17] (./source_manager.cpp 200)Can not find device for channel: 0x00000002
```

and abandons most of init, so the ~2.6 KB ring only ever held the tail errors.
Two runs were spent concluding that ERROR was a compile-time ceiling and that
`elog_i()` had been compiled out. **That was wrong.** With `source_id=1` the log
is full of `I/` and `W/` lines. Always pass the source: `h713_disp test 0x33 1`.

The lesson is the same one this log keeps recording: a null result was read as a
property of the system when it was a property of how we had configured it.

## What the full log shows

**TSE loading works, and task 13 was probably a false alarm.** The firmware
reads a run of headers -- types 0,1,3,4,5,6,2,5 -- and loads groups
(`SYSTEM_INIT_SOC`, `V_PANEL`, `ProjectID_0x0033` with 4 modules, `UI_Feature`,
`PQ`, ...). The `magic code incorrect` error fires *after* the last good header
and is immediately followed by `Load TSE used:0`, which reads like
sequential-read termination rather than a corrupt blob.

**The memory allocator is being handed nothing**, and this looks like the real
cause of the PQ and gamma failures:

```
I/NO_TAG (./dp_mem_group.c 446)<Memory Allocator> Error:
  p_mem_group->dwAllo[0]:0x4bf42000-0x4d4f3000   RealOffer:0x4bf41000-0x4bf41000
```

It asks for ~25.7 MB and is offered a zero-length range -- at exactly the
`frame_buffer` address `display_cfg.xml` declares. That ties directly to the
unreserved-scanout question.

**A timing discrepancy:** `I/wce_top (WCETop.cpp 431) hs_size:20,
h_back_porch:57`, where our config and patch table use HBP 40.

## The HAL, which changes how teardown should be done

The firmware exposes a CPU_COMM-callable HAL, and the names are in the binary:

| module | entry points |
| --- | --- |
| `thal_display_misc.cpp` | `THal_Vp_Init`, **`THal_Vp_Deinit`**, `THal_Vp_EnableBlackScreen` / `Disable`, `THal_Vp_EnableVideoFreeze` / `Disable`, `THal_Vp_EnableScreenCover` / `Disable`, `THal_Vp_SetBrightness` |
| `thal_display_backlight.cpp` | `THal_Vp_SetBacklightWorkMode`, **`Thal_Vp_SetBacklightPwmInfo`**, **`Thal_Vp_SetBacklightLevel`** |
| `crtc_ctrl/crtc_base.cpp` | `swpll_stop`, `swpll_start`, `hwpll_stop`, `hwpll_start`, `active`, `crtc is disable` |

So the teardown sequence this project was about to reverse-engineer and replay
as raw registers is **already implemented in the firmware**, and CPU_COMM works
end to end with a `commcall` command and a live 1224-entry call table.

Asking the firmware to blank, drop the backlight and deinit is far safer than
replaying a guessed register order into a panel with power-sequencing
requirements.

`Thal_Vp_SetBacklightPwmInfo` also bears on the backlight question: the firmware
owns the PWM configuration, so the disagreement between `display_cfg.xml`
(channel 0) and `panel_config.ini` (channel 5) may be resolvable by asking it.

## What is still missing

Call ids are **not** a hash of the name -- crc32, djb2, sdbm, FNV and ELF all
fail against the known pair `THal_Vp_GetImageBufferAddr` -> `0x2f02f7dd`. The
name strings are not referenced through a 32-bit pointer table either, so they
are reached by `lui`/`addiu` immediates.

The practical route is therefore the **live call table** (`h713_disp calltable`,
1224 entries) rather than static derivation.

## Dead ends, recorded

- The `debug_buffer` declared at `0x4bd01000` is not where elog writes.
- The 7.6 MB above `0x4b560000` holds only firmware name tables.
- Sync mode produced no console output, so the firmware's UART route is not the
  U-Boot console UART.
- `u-boot.bin` disassembled at base `0x4a000000` puts the cited `0x4a024894`
  inside device-tree strings, so either that base or that binary is wrong for
  the stock-U-Boot addresses this project has been citing.

# The framebuffer fault was our own omission (2026-08-04, test_35)

`h713_disp_panel_patch` transcribes stock's panel-patch sites and left two out:

> Two sites are deliberately omitted. Stock's `0x05280084[31:16]` and
> `0x0528008c[15:0]` both resolve to a literal zero in static analysis, which
> may be a decode artefact rather than a real store; writing a zero we cannot
> justify is worse than leaving the vendor default in place.

The vendor default at `0x0528008c` is another panel's, and it is **123** -- the
pale left band in every framebuffer photograph of this bring-up, and through the
source advance the shear as well. The static analysis was right, the caution was
wrong, and what it lacked was hardware.

Restored and confirmed:

```
+0x3584  0528008c  0000007b -> 00000000  shift 0 mask 0xffff
H713 panel: config applied, 22 record field(s) patched, 12 guarded by record mask
```

`0x0528008c` now reads `00000000` in both dumps **including after the DE
replay**, which previously restored 123, and the backstop stayed silent. Fixed
at source, so no path can miss it -- which matters, because for a day the fix
lived only in panel-test while `auto` still produced the band.

The blob carries one such record per DE block (block 5's at `+0x3584` = 0x7b;
others hold 0x73 and 0x10) -- exactly the "another panel's defaults" the
original comment described.

`0x05280084[31:16]` is still omitted on the same reasoning, holds 720, and is
now *more* suspicious rather than less. It has earned its own two-sided
perturbation.

## A wrong call, and what caught it

The preceding run was read as "the record patch did not take" -- count still
21/12, backstop firing. It had not been flashed yet: the console's own wording
gave it away, since that build printed the older message text. The version
banner said `g937b06f1de16-dirty`, naming the last *commit* while running newer
uncommitted code.

So: trust `-dirty` and the behaviour, not the hash. A stale flash and a failed
patch look identical in the counter and are distinguishable in the prose.

## Config files, read properly at last

Reading the vendor config for the teardown work turned up four things worth
recording:

- **The panel declares its own off-timings.** `PanelOffTiming0/1/2 = 20/250/75`
  against `PanelOnTiming0/1/2 = 20/550/75`. The on-side mapping is already
  confirmed in our code: 550 is the "stock power pre-delay", 20 the wait before
  display clocks. The off-side semantics -- which step each delay separates --
  are still unknown.
- **`display_cfg.xml` declares the firmware's memory map**, and it matches the
  DT reservations exactly: `frame_buffer 0x4bf41000 size 0x1A00000` is the
  `framebuf@4bf41000` node. Our scanout at `0x6c100000` is outside all of it and
  unreserved -- but it is also where the vendor's own LogoRegData points AFBD,
  so there are genuinely two buffers, not one misplaced one.
- **Two PWM configs disagree.** `display_cfg.xml` says channel 0, high-active,
  1.2 MHz; `panel_config.ini` says channel 5, low-active, 40 kHz. We drive PWM2
  on PB4, which matches neither. Polarity alone could explain a dimmer that is
  "HW-correct" and ignored.
- **The firmware has a UART logger we can turn up.** `elog_init_setting` sits at
  level 1 (ERROR) with per-tag overrides available, and `display_cfg.xml` is a
  file on the eMMC FAT that `h713_disp load` exists to let us patch. Raising it
  may answer the shutdown sequence and the pre-run-read fault directly.

# The display bring-up is done (2026-08-04, test_34)

The stock vendor asset renders correctly: legible red "SMART PROJECTOR" on blue,
via `vendor-logo-late` and then `vendor-logo-chroma`, which now share the same
deferred-load path. Legible is the load-bearing word -- a sheared frame smears
those glyphs into diagonals.

## The last fault was the load ordering, not the framebuffer

`vendor-logo` selected a block device, read 2.7 MB off FAT to `0x6d000000` and
hashed it, all between `h713_disp_load()` and `h713_disp_run()`. Moving that work
after init, and changing nothing else, renders the logo.

Five runs were spent before that. The reason it took five is worth recording,
because none of the evidence was missing -- it was all being read as being about
something else:

- every register dump came back **byte-identical** to a run that rendered;
- `fbcheck` proved the framebuffer in memory **correct**, rows 343..378 and
  columns 367..912 against the expected bounds;
- the frame **committed**, AFBD completion bit set.

Three independent signals all said "the framebuffer path is fine", and they were
all true. The conclusion drawn from them -- that the fault must therefore be in
framebuffer scanout -- did not follow. Identical register state cannot produce
different panel output, and that contradiction was visible from the first run.
It should have redirected attention to what the mode did *outside* the dumped
state, which is exactly where the fault was.

The mechanism is unestablished, and the obvious guess is already ruled out:
`h713_disp_load()` reads the same filesystem in every mode, so FAT access before
the sequence is not the problem by itself. What is new is the extra read plus a
SHA-256 over it -- seconds of work and heavy cache traffic in a window where
nothing else does any. `vendor-logo-early` reproduces the break.

## Two controls that came out of it

Both were missing for the whole investigation, and both are now permanent:

- **A refusal on a second `panel-test` per power-on.** Every mode ends holding
  the MIPS in reset, so a second run initialises from a torn-down state: the
  console re-reports success, the dumps come back identical, the panel stays
  dark. Undetectable from the log, and it cost four results before it became one
  line of output. It belonged in the tool, not in a note on this page.
- **A positive control in every mode.** "Nothing on the panel" is unfalsifiable
  without one. The TCON chroma marker reaches the panel without touching the
  framebuffer path, so no blinks means the panel is not lit and nothing
  downstream is being tested. `vendor-logo` never had one.

## Also fixed along the way

`vendor-logo` cannot confirm anything on its own: the stock `bootlogo.bmp` is 99%
black with lit pixels at pure grey, chroma `|R-B|` exactly 0, maximum 0 -- the
one content class this optical path is documented to normalise away.
`vendor-logo-chroma` keeps the file, hash, geometry and `fbcheck` bounds and
swaps only the palette.

A scripted `str.replace` silently missed the pixel loop while landing on the
adjacent `printf`, so one build asserted on the console that the chroma palette
was active while the grey conversion ran. `fbcheck` caught it -- "no matching
pixel anywhere" -- and the message was too soft to be read as the alarm it was.
Both fixed: the edit, and the message.

## Open, none load-bearing

- Why an origin of 123 costs 42 px of source advance per row.
- What writes 123 to `0x0528008c` in the first place. It survives the DE replay,
  so LogoRegData or the firmware.
- Why the extra pre-run read kills the display.

# S = V: there was never a second fault (2026-08-04, test_33)

`fb-fix` was built to test S = V - 42 and find a minimum near register 1322. It
falsified that model instead.

| photo | register | stripes | implied S |
| --- | --- | --- | --- |
| IMG_0626 | 1300 | 11.63 | 1300.7 |
| IMG_0627 | 1310 | 16.18 | 1308.8 |
| IMG_0628 | 1320 | 22.71 | 1320.4 |
| IMG_0629 | 1330 | 27.06 | 1328.1 |
| IMG_0630 | 1340 | 33.30 | 1339.2 |
| IMG_0631 | **1280** (stock) | **0** | **1280** |

**S = V.** `0x05600170` is a plain byte stride and was correct all along. At the
stock 0x1400 the pattern renders as one red/blue boundary drifting **0.0 display
px per row**, full width, no band. IMG_0625, an extra frame before the sweep,
shows the same thing at -0.01 px/row.

So zeroing `0x0528008c` fixed the shear as well as the band. The stride deficit
was a consequence of the origin, not an independent fault.

## The mapping was checked, not assumed

Seven photographs arrived for six steps, and an off-by-one produces a plausible
constant offset rather than an obvious mess -- aligning IMG_0625 to step 1 fits
S = V - 11 across the first five steps quite happily. Only one alignment is
self-consistent: under the other, the stock-register step needs S = 1221 while
its own photograph shows 33 stripes. The consistency check is what distinguishes
them, not the quality of the fit.

## What this says about the previous two days

The stride was measured twice, by experiments sharing no assumptions, and they
agreed on 1237-1238. That agreement was used here as licence to model it as an
independent fault with its own register. It was not.

Both measurements were *correct*. S really was 1238 while the origin was 123.
What was wrong was the causal reading: a number measured downstream of a fault
got promoted to a fault of its own.

That is precisely the error this log recorded on 2026-08-03, when the old "~1187
px/line" turned out to be a content width being used to predict a stride. The
same mistake, one level up, made by the correction. Two independent measurements
agreeing constrains a *value*; it says nothing about what causes it.

The cheap guard that would have caught it: after identifying the origin, predict
what the stride sweep should do *if the two are independent* and check it. The
prediction was in the source (12.4/6.8/1.1/4.5/10.1) and the observation
(11.3/16.9/22.5/28.1/33.8) falsified it on the first photograph.

## Open

- Why an origin of 123 costs 42 px of advance per row. Not understood, and no
  longer load-bearing.
- What writes 123 in the first place. It survives the DE replay, so LogoRegData
  or the firmware.
- The vendor bootlogo on real content: `panel-test 0x33 vendor-logo`, no
  override.

# The left band is 0x0528008c, the layer X origin (2026-08-04, test_32)

Named in one run, and fixed.

| step | written | left pad |
| --- | --- | --- |
| 1 | control (`0x0528008c` = 123) | 119.4 |
| 2 | `0x0528008c` -> 0 | **0.0** |
| 3 | `0x0528008c` -> 400 | **406.2** |
| 4 | mixer `0x0525c01c`+`034` low 60 -> 0 | 120.6 |
| 5 | de `0x0524c004` low 22 -> 0 | 121.3 |
| 6 | vblender `0x0520000c`+`024` low 49 -> 0 | 105.6 |

`0x0528008c` is a plain pixel X origin for the layer, 1:1 with nothing else in
it. At 0 the content starts at column 0 and fills all 1280. Now written to 0
after the DE replay, for every mode but `fb-band`.

The two-sided perturbation is what makes this a measurement. Zero alone would
have been weak -- many registers could blank a band by breaking something --
but only an origin puts content at 406 when set to 400.

The control step separated two hypotheses nothing else in the run could. The
band stayed **pale** against a saturated red fill, so it was never framebuffer
content: a geometry fault, not addressing or fetch.

Steps 4 and 5 are real nulls, not hopeful ones, because the noise floor was
measured first -- re-scoring test_31, where nothing could have moved the band,
gives 8 px. They came back at 1-2.

## A scorer bug this exposed

The `--band` scorer thresholded the panel edge at a fraction of the panel's own
peak brightness. The pale band is dimmer than saturated content, so that put the
edge *inside* the band, eating ~20 px off a narrow one and barely touching a
wide one. It read 123 as 102 while reading 400 as 401, which looked like a
nonlinearity in the hardware and was nothing of the sort. Half way between wall
and panel gives 119.4 and 406.2, and the register is linear after all.

Worth remembering: the shape of a systematic error can imitate a physical
effect, and "the small case disagrees, the large case is exact" is a signature
of a threshold problem, not of hardware.

## Loose ends, neither load-bearing

- **Step 6 moved the band 14 px**, above the 8 px floor. Its pairing was also
  wrong: `0x05200024` holds `02d00016`, so the value-sibling of `0x0520000c` is
  `0x05200020`, not what was written. Since `0x0528008c` accounts for the band
  exactly, this is at most a small second contribution.
- **What writes 123 is unknown.** It survives the DE replay, so it is
  LogoRegData or the firmware itself -- which is why the fix is a write
  afterwards rather than a patched record.

## Next

The stride is the only fault left. `fb-fix` now sweeps it against a full-width
image.

# The stride register is live, and unit-slope (2026-08-03, test_31)

`fb-stride` held the pattern at 1237 and swept AFBD `0x05600170`. Every write
read back. The display followed:

| photo | register | stripes (FFT / acorr) | predicted if live | tilt |
| --- | --- | --- | --- | --- |
| IMG_0612 | 1280 (default) | 3.77 / 2.88 | 0 | - |
| IMG_0614 | 1284 | 2.94 / 2.98 | 2.3 | - |
| IMG_0615 | 1288 | 5.18 / 5.29 | 4.7 | - |
| IMG_0616 | 1292 | 7.54 / 7.62 | 7.0 | - |
| IMG_0617 | 1296 | 9.98 / 10.04 | 9.3 | - |
| IMG_0618 | 1272 | 4.05 / 4.09 | 4.7 | **+** |

**The register is consulted.** The control passes too: 1272, the only step below
the default, is the only one whose stripes lean the other way, so this is a real
response and not a count that happens to grow.

Fitting `N = (720/P)|a(V - V0)|` over the four well-determined steps:

```
a = 1.006 px stride per px register     V0 = 1279.0     rms = 0.04 stripes
S(V) = V - 42        S(1280) = 1238
```

The two lowest-count steps are excluded. At about one cycle in the frame an FFT
has nothing to resolve, and 1280's two methods disagree 3.77 against 2.88 where
every other step agrees to 1%. They are not needed: the photograph settles the
ordering they would have decided, since step 1 carries visibly fewer stripes
than step 2, putting the minimum at or below 1280 exactly where the fit has it.

**S(1280) = 1238 against test_30's 1237 +- 2, from an unrelated experiment.**
test_30 swept the pattern and held the hardware fixed; test_31 held the pattern
and swept the hardware. They share no assumption beyond the stripe model, so the
stride is settled at 1237-1238.

## Next

`S = V - 42` says the framebuffer path comes right at V = 1322 px, `0x14a8`
bytes. `fb-fix` writes the pattern at the natural 1280 and sweeps 1300..1340 for
it, with a control at today's value; a step with one vertical edge is the fix.
Then `panel-test 0x33 vendor-logo 0x14a8` puts it on real content.

The extrapolation is 42 px beyond anything measured, hence 10 px steps rather
than a bracket around 1322 -- a wide sweep still measures if the offset is off.

The band is untouched by any of this: the stride moved 24 px across the sweep
(1230..1254) and the band held at 1158 +- 4. It is a content width and remains
open.

# The framebuffer stride is 1237, and it was never two numbers (2026-08-03, test_30)

`fb-edge` ran six steps at 1180..1200. Five were photographed (test_30). Every
one of them missed, and the run still produced the answer, because the stripe
count is a slope rather than a match.

## What the photographs say

| photo | assumed pitch | stripes (FFT / autocorr) | band width |
| --- | --- | --- | --- |
| IMG_0604 | 1180 | 34.80 / 34.43 | 1122 |
| IMG_0605 | 1184 | 32.24 / 31.30 | 1129 |
| IMG_0606 | 1188 | 30.06 / 29.79 | 1135 |
| IMG_0608 | 1196 | 25.45 / 24.90 | 1144 |
| IMG_0611 | 1200 | 22.89 / 23.03 | 1138 |

Row Y begins at source word `Y*S`, so the boundary slides `S mod P` px per row
and wraps, painting `N = 720*min(S mod P, P - S mod P)/P` stripes. A count fixes
`S mod P` but not its sign, so `S` came from searching every stride in 2..4000
for one consistent with all five pitches. There is exactly one:

```
S=1237  rms=0.471      S=1238  rms=0.619      S=1236  rms=0.890
```

Only five of the six steps were photographed, so the step-to-pitch mapping is
inferred. Re-solving under all six possible mappings gives 1236..1240, and the
best-fitting one -- step 1192 unphotographed, rms 0.471 against 0.90..1.13 for
every alternative -- gives 1237.

**S = 1237 +- 2 px/row.** `fb-edge-fine` sweeps 1232..1240 and closes it.
Reproduce with
`tools/display/edge-measure.py --pitches 1180,1184,1188,1196,1200 IMG_*.jpeg`.

Two guards were run before crediting this. Three counting methods were compared
and FFT and autocorrelation agree to ~1% (zero-crossing undercounts on the two
blurriest frames, as expected). And the stripes are 17..26 image px apart
against a ~600 px content height, so they are resolved several times over, not
moire -- the trap that cost two numbers the day before.

## The mistake this corrects

The band and the stripes were both being called "the pitch". They are not the
same quantity:

- **stride S = 1237** -- how far the source pointer advances per display row.
  Only the stripes see it.
- **width W = 1155 +- 5** -- how much of the display line receives content. Only
  the band sees it.

The old "~1187 px/line" was `W`, inferred from the band, then used to *predict*
`S` and to centre a sweep at 1180..1200. The answer was 37..57 px outside that
range, in the direction nobody swept. `W` held flat across all five
steps while the stripe count moved 34 -> 23, which is exactly how a
pattern-independent hardware property must behave, and is the internal check
that the two are distinct.

The prediction made before the run -- 4.3/1.8/0.6/3.0/5.4/7.8 stripes for
S = 1187 -- was falsified outright by counts of 34/32/30/25/23. Stating it as a
number is what made the miss legible within one run instead of a session.

## Next

`0x05600170` holds `00001400` (5120 B, 1280 px) while the fetch measures 1237,
so it is either not consulted or consulted through some transform. `fb-stride`
holds the pattern at 1237 and sweeps the register over 1280/1284/1288/1292/1296/
1272 px: live-with-unit-slope predicts 0/2.3/4.7/7.0/9.3 stripes with step 6
leaning opposite to step 3, inert predicts six identical vertical edges. Step 1
leaves the register alone and so re-measures the stride for free.

# SESSION HANDOFF -- 2026-08-01 (CPU_COMM ring wrap and marshalling hardware-proven)

Read this first. It supersedes the earlier 2026-08-01 static handoff and every
older claim that `THal_Vp_GetImageBufferAddr` uses handler `0x8b10a110`.

The peak-count fix completed the first CPU_COMM round trip on hardware. The
authenticated board-B firmware accepted the CALL, returned
CALL_ACK and RETURN in 0 ms, and U-Boot received the matching reply, published
RETURN_ACK, observed the low-level interrupt handler consume that publication,
and recycled FreeReturn slot 0:

```
reply after 1 ms, session=1 comp_id=2f02f7dd
ReturnCmd queued slot 0
RETURN_ACK publication consumed after 1 ms
FreeReturn slot 0 recycled (rd=1 wr=20 -> 0)
```

The post-run dump exposed and verified the receiver-ownership fix: ARM
ReturnCmd now advances from `rd=0 wr=1` to `rd=1 wr=1`. The MIPS sender does
not consume that receiver-local staging FIFO, so advancing ARM `rd` is correct.

An earlier two-call run exposed a deeper ACK boundary. The second CALL
was published and accepted by the interrupt handler, but MIPS CallCmd stayed
at `rd=1 wr=2` and produced no second reply. The trace remained at `0xc009`.
Therefore no worker dequeued the second CALL. Because `0xc009` was the old
trace's final marker, that run alone could not tell whether the first worker
was still in the ACK wait, stalled during post-ACK cleanup, or had returned
before the second-call failure.

The expanded trace has now resolved that ambiguity on hardware. The ACK copied
session 1 and the valid MIPS wait pointer `0x8b253e7c`; the interrupt consumed
the publication after 1 ms, and the trace reached `0xc013` before U-Boot's
next 1 ms poll:

```
RETURN_ACK metadata session=00000001 wait=00000000:8b253e7c
RETURN_ACK publication consumed by interrupt handler after 1 ms
MIPS sender completed RETURN after 0 ms
```

This proves the deferred ACK action posted the wait semaphore,
`SendComm2CPUEx` resumed, released its send semaphore, and returned to the CALL
worker. The earlier `c009` value was merely the last marker available in that
build, not evidence of an ACK stall. The ACK path is cleared.

The second CALL on that same boot reproduced the failure. Its msgbox FIFO was
drained and the CALL publication bit was cleared in 0 ms, but it produced no
second CALL_ACK or RETURN. The independent trace then proved the global HISR
queue send succeeded, the prior RETURN_ACK wrapper fully returned (`f003`),
and CALL #2 reached **`e008`, inside `SendAckLow` immediately before sending
CALL_ACK**. The stall is therefore not in queue reuse or dispatch.

This exposes the missing receiver operation. `SendAckLow` publishes CALL_ACK
metadata in the opposite-direction `share_seq(0,1,0)` at shared `+0x13a8`,
fields `+0x68..+0x74`; it raises `+0x69` bit 2 and rings mailbox type 2. U-Boot
drained that mailbox word but never cleared the shared publication bit. On
CALL #2, `SendAckLow` checks `+0x69` at
`0x8b120964`, sees the first ACK still outstanding, and assert-spins at
`0x8b120b28` before sending anything.

The current source now mirrors the stock ARM CALL_ACK handler: on mailbox type
2 it reads and validates index 20, session 1, and the raised state bit, then
clears `share_seq(0,1,0)[+0x69]` bit 2 and flushes the exact containing cache
line.
It also prints the ACK metadata and refuses malformed publications. This is
the protocol fix, not a timing workaround.

The first implementation deliberately validated before writing and caught an
addressing error on hardware: reading ACK fields from the original
`share_seq(1,0,0)` returned untouched init values `index=20 session=ffffffff
state=00`, so U-Boot refused to consume them. The wrapper at `0x8b1195ec`
settles the mapping: `getShareSeqW(remote=0, dir=0)` calls the core lookup with
`(remote=0, current=1, dir=0)`, which is shared `+0x13a8`. The current build
uses that exact sequence.

The corrected build completed **two consecutive transactions on one boot**.
Both CALL_ACK publications were read as `index=20 session=1 state=04` and
consumed; both matching RETURNs were acknowledged; and both MIPS senders
reached `0xc013`. Afterward, all receiver staging FIFOs were empty and both
active free rings retained all twenty descriptors:

```
MIPS CallCmd       rd=2 wr=2
ARM  ReturnCmd     rd=2 wr=2
MIPS FreeCall      rd=2 wr=1   count=20
ARM  FreeReturn    rd=2 wr=1   count=20
```

This is the first hardware proof of repeatable, leak-free ARM-to-MIPS
CALL/CALL_ACK/RETURN/RETURN_ACK traffic in this project.

The ring-wrap test is now complete as well. On one boot the trace build ran 22
consecutive calls, crossing the 21-entry boundary. Every call received and
consumed CALL_ACK, received RETURN, completed the deferred RETURN_ACK wakeup,
consumed ReturnCmd, and recycled FreeReturn. The post-run state matched the
modulo-21 prediction exactly:

```
MIPS CallCmd       rd=1 wr=1
ARM  ReturnCmd     rd=1 wr=1
MIPS FreeCall      rd=1 wr=0   count=20
ARM  FreeReturn    rd=1 wr=0   count=20
```

The same boot then completed another 22-call loop. The transcript contains 44
matching replies, 44 consumed CALL_ACK publications, and 44 recycled
FreeReturn descriptors with no timeout or malformed-publication report. The
final snapshot was exactly `FreeCall rd=2 wr=1`, `CallCmd rd=2 wr=2`,
`FreeReturn rd=2 wr=1`, and `ReturnCmd rd=2 wr=2`; the persistent trace remained
at CALL `e011`, sender `c013`, RETURN_ACK `f003`, with HISR queue send zero.
Thus the active rings crossed their wrap boundary more than once without a
descriptor leak or stale staging entry.

The result is not dependent on the diagnostic firmware patches. After a power
cycle, ordinary `h713_disp mips-test 0x33` (no CPU_COMM progress trace
installed) completed a separate 22-call wrap run. It produced 22 matching
replies, consumed all 22 CALL_ACK publications and ReturnCmd entries, and
recycled all 22 FreeReturn descriptors. The final state again matched the
modulo-21 prediction exactly: `FreeCall rd=1 wr=0`, `CallCmd rd=1 wr=1`,
`FreeReturn rd=1 wr=0`, and `ReturnCmd rd=1 wr=1`. Successful descriptor reuse
after the wrap also proves the sender cleanup completed even though the
trace-only `MIPS sender completed RETURN` message is intentionally unavailable
in this mode. Production-mode CPU_COMM ring wrap is therefore hardware-proven.

The current artifact adds a guarded real-handler marshalling test. Static
analysis of the authenticated board-B image identified the safest
getter/setter pair:

- `THal_Vp_GetPictureMode` (`0x2d8338c3`, handler `0x8b10a8ec`) returns one
  word read from the live picture-mode state at `0x8b272988`;
- `THal_Vp_SetPictureMode` (`0x83a878bf`, handler `0x8b10a8c0`) accepts one
  word and compares it with that same state before doing anything else. An
  equal value branches around the hardware update.

`h713_disp comm-pq-test` first verifies both live call-table entries, including
their ids, owner PID, and exact authenticated handler addresses. It gets the
current mode, sets precisely that value back, then gets it again. The command
requires getter `nret=1`, setter `nret=0`, and an identical final value. This
exercises zero-input/one-output and one-input/zero-output marshalling while
deliberately taking the setter's side-effect-free equality path. It refuses to
run if any guard differs. Generic `commcall` now also captures the returned
count and up to ten returned words; raw count `0x0f` is correctly retained as
the worker's no-output sentinel and normalized to zero, preserving the proven
no-op probe.

Hardware validation passed on the production `mips-test` path. The live guards
found SetPictureMode at entry 191 with handler `0x8b10a8c0` and GetPictureMode
at entry 195 with handler `0x8b10a8ec`. The three transactions returned:

```
GetPictureMode  nret=1  ret[0]=00000000
SetPictureMode  nret=0
GetPictureMode  nret=1  ret[0]=00000000
picture-mode marshalling PASS
```

Every CALL_ACK and RETURN_ACK publication was consumed and every ReturnCmd and
FreeReturn descriptor was reconciled. The final transport state was exactly
`FreeCall rd=3 wr=2`, `CallCmd rd=3 wr=3`, `FreeReturn rd=3 wr=2`, and
`ReturnCmd rd=3 wr=3`. Zero-input/one-output and one-input/zero-output
marshalling are therefore hardware-proven without changing the picture-mode
state. To reproduce after flashing and power-cycling, run:

```
h713_disp mips-test 0x33
h713_disp commdev
h713_disp comm-pq-test chan=0 pid=8b8f32b0
h713_disp commstate
```

On a fresh transport, three successful transactions leave FreeCall and
FreeReturn at `rd=3 wr=2` and both active staging FIFOs at `rd=3 wr=3`.

The same production boot then invoked the real state-changing
`THal_Vp_DisableBlackScreen` component (`0xb66041d8`). The firmware accepted
the zero-input CALL, returned matching `comp_id=b66041d8` with `nret=0`, and
completed the full acknowledgement and recycling path. The post-call state was
exactly `FreeCall rd=4 wr=3`, `CallCmd rd=4 wr=4`, `FreeReturn rd=4 wr=3`, and
`ReturnCmd rd=4 wr=4`. This hardware-proves dispatch through a nontrivial
state-changing adapter as well as transport and marshalling. The bench
operator reported no visible panel difference after the successful call. The
firmware black-screen gate is therefore not the sole visible blocker; the next
narrow gate test was `THal_Vp_DisableScreenCover` with selector 0. That
one-input call also completed with `nret=0`; its queues balanced at
`FreeCall/FreeReturn rd=5 wr=4` and `CallCmd/ReturnCmd rd=5 wr=5`, but the
operator again saw no screen difference. The default cover target is not the
visible blocker. Selectors 1, 2, and 3 were then invoked individually; all
three returned matching `comp_id=143ffc87` with `nret=0`, completed every ACK
and recycle operation, and produced no visible difference. The final state was
exactly `FreeCall/FreeReturn rd=8 wr=7` and `CallCmd/ReturnCmd rd=8 wr=8`.
Black-screen and all four mapped screen-cover targets are now excluded as the
sole cause. Further work moves below the overlay-gate layer into composition,
buffer publication/fetch, and DE/AFBD state.

A fresh `panel-test 0x33` then published known 1280x720 ARGB8888 patterns at
`0x6c100000` before calling `THal_Vp_SetSource(2)` (`0xeaf13de5`). The RPC
completed with `nret=0` and balanced at `FreeCall/FreeReturn rd=1 wr=0` and
`CallCmd/ReturnCmd rd=1 wr=1`. Comparing all 212 words in the pre-call and
post-call display dumps found exactly one difference: `0x05880000`, the live
scan counter. TVTOP, mixer, DE, AFBD, buffer address, routing, PLL, and module
clock values were otherwise byte-identical. Thus SetSource(2) caused no
synchronous change in the sampled hardware composition path. Static
disassembly shows the setter calls the source object through
`[0x8b253578]->vtable[3]` and then stores the requested value at firmware state
word `0x8b2729ac`.

The first boundary read returned `0x8b2729ac=0` while the source object pointer
was live at `0x8b253578=0x8b8c8ecc`. That zero does **not** show that the
setter rejected 2: both are ordinary cached MIPS KSEG0 locations, and ARM
cache invalidation cannot evict a dirty MIPS data-cache line. Static analysis
settles the part that can be proven without another artifact. The object's
vtable is `0x8b1eb594`; slot 3 is `0x8b107574`. That callback does not touch
display MMIO. It submits the 16-byte `{event=0, source}` record to the object's
nonblocking queue at `0x8b15c460`. The object's worker at `0x8b1091f4` later
dequeues event zero, compares the requested source against its private current
source at object `+0xe0`, and only then runs the transition path. The stock
`THal_Vp_GetSource` component cannot expose this state: handler `0x8b10a244`
calls `0x8b14b524`, which returns one output word containing zero
unconditionally.

The current communication-trace build therefore instruments this asynchronous
worker through the MIPS uncached `0xae34xxxx` alias. It records the event,
requested source, worker's previous source, raw queue result, and final stage:

| source stage | meaning |
| --- | --- |
| `0x5101` | source callback received the event |
| `0x5102` | callback's nonblocking queue send returned |
| `0x5201` | worker dequeued a source-change event |
| `0x5202` | worker found requested source equal to current source and skipped it |
| `0x5203` | worker completed the source-transition path |

The first hardware run returned callback stage `0x5102`, `event=0`, `new=2`,
`old=0`, and queue result zero. This already proves that the worker dequeued
the event: `old` was initialized to `0xffffffff` and only the worker writes
that field. It also proves this was a real 0-to-2 change, not the equality
shortcut. The higher-priority worker preempted the callback during the queue
send, wrote a `0x52xx` stage and `old=0`, then the resumed callback overwrote
the shared stage with `0x5102`. Thus that run cannot distinguish worker entry
from worker completion. The corrected trace stores callback and worker stages
in separate words so this scheduling race cannot erase either result.

The corrected trace then closed the path on hardware. It retained callback
`0x5102` and worker `0x5203` simultaneously with `event=0 new=2 old=0
queue=00000000`. Thus the firmware performed and returned from the complete
0-to-2 source transition. CPU_COMM and source selection are not the remaining
display blocker. Combined with the earlier byte-identical pre/post MMIO dump,
this proves that a source transition does not itself publish an image buffer
or alter the sampled DE/AFBD composition state.

Static inspection also closes the tempting next CPU_COMM call. In this exact
firmware, `THal_Vp_SetImageBufferAddr` entry 703 uses handler `0x8b10ada8` and
`THal_Vp_GetImageBufferAddr` entry 989 uses `0x8b10adb0`; both handlers are
only `jr ra; nop`. Despite their exported names, neither can register, set, or
return an image buffer. Do not spend a run calling `0x396f16bf` with guessed
parameters. Image publication must use another internal interface, or the
already recovered direct AFBD/DE path.

The nearest asynchronous source event is not that interface either. The event
one producer at `0x8b1075bc` is `CallbackOfSignalChange` in
`app_top_projector.cpp`. It copies a 0xac-byte input-signal descriptor into
firmware state at `0x8b25357c` and queues `{event=1, descriptor}` to the same
source worker. It describes input timing/signal state; it does not carry or
publish an OSD framebuffer. Do not patch or synthesize event one as a display
test.

A prior artifact tested a concrete but provisional related-platform inference:
after writing AFBD channel-1 ready `0x05600144[0]`, it also set bit 0 in the
selected OSD control word at `0x0524c000`. `panel-test` had previously left
that word at the authenticated board-B value `0x00fc0202`. The experiment
preserved every other format/routing bit and printed both immediate readbacks.

Hardware accepted both writes. All four frames immediately read
`AFBD=00000001 OSD=00fc0203`; `0x05880000` continued advancing, and
`0x05600168` remained 2. The attached photograph shows a large, uniform lit
image rectangle rather than the eight coloured bars. The second OSD write is
therefore real and materially changes the active-plane boundary, but it has
not yet demonstrated that the supplied ARGB pixels reach the output.

Static cross-check against the recovered `ge2d_dev.ko` AFBD hard IRQ gives
`0x05600168` a precise meaning: it is channel 1's write-one-to-clear IRQ
status, and bit 1 is writeback complete. Stock reads it and writes the same
value back before advancing the AFBD state machine. U-Boot had no handler and
left completion `2` pending before every moving-frame commit. The current
artifact now mirrors that ownership explicitly: before each frame it writes
back any pending status, verifies the cleared readback, submits AFBD then OSD,
and waits at most 50 ms for bit 1 to reassert. Its one-line trace reports
`irq=<pending>-><cleared>-><done> wait=<us>`. A `2->0->2` transition proves a
fresh AFBD transaction completed; failure to clear or reassert localizes the
fault inside AFBD instead of downstream composition.

The hardware run closed that boundary. Every frame cleared the old status and
generated a new completion well inside one refresh interval:

```
pattern 1: irq=00000002->00000000->00000002 wait=9700us
pattern 2: irq=00000002->00000000->00000002 wait=6900us
pattern 3: irq=00000002->00000000->00000002 wait=7000us
pattern 4: irq=00000002->00000000->00000002 wait=7000us
```

The OSD control remained at the experimental `00fc0203`, the LVDS scan counter
moved throughout, and the operator still saw no clean bar image. This rules
out a stale AFBD interrupt and a submission that never finishes. It proves a
fresh channel-1 hardware transaction for every supplied frame; it does not by
itself validate the resulting pixels. The extra OSD write is not evidence for
a missing latch; the exact stock-driver cross-check below supersedes that
interpretation.

Stock U-Boot provides no additional post-blit show/commit write to copy. Its
BMP path fills the same 1280x720 32-bit surface, patches the AFBD `+0x178`
record, applies the ordinary register table, and only then starts the display
fabric/MIPS. The tempting `0x0520003c` bit-24 sequence is not valid evidence
for this board: it came from a related Linux reverse-engineering table later
identified in that tree as a wrong-base transcription. Do not write it here.

The next artifact adds an ownership discriminator instead of guessing another
mux bit. `quiesce` starts the firmware normally through application readiness,
then asserts only the MIPS core reset while retaining every display clock. It
samples `0x05880000` twice after reset, re-latches 720p, replays the
authenticated DE block, and submits the moving frames. It also expands the
read-only dump over the vblender, both OSD/DE2 channel companions, and AFBD
global/source-mux windows omitted from all prior comparisons.

After flashing and power-cycling, run only:

```
h713_disp panel-test 0x33 quiesce
```

Record the `MIPS core quiesced` line, the complete post-quiesce dump, the four
`frame commit` lines, and what is visible. If its last two scan words differ
and the moving bars appear, the firmware was actively owning/hiding the plane.
If the scan remains live and the bars do not appear, the fault is static
channel-1 DE/vblender routing and the new dump is the input for the next
single-register test. If the scan words are zero or equal, the command prints
a warning and the visual result is not a compositor verdict. Another
source-selection CALL is not useful in any of these cases.

The quiesced hardware run closed the ownership branch. Core reset and status
both read zero, while the scan counter continued through
`00ba033c->00800301->004202c4`. The 720p timing re-latched, the authenticated
DE block replayed, and all four submissions completed `2->0->2` with the MIPS
still held in reset. OSD channel 0 and both extra DE2 companion windows were
all zero; the selected channel-1 OSD/AFBD state remained populated. The AFBD
global source/mux windows also remained live, including buffer pointers
`0x4c5ee000` and `0x4cbeb000`. Therefore neither continued MIPS execution nor
a hidden channel-0 software plane explains the missing bars. The supplied
transcript did not include a visual observation, so do not infer one from the
register result.

### Exact AFBD submission and selected-plane gate

Board B's own `ge2d_dev.ko`, extracted directly from `vendor_a` inside the
`super` partition of `board-b-mmcblk0-20260705T072349Z.img`, has SHA-256
`a79017e5d3bc9563135e463404d3bb38bf6f263d5b31fbe122768f2dca11583f` and
build ID `0e41eee871447a0f1d8c89ae0d19c9a13c7c5513`. It is an unstripped ARMv7
module with the display symbols intact. This supersedes the differently hashed
board-A module for register semantics. Its read-only `OSD_AFBD_REG_OFFSET`
table contains
`{0x05600100, 0x05600140}`. Disassembly of `osd_ready_for_update()` indexes
that table and writes literal 1 to the selected base plus 4. For plane 1 this
is `0x05600144`, not `0x0524c004` and not `0x0524c000`.
`tgd_put_plane_info()` immediately precedes it by setting bit 0 at AFBD base
`0x05600140`. There is no per-frame write to OSD control bit 0. The earlier
related-platform OSD-bit inference is therefore retired.

The earlier board-A inference assigned plane visibility to
`0x0524c000[31]`. Board B's driver proves that assignment wrong:
`tgd_is_plane_open()` selects the plane's `0x0524c000` base, reads **base
+0x1c**, and returns bit 0. The live Board-B word is `0x0524c01c=79860601`,
so the exact plane-open gate is its low bit. The historical `quiesce`
diagnostic instead:

1. submits frames in stock order: AFBD `+0x00[0]`, then literal 1 to AFBD
   `+0x04`, without changing the OSD word;
2. set the now-retired `0x0524c000[31]` hypothesis for five seconds;
3. restores the complete original word for five seconds and crosses another
   frame boundary;
4. performs the AFBD enable-bit gate in the same labelled fashion;
5. publishes one static eight-bar frame and holds it for fifteen seconds.

The rotating animation is intentionally disabled in `quiesce` mode. Until one
bar frame appears, additional phases only repeat the same failed publication
and make hand-recorded observations harder to associate with a label. Other
`panel-test` modes retain their animation.

After flashing and power-cycling, run the same command and report what happens
during the two explicitly labelled intervals:

```
h713_disp panel-test 0x33 quiesce
```

Those old `plane DISABLED/RESTORED` labels do not represent stock visibility
and must not be used to conclude whether channel 1 reaches the final mix. The
AFBD gate and fresh-completion evidence remain valid.

The hardware accepted the discriminator exactly: `0x0524c000` changed
`00fc0202 -> 80fc0202 -> 00fc0202`; both frame-boundary submissions completed
`2->0->2`, and the raster remained live. The earlier `test_8` photographs were
not phase-labelled, so their warmer/brighter difference could not be assigned
to the gate.

The next discriminator moves one boundary upstream without guessing a format
field. The exact stock update path sets `0x05600140[0]` immediately before
writing AFBD ready, and stock disabled-channel state has bit 0 clear. The
current `quiesce` test now clears only that channel-enable bit for five seconds,
then restores the entire saved word, submits a normal frame, and holds another
five seconds. It prints two additional labels:

```
H713 panel: AFBD DISABLED ...
H713 panel: AFBD RESTORED ...
```

This historical run requested observations for both labelled pairs. Board-B
RE now supersedes any interpretation of its `plane DISABLED/RESTORED` pair;
only the AFBD pair exercised a confirmed gate. In every case, the authenticated AFBD
`+0x0c=00000080` must not yet be replaced with board-A's `00ff0080`: those are
the proven XRGB and NV12 channel modes respectively, not an established alpha
omission.

The phase-labelled `test_9` photographs close the visual half of both gate
tests. Baseline, AFBD enable, `plane DISABLED`, `plane RESTORED`, and `AFBD
RESTORED` all show the same uniform illuminated rectangle; no bar structure or
gate transition is visible. The transcript simultaneously proves that the OSD
and AFBD gate writes took effect, every restored submission completed a fresh
`2->0->2` transaction, and scanout remained live. Only the AFBD bit is now
known to have been an enable bit; Board-B RE retires the other candidate. This
supersedes the unlabeled `test_8` visual inference, but does not replace the
exact Board-B plane-open test below.

Before assigning a negative static-bar result to routing, the artifact also
contains a stricter pixel-source control:

```
h713_disp panel-test 0x33 vendor-logo
```

This mode uses `bootlogo.bmp` from Board B's bootloader partition alongside
the MIPS artifacts. Both `bootloader_a` and `bootloader_b` in
`board-b-mmcblk0-20260705T072349Z.img` contain byte-identical copies; the
runtime `mmc 1:2` path selects the latter. It is a 1280x720, 24-bit BMP of
2,764,854 bytes with SHA-256
`e812cd928c67b89608c7424ac80066c19633e76b150378abf4de9d62698eb22c`.
It happens to be byte-identical to the board-A copy, but Board B is the pinned
provenance. At runtime the command reads the board's own file from `mmc 1:2`
and refuses it unless that complete hash matches.

`vendor-logo` reproduces the statically verified stock blitter literally:
bottom-up BMP B,G,R triples become little-endian `0xffRRGGBB` framebuffer
words. It then performs the normal firmware initialization, quiesces the MIPS
owner, restores the authenticated 720p timing and DE block, and submits one
frame. It deliberately skips the OSD gate, AFBD gate, enable probe, bar frames,
and every animation. Photograph only the fifteen-second interval labelled
`EXACT VENDOR LOGO COMMITTED`. If the logo is absent while the fresh AFBD
transaction and scan counter remain live, the generated bar contents and BMP
conversion are eliminated together; the remaining fault is downstream of the
pixel buffer.

The `test_10` hardware run produced exactly that negative control. Both reads
of `bootlogo.bmp` matched the pinned Board-B SHA-256, both conversions
published the expected `0xffRRGGBB` surface, the final submission completed a
fresh `00000002 -> 00000000 -> 00000002` AFBD transaction in 5.4 ms, and the
720p scan counter was live. The expected source image is a black frame with
centered white `SMART PROJECTOR` text. The phase-labelled `baseline.jpeg` and
`logo.jpeg` instead contain only the same uniform illuminated rectangle; no
letterform, edge, or other source-image structure is present. The latter is
somewhat brighter and has a faint vertical tint boundary, but the camera moved
between frames and automatic white balance remained enabled. Both captures
used 1/60 s, ISO 800, and f/2.2, so the luminance change is worth retaining as
an observation but is not evidence that logo pixels were fetched.

This closes the test-pattern-content branch: bars, BMP selection, BMP row
order, per-pixel byte order, cache clean, and stale completion are no longer
productive variables. It does **not** prove AFBD decoded the surface or that
channel 1 reached the final mixer. Board B's exact plane-open bit must be tested
before moving downstream to static mixer/vblender routing; do not spend another
run changing framebuffer contents.

The follow-up `test_11` run independently repeated the upstream result. The
console proves the retired `0x0524c000[31]` candidate changed
`00fc0202 -> 80fc0202 -> 00fc0202`, the AFBD channel changed
`03001901 -> 03001900 -> 03001901`, each restored frame generated a fresh
completion, and the 720p scan counter remained live. `test.jpeg` was taken
during the labelled DISABLED/RESTORED tests, not during the later static-bar
hold. The operator saw no transition during either the gates or the final bar
publication. Its vertical tinting is therefore not bar evidence; the capture
also used substantially different automatic exposure from `baseline.jpeg`.
Photo filesystem timestamps are deliberately not used to assign phases.

The next artifact uses the newly recovered Board-B plane-open control and omits
the invalid old OSD gate and already-settled AFBD gate:

```
h713_disp panel-test 0x33 plane-gate
```

It starts the firmware, quiesces only the MIPS core while retaining display
clocks, restores the authenticated 720p/DE state, publishes one static bar
frame, and proves a fresh AFBD completion. It then saves `0x0524c01c`, clears
only bit 0 for five seconds, and restores the exact saved word for five
seconds. Observe `BOARD-B PLANE CLOSED` and `BOARD-B PLANE RESTORED`. A visible
transition proves the selected OSD/AFBD plane reaches the optical path. No
transition with a moving scan counter and fresh AFBD completions moves the
boundary downstream to the static mixer/vblender route.

The phase-labelled `test_12` run produced the exact electrical transaction but
no visual transition. `0x0524c01c` changed
`79860601 -> 79860600 -> 79860601`; all three submissions completed a fresh
`00000002 -> 00000000 -> 00000002` AFBD cycle, and the scan counter moved in
every interval. `BASELINE.jpeg`, `CLOSED.jpeg`, and `RESTORED.jpeg` retain the
same uniform illuminated rectangle without bar structure. `CLOSED.jpeg` used
different automatic exposure, so its small luminance difference is not a
structural display result. This proves the stock plane-open status bit is
writable but also shows that changing that bit alone does not control the
visible rectangle.

Board B's unstripped module provides a stronger downstream split without
another guessed mixer field. The style-selection tail of
`tgd_set_checkboard_style(8)` enables the TCON's own checker generator using a
literal sequence: mode 5 at `0x0588001c`, bit 3 at `0x0588000c`, cell size
`0x00800080` at `0x05880038`, and packed colours
`0xff000000`/`0x000000ff` at `0x0588003c/40`. Its preceding writes only rebuild
TCON timing from cached panel geometry; this command has already latched the
authenticated 720p timing. The next artifact reproduces the Board-B style tail
after firmware initialization and MIPS quiesce:

```
h713_disp panel-test 0x33 tcon-checker
```

It holds one static 128x128-cell checker for fifteen seconds under the label
`BOARD-B TCON CHECKER ACTIVE`, then restores every touched word exactly and
holds another five seconds. If the checker appears, the TCON/LVDS/panel path is
good and the remaining fault is upstream composition. If the illuminated
rectangle does not change while the programmed words read back and the scan
counter moves, the optical output is not responding to the LVDS pixel stream
being programmed; further OSD/AFBD/mixer format tests cannot fix that boundary.

The phase-labelled `test_13` run produced a third and more useful result. The
hardware accepted every exact style-8 word:

```
ctrl  00e40202 -> 00e4020a -> 00e40202
mode  00000004 -> 00000005 -> 00000004
size  00080008 -> 00800080 -> 00080008
rgb   00000000/3fffffff -> 3f000000/000000ff -> 00000000/3fffffff
scan  ... -> 00e10363 -> 00870309
```

The top two requested colour bits are not implemented, so the literal
`ff000000` correctly reads back as `3f000000`. While style 8 was active, the
projected rectangle changed to **three vertical colour bands**. It did not show
the expected 128x128 red/blue checker cells. The operator confirmed that the
three bands were visible directly and matched the photographs, so this is not
a camera rolling-shutter artefact. Restoration removed the test response.

This is the first positive pixel-path boundary result. The optical engine is
not merely showing fallback illumination: TCON-local generated data reaches
the LVDS/downstream optical chain and changes the projected image. It is
nevertheless being interpreted incorrectly. Since this generator bypasses
framebuffer, AFBD, OSD, DE and vblender, no further compositor gate test can
explain the malformed checker. Attention moves to the downstream link:
packed-colour interpretation, lane/bit mapping, and receiver input geometry.

Board B's same stock function has a stronger discriminator in style 1. It uses
the identical mode, enable bit, and 128x128 cell size, but supplies black and
white (`00000000`/`3fffffff`). The next artifact exposes that exact static
variant without bringing any animation back:

```
h713_disp panel-test 0x33 tcon-checker-mono
```

A roughly 10-column by 5-to-6-row black/white grid means geometry and lane
ordering are intact and isolates the style-8 failure to colour packing. Three
monochrome vertical bands instead implicate row/lane or receiver input geometry.
The command again holds for fifteen seconds, restores all five saved words,
and leaves the MIPS core quiesced.

The style-1 hardware run accepted the command exactly but produced **no visual
change**:

```
ctrl  00e40202 -> 00e4020a -> 00e40202
mode  00000004 -> 00000005 -> 00000004
size  00080008 -> 00800080 -> 00080008
rgb   00000000/3fffffff (unchanged black/white)
scan  ... -> 00e40366 -> 00830305
```

The stock logo being white text on black does not make this a null test: ten
by roughly six 128-pixel checker cells would dominate the entire 1280x720
frame. The combined style result is therefore narrower than either run alone.
Changing the two generated colour words in style 8 visibly creates three
colour bands, but enabling the same generator and cell geometry with stock
black/white words produces no spatial grid. A simple ARGB/packed-colour error
cannot by itself explain the missing row and column alternation. The receiver
input geometry or LVDS lane/bit interpretation remain the leading candidates.

After that observation, use the already-built non-register-writing address
probe on the same boot:

```
h713_i2c scan
```

The hardware scan answered only at `0x18`:

```
H713 i2c: scanning PH2/PH3
  0x18 ACK
H713 i2c: 1 device(s) responded
```

That address matches Board B's enabled STK8BA58 accelerometer node, proving
the PH2/PH3 bus, address convention, and scanner. The earlier expectation that
`0x6a` was the positive control was stale: the stock DT lists several
alternative accelerometers, and this board populated the `0x18` choice.

There was no response at `0x1b` after the stock PF6/PH16 power sequence and a
live TCON run. Board B's stock DT also contains no DLPC node. Its unstripped
`ge2d_dev.ko` does contain a legacy optional `DLPC3435` driver, but the exact
`tv_i2c_detect()` implementation restricts detection to adapter 1, which is
the PH2/PH3 bus just proven. The callback's presence therefore does not prove
this board uses that optional controller path. Do not issue the recovered
DLPC initialization writes on this hardware.

The same freshly extracted Board-B module confirms the current diagnostic's
store order exactly: mode 5, control bit 3, then size and the two color words.
It also provides solid-black style 2 and solid-white style 3. The next
diagnostic applies those two exact styles for 7.5 seconds each:

```
h713_disp panel-test 0x33 tcon-solid
```

A full black-to-white transition proves that the generator replaces the
source image and isolates the checker failure to its spatial/lane handling.
No change during either solid phase means the style-8 bands came from the
color-word path without a functioning source replacement; the next work must
reproduce more of the TCON setup rather than chase an absent I2C peripheral.

Hardware instead produced a decisive inversion-like response. Exact stock
style 2 (both color words zero) made the field lighter; exact stock style 3
(both color words `0x3fffffff`) made it darker, yellowish, and nonuniform, with
an oval region visible near the centre. The persistent far-left column and
jittering white line at the top survived both spatially uniform sources. This
proves that the TCON generator is controlling the visible output, rules out
the framebuffer, AFBD decoder, and checker geometry as the cause of those
boundary artifacts, and places the fault in the downstream timing/link
interpretation. The response is not clean enough to call it a simple logical
color inversion; sampling edge, LVDS lane/bit mapping, and timing remain live
possibilities.

Every generator diagnostic above quiesced the firmware and immediately
replaced its final 1920x1080 TCON timing with the reconstructed 1280x720 panel
timing. Preserve the firmware timing while applying the identical solid
styles to isolate that overwrite:

```
h713_disp panel-test 0x33 tcon-solid-native
```

The command must report the retained firmware tuple, expected from the known
image as mode 2, 2200x1125 total, and 1920x1080 active, before announcing the
black phase. If the left column, top jitter, or intensity ordering materially
improves, the 720p relatch is wrong for the live receiver even though the XML
and vendor table describe a 1280x720 panel. If the result is unchanged, timing
selection is substantially de-risked and the next controlled sweep should
change only the LVDS sampling-edge polarity, then lane/dual-port mapping, under
the same spatially uniform source.

The native-timing run was clearly worse. At boot the output was mostly white
with a dark left column, then gradually drifted blue. Its first observation
was a fixed white oval with dark edges, and neither the all-zero nor all-one
generator phase caused a visible transition. The firmware's mismatched 1080p
TCON timing is therefore closed as a route to a usable diagnostic image; keep
the explicit 720p relatch for subsequent tests.

The next diagnostic keeps that 720p timing and the exact style-2 all-zero TCON
source fixed, and changes only `PanelInvDCLK` at `0x05800000[24]` in an
inverted/normal/inverted A/B/A sequence:

```
h713_disp panel-test 0x33 tcon-dclk
```

The bit position was rechecked directly against Board B's stock U-Boot patch
function before adding the test. The apparently contradictory older notes use
a differently ordered panel-setting array; the actual calls map DCLK to bit
24, DE to bit 18, HSync to bit 16, and VSync to bit 17, matching the current
recovery implementation. A real edge effect must appear in the middle
`DCLK B NORMAL ACTIVE` phase and reverse in `DCLK A INVERTED RESTORED`.

Hardware showed a synchronized edge effect. Before the test the output was a
nearly uniform dark blue and the far-left column was only slightly different.
The first inverted-DCLK observation was uniformly dark with the familiar
white artifact at the top. On entry to the normal-DCLK phase, many vertical
lines appeared for a fraction of a second while the link resynchronized; it
then settled to uniform dark blue **without the top white artifact**. After
the test restored the prior state, the field briefly became light and faded
back to dark blue with the top artifact present again. This is stronger than
the unrelated slow optical drift: the transition was phase-locked to the bit
change and the most persistent boundary artifact followed the edge selection.

Because changing the edge on a live serial stream visibly resynchronizes the
receiver, do not yet treat the normal setting as a permanent configuration
fix. Select normal DCLK before enabling the generator, let it settle, and run
the exact zero/one solid comparison entirely under that edge:

```
h713_disp panel-test 0x33 tcon-solid-dclk-normal
```

The corresponding DDR3 artifact is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (915761 bytes), SHA-256
`10bf71d2e52bc782c2e90c660fc1fd4c38667f2ac8c99d0771c3ae8989f5081d`.

If the two solid codes now produce a stable, repeatable transition without the
top line or strong left-column boundary, normal DCLK becomes the leading
candidate configuration correction. If the boundary improves but the codes
remain misinterpreted, keep normal DCLK for the next test and move one variable
downstream to LVDS mapping/port selection.

### The test_14 run is inconclusive, and it invalidates the method

That run happened and produced neither outcome. It is recorded as
`local/lcd-photos/test_14/IMG_0565.MOV`, a 37.33 s 3840x2160 30 fps capture
started immediately before the command was entered. The console shows every
programmed write landing: `lane=00e0a404` (bit 24 cleared, saved `01e0a404`),
solid black `rgb=00000000/00000000`, solid white `rgb=3fffffff/3fffffff`, all
five words restored, and a live scan counter in every phase.

Frame analysis was required because the camera's automatic exposure had already
corrupted earlier photographic comparisons. Measuring the projected rectangle
against an ambient wall region cancels that: auto-exposure moves both, the
projector moves only the rectangle. The resulting ratio has exactly three real
optical events in the whole recording, all inside the first 3.1 s:

| video time | rect/wall | note |
| --- | --- | --- |
| 0 -- 1.4 s | 1.825 flat | idle |
| 1.4 s | +0.072 step | real; ambient flat at 102.5 |
| 2.1 -- 3.1 s | +0.194 step, plateau 2.05 | real; left column, top bar and central oval all visible |
| 3.1 s | -0.143 step | returns to featureless |
| **3.1 -- 37.3 s** | **1.925 -- 1.965** | **flat for 34 s** |

The largest ratio step anywhere after 4 s is 0.032. Column profiles across the
rectangle interior are identical between the phases; the only per-column
differences are at the rectangle's edges and track slow camera drift. Across
the black/white boundary the interior luminance moves 0.3 units in 200, 0.15 %.

The command's visible portion is 21 s (1 s settle, 7.5 s, 7.5 s, 5 s), and its
pre-test portion -- MMC loads, the 550 ms power pre-delay, a 1.2 MB SHA-256,
MIPS release and readiness, and two full register dumps -- cannot complete in
3.1 s. The entire test therefore ran inside the flat window. The panel's last
structured output was roughly thirteen seconds **before** the DCLK write.

That is why this run does not answer the question. A featureless result during
the solid phases is equally consistent with "normal DCLK silenced the link" and
with "the link was already silent when the edge was changed", and the timing
favours the second. Recording the artifacts appearing for one second near the
start and never again is itself unexplained; every prior generator run had them
persisting throughout.

Two method failures, both fixed in the current artifact:

- **No in-run liveness evidence.** Every generator test so far has been scored
  against expectations from a different boot. Without a positive control on the
  same boot, a null phase cannot be distinguished from a dead link. Style 8 is
  the only generator state with a confirmed optical response on this hardware
  (`test_13`, three vertical colour bands, operator-confirmed by eye), so it is
  the control.
- **No optical phase labels.** Serial labels are invisible to a camera, so
  test_14 had to be aligned by inference. Alignment must be carried in the
  optical channel itself.

The current artifact brackets the single variable with controls and blinks a
countable marker before every phase:

```
h713_disp panel-test 0x33 tcon-solid-dclk-normal
```

```
1 blink   style 8 under the stock inverted edge
2 blinks  style 8 under the normal edge
3 blinks  solid all-zero, normal edge
4 blinks  solid all-one, normal edge
5 blinks  fully restored
```

The generator is also switched off between the two solid codes, so a null
result cannot be attributed to the receiver holding its last decoded value
across a same-geometry change. Scoring rules, decided before the run:

- control 1 blank -> the run is invalid; nothing after it counts;
- control 1 banded, control 2 blank -> the normal edge breaks the link, and
  inverted DCLK is correct, which is also what Board B's `panel_config.ini`
  requests;
- both banded -> the solid comparison is meaningful for the first time.

The artifact is `build/out/u-boot-sunxi-with-spl-ddr3.bin`, 915761 bytes,
SHA-256 `8b5912d5a5a253bdf1e1ebffdca2b6c74328b8a19315faa6fc484fcd77d625b5`.

### DISPLAY BRING-UP COMPLETE

Three independent paths now render correctly with `pll_n_plus_1 = 36` applied
through the ordinary panel init:

| path | result |
| --- | --- |
| TCON pattern generator | vivid, geometrically correct red/blue checkerboard at 128px and 32px |
| framebuffer / AFBD / OSD / DE | eight horizontal colour bands, correct order, correct hues, full height |
| vendor `bootlogo.bmp` | renders faithfully |

**Correction: there was never a vertical-collapse bug.** The previous entry
reported the vendor logo "collapsed into a thin horizontal band rather than
occupying its proper height". The logo *is* a thin horizontal band. The BMP is a
black frame whose only content sits in rows 340-380 of 720:

```
row-band mean luminance, bootlogo.bmp downscaled to 36 rows
  rows  0-16    3.0    (black)
  rows 17-18   42.4, 39.0
  rows 19-35    3.0    (black)
```

The projection matched it. The apparent "light field" behind the text is the
projector's black level in a dark room plus camera exposure, not image content.

That fault was diagnosed by comparing the projection against this document's
description of the image -- "a black frame with centered white SMART PROJECTOR
text", which is accurate but reads as though the text is large -- rather than
against the file, which has been in `local/mips-display/research/bootloader_fat/`
throughout. Render the asset before concluding the hardware mangled it.

`fb-vprobe` was built to chase that phantom and is worth keeping anyway: it
independently confirmed the framebuffer path end to end, which no previous test
in this log had done. Eight bands in the right order rules out vertical scale
error, row-repeat, and stride or tiling mismatch in one frame.

## Summary of the bring-up

The single defect was the display PLL at `0x058c0014`. The vendor table leaves
N+1 = 43, giving 1032 MHz and 73.71 MHz of DCLK; the panel needs N+1 = 36,
giving 864 MHz and 61.71 MHz against the 62.00 MHz `panel_config.ini` requests.
At 43 every pattern arrives as a uniform blur carrying colour but no position;
at 36 the panel decodes correctly.

Everything else investigated at length in this document -- OSD plane gates, AFBD
enable and ready bits, the Board-B plane-open bit, framebuffer contents and byte
order, the DCLK sampling edge, CPU_COMM framing, source selection -- was working
the whole time.

### SOLVED: the display decodes correctly at a display-PLL N+1 of 36

The panel produces a **crisp red/blue checkerboard** -- square cells, clean
edges, correct two-dimensional structure -- when the display PLL at
`0x058c0014` is set to N+1 = 36. At the vendor table's N+1 = 43 the same
pattern is the uniform magenta blur every earlier test in this document
recorded. The frame is in `local/lcd-photos/test_20/IMG_0577.MOV` at the
second sweep step.

The arithmetic closes exactly:

```
N+1 = 36   ->  PLL = 24 MHz x 36 = 864 MHz
counter      15421 kHz measured, 864/56 = 15.429 predicted
DCLK         864/14 = 61.71 MHz   (panel_config.ini asks 62.00, 0.46% low)
refresh      59.71 Hz             (1360x760 total; 59.98 Hz nominal)

stock N+1 = 43 -> 1032 MHz -> 73.71 MHz DCLK, 18.9% fast, 71.32 Hz
```

That confirms **K = 14** -- the 7:1 serialisation with a further /2 -- which had
been one of three candidates and could not be resolved by the counter alone.

The original PLL analysis in this document computed the right answer and applied
it to the wrong register. "N+1 = 36 lands at 61.71 MHz, 0.46% low" was correct;
it was written about the CCU's `PLL_VIDEO2`, which does not feed the TCON. The
value transferred unchanged once `clkfind` identified the real PLL.

`h713_panel_cfg_board_b.pll_n_plus_1 = 36` now carries this, patched into the
LogoRegData record for `0x058c0014` alongside the other panel fields.

**Correction to the previous entry.** It reported "no row alternation" from the
`tcon-nsweep` scoring. That claim was produced by a column-only chroma metric
which could not see rows at all, and it is wrong: the N+1 = 36 step has full
two-dimensional checker structure. The operator observed it directly. Prefer the
photograph to the metric when the two disagree, and do not report a property an
instrument cannot measure.

The amplitude ranking in that entry is also unreliable for the same reason: it
scored N+1 = 52 highest at 8.26 against 5.68 for 36, but 52 produces vertical
banding while 36 produces a correct checker. Column amplitude does not
distinguish them.

### BREAKTHROUGH: the pixel clock controls spatial resolution

`tcon-nsweep` stepped the display PLL across six values with the red/blue 128px
checker at each, every step verified by the counter tracking N proportionally
(all six within 0.1% of prediction). Scored from
`local/lcd-photos/test_20/IMG_0577.MOV` by detrended column-chroma amplitude,
which removes the projector's lens falloff and leaves only banding:

| N+1 | PLL | band amplitude | verdict |
| --- | --- | --- | --- |
| 32 | 768 MHz | 5.16 | structure |
| 36 | 864 MHz | 5.68 | structure |
| 40 | 960 MHz | 1.10 | noise floor |
| **43** | **1032 MHz** | **0.97** | **noise floor -- this is the stock setting** |
| 47 | 1128 MHz | 0.76 | noise floor |
| 52 | 1248 MHz | **8.26** | **strongest, visible vertical bands** |

At N+1 = 52 the projected image shows plainly separated vertical bands. At the
stock N+1 = 43 it is the uniform magenta blur every previous test produced.

**This is the first time anything in this project has put spatial content on the
panel.** It also establishes the direction: the pixel clock controls whether
position survives the link, and the vendor table's value sits in the dead zone.

Three cautions, none of which the result needs to be useful.

The response is not a single peak. Structure appears at 32 and 36, disappears
across 40 to 47, and returns strongly at 52. A single correct DCLK would give one
optimum, so this looks more like a beat or lock-range effect than a simple
focus. Do not read N+1 = 52 as "the correct clock" yet.

No step produced a correct checker. At its best the output is vertical bands with
no row alternation, where a 128px checker on 1280x720 should give a 10 by 5.6
grid. Horizontal position is partially resolved; vertical is not.

52 was the top of the swept range and gave the strongest response, so the
optimum may lie beyond it. `tcon-nsweep-hi` extends to N+1 = 50..60.

The earlier reasoning that put DCLK at 73.71 MHz assumed a 7:1 ratio that was
never verified. If N+1 = 52 is near-correct and the panel wants 62 MHz, the
divider is nearer 20 than 14. Treat the ratio as still unmeasured.

### CONFIRMED: 0x058c0014 is the display PLL that drives the TCON

Measured, not inferred:

```
h713_disp init 0x33 quiesce
h713_disp clkfind 0

baseline counter 18421 kHz
perturbing 0x058c0014[15:8] 0x2a->0x29, b8002a00 -> b8002900
counter 18421 -> 18001 kHz (-2.2%), restored to 18432
IN THE CLOCK PATH
```

N+1 going 43 to 42 predicts -2.326%; the measurement gives -2.28%, inside one
quantization step of the counter (~10 kHz at a 100 ms window, which is also the
18421/18432 baseline spread). So the display block's PLL uses the same
`24 MHz * (N+1)` form as the CCU video PLLs, runs at 1032 MHz, and the
free-running counter is PLL/56.

This is the first positive identification in the clock work. Everything before
it -- the CCU chain arithmetic, the PLL_VIDEO2 retune -- computed a correct
number for a PLL that turned out not to feed the display.

**What is still unknown is the divider between the PLL and DCLK.** The counter
is PLL/56 and 56 = 8 * 7, but how that splits between the LVDS serialisation
ratio and any counter prescale is not determined, so DCLK could be 1032/14 =
73.7 MHz, 1032/7 = 147.4 MHz, or 18.43 MHz, and nothing measured so far
distinguishes them. The 73.71 MHz figure elsewhere in this document is one of
three candidates, not a result.

The panel config writes two fields in the neighbouring register, which are the
obvious next candidates:

```
+0x18c4  058c0024  00000000 -> 2f000000  shift 24 mask 0x3f
+0x18c4  058c0024  2f000000 -> 2f000007  shift 0 mask 0x7
```

`clkfind 1` perturbs `0x058c0024[2:0]` from 7 to 6 and `clkfind 2` perturbs
`[29:24]` from 0x2f to 0x2e. A divide-by-7 field moving to 6 shifts the counter
by +16.7%, or +14.3% if the field is N+1; either is unmistakable against the
2.3% just measured. A 47-to-46 change on the other field gives +2.2%, close
enough to the PLL result that it needs the exact number rather than the flag.

Both restore cleanly, so they can run in sequence on one boot after a single
`h713_disp init 0x33 quiesce`.

### CORRECTION: PLL_VIDEO2 is not the panel clock source

The PLL arithmetic below computes the CCU chain correctly and then attributes it
to the wrong PLL. Retuning `PLL_VIDEO2` from N+1 = 43 to 36 proved it: the write
landed -- readback `0xb9002300` -- and the free-running counter did not move by
a single kHz, 18432 before and 18432 after. Lock never dropped either. The CCU's
`PLL_VIDEO2` does not feed the TCON.

The display block has its own PLL. `0x058c0014` reads `0xb8002a00`: the same
`0x2a` in bits 15:8 and near-identical control bits to `PLL_VIDEO2`'s
`0xb9002a00`, so the same N+1 = 43 and the same 1032 MHz. And it is what the
panel configuration actually writes:

```
+0x1694  058c0014  01000000 -> 00000000  shift 24 mask 0x1
+0x18c4  058c0024  00000000 -> 2f000000  shift 24 mask 0x3f
+0x18c4  058c0024  2f000000 -> 2f000007  shift 0 mask 0x7
```

Panel-derived values into `0x058c0014` and `0x058c0024`. The clock path runs
through the display block, not the CCU.

The counter arithmetic is unaffected -- 1032/56 = 18.4286 MHz against 18432
measured is the same 0.02% agreement, just with a different PLL producing the
1032. The computed 516 MHz panel clock and 73.71 MHz DCLK therefore remain
plausible but are now attributed to an unverified source, so treat the figure as
open rather than established.

`h713_disp clkfind` perturbs one candidate field at a time in the display PLL
block and watches the counter, restoring each before the next and aborting if
the counter fails to return to baseline. Whichever field moves the counter is in
the chain. That replaces one build per guess with one boot for the set.

The retune guard is what kept this from becoming another wrong reading: it
required the clock witness to confirm the change before any visual result
counted, and it correctly declared the run meaningless.

### CORRECTION: 0x05880000 is not a raster position counter

Measured with `h713_disp scanrate`:

```
784312 samples in 200000 us (3921 kHz sampling), timing HT=1360 VT=760
high half max 1023, 3599 wrap(s) -> 17995 Hz
low  half max 1023, 3600 wrap(s) -> 18000 Hz
```

Both 16-bit halves are **10-bit** counters -- maximum exactly 1023 -- wrapping
at the same ~18 kHz. A raster position counter for a 1360x760 frame would max at
1359 and 759, and its two rates would differ by a factor of VT. The measurement's
own consistency check caught this: a frame rate of 17995 Hz against a `line/VT`
of 23 Hz is impossible.

The DCLK figure that command printed, 24.48 MHz, is therefore meaningless. It is
`wrap_rate * HT` where the wrap rate is not a line rate. Discard it. The PLL
arithmetic below stands unverified, not refuted.

**Every "scan=... proves the raster is live" claim in this document is void.**
That includes the quiesce warning path, the AFBD and plane gate tests, the
generator runs, and the frame-commit traces. The register moves, so something is
clocked, but nothing in this log establishes that a raster is scanning at the
programmed timing. The claim originated as an assumption about the register's
meaning and was repeated as evidence thereafter.

For the record the counters run at 18000 x 1024 = 18.432 MHz almost exactly,
which is a standard oscillator frequency and not an obvious divisor of the
computed 516 MHz panel clock. One measurement is not enough to say what they are.

`h713_disp regscan [base] [words]` sweeps a register range and reports which
words change, with their observed minima, maxima and change counts. A real
horizontal or vertical counter is identifiable by maxing at HT-1 or VT-1, which
the command prints for the live timing; anything maxing at a power of two minus
one is free-running. Finding the real counter is a prerequisite for measuring
DCLK, and for restoring any liveness check at all.

### RESOLVED: the link carries colour and no spatial information

`test_17` ran the chroma sweep. `local/lcd-photos/test_17/IMG_0568.MOV`, 64.4 s.
The chroma markers were visible at every phase boundary -- the first optical
alignment aid in this project that actually worked -- so the phases are read
directly off the recording rather than inferred.

**The positive control passes.** All three primaries are separately
controllable, measured over the rectangle interior:

| phase | R | G | B | R-B | G-(R+B)/2 |
| --- | --- | --- | --- | --- | --- |
| baseline | 183.4 | 189.4 | 227.9 | -44.5 | -16.3 |
| SOLID RED | **213.3** | 191.5 | 221.0 | **-7.7** | -25.7 |
| SOLID GREEN | 204.2 | **233.0** | 217.5 | -13.3 | **+22.2** |
| SOLID BLUE | 196.7 | 187.9 | **231.8** | **-35.0** | -26.4 |
| CHECKER 128px | 203.3 | 190.9 | 228.5 | -25.2 | -25.0 |
| CHECKER 32px | 199.2 | 189.2 | 226.2 | -27.0 | -23.5 |

The green phase is unmistakable both in the numbers and in the photograph. The
TCON generator, the LVDS serialiser, the panel and the optical engine all
deliver a requested colour correctly.

**Both checkers arrive as a uniform blend.** `CHECKER 128px` reads `R-B = -25.2`
against red at `-7.7` and blue at `-35.0` -- almost exactly their midpoint. The
column profile shows no alternation whatever:

```
baseline       -21 -32 -36 -38 -39 -41 -42 -45 -47 -48 -48 -50 -51 -51 -51 -51 -49 -48 -45
CHECKER 128px  -22 -29 -28 -27 -26 -23 -21 -20 -20 -22 -24 -24 -24 -27 -40 -34 -35 -36 -38
CHECKER 32px   -24 -32 -32 -31 -28 -26 -23 -22 -22 -23 -24 -25 -25 -30 -34 -35 -34 -38 -40
```

A 128-pixel cell is ten cells across a 1280-pixel line and roughly nine samples
wide in this profile: trivially resolvable if it were present. It is not there.
The photograph shows a uniform magenta field. The 32-pixel result agrees but is
undersampled and adds nothing on its own.

**The link carries colour but no positional content. Every pixel receives the
same value -- the spatial average of the pattern.**

The consequence is large, because the TCON pattern generator bypasses the
framebuffer, AFBD, OSD, DE, vblender and mixer entirely. All of them are
therefore exonerated. Every compositor-level investigation in this log -- OSD
plane gates, AFBD enable and ready bits, the Board-B plane-open bit, framebuffer
contents, byte order, the vendor bootlogo control -- was working a layer that
was never the problem. Those results stand as measurements and are worthless as
explanations.

What remains is the pixel clocking and serialisation path between the generator
and the panel's receiver: DCLK frequency, lane and bit mapping, single versus
dual port, and the 7:1 serialisation ratio. A uniform blend is the signature of
a receiver that is not latching per-pixel data at all and is integrating the
line instead.

The highest-value open item is now the one the handoff already lists and nobody
has done: **verify that the project table's PLL and divider sequence actually
produces the 62 MHz `PanelDCLK` the panel asks for.** The current implementation
takes the clock programming from the vendor table without recomputing it. A
DCLK far from the panel's expectation would produce exactly this result --
correct DC colour, no resolvable pixels -- and it is checkable offline from the
`0x058c00xx` register values already captured in every transcript.

This does not explain the `test_13` bands, and that observation should now be
treated as unexplained rather than load-bearing.

### The optical path responds to chroma and ignores luminance

`test_16` ran the bracketed-control build with the DE replay gated out of the
generator modes. The console confirms the gate took effect and all three
firmware words survived to the test: `0x051c0014=18000005`,
`0x051c0028=1f300030`, `0x05140054=40000080`. This is the first generator run in
the project with the firmware's PHY and routing configuration standing.

Frame analysis of `local/lcd-photos/test_16/IMG_0567.MOV` (47.2 s) shows exactly
two optical events, matching the two positive controls. Neither reproduces the
`test_13` colour bands, so **by the pre-declared rule this run is invalid and
the solid comparison downstream of it does not count.** Gating out the replay
did not restore the banded response.

But the controls are not blank. Both produce a large, repeatable shift of the
whole field, measured as R-B across the rectangle interior:

```
baseline   26  24 -17 -20 -23 -24 -25 -25 -28 -30 -32 -33 -35 -36 -38 -39 -42
CONTROL 1  16 -17 -21 -21  10   9   8   8   6   6   4   3   2   2  -2  -4  -5
CONTROL 2  32   6 -18 -20  10  11  10   9   8   7   5   4   3   3   1  -2  -6
solids     26  24 -16 -20 -23 -24 -26 -26 -28 -30 -32 -33 -35 -36 -38 -39 -43
```

Two things follow.

**The DCLK edge has no optical effect.** Controls 1 and 2 differ only in
`0x05800000[24]` and their profiles are indistinguishable. This is the first
same-boot A/B of that bit under an identical source, and it closes the DCLK
avenue that has been open since the `tcon-dclk` run. The earlier "phase-locked
edge effect" was a live-resynchronisation transient, not a configuration result.

**There is no spatial information in the link.** The profile is a smooth
gradient in every phase; maximum adjacent-column contrast *falls* during the
controls (48.3 and 44.2) versus baseline (70.8, which is the left column). A
128x128 checker would raise it sharply. The generator changes the field
uniformly and carries no positional content.

The stronger pattern is a perfect correlation across five generator styles and
four bench runs:

| style | cell size | colour words | words differ in | observed |
| --- | --- | --- | --- | --- |
| 8 red/blue checker | `0x00800080` | `3f000000`/`000000ff` | **chroma** | **visible** |
| 1 b/w checker | `0x00800080` | `00000000`/`3fffffff` | luminance | no change |
| 2 solid black | `0x00000000` | `00000000`/`00000000` | luminance | no change |
| 3 solid white | `0x00000000` | `3fffffff`/`3fffffff` | luminance | no change |
| marker blink | `0x00000000` | `3fffffff`/`3fffffff` | luminance | never detected |

Every style that differs in chroma is visible. Every style that differs only in
luminance is invisible, independent of cell size. A projector light engine with
dynamic contrast or auto-brightness would produce exactly this: it normalises
luminance changes away and cannot normalise a hue change.

If that reading holds, **every luminance-based result in this log is void** --
the solid black/white comparisons, the monochrome checker, the optical blink
markers, and the "field became lighter/darker" observations, including the
inversion-like response attributed to styles 2 and 3. Those did not measure the
link. Diagnostics must be rebuilt on chroma-differing sources before any further
optical conclusion is drawn.

This does not yet explain why `test_13` produced three spatial bands from the
same style-8 source that now produces a uniform shift.

### RESOLVED: the firmware sets those bits, and the DE replay destroys them

A four-point probe across a single boot settles the ownership question that two
sessions of disassembly could not:

| register | ARM records applied | MIPS ready | MIPS quiesced | after DE replay |
| --- | --- | --- | --- | --- |
| `0x051c0014` | `18000000` | **`18000005`** | `18000005` | `18000000` |
| `0x051c0028` | `00000030` | **`1f300030`** | `1f300030` | `00000030` |
| `0x05140054` | `40000000` | `40000000` | **`40000080`** | `40000000` |

The coprocessor sets `0x051c0014[2:0]=5` and `0x051c0028[28:16]=0x1f30` by MIPS
readiness, and `0x05140054[7]` later, during application readiness. Replaying DE
block 5 returns all three to their pre-release values.

This **contradicts the static analysis**, which resolved 604 of the firmware's
845 register-helper call sites and found none of them touching these three
words. The unresolved remainder computes addresses from runtime tables, and the
answer was in there. Treat the static write map as a lower bound on firmware
register access, never as an exhaustive one.

The current artifact skips the DE replay in the TCON generator modes, which
take nothing from the OSD/AFBD path and were therefore paying pure damage for
it. Artifact `build/out/u-boot-sunxi-with-spl-ddr3.bin`, 915761 bytes, SHA-256
`fe322515e2a77bdbad30c37308941039de72258a69f500305a9230b1025d1760`.

**This does not by itself explain the generator's boot-to-boot
irreproducibility.** `test_13` produced three colour bands on this same code
path with the replay included. Removing a demonstrably destructive step is
correct regardless; whether it restores the banded response is the open
question for the next run.

### The DE replay clears LVDS PHY and routing bits

Independently, test_14's two dumps -- taken after firmware init with the MIPS
quiesced, and again after the DE block 5 replay -- differ in four words:

| register | after firmware init | after DE re-assert |
| --- | --- | --- |
| `0x051c0014` LVDS PHY | `18000005` | `18000000` |
| `0x051c0028` LVDS PHY | `1f300030` | `00000030` |
| `0x05140054` display-route | `40000080` | `40000000` |
| `0x0560030c` AFBD mux | `00804258` | `0080c258` |

`quiesce` is set for every TCON mode, so `h713_disp_reassert_osd()` runs before
every generator test performed so far, clearing two LVDS PHY words and a
display-route bit shortly before the panel is asked to decode a pattern. This
is a candidate for the missing structure but is not yet a conclusion: `test_13`
took the identical path and still produced three colour bands. The TCON
generator needs nothing from the OSD/AFBD path, so gating the replay out of the
generator modes is a cheap single-variable test -- but it must wait until a run
with positive controls establishes what a live link looks like on that boot.

The separate source trace patches every instruction only after checking the
authenticated image. That path is already closed on hardware; reproduce it
only if needed with:

```
h713_disp mips-comm-trace 0x33
h713_disp commcall eaf13de5 chan=0 pid=8b8f32b0 2
h713_disp commtrace
h713_disp commstate
```

`callback=0x5102 event=0 new=2 queue=00000000` proves correct submission.
Worker `0x5202` means the requested source was already selected; worker
`0x5203` proves the full asynchronous transition ran and moves the remaining
fault boundary downstream into source-buffer publication/composition. Worker
stage zero after callback `0x5102` means the object worker did not dequeue the
accepted event.

The trace-cleanup artifact itself (SHA-256 `1b03781e...`) has now repeated the
same two-call result: CALL ends at `e011`, RETURN_ACK ends at `f003`, and the
global HISR queue send returns zero. Removing the generic `e002` overwrite did
not change protocol behaviour and makes the persistent CALL stage accurate.

Static disassembly resolves the apparent contradiction. The RETURN_ACK
interrupt handler at `0x8b11f804` clears that bit at `0x8b11f9bc..c4`, then
only queues action type 3 at `0x8b11f9dc`. The deferred ACK action at
`0x8b11ec9c` later reads the wait pointer from ACK sequence `+0x70/+0x74` and
posts it through `osal_semaphore_set` at `0x8b11edb4`. Only after that post can
the blocked sender resume at `0x8b120504`. Thus bit-clear proves interrupt
receipt, not completion of the ACK action; the deferred action is now the
boundary that the expanded hardware trace has now proven successful.

The current trace instruments every one of those boundaries plus the entire
post-ACK cleanup. In trace mode, `commcall` waits up to one second for
`0xc013` (the sender returning to its CALL worker) before consuming ARM
ReturnCmd or recycling FreeReturn. It prints the exact session and 64-bit wait
pointer copied into the ACK. This prevents a merely consumed ACK publication
from being reported as a completed round trip and distinguishes a wakeup
failure from a cleanup failure in the same run.

The channel is live and internally consistent. `pcpu_comm_dev=0x8b254410`,
slot 0 has key `0xb8f32b00`, channel 0, pid `0x8b8f32b0`, and a populated
semaphore object. The live call-table entry at `0x8e31e8a8` also settles an
important disassembly error: entry 989 is `THal_Vp_GetImageBufferAddr`
(`0x2f02f7dd`), but its handler is **`0x8b10adb0`**, whose complete body is
`jr ra; nop`. `0x8b10a110` is the `THal_Vp_DisableBlackScreen` adapter and
must not be used to reason about this CALL.

The first communication-trace build returned `stage=0x0000`. In the same run,
`FreeCall wr` wrapped 20 -> 0 and MIPS `CallCmd` became `rd=1 wr=1`, proving
that the worker dequeued and recycled the descriptor but never reached the
handler-return marker. This rules out `SendComm2CPUEx`, its semaphore, the
receiver FIFO-space check, and FreeReturn allocation as the current stall.

The second trace build returned **`stage=0xa001`** with the same ring state.
The worker therefore enters `Comm_ReleaseFreeCall`, and that helper commits the
slot back to the FIFO (`wr: 20 -> 0`), but the helper never returns to routine
lookup. Its remaining operations are a sequence-semaphore post and two log
calls, so the current build instruments those internal boundaries.

The third trace build returned **`stage=0xa004`**, not `a005`: the worker is
still inside `fifo_requestItemWr()` after it updates `wr`, before it attempts
the sequence-semaphore post. The semaphore wrapper at `0x8b253e20` is also
valid and points to `0x8b914880`, so the semaphore was another false lead.

This exposed the exact ARM initialization error. The vendor initializer starts
each free FIFO at `wr=0` and pushes twenty slots through
`fifo_requestItemWr()`. Because tracking is enabled, those pushes leave
`peak_count=20`. U-Boot populated the ring directly and set `wr=20`, but left
`peak_count=0`. On the first recycle, the helper restores `count=20` and
`fifo_getCount()` asserts that `count > peak_count + 1`, then spins forever.
The current source publishes `peak_count=20` for every pre-populated
FreeCall/FreeReturn ring, matching the final state of the vendor algorithm. It
also updates the peak when U-Boot manually enqueues an ARM-side `ReturnCmd`,
preserving the same tracking invariant throughout the reply handshake.

The trace now also covers descriptor recycling, routine lookup, the pre-call
logger, and the indirect handler entry. It records the last stage reached
through the MIPS uncached shared-memory alias:

One concrete risk now exposed by the correct handler is that the worker passes
`sp+0x124` as the output-count pointer but does not initialise that word on the
successful lookup path. The no-op handler does not write it. A fresh ThreadX
stack is likely zero-filled, but that is an assumption; a stale non-zero count
would send the worker through its output-copy loop before `SendComm2CPUEx`.
That case will stop at `0xc001`, while any send-side stall reaches at least
`0xc002`.

| stage | last proven point |
| --- | --- |
| `0xa001` | entered `FreeCall` recycling |
| `0xa002` | release semaphore acquired; pre-commit log entered |
| `0xa003` | pre-commit log returned; requesting FIFO write slot |
| `0xa004` | committing the recycled slot to `FreeCall` |
| `0xa005` | posting the release semaphore |
| `0xa105` | release-semaphore post returned an error |
| `0xa006` | release-semaphore post succeeded |
| `0xa007` | final release log entered |
| `0xb001` | routine lookup entered; recycling returned |
| `0xb002` | routine lookup returned |
| `0xb003` | handler arguments prepared; pre-call log entered |
| `0xb004` | component handler entered |
| `0xc001` | component handler returned |
| `0xc002` | `SendComm2CPUEx` entered |
| `0xc003` | blocked in the send-semaphore wait |
| `0xc103` | send-semaphore wait returned an error |
| `0xc004` | send semaphore acquired |
| `0xc005` | checking receiver `ReturnCmd` FIFO space |
| `0xc006` | receiver FIFO has space |
| `0xc007` | attempting to allocate `FreeReturn` |
| `0xc008` | publishing RETURN through `SendLow` |
| `0xc009` | waiting for `RETURN_ACK` |
| `0xd001` | RETURN_ACK interrupt queued the deferred action |
| `0xd005` | `queueAction` returned to the RETURN_ACK interrupt handler |
| `0xd002` | deferred ACK action reached the sender-wakeup path |
| `0xd003` | deferred action entered `osal_semaphore_set` |
| `0xd103` | sender wait-semaphore post returned an error |
| `0xd004` | sender wait-semaphore post succeeded |
| `0xc010` | `SendComm2CPUEx` resumed after RETURN_ACK |
| `0xc011` | `SendComm2CPUEx` is releasing its send semaphore |
| `0xc111` | send-semaphore release returned an error |
| `0xc012` | send semaphore released successfully |
| `0xc013` | `SendComm2CPUEx` returned to the CALL worker |

The build now records the CALL interrupt/HISR lifecycle independently at
trace `+0x0c`, so asynchronous worker activity cannot overwrite it. The raw
return from the global HISR queue send is retained at trace `+0x08`:

| CALL stage | last proven point |
| --- | --- |
| `0xe001` | CALL interrupt is invoking `queueAction` |
| `0xe004` | `queueAction` returned to the CALL interrupt handler |
| `0xe005` | CALL HISR wrapper invoked the dispatcher |
| `0xe006` | `command_action` entered for CALL |
| `0xe007` | enqueueing the high-priority CALL worker |
| `0xe008` | sending CALL_ACK through `SendAckLow` |
| `0xe009` | `SendAckLow` returned |
| `0xe010` | `command_action` is returning to the CALL HISR wrapper |
| `0xe011` | CALL HISR dispatcher returned |

RETURN_ACK wrapper completion is retained separately at trace `+0x10`. This
tests whether the shared queue consumer is still trapped in the previous
callback when CALL #2 is enqueued:

| ACK stage | last proven point |
| --- | --- |
| `0xf001` | `ack_action` is returning to the RETURN_ACK HISR wrapper |
| `0xf002` | RETURN_ACK HISR dispatcher returned |
| `0xf003` | RETURN_ACK HISR wrapper is returning |

The trace only changes the authenticated `4380f1b3...` image after its SHA-256
check, validates every original instruction before patching, and is mutually
exclusive with the startup and stability traces. Run exactly once after a
power cycle:

```
h713_disp mips-comm-trace 0x33
h713_disp commcall 2f02f7dd chan=0 pid=8b8f32b0
h713_disp commstate
```

The first `commcall` now reports the decisive ACK-action stage automatically;
`h713_disp commtrace` can read it again. Only if the first reaches `0xc013`
and returns normally, run the second call:

```
h713_disp commcall 2f02f7dd chan=0 pid=8b8f32b0
h713_disp commstate
```

The current build containing this trace, the source-worker extension, all
queue fixes, returned-parameter capture, guarded picture-mode marshalling, the
exact AFBD frame submission, MIPS-owner quiesce, selected-plane gate, static
bar, exact Board-B vendor-logo diagnostics, and the corrected Board-B
`0x0524c01c[0]` plane-open gate, red/blue and monochrome TCON checkers, the
exact solid-black/solid-white TCON discriminator, and corrected I2C device
labels is
`build/out/u-boot-sunxi-with-spl-ddr3.bin`, 911,665 bytes, SHA-256
`39b280c59cda2123f5e59eb77c5e0ef9ad45a974c582370031ea17d7f9686fdd`.

Forty-four complete consecutive CALL/CALL_ACK/RETURN/RETURN_ACK transactions,
including ACK publications, deferred wakeups, sender cleanup, slot recycling,
and repeated ring wrap, are hardware-proven on one boot. Longer-duration,
concurrent, and opposite-direction traffic remain useful transport coverage.
The zero-parameter no-op call used for the ring test did not exercise
parameter/output marshalling; the guarded hardware test above now closes that
case. The same source rejects the unsafe
`commcall db=` override, supports all ten CALL parameters, validates FIFO
headers before following pointers, and expands `h713_disp dump` over the
missing DE/LVDS ranges.

# SESSION HANDOFF -- 2026-07-31 (evening; superseded where noted above)

Read this first. It supersedes anything below it that it contradicts,
**including the earlier handoff of the same date.**

## Where the two threads stand

**The panel lights.** PF6 is board B's `panel_power_en`; with it asserted the
firmware's internal colour source is plainly visible. Every earlier "not
working" verdict was measured through an unpowered panel and is void.

**The OSD still does not display.** The firmware owns the LVDS PHY and the
raster -- proven by holding the MIPS in reset, where the PHY registers and the
scan counter all read zero and nothing reaches the panel at all.

**CPU_COMM works in both directions. Proven on hardware.** The ARM sent a CALL,
the firmware accepted it, consumed the descriptor, and acknowledged over the
mailbox. Two ARM-side defects had to be fixed together, because either one
alone produced the identical symptom:

1. **The doorbell word is the bare message type, 0..3.** A CALL is
   `0x00000000`. We were sending `0x00000002`, which is CALL_ACK.
2. **`share_seq[+0x08]` bit 2 is the presence gate**, and U-Boot published
   zero there. Every handler returns immediately when that bit is clear, so
   *no* doorbell value could ever have worked.

That is why five encodings "behaved identically": the flag, not the encoding,
was the invariant blocker. The previous handoff's conclusion that the encoding
is not the variable was half right for the wrong reason, and its instruction
not to re-test encodings is now withdrawn.

The bench transcript, `commcall 2f02f7dd` (`THal_Vp_GetImageBufferAddr`):

```
doorbell 0x00000000 rung + IRQ pulsed; fifo count now 0
MIPS drained the FIFO after 0 ms
firmware accepted the message after 0 ms (state bit 2 cleared)
published idx changed -- consumed
FreeCall  rd=1 wr=20  idx=14 state=00
```

`idx=14` is hex -- 20, the empty-slot sentinel that `command_action` writes
back at `0x8b120f84`. The firmware did not merely read the descriptor, it
reset it. Then, at `0x03003164`/`0x03003174` -- the **MIPS-to-ARM** half of the
mailbox, which nothing on the ARM side had ever read:

```
md.l 0x03003164 1   ->  00000001
md.l 0x03003174 1   ->  00000002      CALL_ACK
```

which is exactly the acknowledgement mapping at `0x8b11eadc` (`0 -> 2`,
`1 -> 3`). Both directions of the encoding model are now confirmed against
hardware rather than inferred.

## Current state in one screen

Everything below was measured on the DDR3 bench board this session unless
marked otherwise.

**Works, hardware-proven:**

| step | evidence |
| --- | --- |
| doorbell delivery | FIFO drains in 0 ms |
| message recognised | `share_seq[+0x08]` bit 2 cleared by the firmware |
| descriptor consumed | `share_seq[+0x10]` reset to `0x14` (the sentinel) |
| acknowledgement | `0x00000002` CALL_ACK read at `0x03003174` |
| channel resolved | `chan=0 pid=0x8b8f32b0`, key `0xb8f32b00`, slot 0 |
| worker dequeue | staging `CallCmd rd=1 wr=1` |
| slot recycled | `FreeCall wr` wraps 20 -> 0 |
| routine located | entry 989 read live; handler `0x8b10adb0` is a valid no-op |

**Does not work:** no RETURN is ever published. `FreeReturn` and `ReturnCmd`
never move, no second doorbell is rung, and the worker does not come back to
its dequeue loop -- so exactly **one CALL per boot** is possible.

**The four ARM-side defects fixed to get here**, all in
`external/u-boot/arch/arm/mach-sunxi/h713_mips.c`:

1. doorbell word is the bare message type; a CALL is `0x00000000`
2. `msg[+0x06]` bit 2 (`MSG_FLAG_SENT`) is the presence gate
3. `chan`/`pid` must address a registered channel
4. the MIPS-to-ARM mailbox at `0x03003164`/`0x03003174` was never drained

**Ruled out this session, with evidence -- do not re-test:**

- the MIPS-owned CallCmd/ReturnCmd staging FIFOs: the MIPS builds all four of
  its own (`cap=21 isz=4`, MIPS-local rings). This did not validate the
  separately owned ARM-side headers; see the 2026-08-01 handoff.
- the selected routine handler: `GetImageBufferAddr` points to the two-word
  no-op at `0x8b10adb0`; `0x8b10a110` instead belongs to
  `DisableBlackScreen` and calls `0x8b149948`
- the call-table entry: read live, `comp_id`, name and handler all correct
- the channel's call semaphore: a real object, and its post **succeeds**
  (`0x8b103504` returns 1 on both branches)
- the per-CPU `Seq` semaphores: both exist, named, `count=1 capacity=0x20`,
  and the get takes the acquire path
- the worker being asleep on `0x8b232c00`: it *posts* that, never waits on it
- `msg[+0x01] = 1`: tried, regressed the channel match, reverted

**Superseded twice:** the static audit placed the wedge at the receiver
staging-FIFO space check, but the next hardware run published a valid
`cap=21` header and still produced no RETURN. The guarded communication trace
in the current handoff now distinguishes every blocking point across that
path.

**Why the firmware's own log is not available:** it uses SEGGER RTT at
`0x4bd01000`, and the Terminal channel's `WrOff` is 8 -- the assert strings go
to a UART instead. `display_cfg.xml` carries no logging settings, so there is
no reroute from the files we load. See the RTT section below for the buffer
addresses.

## How the RETURN gap was narrowed

### The MIPS-owned staging FIFO is healthy; the ARM-owned half needed fixing

`command_action` hands an accepted CALL to `0x8b11d544`, which allocates from a
FIFO at **`share_seq + 0x20`** -- not the FreeCall ring at `+0x78`. The Linux
driver names this the **CallCmd staging FIFO**: header at `+0x20`, name
`"CallCmd"` at `+0x40`, capacity 21, item_size 4, `base_addr` pointing at the
**receiver's own local memory**. Neither U-Boot nor `0x8b1197d4` writes
`+0x20..+0x3f`, which made "the MIPS never built it" look like the answer.

It is not. On hardware the MIPS builds all four of its own:

```
cpu=1 dir=0 idx=0  staging +0x20 CallCmd    rd=0 wr=1 cap=21 isz=4 base=8b253e24
cpu=1 dir=0 idx=1  staging +0x20 ReturnCmd  rd=0 wr=0 cap=21 isz=4 base=8b253ed4
```

The `cpu=0` rows are the ARM's receive-side staging FIFOs. Their payload rings
may be empty while U-Boot polls, but their headers still require valid
`capacity`, `item_size`, and `base_addr` fields: the remote sender checks this
FIFO for space before publishing. Leaving the zeroed header in place blocks a
MIPS-to-ARM RETURN before it can allocate a FreeReturn slot. Publishing the
valid header was therefore necessary, but the subsequent hardware run proves
it was not sufficient: `FreeReturn` still did not move.

### What the indices proved, before the channel was addressed correctly

*This subsection describes the state with `chan=0 pid=0`, i.e. before the
channel fix. It is kept because it is how the channel requirement was found.
With `chan=0 pid=0x8b8f32b0` the lookup succeeds and `rd` advances to 1.*

After one CALL, `wr` advanced to 1 and `rd` stayed 0. The message was pushed
and never popped. `0x8b11d544` does the push **before** it does anything else:

```
0x8b11d5a4  0x8b11825c(share_seq + 0x20)      ; allocate a ring position
0x8b11d5b4  0x8b118430(share_seq + 0x20)      ; COMMIT -- wr++ happens here
0x8b11d5b8  *slot = msg
0x8b11d5d4  msg[+0x0A] |= 0x10                ; "in work queue"
0x8b11d5ec  0x8b11ccec(dev + 0x18, key)       ; session lookup -- FAILS
0x8b11d62c  beqz -> 0x8b11d8dc                ; error path
0x8b11d93c  return -2
```

`0x8b1212a0` never checks that return value, so the CALL_ACK goes out anyway
and the message is abandoned in the FIFO. Every observation is accounted for.

### The error, in the firmware's own words

The path at `0x8b11d8dc` logs:

```
ERROR!!! no Channel for chan:%d, pid:%d, pCommPara=%p, index=%d,
         SessionId=%x, tgetCpu=%d, funcId=%lx
```

Decoding the varargs against the stack slots it fills, the message fields are:

```
chan      = msg[+0x00]        index     = msg[+0x04]
pid       = msg[+0x10]        SessionId = msg[+0x0C]
tgetCpu   = msg[+0x02]        funcId    = msg[+0x28]
```

so the kernel header's `src_cpu` at `+0x00` and `sequence` at `+0x10` are
really **`chan`** and **`pid`**. That is the second field mislabelled in that
struct, after `+0x02`.

`0x8b11ccec` is the raw lookup: a 16-entry direct-mapped table of 48-byte
records at `dev + 0x18 + 0x9c`, keyed by

```
key = (pid << 4) | (chan & 0xf)
```

matching the Linux driver's `Comm_AddNewChannel`, which builds
`channel_id = comp_id | (cpu << 4)` -- same packing, different names. U-Boot
memsets both fields, so we ask for `chan=0, pid=0`, and no channel is
registered for it.

### Where channels come from

`0x8b122554` is the channel-open API. It takes a `pCommPara` block, computes
the same `key = (pid << 4) | (chan & 0xf)`, calls `Comm_QueryChannel`
(`0x8b11ce08`, matching the Linux driver's signature exactly), and on a miss
calls `0x8b11ce34` to add one. Its only caller is `0x8b12486c`, inside the
**routine-registration** path -- so the firmware's own 82 registrations are
what populate this table, and the fields come from:

```
pCommPara[+0x00] u16  chan       (from $s2 at the registration site)
pCommPara[+0x02] u16  TargetCPU  getCurCPUID() = 1
pCommPara[+0x04]      pid        0x8b15be70 -> 0x8b104fac, tx_thread_identify()
pCommPara[+0x08]      comp_id    0x8b1249d0, the 0x123456-seeded CRC
```

**`pid` is a runtime ThreadX thread identifier.** It is whatever thread ran the
registrations on that boot, so it cannot be derived from `display.bin` at all
and must be read from the live table. Do not try to guess it.

Note this is a different `pid` from the one in the routine *name*
(`<name>_<cpu_id>_<pid_low12>` with `pid_low12 = 000`), which feeds the comp_id
hash and is 0 for firmware-side registrations. Two unrelated fields, same word.

### Reading it: `h713_disp commdev`

```
key  = (pid << 4) | (chan & 0xf)
idx  = ((key >> 2) & 0xc) | (key & 3)      = (pid & 3) << 2 | (chan & 3)
rec  = pcpu_comm_dev + 0x18 + 0x90 + 48*idx
hit  = rec[+0x0c] == key,  then rec[+0x02] == chan and rec[+0x08] == pid
```

`commdev` resolves `pcpu_comm_dev` from `[0x8b22efe4]`, converts KSEG to the
ARM alias, and dumps all 16 slots. `commcall` now takes `chan=` and `pid=` so
the values it reports can be used on the same boot without a reflash.

Both use an **invalidating** read. A plain `md` of firmware BSS returns the
zeros U-Boot left before the coprocessor started -- that is why
`md.l 0x4b253e24` showed all zeros on a boot where the FIFO indices clearly
proved the MIPS had written.

### What the table actually holds (read on hardware)

Exactly one live channel. Slots 1..15 are `0xffffffff`, the same free sentinel
the call table uses.

```
pcpu_comm_dev = 0x8b254410
table         = 0x8b2544b8   (ARM 0x4b2544b8)

[ 0] key=b8f32b00  chan=0000  pid=8b8f32b0   <== the only live row
```

It checks out against the addressing: `key = (pid << 4) | chan =
(0x8b8f32b0 << 4) | 0 = 0xb8f32b00`, and
`idx = ((key >> 2) & 0xc) | (key & 3) = 0`, so it sits in slot 0.

`pid = 0x8b8f32b0` is the same owner pointer that appears at `+0x04` of every
call-table entry, which is what a `tx_thread_identify()` value should look
like -- the one thread that registered all 82 routines.

So the CALL to send is:

```
h713_disp commcall 2f02f7dd chan=0 pid=8b8f32b0
```

**Trap, and it cost a run:** `commdev` originally printed `pid` in decimal while
`commcall` parses hex, so `2341417648` was read back as `0x41417648`. Both are
hex now. Always check the `key`/`channel slot` values echoed in the published
line before trusting an attempt.

### The channel is right, and the receive thread now stalls past it

`commcall 2f02f7dd chan=0 pid=8b8f32b0` behaves **differently** from every
earlier send, which is what proves the addressing is now correct:

```
                       chan=0 pid=0        chan=0 pid=8b8f32b0
state bit 2 cleared    yes                 yes
share_seq[+0x10]       reset to 0x14       stays 0x03      <-- diverges
CALL_ACK returned      yes                 none
```

With the lookup failing, `0x8b11d544` returned -2 and `command_action` ran to
completion, writing the empty marker back at `0x8b120f84` and sending the ACK.
With the lookup succeeding it never gets there, so the divergence is inside
`0x8b11d544`'s hit path at `0x8b11d7a0`:

```
0x8b11d7cc   s4 = channel_record + 0x10        ; the channel's call semaphore
0x8b11d808   0x8b15c1d0(s4)                    ; osal_semaphore_set -- POST
0x8b11d810   beqz v0 -> 0x8b11d858             ; log "_r=0", return 0
             ...else assert, then b . at 0x8b11d850   <-- infinite loop
```

**Correction to an earlier reading in this document.** `0x8b15c1d0` is
`osal_semaphore_set` -- the *post* -- not a wait. The success target at
`0x8b11d858` logs `'osal_semaphore_set()->_r=%d, sem = %p'` with `_r=0` and the
object just operated on, which fixes the operation's identity. The wait with a
timeout is `0x8b15c0f8`, and `0x8b15c27c` is neither -- it takes an out-pointer
and returns a value through it. Anywhere this document earlier described
`0x8b15c1d0` as "pending on a semaphore" (notably in the `SendComm2CPUEx`
notes), read *post*.

So a correctly addressed CALL posts the channel semaphore and either that post
fails and the thread spins at `0x8b11d850`, or it blocks inside. Either way the
CPU_COMM receive thread is stuck and the board needs a power cycle. The LISR
still runs -- interrupt context is unaffected -- so a later send would still
clear the state bit while never being processed. Do not read that as progress.

`0x8b15c1d0` also has an ISR-context branch at `0x8b15c218` which stores to
`0x8b232c04` and raises a CP0 software interrupt (set `Cause` IP0, then clear).
That address is adjacent to the worker semaphore `0x8b232c00`, which is worth
remembering when chasing how the worker is ever woken.

`commdev` now dumps the object behind `record[+0x10]`, checking for ThreadX's
`'SEMA'` tag at `+0x00` and printing the count at `+0x08`. If it is not a valid
semaphore, the post failing is explained outright.

### Where that leaves the next session

There are two candidate routes and they need to be told apart before any code
is written:

1. **A channel must be opened first.** `0x8b11d948` -- logged as
   `Comm_GetCallbyChannel`, called only from the worker thread `0x8b123b10` --
   is a get-**or-create** wrapper: it calls the raw `0x8b11ccec`, and on a miss
   creates one, logging `chan%d: Chanpid:%x, new call semi:%p got!`. It also
   pops the staging FIFO at `0x8b11dc0c`. So the create path exists and the
   worker owns it.
2. **The worker is asleep.** `0x8b123b10` blocks on the semaphore at
   `0x8b232c00`. Its only three references in the whole image are the C-runtime
   BSS clear at `0x8b1b1164`, the create at `0x8b1243c4`, and this wait at
   `0x8b123c74`. **Nothing found so far signals it.** If that survives a closer
   look, the worker never runs, the channel is never created, and no CALL can
   ever complete regardless of what the ARM sends.

Read the worker `0x8b123b10` and settle (2) first -- it is cheap, static, and
it decides whether (1) is even reachable. If the worker is genuinely unsignalled
from the firmware side, then the signal has to come from something the ARM does,
and that is the next thing to find in `display.bin`.

Do not guess a `chan`/`pid` pair and retry blind: the lookup is a direct-mapped
table read at `dev + 0x18 + 0x9c + 48*i`, which the ARM can read directly
(`dev = 0x8b254410`, ARM-physical alias `0x4b254428 + 0x9c`). Dump it first and
see whether any channel exists at all.

## What is settled, and must not be re-derived

- `panel_config.ini`: the DT/INI merge, the bitfield-insert helper at
  `0x4a024894`, all 32 patch sites, implemented and verified live (18 patched,
  8 guarded). The compare at `+0x24e12` matches **either** `0x0524c010` or
  `0x0525c000`; transcribing one leaves the DE at 1440x741 under a mixer at
  1360x760.
- No ARM-side difference from stock remains. Every MMIO literal in stock's
  fastlogo was enumerated and diffed.
- `0x05880000` is a live scan counter. This document previously claimed no
  scan-liveness signal existed, which sent the investigation to `0x05880FE0` --
  a constant -- for months.
- AFBD is clocked, globally enabled, correctly addressed, and its trigger
  latches. Not the fault.
- The CPU_COMM master init, decoded and implemented: 8 share_seq at
  `0x98 + 9760*cpu + 4880*dir + 2440*idx`, 5 list heads, a 256-record pool.
- The routine map: all 85 names with comp_ids, verified three ways.
- The msgbox is **gated from cold** and must be enabled at `0x0200171c`
  (bits 0 and 16) **before reset release**, or the firmware never arms its
  receive side.

## The notification path, end to end

Every hop below is read out of `display.bin`; none of it is inferred.

```
msgbox IRQ 4
  -> LISR 0x8b121698 (./msgbox.c)
       walks the registered channel list at [0x8b2543d8]
       while (readl(0x03003864))            ; RX FIFO count, port 1
           word = readl(0x03003874)         ; RX MSG_DATA,   port 1
           handler[+0x14](word)             ; $a0 = the raw word, only arg
       writel(0x03003824, 1 << 2)           ; ack status, port 1
  -> channel callback 0x8b121d78
       cb = [0x8b2543f0]; if (!cb) return
       tail-call cb($a0 = word, $a1 = 0)    ; <-- $a1 is HARDCODED ZERO
  -> cpu_comm_cb 0x8b122678 (./trid_cpucomm_hal.c)
       logs "******** cpu_comm_cb : comm_type: %d, cpu_type=%d"
       cpu_type 0 -> 0, 2 -> 1, else 2      ; always 0 here, so PLF-CPU
       switch (comm_type)                   ; the WHOLE 32-bit word
         0 -> 0x8b11f0a4(cpu)   CALL
         1 -> 0x8b11f360(cpu)   RETURN
         2 -> 0x8b11f61c(cpu)   CALL_ACK
         3 -> 0x8b11f804(cpu)   RETURN_ACK
         default -> silently dropped
  -> queueAction 0x8b11ef00(index, cpu)     ; ./cpu_comm_core.c
       asserts ctx.cpu == cpu and ctx.index == index
       osa_hisr_activate(ctx)  ->  tx_queue_send([0x8b2543e4], &ctx, 0)
  -> HISR worker pops ctx, runs ctx[+0x14]
  -> dispatcher 0x8b1212cc(ctx) routes on ctx[+0x1c] = index
```

### Consequences

**The doorbell word is the message type and nothing else.** There is no
`msg_type << 16` field and no `intr_type` field in what this firmware parses.
The Linux tree's `((msg_type & 3) << 16) | intr_type` packing does not apply
here. A CALL is `0x00000000`.

**Out-of-range words are inert, not fatal.** `cpu_comm_cb` drops them without
dispatching. The old warning that a bad type hangs the firmware was about
`0x8b1212cc`, which routes on `ctx[+0x1c]` -- a value fixed at init to 0..3 and
never derived from the message. It can never be out of range. Doorbell
experiments are cheap and safe.

**The handler-table order was recorded backwards.** The four HISR records are
named from the format strings the init passes to `osa_hisr_init`:

| index | name | table entry (cpu 0 / cpu 1) | dispatched by word |
| --- | --- | --- | --- |
| 0 | `"%s CALL HISR"` | `0x8b121410` / `0x8b121418` | 0 |
| 1 | `"%s RETURN HISR"` | `0x8b1214cc` / `0x8b1214d4` | 1 |
| 2 | `"%s CALL_ACK HISR"` | `0x8b121588` / `0x8b121590` | 2 |
| 3 | `"%s RETURN_ACK HISR"` | `0x8b121644` / `0x8b12164c` | 3 |

This matches the Linux enum (`0=CALL, 1=RETURN, 2=CALL_ACK, 3=RETURN_ACK`)
exactly. The earlier claim that `[0]` was RETURN and `[1]` was CALL was wrong,
and it is what made `type 1` look like the answer.

**The `0x8b119354` "open tension" is closed, and it was a false lead.** The
function is `get_cpu_name(cpu)`. It returns `0x8b22efbc + 4` or `+ 0x18`, which
are pointers into a 0x14-stride CPU descriptor array holding the inline strings
`"PLF-CPU"` (cpu 0) and `"DISP-CPU"` (cpu 1). The 4 and 0x18 are **struct
offsets to a name**, used only to format HISR and log strings. They have
nothing to do with the doorbell. `db=00000004` was never meaningful.

### The presence gate -- the actual blocker

`comm_handle_call` at `0x8b11f0a4`, in order:

```
assert cpu < 2
assert cpu != getCurCPUID()                  ; getCurCPUID() == 1, so cpu must be 0
sq = 0x8b1195b8(cpu, 0) = share_seq(1,0,0)   ; = shared+0x026b8, the queue we write
if (!(sq[+0x08] & 4)) { log; return; }       ; <-- THE GATE. Bails here, always.
if ((sq[+0x10] & 0xff) >= 20) assert-hang    ; slot index bound
get_cpu_name(sq[+0x01]); get_cpu_name(sq[+0x00])   ; logging only
sq[+0x08] &= ~4                              ; <-- CONSUMPTION, observable from the ARM
queueAction(0, cpu)
```

U-Boot published `sq[+0x08] = 0`. So the interrupt ran, the FIFO drained in
0 ms, and the handler returned without looking at anything -- which is exactly
what the bench reported, for every encoding, every time.

The publish helper `0x8b11f9ec` takes the state byte from `msg[+0x06] & 0xff`
(the `flags` halfword) at its call site `0x8b12046c`. Bit 2 there is the
kernel patch's own `MSG_FLAG_SENT`. Note this is a *different* field from the
`msg[+0x0A] |= 4` that the same call site performs on `flags2`; the earlier
write-up conflated the two.

**Ordering hazard.** Once bit 2 is up, `sq[+0x10]` must hold an index below 20
or `0x8b11f24c` asserts and spins the firmware forever. Init writes exactly 20
there as the empty marker, so the flag must never be raised over a stale index.
`h713_comm_call` writes the index first and flushes before the doorbell.

### The msgbox register map, derived rather than guessed

`msgbox_init` at `0x8b1217c4` and the channel registration at `0x8b121918`
compute their addresses as `base + (chan << 2) + (field << 10) + (user << 8)`:

```
MIPS RX (ARM -> MIPS)   count 0x03003864   data 0x03003874
                        irq enable 0x03003820 bit 2   status 0x03003824 bit 2
MIPS TX (MIPS -> ARM)   count 0x03003164   data 0x03003174
```

The TX pair is confirmed live: after the first accepted CALL, `0x03003164`
read 1 and `0x03003174` read `0x00000002`. `H713_COMM_MSGBOX_COUNT` in U-Boot
is the **RX** counter `0x03003864` -- correct for proving the MIPS drained our
doorbell, but it says nothing about replies, and for a long time it was the
only mailbox register the ARM ever read.

The firmware registers user 0, channel 1 and enables its own RX bit, so the
ARM's write to `0x03003874` is correct and always was. `msgbox_init` also
drains any stale RX words at startup, logging them as "msgbox fifo garbage
data".

## Next session, in order

1. **`h713_disp mips-test 0x33` then `h713_disp commdev`.** Read-only, same
   boot. This prints the 16 channel slots with their `key`, `chan` and `pid`.
   - **Populated slots** -- take a `chan`/`pid` pair from the table and retry
     `h713_disp commcall 2f02f7dd chan=<C> pid=<P>` on the same boot. The
     FreeCall ring has 20 slots, so several attempts fit in one power cycle.
   - **All empty** -- the firmware registered 82 routines without creating a
     channel, which means `0x8b122554` bailed early at `0x8b11c5f0` or the
     registration path took a different branch. Read `0x8b12486c`'s caller for
     which `chan` (`$s2`) it passes.
2. **The worker is not asleep on `0x8b232c00` -- that reading was wrong.**
   `0x8b123c70` calls `0x8b15c1d0` on it, and `0x8b15c1d0` is
   `osal_semaphore_set`, a **post**, confirmed by the log at its success target
   `0x8b123cc0`. So the worker *signals* `0x8b232c00` at startup and moves on;
   it never waits there. An earlier revision of this document claimed nothing
   posts that semaphore and concluded the worker could never run. Ignore that.

   The worker's real loop is:

   ```
   0x8b123d1c   0x8b11d948(dev + 0x18, key, &msg_out)   ; wait + dequeue
   0x8b123d2c   non-zero return -> error exit
   0x8b123d38   msg_out == NULL -> loop again
   ```

   and `0x8b11d948` is where it blocks, on the **channel's own call
   semaphore** -- the object at `channel_record + 0x10`, which it obtains
   lazily and logs as `chan%d: Chanpid:%x, new call semi:%p got!`. That closes
   the loop with the receive side: `0x8b11d544` posts exactly that semaphore at
   `0x8b11d808` to wake the worker. The two halves of the design fit.

   Which makes the failing post the whole problem. Read on hardware, with the
   reader self-test passing against `getCurCPUID`'s known instructions:

   ```
   record[+0x10] = 0x8b915200

   sem@8b915200: 8b915200 8b915200 8b915200 8b915200
                 00000000 8b915218 ffffffff 8b915218
                 8b915218 00000001 8b91522c ffffffff
   ```

   A real object, not a bad read -- four self-pointers followed by
   self-referencing list heads at `self+0x18` and `self+0x2c`, the same
   `{self, ...}` idiom the shared-memory list heads use. But **no ThreadX
   `'SEMA'` tag**, so whatever `record[+0x10]` addresses, it is not a plain
   semaphore control block.

   The wider dump settles what it is and what the post does:

   ```
   +0x30: 8b955268 8b955268    read/write pointers, both at start
   +0x38: 00000000 00000020    count 0, capacity 32
   +0x40: 00000000 8b00ffff
   +0x4c: 8b499dc8 8b499dc8    suspension list, empty
   ```

   A queue-like object with room, not a full one. Tracing `0x8b103504` with
   those values: `a1 = 0` sends it via `0x8b103780`, `handle[+0x40] == 0`
   returns it to the main body, `count(0) < capacity(0x20)` takes
   `0x8b10364c`, and `handle[+0x24] == 1` takes `0x8b103720` -- where **both**
   branches converge on `0x8b103684`, which returns **1**. `osal_semaphore_set`
   maps a non-zero return to 0, i.e. success.

   **So the post succeeds.** An earlier revision of this section claimed it
   failed and that `0x8b11d544` was spinning at `0x8b11d850`; that was inferred
   from the missing completion without tracing the return path, and it is
   wrong. `0x8b103720` also sets `[0x8b232c04] = 1` and raises the CP0 IP0
   software interrupt -- it wakes a waiter and requests a context switch.

   That relocates the fault to the **worker** side. Its loop retries with no
   blocking of its own:

   ```
   0x8b123d1c   0x8b11d948(dev + 0x18, key, &msg_out)
   0x8b123d38   msg_out == NULL -> branch straight back to 0x8b123d1c
   ```

   so a `0x8b11d948` that keeps returning NULL spins and starves whichever
   thread is running `command_action` -- which matches the symptom exactly:
   `share_seq[+0x10]` never reset, no CALL_ACK, interrupts still serviced.

   **Resolved on hardware: `rd=1 wr=1`. The worker pops it.** With
   `chan=0 pid=8b8f32b0` the entire receive chain runs:

   ```
   CALL_ACK returned                   yes
   share_seq[+0x10] reset to 0x14      yes   command_action completed
   staging CallCmd   rd=1 wr=1         yes   the worker dequeued it
   FreeCall          rd=1 wr=0         yes   firmware recycled the slot
   ```

   `wr` going 20 -> 0 is the 21-capacity ring wrapping: the firmware pushed our
   message slot back onto the free pool. Receive-side bookkeeping is complete
   and correct. **Only the RETURN is missing** -- `FreeReturn` and `ReturnCmd`
   are untouched and no second msgbox word arrives.

### The worker's dispatch, and where it stops

```
0x8b123db8   memcpy(local, msg, 0x68)          ; local copy at sp+0x30
0x8b123dec   0x8b118cb0(share_seq, msg)        ; free the slot -- the wr 20->0
0x8b123df4   a0 = local[+0x28]                 ; comp_id
0x8b123df8   0x8b11c5e8(comp_id, &out)         ; routine lookup
0x8b123e00   beqz -> 0x8b123eb0                ; found: marshal params, invoke
             else  -> log "[S]Find no matched Routine for FuncID:%#lx"
                      msg[+0x08] = 0xf         ; error code, reusing cmd_type
```

`sp+0x38` is `local[+0x08]`, the parameter count, and the found path copies
`count` words from `local + 0x2c` -- exactly the layout U-Boot builds.

Note both paths normally publish a RETURN: not-found replies with error `0xf`.
The only escape is flags bit 0 (`MSG_FLAG_NOTIFY`) at `local[+0x06]`, which
sends the worker straight back to its dequeue with no reply. U-Boot sets flags
to `4` (SENT), so bit 0 is clear and a reply is expected either way.

Since **no** RETURN appears and no second doorbell is rung, the worker stalls at
or after the invocation rather than failing the lookup.

### The stall is generic, and it costs one CALL per boot

`THal_Vp_DisableBlackScreen` (`0xb66041d8`, zero-parameter) as the **first**
call of a fresh boot behaves identically to `GetImageBufferAddr`: CALL_ACK,
`idx` reset to `0x14`, `FreeCall wr` wrapping 20 -> 0, no RETURN, no visible
change on the panel. So the stall is in dispatch generally, not in one handler.

Two operational facts worth carrying:

- **One usable CALL per boot.** After the first, `staging CallCmd` reads
  `rd=1 wr=2`: the second is pushed and never popped. Any test that sends two
  CALLs in a boot has a contaminated second result.
- Reaching "slot recycled" proves only that the worker got as far as
  `0x8b118cb0` at `0x8b123dec`, which runs **before** the routine lookup. It is
  not evidence that any routine executed.

The rest of the worker, decoded:

```
0x8b123f44   v0 = sp[0xe4]                    ; routine pointer from the lookup
0x8b123f4c   jalr v0                          ; invoke: (params@sp+0xe8, out@sp+0x124)
0x8b123e3c   flags bit 0 (NOTIFY) -> no reply, back to dequeue
0x8b123e4c   retcode = sp[0x124] -> local[+0x08]
0x8b123e5c   retcode != 0xf -> marshal output params back into local + 0x2c
0x8b123e68   0x8b1208c8(local, 1)             ; publish the RETURN
0x8b123e70   ok -> back to dequeue
             else log "[S]Failed to send return, FuncID:%#lx"
                  -> back to dequeue
```

**Every path after the invocation returns to the dequeue loop at
`0x8b123d1c`.** So the worker cannot wedge in the reply logic as written --
which leaves the `jalr` itself, or a blocking call inside `0x8b1208c8`.

The handler is not the problem. `DisableBlackScreen`'s call-table entry, read
live at shared `+0x126c8`, is exactly as documented and its handler is a clean
adapter:

```
+0x00 00010000  +0x04 8b8f32b0  +0x08 b66041d8
+0x0c "THal_Vp_DisableBlackScreen_1_000"
+0x50 8b10a110  +0x5c ffffffff

0x8b10a110:  jal 0x8b149948 ; *out = 0 ; return    (params, out) -- valid code
```

`+0x04` being `8b8f32b0` is also an independent confirmation that the channel's
`pid` is the registering thread's owner pointer.

### The firmware logs over SEGGER RTT, and it is nearly silent

The debug region at `0x4bd01000` (`sys:dbg_buf`) holds an **RTT control block**,
not text:

```
MaxNumUp=3  MaxNumDown=3
aUp[0]   = { "Terminal", buf=0xabd01300, size=0x41c00, WrOff=8, RdOff=0 }
aUp[1]   = { "SysView",  buf=0xabd43000, size=0x7d000, WrOff=0 }
aDown[0] = { "Terminal", buf=0xabd01200, size=0x100 }
aDown[1] = { "SysView",  buf=0xabd42f00, size=0x100 }
```

`WrOff = 8` -- eight bytes have ever been written to the Terminal channel. So
the assert and log strings this document has been reading all session do **not**
land in memory; `elog route='0'` sends them to a UART. `display_cfg.xml` was
checked and carries no logging settings at all, so there is no reroute
available from the files we load.

Reaching the firmware's own log therefore needs either the MIPS UART pins on
the board, or a patch to `display.bin`'s log routing. Both are bigger jobs than
anything attempted here, and the RTT buffer addresses above are the starting
point for the second.

### A misattribution worth not repeating: `msg[+0x01]`

`0x8b1208c8` is **`SendAckLow`**, and it guards on the message before doing
anything:

```
0x8b12093c   msg == NULL                    -> assert, line 0x2bd
0x8b120948   s7 = msg[+0x01]                ; BYTE
0x8b12094c   s7 != getCurCPUID() (== 1)     -> assert, line 0x2be  <-- fires
0x8b12095c   msg[+0x02] (byte) >= 2         -> assert, line 0x2bf
0x8b12096c   msg[+0x69] & 4                 -> assert, line 0x2c2
```

Each assert logs `SendAckLow` and then spins in `b .`.

**Those guards are not on the worker's path, and setting that byte regressed a
working run.** `0x8b1208c8` is a two-instruction thunk:

```
0x8b1208c8   j 0x8b11fd58            ; tail-jump to SendComm2CPUEx
0x8b1208cc   addiu a2, zero, -1
```

`SendAckLow` is the **next** function, at `0x8b1208d0`. Disassembling from
`0x8b1208c8` runs straight through the thunk into it, and its asserts get
attributed to the wrong function. Always find the entry and the `jr $ra` before
reading a function's guards.

Tried on hardware, `msg[+0x01] = 1` made things worse: `command_action` stopped
completing (`idx` stayed `00`, `wr` stayed 20, no CALL_ACK), because
`0x8b11d544` compares the **full u16** at `msg[+0x00]` against the channel
record's `+0x02` at `0x8b11d63c`. `chan` is a halfword and must stay 0.
Reverted.

So the reply really goes through `SendComm2CPUEx`. Its only unbounded wait is

```
0x8b12000c   0x8b119618(peer)        ; per-CPU BSS object
0x8b120018   s7 = obj + 0x3e0        ; obj + 8 when idx == 0
0x8b12002c   0x8b15c0fc(s7, -1)      ; osal_semaphore_get, wait forever
```

and that is **not** the blocker either. Read live, both objects exist and are
named: `obj+0x008 -> 0x8b9140c8` and `obj+0x3e0 -> 0x8b9147e8`, with inline
names `"Seq(cpu[0]) ..."` and `"Seq(cpu[0]) Retu..."`. Both carry `+0x38 = 1`
(count) and `+0x3c = 0x20` (capacity), and `0x8b103f5c` takes the acquire path
at `0x8b103fc4` whenever the count is non-zero. The Return object's list heads
at `+0x08..+0x34` are zero where the Call object's are self-referencing, which
looks wrong, but nothing on the get path dereferences them.

**Where the wedge actually is remains unlocated.** It is somewhere in
`SendComm2CPUEx` past that wait. Static reading has resolved four frames in a
row to "this one is fine", which is a poor return per bench cycle -- see the
RTT note above for why the firmware's own log is not currently reachable.

   `h713_disp fwmd <mips-va> [words]` now dumps any firmware address with the
   cache invalidated, so chasing this no longer costs a reflash per address.
3. Do not brute-force `chan`/`pid`. `pid` is a live thread id; the space is far
   too large and each wrong guess is only worth one FreeCall slot.
4. If CPU_COMM stalls here, **switch threads**: the OSD failure is independent
   of it. AFBD status at `0x05600168` sits at 2 and never moves, and the
   mixer/DE composition path has never been explained.
5. **Stock register parity** remains the decisive comparison and is now cheap:
   the registers that matter are known (`0x051c0000..0xcc`, the mixer layer
   words, AFBD). One dump from a stopped stock boot would likely settle the OSD
   question outright.

## Bench notes

- `h713_disp mips-test 0x33` brings the firmware up with no display phases --
  use it for CPU_COMM work. `panel-test` is now slim (~20 s); `full` restores
  the long-form phases.
- `commcall`, `calltable` and `commstate` all run at the prompt on the same
  boot. Only `commcall` writes.
- The FreeCall ring has 20 slots, so ~20 sends fit in one boot.
- One MIPS launch per physical power cycle still holds.
- `commcall` now refuses a doorbell word above 3, because the word *is* the
  type. Out-of-range is inert, not fatal -- it just wastes a slot.

## Traps

- Do not add `h713_display_prepare()` to the fastlogo replay; the vendor
  prologue already does its clock work.
- Do not use `0x05880FE0` as a criterion.
- `0x8b119bb4` and `0x8b124ba4` touch only firmware BSS -- the ARM owes them
  nothing.
- `getCurCPUID` always returns 1, so the master-init block in `display.bin` is
  compiled in but never executed by the firmware. That is *why* it is a
  reliable specification of what the ARM must build.

# MIPS display recovery plan

This plan recovers the H713 bench kernel first, then brings up the display
coprocessor one dependency at a time. It deliberately separates "the kernel
boots" from "the MIPS firmware starts" and from "ARM/MIPS RPC works." A build
that merely links is not evidence that the shared-memory protocol is safe.

The DDR3 `HY200_QZ713DF_A1` bench board is the only target in scope. Do not
flash these experiments to the untested LPDDR3 projector board.

## CPU_COMM: the routine map is recovered (2026-07-31)

The firmware's HAL routines are addressable, and the identities are confirmed
against this exact firmware rather than inferred.

### How a routine is named

The transport addresses a routine by a hashed id computed over
`<name>_<cpu_id>_<pid_low12>` -- `cpu_id` 1 for MIPS-side routines callable
from the ARM, 0 for MIPS-to-ARM callbacks, and `pid_low12` `000` for both
sides of the firmware's own registrations. The hash is an Allwinner CRC32
variant:

```python
def comp_id(name, seed=0x123456):
    crc = seed
    for b in name.encode():
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return crc & 0xFFFFFFFF
```

### Why this is trusted

Three independent checks, in increasing strength:

1. The function reproduces 10/10 ids documented externally.
2. `display.bin` contains 85 `THal_Vp_` and `MipsHalCallback_` name strings,
   against the 82 registrations counted on hardware.
3. **Decisive:** the live call table stores each routine's *name* alongside its
   id, and the stored name hashes to the stored id. Verified on hardware for
   `THal_Vp_GetSNR_1_000`, `THal_Vp_SetHDCP22Key_1_000`,
   `THal_Vp_SetBrightness_1_000` and `THal_Vp_AtvSetRegion_1_000`. The third
   also reproduces the externally documented `0x7221d017`.

### Call-table entry layout

1224 entries of 0x60 bytes at `shared+0x75c8`, count at `+0x75c4`, version at
`+0x75c0`. Version is exactly twice the count -- each insertion bumps it twice.

```
+0x00   00010000     flags/type
+0x04   8b8f32b0     owner/vtable pointer, identical across entries
+0x08   comp_id
+0x0c   routine name, NUL-terminated ASCII, stored in place
+0x50   handler function pointer (MIPS VA, unique per entry)
+0x5c   next/free link, 0xffffffff when free
```

The handler pointer at `+0x50` means any routine can be disassembled in
`display.bin` before it is called.

### Reading it on hardware

```
h713_disp panel-test 0x33     # or mips-test -- the table only exists
h713_disp calltable           # after a launch
```

`calltable` is read-only: no writes, no messages. It does **not** consume the
one-launch-per-power-cycle budget, so run it at the prompt on the same boot
while the firmware is still up. Observed: `version=164 count=82`, all 13
embedded ids matched at entry offset `+0x08`.

### Entries that matter for the display problem

| entry | routine | why |
| --- | --- | --- |
| 989 | `THal_Vp_GetImageBufferAddr` | exported but handler `0x8b10adb0` is a two-word no-op |
| 703 | `THal_Vp_SetImageBufferAddr` | exported but handler `0x8b10ada8` is a two-word no-op |
| 472 | `THal_Vp_DisableBlackScreen` | zero-parameter; would explain every observation if asserted at power-on |
| 107 | `THal_Vp_EnableBlackScreen` | its peer |
| 485 | `THal_Vp_SetSource` | source selection |
| 969 | `THal_Vp_GetSource` | read-only |
| 325 | `Thal_Vp_SetBacklightPwmInfo` | the unresolved PWM5 question |
| 894 | `Thal_Vp_SetBacklightLevel` | brightness |

### What a CALL still needs

Sending is **not** implemented and is not a small addition. A call goes through
routine lookup, session allocation, message allocation, FIFO enqueue, the
msgbox doorbell at `0x03003874`, an ACK wait and a return read. Those run on
master-side structures U-Boot does not initialise:

```
0x04CE8   va_offset
0x04D0C   linked lists (5 pairs)
0x04DB0   rec entries + wait/share-seq structures
0x240E8   component pool
0x2C068   messager pool      <- messages are allocated from here
0x2CCF0   SMM heap
```

What we do initialise -- magic words, `max_cpu`, CPU flags, 12 spinlocks, call
table sentinels -- is exactly enough for the MIPS to register and report ready,
which is why everything to date has worked. It is not enough to send.

Recovering the rest is the same job as `comm_InitSpinLock` and the call-table
sentinels, both of which were read out of `display.bin` successfully. Do not
guess at it: a malformed message to a live coprocessor can wedge it, and every
wedge costs a power cycle.

### Complete routine map

Ids for the ARM-to-MIPS direction (`_1_000`), or `_0_000` for the
`MipsHalCallback_` entries, computed from the 85 names in `display.bin`.

| routine | comp_id |
| --- | --- |
| `MipsHalCallback_DisplayLatencyChange` | `0xad9f0a86` |
| `MipsHalCallback_HdmiHotPlugByPortHandler` | `0x38d780e2` |
| `MipsHalCallback_SignalChange` | `0x3e7fbc46` |
| `THal_Vp_AtvChannelChange` | `0xa138c8fe` |
| `THal_Vp_AtvChannelScanEnd` | `0x9558d223` |
| `THal_Vp_AtvChannelScanStart` | `0x39d6eec4` |
| `THal_Vp_AtvEnableSnowScreen` | `0x6e857547` |
| `THal_Vp_AtvSetRegion` | `0xa16b7c24` |
| `THal_Vp_AtvSetSignalStd` | `0x80e56656` |
| `THal_Vp_CvbsSetPedestalMode` | `0x24f44438` |
| `THal_Vp_Deinit` | `0xeaaa24c9` |
| `THal_Vp_DisableBlackScreen` | `0xb66041d8` |
| `THal_Vp_DisableScreenCover` | `0x143ffc87` |
| `THal_Vp_DisableVideoFreeze` | `0x3ab1d1dc` |
| `THal_Vp_EnableBlackScreen` | `0xa30d4c6b` |
| `THal_Vp_EnableScreenCover` | `0x0152f134` |
| `THal_Vp_EnableVBILine` | `0xf3772724` |
| `THal_Vp_EnableVideoFreeze` | `0x2fdcdc6f` |
| `THal_Vp_GetBlackExtension` | `0x5d3d7258` |
| `THal_Vp_GetBrightness` | `0x880be6ff` |
| `THal_Vp_GetColorManagement` | `0xe661461f` |
| `THal_Vp_GetContrast` | `0x6665fe81` |
| `THal_Vp_GetDCI` | `0xf9b94e50` |
| `THal_Vp_GetDisplayLatency` | `0x434567b0` |
| `THal_Vp_GetHue` | `0x5432b456` |
| `THal_Vp_GetImageBufferAddr` | `0x2f02f7dd` |
| `THal_Vp_GetLowLatencyMode` | `0xc32fe5ff` |
| `THal_Vp_GetPictureMode` | `0x2d8338c3` |
| `THal_Vp_GetSNR` | `0xcfc4bc0d` |
| `THal_Vp_GetSaturation` | `0x5263b52b` |
| `THal_Vp_GetSharpness` | `0x563e60ab` |
| `THal_Vp_GetSignalInfo` | `0x24b17fb7` |
| `THal_Vp_GetSource` | `0x24efc7c9` |
| `THal_Vp_GetTNR` | `0xaba5d1c4` |
| `THal_Vp_GetVBIAddr` | `0x8f5859c2` |
| `THal_Vp_GetVBIData` | `0x096b60b1` |
| `THal_Vp_GetVBIOffset` | `0xec2ca0b4` |
| `THal_Vp_GetVBISize` | `0x96046e19` |
| `THal_Vp_GetVideoRange` | `0x623d9729` |
| `THal_Vp_HDMI_GetPortStatus` | `0xcbf83247` |
| `THal_Vp_HDMI_ReloadHdcp14Key` | `0x449effe8` |
| `THal_Vp_HDMI_SetHPDTimeInterval` | `0x6eb4c96a` |
| `THal_Vp_HDMI_SetPortMap` | `0x9ce74c48` |
| `THal_Vp_Init` | `0x1c6ff747` |
| `THal_Vp_RegisterCallbackOfDisplayLatencyChange` | `0x87a96488` |
| `THal_Vp_RegisterSignalChangeCallback` | `0x671ceca6` |
| `THal_Vp_ResetVBI` | `0x9c91450e` |
| `THal_Vp_SeamlessDisable` | `0xc5429d4a` |
| `THal_Vp_SeamlessEnable` | `0xcb6d765f` |
| `THal_Vp_SetBacklightWorkMode` | `0x4d80db0e` |
| `THal_Vp_SetBlackExtension` | `0x5c135587` |
| `THal_Vp_SetBrightness` | `0x7221d017` |
| `THal_Vp_SetColorManagement` | `0xf00ca77d` |
| `THal_Vp_SetContrast` | `0x023c4033` |
| `THal_Vp_SetDCI` | `0xf6a798d3` |
| `THal_Vp_SetGamma` | `0x1a116843` |
| `THal_Vp_SetHDCP22Key` | `0x50817813` |
| `THal_Vp_SetHDCP22Pkf` | `0xfa085aaa` |
| `THal_Vp_SetHDMIHotPlugByPortCallback` | `0xba3e5a70` |
| `THal_Vp_SetHue` | `0x5b2c62d5` |
| `THal_Vp_SetImageBufferAddr` | `0x396f16bf` |
| `THal_Vp_SetLowLatencyMode` | `0xc201c220` |
| `THal_Vp_SetPictureMode` | `0x83a878bf` |
| `THal_Vp_SetSNR` | `0xc0da6a8e` |
| `THal_Vp_SetSaturation` | `0xa84983c3` |
| `THal_Vp_SetSharpness` | `0x7335ebb5` |
| `THal_Vp_SetSource` | `0xeaf13de5` |
| `THal_Vp_SetTNR` | `0xa4bb0747` |
| `THal_Vp_SetVideoRange` | `0x9817a1c1` |
| `THal_Vp_SetWhiteBalance` | `0xfc42fe0c` |
| `THal_Vp_StartVBI` | `0x0fe1790c` |
| `THal_Vp_StopVBI` | `0x8a0d26cb` |
| `THal_Vp_SwitchARCTXPath` | `0xe9b4464d` |
| `THal_Vp_TurnOnARCAudioPath` | `0x93965d14` |
| `THal_Vp_UnregisterCallbackOfDisplayLatencyChange` | `0x72341984` |
| `THal_Vp_UnregisterSignalChangeCallback` | `0x2692bdbe` |
| `THal_Vp_Wce_DisablePixel2PixelMode` | `0xea7ffef5` |
| `THal_Vp_Wce_EnablePixel2PixelMode` | `0x8f8a9581` |
| `THal_Vp_Wce_GetActiveWindow` | `0x7bbd5772` |
| `THal_Vp_Wce_GetWindow` | `0xfd483f67` |
| `THal_Vp_Wce_SetMirrorMode` | `0x09ffc6eb` |
| `THal_Vp_Wce_SetWindow` | `0x3356c54b` |
| `Thal_Vp_AtvIsFastSyncLock` | `0x71a4c888` |
| `Thal_Vp_SetBacklightLevel` | `0x51ad877e` |
| `Thal_Vp_SetBacklightPwmInfo` | `0xb46ce545` |

## CPU_COMM: the master-side init, recovered (2026-07-31)

Sending a call needs shared-memory structures U-Boot does not build. This is
what the firmware's own master path builds, read out of the authenticated
`display.bin` and cross-checked against `cpu_comm.h` in the 32-bit Linux tree.
Every field that both sources describe agrees.

### The master init function

`0x8b11ace8` (raw `display.bin+0x1ace8`). It is the combined init: it calls
`getCurCPUID` at `0x8b1227b4` and `bnez` sends CPU 1 to `0x8b11b118`, so this
path is the ARM master's. It is idempotent -- it reads `shared+0x90` and skips
the whole body if the magic is already `0xdeadbeef`.

```
jal 0x8b124ba4                        (1)  first init, NOT YET DECODED
jal 0x8b124d38                        (2)  comm_InitSpinLock      -- U-Boot has
memset(shared+0x75c0, 0, 0x1cb08)     (3)  call table             -- U-Boot has
    count=0, version=0, 1224 sentinels
memset(shared+0x90, ...)              (4)
sw max_cpu -> 0x4cd8                  (5)                         -- U-Boot has
jal 0x8b119bb4  (cpu 0)               (6)  per-CPU comm object    NOT DECODED
jal 0x8b1197d4  (cpu 0, dir 0)        (7)  share_seq -- decoded below
jal 0x8b1197d4  (cpu 0, dir 1)        (8)
jal 0x8b119bb4  (cpu 1)               (9)
jal 0x8b1197d4  (cpu 1, dir 0)       (10)
jal 0x8b1197d4  (cpu 1, dir 1)       (11)
jal 0x8b1190c0                       (12)  final init, NOT DECODED
    five self-referencing list heads (13)
    256-entry record loop            (14)
magic1 = magic2 = 0xdeadbeef         (15)                         -- U-Boot has
```

### share_seq addressing

`0x8b1193d8(cpu, dir, idx)`, all three arguments validated `< 2`:

```
shared + 0x98 + 9760*cpu + 4880*dir + 2440*idx
```

Eight structs of 0x988 bytes spanning `shared+0x00098..0x04CD8`. The array ends
exactly where `max_cpu` begins, which is the check that the formula is right.

| cpu | dir | idx | offset |
| --- | --- | --- | --- |
| 0 | 0 | 0 | `0x00098` |
| 0 | 0 | 1 | `0x00a20` |
| 0 | 1 | 0 | `0x013a8` |
| 0 | 1 | 1 | `0x01d30` |
| 1 | 0 | 0 | `0x026b8` |
| 1 | 0 | 1 | `0x03040` |
| 1 | 1 | 0 | `0x039c8` |
| 1 | 1 | 1 | `0x04350` |

### share_seq contents

`0x8b1197d4(cpu, dir)` writes, relative to the struct base:

```
+0x00  cpu (byte)        +0x78  rd_idx     = 0
+0x01  dir (byte)        +0x7c  wr_idx     = 0
+0x02  0    (byte)       +0x80  peak_count = 0
+0x08  0    (byte)       +0x84  track      = 1
+0x10  20   (byte)       +0x88  capacity   = 21
+0x14  -1                +0x8c  item_size  = 4
+0x68  20   (byte)       +0x90  base_addr  = ARM-phys of (struct + 0xc0)
+0x69  0    (byte)       +0x94  0
+0x6c  -1                +0x98  FIFO name string
                         +0xb8  0
```

The block at `+0x78` is the driver's `comm_fifo` field for field: `rd_idx`,
`wr_idx`, `peak_count`, `track_stats`, `capacity`, `item_size`, `base_addr`.
Capacity 21 with one slot wasted for full-detection gives 20 usable, matching
the driver's documented sequence maximum of 19.

`base_addr` is `((VA + 0xc0) & 0x1fffffff) + 0x40000000` -- the firmware
converting its own KSEG address into an ARM-visible physical one. `struct+0xc0`
is the message slot array; the slot stride computes as `104 * i`, which is
`COMM_MSG_SIZE`.

### Directly replicable today

Five self-referencing empty circular lists, each `{self, 0, self, 0}`:

```
shared+0x4d10  0x4d28  0x4d58  0x4d70  0x4d88
```

A 256-entry record array from `shared+0x4db0` to `+0x75b0`, stride `0x28`
(`0x2800/0x28 = 256`), each with the same `{self, 0, self, 0}` head plus a call
to `0x8b1234c8(2, 0, entry-0x18)`. It lands exactly on `magic2` at `0x75b8`.

### The gap, stated precisely

U-Boot memsets the whole 5 MB then writes magic, flags, spinlocks and the call
table. **The entire `0x98..0x4CD8` share_seq region is left zero** -- capacity
0, `base_addr` 0, no FIFOs at all. That is enough for the MIPS to register its
82 routines and report ready, which is why every run to date has worked, and it
is why a call would find an empty transport.

### Why reading this block is safe to trust

`getCurCPUID` at `0x8b1227b4` is two instructions and always returns 1:

```
jr    $ra
addiu $v0, $zero, 1
```

So the `bnez $v0` at `0x8b11adac` is always taken and **the firmware never
executes the master-init block above**. It is compiled-in reference code for
the ARM side. That is exactly why replicating from it has worked twice already
-- `comm_InitSpinLock` and the call-table sentinels both came from here and
both were correct on hardware.

One caveat for replication: helpers that call `getCurCPUID` internally take the
CPU-1 path when read here, so trace each helper's `cpu == 0` branch rather than
copying its literal behaviour.

### The helpers, decoded

`0x8b150948` is the assertion logger, `"ASSERT FAILED, File:%s Line:%d
Routine:%s"`. Most branching in these functions is assertion paths, not
structural work, which makes them smaller than they look.

`0x8b118ff8(cpu, dir)` -- argument validator, both `< 2`, returns 0.

`0x8b1190c0` -- loop over `dir` in {0,1}, from `./comm_request.c`, guarding
`comm_WriteRegWord`. The `cpu == dir` case falls through to the tail, so on the
master only the cross direction does work.

`0x8b124ba4(type)` -- **not shared state.** Allocates a bookkeeping object into
the firmware's own BSS and bumps a counter at `0x8b27198c + type*4`. Called
with type 0. U-Boot does not need to replicate it; the ARM side allocates its
own equivalent in its own memory.

`0x8b1234c8(2, 0, record)` -- free-list insertion. Appends the record onto the
list header at `shared+0x4d80`, anchor `0x4d88`, incrementing a `u16` count at
`+0x02`:

```
[0x4d80+0x10] = record + 0x18      ; list tail
[record+0x20] = old tail           ; back link
[record+0x18] = 0x4d88             ; list anchor
```

So the 256 records at `0x4db0..0x75b0` are a **free pool**, pre-chained at init.

`0x8b11825c(fifo)` -- the FIFO slot allocator, called on `share_seq+0x78`:

```
if (rd_idx >= capacity) assert
if (wr_idx >= capacity) assert
if ((wr_idx + 1) % capacity == rd_idx) return NULL     ; full
return base_addr + wr_idx * item_size
```

confirming the `comm_fifo` layout from a second direction:

```
+0x00 rd_idx   +0x10 capacity    +0x18 base_addr
+0x04 wr_idx   +0x14 item_size   +0x40 debug_flags
+0x08 peak     +0x0c track
```

It does **not** advance `wr_idx`; commit is a separate operation. That matters
for getting a send right.

### The two FIFO names

The share_seq initialiser copies one of these into `struct+0x98` depending on
direction:

```
0x8b1edb1c  "FreeCall"
0x8b1edb28  "FreeReturn"
```

**`idx`, not `dir`, selects which.** `0x8b1197d4` runs its body twice per
`(cpu, dir)` call: `idx 0` names the FIFO "FreeCall" at `0x8b119b84`, then the
tail at `0x8b119bac` sets `idx` to 1 and repeats for "FreeReturn". That is what
the `idx` term in the addressing formula is for, and it means all eight
structures are live rather than four. The pair is the call queue and the return
queue, which is what a synchronous RPC needs and matches the protocol doc's
"session pool, FreeCall pool, returnPipeLine".

### The message slot loop, and the complete share_seq layout

The tail of `0x8b1197d4` runs 20 iterations over a message slot array:

```
fp = share_seq + 0x168
loop i = 0..19:
    sh   i,  4(fp)                     ; slot[+0x04] = i
    sw  -1,  slot + 0x0c               ; slot[+0x0c] = -1
    *ring_entry = (slot & 0x1fffffff) + 0x40000000    ; ARM-physical
    jal 0x8b118430                     ; FIFO push/commit
    fp += 0x68                         ; 104 bytes
until i == 0x14
```

`slot[+0x04] = i` and `slot[+0x0c] = -1` are the driver's `comm_msg.slot_index`
and `comm_msg.session_id`. The arithmetic closes the structure:
`0x168 + 20*104 = 0x988`, exactly the struct size.

```
+0x000  cpu (byte), dir (byte), 0
+0x008  0
+0x010  20            +0x014  -1
+0x068  20            +0x06c  -1
+0x078  comm_fifo   rd=0 wr=0 peak=0 track=1
                    capacity=21 item_size=4
                    base_addr = ARM-phys(share_seq + 0xc0)
+0x098  name: "FreeCall" (idx 0) or "FreeReturn" (idx 1)
+0x0b8  0
+0x0c0  FIFO ring, 21 x u32
+0x168  20 message slots x 104 bytes  -> ends exactly at 0x988
```

The 20 slots are pushed onto the FIFO at init, each as its ARM-physical
address, so the ring starts full of free slots -- 20 entries in a 21-capacity
ring, which is the "one wasted for full detection" the driver documents.
`0x8b11825c` allocates a ring position, `0x8b118430` commits it.

### Firmware-local, not needed by U-Boot

```
0x8b124ba4   allocates into firmware BSS, bumps a counter at 0x8b27198c
0x8b119bb4   per-CPU object at BSS 0x8b253a98 + 1168*cpu
0x8b1190c0   validation loop only
```

`0x8b119bb4` never loads the shared-memory base -- that is only reachable
through the global at `0x8b2543d4`, which it does not touch. Both it and
`0x8b124ba4` write only firmware BSS, so the ARM side has no shared-memory
obligation for either.

### The master init is fully decoded

Nothing unknown remains. What U-Boot must add, specified to the byte:

- 8 x `share_seq` at `0x98 + 9760*cpu + 4880*dir + 2440*idx`, layout above
  -- all eight, with the name chosen by `idx`
- 5 list heads at `0x4d10/0x4d28/0x4d58/0x4d70/0x4d88`, each `{self,0,self,0}`
- 256-record free pool `0x4db0..0x75b0` stride `0x28`, chained onto `0x4d80`

## CPU_COMM: the send path (2026-07-31)

Partial. Enough is known to say where a send goes; not enough to send one.

### SendComm2CPUEx

`0x8b11fd58` (raw `display.bin+0x1fd58`), 224-byte frame. Arguments match the
Linux driver's prototype: `a0` = message pointer, `a1` = target cpu, `a2` =
flags. `a1 == 0` means auto-detect via routine lookup, and that path's work
begins at `0x8b11ffb4`. `a0 == 0` is rejected.

The function contains no msgbox constants -- the doorbell is rung by a helper.
Note this firmware runs on the MIPS, so its own notification path is
MIPS-to-ARM; the ARM-to-MIPS doorbell is the other half and comes from the
Linux driver.

### The ARM-to-MIPS doorbell

A single write, no interrupt-enable pulse. The pulse workaround in that tree is
for the ARISC path, not MIPS.

```c
raw = ((msg_type & 0x3) << 16) | (intr_type & 0xFFFF);
writel(raw, 0x03003874);
```

`msg_type` 0=CALL, 1=RETURN, 2=CALL_ACK, 3=RETURN_ACK; `intr_type` is 2 in
stock. So a CALL is `0x00000002` written to `0x03003874`.

**Verified against our own firmware.** The MIPS TX function at `0x8b121870`
forms both addresses from the msgbox base:

```
addiu $s6, $s0, 0x3864     ; FIFO count, port 1
addiu $s5, $s0, 0x3874     ; MSG_DATA,   port 1
jal   0x8b180550($s6)      ; poll the count
```

With `$s0 = 0x03000000` those are `0x03003864` and `0x03003874`, matching the
driver's constants and the protocol doc.

### The message layout, settled by the receive side

`command_action` at `0x8b120bc0` is the consumer. It resolves a share_seq via
`0x8b1195b8(cpu, ...)`, reads a slot index from `share_seq+0x10` and rejects it
unless `< 20`, then forms the message base as `share_seq + 0x168 + 104*index`.
Subtracting `0x168` from its accesses gives the layout:

```
+0x00  lhu        src/dst pair
+0x02  lhu / sh   dst_cpu        compared against getCurCPUID
+0x04  lhu        slot_index
+0x06  lhu        flags
+0x08  lhu        cmd_type       <- parameter count
+0x0A  lhu / sh   flags2         bit 3 set on receipt
+0x0C  lw         session_id
+0x20  lw         payload[0]
+0x24  lw         payload[1]
+0x28  lw         comp_id        <- 40 decimal
```

This is the Linux driver's `CPUComm_CallEx` layout, field for field:
`dst_cpu` at `+2`, parameter count in `cmd_type` at `+8`, `comp_id` at `+40`,
parameters from `+44`. **The protocol doc's 168-byte form is wrong for this
path** -- its parameter count at `+64` and parameters at `+68` are not what the
firmware parses. The 104-byte form is also what fits the slots we build.

One correction to the driver's own header: it labels `+0x02` `component_id`,
but the firmware compares it with `getCurCPUID`, so it is `dst_cpu`. The
driver's code has this right; only its struct comment is misleading.

Note this also validates our init from the consumer's side: the message base is
`share_seq + 0x168 + 104*index` with a slot index bounded by 20, which is
exactly the array we build and the value 20 we write at `+0x10` as the
out-of-range/empty marker.

### Which queue a message goes in

The send and receive resolvers are mirrors of `0x8b1193d8`:

```
receiver  0x8b1195b8(peer, idx) = share_seq(my_cpu, peer, idx)
sender    0x8b1195ec(peer, idx) = share_seq(peer, my_cpu, idx)
```

So a message from X to Y lives in `share_seq(Y, X, idx)` -- indexed by
**(destination, source)** -- and Y reads that same structure. `idx` selects
FreeCall (0) or FreeReturn (1). Against the eight transports U-Boot builds:

```
ARM(0) -> MIPS(1) CALL     share_seq(1,0,0) = shared+0x026b8   FreeCall
MIPS(1) -> ARM(0) RETURN   share_seq(0,1,1) = shared+0x01d30   FreeReturn
```

Both offsets are in memory we already initialise and have dumped live.

### The ARM does not participate in the locking

`0x8b119618(cpu)` returns `0x8b253a98 + 1168*cpu` -- the firmware's own BSS
object, the same one `0x8b119bb4` initialises. The semaphores `SendComm2CPUEx`
takes at `+0x8` and `+0x3e0` of that object are MIPS-local ThreadX primitives,
not shared memory. The ARM side has no obligation to them.

`0x8b11a920(cpu)` and `0x8b11a720(cpu)` are readiness guards -- shared base
non-null, cpu in range, `magic1 == 0xdeadbeef` -- not publication.

### The publication step

The enqueue helper is `0x8b11f9ec`, called once from `SendComm2CPUEx` at
`0x8b12046c`. Its signature is
`publish(share_seq, slot_index, state, session, wait_ptr)`, and the call site
sources every argument from the message being sent:

```
memcpy(slot, msg, 0x68)          ; 104 bytes, COMM_MSG_SIZE
msg[+0x0A] |= 4                  ; set bit 2 in flags2

publish( share_seq,
         msg[+0x04],             ; -> share_seq[+0x10]  slot index
         msg[+0x06] & 0xff,      ; -> share_seq[+0x08]  state
         msg[+0x0C],             ; -> share_seq[+0x14]  session id
         s7 + 4 )                ; -> share_seq[+0x18]  wait pointer
```

with `share_seq[+0x04]` bumped by one and `[+0x1c]` cleared. This closes the
loop with the receive side: the handler reads the index from `+0x10` and tests
bit 2 of `+0x08`.

**Correction.** An earlier revision said bit 2 of `+0x08` "is exactly what is
OR'd into `flags2` immediately before publishing." Those are two different
fields. `share_seq[+0x08]` comes from `msg[+0x06]` (`flags`); the `|= 4` at
`0x8b120450` lands in `msg[+0x0A]` (`flags2`) and is never published. The ARM
must set bit 2 in **`flags`**, and that is what gates the whole receive path --
see the handoff at the top of this document.

### The slot carries its own index

The sender does not pop a ring to choose a slot index. It reads it back out of
the slot: `lhu $s6, 4($fp)` takes `slot[+0x04]`. That is the field U-Boot
stamps with `i` for each of the twenty slots, so **our slot initialisation is
load-bearing**, not decorative. The allocator is `0x8b118be8(share_seq)`.

### Hazard: the published wait pointer

`s7` is `0x8b119618(cpu) + 8` or `+ 0x3e0` -- a pointer into the firmware's own
BSS per-CPU object, i.e. a ThreadX wait object. So `share_seq[+0x18]` is a
wait-object pointer and `[+0x1c]` its zero high half, matching the driver's
`comm_msg.wait_ptr_lo`/`wait_ptr_hi`.

The receiver signals through that pointer on completion. U-Boot polls rather
than sleeps and has no wait object, so **publishing a bogus pointer would have
the firmware write into arbitrary MIPS memory.** Resolve this before any send:
either find a value the firmware treats as "no waiter", or point it somewhere
harmless and verified.

### The two memcpys are a fill and a sync-back

`0x8b1bcf34` is `memcpy(dst=a0, src=a1, n=a2)` -- confirmed from its byte loop,
which reads through `a1` and writes through the saved `a0`. Both call sites are
on the CALL path, which converges at `0x8b120430` from the slot-address check
at `0x8b120330`:

```
0x8b1201b8   memcpy(slot, msg, 104)      ; fill the slot
             slot[+0x04] = index
             slot[+0x0A] = 2             ; CALL marker
             assert slot == share_seq + 0x168 + 104*index
0x8b120438   memcpy(msg, slot, 104)      ; sync back into the caller's buffer
             msg[+0x0A] |= 4
0x8b12046c   publish(...)
0x8b1203a8   0x8b15c1d0(wait_obj)        ; sender pends on its own semaphore
```

The sync-back exists so the caller can read fields the send path filled in --
which is exactly why the Linux driver reads `session_id` from its own buffer
*after* `SendComm2CPUEx` returns.

### The wait pointer: publish zero

Resolved. Three pieces of evidence:

1. The receiver **stores** the pointer without dereferencing it. In
   `0x8b1208d0` it copies the two stack arguments into `share_seq[+0x70]` and
   `[+0x74]`.
2. The eventual signal null-checks. `0x8b15c27c` does `beqz $a0 -> return 5`,
   as does its wait counterpart `0x8b15c1d0`. A zero pointer yields an error
   return, never a write.
3. U-Boot polls and does not need signalling; it reads the reply from the
   FreeReturn queue at `shared+0x01d30`.

So publishing `0` at `+0x18`/`+0x1c` is memory-safe. The residual risk is
behavioural, not corrupting: the firmware gets an error code from the signal
attempt and may log it or take an error path.

This also explains the `+0x68`/`+0x6c` pair the init writes alongside
`+0x10`/`+0x14`. They are a **mirror descriptor** -- one for the inbound
message, one for the pending reply -- and `0x8b1208d0` fills the second set
(`+0x68`, `+0x69`, `+0x6c`, `+0x70`, `+0x74`) on receipt.

## CPU_COMM: the msgbox delivers (2026-07-31, morning)

**Superseded in part.** The msgbox gating result below stands and is still
load-bearing. Everything in this section about *doorbell encoding* is
superseded by the handoff at the top of this document: the word is the bare
message type, the handler table order was recorded backwards, and the
`0x8b119354` "open tension" was a misread of a name lookup. Read the handoff
first; this section is kept for the gating history.

### The msgbox was gated from cold

Its bus gate and reset at `0x0200171c` read `0x00000000` on a cold boot. Linux
takes `CLK_BUS_MSGBOX`/`RST_BUS_MSGBOX` for `msgbox@3003000`; U-Boot never did,
so every doorbell this project ever wrote went into a dead block.

Enabling bits 0 and 16 brings it up. The per-sub-block version register then
reads `0x00020000`, its documented value, which is the check that the block is
really alive.

**Enable it before reset release, not at send time.** The firmware configures
its own receive side during startup, so with the block gated that configuration
went nowhere. Enabling at send time left the message reaching the FIFO -- count
0 to 1 -- and the MIPS never draining it. Moving the enable into the shared
memory preparation fixed that: the firmware now drains the notification in
0 ms.

**That is the first successful ARM-to-MIPS delivery in this project.**

### The receive dispatch table

```
thunks 0x8b121644 / 0x8b12164c  ->  cpu 0 / cpu 1
  0x8b121598(cpu):  ctx = [0x8b22efe4] + 0x734 + 128*cpu
    0x8b1212cc(ctx):  type = ctx[+0x1c]
      0 or 1  ->  0x8b120bc0  command_action   (CALL / RETURN)
      2       ->  0x8b11ec9c(ctx, 0)           (CALL_ACK)
      3       ->  0x8b11ec9c(ctx, 1)           (RETURN_ACK)
      other   ->  assert, infinite loop
```

Two consequences. A type outside 0..3 **hangs the firmware**, so any doorbell
experiment must keep the type in range. And the type is read from a persistent
per-CPU context, not from the FIFO word directly -- something between the
interrupt and this dispatcher sets `ctx[+0x1c]`, and that path is not yet
traced.

### The doorbell encoding is not the variable

Four encodings were tried in one boot -- `0x00000002`, `0x00010000`,
`0x00000000`, `0x00010002` -- covering the type in either half with the
direction field at 0 or 2. **All four behaved identically**: FIFO drained in
0 ms, published index never consumed, no reply, board healthy.

The drain happens even for `0x00000000`, which the Linux tree documents as a
no-op the MIPS ignores. So a drain proves the interrupt handler ran, not that
the message was understood.

### The open tension

`0x8b119354` maps **cpu 0 -> 4** and **cpu 1 -> 0x18**. If the low half of the
doorbell is the direction field, `4` is the right value for an ARM-sourced
message. But a `4` in the low half is fatal if that half is instead the type,
because the dispatcher asserts and hangs.

This cannot be settled by guessing. Trace whatever writes `ctx[+0x1c]`: it
determines which half is the type, and therefore whether `db=00000004` is safe
or fatal.

### The handler contexts are pre-typed at init

`0x8b1221e0` populates them:

```
ctx = [0x8b22efe4] + 0x6d4 + (cpu*4 + index)*32
ctx[+0x18] = cpu
ctx[+0x1c] = index
```

confirmed against both handlers traced independently -- index 0 at `+0x6d4`,
index 3 at `+0x734`, 96 bytes apart, and `128*cpu` matching `(cpu*4)*32`.

So `ctx[+0x1c]` is **not** parsed from the message; it is the handler's own
index, fixed at init. The dispatcher at `0x8b1212cc` therefore routes on *which
handler ran*, which means the doorbell has to select the handler. Five
encodings say it does not, at least not by the model tried.

### The doorbell encodings tested, all negative

| word | high | low | result |
| --- | --- | --- | --- |
| `0x00000002` | 0 | 2 | drained 0 ms, not consumed |
| `0x00010000` | 1 | 0 | drained 0 ms, not consumed |
| `0x00000000` | 0 | 0 | drained 0 ms, not consumed |
| `0x00010002` | 1 | 2 | drained 0 ms, not consumed |
| `0x00000001` | 0 | 1 | drained 0 ms, not consumed |

The handler table order is `[0]=return, [1]=call, [2]=call_ack,
[3]=return_ack`, which is *not* the enum the Linux tree documents
(`0=CALL, 1=RETURN`). That made `type 1` look like the answer; it was not.

### Where the send stands

Transport works; content does not. The firmware takes the doorbell and never
consumes the shared-memory message. Everything through the notification is
proven on hardware; the failure is now isolated to how the message is
recognised.

## Board-B OSD handoff (2026-07-31)

This section supersedes the 2026-07-30 handoff below for anything it contradicts.
The panel now lights: PF6 is the correct board-B `panel_power_en`, and with it
asserted the firmware's internal colour source is plainly visible on the screen.
What does **not** appear is the OSD framebuffer.

### The one-line state

Everything from panel power through the LVDS PHY works. The MIPS firmware owns
the final output stage and composites its configured source — `source_id=1`,
VideoDecoder, an empty stream that is black by design — rather than our OSD
layer. That is the whole remaining gap.

### Proven on hardware this session

- **PF6 is panel power.** `PF_DAT=00000040`, and cutting it mid-run visibly
  changes the panel. PH16 (`panel_gpio_0`) latches correctly too; the old
  `gpio_set_value()` flag-loss defect is gone.
- **The firmware, not the ARM, drives the output stage.** With the coprocessor
  held in reset (`h713_disp panel-test <id> noboot`), `0x051c0000..0x0c` and
  `0x051c00b0..0xcc` all read zero, the scan counter at `0x05880000` is dead,
  and nothing at all reaches the panel — not even the internal colour source.
  With the firmware running, those registers are populated (including PHY
  geometry `0x051c00bc=05000030`, `0x051c00c0=02d00016`) and the raster runs.
  The doc's long-standing claim that the ARM path is not independent of the
  MIPS is now proven with registers rather than inferred.
- **AFBD is not the fault.** It is clocked (`0x02001dc0=80000005`, set by the
  vendor prologue, not by `h713_display_prepare()`), globally enabled
  (`0x05600000=80000020`), correctly sized/strided/addressed, and its enable at
  `0x05600144` latches and self-clears when the raster runs. Every AFBD-side
  explanation is closed.
- **The firmware does not tear our OSD down.** Dumping the fetch path before and
  after re-applying DE block 5 post-readiness yields byte-identical output.

### `panel_config.ini` is decoded and implemented

Stock does not write panel settings to MMIO directly. It parses its runtime DT
into a flat 35-entry `u32` array, overwrites the same array from
`/panel_config.ini`, then **patches the LogoRegData records in place** before the
generic applier runs them. The two name tables at stock `0x4a05ae30` (DT) and
`0x4a05a4fc` (INI) are index-for-index parallel, which is what makes the
override work.

The patch helper at `0x4a024894` is a bitfield insert:

```
patch(out, in_ptr, record, shift, fieldmask):
    require (fieldmask << shift) subset of record.mask   ; else log + skip
    if (*in_ptr < 0) return                              ; negative = unchanged
    record.value = (record.value & ~(fieldmask<<shift))
                 | ((*in_ptr & fieldmask) << shift)
```

All 32 call sites in the function at `0x4a0248fc` are transcribed into
`h713_disp_panel_patch()`. The mapping was validated by bit-width agreement:
1-bit flags land in 1-bit fields, the three-bit drive currents in `0x7` masks,
the six-bit DE current in `0x3f`, `MirrorMode` (0..3) in a two-bit AFBD field.

Two traps for whoever revisits this:

- The two fields in `0x05800000` do not consume the same setting. Bits 7:6
  take `Mapping`; bits 4:3 take `ColorDepth`. Board B supplies 0 and 8
  respectively, and the helper masks the latter to two bits, so both happen
  to insert zero on this board. The recovery model now represents the two
  inputs separately even though correcting the field name makes no MMIO or
  patch-count change for Board B.
- The compare at `+0x24e12`/`+0x24e26` matches **either** `0x0524c010` **or**
  `0x0525c000` and patches whichever record it found. Transcribing only one
  leaves the DE composing 1440x741 under a mixer at 1360x760. All 32 sites were
  re-scanned for this class of error; that was the only one.
- `0x0525c000` takes `PanelVTotal`/`PanelHTotal` (`0x02f80550`), not the active
  size. The helper does a straight insert with no minus-one.

Expected bench output is `18 record field(s) patched, 8 guarded by record mask`.
Any other counts mean the record framing diverged and the run is void.

`PanelLvds0Pol`/`PanelLvds1Pol` are absent from both the DT and the INI, so
their two sites are no-ops on this board. `panel_dual_port` (DT 1 -> INI 0) and
`SpreadSpectrumEnable` (DT 1 -> INI 0) are the only two fields where the INI
actually overrides the DT.

The verified artifacts are extracted to `local/mips-display/board-b-mips/`:
`panel_config.ini` (2513 B, SHA-256 `7bffff88...`, carved from `Reserve0_a` at
eMMC `0xa78a3600`) and `runtime-toc1.dtb`.

### Closed, so nobody re-runs them

- The mixer/DE geometry mismatch is fixed and was **not** the blocker.
- The AFBD module clock is **not** gated; the vendor prologue sets it. Do not
  add `h713_display_prepare()` to the fastlogo replay — it is redundant there,
  and the prologue already writes `0x02001050` and `0x02001db0/db4/db8/dc0/dd8`.
- Stock's LVDS PHY tail (`0x051c00d4..0xe0` written as a barriered group at
  stock `+0x22cca`) is now replayed, and is a no-op: the neighbouring registers
  already hold those values.
- Enumerating every MMIO literal in stock's fastlogo function (`0x4a0228d4`) and
  diffing against our sequence leaves **no remaining difference** except the
  deliberately-skipped `0x02001020` PLL_PERIPH0 write.
- `source_id=2` (Image) was patched at the correct offset — `0x4be01e48` is
  genuinely the `'1'` character. The firmware getting *less* far therefore means
  the Image path needs a registered image source, not merely a config value.

### Next, in priority order

1. **CPU_COMM.** The transport works: MIPS READY, application-ready, 82 HAL
   registrations, a validated 1224-entry call table. This is the vendor's
   designed interface for telling the firmware what to display, and it is the
   only route that addresses the actual gap.
2. **Stock register parity.** Still decisive, and now cheap: the registers that
   matter are known (`0x051c0000..0xcc`, the mixer layer words, AFBD). One dump
   from a stopped stock boot would likely settle it outright.
3. Do not spend more runs on ARM-side register archaeology. It is exhausted.

### Diagnostics available

```
h713_disp panel-test <id>            # full launch, dumps, AFBD probe, OSD
h713_disp panel-test <id> noboot     # same, MIPS held in reset -- repeatable
                                     # without a power cycle, since no launch
```

`noboot` exists because the launch rule (one per physical power cycle) does not
apply when nothing is launched. It is the cheap way to iterate on ARM-side
sequence changes.

## Board-B LCD handoff (2026-07-30)

This section is the short path for the next investigator. It consolidates the
latest board-B reverse engineering and supersedes older board-A GPIO
assumptions preserved later in the chronological log.

### Immediate conclusion

The MIPS firmware is no longer the leading bring-up blocker. With the required
shared-memory spinlocks and call entries initialized, repeated cold starts
reached:

```
CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005
firmware readiness proven by MIPS READY
application readiness proven
```

The recovery code also publishes a valid 1280x720 ARGB8888 buffer, can latch
the panel's 1360x760 timing, and produces electrical activity on at least one
LVDS pair. The important missing stock input was found in the **ARM-side
board-B boot artifacts**:

1. board B's runtime TOC1 DT names **PF6**, not PH19, as
   `panel_power_en`;
2. board-B stock U-Boot loads `panel_config.ini` from `/oem` and falls back
   to `Reserve0`;
3. that file changes the parsed display configuration to single-port LVDS,
   inverted DCLK, VESA mapping, 8-bit color, and PWM channel 5.

The prior PH19 power tests mixed board-B MIPS artifacts with a board-A TOC1
DT. They changed the PH19 software latch correctly but said nothing about
board-B panel power. Likewise, PB4/PWM2 is only the pre-override runtime-DT
choice and is not authoritative once `panel_config.ini` is loaded.

### Artifact identities and extraction coordinates

Keep the two boards and the two U-Boot DTs distinct:

- complete board-B eMMC image:
  `local/h713-lab/captures/board-b/board-b-mmcblk0-20260705T075628Z.img`,
  7,818,182,656 bytes;
- board-B stock U-Boot:
  `local/mips-display/board-b-stock/u-boot-stock.bin`, 638,976 bytes,
  SHA-256
  `22c9afa98503d4ce0b2b929cf8109af034d841560fbd11baf4ad851197134440`;
- board-B `display.bin`: 1,255,696 bytes, SHA-256
  `4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`;
- board-B `database.TSE`: 282,464 bytes, SHA-256
  `27e2abad947f319b7b5da229f1b078a6a986592718f98dcd745215338fcd4f81`.

The relevant TOC1 begins at eMMC byte `0x00c00000`. Its runtime-DT item begins
at TOC1 `+0x11b400`, therefore eMMC `0x00d1b400`, and declares a `0x12000`
window. The DTB itself is 69,380 bytes, SHA-256
`3902567a079720921e226c9176877f49916c6bdabfb6d82885e65d9f0a7d58b0`.
(An earlier revision of this document recorded `06e5279c...` here; that hash is
wrong. All three board-B eMMC captures yield the value above at that exact
offset and size, and both byte-level facts quoted below — `panel_power_en` at
DTB `+0x9f64` and `panel_gpio_0` at `+0x9f9c` — match it.)
This is the DT parsed by the stock fastlogo path and is the authority for its
named GPIO descriptors.

Board-B stock U-Boot also embeds a **different control DT** at raw
`+0x964e8`, size `0x474b`. Its seven-cell `panel_power_en` value at raw
`+0x990d4` is `<0x0d 5 6 1 2 3 1>`, again identifying PF6, but it describes
additional panel GPIOs. Do not substitute that embedded control DT for the
runtime TOC1 DT when reconstructing the fastlogo object's descriptors.

### Exact board-B panel controls

The runtime-DT cells are:

```
panel_power_en = <0x2c 0x05 0x06 0x20>;  /* PF6, active high, pull-down */
panel_bl_en    = <0x2c 0x01 0x05 0x00>;  /* PB5 */
panel_gpio_0   = <0x2c 0x07 0x10 0x20>;  /* PH16, active high, pull-down */
```

The `panel_power_en` value is at DTB `+0x9f64`, bytes:

```
00 00 00 2c 00 00 00 05 00 00 00 06 00 00 00 20
```

It is at TOC1 `+0x125364` and eMMC `0x00d25364`. The `panel_gpio_0` value is at
DTB `+0x9f9c`, bytes:

```
00 00 00 2c 00 00 00 07 00 00 00 10 00 00 00 20
```

It is at eMMC `0x00d2539c`. The compiled board-B property string
`panel_power_en\0` begins in stock U-Boot at raw `+0x6200b`, bytes
`70 61 6e 65 6c 5f 70 6f 77 65 72 5f 65 6e 00`; its little-endian pointer is
at raw `+0x23be0`, bytes `0b 20 06 4a`. `panel_gpio_%d` begins at raw
`+0x62038`, with its pointer at `+0x23c60`, bytes `38 20 06 4a`.

H713 uses the new 0x30-byte PIO bank stride. The useful coordinates are:

```
PF6 linear GPIO       166
PF_CFG0               0x020000f0  (PF6 mux is bits 27:24)
PF_DATA               0x02000100  (PF6 data is bit 6)
PH_CFG2               0x02000158  (PH16 mux is bits 3:0)
PH_DATA               0x02000160  (PH16 data is bit 16)
```

The decoded board-B stock power method begins at U-Boot raw `+0x224e4`,
bytes `2d e9 f0 45`. On power-on it applies `panel_power_en`, walks the
present `panel_gpio_N` descriptors low with a 2 ms delay, then applies their
configured active values with a 5 ms delay. The first loop starts at
`+0x22528`, bytes `a0 46 4f f0 00 0a 58 f8 04 1b`; the second begins at
`+0x22554`, bytes `54 f8 04 1b a9 b1 38 22`. Only `panel_gpio_0` is present
in the runtime DT. The reconstructed board-B operation is therefore:

```
wait 550 ms
PF6 = high
PH16 = low
wait 2 ms
PH16 = high
wait 5 ms
wait the remaining 20 ms stock phase
```

The current recovery code implements that sequence. Its earlier PH19 version
did not.

The runtime DT also names `lcd_standby=PH15` and
`spi_cs/spi_scl/spi_sda=PH10/PH11/PH12`. Those names have no compiled
property-name occurrence in board-B stock U-Boot. They are possible inputs to
another component, but there is currently **no evidence** that the fastlogo
path bit-bangs those pins. Treat panel serial initialization as a hypothesis
to trace, not a step to copy blindly.

### The other missed input: `panel_config.ini`

Board-B stock U-Boot contains the following strings:

```
+0x61e7a  load file %s fail, try load panel_config.ini!
+0x61ea9  panel_config.ini
+0x61ec7  /oem
+0x61ef6  Reserve0
+0x61f47  load file panel_config.ini fail!
+0x61f98  PanelSetting
+0x62084  PWMSetting
+0x6208f  pwm_channel
```

The loader/distributor is around raw `+0x236ec..+0x238d4`. It tries `/oem`
first and then the `Reserve0` partition. In the board-B dump `Reserve0_a`
starts at eMMC byte `0xa7880000` and contains `/panel_config.ini`, 2,513
bytes, SHA-256
`7bffff88a8319c3cdd1a2cdba0fc26df9fdac16c01aedaea7cc20353bc618cc3`.
The file begins:

```
5b 50 61 6e 65 6c 53 65 74 74 69 6e 67 5d 0a 50
72 6f 6a 65 63 74 49 44 20 3d 20 35 32 0a
```

or `[PanelSetting]\nProjectID = 52\n`. Its relevant values are:

```
ProjectID              = 52
PanelWidth             = 1280
PanelHeight            = 720
PanelDualPort          = 0       # single port
OddEven                = 0
Mapping                = 0       # normal/VESA
ColorDepth             = 8
MirrorMode             = 0
PanelInvDCLK           = 1
PanelInvDE             = 0
PanelInvHSync          = 0
PanelInvVSync          = 0
PanelNoiseDith         = 1
PanelDCKLCurrent       = 7
PanelDECurrent         = 47
PanelODDDataCurrent    = 7
PanelEvenDataCurrent   = 7
PanelOnTiming0/1/2     = 20/550/75 ms
PanelMax/typ/MinHTotal = 1360/1360/1360
PanelMax/typ/MinVTotal = 760/760/760
PanelDCLK              = 62000000
PanelHsync/PanelVsync  = 20/2
PanelHBP/PanelVBP      = 40/20
PanelTimingWorkMode    = 2
pwm_channel            = 5
pwm_polarity           = 1       # low-level active
pwm_freq               = 40000
pwm_vs_lock            = 1
pwm_min/max/default    = 1/100/50
```

`ProjectID=52` decimal is `0x34`, while the MIPS artifact selection used in the
bench command is `0x33`. Record the discrepancy; do not assume these fields
share a namespace or silently change the proven `h713_disp ... 0x33` path.

The INI does not override GPIO names, so it does not weaken the PF6 finding.
It does override the runtime DT's `panel_pwm_ch=2`; consequently PB4/PWM2
tests are rejected as board-B brightness evidence. The runtime DT's PWM5 node
has no pinctrl properties, so the physical PWM5 route still needs static
tracing or a stock-register comparison.

### What the bench has and has not proven

Proven:

- the exact board-B `display.bin` is loaded as a raw MIPS32 little-endian image
  at ARM `0x4b100000`;
- its direct file-offset/load-address identity holds: for example raw
  `+0x88124` appeared at ARM `0x4b188124` in the earlier guarded patch test;
- firmware execution, MIPS READY, the 82-entry HAL registration set, and
  application READY all complete once 12 CPU_COMM spinlocks and 1,224 call
  entries are initialized;
- the MIPS can remain stable and does not need another speculative readiness
  patch;
- mixer and DE retain `0x02e4059f`, a size-minus-one 1440x741 internal
  processing size;
- the vendor timing table and `panel_config.ini` agree on 1360x760 total,
  1280x720 active. The recovery latch reads back
  `00000004 02f80550 02d00500 00140028 80000014 80010003`;
- the moving ARGB8888 test buffer at `0x6c100000`, 1280x720 with stride
  `0x1400`, is written, read back, and cache-cleaned;
- an internal TCON color source accepts and reads back its requested colors;
- at least one connector-side LVDS pair is driven. The 15.509-second Saleae
  analog capture has conductor means 1.1831 V and 1.2765 V, common-mode
  1.2298 V, and correlation -0.7864. Its stable per-second distribution is
  consistent with a clock pair but does not prove that identification.

Not proven:

- PF6 has not yet been tested on hardware by the corrected recovery build;
- the analyzer's former channel 2 was not on a switched 3.3 V rail. It rose
  slowly from about 0.64 V to 1.06 V and is an unidentified connector signal;
- the panel was powered during any earlier internal-color or framebuffer test;
- the current lane count, single/dual-port mode, mapping, DCLK polarity, color
  depth, and drive-current registers match the post-INI stock state;
- PWM5 reaches the backlight hardware;
- PH10/PH11/PH12 perform any required panel transaction;
- the suspected pair is definitely the LVDS clock rather than data.

Do not infer a downstream-LVDS fault from the earlier no-image runs: they used
the wrong board's panel-power GPIO. More framebuffer patterns cannot resolve
power, lane mode, mapping, or panel initialization.

The `Output_Resolution` reverse engineering is valid but not an active route.
`OUTPUT_TIMING_PROJECTOR` selector 3 maps to the 1360x760/1280x720 row and
selector 4 maps to 2200x1125/1920x1080. However, the one-shot entry marker
proved `_LoadTFDPanelTiming` is not called on this startup path. The selector
patch and marker have been removed. Do not reintroduce the raw
`display.bin+0x88124` patch; `panel-test` instead restores the known 720p TCON
values after MIPS startup.

### Current recovery build

`external/u-boot/arch/arm/mach-sunxi/h713_mips.c` now:

- drives PF6 through `0x02000100`;
- pulses PH16 through `0x02000160`;
- reports both mux and latch states;
- leaves shared fan/backlight enable PB5 asserted;
- no longer calls PB4 an authoritative brightness input or wastes six seconds
  toggling it;
- still does **not** implement the INI's single-port/mapping/DCLK/PWM5
  overrides because their final hardware writes have not been identified.

The last validated DDR3 artifact is:

```
build/out/u-boot-sunxi-with-spl-ddr3.bin
size    874009 bytes
sha256  4153a1983377eaa2e2edac85982df5aee19eae887b5405506ce2257cf30e88c1
```

It builds successfully with nine pre-existing 32-bit MMIO pointer-cast
warnings in the LogoRegData interpreter. `git diff --check` passes in both the
root repository and U-Boot submodule. The changes are intentionally uncommitted
for review.

### Resume plan, in priority order

The board was powered off at handoff. Preserve the rule: **one MIPS launch per
physical power cycle**. Plain GPIO/register reads before a MIPS launch do not
consume that run.

#### 1. Prove PF6 and the panel rail before reflashing

Cold boot the currently installed U-Boot to its prompt. Put analyzer channel 2
on the actual panel 3.3 V/VDD pin, retain channels 0/1 on the suspected LVDS
pair, and run:

```
md.l 0x020000f0 1
md.l 0x02000100 1
gpio set 166
md.l 0x020000f0 1
md.l 0x02000100 1
sleep 10
```

Expected software result: PF6's mux nibble becomes 1 and PF_DATA bit 6
(`0x40`) is set. Expected hardware result: the panel VDD rail makes a clear
step to its nominal voltage.

- If the registers change and the measured rail rises, the missing-power
  diagnosis is confirmed. Proceed to the corrected build.
- If the registers change but connector VDD does not, verify the connector
  pin, then locate the PF6-controlled load-switch input and output. The stock
  DT proves the logical control identity, not the connector pinout or health
  of the upstream regulator.
- If the PF6 registers do not change, resolve the U-Boot GPIO command/mux
  issue before involving MIPS.

#### 2. Run the corrected integrated test once

Flash the artifact identified above, physically power-cycle, start a UART log
and Saleae capture, and run exactly:

```
h713_disp panel-test 0x33
```

Record separately:

- the PF6/PF_DATA and PH16/PH_DATA printouts;
- whether panel VDD rises at the initial stock-power phase;
- whether the panel changes opacity at PF6 off/on or PH16 low/high;
- whether the suspected LVDS pair changes when the 720p timing is latched;
- whether internal white/colors appear after panel power and 720p timing;
- whether the moving framebuffer appears;
- MIPS READY and application READY;
- the final `0x05880020/+0x24` timing readback.

If this produces an image, reduce the diagnostic sequence into the permanent
boot order and then address Linux ownership. If it only changes panel opacity
or brightness, power control is solved and the remaining fault is signaling
configuration or initialization.

#### 3. If VDD is correct but no internal color appears

The best next discriminator is **stock-register parity**, not another
framebuffer:

1. If a reversible stock boot is available, stop it after the factory logo and
   capture these blocks with `md.l`:

   ```
   md.l 0x05800000 0x0c    # LVDS lane/map block
   md.l 0x05880000 0x10    # LVDS/TCON block
   md.l 0x058c0000 0x0c    # display PLL
   md.l 0x051c0000 0x08    # LVDS PHY
   md.l 0x020000f0 0x08    # PF mux/data neighborhood
   md.l 0x02000150 0x08    # PH mux/data neighborhood
   ```

   Compare them word-for-word with `h713_disp dump` after the corrected run.
   This directly exposes single/dual-port, lane-map, clock-polarity, and PHY
   differences without guessing register semantics.

2. In static analysis, continue from board-B stock U-Boot
   `+0x236ec..+0x238d4`. Recover the destination structure offsets for
   `PanelDualPort`, `Mapping`, `ColorDepth`, `PanelInvDCLK`, the four drive
   currents, and `pwm_channel`. Follow consumers of those fields to the final
   MMIO writes. Search literal/xref neighborhoods for the already observed
   blocks `0x05800000`, `0x05880000`, `0x058c0000`, and `0x051c0000`.

3. Replay only the confirmed differences in a new diagnostic, one category at
   a time:

   - single-port/lane count and odd/even selection;
   - VESA mapping and 8-bit depth;
   - inverted DCLK;
   - drive-current values;
   - PWM5.

   Keep the internal TCON white/color source active during these tests. It
   removes AFBD, framebuffer layout, cache coherency, and DE composition from
   the result.

#### 4. Resolve PWM5 independently

Do not return to PB4/PWM2. The post-INI setting is PWM5, polarity 1, 40 kHz,
default 50%, range 1..100. Because the runtime DT's PWM5 node lacks a pinctrl
route:

- follow the stock PWM channel field into its controller/pinmux calls;
- search the embedded control DT and stock pinctrl tables for a PWM5 function;
- compare PIO mux registers before and after a stock logo boot;
- only then attach the analyzer to the candidate brightness signal.

PB5 remains useful only as the shared fan/backlight-enable control. Fan motion
or tach activity does not prove the panel 3.3 V rail or PWM5 duty.

#### 5. Investigate panel-side serial initialization only with evidence

If power, 720p timing, LVDS clock, lane/mapping parity, and backlight are all
correct, trace the runtime-DT `lcd_standby` and `spi_*` pins:

- search `display.bin`, `ProjectID_0x0033.TSE`, database modules, and other
  stock binaries for the pin numbers or a software-SPI transaction;
- inspect xrefs to GPIO descriptor arrays rather than string occurrence alone;
- if stock firmware can boot, capture PH10/PH11/PH12 and PH15 during the logo
  transition and compare against the recovery run.

No compiled fastlogo property-name reference has yet tied these pins to stock
U-Boot, so this route comes after the confirmed INI and LVDS-mode work.

#### 6. Preserve established dead ends and safety boundaries

- Do not use PH19 as board-B panel power.
- Do not use PB4/PWM2 as final board-B brightness evidence.
- Do not source panel geometry from `LogoRegData.bin`; it is a register replay
  file. The projector database row and `panel_config.ini` independently give
  1360x760/1280x720.
- Do not treat mixer/DE `0x02e4059f` as TCON total geometry; 1440x741 remains
  an unexplained internal processing size.
- Do not patch `_LoadTFDPanelTiming`; the entry marker proved it dead here.
- Do not launch MIPS twice without a physical power cycle.
- Do not use the old Linux MIPS observer/loader path or touch MIPS control
  registers from Linux during bring-up.
- Do not touch `external/sunxi-tools` or the FEL/flash recovery documents in
  this display thread.

## Current status (2026-07-29)

The reviewed end state deliberately moves MIPS boot ownership out of Linux:

- the active Linux 6.18.38 series contains 31 patches; Gemini's 910-line
  `sunxi-mipsloader` patch and the later read-only MMIO observer are removed;
- the kernel, modules, both board DTBs, and bench FIT build from a fresh
  extraction;
- NSI, CPU_COMM, TVTOP, DECD, and GE2D remain disabled;
- the compiled bench DTB contains one MIPS object: a no-map reserved-memory
  pool at `0x4b100000+0x0e41000`. It has no MIPS platform device, boot-vector
  property, clock/reset handle, or control-register address;
- the linked kernel has no loader/observer symbols and Linux creates no
  `/dev/mips*` device;
- no display firmware is embedded in the kernel or root filesystem.

The current RAM-only kernel artifact is `build/out/h713-kernel.fit`
(7,701,060 bytes), SHA-256:

```
2791e08e4bc18f5b032829bb98ad869711e22ccbd9b1870b38cd0695cd66b067
```

Its embedded kernel and bench DTB hashes are, respectively:

```
3a5c27c37eabaef514a4a4b43e87d87cd4bca40ee5320aa60f7a74c35fe028e1
23d37712e9822d44152dcb93ef0923f6b382288bdfea85a3cae6ae7397df3ac7
```

U-Boot verified both hashes before the 2026-07-27 bench boot. Linux reached
the Debian root shell and `systemctl is-system-running` reported `running`.
The UART log showed four CPUs, the ext4 root, eMMC, RTC, Panfrost, Cedrus,
AIC8800, serial getty, hotspot, Bluetooth attach, and SSH coming up. The only
MIPS lines in `dmesg` were reserved-memory initialization; `/dev/mips*` did not
exist. This passed the point where the observer-equipped kernel had stopped
responding.

The observer-equipped FIT, SHA-256
`3ee4e49beef8671e3727df319b7f2f1e7c79b0f04b4d16fd417664f2f7a361ce`,
is rejected evidence and must not be reused. Although its driver performed only
a register read, the board stopped responding after Linux clock takeover. The
safety boundary is therefore stronger than "read-only": Linux does not map or
touch the MIPS control registers during this phase.

The factory cold-start sequence is substantially narrower. Reverse engineering
the stock U-Boot
`0a44d54b3683453765fdbda93744eb5510b8d68ce829d1b0481c2cf2844e28f0`
shows that it loads `display.bin` at ARM physical `0x4b100000` and writes that
physical address, not its MIPS KSEG0 alias, to boot-address register
`0x03061030`. It then drives the MIPS clock/reset registers as follows, with
12 ms between reset stages and 300 ms after release:

```
0x02001600 <- 0x80000002
0x0200160c <- 0x00000000
0x0200160c <- 0x00010000
0x0200160c <- 0x00030000
0x0200160c <- 0x00030001
0x03061030 <- 0x4b100000
0x0200160c <- 0x00070001
```

UART-controlled tests established the hardware boundary:

- Writing stock register `0x051c0010 <- 0x01800045` by itself stalled both
  ARM UART and USB ACM. This register belongs to the factory fast-logo/LVDS
  sequence, not the standalone MIPS reset primitive. A power cycle recovered
  the board, and the known-good kernel subsequently booted cleanly.
- Replaying only the MIPS clock/reset sequence remained stable and changed CPU
  status register `0x0306101c` from zero to one. Status one therefore proves
  reset release, not firmware readiness.

Static analysis supplied a separate execution witness. The reset path enters
at the firmware's MIPS BFC vector, executes `eret` to `0x8b1b0868`, and then
clears BSS from MIPS address `0x8b232c00` through `0x8bac7c28`. The firmware's
observed address translation maps these to ARM physical
`0x4b232c00..0x4bac7c28`. Witness address `0x4b600000` is inside that loop but
is the first word beyond the five-megabyte window cleared by U-Boot. The
command writes `0x4d495053` there, flushes that ARM cache line, releases the
MIPS, then invalidates the line before reading it. Only a firmware-owned store
is expected to turn the seed into zero.

The ownership boundary is now explicit: U-Boot proper loads, verifies, and
releases `display.bin` before Linux. SPL remains responsible only for DRAM and
normal boot prerequisites unless a specific clock/interconnect dependency is
later proven to require earlier setup. Linux must not reload or restart the
coprocessor; its eventual role is reserved-memory protection and post-boot IPC
or display management.

A manual U-Boot command implements this boundary without changing autoboot.
`h713_mips load` reads the exact 1,256,216-byte image from a filesystem, clears
the five-megabyte firmware window, and accepts only SHA-256
`16c74a28187f342de657828fab65145b140ac9411c40cccc02eed25047472ee9`.
Separate `verify`, `start`, `stop`, and `status` operations keep each bench
transition observable. Before reset release, `start` applies only the
bench-proven display PLL/module-clock, TVTOP-routing, and mixer prerequisites.
It deliberately excludes LVDS, PH pinmux, TVCAP, HDMI, and INCAP. `start`
requires both CPU status one and the independent BSS-clear witness; it returns
the core to reset if either check fails.

The first installed and hardware-tested DDR3 bench artifact containing the
execution-witness command was 844,537 bytes, SHA-256:

```
493c45149a84e528f04b4b5861853cbbff43543bbd7048602966aca7d920d1ce
```

The current installed DDR3 build incorporates the proven display prerequisites
and deletes the unsafe experimental `factory-start` path. It also disables the
MIPS clock in `stop` after asserting reset. It is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (844,537 bytes), SHA-256:

```
956a03a61693add8c281f6f2678609e8d427a972b0797a3bd09b22fd8428fef2
```

The command is compiled into U-Boot proper and is absent from SPL as designed.
It is enabled only in the DDR3 bench defconfig, not the projector defconfig,
and it is manual: the normal autoboot path remains unchanged.

Bench execution validated the negative and transition paths:

- uninitialized firmware was rejected and left reset/status zero;
- the known image transferred by YMODEM produced the pinned SHA-256;
- deliberately dirtied bytes beyond the image were cleared before start;
- `start` reproduced the stock staged reset transition and reported status one
  with physical boot address `0x4b100000`;
- on three fresh firmware loads, the BSS witness changed from `0x4d495053` to
  zero while status remained one, independently proving that the MIPS fetched
  and executed its firmware startup code;
- the running firmware modifies bytes in its loaded image. A second `start`
  without restoring a pristine image produced SHA-256
  `6a7a86d23be26a712c6af9671acfd06ed4bcdb1d7216fa89949f6fca3d2bccde`;
  the pinned-image check rejected it and kept the MIPS in reset. Every new run
  must therefore use `load`/`boot` or otherwise restore the pristine image;
- UART and USB ACM remained responsive during all three runs, and `stop`
  returned reset, status, and boot address to zero.

The first post-test Linux handoff stopped producing UART output during driver
bring-up. At that point `stop` had asserted reset but left MIPS clock register
`0x02001600` at `0x80000002`, unlike its cold-boot value of zero. A follow-up
build disabled that clock after asserting reset and was hardware-verified to
return clock, reset, status, and boot address to zero. Linux nevertheless
stopped at the same point after the start/stop cycle. The lingering clock was
therefore not the sole cause. Abruptly resetting active firmware may leave an
outstanding transaction or another display/interconnect register in a state
that reset does not unwind.

Do not treat `stop` after successful execution as a clean Linux handoff. The
intended ownership-model test instead loaded and started the MIPS in U-Boot,
left it running, and booted the protected-memory Linux image. A power cycle
remains the known recovery for a failed post-execution handoff.

The initial live-MIPS handoff reached Linux but stopped deterministically in
the Panfrost probe. Panfrost printed its 864 MHz core and 100 MHz bus clock
rates, then the machine stopped before the next, normally immediate GPU-ID
line. The same boundary occurred after an execute/stop cycle and with the MIPS
left running, so the stop implementation was not the root cause. MIPS startup
needed an earlier display-fabric prerequisite before Linux's first GPU MMIO
access.

A one-boot `modprobe.blacklist=panfrost` isolation test confirmed the boundary:

- the pinned firmware passed its hash and BSS execution witness and remained
  running across the Linux handoff;
- the kernel command line contained the temporary Panfrost blacklist;
- Cedrus, AIC8800, networking, SSH, serial getty, and the Debian root filesystem
  came up;
- `systemctl is-system-running` reported `running` with no failed units;
- Panfrost and DRM scheduler modules were absent, and Linux still created no
  `/dev/mips` device.

The blacklist was transient and was not saved to the U-Boot environment or
kernel image. A normal reboot after the isolation test removed the blacklist,
left the MIPS off, loaded Panfrost, reached `systemd` state `running`, and
reported no failed units.

Register isolation then recovered the missing prerequisite. SPL already leaves
the display bus clock/reset enabled, but the video2 PLL parent and the deint,
panel, SVP-DTL, and AFBD module clocks are gated. The safe pre-start sequence:

```
0x02001050 |= BIT(31)       # video2 PLL parent
0x02001db0 |= BIT(31)       # deint, cold divider preserved
0x02001db4 |= BIT(31)       # panel, cold divider preserved
0x02001db8 |= BIT(31)       # SVP-DTL, cold divider preserved
0x02001dc0 |= BIT(31)       # AFBD, cold divider preserved
0x02001dd8 |= BIT(16)|BIT(0)

0x05700004 <- 0x00000001
0x05700044 <- 0x11111111
0x05700088 <- 0x11111111
0x05700000 <- 0xfff11111
0x05700040 <- 0x00011111
0x05700080 <- 0x00001111
0x05700084 <- 0xfff000ef
0x0525c038 <- 0x00000100
```

With only those writes, the mixer remained readable, the MIPS passed its BSS
execution witness, and Linux booted with Panfrost enabled. Panfrost read GPU ID
`0x7093`, reported one shader and one L2, registered DRM minor zero, and created
`/dev/dri/card0` plus `/dev/dri/renderD128`. Debian reached `running` with zero
failed units. The same handoff passed first as a manual register experiment and
again from the installed cleaned U-Boot implementation.

The broader factory sequence is not safe to carry forward. A diagnostic
`factory-start` path containing PH, TVCAP, HDMI, and LVDS phases wedged after
MIPS release and has been deleted. Direct INCAP access at `0x06940000` wedges
independently even after reconstructing the display and TVCAP clocks and was
also excluded. LVDS registers become ARM-accessible once the display clock tree
is prepared, but no LVDS write is required for the proven Linux handoff, so
they remain out of `h713_mips`.

The specific claim that stock register `0x051c0010 <- 0x01800045` stalls ARM
UART and USB ACM is **withdrawn**. That observation predates
`h713_display_prepare()` and was a clocking artifact, not a property of the
register. Retested on the bench on 2026-07-28 with the MIPS held in reset and
only the prepared clock tree applied by hand:

- the whole LVDS window `0x051c0000..0x051c0057` reads back zero, so the block
  is idle rather than absent;
- `0x051c0010` is readable, and the stock write lands and persists — a
  subsequent read returns `0x01800045`;
- the write is repeatable: two back-to-back writes both completed, and no other
  register in the window changed, so it behaves as a standalone enable rather
  than the entry point of a state machine;
- UART stayed responsive throughout. An observed reset during the first attempt
  was the 16 s watchdog expiring (`wdt start` does not self-service), not a
  stall; re-running the whole sequence inside a single `;`-separated line
  reproduced the writes with no reset.

The cold module-clock dividers were captured in the same session and
independently corroborate the recovered frequencies: `0x02001050` is
`0x08003101` (N=49, 1200 MHz), and deint/panel `0x00000007` (÷8 = 150 MHz) and
SVP-DTL `0x00000005` (÷6 = 200 MHz) match the documented rates. AFBD
`0x00000000` (÷1) implies 1200 MHz, not the 600 MHz recorded earlier; treat the
AFBD figure as unverified. `0x02001dd8` already reads `0x00010001` cold, so
that line of `h713_display_prepare()` is a no-op against the current SPL.

The general lesson is that "this register wedges the interconnect" has meant
"this block was unclocked" every time it has been run down. Apply the same
suspicion to the remaining exclusions — INCAP at `0x06940000` in particular —
before treating them as hardware limits.

## Firmware startup trace (2026-07-28)

`h713_mips probe-trace` instruments the authenticated image with 671 volatile
word patches — code caves plus `j`/`jal` redirection — that store marker ids to
the firmware's uncached `0xae340000` alias, visible to the ARM at
`H713_MIPS_SHMEM_ADDR + H713_MIPS_TRACE_OFF`. Markers are streamed to UART as
they change rather than dumped after the poll loop, because the failure being
chased stalls the interconnect and kills the ARM console; a post-hoc dump
returns nothing in exactly the case that matters.

A marker fires when its call is **entered**, so the last marker reported names
a call that never returned. Relevant sites:

| Marker | Site | Enters |
| --- | --- | --- |
| 17 | `0x4b152cf0` | `0x4b10e770` (config parser, passed `0xabe01000`) |
| 20 | `0x4b152d10` | `0x4b159a60` (`memset`) |
| 24 | `0x4b152d30` | `0x4b152b2c` (early system init) |
| 30 | `0x4b10d598` | `0x4b115cec` |
| 44 | `0x4b152c24` | `0x4b152a5c` (nine `0x3003xxxx` resource loads) |
| 45 | `0x4b152c2c` | `0x4b1895c4` |

### The firmware needs three artifacts, not one

The startup hang was **missing vendor artifacts**, not a hardware gate. Stock
U-Boot loads a firmware image, a config blob, and a set of TSE databases; every
earlier run staged only the firmware.

Marker 20 is `memset(cfg["sys:dbg_buf"], 0, cfg["sys:dbg_buf_size"])`. Both
arguments come from config lookups (`0x4b10d40c` and `0x4b10d444`, each fetching
a singleton at `0x8b2536bc` and calling its `vtable[0x14]` with a string key).
With no config staged the parser at marker 17 reads uninitialized DRAM at
`0xabe01000`, the keys resolve to garbage, and `memset` walks a bad pointer
until the bus stalls.

`display_cfg.xml` documents the layout, and the parser's `0xabe01000` argument
is exactly the uncached alias of its `cfg_file` LMA:

| Region | LMA | Size | Staged from |
| --- | --- | --- | --- |
| boot code + C code | `0x4b100000` | `0xc01000` | `display.bin` |
| debug buffer | `0x4bd01000` | `0x100000` | — (cleared) |
| cfg file | `0x4be01000` | `0x40000` | `display_cfg.xml` |
| TSE data | `0x4be41000` | `0x100000` | concatenated `*.TSE` |
| frame buffer | `0x4bf41000` | `0x1a00000` | — (cleared) |

The TSE window takes `database.TSE`, `projecttable.TSE`,
`ProjectID_0x0012.TSE`, and `pq_custom.TSE` **simply concatenated** in that
order (347,816 bytes; kept as `local/mips-display/tse_blob.bin`). Each file is
magic-tagged `TSE` plus a type byte, so the firmware evidently scans for the
magic rather than indexing fixed offsets. Stock U-Boot selects the ProjectID
file via a `mips_projectID` value; `0x0012` is the literal in its binary.

Stage each window with its own fastboot pass and exit with `fastboot continue`
— a warm reset destroys staged DRAM (see [flash.md](flash.md)). `probe-trace`
clears everything above the image except the config and TSE windows, so those
two survive; the firmware image must be re-staged for every run because both
the trace patches and the running firmware modify it.

### Run protocol: one probe per boot

**A `probe-trace` or `probe-ready` run leaves hardware state that breaks the
next run**, and `h713_mips_stop()` does not clean it. The symptom is a stall at
marker 12, the firmware's interrupt init. After a run, even U-Boot's `reset`
command hangs, so recovery is a physical power cycle.

This single rule accounts for every irreproducible result recorded earlier in
this document. Runs that looked like they proved TVCAP ordering, TSE damage, or
non-determinism were second-or-later runs on one boot. Bench procedure:

1. power cycle;
2. `mw.l 0x4be01000 0 0x50000`;
3. stage `display_cfg.xml`, the TSE blob, then `display.bin`;
4. `h713_mips verify` — must print `16c74a28...`;
5. exactly one `h713_mips probe-trace` (or `probe-ready`).

Treat any result from a second run on the same boot as void.

### TVCAP: the ARM does enable it, with specific values

This section previously said the ARM must leave TVCAP alone. That was drawn
from `probe-trace` A/B runs which set the gates with `|= BIT(31)` and released
them mid-run from the poll loop; both harmed firmware startup.

Stock U-Boot's fastlogo disproves the general claim. It enables TVCAP with
explicit values as part of bringing up the display:

```
0x02001d88 <- 0x00010001    bus gate + reset
0x02001d6c <- 0x80000305    TCD3
0x02001d74 <- 0x81000001    VINCAP DMA
0x02001d84 <- 0x80000000    HDMI audio
0x02001d80 <- 0xc0000000    TVCAP bus
```

So the rule is about *values and ordering*, not about ownership. Do not set
these gates by OR-ing an enable bit onto whatever the cold state happens to be.

### Current state: the MIPS never receives a timer interrupt

With all three artifacts staged and one run per boot, the firmware executes
every instrumented point: markers 10-14, 16-24, 26-53, 62-66, 68-78, 84-89,
93-96, 101-104, 111, and 130-132. The HDMI-RX byte load at physical
`0x06840093` succeeds, and the four-registration group at `0x8b128020`
completes. `status` is 1, the BSS witness is clear, both CPU_COMM magics read
`deadbeef`, and the ARM flag reads back `0x5`. An uninstrumented `probe-ready`
with a ten-second budget behaves the same.

`MIPS READY` is never set, and the trace explains why. Markers 1-9 — the entire
CPU_COMM path — never fire:

```
0x4b15257c   ThreadX thread entry           (markers 6, 7)
  0x4b12423c   CPU_COMM init                (markers 8, 9)
    0x4b123828   share-register reader      (markers 1, 2, 3)
    0x4b11abbc   spinlock + slave init      (markers 4, 5)
```

`0x4b15257c` has no direct callers; its address is materialised into `$a3` at
`0x4b152d38`/`0x4b152d44` and handed to a thread-creation call. That call sits
between marker 24's site (`0x4b152d30`) and marker 25's (`0x4b152d54`). Marker
24 fires and marker 25 does not, so the early-system-init call never returns
and the thread is never created.

The innermost stall is marker 53's call into `0x4b1839dc` (marker 54 does not
fire). Inside it, trace slots 104 and 105 — which capture the polling loop's
current and initial tick rather than marker ids — both read **zero**. The loop
is `while ((now - start) < 0x33)`, so a tick that never advances never expires.

The tick source is a software counter at `0x4b252cc0` (BSS), read under an
interrupt-disable/restore pair at `0x4b104b04` and incremented by a timer ISR.
It reads zero, so **the MIPS is receiving no timer interrupt**. The complete
chain is:

> no MIPS timer IRQ -> tick counter stays 0 -> the wait loop never expires ->
> `0x4b1839dc` never returns -> thread creation never runs -> the CPU_COMM
> thread never starts -> `MIPS READY` is never set.

The firmware does program an interrupt block: marker 12's function
`0x4b147950` clears CP0 Cause IP bits and writes `0x03061300..0x03061320` in
the MIPS control window. What is not yet established is where the timer source
lives, whether its clock or reset needs releasing from the ARM the way the
display tree did, and whether the CP0 `Status` interrupt enable is being set.
That is the next thing to recover.

The `0x4b22cf68` flag consulted before each tick read is initialised data whose
image value is `1`, so the stub path is not the issue; the real read is taken
and returns zero.

**Framing correction.** Calling "no timer interrupt" the root cause is too
strong. The tick is a ThreadX software counter incremented by the CP0 Compare
ISR, and interrupts are legitimately masked this early in startup, so a
stopped tick is expected at that point rather than a fault. The real defect is
that `Rx_HDCP14_LoadKey` polls HDMI-RX `0x06840093` for an acknowledgement
that never arrives, and its timeout — which stock relies on to recover — cannot
expire while the tick is stopped. The timer needs no CCU gate either: it is the
MIPS core's own CP0 Count/Compare, and the coprocessor cannot reach the CCU at
all, so every clock it depends on must come from the ARM.

## The ARM display path, and why it is not independent

`LogoRegData.bin` is a fourth vendor artifact that stock U-Boot parses and
applies itself before blitting its logo, as its own strings show
(`Invalid logo regbin:%s`, `create_fastlogo_inst fail!`,
`Display fastlogo finish!`). It is a masked register write-table of 16-byte
`{address, value, mask, type}` records where type 1/2/4 is the access width and
a zero address with type `0xff` carries a delay. Records are 16 bytes but only
4-byte aligned and the stream changes phase between runs, so a walker must
resynchronise rather than step a fixed lattice.

The container is **indexed**. Descriptors of `0x18` bytes start at offset `0x10`,
their count given by the header at `+0x08` divided by `0x18`. Each begins with a
project ID matching the `ProjectID_*.TSE` filenames, and two words select that
project's tables:

| Field | Selects |
| --- | --- |
| word3 & 0xffff | prologue variant, 1-based |
| word3 >> 16 | timing variant, 0-based |
| word4 & 0xffff | DE/mixer variant, 0-based |

A working configuration is a *consistent triple*, not three ranges picked by
eye; choosing them by hand produced combinations no project uses.

**The ARM path is not independent of the MIPS.** Stock's fastlogo releases the
coprocessor as an integral step of putting its logo on screen, so a boot console
cannot be reached from the ARM alone.

### Use the board's own artifacts

Everything in this project had been derived from a captured dump that is **a
different firmware revision than the bench board carries**:

| Artifact | Board | The dump previously used |
| --- | --- | --- |
| `display.bin` | 1255696 B, `4380f1b3...` | 1256216 B, `16c74a28...` |
| `LogoRegData.bin` | 15652 B, 15 descriptors | 14380 B, 13 descriptors |
| stock U-Boot | `2018.05-00027-ge159793` (Aug 2025) | `2018.05-00021-g346d3eb` (Mar 2025) |

Consequently the pinned hash, every block offset, the project-to-table mapping,
the HDCP wait address, the BSS bounds and the 671-entry trace table were all
wrong. Any conclusion measured against them is void, including the earlier
four-project sweep and the whole marker map.

The board's copies live in the stock FAT bootloader partition at `mmc 1:2`, and
`h713_disp auto <project>` reads them from there. Extracted copies are kept in
`local/mips-display/board-b-mips/`, and the board's real stock bootloader --
pulled from its TOC1 container at `0xc00800` in the eMMC capture -- in
`local/mips-display/board-b-stock/`. Slots A and B are byte-identical.

Stock's fastlogo sequence is **byte-identical between the two U-Boot builds**,
so the transcription below stands; what was wrong was the data it was pointed
at.

### Stock fastlogo, transcribed

The stock U-Boot is **Thumb**, not ARM -- its first word is only the exception
vector. Load base `0x4a000000`, verified by every string address appearing as a
literal. In the board's build `"Display fastlogo finish!"` prints at
`0x4a022c3a`.

```
0x02000150 <- 0x22ffff22    PH pin mux (PH0/1 stay UART0)
0x02001d88 <- 0x00010001    TVCAP gate/reset
0x02001040 <- 0xb8003501    PLL enable (cold state is off)
0x02001d6c <- 0x80000305
0x02001020 <- 0xb8006301    PLL_PERIPH0  -- SEE HAZARD
0x02001d74 <- 0x81000001
0x02001068 <- 0xb8002f01    PLL enable (cold state is off)
0x02001d84 <- 0x80000000
0x02001d80 <- 0xc0000000
0x06e00004/8/0 set, cleared, set again   (reset pulse)
0x06940000 <- 1             INCAP
0x051c0010 <- 0x01800045    LVDS enable
<MIPS clock/reset/bootaddr/release>
delay 300 ms
0x051c0010 <- 0x45          LVDS finalise
```

Within the table-application loop, stock also issues an LVDS FIFO reset after
the timing table -- pulse bit 8 of `0x05700088`, then **rewrite `0x0588000c`
with its saved value** -- and writes `0x0525c038 <- 0x100` before the DE table.

**INCAP does not wedge.** `0x06940000 <- 1` is safe once the fabric is
configured, on stock and on ours.

**TVCAP is enabled by the ARM**, with the explicit values above rather than by
OR-ing an enable bit onto the cold state.

**Hazard: do not write `0x02001020`.** That is PLL_PERIPH0, which clocks MMC and
the buses. Stock writes a value already in force in its own boot context; ours
runs at `0xb8003100`, and replaying stock's write powers the bench board off.
`0x02001040` and `0x02001068` are safe because both are disabled cold.

**Bench hazard: unplug USB after staging.** With the DC adapter and USB both
connected the board browns out when the display fabric comes up. Two brown-outs
were misattributed to register writes before this was identified.

### Firmware facts, re-derived from the board's image

- boot vector erets to `0x8b1b1148`
- BSS is cleared from `0x8b232c00` to `0x8bac7c40`
- `Rx_HDCP14_LoadKey` polls HDMI-RX `0x06840093` with its wait bound at
  `0x4b13d6f8`; `h713_disp ... nowait` rewrites it so the wait expires at once
- the execution witness sits *inside* BSS, so the firmware zeroes it and then
  reuses that memory. Only the seed surviving proves non-execution; a zero or
  any other value proves the write

### Where it stops

With the board's own artifacts, a consistent project triple, stock's sequence
and the coprocessor executing, the panel stays dark and the LVDS FIFO at
`0x05880FE0` never changes between consecutive reads. Projects `0x16`, `0x33`,
`0x34` and `0x35` -- the ones selecting the timing variant that matches this
panel -- were all tried, with and without the HDCP override.

`display_cfg.xml` carries an `elog_init_setting`. With `mode='2'` (buffer) and
`async_display='0'` the firmware runs and logs **nothing at ERROR level**, so by
its own account startup completes without faults. It does, however, wedge the
interconnect some seconds *after* the sequence completes, which suggests live
activity that later fails rather than a coprocessor sitting idle.

Open threads, in priority order:

1. `source_id` in `display_cfg.xml` is `1` (VideoDecoder), not `2` (Image). A
   faithfully-displayed empty decoder stream is black by design and would log
   no error. Patch it at `0x4be01e48` after `h713_disp load`.
2. Raise the elog level with `async_display='0'` and read the firmware's own
   account of what it does before it wedges.
3. Time the delayed hang; a consistent interval points at a firmware timer.
4. Rebuild the trace instrumentation against `4380f1b3...` if markers are needed
   again -- the existing 671-entry table targets the wrong image.

## Fixed: the walker dropped `type 0xfe`, and its delays were in the wrong unit

`h713_logo_walk()` in `arch/arm/mach-sunxi/h713_mips.c` understood three record
types: 1/2/4 (a masked write of that width) and `0xff` with a zero address (a
delay). Anything else it skipped by advancing four bytes and resynchronising,
which silently discarded a fourth type. The delay unit was a guess.

Both are now settled by reading the vendor applier, not by inference. Stock
U-Boot 2018.05 for this board (`local/mips-display/board-b-stock/u-boot-stock.bin`)
is **32-bit ARM, Thumb-2, load base `0x4a000000`** — not AArch64, which is why
earlier disassembly attempts produced noise. The record applier is at
`0x4a025164`, reached through the ops table at `0x4a025488+0x24`; it belongs to
the LogoRegData module, whose neighbouring strings are `LogRegData.bin version
is %u-%u-%u-%u`, `Get reg of type:%u fail!` and `null fastlogo inst!!!`.

It walks a `{?, records, count}` descriptor, stride 16, type word at `+0xc`:

| type | what stock does |
| --- | --- |
| `<= 4` | `*addr = (*addr & ~mask) \| value`, **always a 32-bit access** |
| `0xfe` | one read, then `*addr = cur & ~mask`, then `*addr = cur \| mask` |
| `0xff` | `udelay(value)` |

Three corrections fall out of that:

**`type 0xfe` is not a poll — it is a masked bit pulse.** The `value` word is
never read. Our four records all carry `mask 0x80000000` on the display PLL at
`0x058c0014`, and bit 31 there is PLL_ENABLE, so each one is a **PLL restart**:
drop enable, raise it again. They sit at container offsets `0x0ec4`, `0x1734`,
`0x1d1c`, `0x1fa4`, and the one at `0x1734` is inside **timing block 6 — the
block this panel uses** — in the middle of a divider reprogram:

```
+0x16e4 0x058c0014 <- 0x08000000 mask 0x08000000
+0x16f4 DELAY 500 us
+0x1704 0x058c0028 <- 0x00000000
+0x1714 0x058c0014 <- 0x0000001e mask 0x0000fffe   reprogram divider
+0x1724 DELAY 15000 us
+0x1734 PULSE 0x058c0014 mask 0x80000000            PLL off, PLL on
+0x1744 DELAY 15000 us
+0x1754 0x058c0014 <- 0x00002a00 mask 0x0000ffff   restore divider
+0x1764 0x058c0028 <- 0x00030000
```

We were skipping the restart outright, so everything written after that point
in the block landed on a PLL that had never been re-locked.

**The delays are microseconds.** `0x4a000d74`, the thunk the walker calls, tail-
branches to the delay core at `0x4a000d50`, which reads CNTPCT and busy-waits
`value * 0x18` ticks — 24 ticks per microsecond on the 24 MHz arch timer. The
`x1000` wrapper immediately after it at `0x4a000d78` is `mdelay`, and the walker
does *not* use it. So the old `mdelay()` path was 1000x too long before the cap
and wrong after it: the whole container is ~126 ms of delay in stock and was
about 4.6 s for us, with the two 15000 waits bracketing the PLL restart cut to
200 ms each. `H713_LOGO_MAX_DELAY_MS` is replaced by `H713_LOGO_MAX_DELAY_US`
at 100000, which only bounds a walk that has fallen into garbage — stock has no
ceiling at all, and the largest genuine value is 15000.

**The width field is vestigial.** Stock uses a 32-bit `ldr`/`str` for every
type in `0..4`. Moot for this container — all 838 write records are type 4, and
there is not a single type 1 or 2 — so the width switch is left in place.

The four `0xfe` records are also *new in this firmware revision*: the superseded
`research/bootloader_fat` extract has 774 writes, 89 delays and no `0xfe` at
all. Same for values — `+0x1664` writes `0x058c002c <- 0x00070010` where the old
extract had `0x00000010`.

### Bench result (2026-07-29): the fix works, the panel stays dark

Timing block 6 now applies `32 records, 1 pulse, 7 delays, 0 resync steps`, and
`0x058c0014` reads back `b9002a00` against the `a9002a00` the table writes. The
one differing bit is 28 — **PLL lock, set by hardware**. It cannot have been set
with the restart skipped, so the vendor's PLL sequence now completes correctly
for the first time. That is the `0xfe` defect closed, on hardware.

It did not light the panel, and it did not move `0x05880FE0`.

Two details from the same disassembly that our sequence still does not model,
both in the fastlogo state machine at `0x4a0228d4`, which applies groups
`0..count-1` where count is a `u16` at `inst->0x34 + 0x104`:

- stock's FIFO reset after group 1 is **conditional** on `readl(0x05880fe0)`
  being non-zero; `h713_disp_fifo_reset()` does it unconditionally.
- the mixer write (`0x100` to `0x0525c038`) happens *before* group 2 is applied,
  which is where we put it — that much is confirmed.

## The firmware overrides the panel timing with 1080p

Dumping the display blocks after `h713_disp auto 0x33`, with the coprocessor
running, and diffing against a replay of what prologue 3 + timing 6 + DE 5
actually wrote: **54 of 65 dumped registers hold exactly the written value.**
Eleven do not.

| register | table wrote | reads | who |
| --- | --- | --- | --- |
| `0x05700000` | `ffffffff` | `fff11111` | **ours** |
| `0x05700004` | `ffffffff` | `00000001` | **ours** |
| `0x0588001c` | `00000004` | `00000002` | firmware |
| `0x05880020` | `02f80550` | `04650898` | firmware |
| `0x05880024` | `02d00500` | `04380780` | firmware |
| `0x05880028` | `00140028` | `00290114` | firmware |
| `0x0588002c` | `00000014` | `8000003e` | firmware |
| `0x05880030` | `00010003` | `80040007` | firmware |
| `0x058c0014` | `a9002a00` | `b9002a00` | hardware (PLL lock) |
| `0x051c0014` | `18000000` | `18000040` | unattributed |
| `0x05600168` | `000003b2` | `00000002` | firmware (AFBD status) |

Reading `+0x20` as total geometry and `+0x24` as active, the LVDS group goes from
**1280x720 active / 1360x760 total** — the panel — to **1920x1080 active /
2200x1125 total**, standard 1080p60. `+0x28` moves consistently with it and
`+0x2c`/`+0x30` come back with bit 31 set.

Nothing in the container writes those values: timing block 6 is the only block
that touches `0x05880020`/`0x24` and it writes 720p, and no record anywhere in
the file writes `04650898` or `04380780` to them. The only ARM code after the DE
table is the clocks/TVCAP step, INCAP, `0x051c0010` and the MIPS release, none in
`0x0588xxxx`. So the coprocessor is the only candidate — **an inference from
exhaustion, not an observation**, and it should be treated as such.

Meanwhile the mixer, DE and AFBD stay at 720p (`mixer +0x20`/`+0x30` =
`02d00010`, AFBD `+0x20` = `02d00500`). The pipeline feeds 720p into a TCON
programmed for 1080p.

**The firmware does not defend the registers.** Re-imposing 720p after it has
run sticks — verified both with the raw table records and, when that turned out
to clear the firmware's bit 31 on `+0x2c`/`+0x30`, again with those bits
preserved. Neither changed anything observable.

The generic `h713_mips start` path calls `h713_display_prepare()` and therefore
narrows TVTOP `0x05700000` to `0xfff11111` and `+0x04` to `1`. The fastlogo
replay does **not** call that helper: `h713_disp_run()` applies the three vendor
tables, then calls `h713_mips_release_raw()`, which verifies the image, applies
only the optional HDCP wait override, and releases reset. Therefore the earlier
claim that the fastlogo replay overwrites its table-programmed TVTOP values was
stale and is withdrawn.

One replay divergence remains: stock pulses the FIFO reset only when
`0x05880fe0` is non-zero, while `h713_disp_run()` currently pulses it
unconditionally. This is the first cheap parity fix.

### The projector selector lookup — mapped, but dead on this startup path

Traced in `display.bin` (MIPS32 LE, raw image; external review, verified here
against the artifacts).

`_LoadTFDPanelTiming` builds the `Output_Resolution` selector `0x00060004` from
a hardcoded immediate pair at raw offset `0x88120`:

```
0x88120:  06 00 02 3c    lui   v0, 0x0006
0x88124:  04 00 42 24    addiu v0, v0, 4
```

Parameter 6 is `Output_Resolution`. `_LoadTFDPanelTiming` asks the TSE object for
the row count through vtable slot `+0x48`, then calls slot `+0x5c` with field
number 6 at `display.bin` offset `0x881ec`. It compares the returned value with
the compiled selector at `0x881f0..0x88204`. For a matching row it obtains the
raw row pointer and copies selected fields from the 0x54-byte row at
`0x882e8..0x88374`. There is no second lookup through the compact u16 mode lists.

`database.TSE`'s `OUTPUT_TIMING_PROJECTOR` module name begins at `0x30c77`:

```
4f 55 54 50 55 54 5f 54 49 4d 49 4e 47 5f 50 52
4f 4a 45 43 54 4f 52 00                         OUTPUT_TIMING_PROJECTOR\0
```

It has six selector predicates, followed in the same order by six 0x54-byte
rows:

| selector | predicate offset and bytes | row offset | total | active |
| --- | --- | --- | --- | --- |
| 4 | `0x30ca9: 04 00 06 00` | `0x30df0` | 2200x1125 | 1920x1080 |
| 3 | `0x30ccd: 03 00 06 00` | `0x30e44` | 1360x760 | 1280x720 |
| 1 | `0x30cf1: 01 00 06 00` | `0x30e98` | 858x525 | 720x480 |
| 2 | `0x30d15: 02 00 06 00` | `0x30eec` | 864x625 | 720x576 |
| 8 | `0x30d39: 08 00 06 00` | `0x30f40` | 1500x825 | 1366x768 |
| 11 | `0x30d5d: 0b 00 06 00` | `0x30f94` | 938x480 | 640x360 |

The decisive selector-4 row fields are:

```
0x30dfc: 98 08 00 00    2200 total columns
0x30e10: 80 07 00 00    1920 active columns
0x30e20: 65 04 00 00    1125 total lines
0x30e34: 38 04 00 00    1080 active lines
```

They explain the exact `0x04650898` / `0x04380780` register readback without
using the unrelated compact 1080 tuple in `WCEData`. The earlier cited
`0x1e86f` is inside that separate payload; its compact geometry tuple actually
begins at `0x1e877`.

The selector-3 row is equally explicit:

```
0x30e50: 50 05 00 00    1360 total columns
0x30e64: 00 05 00 00    1280 active columns
0x30e74: f8 02 00 00     760 total lines
0x30e88: d0 02 00 00     720 active lines
```

This was missed by searching for a contiguous u16
`(1360, 760, 1280, 720)` tuple: the projector timing row stores separated u32
fields. It independently agrees with `LogoRegData.bin`, whose record at
`0x1838` writes `0x02f80550` to TCON register `0x05880020` and whose next record
writes `0x02d00500` to `0x05880024`.

The compact `(1440, 741, 1280, 720)` tuple does exist at `database.TSE`
offsets `0x1f9f9` and `0x2f376`, with bytes
`a0 05 e5 02 00 05 d0 02`, in the separate `WCEData` and `THDMI_ModeList`
payloads. None of the six projector selectors reaches it.

The mixer at `0x0525c000+0x00` and DE at `0x0524c000+0x10` both read
`0x02e4059f`, a size-minus-one encoding of 1440x741. That remains unexplained
internal processing geometry; it is not evidence that the TCON should use a
1440x741 total. The actual projector lookup and the vendor TCON register table
both identify 1360x760 as the panel timing.

So the timing input is a **hybrid**: geometry in the database, selector
initializer compiled into the firmware. Rewriting the `addiu` immediate from 4
to 3 requests the database's 1280x720-active projector row if that initializer
survives the following object call. The immediate byte is at `0x4b188124` once
the raw image is loaded.

**First hardware test, 2026-07-29: changing only that byte was a no-op.** Both

```
h713_disp auto 0x33 720p
h713_disp auto 0x33 nowait 720p
```

authenticated the expected firmware, reported selector 3, proved MIPS
execution, and then read back the unchanged values:

```
0x05880020 = 04650898    2200x1125 total
0x05880024 = 04380780    1920x1080 active
```

The HDCP override therefore has no bearing on the timing result.

The reason the immediate alone is insufficient is visible at the start of
`_LoadTFDPanelTiming`. The function initializes the selector stack slot at
`sp+0x28`, then calls vtable slot `+0x70` with `a1=6` and `a2=&sp[0x28]`:

```
0x88118: 28 00 a6 27    addiu a2, sp, 0x28
0x8811c: 70 00 43 8c    lw    v1, 0x70(v0)
...
0x88158: 28 00 a2 af    sw    v0, 0x28(sp)
0x8815c: 09 f8 60 00    jalr  v1
```

That makes the compiled value an initializer for an in/out parameter, not an
unconditional final selector. The hardware result shows that either this call
replaces it or this loader is not the final writer.

The revised patch keeps the getter call but redirects its in/out pointer to the
unused stack slot at `sp+0x2c`, initialized with the same default. The actual
comparison slot at `sp+0x28` then remains forced to selector 3:

```
0x88118: addiu a2, sp, 0x28 -> addiu a2, sp, 0x2c
0x88124: addiu v0, v0, 4   -> addiu v0, v0, 3
0x88138: sw zero, 0x24(sp) -> sw v0, 0x2c(sp)
```

`sp+0x2c` is otherwise unreferenced throughout the function. The `sp+0x24`
slot is an output pointer written by the row-fetch call immediately before it
is read. U-Boot guards all three stock instructions after authenticating the
firmware and refuses the patch if any differs.

For the second test, the prediction remained
`0x05880024 = 02d00500` (1280x720 active) and
`0x05880020 = 02f80550` (1360x760 total). If those registers remained 1080p,
the loader had to be dead on this startup path or overwritten by a later
writer.

**Second hardware test, 2026-07-29: the revised selector was also a no-op.**
The command read all three patched sites back from executable DRAM:

```
0x4b188118 = 27a6002c
0x4b188124 = 03
0x4b188138 = afa2002c
```

The TCON nevertheless remained at `04650898 04380780`. This rules out an ARM
cache/write-visibility failure and rules out the vtable `+0x70` getter as the
only reason the original byte patch failed. The remaining alternatives are
that `_LoadTFDPanelTiming` is not called on this startup path, or a later writer
replaces its result.

The next build instruments function entry to separate those cases. It replaces
the prologue at `display.bin+0x8810c` with a guarded jump to the unused zero
cave at `+0x300`. The cave writes `0x7133` through the firmware's uncached
`0xae340300` alias, executes the displaced stack adjustment, and returns to
`+0x88114`. U-Boot reads the corresponding ARM address `0x4e340300` after the
run and prints:

```
H713 MIPS: _LoadTFDPanelTiming marker=0x00007133   called
H713 MIPS: _LoadTFDPanelTiming marker=0x00000000   not called
```

**Third hardware test, 2026-07-29: the marker remained zero.** The authenticated
firmware ran and again changed the TCON to
`04650898 04380780`, but U-Boot printed:

```
H713 MIPS: _LoadTFDPanelTiming marker=0x00000000
```

Therefore `_LoadTFDPanelTiming` is not called on this startup path. The
selector-to-record mapping above is valid static analysis, but the immediate at
`display.bin+0x88124` is not the source of this run's 1080p write. Both the
selector patch and its one-shot marker have been removed from U-Boot; the
`h713_disp ... 720p` modifier no longer exists.

There is a separate panel-specific timing path. `display_cfg.xml` contains the
actual panel geometry at offsets `0x729`, `0x760`, `0x794`, and `0x7b3`
respectively (the literal ASCII bytes rendered below):

```
<htotal typical='1360' min='1360' max='1360'/>
<vtotal typical='760' min='760' max='760'/>
<hde_size val='1280'/>
<vde_size val='720'/>
```

In `display.bin`, the function beginning at raw offset `0x2a6ec`
(`98 ff bd 27`, `addiu sp,sp,-0x68`) is identified by its
`load_panel_timing` log string at `0xf1470`. It loads a database timing, then
queries the parsed XML keys. For example, the htotal override is:

```
0x2a88c: 1f 8b 05 3c    lui   a1, 0x8b1f
0x2a898: 09 f8 40 00    jalr  v0
0x2a89c: 38 bc a5 24    addiu a1, a1, -0x43c8
0x2a8a0: 02 00 40 10    beqz  v0, 0x2a8ac
0x2a8a4: 48 00 a2 8f    lw    v0, 0x48(sp)
0x2a8a8: 18 00 02 ae    sw    v0, 0x18(s0)
```

The address formed in the call's delay slot is `0x8b1ebc38`, whose raw string
at `display.bin+0xebc38` is
`73 79 73 3a 70 61 6e 65 6c 3a 68 74 6f 74 61 6c 3a 74 79 70 69 63 61 6c 00`
(`sys:panel:htotal:typical\0`). The corresponding vtotal key is at
`+0xebc8c`, and the store to timing-structure offset `+0x1c` is at
`+0x2a8d8` (`1c 00 02 ae`). The direct wrapper call to this loader is at
`+0x2a1a8` (`bb a9 c4 0e`, `jal 0x8b12a6ec`).

The wrapper is the `CrtcDb` virtual method at slot `+0x14`: the vtable begins
at raw `+0xf13ac`, and its slot at `+0xf13c0` contains
`8c a1 12 8b` (`0x8b12a18c`). The higher-level CRTC initialization path loads
the `CrtcDb` object from offset `+0x4f0` at raw `+0x27e94`
(`f0 04 04 8e`), loads vtable slot `+0x14` at `+0x27e9c`
(`14 00 42 8c`), and calls it at `+0x27ea0`
(`09 f8 40 00`). This supplies a precise next marker site and call chain,
without claiming that the hardware run reached it.

This is now the next candidate to trace. Static references establish that the
path exists and consumes the correct XML totals; they do not yet establish
that it executes before the observed write or that it is the final TCON
programmer.

## `0x05880FE0` is not a scan-liveness signal

Reading the LVDS page wider than the sequence touches:

```
05880040: 3fffffff 38f8f8f8 deadabba deadabba
05880050 .. 058800f0: deadabba throughout
```

`deadabba` is the interconnect's **undecoded-read signature**. The block decodes
only `0x00..0x44`; there is no status or counter register anywhere in that page,
so "read the block twice and look for a tick" cannot work — and back-to-back
reads of the decoded window are indeed byte-identical.

`0x05880FE0` is the exception: it reads `00000000`, not `deadabba`, so it is
decoded — a real register that is simply always zero. Combined with stock gating
its reset on that register being *non-zero*, the likeliest reading is a
fault/underrun status where zero means "no fault".

**So the criterion this investigation has been measured against for months is
not a signal.** Every "the FIFO never moves" result should be re-read as "we
were watching a constant". Project selection in particular was ruled out on the
basis of a dark panel, which was never a sensitive test; `0x05880024` now gives
a direct readout and that thread should be reopened.

Also recorded from these runs: the MIPS execution witness differed between two
otherwise identical runs (`0x8baa0000` vs `0x00000000`) — both count as executed,
but firmware startup is **not deterministic**. The board hangs 5-30 s after
the sequence and has now powered itself off after multiple runs, without a
preceding UART message. Linux was never started, which rules out a Linux kernel
panic but does **not** rule out a MIPS firmware panic or exception: its logging
may be buffered, incomplete, or lost when power drops. A MIPS fault, watchdog,
power-management action, or an electrical/PMIC shutdown all remain possible.
The delayed power cut is uncharacterised and is now the practical limit on
bench iteration.

### MIPS-first recovery plan

The next objective is not merely another visible-panel attempt. It is to make
the coprocessor a known-good component before attributing any remaining display
failure to scanout, LVDS, or panel control.

#### Gate 1 — a reproducible, stock-parity launch

Build one diagnostic command around a single cold-boot run. It must:

1. load and authenticate the board's `display.bin`, `display_cfg.xml`, all four
   TSE inputs, and `LogoRegData.bin`;
2. clear only the documented firmware workspaces and preserve the staged config
   and TSE windows;
3. apply the selected project 0x33 tables with the already-fixed `0xfe` pulse
   and microsecond delay semantics;
4. gate the FIFO reset on `0x05880fe0 != 0`, matching stock;
5. prepare the CPU_COMM shared region and publish its address and size before
   reset release;
6. release the MIPS exactly once and leave it running. Do not use
   `h713_mips_stop()` as cleanup; a physical power cycle remains the only known
   clean boundary after firmware execution.

The omission of stock's `0x02001020` PLL_PERIPH0 write remains intentional:
reprogramming that live clock can power the board off. It is a documented
safety exception, not an unnoticed parity difference.

Acceptance is the authenticated hash, overwritten BSS witness, CPU status 1,
both CPU_COMM magic words intact, ARM flag `0x5`, and the MIPS READY bit set.
The existing `h713_disp auto` path proves only instruction execution because it
does not publish CPU_COMM shared memory; it cannot satisfy this gate.

The Gate-1 implementation is `h713_disp mips-test 0x33`. It automatically uses
the guarded HDCP-wait override, prepares and publishes CPU_COMM, runs the full
project-0x33 display sequence, and waits up to four seconds for both MIPS READY
and application-ready. It prints the final CPU status, execution witness, both
magic words, and ARM/MIPS flags. It deliberately leaves the MIPS running on
both success and failure: power-cycle after collecting its output, and do not
run a second MIPS command on the same boot.

**First Gate-1 hardware run, 2026-07-29: execution passed; readiness failed.**
The conditional FIFO-reset status was `0x00000002`, so the reset ran, and the
post-sequence status cleared to zero. The authenticated MIPS stayed released
and overwrote its witness, while the published CPU_COMM control words remained
intact:

```
H713 MIPS: readiness status=0x00000001 witness=0x8baa0000
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000000
H713 MIPS: firmware readiness not proven; core left running
```

This is not a cache-publication or reset-release failure. It establishes the
remaining boundary precisely: the firmware did not set the CPU_COMM MIPS READY
bit during the four-second window. It does not by itself distinguish a stalled
startup task from a MIPS exception.

The first `mips-trace` build incorrectly reused the known-stale 671-word trace
table from `display.bin` revision `16c74a28...`. Its guards rejected the first
moved site before reset release:

```
H713 MIPS: trace site 0x4b1238d8 is not pristine
```

That run did not execute the MIPS and produced no readiness evidence. Reusing
that table contradicted the artifact warning above; weakening its guards would
have corrupted executable code.

The corrected nine-marker trace was accepted and the MIPS executed, but every
marker remained zero:

```
H713 MIPS: handshake trace 0 0 0 0 0 0 0 0 0
H713 MIPS: readiness status=0x00000001 witness=0x00000000
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000000
```

Marker 6 was the ThreadX application entry and marker 7 the following
CPU_COMM call. Since marker 6 never fired, CPU_COMM is downstream of the
current failure: the application thread is never scheduled. Shared-memory
publication cannot fix that boundary.

The 26-marker run narrowed the failure to one non-returning construction call:

```
H713 MIPS: handshake trace 0 0 0 0 0 0 0 0 0 10 11 12 13 14 15 0 17 18 19 20 21 22 23 24 25 0
H713 MIPS: readiness status=0x00000001 witness=0x00000000
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000000
```

Marker 25 is the call to `0x8b15340c` at raw `display.bin+0x53610`;
the exact little-endian call word is `03 4d c5 0e`. Marker 26 is the following
ThreadX thread-creation call at raw `+0x53634`, bytes `25 72 c5 0e`. Marker 16
is the later scheduler call at raw `+0x1f4c`, bytes `e4 15 c4 0e`. Thus
`0x8b15340c` was entered but did not return, application construction never
reached thread creation, and the scheduler was never entered. This is upstream
of CPU_COMM and does not yet distinguish a blocking initialization call from a
MIPS exception.

The next exact-image trace has 56 markers. Markers 1-26 remain unchanged;
markers 27-56 trace every call in `0x8b15340c`, in ascending call-site order:

```
marker  raw offset  pristine bytes  original target
27      0x053444    7c 01 c6 0e    0x8b1805f0
28      0x053454    4b 35 c4 0e    0x8b10d52c
29      0x053470    09 f8 40 00    jalr v0
30      0x053478    4b 35 c4 0e    0x8b10d52c
31      0x053494    09 f8 40 00    jalr v0
32      0x0534a4    8e 01 c6 0e    0x8b180638
33      0x0534b4    8e 01 c6 0e    0x8b180638
34      0x0534c0    2e 28 c6 0e    0x8b18a0b8
35      0x0534c8    7d 25 c6 0e    0x8b1895f4
36      0x0534d0    4b 35 c4 0e    0x8b10d52c
37      0x0534ec    09 f8 40 00    jalr v0
38      0x0534fc    1e 41 c4 0e    0x8b110478
39      0x053504    cf 4c c5 0e    0x8b15333c
40      0x05350c    a9 27 c6 0e    0x8b189ea4
41      0x053520    09 f8 40 00    jalr v0
42      0x053528    ef 9e c6 0e    0x8b1a7bbc
43      0x053530    be 61 c5 0e    0x8b1586f8
44      0x053538    1e a1 c4 0e    0x8b128478
45      0x053540    c4 79 c6 0e    0x8b19e710
46      0x053548    87 73 c5 0e    0x8b15ce1c
47      0x053550    e3 ec c5 0e    0x8b17b38c
48      0x053558    af 10 c6 0e    0x8b1842bc
49      0x053560    3b 12 c6 0e    0x8b1848ec
50      0x053568    11 f3 c5 0e    0x8b17cc44
51      0x053570    c6 78 c6 0e    0x8b19e318
52      0x053578    60 b1 c6 0e    0x8b1ac580
53      0x053580    e5 4f c5 0e    0x8b153f94
54      0x053590    df 1b c4 0e    0x8b106f7c
55      0x053598    df 1a c4 0e    0x8b106b7c
56      0x0535a0    ed 23 c4 0e    0x8b108fb4
```

The 336 guarded words match the exact `4380f1b3...` image. Each direct call
tail-jumps to its original target; the four indirect sites tail through
`jr v0`, preserving the original target and call-site return address. All 30
new call sites and five-word caves have been disassembled after applying the
patch in memory. Run this trace once after a cold boot and physically
power-cycle afterward.

The 56-marker DDR3 bench image was
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (865,817 bytes), SHA-256:

```
e03823451c391b14ff03dd96644dd726fccfd060e4911a7fe39d0fe1f4cb4a4e
```

Its hardware run reached marker 38 and no later marker:

```
H713 MIPS: handshake trace 0 0 0 0 0 0 0 0 0 10 11 12 13 14 15 0 17 18 19 20 21 22 23 24 25 0 27 28 29 30 31 32 33 34 35 36 37 38 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
H713 MIPS: readiness status=0x00000001 witness=0x00000000
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000000
```

Marker 38 is the call at raw `display.bin+0x534fc`, pristine bytes
`1e 41 c4 0e`, targeting `0x8b110478`. Marker 39 is the immediately following
call at raw `+0x53504`. Thus `0x8b110478` was entered and did not return.

This function is `tse_init`, not an unidentified scheduler primitive. Its
diagnostic arguments reference `./tse_init.cpp` at raw `+0xec008` and
`tse_init` at `+0xec84c`; its error strings include
`pTFDHandler->InitTFDMemory FAILED` at `+0xec88c` and
`TSEXX init FAILED!` at `+0xec8b0`. Its success path has only three calls:
a global enable-byte setter, the `InitTFDMemory` virtual call, and
`tse_init_data`. Two additional calls are fatal-log paths. The 61-marker trace
assigns them as follows:

```
marker  raw offset  pristine bytes  original target / meaning
57      0x0104a0    c9 27 c6 0e    0x8b189f24, enable-byte setter
58      0x0104b8    09 f8 40 00    jalr v0, InitTFDMemory
59      0x0104c8    a4 3a c4 0e    0x8b10ea90, tse_init_data
60      0x010518    52 42 c5 0e    0x8b150948, failure log
61      0x010568    52 42 c5 0e    0x8b150948, invalid-input log
```

Interpretation is branch-sensitive. Marker 57 should be followed by 58.
Marker 58 without 59 or 60 means `InitTFDMemory` did not return. Marker 59
without marker 39 means `tse_init_data` did not return. Marker 60 or 61 means
`tse_init` selected an error path; marker 39 then shows whether the logger and
function returned. All 366 guarded words match `4380f1b3...`, and the five new
trampolines have been disassembled after applying the patch in memory.

The corresponding 61-marker DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (865,817 bytes), SHA-256:

```
4577774aa219fdaac508556e74fa629aa18f918f9dd5eca97dcf96118febb6e0
```

That image's first hardware run diverged before `tse_init`:

```
H713 MIPS: handshake trace 0 0 0 0 0 0 0 0 0 10 11 12 13 14 15 0 17 18 19 20 21 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
H713 MIPS: readiness status=0x00000001 witness=0x8baa0000
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000000
```

Marker 21 is raw `display.bin+0x535f0`, bytes `d0 68 c5 0e`, calling the
firmware's optimized `memset` at `0x8b15a340`. Its address and length are the
results of the two immediately preceding configuration lookups. Their keys
are `sys:dbg_buf` and `sys:dbg_buf_size` at raw `display.bin+0xebb20` and
`+0xebb2c`; the bytes from `+0xebb20` are
`73 79 73 3a 64 62 67 5f 62 75 66 00 73 79 73 3a 64 62 67 5f 62 75 66 5f
73 69 7a 65 00`. The staged XML supplies address `0x4bd01000` at
`display_cfg.xml+0x497` and size `0x00100000` at `+0x4bc`.

This exposed a concrete ARM/MIPS coherency omission. U-Boot zeroed the config
and TSE windows, loaded their files through the ARM, but did not clean either
window after the filesystem reads. The later firmware-image flush ends at
`0x4b600000`, far below config at `0x4be01000` and TSE at `0x4be41000`.
Consequently the MIPS could observe stale or zero XML/TSE cache lines. The
lookup wrappers ignore their virtual lookup's return status and return an
output stack word unconditionally, so a failed lookup can feed an
uninitialized address or length to `memset`. This accounts for failure
movement between cold boots without assuming that each called subsystem has
an independent defect.

The next build explicitly cleans the complete 256 KiB config window and
complete 1 MiB TSE window after loading them. The 61-marker trace remains
installed. Marker 21's cave additionally records its live `a0` and `a2`
arguments, printed as `sys:dbg_buf` and `sys:dbg_buf_size`; the expected values
are the MIPS uncached alias `0xabd01000` and `0x00100000`.

The corresponding cache-publication DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (869,913 bytes), SHA-256:

```
ee4d61e8d42b76c80a63b91cc88cbf19e3177103a8ff519f9e3e4441bfde6796
```

**The cache-publication build completed the firmware startup chain on
hardware.** Markers 2-59 all fired; marker 15 arrived later in the streamed
output but was present in the final vector. The error-only markers 60-61 did
not fire:

```
0 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26
27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49
50 51 52 53 54 55 56 57 58 59 0 0
```

Marker 1 is the share-address-absent path and is correctly absent because the
published share registers were accepted at marker 2. Markers 60 and 61 are
`tse_init` error logs and are also correctly absent. The live configuration
arguments captured at marker 21 were `sys:dbg_buf=0xabd01000` and
`sys:dbg_buf_size=0x00100000`. The address is correct: it is the MIPS KSEG1
uncached alias of the XML's ARM physical `0x4bd01000`, not a corrupt lookup.
This closes the config/TSE cache-publication failure and proves reset, C
runtime, application construction, `tse_init`, scheduler entry, ThreadX
application entry, share-register discovery, and CPU_COMM entry.

The CPU_COMM flag ownership is also explicit in the exact image. The
`getCurCPUID` function at raw `display.bin+0x227b4` is only:

```
08 00 e0 03    jr    ra
01 00 02 24    addiu v0, zero, 1
```

so this MIPS firmware is CPU 1. `setCPUReady` begins at raw `+0x1a3dc`; it
indexes `pComm + 0x4cdc + cpu_id*4`, making CPU 0's flag `+0x4cdc` and CPU 1's
flag `+0x4ce0`. U-Boot's ARM/MIPS slot assignment and its wait on the second
word are therefore correct.

The remaining boundary is inside the slave-side `InitCommMem` work rather than
the flag mapping. Marker 5 fires by redirecting the call at raw `+0x1b34c`,
bytes `ed 66 c4 0e`, into the first per-CPU communication-object initializer
at `0x8b119bb4`. If that call and the identical second call return,
`InitCommMem` calls `getCurCPUID` at raw `+0x1b35c`, bytes
`ed 89 c4 0e`, and then `setCPUReady(1)` at raw `+0x1b364`, bytes
`f7 68 c4 0e`, with `move a0,v0` (`25 20 40 00`) in the delay slot. The
hardware readback remained CPU 1 flag zero, so the next trace must distinguish
an initializer stall from a later flag change rather than relabeling the two
flag words.

The next exact-image trace has 88 markers. Markers 62-85 cover every non-log
call on the success path through the first initializer at `0x8b119bb4`.
Markers 86-88 cover the second initializer, `getCurCPUID`, and
`setCPUReady(getCurCPUID())`. Its 530 guarded words all match the pristine
`4380f1b3...` image, every new five-word cave disassembles as
marker-store / tail-jump / `nop`, and no patch address is duplicated. The
corresponding DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
906184b11b2f33a22896d443472ebc00e473932119ae40d02aeb32ea987e56b4
```

That build's hardware run reached every success marker through marker 88:

```
0 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26
27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49
50 51 52 53 54 55 56 57 58 59 0 0 62 63 64 65 66 67 68 69 70 71 72
73 74 75 76 77 78 79 80 81 82 83 84 85 86 87 88
```

The live debug-buffer values remained correct at `0xabd01000` and
`0x00100000`, while the final CPU 1 flag was still zero. In that trace,
markers 62-85 covered the rest of the first object initializer, marker 86 the
second initializer, marker 87 `getCurCPUID`, and marker 88 entry to
`setCPUReady(1)`. Thus neither object initializer is the boundary:
`setCPUReady` itself was entered but did not leave a READY bit set. The old
trace does not distinguish a pre-store stall from a later flag change.

A deterministic pre-store blocker is the CPU_COMM software-spinlock table.
At raw `display.bin+0x1a56c`, `setCPUReady` calls `comm_SpinLock(3)` with:

```
f1 96 c4 0e    jal   0x8b125bc4
03 00 04 24    addiu a0, zero, 3
```

Only after that returns does it write CPU 1's flag. The first READY store is at
raw `+0x1a588`, bytes `dc 4c 43 ac`; the corresponding unlock call is at
`+0x1a5a4`, bytes `fa 96 c4 0e`. `comm_SpinLock` calls the inner lock routine
at raw `+0x25bcc`, bytes `9d 95 c4 0e`, with mode 2 in its delay slot
(`02 00 05 24`). The inner routine indexes a 12-byte record from the shared
base and waits for its byte 0 type field to equal 2. The relevant comparison at
raw `+0x25170` begins with:

```
00 00 17 92    lbu   s7, 0(s0)
02 00 02 24    addiu v0, zero, 2
```

U-Boot previously zeroed the complete CPU_COMM region and populated only its
CPU count, flags, and magic words. Therefore lock record 3 had type 0, not 2,
and `comm_SpinLock(3)` cannot complete with that input. The refined trace below
will show whether that is the observed boundary as well as removing it.

The exact master-side initialization is present in the same authenticated raw
image at `comm_InitSpinLock`, raw `display.bin+0x24d38`. Its loop derives each
entry as `shared_base + index*12`; the stores at `+0x24e30` through `+0x24e44`
are:

```
01 00 43 a0    sb    v1, 1(v0)       # status = 2
08 00 45 ac    sw    a1, 8(v0)       # thread = 0x000000ff
02 00 40 a0    sb    zero, 2(v0)     # mutex = 0
00 00 43 a0    sb    v1, 0(v0)       # type = 2
04 00 40 ac    sw    zero, 4(v0)     # refcount = 0
03 00 43 a0    sb    v1, 3(v0)       # owner = 2
```

Here `v1=2` is loaded at raw `+0x24e20` (`02 00 03 24`), `a1=0xff` at
`+0x24e24` (`ff 00 05 24`), and the loop bound 12 at `+0x24e2c`
(`0c 00 04 24`). The next build reproduces this exact 12-entry layout before
publishing CPU_COMM magic, instead of bypassing synchronization.

Its trace retains the 88-slot vector but refines the last boundary:

- marker 62: enter `setCPUReady(1)`;
- marker 63: enter `comm_SpinLock(3)`;
- marker 64: lock acquired and READY stores complete; enter unlock;
- marker 65: unlock returned; enter the final log call;
- marker 66: `setCPUReady` returned to `InitCommMem`;
- markers 67-87: retained initializer/get-CPU trace sites;
- marker 88: enter the later `setCPUAppReady` wrapper.

All 530 guarded words match the pristine `4380f1b3...` raw image, no patch
address is duplicated, and the six revised five-word caves disassemble as the
intended uncached marker store followed by a tail jump to the original target.
The next cold-boot run should set CPU 1 READY at marker 64 and may advance it to
the application-ready value after marker 88. This remains a hardware
prediction until the new build is run.

The corresponding CPU_COMM-spinlock DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
75dc804d8d963f681ac2f7be545c57c410544daeab2ee8044f9a71786e1540f3
```

**The CPU_COMM-spinlock build passed Gate 1 on hardware.** Markers 62-66 all
fired, proving entry to `setCPUReady(1)`, entry and return of
`comm_SpinLock(3)`, execution of the READY stores, return of the unlock, and
return to `InitCommMem`. The retained markers continued through marker 87.
The final control words were:

```
H713 MIPS: CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000001
H713 MIPS: firmware readiness proven by MIPS READY
```

This validates the reconstructed spinlock layout and closes the CPU_COMM READY
failure. Marker 88 was still zero in the final vector, but that sample does not
establish an application-ready failure: `h713_mips_wait_ready()` exits its poll
loop immediately when MIPS flag bit 0 appears, then prints the trace. The
marker-88 call and MIPS flag bit 2 occur later in the same application thread.

While that one MIPS instance is still running, its later state can be checked
without violating the one-launch-per-power-cycle rule:

```
md.l 0x4e304cdc 2; md.l 0x4e34015c 1
```

The first pair is the ARM and MIPS CPU flags; the second read is trace slot 87,
where marker 88 stores `0x00000058`. An eventual MIPS flag `0x00000005` and
marker slot `0x00000058` prove application-ready. These are read-only
observations, not a second MIPS launch.

The delayed read remained at MIPS flag `0x00000001` and marker-88 slot zero:

```
4e304cdc: 00000005 00000001
4e34015c: 00000000
```

READY is therefore stable, but the application thread does not reach
`setCPUAppReady`. The exact post-`InitCommMem` path in the application function
contains only five calls before the marker-88 call:

```
marker  raw offset  pristine bytes  original target
67      0x052ec8    9d 71 c5 0e    0x8b15c674
68      0x052ed0    6e 2b c4 0e    0x8b10adb8
69      0x052ed8    9d 71 c5 0e    0x8b15c674
70      0x052ee4    61 21 c5 0e    0x8b148584
71      0x052eec    32 21 c5 0e    0x8b1484c8
88      0x052ef4    2c 91 c4 0e    0x8b1244b0, setCPUAppReady wrapper
```

The second call is `hal_adapter_init`: its success log passes the name at raw
`display.bin+0xeb61c` (`68 61 6c 5f 61 64 61 70 74 65 72 5f 69 6e 69 74 00`)
and source filename at `+0xeb630`
(`2e 2f 68 61 6c 5f 61 64 61 70 74 65 72 2e 63 70 70 00`). It walks nine
groups of callback objects and repeatedly calls the helper at raw `+0x24918`.
That helper constructs a communication request and submits it at raw
`+0x2486c`, bytes `55 89 c4 0e`, to `0x8b122554`. A request that expects an
ARM-side CPU_COMM consumer is now a leading candidate, because U-Boot
publishes the shared transport and ARM-ready flags but does not service its
message queues. This is a candidate, not yet a hardware-localized conclusion.

The next trace repurposes the already-proven markers 67-87:

- markers 67-71 cover the five post-`InitCommMem` calls above;
- markers 72-80 cover each registration group in `hal_adapter_init`;
- markers 81-82 cover its final registration and return log;
- trace slots 90-92 count registration-helper entries and retain the latest
  object and callback pointers;
- markers 84-86 cover formatting, request construction, and the request call;
- marker 87 covers the final registration lock;
- marker 88 remains the application-ready wrapper.

The repeated-helper trampoline is eight instructions and increments an
uncached counter rather than merely storing a constant marker. Together, the
last outer-group marker, call count, object/callback pointers, and marker 86
will distinguish an unserviced request from a stall before or after
`hal_adapter_init`.

For this diagnostic only, `h713_mips_wait_ready()` continues streaming after
MIPS READY until either application-ready bit 2 appears or the existing
four-second display-readiness window expires. `mips-test` retains its original
READY-only exit behavior. The trace reports application readiness separately
without turning the already-proven READY result into a failure.

All 533 guarded words match the pristine `4380f1b3...` raw image, no address is
duplicated, and every replacement cave—including the eight-instruction
counter/capture cave—has been disassembled after applying the patch in memory.
The corresponding post-READY/hal-registration DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
612dad5b4d4c9ea04065dafff383807fd0fec6c56c0288b2f954cc825ec73043
```

**The post-READY trace localized the next boundary to the first registration
request.** MIPS READY remained proven (`ARM=5`, `MIPS=1`), and the post-init
markers reached `hal_adapter_init` at marker 68. Its first registration group
fired marker 72, the repeated helper count reached one, and markers 84-86
showed formatting, request construction, and entry to the request call. No
later registration group or application-ready marker fired:

```
... 62 63 64 65 66 67 68 0 0 0 72 ... 84 85 86 0 0
hal registrations=1 object=0x8b22e890 callback=0x8b109d20
CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000001
```

The marker-86 site is raw `display.bin+0x2486c`, bytes `55 89 c4 0e`,
calling the request routine at `0x8b122554`. That routine's first non-log call
is at raw `+0x225dc`, bytes `7c 71 c4 0e`, and enters
`0x8b11c5f0`. The next calls are at `+0x22614`, bytes `82 73 c4 0e`, and
`+0x22658`, bytes `8d 73 c4 0e`. Since the old trace only marked entry to the
outer request, the hardware result by itself does not distinguish those three
inner stages.

Static analysis of the exact image exposes another deterministic master-side
initialization omission before an ARM message consumer is relevant.
`0x8b11c5f0` reads the shared call-entry count at raw `+0x1c694`, bytes
`c4 75 23 8e`, and bounds it to 1224 at `+0x1c698`, bytes
`c8 04 63 28`. After taking software spinlock 2 at `+0x1c7a8`, bytes
`f1 96 c4 0e 02 00 04 24`, it tests a per-entry word against `-1`:

```
0x1c7f0: c4 75 97 8e    lw    s7, 0x75c4(s4)
0x1c7f4: ff ff 05 24    addiu a1, zero, -1
0x1c7f8: 2a 00 e5 16    bne   s7, a1, failure
0x1c800: c8 75 84 24    addiu a0, a0, 0x75c8
0x1c804: 60 00 06 24    addiu a2, zero, 0x60
```

The computed entry address begins at `shared+0x75c8`, has stride `0x60`,
and the tested word is entry offset `+0x5c`. U-Boot had zeroed every such
field, so the first insertion could not observe the required free-entry
sentinel.

The exact ARM-master initializer in the same firmware confirms the complete
layout. At raw `+0x1ae4c..+0x1ae58`, bytes
`01 00 06 3c c0 75 c4 27 08 cb c6 34 ad f4 c6 0e`, it clears
`shared+0x75c0` for `0x1cb08` bytes. It then zeroes the count and version and
constructs the sentinel loop:

```
0x1ae60: 02 00 04 3c    lui   a0, 2
0x1ae64: 24 41 84 24    addiu a0, a0, 0x4124
0x1ae68: c4 75 c0 af    sw    zero, 0x75c4(fp)
0x1ae6c: 24 76 c2 27    addiu v0, fp, 0x7624
0x1ae70: 21 20 c4 03    addu  a0, fp, a0
0x1ae74: c0 75 c0 af    sw    zero, 0x75c0(fp)
0x1ae78: ff ff 05 24    addiu a1, zero, -1
0x1ae7c: 00 00 45 ac    sw    a1, 0(v0)
0x1ae80: 60 00 42 24    addiu v0, v0, 0x60
0x1ae84: fe ff 82 54    bnel  a0, v0, 0x1ae80
0x1ae88: 00 00 45 ac    sw    a1, 0(v0)
```

The loop writes `0xffffffff` from `shared+0x7624` through
`shared+0x240c4`, exactly 1224 `+0x5c` fields. The rejected CPU_COMM Linux
patch agrees with these dimensions, but it is corroboration only; the bytes
above from authenticated `display.bin` are the source of truth.

The next build reproduces that exact call-table initialization before
publishing the magic words. It also repurposes markers 73-77:

- 73: enter the shared call-table insertion at raw `+0x225dc`;
- 76: enter its `comm_SpinLock(2)` call at raw `+0x1c7a8`;
- 77: the entry was copied and counted; enter `comm_SpinUnlock(2)` at raw
  `+0x1c838`, pristine bytes `fa 96 c4 0e`;
- 74: insertion returned; enter result lookup at raw `+0x22614`;
- 75: the result pointer was absent; enter the alternate cleanup/removal call
  at raw `+0x22658`.

Markers 78-82 retain later registration groups and the return path. All 533
guarded words match the pristine `4380f1b3...` image, no address is duplicated,
and the five replacement caves disassemble to the intended uncached marker
store and original tail call.

The corresponding call-table-initialization DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
68c8cf7e10d0dc3f275c1d5721e115a75c721feb8275972af928e43846fdf301
```

This defers the missing-ARM-consumer hypothesis. If marker 77 and then marker
74 fire, the deterministic insertion defect is closed; only a later boundary
can establish whether the request actually requires an ARM-side responder.
The trace summary also prints the live call-table version, count, and entry
zero's `+0x5c` link field.

**The call-table build passed complete application readiness on hardware.**
The first registration traversed every new inner marker: 73 entered the table
insertion, 76 entered spinlock 2, 77 proved the entry was copied and counted,
and 74 proved insertion returned into result lookup. Marker 75's alternate
cleanup/removal path also fired at least once during the complete registration
sequence, but it did not prevent progress. All retained later registration and
return markers through 82 fired, followed by marker 88 at `setCPUAppReady`:

```
... 67 68 69 70 71 72 73 74 75 76 77 78 79 80 81 82 0 84 85 86 0 88
hal registrations=82 object=0x8b22d030 callback=0x8b10ac98
call table version=164 count=82 first-next=0xffffffff
CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005
firmware readiness proven by MIPS READY
application readiness proven
```

The table accounting is exact: each successful insertion increments the
version word twice. The first sequence is raw
`display.bin+0x1c7b4/+0x1c7c4/+0x1c7cc`, bytes
`c0 75 25 8e` / `01 00 a5 24` / `c0 75 25 ae`; the second is
`+0x1c828/+0x1c830/+0x1c834`, bytes
`c0 75 22 8e` / `01 00 42 24` / `c0 75 22 ae`. Thus version 164 is
precisely twice the 82-entry count. The first entry's restored
`0xffffffff` link confirms the sentinel invariant after use. This closes the
call-table defect and disproves an ARM-side request consumer as a prerequisite
for these startup registrations.

Gate 1 first passed with the instrumented image: the authenticated firmware
executed, initialized CPU_COMM, completed all 82 HAL registrations, set MIPS
READY and application-ready, and left the ARM console responsive through the
four-second trace window.

The lower-risk confirmation also passed on hardware. Ordinary
`h713_disp mips-test 0x33` applied none of the 533 trace patches and reported:

```
CPU_COMM magic=deadbeef/deadbeef ARM=00000005 MIPS=00000005
firmware readiness proven by MIPS READY
application readiness proven
```

This run still used the separately guarded HDCP timeout-bound override, printed
as `HDCP key-load wait defeated`; "no trace patches" does not mean the loaded
image remained byte-for-byte pristine after authentication. It does prove that
the startup trampolines were not a condition of success. Gate 1 is therefore
fully passed.

The corresponding uninstrumented-application-readiness DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
4794550b6fe38a92a7738e283c49945b95ac5bb673fc0e0eab6ec51e4efbeff0
```

#### Gate 2 — distinguish a MIPS fault from a board-level power cut

The exact firmware provides a natural heartbeat. Its ThreadX tick function
loads, increments, and stores the word at MIPS `0x8b252cc0`:

```
display.bin+0x4b74: 25 8b 02 3c    lui   v0, 0x8b25
display.bin+0x4b78: c0 2c 53 8c    lw    s3, 0x2cc0(v0)
display.bin+0x4b7c: 01 00 73 26    addiu s3, s3, 1
display.bin+0x4b80: c0 2c 53 ac    sw    s3, 0x2cc0(v0)
```

The live exception vectors are also identified rather than assumed. Startup
sets EBase to `0x8b101000` at raw `+0xb11ac..+0xb11b4`, bytes
`10 8b 08 3c 00 10 08 25 01 78 88 40`. Therefore the cache-error and
general-exception vector words are raw `+0x1100`,
`79 6f c5 0a` (`j 0x8b15bde4`), and raw `+0x1180`,
`4a 6f c5 0a` (`j 0x8b15bd28`). The general handler disables interrupts at
raw `+0x5bd34`, bytes `00 60 62 41 c0 00 00 00`, calls the register saver at
`+0x5bd3c`, bytes `f6 6e c5 0e`, and ultimately loops forever at
`+0x5bddc`, bytes `ff ff 00 10 00 00 00 00`. The saver itself reads CP0
`Status`, `Cause`, `EPC`, and `BadVAddr` at raw
`+0x5bc54/+0x5bc5c/+0x5bc64/+0x5bc6c`, bytes respectively
`00 60 1b 40`, `00 68 1b 40`, `00 70 1b 40`, and `00 40 1b 40`.

`h713_disp mips-stability 0x33` now installs 34 guarded words after the
SHA-256 identity check. The tick instruction at raw `+0x4b7c` is redirected to
the zero cave at raw `+0x300`, whose bytes are:

```
01 00 73 26 34 ae 1a 3c 00 10 53 af e1 12 c4 0a c0 2c 53 ac
```

That cave performs the displaced increment, writes the new tick through the
uncached MIPS alias `0xae341000` (ARM `0x4e341000`), preserves the original
tick store, and resumes at raw `+0x4b84`.

The general and cache vector words are redirected from
`4a 6f c5 0a` / `79 6f c5 0a` to `c8 00 c4 0a` / `d8 00 c4 0a`,
respectively. Their zero caves at raw `+0x320` and `+0x360` save CP0 state to
the same uncached record, store exception type 1 or 2 last, then jump to the
original fatal handler. The cache path records CP0 `ErrorEPC` in the EPC field.
No normal interrupt vector is changed.

After both CPU_COMM ready bits appear, U-Boot samples the heartbeat, exception
record, core status, and MIPS flags once per second for 60 seconds. It does not
arm or pet a watchdog. If an exception appears, it immediately prints
`Status`, `Cause`, `EPC`/`ErrorEPC`, and `BadVAddr`. If the heartbeat stops
while the ARM remains responsive, it reports a MIPS stall. If the board loses
power while the last UART samples still show an advancing heartbeat and no
exception, the next evidence must come from reset-cause/PMIC/electrical
investigation rather than calling the silence a MIPS panic.

Acceptance is no exception marker, a continuing heartbeat, a responsive U-Boot
console, and no uncommanded shutdown for 60 seconds on three cold boots.

The corresponding Gate-2 DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
b097cbe2bd314003bf6991396253ac22f11f779b7d3809e680a2e7037f4ad51c
```

**The first Gate-2 stability run passed on hardware.** Starting at tick 210,
all 60 one-second samples advanced by 1005--1008 ticks. CPU status stayed one,
the MIPS CPU_COMM flags stayed `0x00000005`, and the exception type stayed
zero. The final tick was 60665, U-Boot remained responsive, and the board did
not shut down during the window. Two more cold-boot passes remain before the
three-run acceptance criterion is complete, but this run establishes that a
running, application-ready MIPS is not inherently causing the earlier
uncommanded shutdown.

#### Gate 3 — identify the live timing path

Only after Gate 1 works, add two one-shot probes to the same diagnostic run:

1. mark entry to `load_panel_timing` at raw `display.bin+0x2a6ec`
   (`98 ff bd 27`), reached through the `CrtcDb` call at `+0x27ea0`;
2. trace stores that target TCON `0x05880020` and `0x05880024`, recording the
   value and caller/return address before allowing the original store.

The entry marker answers whether the XML-aware loader is live. The write trace
answers which later function wins. Patching the dead `_LoadTFDPanelTiming`
selector again cannot answer either question.

Once the final writer is known, correct its input structure or database
selection rather than overwriting the registers after the fact. The expected
panel result is:

```
0x05880020 = 02f80550    1360x760 total
0x05880024 = 02d00500    1280x720 active
```

The mixer/DE value `0x02e4059f` remains an internal 1440x741 processing size,
not the target TCON total.

#### Gate 4 — return to the physical panel

With MIPS READY, no exception/shutdown, and stable 720p TCON timing, test the
physical output:

1. assert board-B PF6 and verify the panel VDD rail at the connector;
2. with PF6 and PH16 correct, use the internal TCON color source after latching
   the 720p timing;
3. compare the recovery and stock LVDS lane/mapping, single-port, DCLK
   polarity, color-depth, drive-current, and PHY registers;
4. trace and validate the post-INI PWM5 route while leaving PB5 asserted;
5. only if those are correct, seek evidence for any PH10/PH11/PH12/PH15
   panel-side transaction before attempting to replay it.

This orders the work so a dark panel cannot be used as the sole verdict on
MIPS, scanout, signaling, and illumination at the same time. Re-checking the
other three `0xfe` timing-table sites can wait until the project-0x33 MIPS path
passes these gates.

The live project-0x33 dump now identifies the scanout buffer without probing
the PCB. Its selected DE block 5 contains these exact `LogoRegData.bin`
records:

```
file offset  bytes                                      meaning
0x32e4       50 01 60 05 ff 04 cf 02 ff ff ff ff 04... AFBD+0x10 = 02cf04ff
0x3344       70 01 60 05 00 14 00 00 ff ff ff ff 04... AFBD+0x30 = 00001400
0x3354       74 01 60 05 00 14 d0 02 ff ff ff ff 04... AFBD+0x34 = 02d01400
0x3364       78 01 60 05 00 00 10 6c ff ff ff ff 04... AFBD+0x38 = 6c100000
```

The corresponding live reads were `AFBD+0x10=0x02cf04ff`,
`AFBD+0x30=0x00001400`, `AFBD+0x34=0x02d01400`, and
`AFBD+0x38=0x6c100000`. Thus the selected OSD is 1280x720, four bytes per
pixel, stride `0x1400`, at ARM physical `0x6c100000`; the complete buffer is
`0x384000` bytes. Manual writes to its first and last bands read back
correctly, but that run was not watched at the panel and did not flush the ARM
data cache, so it is not a visible-scanout result.

The stock U-Boot image also contains its `bootlogo.bmp` lookup text at raw
offset `0x60e5c`, bytes
`62 6f 6f 74 6c 6f 67 6f 2e 62 6d 70`. Our fast-logo replay applies the
register records but does not load logo pixels. A new
`h713_disp panel-test 0x33` closes that gap deterministically: it fills and
flushes a moving ARGB8888 color-bar pattern at `0x6c100000`, completes the
authenticated MIPS/CPU_COMM launch, animates for five seconds with the
firmware-selected timing, then writes and latches project 0x33 timing block
6's 1360x760-total/1280x720-active values and animates for another 15 seconds.
That first image intentionally did not change panel GPIOs or PWM, so its
scanout/timing result remained separate from panel power and backlight.

The corresponding pixel/timing-only panel-test DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
8aafab3f830aa58890c0ee42d1099837244f213625332ef41a3371532c07b36a
```

**The first panel-test hardware run produced no visible change in either
phase.** It nevertheless completed MIPS READY and application-ready
(`ARM=5`, `MIPS=5`), published and cache-cleaned all 21 moving patterns, and
read back the requested phase-2 TCON values:

```
00000004 02f80550 02d00500 00140028 80000014 80010003
```

Missing framebuffer contents and the 1080p-versus-720p TCON mismatch are
therefore not sufficient explanations for the dark panel. This does **not**
prove that AFBD fetched the buffer or that LVDS pins carried the changing
pixels; neither has a software liveness counter.

### Stock panel-power sequence recovered

**Board correction, 2026-07-30:** the earlier analysis in this section mixed
the board-B MIPS artifacts with the older board-A TOC1 DT. The board-B runtime
TOC1 DT is a separate item in the eMMC dump at TOC1 offset `0x11b400`,
SHA-256 `3902567a079720921e226c9176877f49916c6bdabfb6d82885e65d9f0a7d58b0`.
(An earlier revision of this document recorded `06e5279c...` here; that hash is
wrong. All three board-B eMMC captures yield the value above at that exact
offset and size, and both byte-level facts quoted below — `panel_power_en` at
DTB `+0x9f64` and `panel_gpio_0` at `+0x9f9c` — match it.)
It lists **PF6**, not PH19, as `panel_power_en`; `panel_gpio_0` remains PH16.
Both are active-high with pull-down flags (`0x20` is `GPIO_PULL_DOWN`;
polarity bit zero is `GPIO_ACTIVE_HIGH`):

```
panel_power_en = <0x2c 0x05 0x06 0x20>;
panel_gpio_0   = <0x2c 0x07 0x10 0x20>;
```

The exact board-B DTB property records begin at DTB offset `0x9f58`. The
`panel_power_en` value is at `+0x9f64`, bytes
`00 00 00 2c 00 00 00 05 00 00 00 06 00 00 00 20`; the
`panel_gpio_0` value is at `+0x9f9c`, bytes
`00 00 00 2c 00 00 00 07 00 00 00 10 00 00 00 20`.
In the complete eMMC dump those values are at `0x0d25364` and `0x0d2539c`.

The matching compiled property references are present in the board-B stock
U-Boot `22c9afa98503d4ce0b2b929cf8109af034d841560fbd11baf4ad851197134440`.
`panel_power_en\0` begins at raw `+0x6200b`, bytes
`70 61 6e 65 6c 5f 70 6f 77 65 72 5f 65 6e 00`, and its
little-endian pointer appears at raw `+0x23be0`, bytes `0b 20 06 4a`.
The `panel_gpio_%d` format begins at raw `+0x62038` and its pointer appears at
raw `+0x23c60`, bytes `38 20 06 4a`.

The fastlogo state dispatch is a Thumb `tbb` at raw `+0x22886`, bytes
`df e8 02 f0`; its five-entry table at `+0x2288a` is
`1b 03 0b 0f 0f`. State 0 applies every LogoRegData group and loads the delay
at configuration offset `+0x88` at raw `+0x22902`, bytes
`02 9b d3 f8 88 30 c8 e7`. The extracted DT supplies that
`panel_poweron_delay1` as `0x226`, or 550 ms. State 1 calls the object's
panel-power method with argument one at raw `+0x22890`, bytes
`43 69 01 21 98 47`, then loads configuration offset `+0x84` at
`+0x22896`, bytes `02 9b d3 f8 84 30 07 93`; the DT supplies
`panel_poweron_delay0=0x14`, or 20 ms.

The power method itself begins at raw `+0x224e4`, bytes
`2d e9 f0 45`. For power-on it:

1. applies the `panel_power_en` descriptor from object offset `+0x48`;
2. walks the four possible `panel_gpio_N` descriptors from object
   `+0x4c..+0x58`, forces each present pin low, and waits 2 ms — the loop
   starts at raw `+0x22528`, bytes
   `a0 46 4f f0 00 0a 58 f8 04 1b`;
3. walks the same descriptors using their configured active value and waits
   5 ms — the second loop starts at raw `+0x22554`, bytes
   `54 f8 04 1b a9 b1 38 22`.

Only `panel_gpio_0` is present in the runtime TOC1 DT. Thus the reconstructed
sequence must drive PF6 high, drive PH16 low for 2 ms then high, wait 5 ms,
then wait 20 ms before the
display-clock/MIPS phase.

The raw literal pair at `+0x22c60` is
`50 01 00 02 22 ff ff 22`, encoding
`0x02000150 <- 0x22ffff22`. The earlier interpretation that this disabled
PH16 and PH19 was wrong. H713 banks are 0x30 bytes apart, making
`0x02000150` **PH_CFG0 for PH0..PH7**; PH16 and PH19 are in PH_CFG2 at
`0x02000158`. The write configures PH0/PH1 and PH6/PH7 as function 2 and
disables PH2..PH5. It does not touch either panel GPIO.

Stock U-Boot's compiled fastlogo code parses `panel_power_en`,
`panel_gpio_%d`, `panel_bl_en`, and the PWM properties. The strings
`lcd_standby`, `spi_cs`, `spi_scl`, and `spi_sda` occur in the extracted stock
DT but have no compiled property-name occurrence in the U-Boot code. Treat the
old claim that stock fastlogo bit-bangs PH10/PH11/PH12 as an unproven
hypothesis, not an established panel-initialization step.

The first stock-panel-power build used PH19 and is now rejected as a
cross-board test. Its brief panel response remains an observation, but it
cannot validate the board-B power rail. That build,
SHA-256 `3cf25e3df12d259bc2a100401db95a983f4a6711326096fa3fd70b05cce97875`,
produced the first physical panel response seen in this investigation: a very
brief flash that looked as though the LCD stopped obscuring the illuminated
backlight. Its exact point in the sequence was not observed. The serial
diagnostic also proved that this was **not yet the intended reset release**:

```
stock GPIO phase complete: PH19 cfg=1 latch=1, PH16 cfg=1 latch=0
post-stock PH mux:          PH19 cfg=1 latch=1, PH16 cfg=1 latch=0
```

The board-A PH19 pin was asserted, while PH16 remained actively driven low for the
rest of the run. The cause is the legacy GPIO compatibility API in this
DM_GPIO build. `gpio_direction_output()` constructs a temporary descriptor
with output flags, but the later `gpio_set_value()` constructs a new descriptor
without those retained flags. The sunxi driver implements `.set_flags` rather
than `.set_value`, so that later high request does not enter its output path.
The PH16 low-to-high pulse was therefore lost in software, exactly as the data
latch reported.

The first corrected `h713_disp panel-test 0x33` still used the wrong board-A
power pin: it wrote PH19 through `0x02000160`. The board-B correction instead
sets PF6 through PF data register `0x02000100`, then pulses PH16 through
`0x02000160`. It still leaves PB5 high because this U-Boot enables the shared
fan/backlight rail in `board_init`, and dropping it for sequence parity would
defeat the cooling interlock.

The corresponding corrected stock-panel-power DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
c4a7ca24b83ce782f05e5547e7a38db2fdb4494cd617afac58f41b6de6a95dbb
```

The corrected-GPIO hardware run proved the requested state survived the whole
sequence:

```
stock GPIO phase complete: PH19 cfg=1 latch=1, PH16 cfg=1 latch=1,
                           PH_DAT=00090000
post-stock PH mux:          PH19 cfg=1 latch=1, PH16 cfg=1 latch=1
CPU_COMM:                   ARM=00000005 MIPS=00000005
```

There was no visible change in either pattern/timing phase. This result says
nothing about panel power because PH19 is not the board-B power pin. The
earlier flash occurred only in the defective build that left PH16 low; treat
it as a power/reset transient, not as proof of valid pixels.

### Firmware hardware-blue-screen discriminator

Static analysis closes the remaining framebuffer-format question. The stock
U-Boot BMP blitter at raw `u-boot_real2.bin+0x24014`, bytes
`96 78 03 32 12 f8 03 3c 43 f0 7f 43 43 ea 06 43`
followed by
`12 f8 02 6c 43 ea 06 23 41 f8 04 3b`, reads three source bytes,
sets the high byte to `0xff`, and stores one 32-bit destination pixel. Thus
the stock 24-bit BMP path produces the same `0xffRRGGBB`-class words used by
`panel-test`; an unexpected compressed framebuffer format does not explain
the negative result.

Stock U-Boot also does not perform a hidden hardware commit when it supplies
the framebuffer. Its method at raw `+0x2481c`, beginning
`f0 b5 0e 46 85 b0 15 46`, enumerates the parsed 16-byte register records,
compares each address against the first address plus `0x178`, and stores the
surface pointer into that record's value field (`45 60` at raw `+0x24868`).
For DE block 5 that is the already identified `0x05600178` record whose file
bytes contain `00 00 10 6c`. The ordinary LogoRegData replay is the operation
that later writes it to hardware.

The MIPS firmware contains a better probe-free split. Its
`EnableHWBlueScreenPanel` implementation begins at raw `display.bin+0x16600`.
At `+0x16610..+0x1664c`, bytes
`1c ba 02 3c b8 00 43 8c ... 84 31 a3 7c ...`
and
`04 10 83 7c ... c4 28 83 7c`, it read-modify-writes MIPS panel register
`0xba1c00b8`, setting bit 6 and both three-bit fields to seven. Under the
firmware's MMIO mapping this is ARM `0x051c00b8`. Its color setter at raw
`+0x17a68` begins
`d8 ff bd 27 1c ba 02 3c` and packs three 10-bit components into
`0xba1c00b0` and `0xba1c00b4` (ARM `0x051c00b0/+0xb4`).

`panel-test` reproduces those exact hardware-blue-screen writes only after MIPS
application readiness. It cycles four internal colors for three seconds each
and restores all three saved registers exactly. Once the TCON is at the
panel's 720p timing, this removes AFBD, DE, the framebuffer address, cache
coherency, and pixel format from the test:

- visible hardware colors mean LVDS and the physical panel path work, leaving
  the OSD/DE path as the fault;
- no hardware colors **at the panel timing** put the fault downstream of DE,
  in panel/LVDS signaling or panel initialization/power.

The corresponding DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
0b0e2374738c7f9d7259b8e4bebca75941be77043498e3bca4e26f3cbcc9816a
```

**The first hardware-blue-screen run accepted every register write but
produced no visible change.** The baseline and four readbacks were:

```
blue-screen baseline: 00000200 00000000 00000038
hardware colour 1/4:  3ff00000 3ff00000 0000007f
hardware colour 2/4:  000003ff 000003ff 0000007f
hardware colour 3/4:  000ffc00 000ffc00 0000007f
hardware colour 4/4:  3fffffff 3fffffff 0000007f
restored:             00000200 00000000 00000038
```

MIPS READY and application-ready were both still proven. The test then latched
`02f80550 02d00500` and ran the moving framebuffer for 15 seconds, also
without a visible response.

That run does **not** yet prove the failure is downstream of DE. The internal
color phase preceded the 720p latch and therefore ran while the firmware's
1920x1080-active timing was still selected. A 1280x720 panel is not expected to
display that signal. The next build moves the internal colors after the
1360x760-total/1280x720-active latch before using their visibility as an LVDS
discriminator.

The same run added a panel-power/readiness phase while internal white was
selected. It left PB5—the shared fan/backlight enable—asserted throughout,
but it still used the board-A PH19 assignment:

1. drives PB4, the stock `panel_pwm_ch=2` input, statically low and high for
   three seconds each (the unambiguous PWM duty extremes);
2. holds PH16 reset/enable low for three seconds, then high for three seconds;
3. asserts PH16 low, toggles PH19 for three seconds, restores it, and replays
   the stock 2 ms PH16 release.

Each step printed the PB4/PB5/PH16/PH19 mux and data-latch readback. The PF6
correction above invalidates PH19 as a panel-power discriminator.

The corresponding 720p/power-control DDR3 bench image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (878,105 bytes), SHA-256:

```
8fa2c6e7c037f746388b04b0426be0359c01ce239a29ede72571698b0a388364
```

**The 720p/board-A-power-control run produced no visible response in any
phase.**
MIPS reached READY and application-ready, the TCON read back
`02f80550 02d00500`, and the internal-color registers read back each requested
value. PB4 then read back low and high, PH16 read back low and high, and PH19
read back low for three seconds before the stock power/reset release restored
both PH19 and PH16 high. PB5 remained configured as an asserted output
throughout. The operator saw no color, brightness, flash, opacity, or other
output change.

This moves the pixel-source boundary downstream of AFBD/DE, but it does not
move the panel-power boundary: PH19 is not the board-B `panel_power_en`.
The next useful evidence is the corrected PF6 run:

1. assert PF6 and measure the panel's DC supply at the connector;
2. if the supply falls and returns, check one LVDS clock pair for continuous
   differential activity during the 720p internal-color phase;
3. only if both power and clock are present should the investigation move to
   lane mapping/polarity, panel initialization, or connector pinout.

No additional framebuffer pattern can distinguish those cases.

**A Saleae Logic Pro 8 analog capture now proves that at least one physical
LVDS pair is active.** Channels 0 and 1 were clipped to the suspected pair,
with a shared board ground, during `h713_disp panel-test 0x33`. The retained
15.509 seconds cover the final moving-OSD phase after the 720p timing latch.
Across 48,468 exported samples:

```
channel 0 mean = 1.1831 V
channel 1 mean = 1.2765 V
pair common-mode mean = 1.2298 V
channel correlation = -0.7864
```

Both conductors moved throughout every one-second pattern interval and were
strongly complementary. That is an electrically driven LVDS pair, not two
inactive GPIOs. Its nearly invariant per-second distribution is consistent
with the operator's identification as the clock pair, but the capture cannot
prove that classification: the Logic Pro 8 analog front end is only 5 MHz,
and its available single-ended digital thresholds do not sit at the pair's
approximately 1.23 V common-mode. A high-speed digital capture consequently
reported both conductors low and is discarded for waveform/frequency analysis.

The third Saleae channel in this run was attached to the wrong connector pin
and remained near zero; it is explicitly **not** panel-power evidence. The
native capture is preserved locally at
`local/mips-display/h713-lvds-ch0-ch1-active-20260730.sal`.

A second, lower-rate capture retained the complete 73.186-second cold-boot
run. Channels 0 and 1 rose from approximately zero to an active differential
state at 8.1 seconds and remained driven through the prompt. At 43.83 seconds
their sampled distribution changed sharply from one stable differential state
to complementary motion around 1.23 V common-mode, proving that a later test
phase changes the pair electrically. Without a simultaneous UART/GPIO marker,
this capture does not assign that transition to a specific printed phase.

The repositioned third channel began near 0.64 V and slowly rose to
approximately 1.06 V; it never behaved as a switched 3.3 V supply and did not
drop during the run. It is therefore still an unidentified connector signal,
not panel-VDD evidence. This full capture is preserved locally as
`local/mips-display/h713-lvds-full-run-ch2-unknown-20260730.sal`.

This result rules out a globally silent LVDS PHY and cable-side absence of all
lane drive. The next discriminator is the corrected PF6 panel-power run,
followed by the panel-side PH16/reset level. If both controls respond correctly,
attention moves to lane/clock identification, mapping/polarity, and any
panel-specific initialization rather than AFBD/DE.

### Board-B `panel_config.ini` is another stock input

The board-B eMMC dump also contains the file that its stock U-Boot explicitly
tries to load. `Reserve0_a` starts at eMMC byte `0xa7880000` and is FAT16.
Its `/panel_config.ini` is 2513 bytes, SHA-256
`7bffff88a8319c3cdd1a2cdba0fc26df9fdac16c01aedaea7cc20353bc618cc3`.
The corresponding stock U-Boot strings are at raw offsets `0x61e7a..0x61f47`:
`load file %s fail, try load panel_config.ini!`, `panel_config.ini`,
`/oem`, `Reserve0`, and `load file panel_config.ini fail!`.

This file does not override the panel GPIO names, so it does not weaken the
PF6 conclusion. It does override several display settings after the DT is
parsed:

```
PanelDualPort = 0
Mapping = 0
ColorDepth = 8
PanelInvDCLK = 1
PanelHTotal = 1360
PanelVTotal = 760
PanelDCLK = 62000000
pwm_channel = 5
pwm_polarity = 1
pwm_freq = 40000
```

The existing TCON table and the manually latched phase already reproduce the
1360x760 timing. The single-port setting and PWM5 route have not yet been
traced to their final hardware writes. They are the next stock-parity items
after proving that PF6 restores the panel rail; PB4/PWM2 testing came from the
pre-override DT and is not authoritative for board B.

The corrected recovery path now drives board-B PF6 instead of board-A PH19,
and the panel control diagnostic no longer presents PB4 as an authoritative
brightness test. The corresponding DDR3 image is
`build/out/u-boot-sunxi-with-spl-ddr3.bin` (874,009 bytes), SHA-256:

```
4153a1983377eaa2e2edac85982df5aee19eae887b5405506ce2257cf30e88c1
```

### Where the display stands, for a cold start

Hardware is an **LCD panel** (`HY200-1-3-W`, 1280x720) over LVDS. It is known
to work: the stock firmware displays a logo.

Everything needed is on the board and loaded automatically:

```
h713_disp mips-test 0x33       # full launch plus CPU_COMM/app-ready proof
h713_disp mips-trace 0x33      # same launch, streaming startup markers
h713_disp mips-stability 0x33  # same launch, 60s heartbeat/exception test
h713_disp panel-test 0x33      # 720p colors, power controls, then moving OSD
h713_disp auto 0x33            # load from eMMC, run the full sequence
h713_disp test 0x33            # same, plus config patches, timed sampling, log
h713_disp list 0x4e000000      # project -> prologue/timing/DE table
h713_mips log                  # scan the firmware workspace for its own text
```

Verified: artifacts load from `mmc 1:2`, `display.bin` verifies against
`4380f1b3...`, the coprocessor executes (witness overwritten), the replay
follows stock's group order and is now faithful record-for-record, the display
PLL locks, and 54 of 65 dumped registers hold exactly what the tables wrote.
Every "not working" result recorded before 2026-07-29 predates the `0xfe` and
delay-unit fixes, so the replay that produced them was not faithful.

Not working: the panel stays dark. **Do not use `0x05880FE0` as the criterion** —
it is decoded, reads `0x00000002` before the conditional reset and zero after,
and is most likely a fault status where zero means "no fault"; see the section
above.

**Correction (2026-07-31): there is a scan-liveness signal, and it is
`0x05880000`.** Its two halves advance continuously while the raster runs and
read `0x00000000` when it does not, which is exactly the instrument this
investigation lacked for months. Use it, not `0x05880FE0`. The earlier claim
that the block "only decodes `0x00..0x44`" stands for the *upper* page; it does
not mean the decoded window is static.

Ruled out: table selection (`0x16`, `0x33`, `0x34`, `0x35` all tried, with and
without the HDCP override), `source_id` (2 is invalid — the board's own
`display_cfg.xml` already carries 1, and forcing 2 makes the firmware log
`Element name=source_` and get *less* far), and the HDCP key-load wait.

**Each of those was judged on "the panel stayed dark", which was never a
sensitive test.** Table selection especially deserves re-testing, now that
`0x05880024` gives a direct readout of what timing the firmware settles on.

At ERROR level the firmware logs nothing, so by its own account
startup succeeds. Its elog `route='0'` means uart, so raising the level does
not put anything in memory; capturing it properly needs the elog buffer
addresses re-derived for `4380f1b3...`.

## Safety rules

- Keep a known-good FIT available and preserve UART as the recovery path.
- Do not enable `cpu-comm`, `tvtop`, `decd`, or GE2D in the recovery image.
- Do not map or access the MIPS control registers from Linux until their clock
  and power-domain behavior is independently understood.
- Do not mix unrelated GPU, filesystem, WiFi, or DVFS changes into display
  experiments.
- Treat `display.bin` and vendor image extracts as local-only research inputs.
  Record their hashes, but do not embed workstation-specific paths in defconfig.
- Every patch-series edit must pass a fresh `build/build.sh kernel`; cached or
  previously published artifacts are not proof of the current tree.
- A driver must return an error when its hardware does not become ready. Probe
  success and log messages must not conceal a failed reset/clock/firmware step.

## Milestone 0 — preserve evidence and restore a buildable series

Actions:

1. Keep the experimental GE2D patch and reverse-engineering inputs out of the
   active series while they are reviewed.
2. Repair all malformed or stale new-file hunk counts.
3. Remove the absolute `CONFIG_EXTRA_FIRMWARE_DIR` and rootfs dependency on
   `tmp/`.
4. Restore the bench overlay to its known boot-safe state: reserve the firmware
   DRAM, but expose no MIPS control device to Linux.
5. Revert unrelated GPU IRQ and ext4 `norecovery` changes.

Acceptance:

- `build/build.sh kernel` applies every patch from a clean extraction.
- `Image`, both board DTBs, modules, and the bench FIT are published.
- The bench DTB has no enabled MIPS/display device and contains only the
  no-map firmware DRAM reservation.
- No MIPS/display firmware is compiled into the recovery kernel.

## Milestone 1 — verify the recovery kernel on the bench

Boot the Milestone 0 FIT over the existing safe path before writing it to eMMC.

Acceptance on UART:

- U-Boot hands off to Linux and Debian reaches the normal login target.
- Root ext4 mounts normally, without `norecovery`.
- Fan, UART, eMMC, RTC/reboot-mode, and the existing WiFi fixes show no
  regression.
- Save the complete UART log and FIT SHA-256 as the new display-recovery
  baseline.

## Milestone 2 — U-Boot firmware loader

Keep the operation in U-Boot proper while it needs filesystem access and
SHA-256. Do not place the proprietary firmware in SPL or the U-Boot image.
Keep the command manual until firmware readiness has a bounded independent
witness.

Required behavior:

- hold MIPS reset before modifying its DRAM window;
- accept only the known size and SHA-256 of `display.bin`;
- clear the complete factory five-megabyte load window before copying;
- flush ARM caches before releasing the external processor;
- use the recovered physical boot address and staged reset sequence;
- prepare only the proven display clocks, TVTOP routing, and mixer register;
- exclude LVDS, PH pinmux, TVCAP, HDMI, and INCAP;
- return to reset after a bad hash, short read, or unexpected CPU status;
- print reset status separately from firmware readiness.

Acceptance:

- The command is present only in the DDR3 bench U-Boot proper image and absent
  from SPL and the projector defconfig. **Passed on 2026-07-27.**
- A rejected or missing firmware image leaves CPU status zero. **Passed on
  2026-07-27.**
- The known image produces the expected hash and reset transition without
  disrupting UART, USB ACM, or eMMC. **Passed on 2026-07-27.**
- A second observable witness, such as a firmware-owned memory word or bounded
  IPC acknowledgement, proves instruction execution before autoboot is added.
  **Passed on 2026-07-27:** the cache-coherent BSS-clear witness passed on three
  pristine firmware loads.
- The complete recovery kernel reaches userspace with the MIPS running.
  **Passed on 2026-07-27:** the installed minimal display preparation makes the
  live-MIPS handoff safe with Panfrost enabled; DRM and the render node register
  and Debian reports `running` with zero failed units.
- A bounded firmware mailbox/IPC acknowledgement proves higher-level readiness
  before autoboot or Linux clients are added. **Pending.**

## Milestone 2b — Linux post-boot ownership

Enable only the no-map MIPS firmware reservation. Do not instantiate a Linux
MIPS loader, observer, or management driver. Keep CPU_COMM, TVTOP, DECD, GE2D,
and their extra framebuffers disabled.

Acceptance:

- Linux reaches userspace when U-Boot has not started the MIPS. **Passed on
  2026-07-27.**
- Linux reaches userspace with MIPS running and Panfrost transiently
  blacklisted. **Passed on 2026-07-27; diagnostic configuration only.**
- Linux reaches userspace with MIPS running and Panfrost enabled after U-Boot
  applies the minimal display prerequisites. **Passed on 2026-07-27; installed
  U-Boot and unmodified kernel command line.**
- Linux never loads `display.bin`, rewrites the boot vector, or toggles the
  MIPS reset sequence.
- The compiled DT contains no MIPS control-register address and Linux creates
  no MIPS platform or character device. **Passed on 2026-07-27.**
- `dmesg` reports only the no-map firmware reservation, not a MIPS probe.
  **Passed on 2026-07-27.**

## Milestone 3 — CPU_COMM address model

Do not enable CPU_COMM until its address domains are explicit:

- native kernel virtual addresses use `uintptr_t`/pointers and are never stored
  in protocol `u32` fields;
- shared-memory protocol fields contain 32-bit MIPS-visible physical addresses
  or offsets, converted through checked helpers;
- no helper reconstructs a pointer by OR-ing a fixed arm64 VA prefix;
- kernel-only lists use native `struct list_head` or native-width storage;
- shared structures retain the vendor ABI with compile-time layout assertions.

Add host-side KUnit or equivalent tests for FIFO wrap/full/empty behavior,
physical↔virtual conversion bounds, list insertion/removal, and malformed
shared-memory values.

Acceptance:

- The CPU_COMM objects build without pointer-to-int or int-to-pointer warnings.
- The platform driver is present in the linked image and probes exactly once.
- Invalid shared pointers return errors rather than reaching `BUG()`.
- With MIPS running, ARM and MIPS exchange a bounded ping/ack before any
  synchronous display RPC is attempted.

## Milestone 4 — TVTOP and DECD

Enable TVTOP first, then DECD. Keep GE2D disabled. Define resource ownership so
shared display clocks, resets, IRQs, and overlapping register windows have one
clear owner. Child population must propagate errors and be paired with
depopulation.

Acceptance:

- Both drivers can defer and reprobe without leaked PM, IRQ, clock, reset, or
  character-device state.
- No IRQ is requested non-shared by two active devices.
- CPU_COMM ping/ack remains reliable while TVTOP and DECD probe.

## Milestone 5 — GE2D and visible panel path

Review the GE2D patch as a separate feature series. Probe must not issue
synchronous MIPS RPC until CPU_COMM reports ready, and every RPC result must be
checked. Start with framebuffer/IRQ/backlight side effects disabled, then enable
one at a time.

Acceptance:

- GE2D can probe without changing fan/backlight GPIO state unexpectedly.
- Panel initialization, PWM configuration, and framebuffer scanout are separate
  observable steps.
- The LVDS path produces a stable test pattern before compositor or GPU
  integration begins.

## Artifact organization

After Milestone 0 builds:

- discard one-off top-level `fix_*.py`, `patch_editor.py`, `wait.sh`, and saved
  build stdout/stderr;
- move useful vendor extracts, firmware, disassembly, and analysis scripts under
  ignored `local/mips-display/`;
- keep the inactive GE2D patch in a clearly named local research location until
  it passes review and has reproducible provenance.

Nothing under `local/` is published or force-added to Git.
