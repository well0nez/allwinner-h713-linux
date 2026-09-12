#!/usr/bin/env python3
"""V4L2-Steuerung setzen/lesen ohne v4l2-ctl: camset.py DEV ID WERT | camset.py DEV ID"""
import fcntl, struct, os, sys
VIDIOC_G_CTRL = 0xc008561b
VIDIOC_S_CTRL = 0xc008561c
dev, cid = sys.argv[1], int(sys.argv[2], 0)
fd = os.open(dev, os.O_RDWR)
if len(sys.argv) > 3:
    b = bytearray(8); struct.pack_into("<Ii", b, 0, cid, int(sys.argv[3]))
    try:
        fcntl.ioctl(fd, VIDIOC_S_CTRL, b, True); print("gesetzt")
    except OSError as e:
        print("S_CTRL fehlgeschlagen:", e)
b = bytearray(8); struct.pack_into("<Ii", b, 0, cid, 0)
try:
    fcntl.ioctl(fd, VIDIOC_G_CTRL, b, True)
    print("0x%08x = %d" % struct.unpack_from("<Ii", b, 0))
except OSError as e:
    print("G_CTRL fehlgeschlagen:", e)
