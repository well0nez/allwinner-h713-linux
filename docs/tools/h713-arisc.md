# h713-arisc

Which firmware runs on the ARISC, the SoC's power-management coprocessor: the vendor's, which an image runs,
or crust, ours, as an experiment - without a reinstall. On the device, as root.

```
h713-arisc status              # which runs now, where that choice came from, what it means
h713-arisc set crust           # crust, built with the image, from the next boot on (experimental)
h713-arisc set vendor          # the vendor firmware from your dump again, from the next boot on
```

**The choice.** An image runs the vendor's firmware (`h713-arisc.bin`, which `h713-install` puts into every
image from your own dump): it carries `/etc/modprobe.d/h713-arisc.conf` with `options sun50i_h713_arisc
firmware=vendor`, and the driver loads that file instead of the crust image the device tree names (kernel
patch `0267`). With it there is no standby, and a power-off ends in the [power-on gate](../uboot/power-gate.md),
2.9 W, where the key on the projector, not the remote, starts the next boot. The owner decided so on 22.10.2026, for the HY310 and the
HY300PRO-G-EU alike: with crust the power supply hums or whines - in standby (2.0 W) and when off through crust
(0.3 W) - and a night of measurements with a microphone at the supply found no crust change that is quiet at
the same power; in the gate it is silent (TODO 2.42, and the whine in standby already noted in `doku/181`).

crust stays in the image, as an experiment ([arisc](../subsystems/arisc.md)): `set crust` writes
`firmware=crust`, and from the next boot on the driver loads `<board>-crust.bin` from `/lib/firmware`. Then a
power-off switches the board's rails off (0.3 W, the key or the remote wakes into a fresh boot), and on an image
built with the standby (`release/build-all.sh --standby`, [standby](../subsystems/standby.md)) the countdown of
[h713-power](h713-power.md) offers it. An image built with the standby runs crust from the start: BL31 starts it
from the FIT, and it carries no `h713-arisc.conf`. On an image without it the boot chain starts no crust, so a
mains-on waits in the gate whichever firmware is chosen; only a power-off from Linux goes through crust.
`set vendor` goes back.

*Superseded (22.10.2026):* "crust is the default on every board with a measured crust configuration (the HY310,
the HY300PRO-G-EU) - only with it the standby and the 0.3 W power-off exist. [...] `set vendor` writes
`/etc/modprobe.d/h713-arisc.conf` [...] (with crust started by TF-A, the driver replaces it, patch `0192`)."

**Without `h713-arisc.bin`** nothing hangs. `h713-install` stops before it writes anything when the dump lacks
the file. Should it be gone on the device, the driver loads the device tree's crust image instead, with a
warning, and the state file says `firmware_from=device tree, the vendor image missing` (kernel patch `0327`);
`set vendor` refuses while the file is missing. The ARM side never touches the ARISC's `R_` block itself
([arisc](../subsystems/arisc.md)), so not even a driver that did not bind could hang the SoC.

**What `status` says**, line by line: what runs (`firmware=` of the driver's state file) and whether the
device tree or the module option chose it (`firmware_from=`); what that means - standby ready or not
(`ready=`; "not on this image" for one built without it), a power-off through crust (its build word, bit 24) or through the gate; what the next boot will
load (`h713-arisc.conf`, or the device tree without it); and what the image carries, the vendor firmware
and a crust image for this board. `set` refuses what the image does not carry: `vendor` without
`h713-arisc.bin` (a reinstall with your dump brings it), `crust` on a board whose image has no crust.

**At the end of an install**, `h713-install` says which firmware the image runs (`ARISC: the vendor firmware
from your dump ...` or, on an image with the standby, `ARISC: crust ...`, from the image table's `arisc` key,
`h713-mkimage --arisc`).

Exit: 0, 1 not possible on this image or the file not written, 2 usage. Measured: at the PC against a made-up
`/sys`, `/etc` and `/lib` (`userspace/h713-power/tests/test_arisc.py`), and on the HY300PRO-G-EU on 22.10.2026, on an
image whose FIT still started crust: the image's `h713-arisc.conf` -> the vendor firmware at the next boot, the EDID
sequence as under crust, `h713-power` offering no standby and the launcher without its Standby entry; `set crust` ->
crust, `set vendor` -> the vendor firmware again, each after a warm start; the HDMI picture the same under both (599
warp frames in 10.08 s); `h713-arisc.bin` moved away -> crust kept, with `0327` loaded from the device tree. Not
measured: an image without crust in its FIT (the release), and its cold start.
