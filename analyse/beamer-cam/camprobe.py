#!/usr/bin/env python3
"""Minimal V4L2-Abfrage ohne v4l2-ctl: Faehigkeiten, Formate, Groessen."""
import fcntl, struct, sys, ctypes

VIDIOC_QUERYCAP      = 0x80685600
VIDIOC_ENUM_FMT      = 0xc0405602
VIDIOC_ENUM_FRAMESIZES = 0xc02c564a

def fourcc(v):
    return "".join(chr((v >> (8*i)) & 0xff) for i in range(4))

dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/video2"
fd = open(dev, "rb+", buffering=0)

buf = bytearray(104)
fcntl.ioctl(fd, VIDIOC_QUERYCAP, buf, True)
driver, card, businfo = buf[0:16], buf[16:48], buf[48:80]
version, caps, dcaps = struct.unpack_from("<III", buf, 80)
z = lambda b: b.split(b"\0")[0].decode("utf-8", "replace")
print("Geraet     :", dev)
print("Treiber    :", z(driver))
print("Karte      :", z(card))
print("Bus        :", z(businfo))
print("Version    : %d.%d.%d" % (version >> 16, (version >> 8) & 0xff, version & 0xff))
print("Caps       : 0x%08x  (Video-Capture: %s, Streaming: %s)"
      % (dcaps, bool(dcaps & 0x00000001), bool(dcaps & 0x04000000)))

print("\nFormate:")
for i in range(32):
    f = bytearray(64)
    struct.pack_into("<II", f, 0, i, 1)   # index, type=V4L2_BUF_TYPE_VIDEO_CAPTURE
    try:
        fcntl.ioctl(fd, VIDIOC_ENUM_FMT, f, True)
    except OSError:
        break
    flags, = struct.unpack_from("<I", f, 8)
    desc = z(bytes(f[12:44]))
    pf,  = struct.unpack_from("<I", f, 44)
    print("  %-8s %-28s flags=0x%x" % (fourcc(pf), desc, flags))
    sizes = []
    for j in range(24):
        s = bytearray(44)
        struct.pack_into("<II", s, 0, j, pf)
        try:
            fcntl.ioctl(fd, VIDIOC_ENUM_FRAMESIZES, s, True)
        except OSError:
            break
        stype, = struct.unpack_from("<I", s, 8)
        if stype == 1:   # DISCRETE
            w, h = struct.unpack_from("<II", s, 12)
            sizes.append("%dx%d" % (w, h))
        else:
            w0,h0,w1,h1 = struct.unpack_from("<IIII", s, 12)[:4]
            sizes.append("%dx%d..%dx%d" % (w0,h0,w1,h1)); break
    if sizes:
        print("           ", ", ".join(sizes))
fd.close()
