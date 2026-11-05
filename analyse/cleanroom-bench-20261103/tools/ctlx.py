import sys; sys.path.insert(0,"/data/bench"); from blog import _page, log, openlog
def rb(a):
    m,o=_page(a); return m[o]
openlog(sys.argv[1]); lab=sys.argv[2]
for a in range(0x06801000, 0x06804000, 32):
    log(f"DUMP {lab} ctlx {a:#010x}: " + " ".join("%02x" % rb(a+i) for i in range(32)))
