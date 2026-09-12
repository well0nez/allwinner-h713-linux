import mmap, os, sys
BASE = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x01c0e000
LEN  = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x2000
f = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(f, LEN, mmap.MAP_SHARED, mmap.PROT_READ, offset=BASE)
prev = None; star = False; nz = 0
for off in range(0, LEN, 16):
    w = [int.from_bytes(m[off+i:off+i+4], 'little') for i in range(0, 16, 4)]
    line = " ".join("%08x" % x for x in w)
    if any(w): nz += 1
    if line == prev:
        if not star: print("*"); star = True
        continue
    star = False; prev = line
    print("%04x: %s" % (off, line))
m.close(); os.close(f)
print("# %s..+%s, %d non-zero rows of %d" % (hex(BASE), hex(LEN), nz, LEN//16))
