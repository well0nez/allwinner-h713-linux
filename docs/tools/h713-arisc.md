# h713-arisc

Which firmware runs on the ARISC, the SoC's power-management coprocessor, and the way back to the
vendor's without a reinstall. On the device, as root.

```
h713-arisc status              # which runs now, where that choice came from, what it means
h713-arisc set vendor          # the vendor firmware from your dump, from the next boot on
h713-arisc set crust           # crust, built with the image, from the next boot on
```

**The choice.** crust is the default on every board with a measured crust configuration (the HY310,
the HY300PRO-G-EU) - only with it the standby and the 0.3 W power-off exist
([arisc](../subsystems/arisc.md), [standby](../subsystems/standby.md)). The vendor's firmware
(`h713-arisc.bin`, which `h713-install` puts into every image from your own dump) stays one command away:
`set vendor` writes `/etc/modprobe.d/h713-arisc.conf` with `options sun50i_h713_arisc firmware=vendor`,
and the driver loads that file at the next boot instead of the tree's crust image (kernel patch `0267`;
with crust started by TF-A, the driver replaces it, patch `0192`). `set crust` writes `firmware=crust`,
which names the tree's own image again. With the vendor firmware there is no standby, and a power-off
ends in the power-on gate, where the key starts the next boot.

**What `status` says**, line by line: what runs (`firmware=` of the driver's state file) and whether the
device tree or the module option chose it (`firmware_from=`); what that means - standby ready or not
(`ready=`), a power-off through crust (its build word, bit 24) or through the gate; what the next boot will
load (`h713-arisc.conf`, or the device tree without it); and what the image carries, the vendor firmware
and a crust image for this board. `set` refuses what the image does not carry: `vendor` without
`h713-arisc.bin` (a reinstall with your dump brings it), `crust` on a board whose image has no crust.

**At the end of an install**, `h713-install` says which firmware the image runs (`ARISC: crust ...` or
`ARISC: the vendor firmware from your dump ...`, from the image table's `arisc` key, `h713-mkimage --arisc`).

Exit: 0, 1 not possible on this image or the file not written, 2 usage. Measured: at the PC against a made-up
`/sys`, `/etc` and `/lib` (`userspace/h713-power/tests/test_arisc.py`); the switch on the device is TODO 5.20's
measurement.
