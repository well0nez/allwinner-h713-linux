#!/usr/bin/env python3
"""check-display.py -- do the U-Boot environment and the rootfs agree on the two display stacks?

docs/subsystems/display-stacks.md: the environment key h713_display picks the stack per boot, vendor by default.
This gate judges the ARTEFACTS: release/build-all.sh runs it in step 10 with the release environment image, the
rootfs tar, the kernel defconfig and the built kernel's .config.

  release/check-display.py --env hy310-env-release.bin --rootfs hy310-rootfs.tar \
      --defconfig mainline/patches/kernel/board/hy200_qz713df_a1_defconfig --kernel-config <kernel tree>/.config
  release/check-display.py --env mainline/external/u-boot/board/sunxi/hy310.env [--define CONFIG_CONSOLE_RECORD]
                                                                                   (the source, before a build)

--env takes the 64 KiB image (CRC), U-Boot's u-boot-initial-env (k=v lines) or a board .env source (its #ifdef lines
taken with the --define symbols set, then joined the way scripts/env2string.awk joins it). The boot command is run in
a small model of U-Boot's hush (if/then/else/fi, test,
setenv, run; ext4load and the rest succeed, bootm ends the boot) for every h713_display (unset, vendor, clean,
something else) on both boot paths, and what it does must be: clean = `h713_disp init <project> noboot logo` and the
kernel refusing the five firmware drivers with the word userspace reads; anything else = today's `h713_disp init
<project> logo` and the kernel refusing h713_drm. The two stacks' command lines may differ in those words only. The
rootfs must carry the other half: h713-display (its word and module name the environment's), its unit run on that word
only, the units that talk to the firmware skipped on it, h713_drm's firmware through /boot/mips, every blacklisted name
a module the image has, and an h713_drm, where the image has one, built for the image's kernel. The installer must
carry h713_display over. When the defconfig asks for CONFIG_RUST=y / CONFIG_DRM_H713=m, the built .config must carry
them and the rootfs must carry h713_drm for its kernel - kconfig drops both without a word when the build container
has no Rust toolchain. Exit 0 = may be released, 1 = do not release.
"""
import argparse
import os
import re
import struct
import sys
import tarfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "h713_display"
MARK = "h713.display=clean"
CLEAN_REFUSED = ("hy310_cpu_comm", "sun50i_h713_hdmirx", "sun50i_h713_mips", "sun50i_h713_msp", "sun50i_h713_afbd")
MODULE = "h713_drm"
PROVIDER = "sun50i_h713_arisc"
SKIPPED_ON_CLEAN = ("h713-hdcp-key.service", "h713-tv-rescue.service", "h713-sleep-pre.service", "h713-sleep-post.service")
KCONFIG_WANTED = ("CONFIG_RUST=y", "CONFIG_DRM_H713=m")
fails = 0


def ok(msg):
    print("  ok    " + msg)


def fail(msg):
    global fails
    fails += 1
    print("  FAIL  " + msg)


def note(msg):
    print("  note  " + msg)


def check(good, ok_msg, fail_msg):
    (ok if good else fail)(ok_msg if good else fail_msg)
    return good


# --- the environment ---------------------------------------------------------------------------------------------

def env_source(text, defined=()):
    """A board .env file as U-Boot's build makes it: the preprocessor's #ifdef/#ifndef/#else/#endif with DEFINED as
    the CONFIG_ symbols that are set, C comments out; then scripts/env2string.awk: a line that starts with NAME= starts
    a variable, any other line is appended with its leading blanks dropped and one space in front."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    out, var, live = {}, None, []
    for line in text.splitlines():
        d = re.match(r"^\s*#\s*(ifdef|ifndef|else|endif)\b\s*(\w*)", line)
        if d:
            if d.group(1) in ("ifdef", "ifndef"):
                live.append((d.group(2) in defined) == (d.group(1) == "ifdef"))
            elif d.group(1) == "else":
                live[-1] = not live[-1]
            else:
                live.pop()
            continue
        if line.lstrip().startswith("#"):
            raise ValueError("a preprocessor line this model does not take: %r" % line.strip())
        if not all(live) or not line.strip():
            continue
        m = re.match(r"^([^ \t=][^ =]*)=(.*)$", line)
        if m:
            var = m.group(1)
            out[var] = m.group(2)
        elif var is not None:
            rest = line.lstrip(" \t")
            out[var] = rest if not out[var] else out[var] + " " + rest
    return {k: v for k, v in out.items() if v}


def env_load(path, defined=()):
    with open(path, "rb") as f:
        data = f.read()
    if len(data) == 0x10000 and struct.unpack("<I", data[:4])[0] == zlib.crc32(data[4:]) & 0xffffffff:
        out = {}
        for e in data[4:].split(b"\0"):
            if not e:
                break
            k, _, v = e.decode("utf-8", "replace").partition("=")
            out[k] = v                      # the last entry wins, as U-Boot's import does
        return out
    text = data.decode("utf-8", "replace")
    if path.endswith(".env"):
        return env_source(text, defined)
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def split_top(script):
    """Hush's statements: split at ; outside quotes, the quotes kept."""
    out, cur, q = [], "", None
    for c in script:
        if q:
            q = None if c == q else q
        elif c in "\"'":
            q = c
        elif c == ";":
            out.append(cur.strip())
            cur = ""
            continue
        cur += c
    out.append(cur.strip())
    return [s for s in out if s]


def words(stmt, env):
    """One statement's words, ${var} expanded once and the quotes removed (hush expands one level)."""
    out, cur, q, have = [], "", None, False
    i = 0
    while i < len(stmt):
        c = stmt[i]
        if c == "$" and stmt[i + 1:i + 2] == "{" and q != "'":
            j = stmt.index("}", i)
            cur += env.get(stmt[i + 2:j], "")
            have = True
            i = j + 1
            continue
        if q:
            if c == q:
                q = None
            else:
                cur += c
        elif c in "\"'":
            q, have = c, True
        elif c in " \t":
            if cur or have:
                out.append(cur)
            cur, have = "", False
        else:
            cur += c
        i += 1
    if cur or have:
        out.append(cur)
    return out


class Booted(Exception):
    pass


class Hush:
    """Runs a boot script; records every h713_disp, where h713_conlog ran (the number of h713_disp before it) and the
    bootargs bootm boots with."""

    def __init__(self, env):
        self.env = dict(env)
        self.disp = []
        self.conlog = []
        self.bootargs = None
        self.depth = 0

    def run_script(self, script):
        stmts = split_top(script)
        self.block(stmts, 0, len(stmts))

    def block(self, s, i, end):
        rc = True
        while i < end:
            first = s[i].split(None, 1)
            if first and first[0] == "if":
                cond = s[i][2:].strip()
                j, depth, then_at, else_at = i + 1, 0, None, None
                while j < end:
                    w = s[j].split(None, 1)[0]
                    if w == "if":
                        depth += 1
                    elif w == "fi":
                        if depth == 0:
                            break
                        depth -= 1
                    elif depth == 0 and w == "then" and then_at is None:
                        then_at = j
                    elif depth == 0 and w == "else":
                        else_at = j
                    j += 1
                if j >= end or then_at != i + 1:
                    raise ValueError("if without then/fi in %r" % "; ".join(s[i:end]))
                s = list(s)
                s[then_at] = s[then_at][4:].strip() or ":"
                if else_at is not None:
                    s[else_at] = s[else_at][4:].strip() or ":"
                if self.command(words(cond, self.env)):
                    rc = self.block(s, then_at, else_at if else_at is not None else j)
                elif else_at is not None:
                    rc = self.block(s, else_at, j)
                i = j + 1
                continue
            rc = self.command(words(s[i], self.env))
            i += 1
        return rc

    def command(self, w):
        if not w or w[0] == ":":
            return True
        if w[0] == "test":
            if len(w) == 4 and w[2] == "=":
                return w[1] == w[3]
            if len(w) == 3 and w[1] == "-n":
                return bool(w[2])
            raise ValueError("test %r: not in the model" % w[1:])
        if w[0] == "setenv":
            if len(w) == 2:
                self.env.pop(w[1], None)
            else:
                self.env[w[1]] = " ".join(w[2:])
            return True
        if w[0] == "run":
            for name in w[1:]:
                if name not in self.env:
                    return False
                self.depth += 1
                if self.depth > 8:
                    raise ValueError("run nests deeper than 8")
                self.run_script(self.env[name])
                self.depth -= 1
            return True
        if w[0] == "h713_disp":
            self.disp.append(w[1:])
            return True
        if w[0] == "h713_conlog":
            self.conlog.append(len(self.disp))
            return True
        if w[0] == "bootm":
            self.bootargs = self.env.get("bootargs", "")
            raise Booted()
        return True                          # ext4load, dhcp, tftpboot, mmc, saveenv: they succeed


def run_boot(env, display, path):
    """The Hush that ran bootcmd with h713_display=DISPLAY (None: unset) and h713_boot=PATH, up to bootm."""
    e = dict(env)
    e.pop(KEY, None)
    if display is not None:
        e[KEY] = display
    e["h713_boot"] = path
    h = Hush(e)
    try:
        h.run_script(e.get("bootcmd", ""))
    except Booted:
        pass
    return h


def boot(env, display, path):
    h = run_boot(env, display, path)
    return h.disp, h.bootargs


def check_env(env):
    print("environment: %d entries, %s=%s" % (len(env), KEY, env.get(KEY, "-")))
    check(env.get(KEY) == "vendor", "default %s=vendor" % KEY, "default %s is %r, not vendor" % (KEY, env.get(KEY)))
    project = env.get("h713_project", "")
    clean_bl = "module_blacklist=" + ",".join(CLEAN_REFUSED)
    for path in ("emmc", "net"):
        lines = {}
        for display in (None, "vendor", "clean", "Clean"):
            try:
                h = run_boot(env, display, path)
                disp, args = h.disp, h.bootargs
            except ValueError as e:
                fail("bootcmd with %s=%s on boot_%s: %s" % (KEY, display, path, e))
                continue
            name = "%s=%s" % (KEY, display) if display is not None else "%s unset" % KEY
            if args is None:
                fail("%s, boot_%s: bootm never reached" % (name, path))
                continue
            w = args.split()
            bl = [x for x in w if x.startswith("module_blacklist=")]
            if display == "clean":
                good = disp == [["init", project, "noboot", "logo"]]
                check(good and MARK in w and bl == [clean_bl],
                      "%s, boot_%s: h713_disp init %s noboot logo, %s %s" % (name, path, project, MARK, clean_bl),
                      "%s, boot_%s: h713_disp %s, kernel %s - wanted init %s noboot logo, %s and %s"
                      % (name, path, disp, " ".join(bl + [x for x in w if x == MARK]) or "no display words", project, MARK, clean_bl))
                rest = [x for x in w if x not in (MARK, clean_bl)]
            else:
                good = disp == [["init", project, "logo"]]
                check(good and MARK not in w and bl == ["module_blacklist=" + MODULE],
                      "%s, boot_%s: h713_disp init %s logo, module_blacklist=%s" % (name, path, project, MODULE),
                      "%s, boot_%s: h713_disp %s, kernel %s - the vendor stack is init %s logo and module_blacklist=%s"
                      % (name, path, disp, " ".join(bl + [x for x in w if x == MARK]) or "no display words", project, MODULE))
                rest = [x for x in w if x != "module_blacklist=" + MODULE]
            lines[display] = rest
            if h.conlog:
                check(h.conlog == [1], "%s, boot_%s: h713_conlog after the display init" % (name, path),
                      "%s, boot_%s: h713_conlog ran %s - wanted once, after the display init" % (
                          name, path, ", ".join("after %d h713_disp" % n for n in h.conlog)))
        if len({tuple(v) for v in lines.values()}) > 1:
            fail("boot_%s: the stacks' command lines differ beyond the display words: %s" % (
                path, "; ".join("%s: %s" % (k, " ".join(v)) for k, v in lines.items())))
        elif lines:
            ok("boot_%s: vendor and clean differ in the display words only" % path)


# --- the rootfs --------------------------------------------------------------------------------------------------

def rootfs(path):
    """{path: bytes or ('link', target)} of the members this gate reads; usr/lib as lib."""
    want = re.compile(r"etc/systemd/system/[^/]+\.service|etc/systemd/system/sysinit\.target\.wants/[^/]+|"
                      r"(etc|(usr/)?lib)/modprobe\.d/[^/]+\.conf|(usr/)?lib/firmware/h713-mips|"
                      r"(usr/)?lib/modules/[^/]+/modules\.dep|usr/local/sbin/h713-display")
    ko = re.compile(r"(usr/)?lib/modules/[^/]+/.*/(%s|%s)\.ko(\.xz|\.gz)?" % (MODULE, "sun50i[-_]h713[-_]arisc"))
    out = {}
    with tarfile.open(path) as t:
        for m in t:
            name = re.sub(r"^\./", "", m.name)
            if not (want.fullmatch(name) or ko.fullmatch(name)):
                continue
            name = re.sub(r"^usr/lib/", "lib/", name)
            if m.issym() or m.islnk():
                out[name] = ("link", m.linkname)
            elif m.isfile():
                out[name] = t.extractfile(m).read()
    return out


def vermagic(data, name):
    import gzip
    import lzma
    data = lzma.decompress(data) if name.endswith(".xz") else gzip.decompress(data) if name.endswith(".gz") else data
    m = re.search(rb"(?:^|\0)vermagic=([^\0]*)\0", data)
    return m.group(1).decode(errors="replace") if m else None


def unit(parts, name):
    v = parts.get("etc/systemd/system/" + name)
    return v.decode(errors="replace") if isinstance(v, bytes) else None


def config_lines(path):
    """The CONFIG_X=... lines of a defconfig or .config."""
    with open(path) as f:
        return {l.strip() for l in f if l.startswith("CONFIG_")}


def check_kernel_config(defconfig, kconfig):
    """Does the built kernel carry what the defconfig asks for the clean stack? True when it asks for h713_drm."""
    want = [l for l in KCONFIG_WANTED if l in config_lines(defconfig)]
    if not want:
        note("%s asks for none of %s: an image without h713_drm" % (os.path.basename(defconfig), ", ".join(KCONFIG_WANTED)))
        return False
    if kconfig is None:
        fail("%s asks for %s, but no --kernel-config to hold the built kernel against" % (os.path.basename(defconfig),
                                                                                         ", ".join(want)))
    else:
        lost = [l for l in want if l not in config_lines(kconfig)]
        check(not lost, "the kernel's .config carries %s" % ", ".join(want),
              "the kernel's .config lacks %s, which %s asks for: kconfig dropped it (CONFIG_RUST without the build "
              "container's Rust toolchain?)" % (", ".join(lost), os.path.basename(defconfig)))
    return "CONFIG_DRM_H713=m" in want


def check_rootfs(parts, need_drm=False):
    tool = parts.get("usr/local/sbin/h713-display")
    if check(isinstance(tool, bytes), "rootfs carries h713-display", "rootfs carries no /usr/local/sbin/h713-display"):
        t = tool.decode(errors="replace")
        check('MARK = "%s"' % MARK in t and 'MODULE = "%s"' % MODULE in t and 'KEY = "%s"' % KEY in t,
              "h713-display reads %s and %s, loads %s" % (KEY, MARK, MODULE),
              "h713-display's KEY/MARK/MODULE are not %s/%s/%s" % (KEY, MARK, MODULE))
    u = unit(parts, "h713-display.service")
    if check(u is not None, "rootfs carries h713-display.service", "rootfs carries no h713-display.service"):
        check(re.search(r"^ConditionKernelCommandLine=%s$" % re.escape(MARK), u, re.M) is not None
              and "ExecStart=/usr/local/sbin/h713-display load" in u,
              "h713-display.service runs 'h713-display load' on %s only" % MARK,
              "h713-display.service lacks ConditionKernelCommandLine=%s or its ExecStart" % MARK)
        link = parts.get("etc/systemd/system/sysinit.target.wants/h713-display.service")
        check(isinstance(link, tuple) and link[1].endswith("/h713-display.service"), "h713-display.service linked (sysinit)",
              "h713-display.service is not linked into sysinit.target.wants: the clean stack would boot without h713_drm")
    for name in SKIPPED_ON_CLEAN:
        u = unit(parts, name)
        if u is None:
            note("no %s in this rootfs" % name)
            continue
        check(re.search(r"^ConditionKernelCommandLine=!%s$" % re.escape(MARK), u, re.M) is not None,
              "%s skipped on the clean stack" % name,
              "%s has no ConditionKernelCommandLine=!%s: it would reach for the MIPS on the clean stack" % (name, MARK))
    opts = {}
    for k in sorted(k for k in parts if "/modprobe.d/" in k):
        for line in parts[k].decode(errors="replace").splitlines():
            w = line.split("#", 1)[0].split()
            if w[:2] in (["options", MODULE], ["options", MODULE.replace("_", "-")]):
                opts.update(x.split("=", 1) for x in w[2:] if "=" in x)
            if w[:2] in (["blacklist", MODULE], ["install", MODULE]):
                fail("%s: '%s' - the clean stack's own modprobe would be refused" % (k, " ".join(w)))
    fw = [opts.get(p) for p in ("fw", "pq_fw", "gamma_fw")]
    link = parts.get("lib/firmware/h713-mips")
    check(all(f and f.startswith("h713-mips/") for f in fw) and link == ("link", "/boot/mips"),
          "h713_drm reads its display files from /boot/mips (%s; /lib/firmware/h713-mips -> /boot/mips)" % ", ".join(fw),
          "h713_drm's firmware %s, /lib/firmware/h713-mips %s: wanted h713-mips/* and a link to /boot/mips"
          % (fw, link[1] if isinstance(link, tuple) else "missing"))
    check(opts.get("edid_fw") == "hy310-edid.bin", "h713_drm serves /lib/firmware/hy310-edid.bin",
          "h713_drm edid_fw=%s, not the installer's hy310-edid.bin" % opts.get("edid_fw"))
    deps = {k.split("/")[2]: v.decode(errors="replace") for k, v in parts.items()
            if k.startswith("lib/modules/") and k.endswith("/modules.dep") and isinstance(v, bytes)}
    if not deps:
        fail("rootfs carries no lib/modules/*/modules.dep")
    for rel, dep in sorted(deps.items()):
        names = {re.sub(r"\.ko(\.\w+)?$", "", os.path.basename(l.split(":", 1)[0])).replace("-", "_")
                 for l in dep.splitlines() if ":" in l}
        missing = [n for n in CLEAN_REFUSED if n not in names]
        check(not missing, "%s: the five names the clean stack refuses are modules of this kernel" % rel,
              "%s: the clean stack refuses %s, which this kernel has no module of: a renamed driver would load"
              % (rel, ", ".join(missing)))
        drm = [k for k in parts if k.startswith("lib/modules/%s/" % rel) and re.search(r"/%s\.ko" % MODULE, k)]
        arisc = [k for k in parts if k.startswith("lib/modules/%s/" % rel) and re.search(r"/sun50i[-_]h713[-_]arisc\.ko", k)]
        if MODULE not in names or not drm:
            if need_drm:
                fail("%s carries no %s, but the kernel's defconfig builds it (CONFIG_DRM_H713=m): the clean stack would "
                     "be refused on this image" % (rel, MODULE))
            else:
                note("%s carries no %s: h713-display set clean refuses on this kernel (CONFIG_DRM_H713 needs CONFIG_RUST)"
                     % (rel, MODULE))
            continue
        vm = vermagic(parts[drm[0]], drm[0])
        avm = vermagic(parts[arisc[0]], arisc[0]) if arisc else None
        check(vm is not None and vm.split()[0] == rel and (avm is None or vm == avm),
              "%s: %s built for this kernel (%s)" % (rel, MODULE, vm),
              "%s: %s vermagic %r, %s %r: it would not load" % (rel, MODULE, vm, PROVIDER, avm))


def check_installer():
    sys.path.insert(0, os.path.join(ROOT, "installer"))
    try:
        from h713.env import ENV_CARRY_OVER
    except ImportError as e:
        fail("installer/h713/env.py not importable: %s" % e)
        return
    check(KEY in ENV_CARRY_OVER, "the installer carries %s over" % KEY,
          "installer/h713/env.py ENV_CARRY_OVER lacks %s: a reinstall would drop the choice" % KEY)


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("--env", required=True)
    a.add_argument("--rootfs")
    a.add_argument("--define", action="append", default=[], metavar="CONFIG_X",
                   help="a CONFIG_ symbol set for a .env source's #ifdef (the board base's, e.g. CONFIG_CONSOLE_RECORD)")
    a.add_argument("--defconfig", help="the kernel defconfig of the image (patches/kernel/board/<KERNEL_DEFCONFIG>)")
    a.add_argument("--kernel-config", help="the .config of the kernel tree the image's kernel and modules come from")
    o = a.parse_args(argv)
    check_env(env_load(o.env, o.define))
    need_drm = check_kernel_config(o.defconfig, o.kernel_config) if o.defconfig else False
    if o.rootfs:
        check_rootfs(rootfs(o.rootfs), need_drm)
    else:
        note("no --rootfs: the userspace half not judged")
    check_installer()
    print("display gate: %s" % ("green" if fails == 0 else "%d failure(s) - do not release" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, tarfile.TarError) as e:
        print("  FAIL  %s\ndisplay gate: do not release" % e)
        sys.exit(1)
