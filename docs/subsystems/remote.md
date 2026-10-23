# The remote: infrared and Bluetooth

Two paths carry the stock remote's keys into Linux, and both end as ordinary input events that
`h713-keys`, `h713-power`, `h713-settings` and the Wayland compositors read. The user's side is
[the remote guide](../guides/remote.md).

## Infrared

The receiver is the SoC's `sunxi-cir` on PL9 (R_PIO), at the driver's default 8 MHz sample clock:
the device tree gave it 24 MHz until kernel `0252`, and the driver's integer arithmetic then shortened
every pulse to three quarters of its length, so NEC never decoded (measured 02.10.2026). `0253` drops
the vendor register values of `0021`, which belonged to the vendor's own sample model.

The keymap `rc-h713-fd02` (`0254`, built in) holds both stock remotes since `0329` (22.10.2026): the
HY310's and the HY300PRO-G-EU's remote with NEC address `0x02` (customer code `0xfd02`), and the
HY300's with address `0x00` (`0xff00`), each key on the code of the same key. The 15 scancodes of the
second were read on the HY300PRO-G-EU with the HY300's stock remote; they are the vendor's table
`customer_ir_ff00.kl`. The device tree names the map for every board; the table of the keys is in
[h713-keys](../tools/h713-keys.md#ir).

**The vendor's ARISC firmware switches the pin off.** It writes `0x222222ff` to `PL_CFG1` when it
starts and takes PL9 away from the receiver. Stock starts it before the kernel muxes the pin; here the
arisc module starts it after the receiver has probed, and no key arrived under it. Since `0328` the
receiver applies its pin again once the arisc driver has bound, through the pin's sleep state
(`gpio_in`, stock's), because pinctrl writes only a state that changes; the journal says
`PL9 applied again after the ARISC start`. Measured on the HY300PRO-G-EU on 22.10.2026: `PL_CFG1`
`0x222222ff` after a warm start without `0328`, `0x2222223f` with it; the keys of both remotes on both
boards with `v0.97-beta` (`doku/219`). crust leaves PL9 alone, so under it the pin ends where it began.

**In the gate** U-Boot reads the same pin and decodes NEC itself (`0102`): the power key of either
remote starts the board from off ([power-gate](../uboot/power-gate.md)). No ARISC firmware is involved.

**OK and Menu below code 248.** The remote's OK (`KEY_OK` 352 over IR, `KEY_SELECT` 353 over
Bluetooth) and its Menu (`KEY_MENU` 139) lie above the codes xkb names, so a Wayland client never saw
them. `/etc/udev/rules.d/70-h713-remote.rules` lets udev's keyboard builtin change the codes in the
kernel: OK becomes `KEY_ENTER`, Menu `KEY_COMPOSE`; `h713-keys` and `h713-power` read the new codes.

## Bluetooth

The remote that came with the HY310 and the HY300PRO-G-EU is also a BLE HID device (`1d5a:c081`, HID
over GATT). The kernel's `hid-h713-remote` (`0169`) fixes its consumer report, which is one byte
shorter than the descriptor says, and maps Home and the two focus keys; `h713-bluetooth` brings the
AIC8800's controller up on UART1 and bluez runs on top ([Wi-Fi and Bluetooth](wifi.md#bluetooth)).
`h713-remote-pair watch` keeps the remote bonded: hold Left + Right to pair, and a bonded remote
reconnects at the first key press ([h713-remote-pair](../tools/h713-remote-pair.md)). Over Bluetooth
the remote also has an air mouse (`REL_X`/`REL_Y`, OK as the left button) and a microphone; over
infrared the mouse key and the microphone key send one code, `0x66`, and do nothing here.

A held key repeats the same way over both paths: the IR receiver's 500/125 ms, which `h713-keys`
sets on the Bluetooth device when it opens it.

## Who reads the keys

| Reader | Keys |
|---|---|
| `h713-keys` | volume, mute, focus, Home; it holds both devices while the launcher is open, so a program under the launcher gets no key ([h713-keys](../tools/h713-keys.md)) |
| `h713-power` | the power key, on every input device that has one ([h713-power](../tools/h713-power.md)) |
| `h713-settings` | everything while its page is open ([h713-settings](../tools/h713-settings.md)) |
| cage and labwc (Kodi, the desktop, the browser) | the arrows, OK, Back, Menu and the mouse, through libinput; Home, the volume and focus keys and the power key are bound to nothing there ([h713-desktop](../tools/h713-desktop.md)) |

## Measured, and not

All 14 keys over infrared on the HY310 (11.10.2026) and 13 of 13 on the HY300PRO-G-EU; both remotes
on both boards with `v0.97-beta` and the vendor's ARISC firmware (22./23.10.2026, `doku/219`); the
start from the gate by both remotes. Not measured: which way the HY300 remote's focus keys turn the
focus, and the HY300 of issue #1 with its own remote - its owner has the retrofit set `test11`, his
report is outstanding ([known issues](../known-issues.md)).
