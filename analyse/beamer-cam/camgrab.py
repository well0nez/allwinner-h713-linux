#!/usr/bin/env python3
"""Ein Einzelbild von einer V4L2-Kamera holen, ohne v4l2-ctl und ohne ffmpeg.

MMAP-Streaming, YUYV -> PPM. Nur das Noetige; laeuft auf dem Geraet mit
blankem python3.
"""
import fcntl, struct, mmap, sys, os, time

VIDIOC_S_FMT     = 0xc0d05605
VIDIOC_REQBUFS   = 0xc0145608
VIDIOC_QUERYBUF  = 0xc0585609
VIDIOC_QBUF      = 0xc058560f
VIDIOC_DQBUF     = 0xc0585611
VIDIOC_STREAMON  = 0x40045612
VIDIOC_STREAMOFF = 0x40045613

BUF_TYPE_CAPTURE = 1
MEMORY_MMAP      = 1
FMT_YUYV         = 0x56595559   # 'YUYV'

dev  = sys.argv[1] if len(sys.argv) > 1 else "/dev/video2"
out  = sys.argv[2] if len(sys.argv) > 2 else "/tmp/cam.ppm"
W, H = (int(x) for x in (sys.argv[3] if len(sys.argv) > 3 else "640x480").split("x"))
WARM = int(sys.argv[4]) if len(sys.argv) > 4 else 10   # Bilder verwerfen (Belichtung)

fd = os.open(dev, os.O_RDWR)

# Macke der Realtek 0bda:5803 (gemessen 11.09.): frisch geladen liefert sie
# schwarz, bis einmal irgendeine Steuerung geschrieben wurde. Also Belichtung
# lesen und unveraendert zurueckschreiben, bevor der Stream startet.
VIDIOC_G_CTRL, VIDIOC_S_CTRL, EXPOSURE_ABS = 0xc008561b, 0xc008561c, 0x009a0902
try:
    c = bytearray(8); struct.pack_into("<Ii", c, 0, EXPOSURE_ABS, 0)
    fcntl.ioctl(fd, VIDIOC_G_CTRL, c, True)
    fcntl.ioctl(fd, VIDIOC_S_CTRL, c, True)
except OSError:
    pass   # andere Kamera ohne diese Steuerung: egal

# --- Format setzen ---
f = bytearray(208)
struct.pack_into("<I", f, 0, BUF_TYPE_CAPTURE)
struct.pack_into("<IIII", f, 8, W, H, FMT_YUYV, 1)   # width,height,pixelformat,field=NONE
fcntl.ioctl(fd, VIDIOC_S_FMT, f, True)
W, H, pf = struct.unpack_from("<III", f, 8)
bpl, sizeimage = struct.unpack_from("<II", f, 24)
print("Format: %dx%d  %s  bytesperline=%d  sizeimage=%d"
      % (W, H, "".join(chr((pf >> (8*i)) & 0xff) for i in range(4)), bpl, sizeimage))

# --- Puffer anfordern ---
NBUF = 4
r = bytearray(20)
struct.pack_into("<III", r, 0, NBUF, BUF_TYPE_CAPTURE, MEMORY_MMAP)
fcntl.ioctl(fd, VIDIOC_REQBUFS, r, True)
NBUF, = struct.unpack_from("<I", r, 0)
print("Puffer: %d" % NBUF)

maps = []
for i in range(NBUF):
    b = bytearray(88)
    struct.pack_into("<III", b, 0, i, BUF_TYPE_CAPTURE, 0)
    struct.pack_into("<I", b, 60, MEMORY_MMAP)
    fcntl.ioctl(fd, VIDIOC_QUERYBUF, b, True)
    offset, = struct.unpack_from("<I", b, 64)
    length, = struct.unpack_from("<I", b, 72)
    maps.append(mmap.mmap(fd, length, mmap.MAP_SHARED,
                          mmap.PROT_READ | mmap.PROT_WRITE, offset=offset))
    fcntl.ioctl(fd, VIDIOC_QBUF, b, True)

fcntl.ioctl(fd, VIDIOC_STREAMON, struct.pack("<I", BUF_TYPE_CAPTURE))

frame = None
try:
    for n in range(WARM + 1):
        b = bytearray(88)
        struct.pack_into("<II", b, 0, 0, BUF_TYPE_CAPTURE)
        struct.pack_into("<I", b, 60, MEMORY_MMAP)
        for _ in range(200):
            try:
                fcntl.ioctl(fd, VIDIOC_DQBUF, b, True); break
            except OSError as e:
                if e.errno != 11: raise      # EAGAIN
                time.sleep(0.01)
        else:
            raise SystemExit("Zeitueberschreitung beim Warten auf ein Bild")
        idx,       = struct.unpack_from("<I", b, 0)
        bytesused, = struct.unpack_from("<I", b, 8)
        if n == WARM:
            frame = maps[idx][:bytesused or sizeimage]
        fcntl.ioctl(fd, VIDIOC_QBUF, b, True)
finally:
    fcntl.ioctl(fd, VIDIOC_STREAMOFF, struct.pack("<I", BUF_TYPE_CAPTURE))

# --- YUYV -> PPM ---
def clamp(v): return 0 if v < 0 else (255 if v > 255 else v)
rows = bytearray()
for y in range(H):
    line = frame[y*bpl : y*bpl + W*2]
    for x in range(0, len(line) - 3, 4):
        y0, u, y1, v = line[x], line[x+1], line[x+2], line[x+3]
        cu, cv = u - 128, v - 128
        for yy in (y0, y1):
            c = yy - 16
            rows += bytes((clamp((298*c + 409*cv + 128) >> 8),
                           clamp((298*c - 100*cu - 208*cv + 128) >> 8),
                           clamp((298*c + 516*cu + 128) >> 8)))
with open(out, "wb") as fh:
    fh.write(b"P6\n%d %d\n255\n" % (W, H)); fh.write(rows)

hell = sum(frame[i] for i in range(0, len(frame), 2)) / (len(frame)/2)
print("Bild -> %s  (%d Byte), mittlere Helligkeit Y = %.1f" % (out, len(rows)+15, hell))
