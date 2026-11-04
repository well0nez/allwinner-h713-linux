#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
#
# make-sysroot.py - the Debian 13 (trixie) arm64 sysroot that h713-airplay is cross-linked against.
#
#   tools/make-sysroot.py [SYSROOT]        default /srv/h713/sysroot-trixie-arm64
#
# The board has no compiler and the host's own cross glibc (Ubuntu 2.43) is newer than the board's (2.41): a binary
# linked against it can ask for symbol versions the board does not have. So the cross link reads the board's own
# libraries: the packages below, at the versions trixie, trixie-updates and trixie-security carry (the board runs
# the same archive), fetched from deb.debian.org, checked against the SHA-256 of the archive's index and unpacked.
# Only libraries and headers - nothing is run from it. Dependency-free: urllib, lzma, hashlib, and dpkg-deb (or ar
# and tar) to unpack.
import hashlib, lzma, os, shutil, subprocess, sys, tempfile, urllib.request

INDEXES = [
    ("http://deb.debian.org/debian", "dists/trixie/main/binary-arm64/Packages.xz"),
    ("http://deb.debian.org/debian", "dists/trixie-updates/main/binary-arm64/Packages.xz"),
    ("http://security.debian.org/debian-security", "dists/trixie-security/main/binary-arm64/Packages.xz"),
]

# glibc for every binary; the rest for h713-airplay-show (FFmpeg, ALSA, EGL/GLES, GBM, DRM fourccs, libva, Wayland)
PACKAGES = """
libc6 libc6-dev linux-libc-dev libgcc-s1 libcrypt1 libcrypt-dev
libavcodec-dev libavcodec61 libavutil-dev libavutil59 libswresample-dev libswresample5
libasound2-dev libasound2t64
libegl-dev libegl1 libgles-dev libgles2 libgl-dev libglx-dev libgbm-dev libgbm1
libdrm-dev libdrm2 libva-dev libva2 libva-drm2
libwayland-dev libwayland-client0 libwayland-egl1 libwayland-cursor0 libwayland-server0
libfreetype-dev libpng-dev libbz2-dev libbrotli-dev zlib1g-dev libgcc-14-dev
""".split()


def newer(a, b):
    return subprocess.run(["dpkg", "--compare-versions", a, "gt", b]).returncode == 0


def index():
    pk = {}
    for base, rel in INDEXES:
        data = lzma.decompress(urllib.request.urlopen(f"{base}/{rel}", timeout=120).read()).decode("utf-8", "replace")
        for para in data.split("\n\n"):
            m = {}
            for line in para.split("\n"):
                if ": " in line and not line.startswith(" "):
                    k, v = line.split(": ", 1)
                    m[k] = v
            if "Package" in m and "Filename" in m:
                cur = pk.get(m["Package"])
                if cur is None or newer(m["Version"], cur["Version"]):
                    m["_base"] = base
                    pk[m["Package"]] = m
    return pk


def unpack(deb, root):
    if shutil.which("dpkg-deb"):
        subprocess.run(["dpkg-deb", "-x", deb, root], check=True)
        return
    with tempfile.TemporaryDirectory() as t:
        subprocess.run(["ar", "x", os.path.abspath(deb)], cwd=t, check=True)
        data = next(f for f in os.listdir(t) if f.startswith("data.tar"))
        subprocess.run(["tar", "-xf", os.path.join(t, data), "-C", root], check=True)


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/srv/h713/sysroot-trixie-arm64")
    os.makedirs(root, exist_ok=True)
    pk = index()
    missing = [p for p in PACKAGES if p not in pk]
    if missing:
        sys.exit("not in the trixie index: " + " ".join(missing))
    manifest = []
    with tempfile.TemporaryDirectory() as t:
        for p in PACKAGES:
            m = pk[p]
            url = m["_base"] + "/" + m["Filename"]
            deb = os.path.join(t, os.path.basename(m["Filename"]))
            body = urllib.request.urlopen(url, timeout=300).read()
            if hashlib.sha256(body).hexdigest() != m["SHA256"]:
                sys.exit(f"{p}: SHA-256 does not match the index")
            with open(deb, "wb") as f:
                f.write(body)
            unpack(deb, root)
            manifest.append(f"{p} {m['Version']}")
    # merged /usr: the linker scripts of libc6-dev name /lib/aarch64-linux-gnu/...
    for d in ("lib", "lib64"):
        link = os.path.join(root, d)
        if not os.path.lexists(link) and os.path.isdir(os.path.join(root, "usr", d)):
            os.symlink(os.path.join("usr", d), link)
    with open(os.path.join(root, "SYSROOT-MANIFEST"), "w") as f:
        f.write("\n".join(manifest) + "\n")
    print(f"sysroot {root}: {len(manifest)} packages")


if __name__ == "__main__":
    main()
