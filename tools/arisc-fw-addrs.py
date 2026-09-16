#!/usr/bin/env python3
"""arisc-fw-addrs.py -- resolve the ARISC firmware's SRAM addresses from the image.

Host-side model of the resolver in drivers/soc/sunxi/sun50i-h713-arisc.c (kernel
patch 0091a). It runs the same two signatures, the same cross-checks and the same
arithmetic over the same words, so what it prints for an image is what the driver
will resolve for that image - and if it refuses an image here, the driver refuses
the probe there.

Why this exists: every H713 board runs the ARISC build out of its own vendor dump.
The driver was reverse-engineered on the HY310's build (v1.3-3-g293ff69, Jul 2025);
in the HY300 Pro's build (v0.8-4-g792f93b-dirty, Dec 2024) the same data sits
0x338/0x340 bytes lower. Hard-coded addresses therefore hit the firmware's IR
sample array and its stack on that board instead of the objects they name
(doku/126, analysis A9).

  arisc-fw-addrs.py <h713-arisc.bin> [more images ...]
  arisc-fw-addrs.py --table <image ...>     one column per image, for a report

The image is the file request_firmware() loads (DT firmware-name[0], normally
/lib/firmware/h713-arisc.bin), 176132 bytes from the vendor dump. ARISC address ==
file offset; the ARM sees the first 0x23000 bytes at 0x00100000.
"""

import struct
import sys

# ---- what the driver reads -------------------------------------------------
IMAGE_SIZE = 0x23000    # SRAM_IMAGE_SIZE: the part of the file that is loaded
SCAN_START = 0x1000     # first word of code the signatures look at
SCAN_END = 0x14000      # code ends here, rodata follows
PAIR_SPAN = 9           # instructions a l.movhi may wait for its l.ori
WIN_GDATA = 5           # l.sb 2(r5) after the l.ori
WIN_PUMP = 16           # l.addi fp,fp,136 and l.addi r22,fp,5 after the l.ori
WIN_SCRATCH = 5         # l.addi r5,r0,65 / l.jal / l.lbz r3,1(fp)

# ---- the distances inside the two structures (fixed in all known builds) ----
GDATA_HPD_COUNTER = -16
GDATA_EDID_READY = 2
GDATA_EDID_GATE = 3
GDATA_PORTMAP = 12
GDATA_SCRATCH = 228
PUMP_BUF = 5

# ---- the driver's own use of those addresses, for the bound check ----------
SCRATCH_LEN = 65
PAYLOAD_MAX = 67
PORTMAP_STRIDE = 8
HDMI_PORTS = 3

# ---- ORBIS32 words the signatures match ------------------------------------
OP_JAL = 0x01
OP_MOVHI = 0x06
OP_ORI = 0x2A
OP_SB = 0x36

MOVHI1_R5 = 0x18A00001          # l.movhi r5, 0x1
MOVHI1_FP = 0x18400001          # l.movhi fp, 0x1
MOVHI1_R14 = 0x19C00001         # l.movhi r14, 0x1
MOVHI1_R3 = 0x18600001          # l.movhi r3, 0x1
MOVHI1_R6 = 0x18C00001          # l.movhi r6, 0x1
MOVHI1_SP = 0x18200001          # l.movhi sp, 0x1
ADDI_FP_FP_136 = 0x9C420088     # l.addi fp, fp, 136   channel-2 context
ADDI_R22_FP_5 = 0x9EC20005      # l.addi r22, fp, 5    payload pointer
ADDI_R5_R0_65 = 0x9CA00041      # l.addi r5, r0, 65    memset length
LBZ_R3_1_FP = 0x8C620001        # l.lbz r3, 1(fp)      payload[1]
SW_0_R5_R0 = 0xD4050000         # l.sw 0(r5), r0       BSS clear store
SFLTU_R5_R6 = 0xE4853000        # l.sfltu r5, r6
BF_BACK_2 = 0x13FFFFFE          # l.bf -2
ADDI_R5_R5_4 = 0x9CA50004       # l.addi r5, r5, 4
ORI_SELF_R5 = 0xA8A50000        # l.ori r5, r5, lo
ORI_SELF_R6 = 0xA8C60000        # l.ori r6, r6, lo
ORI_SELF_SP = 0xA8210000        # l.ori sp, sp, lo

# The 20-byte ROM port map table, byte-identical in every build seen: mask, tag,
# pin, 1 << pin per port. Words as the file holds them (pre-swapped), which is
# the logical big-endian value of each group of four bytes.
ROM_TABLE = (0x01100001, 0x00000000, 0x02200102, 0x01000000, 0x04300204)

# The build the driver's old constants were read out of. Its addresses must come
# out byte-for-byte as they stood in the source, or the resolver has drifted.
HY310_VERSION = b"projector-tv303-android11-v1.3-3-g293ff69"
HY310_EXPECTED = {
    "gdata": 0x1723C, "hpd_counter": 0x1722C, "edid_ready": 0x1723E,
    "edid_gate": 0x1723F, "portmap": 0x17248, "scratch": 0x17320,
    "rpm_state": 0x15F54, "rpm_buf": 0x15F59,
    "bss_start": 0x15F38, "bss_end": 0x175B0, "stack_top": 0x179B0,
}
VERSION_PREFIX = b"projector-tv303-"

ORDER = ("gdata", "rpm_state", "rpm_buf", "hpd_counter", "edid_ready",
         "edid_gate", "portmap", "scratch")


class Refused(Exception):
    """What the driver prints instead of probing."""


def word(data, pc):
    """The instruction word at ARISC address pc, as the loader reads it."""
    return struct.unpack_from("<I", data, pc)[0]


def image_byte(data, off):
    """Logical byte at off: the image stores every word byte-reversed."""
    return data[(off & ~3) + 3 - (off & 3)]


def pair_end(data, pc, rd):
    """Address of the l.ori rd,rd,lo that completes the l.movhi rd,1 at pc.

    Returns None when rd is written again first - then the l.movhi belonged to
    something else.
    """
    for p in range(pc + 4, pc + 4 * (PAIR_SPAN + 1), 4):
        w = word(data, p)
        if (w >> 26) == OP_ORI and (w >> 21) & 31 == rd and (w >> 16) & 31 == rd:
            return p
        if (w >> 26) == OP_MOVHI and (w >> 21) & 31 == rd:
            return None
    return None


def sb_imm(w):
    """Displacement of a l.sb/l.sw/l.sh (split immediate)."""
    return (((w >> 21) & 31) << 11) | (w & 0x7FF)


def scan(data, sig, rom=0):
    """Distinct values a signature yields. (count, value) - count 1 is a hit."""
    movhi, rd = {"gdata": (MOVHI1_R5, 5), "pump": (MOVHI1_FP, 2),
                 "scratch": (MOVHI1_R14, 14), "portmap": (MOVHI1_R3, 3)}[sig]
    hits, last = 0, 0
    for pc in range(SCAN_START, SCAN_END - 4 * (PAIR_SPAN + WIN_PUMP + 2), 4):
        if word(data, pc) != movhi:
            continue
        ori = pair_end(data, pc, rd)
        if ori is None:
            continue
        value = 0x10000 | (word(data, ori) & 0xFFFF)
        if sig == "gdata":
            # the executor materialises g_Data and stores bEdidDataReady at +2
            ok = any((lambda w: (w >> 26) == OP_SB and (w >> 16) & 31 == 5
                      and sb_imm(w) == 2)(word(data, ori + 4 * k))
                     for k in range(1, WIN_GDATA + 1))
        elif sig == "pump":
            # the receive pump holds its context here: +136 is the channel-2
            # context, +5 the payload pointer the classifier reads from
            win = [word(data, ori + 4 * k) for k in range(1, WIN_PUMP + 1)]
            ok = ADDI_FP_FP_136 in win and ADDI_R22_FP_5 in win
        elif sig == "scratch":
            # the 0x11 group handler's head: memset(scratch, 0, 65), then it
            # reads payload[1] to pick the sub-command
            head = [word(data, ori + 4 * k) for k in range(1, 4)]
            tail = [word(data, ori + 4 * k) for k in range(2, WIN_SCRATCH + 1)]
            ok = (ADDI_R5_R0_65 in head
                  and any((w >> 26) == OP_JAL for w in head)
                  and LBZ_R3_1_FP in tail)
        else:
            # the init copier: the only code that materialises the ROM table,
            # and the l.ori one word earlier carries the port map
            ok = False
            if value == rom:
                w = word(data, ori - 4)
                ry = (w >> 21) & 31
                if (w >> 26) == OP_ORI and ry != rd and (w >> 16) & 31 == ry:
                    movhi_ry = (OP_MOVHI << 26) | (ry << 21) | 1
                    for q in range(ori - 4 - 4 * PAIR_SPAN, ori - 4, 4):
                        if q >= SCAN_START and word(data, q) == movhi_ry:
                            ok = True
                            value = 0x10000 | (w & 0xFFFF)
                            break
        if not ok or (hits and value == last):
            continue
        last = value
        hits += 1
    return hits, last


def rom_table(data):
    """Offset of the ROM port map table literal; 0 unless it is unique."""
    hits = []
    for off in range(SCAN_END, IMAGE_SIZE - 4 * len(ROM_TABLE), 4):
        if all(word(data, off + 4 * i) == ROM_TABLE[i]
               for i in range(len(ROM_TABLE))):
            hits.append(off)
    return hits[0] if len(hits) == 1 else 0


def memory_map(data):
    """(bss_start, bss_end) from the clear loop; 0,0 unless it is unique."""
    hits = []
    for pc in range(SCAN_START, SCAN_END - 32, 4):
        w = [word(data, pc + 4 * k) for k in range(8)]
        if (w[0] == MOVHI1_R5 and w[1] & 0xFFFF0000 == ORI_SELF_R5
                and w[2] == MOVHI1_R6 and w[3] & 0xFFFF0000 == ORI_SELF_R6
                and w[4] == SW_0_R5_R0 and w[5] == SFLTU_R5_R6
                and w[6] == BF_BACK_2 and w[7] == ADDI_R5_R5_4):
            hits.append((0x10000 | (w[1] & 0xFFFF), 0x10000 | (w[3] & 0xFFFF)))
    return hits[0] if len(hits) == 1 else (0, 0)


def stack_top(data):
    """The sp the firmware starts with; 0 unless the init is unique."""
    hits = []
    for pc in range(SCAN_START, SCAN_END - 32, 4):
        if word(data, pc) == MOVHI1_SP and \
           word(data, pc + 4) & 0xFFFF0000 == ORI_SELF_SP:
            hits.append(0x10000 | (word(data, pc + 4) & 0xFFFF))
    return hits[0] if len(hits) == 1 else 0


def image_version(data, size=64):
    """The firmware's git describe, as bytes, or b'' when it is not there.

    The driver reads it into a 64-byte field, so the same bound applies here.
    """
    for off in range(SCAN_END, IMAGE_SIZE - size):
        if all(image_byte(data, off + i) == VERSION_PREFIX[i]
               for i in range(len(VERSION_PREFIX))):
            out = bytearray()
            while len(out) < size - 1:
                b = image_byte(data, off + len(out))
                if b < 0x20 or b > 0x7E:
                    break
                out.append(b)
            return bytes(out)
    return b""


def resolve(data):
    """The eight addresses plus the memory map, or Refused with the reason."""
    if len(data) < IMAGE_SIZE:
        raise Refused("image is %d bytes, at least %d needed"
                      % (len(data), IMAGE_SIZE))
    hits, gdata = scan(data, "gdata")
    if hits != 1:
        raise Refused("g_Data anchor: %d candidates, need exactly one" % hits)
    hits, pump = scan(data, "pump")
    if hits != 1:
        raise Refused("receive pump anchor: %d candidates, need exactly one"
                      % hits)
    o = {
        "gdata": gdata,
        "hpd_counter": gdata + GDATA_HPD_COUNTER,
        "edid_ready": gdata + GDATA_EDID_READY,
        "edid_gate": gdata + GDATA_EDID_GATE,
        "portmap": gdata + GDATA_PORTMAP,
        "scratch": gdata + GDATA_SCRATCH,
        "rpm_state": pump,
        "rpm_buf": pump + PUMP_BUF,
    }
    # cross-check 1: the group handler's own memset target is the scratch
    hits, scratch = scan(data, "scratch")
    if hits != 1:
        raise Refused("scratch cross-check: %d candidates" % hits)
    if scratch != o["scratch"]:
        raise Refused("scratch cross-check: signature 0x%05x, g_Data+%d 0x%05x"
                      % (scratch, GDATA_SCRATCH, o["scratch"]))
    # cross-check 2: the init copier's own store target is the port map
    rom = rom_table(data)
    if not rom:
        raise Refused("ROM port map table literal not found or not unique")
    hits, portmap = scan(data, "portmap", rom)
    if hits != 1:
        raise Refused("port map cross-check: %d candidates" % hits)
    if portmap != o["portmap"]:
        raise Refused("port map cross-check: signature 0x%05x, g_Data+%d 0x%05x"
                      % (portmap, GDATA_PORTMAP, o["portmap"]))
    o["rom_table"] = rom
    # the image states its own memory map; nothing may be written above the BSS
    o["bss_start"], o["bss_end"] = memory_map(data)
    o["stack_top"] = stack_top(data)
    if not o["bss_start"] or not o["stack_top"]:
        raise Refused("memory map: BSS clear loop or sp init not found")
    if not (o["bss_start"] < o["bss_end"] <= o["stack_top"] <= IMAGE_SIZE):
        raise Refused("memory map: bss 0x%05x..0x%05x, stack top 0x%05x"
                      % (o["bss_start"], o["bss_end"], o["stack_top"]))
    for name, last in (("hpd_counter", HDMI_PORTS),
                       ("edid_ready", 1), ("edid_gate", 1),
                       ("portmap", HDMI_PORTS * PORTMAP_STRIDE),
                       ("scratch", SCRATCH_LEN),
                       ("rpm_state", 4), ("rpm_buf", PAYLOAD_MAX)):
        if o[name] < o["bss_start"] or o[name] + last > o["bss_end"]:
            raise Refused("%s 0x%05x..0x%05x is outside the BSS 0x%05x..0x%05x"
                          % (name, o[name], o[name] + last - 1,
                             o["bss_start"], o["bss_end"]))
    o["version"] = image_version(data)
    if o["version"] == HY310_VERSION:
        for name in sorted(HY310_EXPECTED):
            if o[name] != HY310_EXPECTED[name]:
                raise Refused("HY310 build: %s resolved 0x%05x, expected 0x%05x"
                              % (name, o[name], HY310_EXPECTED[name]))
    return o


def read_image(path):
    with open(path, "rb") as f:
        return f.read()


def print_table(rows):
    """One column per image, one row per address: the table for a report."""
    print("%-3s %-34s %s" % ("no", "image", "version"))
    for i, (path, o) in enumerate(rows, 1):
        print("%-3d %-34s %s" % (i, path.split("/")[-1].split("\\")[-1],
                                 o["version"].decode("ascii", "replace")))
    print("")
    head = "".join("%-12d" % (i + 1) for i in range(len(rows)))
    print(("%-13s %s" % ("symbol", head)).rstrip())
    fields = ORDER + (("bss_start", "bss_end", "stack_top"))
    for name in fields:
        cells = "".join("0x%05x     " % o[name] for _, o in rows)
        print(("%-13s %s" % (name, cells)).rstrip())


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    table = "--table" in argv[1:]
    if not args:
        sys.stderr.write(__doc__.split("\n\n")[0] + "\n\nusage: %s [--table]"
                         " <h713-arisc.bin> ...\n" % argv[0])
        return 2
    rc = 0
    rows = []
    for path in args:
        data = read_image(path)
        try:
            o = resolve(data)
        except Refused as why:
            print("%s REFUSED: %s" % (path.split("/")[-1], why))
            rc = 1
            continue
        if table:
            rows.append((path, o))
            continue
        print("%s" % path)
        print("  version     %s" % o["version"].decode("ascii", "replace"))
        for name in ORDER:
            print("  %-11s 0x%05x" % (name, o[name]))
        print("  bss         0x%05x..0x%05x" % (o["bss_start"],
                                                o["bss_end"] - 1))
        print("  stack       0x%05x..0x%05x" % (o["bss_end"],
                                                o["stack_top"] - 1))
        print("  rom table   0x%05x" % o["rom_table"])
        if o["version"] == HY310_VERSION:
            print("  HY310 build: all addresses equal the expected set")
    if rows:
        print_table(rows)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
