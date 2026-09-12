#!/usr/bin/env python3
"""
uart-uboot.py -- am U-Boot-Prompt arbeiten, ohne den Kernel zu starten.

Ergaenzt uart-capture.py um die drei Dinge, die fuer den CPU_COMM-Versuch
fehlen: den Prompt beim Kaltstart abfangen, Firmware-Speicher am Stueck
lesen, und den MIPS-elog daraus dekodieren.

  ./uart-uboot.py catch                     Strg-C hammern bis '=> ', dann anhalten
  ./uart-uboot.py run -c 'h713_disp commdev' -c 'h713_disp calltable 8'
  ./uart-uboot.py fwdump 0x8b272d9c 4096 -o /tmp/ring.bin
  ./uart-uboot.py elog                      Zeiger lesen, Ring holen, als Text
  ./uart-uboot.py chanpid                   chan/pid/id fuer commcall herausziehen

Eine laufende tio-Sitzung vorher beenden (Strg-t q).

Reihenfolge fuer den Vp_Init-Versuch, HDMI gesteckt:

  1. ./uart-uboot.py catch          -- dann Strom ziehen und wieder anstecken
  2. => h713_disp init 0x30 elog=3  -- EINMAL pro Stromzyklus
  3. ./uart-uboot.py chanpid
  4. => h713_disp commcall 1c6ff747 chan=<c> pid=<p> 0 0 4e700000
  5. ./uart-uboot.py elog

Para[2] MUSS eine gueltige Staging-Phys sein (0x4E700000 = SHMEM+4 MiB).
Para[2]=0 laesst die MIPS ein NULL-memcpy ueber 55296 Byte machen und
reisst die Firmware mit -- Session Z, 05.05.2026, siehe DEAD-ENDS.md.

NIEMALS 0152f134 (THal_Vp_EnableScreenCover) rufen: wedgt CPU_COMM, danach
hilft nur ein Stromzyklus.
"""
import argparse, os, re, select, struct, sys, time
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
uc = SourceFileLoader("uc", os.path.join(HERE, "uart-capture.py")).load_module()

PROMPT = uc.PROMPT

# elog Modus 1, aus doku/63-mips-elog.md. Alles MIPS-VA; fwmd will KSEG.
ELOG_RING_VA = 0x8B272D9C
ELOG_RING_SIZE = 102400
ELOG_WRITE_VA = 0x8B48C2A8
ELOG_READ_VA = 0x8B48C2A4
ELOG_OVERFLOW_VA = 0x8B48C2A1
ELOG_ENABLE_VA = 0x8B48C2AC
ELOG_MODE_VA = 0x8B48BE9B

FWMD_MAX_WORDS = 256  # h713_disp_fw_md klemmt darueber auf 16

# Beweise, dass die Kiste wirklich neu gestartet ist. Ohne diese Pruefung
# meldet catch auch dann Erfolg, wenn der Prompt vom letzten Mal noch steht --
# und der naechste 'h713_disp init' waere der zweite im selben Stromzyklus.
COLD_MARKERS = (b"U-Boot SPL", b"DRAM:", b"Hit any key", b"eGON", b"Loading Environment")


def port_path(arg=None):
    if arg:
        return arg
    return uc.PORT_BYID if os.path.exists(uc.PORT_BYID) else uc.PORT_FALLBACK


def send(fd, cmd, timeout=8.0, idle=0.6):
    """Einen Befehl absetzen und die Antwort ohne Echo/Prompt zurueckgeben."""
    os.write(fd, cmd.encode() + b"\r")
    raw, ok = uc.read_until(fd, PROMPT, timeout, idle)
    text = raw.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and cmd.split()[0] in lines[0]:
        lines = lines[1:]
    body = "\n".join(l for l in lines if l.strip() and l.strip() != "=>")
    return body.rstrip(), ok


def expect_prompt(fd, tries=3):
    """Ein Enter, und schauen ob wirklich U-Boot antwortet."""
    for _ in range(tries):
        os.write(fd, b"\r")
        raw, ok = uc.read_until(fd, PROMPT, 2.0, 0.5)
        if ok:
            return True
        if b"root@" in raw or b"$ " in raw:
            sys.exit("Das ist Linux, nicht U-Boot. Erst 'catch' und Strom ziehen.")
    return False


# --------------------------------------------------------------------------
# catch -- den Prompt beim Kaltstart abfangen, ohne bootcmd zu starten
# --------------------------------------------------------------------------

def cmd_catch(a):
    fd = uc.open_port(port_path(a.port), a.baud)
    print("Warte auf Kaltstart -- jetzt Strom ziehen und wieder anstecken.")
    print("(hammert Strg-C, haelt am '=> '-Prompt an)\n")
    sys.stdout.flush()

    acc = b""
    warned = False
    deadline = time.monotonic() + a.timeout
    while time.monotonic() < deadline:
        os.write(fd, b"\x03")
        r, _, _ = select.select([fd], [], [], 0.12)
        if r:
            try:
                acc += os.read(fd, 8192)
            except BlockingIOError:
                pass
        if not acc.rstrip().endswith(b"=>"):
            continue

        if any(k in acc for k in COLD_MARKERS):
            print(acc.decode("utf-8", "replace")[-1500:])
            print("\nKaltstart bestaetigt, U-Boot-Prompt steht.")
            os.close(fd)
            return 0

        # Kein Kaltstart-Beleg: das ist der Prompt von vorher.
        if not warned:
            print("Ein Prompt steht bereits -- das ist der alte, kein Kaltstart.\n"
                  "Warte weiter auf den Stromzyklus (Strg-C laeuft weiter).\n")
            sys.stdout.flush()
            warned = True
        # Puffer leeren, sonst passt das alte '=>' bis zum Timeout weiter.
        acc = b""

    print("KEIN Prompt in %.0f s. Roh gelesen (letzte 800 Zeichen):" % a.timeout)
    print(acc.decode("utf-8", "replace")[-800:])
    os.close(fd)
    return 1


# --------------------------------------------------------------------------
# run -- Befehle am stehenden Prompt
# --------------------------------------------------------------------------

def cmd_run(a):
    cmds = list(a.cmd)
    if a.file:
        with open(a.file) as fh:
            cmds += [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    if not cmds:
        sys.exit("Nichts zu tun -- -c oder -f angeben.")

    fd = uc.open_port(port_path(a.port), a.baud)
    if not expect_prompt(fd):
        print("WARNUNG: kein '=> '-Prompt gesehen, sende trotzdem.\n")

    log = []
    for cmd in cmds:
        body, ok = send(fd, cmd, a.timeout, a.idle)
        print("=> %s%s" % (cmd, "" if ok else "   [TIMEOUT]"))
        if body:
            print(body)
        print()
        sys.stdout.flush()
        log += ["=> %s" % cmd, body, ""]
    os.close(fd)

    if a.out:
        with open(a.out, "w") as fh:
            fh.write("\n".join(log) + "\n")
        print("Geschrieben: %s" % a.out)
    return 0


# --------------------------------------------------------------------------
# fwdump -- Firmware-Speicher am Stueck, ueber h713_disp fwmd
# --------------------------------------------------------------------------

WORD_RE = re.compile(rb"0x([0-9a-fA-F]{8}):((?:\s+[0-9a-fA-F]{8})+)")


def parse_fwmd(text):
    """fwmd-Ausgabe -> {va: wort}. Zeilen sind '0x8b...: w w w w w w'."""
    out = {}
    for m in WORD_RE.finditer(text.encode() if isinstance(text, str) else text):
        va = int(m.group(1), 16)
        for i, w in enumerate(m.group(2).split()):
            out[va + i * 4] = int(w, 16)
    return out


def fw_read(fd, va, nbytes, progress=True):
    """nbytes ab MIPS-VA va lesen. Rueckgabe: bytes (little-endian entpackt)."""
    words = (nbytes + 3) // 4
    got = {}
    done = 0
    while done < words:
        n = min(FWMD_MAX_WORDS, words - done)
        addr = va + done * 4
        body, ok = send(fd, "h713_disp fwmd 0x%08x 0x%x" % (addr, n),
                        timeout=20.0, idle=0.8)
        if "not a KSEG" in body:
            sys.exit("fwmd lehnt 0x%08x ab -- keine KSEG-Adresse." % addr)
        chunk = parse_fwmd(body)
        if not chunk:
            sys.exit("fwmd lieferte keine Woerter bei 0x%08x:\n%s" % (addr, body))
        got.update(chunk)
        done += n
        if progress:
            sys.stderr.write("\r  %6.1f%%  %d/%d Woerter" %
                             (100.0 * done / words, done, words))
            sys.stderr.flush()
    if progress:
        sys.stderr.write("\n")

    # Der ARM liest die Woerter little-endian; Byte 0 ist das niederwertigste.
    buf = bytearray()
    for i in range(words):
        buf += struct.pack("<I", got.get(va + i * 4, 0))
    return bytes(buf[:nbytes])


def cmd_fwdump(a):
    fd = uc.open_port(port_path(a.port), a.baud)
    if not expect_prompt(fd):
        sys.exit("Kein U-Boot-Prompt.")
    data = fw_read(fd, int(a.va, 16), int(a.size, 0))
    os.close(fd)
    if a.out:
        with open(a.out, "wb") as fh:
            fh.write(data)
        print("%d Bytes -> %s" % (len(data), a.out))
    else:
        sys.stdout.write(data.decode("utf-8", "replace"))
    return 0


# --------------------------------------------------------------------------
# elog -- Zeiger lesen, den benutzten Teil des Rings holen, als Text ausgeben
# --------------------------------------------------------------------------

def cmd_elog(a):
    fd = uc.open_port(port_path(a.port), a.baud)
    if not expect_prompt(fd):
        sys.exit("Kein U-Boot-Prompt.")

    # Mode-, Enable- und Overflow-Flag liegen als Bytes in Woertern.
    hdr = fw_read(fd, ELOG_READ_VA & ~3, 16, progress=False)
    words = struct.unpack("<4I", hdr)
    read_ofs = words[(ELOG_READ_VA - (ELOG_READ_VA & ~3)) // 4]
    write_ofs = words[(ELOG_WRITE_VA - (ELOG_READ_VA & ~3)) // 4]
    # Enable ist ein BYTE, nicht das Wort -- als Wort gelesen kommt 0x01010101
    # heraus und sieht wie Unsinn aus.
    enable = hdr[ELOG_ENABLE_VA - (ELOG_READ_VA & ~3)]

    mode_w = fw_read(fd, ELOG_MODE_VA & ~3, 4, progress=False)
    mode = mode_w[ELOG_MODE_VA & 3]
    ovf_w = fw_read(fd, ELOG_OVERFLOW_VA & ~3, 4, progress=False)
    overflow = ovf_w[ELOG_OVERFLOW_VA & 3]

    print("elog: mode=%d enable=%d overflow=%d  read=%d write=%d"
          % (mode, enable, overflow, read_ofs, write_ofs))
    if a.ptrs:
        os.close(fd)
        return 0
    if mode != 1:
        print("WARNUNG: Modus %d, nicht 1. Die Adressen hier gelten fuer Modus 1." % mode)
    if overflow:
        print("WARNUNG: Overflow gesetzt -- die Firmware hat aufgehoert zu loggen.")
    if not write_ofs or write_ofs > ELOG_RING_SIZE:
        print("Nichts im Ring (write=%d)." % write_ofs)
        os.close(fd)
        return 1

    n = min(write_ofs, a.max_bytes) if a.max_bytes else write_ofs
    start = ELOG_RING_VA + (write_ofs - n)
    print("hole %d Byte ab 0x%08x ...\n" % (n, start))
    data = fw_read(fd, start, n)
    os.close(fd)

    text = data.decode("utf-8", "replace")
    if a.out:
        with open(a.out, "w") as fh:
            fh.write(text)
        print("Geschrieben: %s (%d Byte)" % (a.out, len(data)))
    if a.grep:
        pat = re.compile(a.grep)
        for line in text.split("\n"):
            if pat.search(line):
                print(line)
    elif not a.out:
        sys.stdout.write(text)
    return 0


# --------------------------------------------------------------------------
# chanpid -- die drei Zahlen holen, die commcall braucht
# --------------------------------------------------------------------------

ENTRY_RE = re.compile(r"entry\s+(\d+)\s+id\s+([0-9a-f]{8})\s+handler\s+([0-9a-f]{8})\s+(\S+)")
RAW_RE = re.compile(r"entry\s+(\d+) raw:")


def cmd_chanpid(a):
    fd = uc.open_port(port_path(a.port), a.baud)
    if not expect_prompt(fd):
        sys.exit("Kein U-Boot-Prompt.")

    dev, _ = send(fd, "h713_disp commdev", timeout=15.0, idle=1.0)
    print("=> h713_disp commdev")
    print(dev + "\n")

    tbl, _ = send(fd, "h713_disp calltable %d" % a.raw, timeout=45.0, idle=1.5)
    os.close(fd)
    print("=> h713_disp calltable %d" % a.raw)
    print(tbl + "\n")

    if "not populated" in tbl:
        sys.exit("Die Call-Tabelle ist leer -- lief 'h713_disp init 0x30' auf DIESEM Boot?")

    entries = ENTRY_RE.findall(tbl)
    print("--- %d benannte Eintraege ---" % len(entries))
    want = ("THal_Vp_Init", "THal_Vp_SetSource", "GetImageBufferAddr",
            "RegisterSignalChange", "SetHDMIHotPlug", "HDMI_SetPortMap")
    for _i, rid, _h, name in entries:
        if any(w in name for w in want):
            print("  %-46s id %s" % (name, rid))

    # pid steht im Roh-Dump bei +0x04.
    pid = None
    for m in re.finditer(r"\+0x00:((?:\s+[0-9a-f]{8})+)", tbl):
        w = m.group(1).split()
        if len(w) > 1 and w[1] != "00000000":
            pid = w[1]
            break
    print("\npid (aus +0x04): %s" % (pid or "nicht gefunden -- --raw erhoehen"))
    print("chan: aus der commdev-Ausgabe oben ablesen")
    print("\nDann, HDMI gesteckt:")
    print("  h713_disp commcall 1c6ff747 chan=<c> pid=%s 0 0 4e700000" % (pid or "<p>"))
    return 0


# --------------------------------------------------------------------------
# vpinit -- der ganze Vp_Init-Versuch, mit Trockenlauf als Voreinstellung
# --------------------------------------------------------------------------

VP_INIT_ID = "1c6ff747"          # THal_Vp_Init_1_000
VP_INIT_STAGING = "4e700000"     # SHMEM + 4 MiB, siehe Session Z

# Nach einem manuellen init darf bootcmd NICHT laufen -- es wuerde init ein
# zweites Mal ausfuehren, und das gilt als ein Start pro Stromzyklus.
NETBOOT_ONLY = ("dhcp; tftpboot 0x60000000 192.168.8.104:${bootfile}; "
                "bootm 0x60000000")


def cmd_vpinit(a):
    fd = uc.open_port(port_path(a.port), a.baud)
    if not expect_prompt(fd):
        sys.exit("Kein U-Boot-Prompt -- erst 'catch' und Strom ziehen.")

    print("=== 1. Firmware starten (EINMAL pro Stromzyklus) ===")
    body, ok = send(fd, "h713_disp init 0x%s elog=%d" % (a.project, a.elog),
                    timeout=90.0, idle=3.0)
    print(body + "\n")
    if "CPU_COMM magic=deadbeef" not in body:
        print("WARNUNG: kein 'CPU_COMM magic=deadbeef' gesehen.")
        if not a.force:
            os.close(fd)
            sys.exit("Abbruch. --force ueberspringt diese Pruefung.")

    print("=== 2. Kanaltabelle ===")
    dev, _ = send(fd, "h713_disp commdev", timeout=20.0, idle=1.0)
    print(dev + "\n")
    tbl, _ = send(fd, "h713_disp calltable %d" % a.raw, timeout=60.0, idle=2.0)
    print(tbl + "\n")

    if "not populated" in tbl:
        os.close(fd)
        sys.exit("Call-Tabelle leer -- die Firmware hat sie auf diesem Boot nicht gefuellt.")

    pid = a.pid
    if not pid:
        for m in re.finditer(r"\+0x00:((?:\s+[0-9a-f]{8})+)", tbl):
            w = m.group(1).split()
            if len(w) > 1 and w[1] != "00000000":
                pid = w[1]
                break
    chan = a.chan
    if not chan:
        m = re.search(r"chan\s*=?\s*(?:0x)?([0-9a-f]+)", dev, re.I)
        chan = m.group(1) if m else None

    names = {n: i for _e, i, _h, n in ENTRY_RE.findall(tbl)}
    vp = next((i for n, i in names.items() if n.startswith("THal_Vp_Init")), None)
    if vp and vp != VP_INIT_ID:
        print("Hinweis: die Tabelle nennt THal_Vp_Init als id %s, "
              "erwartet war %s -- nehme die Tabelle." % (vp, VP_INIT_ID))
    rid = vp or VP_INIT_ID

    call = "h713_disp commcall %s%s%s 0 0 %s" % (
        rid,
        " chan=%s" % chan if chan else "",
        " pid=%s" % pid if pid else "",
        VP_INIT_STAGING)

    print("=== 3. Der Aufruf ===")
    print("  " + call)
    print("  ParaCount=3, Para[2]=0x%s (Staging). Para[2]=0 wuerde die "
          "Firmware zerlegen." % VP_INIT_STAGING)
    if not chan or not pid:
        print("\n  chan oder pid fehlen -- aus den Ausgaben oben ablesen und "
              "mit --chan/--pid nachreichen.")
        os.close(fd)
        return 1
    if not a.go:
        print("\nTrockenlauf. Mit --go wirklich senden.")
        os.close(fd)
        return 0

    body, ok = send(fd, call, timeout=60.0, idle=3.0)
    print(body + "\n")
    os.close(fd)

    print("=== 4. Weiter ===")
    print("  Log lesen:      ./uart-uboot.py elog -o /tmp/elog-vpinit.txt")
    print("  Linux booten:   ./uart-uboot.py run -c '%s' -t 120" % NETBOOT_ONLY)
    print("  (NICHT 'run bootcmd' -- das startet h713_disp init ein zweites Mal.)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--port")
    ap.add_argument("-b", "--baud", type=int, default=115200)
    sub = ap.add_subparsers(dest="what", required=True)

    c = sub.add_parser("catch", help="Prompt beim Kaltstart abfangen")
    c.add_argument("-t", "--timeout", type=float, default=300.0)
    c.set_defaults(fn=cmd_catch)

    r = sub.add_parser("run", help="Befehle am Prompt")
    r.add_argument("-c", "--cmd", action="append", default=[])
    r.add_argument("-f", "--file")
    r.add_argument("-o", "--out")
    r.add_argument("-t", "--timeout", type=float, default=8.0)
    r.add_argument("-i", "--idle", type=float, default=0.6)
    r.set_defaults(fn=cmd_run)

    d = sub.add_parser("fwdump", help="Firmware-Speicher lesen")
    d.add_argument("va")
    d.add_argument("size")
    d.add_argument("-o", "--out")
    d.set_defaults(fn=cmd_fwdump)

    e = sub.add_parser("elog", help="MIPS-elog aus dem Ring holen")
    e.add_argument("-o", "--out")
    e.add_argument("-g", "--grep", help="nur passende Zeilen ausgeben")
    e.add_argument("-m", "--max-bytes", type=int, default=0,
                   help="hoechstens N Byte, vom Ende her")
    e.add_argument("--ptrs", action="store_true",
                   help="nur die Zeiger, nichts holen -- vor/nach init "
                        "aufrufen, die Differenz beweist die Herkunft")
    e.set_defaults(fn=cmd_elog)

    p = sub.add_parser("chanpid", help="chan/pid/id fuer commcall")
    p.add_argument("--raw", type=int, default=2, help="Roh-Eintraege (fuer pid)")
    p.set_defaults(fn=cmd_chanpid)

    v = sub.add_parser("vpinit", help="init + commcall THal_Vp_Init (Session Z)")
    v.add_argument("--project", default="30", help="ProjectID hex, unser Board 30")
    v.add_argument("--elog", type=int, default=3, help="elog-Level 0..5")
    v.add_argument("--chan", help="statt aus commdev zu raten")
    v.add_argument("--pid", help="statt aus calltable zu raten")
    v.add_argument("--raw", type=int, default=2)
    v.add_argument("--go", action="store_true", help="wirklich senden")
    v.add_argument("--force", action="store_true", help="ohne deadbeef weitermachen")
    v.set_defaults(fn=cmd_vpinit)

    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
