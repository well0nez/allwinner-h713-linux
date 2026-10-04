# h713-features - which optional hardware this board has

The port grew on the HY310, which has an internal USB camera, an SC7A20 accelerometer and a focus motor.
Other boards of the family lack one or more of them - the HY300PRO-G-EU has the accelerometer only
([boards/README.md](../../boards/README.md), `FEATURES`). Two layers say what is there:

- **The record**, `/etc/h713/features`: the board's `FEATURES` out of `boards/<id>/board.env`, written into
  the image by `build-rootfs.sh --board` (`release/build-all.sh` passes its `--board`). It says what to expect.
- **The device nodes**: a `video4linux` node named "HD camera", an `iio:device` with `in_accel_x_raw`, a device
  of the `hy310-focus-motor` driver. They decide.

```
h713-features                     # one line per feature: present (and its node) or not present on this board
h713-features check --wait 30     # the boot check of h713-features.service
```

`check` waits up to `--wait` seconds while a feature the record lists is missing (a USB camera enumerates
late), then writes one line per feature into the journal and one `warning:` line for each the record lists
and the board does not show. It always exits 0: the unit is a report, never failed and never restarted.
Without a record (a tree built without `--board`) the nodes alone decide and nothing is compared.

What the rest of the system does with a missing feature: `h713-keystone-auto` is skipped (a condition on
the node; `99-h713-keystone.rules` starts it when a late sensor appears); `h713-keystone`, `h713-autofocus`,
`h713-focus` and `h713-cam` say "not present on this board" as their last line and exit `7`; the
[settings page](h713-panel.md) hides the controls. `$H713_SYS` replaces `/sys` in all five tools (the tests).
