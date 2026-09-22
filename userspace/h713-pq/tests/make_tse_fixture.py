#!/usr/bin/env python3
"""Build a synthetic TSE file for the h713-pq tests.

No vendor byte is copied: the grammar is written out from AP3f 1.2 (header,
group, module, state, attribute records), AP3p 1.5 (the gamma payload) and
AP3r 1.1 (the UI_ColorTemp selectors), the curves are invented here. The three
channels end on three different values on purpose -- that is where a board's
white balance lives (AP3r 1.4).

Usage:  python3 make_tse_fixture.py <file> [project-id]
"""

import struct
import sys
import zlib

GAMMA_PLUGIN = 0x00090009
UI_COLOR_TEMP = 0x3003
#: The vendor's own state order: warm, cool, normal (AP3r 1.1).
STATE_TEMPS = (0x30030001, 0x30030000, 0x30030002)
#: Per state and channel: end point and exponent of the invented curve.
CURVES = (
    ((4000, 1.35), (3800, 1.40), (3600, 1.50)),      # "warm"
    ((3400, 1.50), (3700, 1.42), (4090, 1.30)),      # "cool"
    ((3900, 1.38), (4090, 1.36), (4020, 1.34)),      # "normal"
)


def curve(end, exponent):
    """1024 monotone samples of 12 bit, ending exactly on ``end``."""
    return [int(round(end * pow(x / 1023.0, exponent))) for x in range(1024)]


def gamma_state_blob(banks):
    """Three banks of 1024 samples -> 512 records of 9 bytes (AP3p 1.5)."""
    out = bytearray()
    for i in range(512):
        low = [banks[c][2 * i] for c in range(3)]
        high = [banks[c][2 * i + 1] for c in range(3)]
        out += bytes(low[c] & 0xFF for c in range(3))
        out += bytes(high[c] & 0xFF for c in range(3))
        out += bytes(((high[c] >> 4) & 0xF0) | ((low[c] >> 8) & 0x0F)
                     for c in range(3))
    return bytes(out)


def _name(text):
    raw = text.encode("ascii") + b"\0"
    return bytes([len(raw)]) + raw


def _attrs(pairs):
    """TFDAttrProp::Load: u16 tag 4, 2 header bytes, u32 count, records."""
    out = struct.pack("<HHI", 4, 1, len(pairs))
    for tag, values in pairs:
        out += struct.pack("<HI", tag, len(values))
        out += b"".join(struct.pack("<I", v) for v in values)
    return out


def gamma_module(project, states):
    """One TTFDGammaFW module with its states and its payload."""
    body = struct.pack("<HHIIB", 13, 1, len(states), 0x00049002, 2)
    body += _name("Gamma_0x%04x" % project)
    body += struct.pack("<I", len(states))
    for index in range(len(states)):
        body += struct.pack("<HHHH", 8, 1, 0x2000 + 0x1000 * index, 0x4900)
        body += _attrs([(5, [0x00050000]), (UI_COLOR_TEMP, [STATE_TEMPS[index]])])
    payload = struct.pack("<I", len(states))
    for blob in states:
        payload += struct.pack("<I", len(blob)) + blob
    body += struct.pack("<II", GAMMA_PLUGIN, 1)
    body += struct.pack("<II", 0x20000009, len(payload)) + payload
    body += _attrs([])
    return body


def build(path, project=0x0030):
    banks = [[curve(end, exponent) for end, exponent in state]
             for state in CURVES]
    module = gamma_module(project, [gamma_state_blob(b) for b in banks])
    group = struct.pack("<HHIIBHH", 17, 1, 1, 0x49, 2, project, 0)
    group += _name("ProjectID_0x%04x" % project)
    group += struct.pack("<I", 1) + module
    body = struct.pack("<I", 1) + group
    header = (b"TSE" + bytes([2]) + struct.pack("<HIIHHII", 26, 0x1891B001,
              0x66F64E84, project, 0, 26 + len(body), zlib.crc32(body)))
    with open(str(path), "wb") as f:
        f.write(header + body)
    return banks


if __name__ == "__main__":
    build(sys.argv[1], int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x0030)
    print(sys.argv[1])
