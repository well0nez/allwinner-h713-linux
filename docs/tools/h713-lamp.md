# h713-lamp - the lamp's modes (the L018)

On the L018 the lamp is dimmable, and the fan follows it: its stock firmware has three lamp modes, and one mode index
sets both. The board manager owns lamp and fan there (kernel `0332`, the L018 tree `0331`) and sets them in one step from
the board's own tables; this tool reads and sets the mode and keeps the choice. Every other board has no lamp modes - the
HY310's light follows the SoC's current and no PWM reaches it.

| Mode | Lamp (PWM2) | Fan (PWM0) | Fan, measured |
|---|---|---|---|
| `std` (the boot mode) | 50 % | 70 % | 3210 rpm |
| `low` | 75 % | 60 % | 2880 rpm |
| `high` | 30 % | 95 % | 3660 rpm after 2 s, rising |

The lamp dims as its duty rises, so `high` has the smallest duty. The registers are the ones the stock firmware wrote in
the same three modes, the brightness of the three was confirmed by eye, and the fan follows (L018, 24./25.10.2026,
`doku/220`). U-Boot already brings the board up at `std` (`CONFIG_H713_BOARD_L018`) and keeps lamp and fan dark in the gate.

```
h713-lamp                 # status: the mode, the modes, the thermal mode, fan speed, temperature, the mode kept
h713-lamp set low         # set it now and keep it in /etc/h713/lamp.conf ("mode = low")
h713-lamp restore         # the boot step of h713-lamp.service: set the kept mode
```

`set` takes a name of `lamp_modes`; another word is refused (exit 2). Exit 7, "lamp modes: not present on this board",
on a board without them; `restore` then says so and exits 0, so `h713-lamp.service` (enabled in every image) finishes
cleanly everywhere - it waits up to 10 s for the board manager, which is a module.

**The thermal mode.** Above `temp_warn` (41 °C on the L018) for 30 cycles of 2 s the driver switches to the board's
thermal mode (mode 3: lamp 75 %, fan 70 %), keeps the chosen mode and sets it again at `temp_resume` (34 °C); a mode
chosen meanwhile is kept for then, so the lamp does not get brighter while the box is hot. `status` says `thermal on`
while it holds. The thermal mode itself is **not measured** (the NTC read 21-28 °C). At `temp_poweroff` (51 °C) the L018
powers off in order, as its stock firmware does ([board manager](../subsystems/board-mgr.md)) - also not measured.

**Where it shows.** The settings page has the area "Projector" with Lamp, Fan and Temperature, and the web panel a card
"Lamp" - both only where `lamp_mode` exists ([h713-settings](h713-settings.md), [h713-panel](h713-panel.md));
`h713-features` names the feature `lamp-modes` ([h713-features](h713-features.md)).

The sysfs the tool uses, in the board manager's device (`hy310-board-mgr`): `lamp_mode` (read: the chosen mode, write: a
name), `lamp_modes` (the names), `thermal_mode` (1 while the thermal mode holds); the attributes exist only with a lamp.
Tests: `userspace/h713-lamp/tests/` (a made-up sysfs, `$H713_SYS`, `$H713_LAMP_CONF`).
