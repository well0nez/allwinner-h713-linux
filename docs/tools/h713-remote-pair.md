# h713-remote-pair - the stock Bluetooth remote

Pairs and keeps the stock BLE remote (`1d5a:c081`) through bluez: a Python 3 script over
`bluetoothctl` in `userspace/h713-remote-pair/`, run as the unit `h713-remote-pair.service` (`watch`).

```
h713-remote-pair pair [--timeout 60]        # scan for a remote in pairing mode and bond it
h713-remote-pair reconnect [--timeout 30]   # connect the bonded remote
h713-remote-pair status                     # bonded, connected, the input nodes
h713-remote-pair forget [ADDR]              # drop the bond
h713-remote-pair watch                      # what the unit runs: keep it bonded, pair when none is
```

Exit: 0 done, 1 no remote seen, 2 bluez refused, 3 usage or no `bluetoothctl`.

![The pairing hint on the wall](../images/osd/pairing.png)

**How pairing goes.** Hold **Left + Right** on the remote until its LED blinks: it drops its bond and
advertises undirected (flags 0x05, LE Limited Discoverable). `watch` bonds, trusts and connects it with
a NoInputNoOutput agent, as stock Android does without a dialog, and bluez reconnects it from then on:
a bonded remote wakes with a directed advert at the first key press, also after a reboot or a wake.
The hint "hold Left + Right" is an overlay of `h713-osd` (`h713-osd ctl pair`, 10 s); nothing in the
image sends it yet (`TODO.md` 2.54).

**A stale bond.** The remote keeps one bond. Paired with another box since, or put into pairing mode
here, it no longer matches the bond this box keeps. bluetoothd lets the kernel connect a bonded remote
on any advert, so the kernel connected the pairing remote within 2 ms with the dropped key, and the
remote left pairing mode before anything could pair it (btmon, HY300PRO-G-EU, 20.10.2026). `watch`
therefore sets the kernel to connect its remote on directed adverts only (mgmt Add Device, action 1)
and reads the HCI monitor channel as btmon does, with no scan of its own: a bonded remote that
advertises in pairing mode is forgotten and paired afresh. Without the monitor channel it works as
before, with `forget` first.

**Measured** on the HY300PRO-G-EU (20.10.2026): the pairing advert recognised and the bond forgotten
twice, the remote paired by a second Left + Right; the one-press pairing over a stale bond is not
measured with the remote (`TODO.md` 2.92). The remote reconnected at the first key after a reboot and
after a wake on both boards (`doku/174`, `doku/217`).

**What it does not do.** Infrared needs no pairing. The IR mouse key (`0x66`) sends only the vendor's
pairing request and starts nothing here (the owner, 17.10.2026). Other remotes may use another key
combination; stock's name list (`bt_list.ini`) is what the script matches. Bluetooth is down in a
standby, so the remote wakes the box over infrared.

Details: [Wi-Fi and Bluetooth](../subsystems/wifi.md#bluetooth), [the remote](../subsystems/remote.md).
