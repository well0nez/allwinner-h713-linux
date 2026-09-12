#!/usr/bin/env python3
"""Ein mit mmdebstrap --variant=extract entpacktes Sysroot fuer clang --sysroot brauchbar machen.

Zwei Dinge fehlen, weil --variant=extract keine Maintainer-Skripte laufen laesst:
 1. die merged-usr-Links /lib -> usr/lib, /bin, /sbin, /lib64 (legt base-files im
    postinst an). Ohne /lib scheitert der Link: der Linker-Script usr/lib/.../libc.so
    verweist auf /lib/aarch64-linux-gnu/libc.so.6, und ld.lld sucht das INNERHALB des
    Sysroots ("cannot find /lib/... inside SYSROOT", 12.09.2026).
 2. absolute Symlinks (-> /lib/...) muessen relativ werden, sonst loest clang sie auf
    dem HOST auf.
    python3 sysroot-fix.py SYSROOT
"""
import os, sys
wurzel = os.path.abspath(sys.argv[1]); n = 0
for name in ("lib", "lib64", "bin", "sbin"):
    ziel = os.path.join(wurzel, "usr", name); link = os.path.join(wurzel, name)
    if os.path.isdir(ziel) and not os.path.lexists(link):
        os.symlink("usr/" + name, link); print(f"{name} -> usr/{name}")
for d, _dirs, files in os.walk(wurzel):
    for f in files + _dirs:
        p = os.path.join(d, f)
        if not os.path.islink(p):
            continue
        ziel = os.readlink(p)
        if not ziel.startswith("/"):
            continue
        neu = os.path.relpath(os.path.join(wurzel, ziel.lstrip("/")), d)
        os.unlink(p); os.symlink(neu, p); n += 1
print(f"{n} absolute Symlinks relativ gemacht")
