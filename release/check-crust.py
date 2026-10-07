#!/usr/bin/env python3
"""check-crust.py -- does a built image carry the crust it was built with, and nothing the release must not?

boards/check.sh judges the sources and release/check-hdcp-artifacts.sh the HDCP path; this one judges
crust and the standby in the ARTEFACTS. release/build-all.sh runs it in step 10 with all of them:

  release/check-crust.py --board hy310 [--crust scp.bin --crust-config crust.config --crust-version v0.6.35]
      --release-fit uboot-proper-release.bin --empty-fit u-boot-installer.bin --empty-fit u-boot-h713-probe.bin
      --uboot-config <release O>/.config --dtb sun50i-h713-hy310.dtb --rootfs hy310-rootfs.tar --bl31 bl31.bin
      [--standby]
  release/check-crust.py --dt-firmware FILE.dtb     prints the arisc node's firmware-name[0] (boards/check.sh)

Without --crust the board has none: no scp in a FIT, no *-crust.bin in the rootfs or the device tree. A
check whose input is missing is named as skipped. Exit 0 = may be released, 1 = do not release.
"""
import argparse
import hashlib
import os
import re
import struct
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The build word crust writes at +0x23c of its contract page: image size in 19..0, these options above.
BITS = {24: "H713_DRAM_SELF_REFRESH", 25: "H713_DEEP_SLEEP", 26: "H713_IR_WAKE_NECX", 27: "H713_DEEP_VDD_SYS",
        28: "H713_DEEP_PLL_LDO", 29: "H713_SLEEP_NET", 30: "H713_TEST", 31: "H713_DEEP_AVCC_GATING"}
REFUSED = (25, 27, 28, 30, 31)    # never in a release: deep sleep, its unmeasured steps, a test build
GATED = (29,)                     # the sleep net: only once versions.env CRUST_RELEASE_ALLOW names it (stage S0)
# crust's DRAM values against U-Boot's, which trained the DRAM: crust's H713_DRAM_<x> = U-Boot's CONFIG_<y>
DRAM = dict([("CLK", "DRAM_CLK")] + [(k, "DRAM_SUNXI_" + k) for k in
            ("ZQ", "ODT_EN", "PARA1", "PARA2", "MR0", "MR1", "MR2", "MR3", "TPR5", "TPR6", "TPR9", "TPR13")])
T1_MARK = b"SoC watchdog fed and armed"                  # TF-A: the reset that feeds the running watchdog first
TEST_BL31_MARK = b"PSCI: test bench BL31"                # TF-A built with SUNXI_STANDBY_UNMEASURED=1: never released
# TF-A's sunxi_standby.c is built only with SUNXI_SYSTEM_SUSPEND=1; these are its texts (NOTICE and ERROR, in every
# release BL31). All of them: the BL31 offers SYSTEM_SUSPEND; none: it does not; some: that file changed and this
# list has to follow - refused, so that a reworded text never makes a suspend BL31 look like one without.
SUSPEND_MARKS = (b"PSCI: system suspend refused (", b"not usable by the ARISC", b"PSCI: msgbox port 3 keeps the request",
                 b"PSCI: system suspend, cpu op req sent", b"PSCI: msgbox port 3 stays full",
                 b"PSCI: system counter restored", b"PSCI: back from system suspend")
# systemd's system.conf: the first main file of these directories, then every drop-in by name, a name in an earlier
# directory hiding the same name in a later one; the last setting wins (systemd-system.conf(5)). /run is a tmpfs
# at boot, a file there in the tar is never read. RebootWatchdogSec's built-in 10min needs no file and never arms:
# sunxi_wdt stops at 16 s, and systemd-shutdown logs "Failed to set watchdog hardware timeout to 10min: Invalid
# argument" (seen on the HY310, 07.10.2026). If W1/W2 change that maximum, this has to count the default.
WD_DIRS = ("etc", "usr/local/lib", "lib")
fails = 0


def ok(msg):
    print("  ok    " + msg)


def fail(msg):
    global fails
    fails += 1
    print("  FAIL  " + msg)


def skip(msg):
    print("  skip  " + msg)


def check(good, ok_msg, fail_msg):
    (ok if good else fail)(ok_msg if good else fail_msg)
    return good


def num(v):
    return int(v, 16) if v.lower().startswith("0x") else int(v)


def fdt_nodes(blob):
    """[(path, {property: bytes})] of a flattened tree, and where a FIT's external data begins."""
    magic, total, off_struct, off_strings = struct.unpack(">IIII", blob[:16])
    if magic != 0xd00dfeed:
        raise ValueError("no flattened device tree")
    strings, out, path, props, p = blob[off_strings:], [], [], [], off_struct
    while True:
        tok, = struct.unpack(">I", blob[p:p + 4])
        p += 4
        if tok == 1:
            end = blob.index(b"\0", p)
            path.append(blob[p:end].decode())
            props.append({})
            p = (end + 4) & ~3
        elif tok == 2:
            out.append(("/".join(path) or "/", props.pop()))
            path.pop()
        elif tok == 3:
            size, name = struct.unpack(">II", blob[p:p + 8])
            props[-1][strings[name:strings.index(b"\0", name)].decode()] = blob[p + 8:p + 8 + size]
            p = (p + 8 + size + 3) & ~3
        elif tok == 9:
            return out, (total + 3) & ~3
        elif tok != 4:
            raise ValueError("bad token %d at %d" % (tok, p - 4))


def fit_scp(path):
    """The FIT's scp image (U-Boot proper, or u-boot-sunxi-with-spl.bin at 32 KiB): bytes, or None."""
    d = open(path, "rb").read()
    off = next((o for o in (0, 0x8000) if d[o:o + 4] == b"\xd0\x0d\xfe\xed"), None)
    if off is None:
        raise ValueError("no FIT at 0 or 32 KiB")
    d = d[off:]
    nodes, base = fdt_nodes(d)
    props = dict(nodes).get("/images/scp")
    if props is None:
        return None
    if "data" in props:
        return props["data"]
    size = int.from_bytes(props.get("data-size", b"\0\0\0\0"), "big")
    if "data-position" in props:
        start = int.from_bytes(props["data-position"], "big")
    else:
        start = base + int.from_bytes(props.get("data-offset", b"\0\0\0\0"), "big")
    return d[start:start + size]


def dt_firmware(path):
    """firmware-name[0] of the arisc node, "" without one, None without an arisc node."""
    for _, props in fdt_nodes(open(path, "rb").read())[0]:
        if b"allwinner,sun50i-h713-arisc" in props.get("compatible", b"").split(b"\0"):
            return props.get("firmware-name", b"").split(b"\0")[0].decode()
    return None


def kconfig(path):
    return dict(re.findall(r'^CONFIG_(\w+)="?([^"\n]*)"?$', open(path).read(), re.M))


def rootfs(path):
    """The parts of the rootfs tar this gate reads, by path without ./ and with usr/lib -> lib."""
    want = re.compile(r"(usr/)?lib/firmware/[^/]+-crust\.bin|(etc|(usr/)?lib|usr/local/lib)/systemd/system\.conf(\.d/[^/]+\.conf)?|"
                      r"etc/systemd/(sleep\.conf\.d/10-h713\.conf|system/multi-user\.target\.wants/h713-power\.service)")
    out = {}
    with tarfile.open(path) as t:
        for m in t:
            name = re.sub(r"^\./", "", m.name)
            if want.fullmatch(name):
                f = t.extractfile(m) if m.isfile() else None
                out[re.sub(r"^usr/lib/", "lib/", name)] = f.read() if f else b""
    return out


def watchdog(parts):
    """The settings systemd ends up with that arm the watchdog: ["RuntimeWatchdogSec=16s (file)", ...]."""
    main = next((d + "/systemd/system.conf" for d in WD_DIRS if d + "/systemd/system.conf" in parts), None)
    drops = {}
    for d in reversed(WD_DIRS):
        drops.update({os.path.basename(k): k for k in parts if k.startswith(d + "/systemd/system.conf.d/")})
    val = {}
    for f in [main] * bool(main) + [drops[n] for n in sorted(drops)]:
        for line in parts[f].decode(errors="replace").splitlines():
            k, eq, v = (x.strip() for x in line.partition("="))
            if eq and k in ("RuntimeWatchdogSec", "RebootWatchdogSec"):
                val[k] = ("%s=%s (%s)" % (k, v, f), v.lower())
    # off, 0, 0s, 0min and an empty value (back to the default) do not arm it; "default" and any time do
    return [s for s, v in val.values() if not re.fullmatch(r"off|(0+(\.0*)?\s*[a-z]*\s*)*", v)]


def sha(b):
    return hashlib.sha256(b).hexdigest()[:16]


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("--dt-firmware", metavar="DTB")
    a.add_argument("--board")
    a.add_argument("--crust")
    a.add_argument("--crust-config")
    a.add_argument("--crust-version")
    a.add_argument("--release-fit")
    a.add_argument("--empty-fit", action="append", default=[])
    a.add_argument("--uboot-config")
    a.add_argument("--dtb")
    a.add_argument("--rootfs")
    a.add_argument("--bl31")
    a.add_argument("--standby", action="store_true")
    a.add_argument("--versions", default=os.path.join(ROOT, "mainline", "config", "versions.env"))
    o = a.parse_args(argv)
    if o.dt_firmware:
        fw = dt_firmware(o.dt_firmware)
        print("-" if fw is None else fw)
        return 0
    if not o.board:
        a.error("--board is needed")
    crust = open(o.crust, "rb").read() if o.crust else None
    name = o.board + "-crust.bin"
    print("crust: %s" % ("%s, %d bytes, sha256 %s" % (name, len(crust), sha(crust)) if crust else "none"))

    # 1. one crust, in the release FIT and in the rootfs; none in the installer's or the probe's FIT
    if o.release_fit:
        scp = fit_scp(o.release_fit)
        if crust is not None:
            check(scp == crust, "release FIT scp is this crust", "release FIT scp is %s, the crust built is %s"
                  % ("missing" if scp is None else sha(scp) if scp else "empty", sha(crust)))
        else:
            check(not scp, "release FIT carries no crust", "release FIT carries an scp nobody built for this board")
    else:
        skip("no --release-fit")
    for f in o.empty_fit:
        scp = fit_scp(f)
        check(not scp, "%s: scp empty" % os.path.basename(f), "%s carries an scp (%s)" % (os.path.basename(f), sha(scp or b"")))
    parts = rootfs(o.rootfs) if o.rootfs else None
    if parts is not None:
        found = sorted(k for k in parts if k.endswith("-crust.bin"))
        if crust is not None:
            check(found == ["lib/firmware/" + name] and parts[found[0]] == crust, "rootfs /lib/firmware/%s is this crust"
                  % name, "rootfs crust %s, wanted only %s %s" % (found or "missing", name, sha(crust)))
        else:
            check(not found, "rootfs carries no crust", "rootfs carries %s" % found)
    else:
        skip("no --rootfs")
    if o.dtb:
        fw = dt_firmware(o.dtb)
        good = fw == name if crust is not None else not (fw or "").endswith("-crust.bin")
        check(good, "device tree arisc firmware-name[0] = %s" % fw,
              "device tree names %r, the build %s" % (fw, "built " + name if crust is not None else "built no crust"))
    else:
        skip("no --dtb")

    # 2. the crust variant: options the release refuses, DRAM values, version text
    word = None
    if o.crust_config:
        before = fails
        cfg = kconfig(o.crust_config)
        allow = re.search(r'^CRUST_RELEASE_ALLOW="?([^"#\n]*)', open(o.versions).read(), re.M)
        allow = (allow.group(1) if allow else "").split()
        for b in REFUSED + GATED:
            if cfg.get(BITS[b]) == "y" and not (b in GATED and BITS[b] in allow):
                fail("crust .config has CONFIG_%s=y (build word bit %d) - not for a release" % (BITS[b], b))
        for x in set(allow) - {BITS[b] for b in GATED}:
            fail("versions.env CRUST_RELEASE_ALLOW names %s, which no release may carry" % x)
        if any(k.startswith("H713_TEST_") and v == "y" for k, v in cfg.items()):
            fail("crust .config has an H713_TEST_* option")
        if o.standby and cfg.get(BITS[24]) != "y":
            fail("--standby without CONFIG_H713_DRAM_SELF_REFRESH: the release standby is self-refresh")
        word = (len(crust) if crust else 0) | sum(1 << b for b in BITS if cfg.get(BITS[b]) == "y")
        if o.uboot_config and cfg.get(BITS[24]) == "y":
            ub = kconfig(o.uboot_config)
            ub_type = 3 if ub.get("SUNXI_DRAM_H713_DDR3_STOCK") == "y" else 7 if ub.get("SUNXI_DRAM_H713_LPDDR3_STOCK") == "y" else None
            diff = ["%s %s/%s" % (k, cfg.get("H713_DRAM_" + k), ub.get(u)) for k, u in DRAM.items()
                    if num(cfg.get("H713_DRAM_" + k, "-1")) != num(ub.get(u, "-2"))]
            if num(cfg.get("H713_DRAM_TYPE", "-1")) != ub_type:
                diff.append("TYPE %s/%s" % (cfg.get("H713_DRAM_TYPE"), ub_type))
            check(not diff, "crust DRAM values = U-Boot's (%d)" % (len(DRAM) + 1), "crust/U-Boot DRAM differ: " + ", ".join(diff))
        elif cfg.get(BITS[24]) == "y":
            skip("no --uboot-config: crust's DRAM values unchecked")
        if fails == before:
            ok("crust options: nothing the release refuses (allowed: %s)" % (" ".join(allow) or "none"))
    elif crust is not None:
        fail("--crust without --crust-config: the variant cannot be judged")
    if o.crust_version:
        m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", o.crust_version)
        check(m and int(m.group(3)) < 10000, "crust version %s" % o.crust_version,
              "crust version %s: a dirty tree or one without tags (scripts/version.sh)" % o.crust_version)
    elif crust is not None:
        fail("--crust without --crust-version")

    # 3. BL31 and rootfs against each other: standby, watchdog
    bl31 = open(o.bl31, "rb").read() if o.bl31 else None
    if bl31 is not None:
        n = sum(m in bl31 for m in SUSPEND_MARKS)
        has = n == len(SUSPEND_MARKS)
        if 0 < n < len(SUSPEND_MARKS):
            fail("BL31 carries %d of the %d texts of TF-A's standby code: sunxi_standby.c changed, check-crust.py's "
                 "SUSPEND_MARKS have to follow" % (n, len(SUSPEND_MARKS)))
        elif has != o.standby:
            fail("BL31 %s SYSTEM_SUSPEND, the build %s --standby" % ("offers" if has else "lacks", "has" if o.standby else "has no"))
        elif has and crust is None:
            fail("BL31 offers SYSTEM_SUSPEND without a crust in the release FIT")
        else:
            ok("BL31 %s SYSTEM_SUSPEND" % ("offers" if has else "without"))
        if TEST_BL31_MARK in bl31:
            fail("BL31 is a test bench build (SUNXI_STANDBY_UNMEASURED=1): it lets unmeasured deep-sleep steps through")
    if parts is not None:
        sleep = parts.get("etc/systemd/sleep.conf.d/10-h713.conf", b"")
        if o.standby:
            good = all(x in sleep.split(b"\n") for x in (b"AllowSuspend=yes", b"SuspendState=mem", b"MemorySleepMode=deep")) \
                and "etc/systemd/system/multi-user.target.wants/h713-power.service" in parts
        else:
            good = b"AllowSuspend=no" in sleep.split(b"\n") and "etc/systemd/system/multi-user.target.wants/h713-power.service" not in parts
        mode = "--standby" if o.standby else "no standby"
        check(good, "rootfs sleep.conf.d and h713-power fit " + mode,
              "rootfs sleep.conf.d/h713-power do not fit %s - a rootfs of another build?" % mode)
        wd = watchdog(parts)
        if wd and (bl31 is None or T1_MARK not in bl31):
            fail("rootfs arms the watchdog (%s), BL31 has no reset that feeds it first: every reboot would hang" % ", ".join(wd))
        elif wd:
            ok("rootfs arms the watchdog, BL31 has the feeding reset")
    if word is not None:
        print("build word 0x%08x (%s)" % (word, " ".join(BITS[b][5:].lower() for b in sorted(BITS) if word >> b & 1) or "-"))
    print("note  not in this repository yet: the contract checkers H3/H4 and the objdump check of BL31's feeding reset")
    print("crust gate: %s" % ("green" if fails == 0 else "%d failure(s) - do not release" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, tarfile.TarError) as e:    # an input that is missing or not what it claims
        print("  FAIL  %s\ncrust gate: do not release" % e)
        sys.exit(1)
