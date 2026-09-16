#!/usr/bin/env python3
"""test-stub.py -- play the driver, so that h713-focus runs without a device.

Creates motor_ctrl, motor_limit and motor_ctrl_no_limit in a directory and
reacts to writes like hy310-focus-motor: cmd 8/9 moves the counter in msteps,
at the edge (default step -206, as measured on 12.09.2026) raw drops to 0, then
the stub reverses, sets edge_dn and holds at -207. A command against a latched
edge is dropped silently -- as in the driver. cmd 3 drains (does nothing here).

    python3 test-stub.py DIR [EDGE] &
    H713_FOCUS_SYSFS=DIR ../h713-focus down 20      # runs into the edge
    H713_FOCUS_SYSFS=DIR ../h713-focus down 4       # blocked: edge_dn=1
    H713_FOCUS_SYSFS=DIR ../h713-focus up 4         # free

With this the whole flow of the script was checked on 12.09.2026 before it
reached the device (result: reproduces the measurement exactly). The stub does
NOT clear edge_dn when driving upwards -- the real driver does; whoever needs
that adds it here. Ends by itself after 60 s.
"""
import pathlib
import sys
import time

d = pathlib.Path(sys.argv[1])
edge = int(sys.argv[2]) if len(sys.argv) > 2 else -206
d.mkdir(parents=True, exist_ok=True)
step, edge_dn, edge_up, raw = -200, 0, 0, 1


def write():
    # Atomic (write + rename): sysfs always delivers a line as a whole, a file
    # with truncate+write on the other hand is briefly empty -- and h713-focus
    # rightly stops on an unreadable line (12.09.: found that way).
    tmp = d / ".motor_limit.neu"
    tmp.write_text(
        f"{1 if raw == 1 else 0} up=1 dn=1 num=1 raw={raw} act=1 "
        f"edge_up={edge_up} edge_dn={edge_dn} step={step}\n")
    tmp.replace(d / "motor_limit")


write()
(d / "motor_ctrl_no_limit").write_text("0\n")
(d / "motor_ctrl").write_text("0\n")
last = 0.0
end = time.time() + 60
while time.time() < end:
    try:
        m = (d / "motor_ctrl").stat().st_mtime
    except OSError:
        m = last
    if m != last:
        last = m
        try:
            word = int((d / "motor_ctrl").read_text().strip())
        except ValueError:
            word = 0
        cmd, n = word >> 8, word & 0x7f
        if cmd in (8, 9):
            down = (cmd == 9)
            if (down and edge_dn) or (not down and edge_up):
                continue                        # the driver drops it silently
            for _ in range(max(1, n)):
                step += -1 if down else 1
                if down and step <= edge:       # the level drops
                    raw = 0
                    write()
                    time.sleep(0.08)
                    step -= 1                   # driver: one mstep on, then back
                    raw = 1
                    edge_dn = 1
                    write()
                    break
                write()
                time.sleep(0.03)
    time.sleep(0.01)
