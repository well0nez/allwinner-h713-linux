# Switching off and on

![A short press of the power key: the countdown](../images/power/countdown-off.png)

**A short press of the power key** - on the projector or on either remote - shows a countdown of 15 s
in the middle of the picture. **OK** or a second press switches off at once, **Back** cancels, and
when the time is up the projector switches off. **A long press** (3 s) switches off without the
countdown.

**Off** is U-Boot's power-on gate: the lamp and the fan are off, the LED is red, the board draws
2.9 W and the power supply is silent. The power key on the projector, or the power key of either
stock remote, starts it again - a fresh boot of about 30 s to the launcher. Plugging the mains in
leaves it in the gate as well, as with the stock firmware.

**There is no standby in this release.** The release runs the vendor's firmware on the
power-management core. Our own firmware for it, crust, brings a standby at 2.0 to 2.4 W and a 0.3 W
off, but with it the power supply hums, so it stays in the image as an experiment
([ARISC](../subsystems/arisc.md), [standby](../subsystems/standby.md)). On an image built with
`--standby` the countdown offers the standby on its left and off on its right:

![On an image with the standby: standby left, off right](../images/power/countdown-standby-or-off.png)

`poweroff` over SSH does the same as the key. `reboot` does not stop in the gate; it comes straight
back up, so a reboot from far away never leaves a projector waiting for a finger.

Details: [h713-power](../tools/h713-power.md), [the power-on gate](../uboot/power-gate.md).
